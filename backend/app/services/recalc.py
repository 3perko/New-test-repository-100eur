"""Conscious recalculation of rate snapshots (audited)."""
from datetime import date

from fastapi import HTTPException

from app.models import BillingStatement, TimesheetEntry, Trip
from app.services import audit, calc


def _locked(db, statement_id) -> bool:
    if not statement_id:
        return False
    st = db.get(BillingStatement, statement_id)
    return bool(st and st.status == "closed")


def _recalc(ctx, items, kind: str) -> int:
    db = ctx.db
    n = 0
    for obj in items:
        if obj.company_id != ctx.company_id or _locked(db, obj.billing_statement_id):
            continue
        if kind == "timesheet":
            before = (obj.cost_rate, obj.billing_rate, obj.cost_amount, obj.billable_amount)
            calc.apply_timesheet(db, obj, refresh_rates=True, hours_explicit=True)
            after = (obj.cost_rate, obj.billing_rate, obj.cost_amount, obj.billable_amount)
            keys = ("cost_rate", "billing_rate", "cost_amount", "billable_amount")
        else:
            before = (obj.km_effective, obj.rate_per_km, obj.cost_amount, obj.billable_amount)
            calc.apply_trip(db, obj, refresh_rates=True)
            after = (obj.km_effective, obj.rate_per_km, obj.cost_amount, obj.billable_amount)
            keys = ("km_effective", "rate_per_km", "cost_amount", "billable_amount")
        if before != after:
            n += 1
            audit.log(db, user_id=ctx.user.id, company_id=ctx.company_id,
                      entity="timesheets" if kind == "timesheet" else "trips", entity_id=obj.id, action="recalculate",
                      changes={k: (a, b) for k, a, b in zip(keys, before, after) if a != b})
    db.commit()
    return n


def recalc_ids(ctx, kind: str, ids: list[int]) -> int:
    if not ctx.is_admin:
        raise HTTPException(403, "Len pre administrátora.")
    model = TimesheetEntry if kind == "timesheet" else Trip
    items = ctx.db.query(model).filter(model.id.in_(ids)).all()
    return _recalc(ctx, items, kind)


def recalc_period(ctx, kind: str, d_from: date, d_to: date) -> int:
    if not ctx.is_admin:
        raise HTTPException(403, "Len pre administrátora.")
    model = TimesheetEntry if kind == "timesheet" else Trip
    items = (ctx.db.query(model).filter(model.company_id == ctx.company_id, model.date >= d_from, model.date <= d_to)
             .all())
    return _recalc(ctx, items, kind)
