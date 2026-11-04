"""Local storage of source files (content addressed by sha256)."""
import hashlib
import mimetypes
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_config
from app.models import SourceFile


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def guess_mime(name: str, data: bytes) -> str:
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] in (b"RIFF",) and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"):
        return "image/heic"
    if data[:2] == b"PK":
        if name.lower().endswith(".xlsx"):
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    m, _ = mimetypes.guess_type(name)
    return m or "application/octet-stream"


def store_file(db: Session, *, company_id: int, name: str, data: bytes, source: str, kind_hint: str = "auto",
               physical: bool = False, drive_file_id: str | None = None, user_id: int | None = None,
               note: str | None = None) -> tuple[SourceFile, bool]:
    """Store the file; returns (source_file, is_new). Identical content (same hash) in the same company is not stored twice."""
    digest = sha256(data)
    existing = (db.query(SourceFile).filter(SourceFile.company_id == company_id, SourceFile.sha256 == digest)
                .order_by(SourceFile.id).first())
    if existing:
        return existing, False
    cfg = get_config()
    today = date.today()
    ext = Path(name).suffix.lower()[:10]
    rel = Path(str(company_id)) / f"{today:%Y}" / f"{today:%m}" / f"{digest}{ext}"
    full = Path(cfg.storage_dir) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(data)
    sf = SourceFile(company_id=company_id, original_name=name[:500], storage_path=str(rel), sha256=digest,
                    mime=guess_mime(name, data), size=len(data), source=source, kind_hint=kind_hint,
                    physical=physical, drive_file_id=drive_file_id, uploaded_by=user_id, note=note, status="new")
    db.add(sf)
    db.flush()
    return sf, True


def read_file(sf: SourceFile) -> bytes:
    return (Path(get_config().storage_dir) / sf.storage_path).read_bytes()


def file_path(sf: SourceFile) -> Path:
    return Path(get_config().storage_dir) / sf.storage_path
