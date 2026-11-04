"""Inbox run (manual or scheduled): Gmail -> Drive -> processing."""
import logging

from sqlalchemy.orm import Session

from app.models import Company
from app.services import google, ingest
from app.services.settings import set_value

log = logging.getLogger(__name__)


def run_inbox(db: Session, company: Company, *, use_google: bool = True) -> dict:
    out: dict = {"company": company.name, "gmail": None, "drive": None, "errors": []}
    if use_google and google.status(db)["connected"]:
        try:
            out["gmail"] = google.fetch_gmail(db, [company])
        except google.GoogleError as exc:
            out["errors"].append(f"Gmail: {exc}")
        try:
            out["drive"] = google.sync_drive(db, company)
        except google.GoogleError as exc:
            out["errors"].append(f"Drive: {exc}")
    out["processed"] = ingest.process_pending(db, company.id)
    from datetime import datetime, timezone
    set_value(db, "inbox.last_run", datetime.now(timezone.utc).isoformat(), company.id)
    db.commit()
    return out


def run_all(db: Session) -> list[dict]:
    results = []
    for c in db.query(Company).filter(Company.active.is_(True)).all():
        try:
            results.append(run_inbox(db, c))
        except Exception as exc:  # noqa: BLE001
            log.exception("Inbox run failed for %s", c.name)
            db.rollback()
            results.append({"company": c.name, "errors": [str(exc)]})
    return results
