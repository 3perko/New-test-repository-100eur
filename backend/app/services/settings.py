"""Global and per-company parameters with typed defaults."""
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import Setting


@dataclass(frozen=True)
class ParamDef:
    key: str
    label: str
    type: str  # number | text | bool | time | list
    default: Any
    company_level: bool = True
    help: str = ""


PARAMS: list[ParamDef] = [
    ParamDef("trip_km_surcharge_pct", "Prirážka k default vzdialenosti jazdy (%)", "number", 10,
             help="Ak nie sú zadané km: 2 × jednosmerná vzdialenosť + táto prirážka."),
    ParamDef("hours_rounding", "Zaokrúhlenie hodín (h)", "number", 0.25,
             help="Hodiny vypočítané z času od–do sa zaokrúhlia na tento násobok. 0 = bez zaokrúhlenia."),
    ParamDef("material_doc_days", "Dni na doloženie dokladu k nákupu materiálu", "number", 7),
    ParamDef("material_markup_pct", "Default prirážka na materiál pri fakturácii (%)", "number", 0),
    ParamDef("default_vat_rate", "Default sadzba DPH pre podklad k fakturácii (%)", "number", 23),
    ParamDef("fleet_alert_days", "Predstih upozornení vozového parku (dni)", "number", 30),
    ParamDef("service_alert_km", "Predstih upozornenia na servis (km)", "number", 1000),
    ParamDef("bank_match_days", "Tolerancia dní pri párovaní banky", "number", 5),
    ParamDef("duplicate_time_tolerance_min", "Tolerancia času pri hľadaní duplicitných bločkov (min)", "number", 2),
    ParamDef("overhead_keywords", "Kľúčové slová dodávateľov/položiek pre Réžiu (čerpacie stanice a pod.)", "list",
             ["slovnaft", "omv", "shell", "orlen", "lukoil", "mol ", "čerpacia", "cerpacia", "nafta", "diesel",
              "benzín", "benzin", "natural 95", "pohonné"]),
    ParamDef("inbox_schedule_time", "Čas automatického spracovania inboxu (HH:MM)", "time", "20:00",
             company_level=False),
    ParamDef("inbox_physical_default", "Súbory z Drive inboxu považovať za sken fyzického originálu", "bool", True),
]
PARAM_MAP = {p.key: p for p in PARAMS}


def _load(db: Session, company_id: int | None, key: str) -> Any:
    row = db.query(Setting).filter(Setting.company_id.is_(None) if company_id is None else Setting.company_id == company_id,
                                   Setting.key == key).first()
    if row is None or row.value is None:
        return None
    return json.loads(row.value)


def get_param(db: Session, key: str, company_id: int | None = None) -> Any:
    p = PARAM_MAP.get(key)
    if company_id is not None:
        v = _load(db, company_id, key)
        if v is not None:
            return v
    v = _load(db, None, key)
    if v is not None:
        return v
    return p.default if p else None


def set_value(db: Session, key: str, value: Any, company_id: int | None = None) -> None:
    q = db.query(Setting).filter(Setting.key == key)
    q = q.filter(Setting.company_id.is_(None)) if company_id is None else q.filter(Setting.company_id == company_id)
    row = q.first()
    if value is None:
        if row:
            db.delete(row)
        return
    if row is None:
        row = Setting(company_id=company_id, key=key)
        db.add(row)
    row.value = json.dumps(value, ensure_ascii=False)


def get_value(db: Session, key: str, company_id: int | None = None) -> Any:
    return _load(db, company_id, key)
