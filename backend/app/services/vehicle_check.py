"""Vehicle data verification against public services.

One adapter per service. If a service offers an API the adapter implements `check()` and the result is
compared with our records automatically; otherwise it offers a link to the official verification page
(the UI copies the plate number). No CAPTCHA circumvention, no scraping against terms of service.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Vehicle, VehicleCheck, VehicleInsurance, VehicleVignette
from app.services.settings import get_value


@dataclass
class Adapter:
    service: str
    label: str
    url: str
    has_api: bool = False
    note: str = ""

    def link(self, v: Vehicle) -> str:
        return self.url.replace("{plate}", (v.plate or "").replace(" ", "")).replace("{vin}", v.vin or "")

    def check(self, v: Vehicle) -> dict:  # pragma: no cover - no public API available today
        raise NotImplementedError


ADAPTERS: dict[str, Adapter] = {
    "vignette": Adapter("vignette", "Diaľničná známka (eznamka.sk)", "https://eznamka.sk/sk/",
                        note="Na stránke zvoľte „Overiť platnosť“, zadajte krajinu SK a ŠPZ presne ako na tabuľke."),
    "pzp": Adapter("pzp", "PZP (Slovenská kancelária poisťovateľov)", "https://www.skp.sk/",
                   note="Overenie platnosti PZP podľa EČV v aplikácii SKP."),
    "stk": Adapter("stk", "STK / TK (TÜV SÜD)",
                   "https://www.tuvsud.com/sk-sk/odvetvia/automobilovy-priemysel/stk-a-kontrola-originality/overenie-stk",
                   note="Online overenie platnosti TK a EK."),
    "ek": Adapter("ek", "EK (TÜV SÜD)",
                  "https://www.tuvsud.com/sk-sk/odvetvia/automobilovy-priemysel/stk-a-kontrola-originality/overenie-stk",
                  note="Online overenie platnosti TK a EK."),
}


def adapters(db: Session) -> list[Adapter]:
    out = []
    for key, a in ADAPTERS.items():
        custom = get_value(db, f"vehicle_check_url_{key}")
        out.append(Adapter(a.service, a.label, custom or a.url, a.has_api, a.note))
    return out


def recorded_valid_to(db: Session, v: Vehicle, service: str) -> date | None:
    if service == "stk":
        return v.stk_valid_to
    if service == "ek":
        return v.ek_valid_to
    if service == "pzp":
        return db.query(func.max(VehicleInsurance.valid_to)).filter(VehicleInsurance.vehicle_id == v.id,
                                                                    VehicleInsurance.insurance_type == "pzp").scalar()
    if service == "vignette":
        return db.query(func.max(VehicleVignette.valid_to)).filter(VehicleVignette.vehicle_id == v.id,
                                                                   VehicleVignette.country == "SK").scalar()
    return None


def compare_with_records(db: Session, chk: VehicleCheck) -> bool | None:
    v = db.get(Vehicle, chk.vehicle_id)
    if v is None:
        return None
    rec = recorded_valid_to(db, v, chk.service)
    today = date.today()
    rec_valid = rec is not None and rec >= today
    if chk.result == "valid":
        if chk.valid_to is not None and rec is not None:
            return chk.valid_to == rec
        return rec_valid
    if chk.result == "invalid":
        return not rec_valid
    return None


def status(db: Session, company_id: int) -> list[dict]:
    rows = []
    for v in db.query(Vehicle).filter(Vehicle.company_id == company_id, Vehicle.active.is_(True)).order_by(Vehicle.name):
        services = []
        for a in adapters(db):
            last = (db.query(VehicleCheck).filter(VehicleCheck.vehicle_id == v.id, VehicleCheck.service == a.service)
                    .order_by(VehicleCheck.checked_at.desc()).first())
            rec = recorded_valid_to(db, v, a.service)
            services.append({
                "service": a.service, "label": a.label, "url": a.link(v), "has_api": a.has_api, "note": a.note,
                "recorded_valid_to": rec.isoformat() if rec else None,
                "last_check": None if not last else {
                    "id": last.id, "checked_at": last.checked_at.isoformat(), "result": last.result,
                    "valid_to": last.valid_to.isoformat() if last.valid_to else None, "matches": last.matches,
                    "method": last.method, "note": last.note},
            })
        rows.append({"vehicle_id": v.id, "name": v.name, "plate": v.plate, "vin": v.vin, "services": services})
    return rows


def run_api_checks(db: Session, company_id: int) -> int:
    """Run automatic checks for adapters with an API (scheduled). Returns number of checks stored."""
    n = 0
    for v in db.query(Vehicle).filter(Vehicle.company_id == company_id, Vehicle.active.is_(True)):
        for a in adapters(db):
            if not a.has_api:
                continue
            try:
                res = a.check(v)
            except Exception as exc:  # noqa: BLE001
                res = {"result": "error", "note": str(exc)}
            chk = VehicleCheck(vehicle_id=v.id, service=a.service, checked_at=datetime.now(timezone.utc), method="api",
                               result=res.get("result", "unknown"), valid_to=res.get("valid_to"),
                               found_data=str(res.get("data") or ""), note=res.get("note"))
            chk.matches = compare_with_records(db, chk)
            db.add(chk)
            n += 1
    return n
