"""Deterministic cost calculations: rate lookup, hours, km, snapshots."""
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import Company, Project, TimesheetEntry, Trip, VehicleRate, WorkerRate
from app.services.settings import get_param

CENT = Decimal("0.01")


def money(v) -> Decimal:
    return Decimal(v or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def _valid_on(model, d: date):
    return and_(or_(model.valid_from.is_(None), model.valid_from <= d), or_(model.valid_to.is_(None), model.valid_to >= d))


def resolve_worker_rates(db: Session, worker_id: int, company_id: int | None, project_id: int | None,
                         d: date) -> tuple[Decimal | None, Decimal | None]:
    """Each rate is resolved separately: worker+project -> worker+company -> worker default."""
    candidates = []
    if project_id:
        candidates.append(and_(WorkerRate.project_id == project_id))
    if company_id:
        candidates.append(and_(WorkerRate.project_id.is_(None), WorkerRate.company_id == company_id))
    candidates.append(and_(WorkerRate.project_id.is_(None), WorkerRate.company_id.is_(None)))
    cost = billing = None
    for cond in candidates:
        rows = (db.query(WorkerRate).filter(WorkerRate.worker_id == worker_id, cond, _valid_on(WorkerRate, d))
                .order_by(WorkerRate.valid_from.desc().nullslast(), WorkerRate.id.desc()).all())
        for r in rows:
            if cost is None and r.cost_rate is not None:
                cost = r.cost_rate
            if billing is None and r.billing_rate is not None:
                billing = r.billing_rate
        if cost is not None and billing is not None:
            break
    return cost, billing


def resolve_vehicle_rate(db: Session, vehicle_id: int, d: date) -> Decimal | None:
    r = (db.query(VehicleRate).filter(VehicleRate.vehicle_id == vehicle_id, _valid_on(VehicleRate, d))
         .order_by(VehicleRate.valid_from.desc().nullslast(), VehicleRate.id.desc()).first())
    return r.rate_per_km if r else None


def hours_between(t_from: time, t_to: time, rounding: float | Decimal | None) -> Decimal:
    start = datetime.combine(date(2000, 1, 1), t_from)
    end = datetime.combine(date(2000, 1, 1), t_to)
    if end <= start:  # crosses midnight
        end += timedelta(days=1)
    h = Decimal((end - start).total_seconds()) / Decimal(3600)
    r = Decimal(str(rounding or 0))
    if r > 0:
        h = (h / r).quantize(Decimal(1), rounding=ROUND_HALF_UP) * r
    return h.quantize(CENT)


def apply_timesheet(db: Session, e: TimesheetEntry, *, refresh_rates: bool, hours_explicit: bool) -> None:
    """Compute hours (if not explicit), snapshot rates (if requested) and amounts."""
    if not hours_explicit and e.time_from and e.time_to:
        e.hours = hours_between(e.time_from, e.time_to, get_param(db, "hours_rounding", e.company_id))
    if refresh_rates or e.cost_rate is None and e.billing_rate is None:
        e.cost_rate, e.billing_rate = resolve_worker_rates(db, e.worker_id, e.company_id, e.project_id, e.date)
    h = Decimal(e.hours or 0)
    e.cost_amount = money(h * Decimal(e.cost_rate or 0))
    e.billable_amount = money(h * Decimal(e.billing_rate or 0)) if e.billable else Decimal("0.00")


def trip_km(db: Session, t: Trip) -> tuple[Decimal | None, bool]:
    if t.km is not None:
        return Decimal(t.km), False
    p = db.get(Project, t.project_id) if t.project_id else None
    if p and p.default_km_one_way:
        pct = Decimal(str(get_param(db, "trip_km_surcharge_pct", t.company_id) or 0))
        km = Decimal(2) * Decimal(p.default_km_one_way) * (Decimal(1) + pct / Decimal(100))
        return km.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), True
    return None, True


def apply_trip(db: Session, t: Trip, *, refresh_rates: bool) -> None:
    t.km_effective, t.km_computed = trip_km(db, t)
    if refresh_rates or t.rate_per_km is None:
        t.rate_per_km = resolve_vehicle_rate(db, t.vehicle_id, t.date)
        p = db.get(Project, t.project_id) if t.project_id else None
        t.billing_rate_per_km = p.transport_rate_per_km if p and p.bill_transport else None
    km = Decimal(t.km_effective or 0)
    t.cost_amount = money(km * Decimal(t.rate_per_km or 0))
    t.billable_amount = money(km * Decimal(t.billing_rate_per_km or 0))


def cost_basis_is_net(company: Company) -> bool:
    """VAT payers count costs without VAT, non-payers with VAT."""
    return bool(company.vat_payer)
