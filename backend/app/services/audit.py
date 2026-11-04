import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def _ser(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime, time)):
        return v.isoformat()
    return v


def log(db: Session, *, user_id: int | None, company_id: int | None, entity: str, entity_id: int | None,
        action: str, changes: dict | None = None, note: str | None = None) -> None:
    payload = None
    if changes:
        payload = json.dumps({k: [_ser(a), _ser(b)] for k, (a, b) in changes.items()}, ensure_ascii=False)
    db.add(AuditLog(user_id=user_id, company_id=company_id, entity=entity, entity_id=entity_id, action=action,
                    changes=payload, note=note))
