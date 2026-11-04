from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException

from app.deps import Ctx, get_ctx, require_admin
from app.models import Project
from app.services import recalc, reports, vehicle_check

router = APIRouter(prefix="/api", tags=["reports"])


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


@router.get("/dashboard")
def dashboard(ctx: Ctx = Depends(get_ctx)):
    if ctx.role != "admin":
        return {"counts": {}, "fleet_alerts": [], "missing_recurring": [], "material_without_document": []}
    return reports.dashboard(ctx.db, ctx.company, True)


@router.get("/reports/project-costs")
def project_costs(date_from: str | None = None, date_to: str | None = None, include_unconfirmed: bool = False,
                  include_inactive: bool = False, ctx: Ctx = Depends(require_admin)):
    return reports.project_costs(ctx.db, ctx.company, _d(date_from), _d(date_to), include_unconfirmed, include_inactive)


@router.get("/reports/project/{project_id}")
def project_detail(project_id: int, date_from: str | None = None, date_to: str | None = None,
                   include_unconfirmed: bool = True, ctx: Ctx = Depends(require_admin)):
    p = ctx.db.get(Project, project_id)
    if not p or p.company_id != ctx.company_id:
        raise HTTPException(404, "Zákazka neexistuje v aktívnej firme.")
    out = reports.project_detail(ctx.db, ctx.company, project_id, _d(date_from), _d(date_to), include_unconfirmed)
    out["monthly"] = reports.monthly_breakdown(ctx.db, ctx.company, _d(date_from), _d(date_to), project_id)
    return out


@router.get("/reports/profitability")
def profitability(date_from: str | None = None, date_to: str | None = None, overhead_split: str | None = None,
                  include_inactive: bool = False, ctx: Ctx = Depends(require_admin)):
    return reports.profitability(ctx.db, ctx.company, _d(date_from), _d(date_to), overhead_split, include_inactive)


@router.get("/reports/vat")
def vat(year: int, month: int, ctx: Ctx = Depends(require_admin)):
    return reports.vat_summary(ctx.db, ctx.company, year, month)


@router.get("/reports/monthly-check")
def monthly_check(year: int, month: int, ctx: Ctx = Depends(require_admin)):
    return reports.monthly_check(ctx.db, ctx.company, year, month)


@router.get("/fleet/alerts")
def fleet_alerts(ctx: Ctx = Depends(require_admin)):
    return reports.fleet_alerts(ctx.db, ctx.company_id)


@router.get("/fleet/checks")
def fleet_checks(ctx: Ctx = Depends(require_admin)):
    return vehicle_check.status(ctx.db, ctx.company_id)


@router.post("/fleet/checks/run")
def fleet_checks_run(ctx: Ctx = Depends(require_admin)):
    n = vehicle_check.run_api_checks(ctx.db, ctx.company_id)
    ctx.db.commit()
    return {"message": f"Automatické overenia: {n} (služby bez API overte cez odkaz a zapíšte výsledok)."}


@router.post("/recalculate")
def recalculate(body: dict = Body(...), ctx: Ctx = Depends(require_admin)):
    d_from, d_to = _d(body.get("date_from")), _d(body.get("date_to"))
    if not d_from or not d_to:
        raise HTTPException(422, "Zadajte obdobie.")
    n1 = recalc.recalc_period(ctx, "timesheet", d_from, d_to) if body.get("timesheets", True) else 0
    n2 = recalc.recalc_period(ctx, "trip", d_from, d_to) if body.get("trips", True) else 0
    return {"message": f"Prepočítané hodiny: {n1}, jazdy: {n2} (uzavreté podklady sa nemenia)."}
