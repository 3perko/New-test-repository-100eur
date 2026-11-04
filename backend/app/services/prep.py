"""PDF / image preparation and QR decoding (deterministic)."""
import io
import logging
import re

log = logging.getLogger(__name__)

# eKasa online receipt id: O-<32 hex>; offline: OKP string "<okp>:<cash register code>:<date>:<number>:<total>"
EKASA_ID_RE = re.compile(r"\bO-[0-9A-F]{32}\b", re.IGNORECASE)


def pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:20]).strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("PDF text extraction failed: %s", exc)
        return ""


def pdf_to_images(data: bytes, max_pages: int = 5, scale: float = 2.0) -> list[bytes]:
    """Render PDF pages to PNG (for scanned PDFs / QR detection)."""
    out = []
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(data)
        for i in range(min(len(pdf), max_pages)):
            img = pdf[i].render(scale=scale).to_pil()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            out.append(buf.getvalue())
    except Exception as exc:  # noqa: BLE001
        log.warning("PDF render failed: %s", exc)
    return out


def normalize_image(data: bytes, max_side: int = 2400) -> tuple[bytes, str]:
    """Convert any supported image to JPEG/PNG within size limits for vision APIs."""
    from PIL import Image, ImageOps
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:  # pragma: no cover
        pass
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue(), "image/jpeg"


def decode_qr(image: bytes) -> list[str]:
    """Return all QR payloads found in the image."""
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(image, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:  # e.g. HEIC – convert via Pillow first
            try:
                jpeg, _ = normalize_image(image, max_side=3000)
                img = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            except Exception:  # noqa: BLE001
                return []
        if img is None:
            return []
        det = cv2.QRCodeDetector()
        results: list[str] = []
        for candidate in (img, cv2.resize(img, None, fx=0.5, fy=0.5), cv2.resize(img, None, fx=2, fy=2)):
            try:
                ok, decoded, _, _ = det.detectAndDecodeMulti(candidate)
                if ok:
                    results.extend(d for d in decoded if d)
            except cv2.error:
                pass
            if not results:
                val, _, _ = det.detectAndDecode(candidate)
                if val:
                    results.append(val)
            if results:
                break
        return list(dict.fromkeys(results))
    except Exception as exc:  # noqa: BLE001
        log.warning("QR decode failed: %s", exc)
        return []


def find_ekasa_id(texts: list[str]) -> str | None:
    for t in texts:
        if not t:
            continue
        m = EKASA_ID_RE.search(t)
        if m:
            return m.group(0).upper().replace("O-", "O-", 1)
    return None


def parse_offline_qr(payload: str) -> dict | None:
    """Offline eKasa QR: OKP:KASA:DDMMYYHHMMSS:NUMBER:TOTAL (colon separated)."""
    parts = payload.split(":")
    if len(parts) == 5 and len(parts[2]) == 12 and parts[2].isdigit():
        return {"okp": parts[0], "cash_register_code": parts[1], "datetime": parts[2], "number": parts[3],
                "total": parts[4]}
    return None
