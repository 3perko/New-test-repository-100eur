"""Project costs, profitability, VAT summary, dashboard, monthly check, fleet alerts."""
import calendar
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, literal_column, or_, true
from sqlalchemy.orm import Session

from app.models import (
    Allocation, BankTransaction, BillingStatement, Company, Document, DocumentLine, Project, RecurringInvoiceRule,
    SourceFile, TimesheetEntry, Trip, Vehicle, VehicleInsurance, VehicleService, VehicleVignette, Worker,
)
from app.registry.base import serialize
from app.services.calc import money
from app.services.settings import get_param

ZERO = Decimal(0)


def _f(v) -> float:
    return float(money(v or 0))


def _period(q, col, d_from: date | None, d_to: date | None):
    if d_from:
        q = q.filter(col >= d_from)
    if d_to:
        q = q.filter(col <= d_to)
    return q


def _alloc_amount(company: Company):
    return Allocation.amount_net if company.vat_payer else Allocation.amount_gross


def _material(db: Session, company: Company, d_from, d_to, include_unconfirmed: bool, direction="cost"):
    """{project_id: {receipt: x, invoice: y, unconfirmed: z}}"""
    amt = _alloc_amount(company)
    q = (db.query(Allocation.project_id, Document.doc_type, Document.status, func.sum(amt))
         .join(Document, Document.id == Allocation.document_id)
         .filter(Allocation.company_id == company.id, Allocation.direction == direction,
                 Document.duplicate_of_id.is_(None)))
    q = _period(q, Document.issue_date, d_from, d_to)
    out: dict[int, dict] = defaultdict(lambda: {"receipt": ZERO, "invoice": ZERO, "unconfirmed": ZERO})
    for pid, dtype, status, s in q.group_by(Allocation.project_id, Document.doc_type, Document.status):
        s = Decimal(s or 0)
        if status != "confirmed":
            out[pid]["unconfirmed"] += s
            if not include_unconfirmed:
                continue
        out[pid]["receipt" if dtype == "receipt" else "invoice"] += s
    return out


def _sum_by_project(db, model, col, company_id, d_from, d_to, extra=None):
    q = db.query(model.project_id, func.sum(col)).filter(model.company_id == company_id)
    if extra is not None:
        q = q.filter(extra)
    q = _period(q, model.date, d_from, d_to)
    return {pid: Decimal(s or 0) for pid, s in q.group_by(model.project_id)}


def project_costs(db: Session, company: Company, d_from: date | None, d_to: date | None,
                  include_unconfirmed: bool = False, include_inactive: bool = False) -> dict:
    mat = _material(db, company, d_from, d_to, include_unconfirmed)
    labor = _sum_by_project(db, TimesheetEntry, TimesheetEntry.cost_amount, company.id, d_from, d_to)
    hours = _sum_by_project(db, TimesheetEntry, TimesheetEntry.hours, company.id, d_from, d_to)
    transport = _sum_by_project(db, Trip, Trip.cost_amount, company.id, d_from, d_to)
    km = _sum_by_project(db, Trip, Trip.km_effective, company.id, d_from, d_to)
    q = db.query(Project).filter(Project.company_id == company.id)
    if not include_inactive:
        q = q.filter(Project.active.is_(True))
    rows = []
    totals = defaultdict(lambda: ZERO)
    for p in q.order_by(Project.is_overhead, Project.name):
        m = mat.get(p.id, {"receipt": ZERO, "invoice": ZERO, "unconfirmed": ZERO})
        r = {
            "project_id": p.id, "project_name": p.name, "status": p.status, "is_overhead": p.is_overhead,
            "active": p.active,
            "material_receipts": m["receipt"], "material_invoices": m["invoice"], "labor": labor.get(p.id, ZERO),
            "transport": transport.get(p.id, ZERO), "hours": hours.get(p.id, ZERO), "km": km.get(p.id, ZERO),
            "unconfirmed": m["unconfirmed"], "budget": Decimal(p.cost_budget) if p.cost_budget is not None else None,
        }
        r["material"] = r["material_receipts"] + r["material_invoices"]
        r["total"] = r["material"] + r["labor"] + r["transport"]
        r["remaining"] = (r["budget"] - r["total"]) if r["budget"] is not None else None
        r["budget_used_pct"] = float(r["total"] / r["budget"] * 100) if r["budget"] else None
        for k in ("material_receipts", "material_invoices", "material", "labor", "transport", "total", "hours", "km",
                  "unconfirmed"):
            totals[k] += r[k]
        rows.append({k: (_f(v) if isinstance(v, Decimal) and k not in ("hours", "km") else serialize(v)) for k, v in r.items()})
    # costs without project (incomplete timesheets / trips)
    no_proj_labor = labor.get(None, ZERO)
    no_proj_transport = transport.get(None, ZERO)
    return {"rows": rows, "totals": {k: (_f(v) if k not in ("hours", "km") else float(v)) for k, v in totals.items()},
            "unassigned": {"labor": _f(no_proj_labor), "transport": _f(no_proj_transport)},
            "basis": "bez DPH" if company.vat_payer else "s DPH"}


def project_detail(db: Session, company: Company, project_id: int, d_from, d_to, include_unconfirmed=True) -> dict:
    p = db.get(Project, project_id)
    amt = _alloc_amount(company)
    q = (db.query(Allocation, Document, DocumentLine)
         .join(Document, Document.id == Allocation.document_id)
         .outerjoin(DocumentLine, DocumentLine.id == Allocation.line_id)
         .filter(Allocation.project_id == project_id, Allocation.company_id == company.id,
                 Document.duplicate_of_id.is_(None)))
    q = _period(q, Document.issue_date, d_from, d_to)
    if not include_unconfirmed:
        q = q.filter(Document.status == "confirmed")
    material, revenue = [], []
    for a, d, ln in q.order_by(Document.issue_date):
        item = {"allocation_id": a.id, "document_id": d.id, "doc_type": d.doc_type, "status": d.status,
                "date": serialize(d.issue_date), "partner": d.partner_name, "number": d.number,
                "line": ln.description if ln else None,
                "amount": _f(a.amount_net if company.vat_payer else a.amount_gross),
                "amount_net": _f(a.amount_net), "amount_gross": _f(a.amount_gross),
                "billed": a.billing_statement_id is not None}
        (revenue if a.direction == "revenue" else material).append(item)
    workers = {w.id: w.name for w in db.query(Worker)}
    tq = _period(db.query(TimesheetEntry).filter(TimesheetEntry.project_id == project_id), TimesheetEntry.date, d_from, d_to)
    hours = [{"id": t.id, "date": serialize(t.date), "worker": workers.get(t.worker_id), "time_from": serialize(t.time_from),
              "time_to": serialize(t.time_to), "hours": float(t.hours or 0), "description": t.description,
              "cost_rate": serialize(t.cost_rate), "cost": _f(t.cost_amount), "billable": t.billable,
              "billable_amount": _f(t.billable_amount), "billed": t.billing_statement_id is not None}
             for t in tq.order_by(TimesheetEntry.date)]
    vehicles = {v.id: f"{v.name} ({v.plate or ''})" for v in db.query(Vehicle)}
    rq = _period(db.query(Trip).filter(Trip.project_id == project_id), Trip.date, d_from, d_to)
    trips = [{"id": t.id, "date": serialize(t.date), "vehicle": vehicles.get(t.vehicle_id), "driver": workers.get(t.driver_id),
              "km": float(t.km_effective or 0), "km_computed": t.km_computed, "rate": serialize(t.rate_per_km),
              "cost": _f(t.cost_amount), "billed": t.billing_statement_id is not None}
             for t in rq.order_by(Trip.date)]
    _ = amt
    return {"project": {"id": p.id, "name": p.name, "budget": serialize(p.cost_budget),
                        "contract_price": serialize(p.contract_price), "billing_type": p.billing_type,
                        "status": p.status, "is_overhead": p.is_overhead},
            "material": material, "revenue": revenue, "hours": hours, "trips": trips,
            "summary": {"material": sum(i["amount"] for i in material if i["status"] == "confirmed" or include_unconfirmed),
                        "labor": sum(h["cost"] for h in hours), "transport": sum(t["cost"] for t in trips),
                        "hours": sum(h["hours"] for h in hours), "km": sum(t["km"] for t in trips),
                        "revenue": sum(i["amount"] for i in revenue if i["status"] == "confirmed")}}


def _wip(db: Session, company: Company, d_from, d_to) -> dict[int, Decimal]:
    """Unbilled work in progress (rozpracovanosť) per project."""
    closed = {r.id for r in db.query(BillingStatement.id).filter(BillingStatement.company_id == company.id,
                                                                  BillingStatement.status == "closed")}

    def unbilled(col):
        return or_(col.is_(None), col.notin_(closed)) if closed else true()

    out: dict[int, Decimal] = defaultdict(lambda: ZERO)
    q = db.query(TimesheetEntry.project_id, func.sum(TimesheetEntry.billable_amount)).filter(
        TimesheetEntry.company_id == company.id, TimesheetEntry.billable.is_(True),
        unbilled(TimesheetEntry.billing_statement_id))
    for pid, s in _period(q, TimesheetEntry.date, d_from, d_to).group_by(TimesheetEntry.project_id):
        out[pid] += Decimal(s or 0)
    default_markup = Decimal(str(get_param(db, "material_markup_pct", company.id) or 0))
    projects = {p.id: p for p in db.query(Project).filter(Project.company_id == company.id)}
    amt = _alloc_amount(company)
    q = (db.query(Allocation.project_id, func.sum(amt)).join(Document, Document.id == Allocation.document_id)
         .filter(Allocation.company_id == company.id, Allocation.direction == "cost", Document.status == "confirmed",
                 unbilled(Allocation.billing_statement_id)))
    for pid, s in _period(q, Document.issue_date, d_from, d_to).group_by(Allocation.project_id):
        p = projects.get(pid)
        if p is None or p.is_overhead:
            continue
        mk = Decimal(p.material_markup_pct) if p.material_markup_pct is not None else default_markup
        out[pid] += Decimal(s or 0) * (1 + mk / 100)
    q = db.query(Trip.project_id, func.sum(Trip.billable_amount)).filter(
        Trip.company_id == company.id, unbilled(Trip.billing_statement_id))
    for pid, s in _period(q, Trip.date, d_from, d_to).group_by(Trip.project_id):
        p = projects.get(pid)
        if p and p.bill_transport:
            out[pid] += Decimal(s or 0)
    for pid, p in projects.items():
        if p.billing_type == "fixed":
            out[pid] = ZERO  # fixed price – WIP is not valued by hours
    return out


def profitability(db: Session, company: Company, d_from, d_to, overhead_split: str | None = None,
                  include_inactive: bool = False) -> dict:
    costs = project_costs(db, company, d_from, d_to, include_unconfirmed=False, include_inactive=include_inactive)
    rev = _material(db, company, d_from, d_to, include_unconfirmed=False, direction="revenue")
    wip = _wip(db, company, d_from, d_to)
    projects = {p.id: p for p in db.query(Project).filter(Project.company_id == company.id)}
    rows = []
    overhead_cost = ZERO
    tot = defaultdict(lambda: ZERO)
    for r in costs["rows"]:
        p = projects[r["project_id"]]
        cost = Decimal(str(r["total"]))
        if p.is_overhead:
            overhead_cost += cost
            continue
        revenue = rev.get(p.id, {"receipt": ZERO, "invoice": ZERO})
        revenue = revenue["receipt"] + revenue["invoice"]
        profit = revenue - cost
        row = {"project_id": p.id, "project_name": p.name, "status": p.status, "billing_type": p.billing_type,
               "revenue": _f(revenue), "material": r["material"], "labor": r["labor"], "transport": r["transport"],
               "cost": _f(cost), "profit": _f(profit), "margin_pct": float(profit / revenue * 100) if revenue else None,
               "wip": _f(wip.get(p.id, ZERO)), "hours": r["hours"],
               "expected_profit": _f(profit + wip.get(p.id, ZERO))}
        if p.billing_type in ("fixed", "combined") and p.contract_price is not None:
            cp = Decimal(p.contract_price)
            row["contract_price"] = _f(cp)
            row["estimated_profit"] = _f(cp - cost)
            row["estimated_margin_pct"] = float((cp - cost) / cp * 100) if cp else None
        rows.append(row)
        for k in ("revenue", "cost", "profit", "wip", "material", "labor", "transport"):
            tot[k] += Decimal(str(row[k]))
        tot["hours"] += Decimal(str(r["hours"]))
    # optional overhead distribution (display only)
    if overhead_split in ("hours", "cost") and rows:
        base_total = sum(Decimal(str(r["hours" if overhead_split == "hours" else "cost"])) for r in rows)
        for r in rows:
            share = (Decimal(str(r["hours" if overhead_split == "hours" else "cost"])) / base_total) if base_total else ZERO
            r["overhead_share"] = _f(overhead_cost * share)
            r["profit_after_overhead"] = _f(Decimal(str(r["profit"])) - overhead_cost * share)
    company_profit = tot["revenue"] - tot["cost"] - overhead_cost
    return {"rows": rows, "overhead_cost": _f(overhead_cost),
            "totals": {"revenue": _f(tot["revenue"]), "cost": _f(tot["cost"]), "project_profit": _f(tot["profit"]),
                       "overhead": _f(overhead_cost), "company_profit": _f(company_profit),
                       "margin_pct": float(company_profit / tot["revenue"] * 100) if tot["revenue"] else None,
                       "wip": _f(tot["wip"]), "expected_profit": _f(company_profit + tot["wip"]),
                       "hours": float(tot["hours"])},
            "monthly": monthly_breakdown(db, company, d_from, d_to), "basis": costs["basis"]}


def monthly_breakdown(db: Session, company: Company, d_from, d_to, project_id: int | None = None) -> list[dict]:
    amt = _alloc_amount(company)
    month = lambda col: func.to_char(col, literal_column("'YYYY-MM'"))  # noqa: E731
    data: dict[str, dict] = defaultdict(lambda: {"revenue": ZERO, "material": ZERO, "labor": ZERO, "transport": ZERO})
    q = (db.query(month(Document.issue_date), Allocation.direction, func.sum(amt))
         .join(Document, Document.id == Allocation.document_id)
         .filter(Allocation.company_id == company.id, Document.status == "confirmed"))
    if project_id:
        q = q.filter(Allocation.project_id == project_id)
    for m, direction, s in _period(q, Document.issue_date, d_from, d_to).group_by(month(Document.issue_date),
                                                                                    Allocation.direction):
        if m:
            data[m]["revenue" if direction == "revenue" else "material"] += Decimal(s or 0)
    for model, key in ((TimesheetEntry, "labor"), (Trip, "transport")):
        q = db.query(month(model.date), func.sum(model.cost_amount)).filter(model.company_id == company.id)
        if project_id:
            q = q.filter(model.project_id == project_id)
        for m, s in _period(q, model.date, d_from, d_to).group_by(month(model.date)):
            data[m][key] += Decimal(s or 0)
    out = []
    for m in sorted(data):
        v = data[m]
        cost = v["material"] + v["labor"] + v["transport"]
        out.append({"month": m, "revenue": _f(v["revenue"]), "material": _f(v["material"]), "labor": _f(v["labor"]),
                    "transport": _f(v["transport"]), "cost": _f(cost), "profit": _f(v["revenue"] - cost)})
    return out


# ----------------------------------------------------------------------------- VAT
def vat_summary(db: Session, company: Company, year: int, month: int) -> dict:
    d_from = date(year, month, 1)
    d_to = date(year, month, calendar.monthrange(year, month)[1])
    tax_date = func.coalesce(Document.tax_date, Document.issue_date)
    docs = (db.query(Document).filter(Document.company_id == company.id, Document.duplicate_of_id.is_(None),
                                      tax_date >= d_from, tax_date <= d_to).order_by(tax_date).all())
    sides = {"input": defaultdict(lambda: {"base": ZERO, "vat": ZERO}), "output": defaultdict(lambda: {"base": ZERO, "vat": ZERO})}
    lists = {"input": [], "output": []}
    pending = 0
    for d in docs:
        side = "output" if d.doc_type == "invoice_out" else "input"
        if d.status != "confirmed":
            pending += 1
        rows = json.loads(d.vat_breakdown) if d.vat_breakdown else []
        if not rows and d.total_net is not None:
            rows = [{"rate": None, "base": float(d.total_net), "vat": float(d.total_vat or 0)}]
        if d.status == "confirmed":
            for r in rows:
                key = f"{r.get('rate'):g}" if r.get("rate") is not None else "?"
                sides[side][key]["base"] += Decimal(str(r.get("base") or 0))
                sides[side][key]["vat"] += Decimal(str(r.get("vat") or 0))
        lists[side].append({"id": d.id, "doc_type": d.doc_type, "status": d.status, "date": serialize(d.tax_date or d.issue_date),
                            "partner": d.partner_name, "partner_ic_dph": d.partner_ic_dph, "number": d.number,
                            "total_net": serialize(d.total_net), "total_vat": serialize(d.total_vat),
                            "total_gross": serialize(d.total_gross)})

    def fmt(side):
        return [{"rate": k, "base": _f(v["base"]), "vat": _f(v["vat"])} for k, v in sorted(sides[side].items())]
    vin = sum((v["vat"] for v in sides["input"].values()), ZERO)
    vout = sum((v["vat"] for v in sides["output"].values()), ZERO)
    return {"company": company.name, "vat_payer": company.vat_payer, "period": f"{year}-{month:02d}",
            "input": fmt("input"), "output": fmt("output"), "input_vat": _f(vin), "output_vat": _f(vout),
            "vat_due": _f(vout - vin), "pending_review": pending, "documents": lists}


# ----------------------------------------------------------------------------- fleet alerts
def fleet_alerts(db: Session, company_id: int) -> list[dict]:
    lead = int(get_param(db, "fleet_alert_days", company_id) or 30)
    lead_km = int(get_param(db, "service_alert_km", company_id) or 1000)
    today = date.today()
    horizon = today + timedelta(days=lead)
    out = []

    def add(v, kind, label, valid_to):
        if valid_to is None:
            out.append({"vehicle_id": v.id, "vehicle": f"{v.name} ({v.plate or ''})", "kind": kind,
                        "severity": "warning", "message": f"{label}: chýba evidencia platnosti", "date": None})
        elif valid_to < today:
            out.append({"vehicle_id": v.id, "vehicle": f"{v.name} ({v.plate or ''})", "kind": kind, "severity": "error",
                        "message": f"{label} – platnosť skončila {valid_to:%d.%m.%Y}", "date": valid_to.isoformat()})
        elif valid_to <= horizon:
            out.append({"vehicle_id": v.id, "vehicle": f"{v.name} ({v.plate or ''})", "kind": kind,
                        "severity": "warning", "message": f"{label} – platnosť končí {valid_to:%d.%m.%Y}",
                        "date": valid_to.isoformat()})

    for v in db.query(Vehicle).filter(Vehicle.company_id == company_id, Vehicle.active.is_(True)):
        add(v, "stk", "STK", v.stk_valid_to)
        add(v, "ek", "EK", v.ek_valid_to)
        pzp = (db.query(func.max(VehicleInsurance.valid_to)).filter(VehicleInsurance.vehicle_id == v.id,
                                                                    VehicleInsurance.insurance_type == "pzp").scalar())
        add(v, "pzp", "PZP", pzp)
        vig = (db.query(func.max(VehicleVignette.valid_to)).filter(VehicleVignette.vehicle_id == v.id,
                                                                   VehicleVignette.country == "SK").scalar())
        add(v, "vignette", "Diaľničná známka SK", vig)
        svc = (db.query(VehicleService).filter(VehicleService.vehicle_id == v.id)
               .order_by(VehicleService.date.desc(), VehicleService.id.desc()).first())
        if svc:
            if svc.next_service_date and svc.next_service_date <= horizon:
                sev = "error" if svc.next_service_date < today else "warning"
                out.append({"vehicle_id": v.id, "vehicle": f"{v.name} ({v.plate or ''})", "kind": "service",
                            "severity": sev, "message": f"Servis – termín {svc.next_service_date:%d.%m.%Y}",
                            "date": svc.next_service_date.isoformat()})
            if svc.next_service_km and v.odometer and v.odometer >= svc.next_service_km - lead_km:
                sev = "error" if v.odometer >= svc.next_service_km else "warning"
                out.append({"vehicle_id": v.id, "vehicle": f"{v.name} ({v.plate or ''})", "kind": "service",
                            "severity": sev,
                            "message": f"Servis pri {svc.next_service_km:,} km (aktuálne {v.odometer:,} km)".replace(",", " "),
                            "date": None})
    return out


# ----------------------------------------------------------------------------- monthly check
def missing_recurring(db: Session, company_id: int, year: int, month: int) -> list[dict]:
    out = []
    d_from = date(year, month, 1)
    d_to = date(year, month, calendar.monthrange(year, month)[1])
    for r in db.query(RecurringInvoiceRule).filter(RecurringInvoiceRule.company_id == company_id,
                                                   RecurringInvoiceRule.active.is_(True)):
        if r.periodicity == "quarterly":
            if month % 3 != 0:
                continue
            start = date(year, month - 2, 1)
        elif r.periodicity == "yearly":
            if month != 12:
                continue
            start = date(year, 1, 1)
        else:
            start = d_from
        cond = [Document.recurring_rule_id == r.id]
        if r.supplier_ico:
            cond.append(Document.partner_ico == r.supplier_ico)
        if r.match_text or r.supplier_name:
            cond.append(Document.partner_name.ilike(f"%{r.match_text or r.supplier_name}%"))
        found = (db.query(Document.id).filter(Document.company_id == company_id, Document.doc_type == "invoice_in",
                                              func.coalesce(Document.tax_date, Document.issue_date) >= start,
                                              func.coalesce(Document.tax_date, Document.issue_date) <= d_to, or_(*cond))
                 .first())
        if not found:
            out.append({"rule_id": r.id, "supplier": r.supplier_name, "periodicity": r.periodicity,
                        "message": f"Chýba faktúra: {r.supplier_name} ({d_from:%m/%Y})"})
    return out


def material_without_document(db: Session, company_id: int, d_from: date, d_to: date) -> list[dict]:
    days = int(get_param(db, "material_doc_days", company_id) or 7)
    today = date.today()
    out = []
    workers = {w.id: w.name for w in db.query(Worker)}
    projects = {p.id: p.name for p in db.query(Project).filter(Project.company_id == company_id)}
    for t in (db.query(TimesheetEntry).filter(TimesheetEntry.company_id == company_id,
                                              TimesheetEntry.material_bought.is_(True),
                                              TimesheetEntry.date >= d_from, TimesheetEntry.date <= d_to)
              .order_by(TimesheetEntry.date)):
        if t.date + timedelta(days=days) > today:
            continue
        q = (db.query(Document.id).join(Allocation, Allocation.document_id == Document.id)
             .filter(Document.company_id == company_id, Document.doc_type.in_(("receipt", "invoice_in")),
                     Document.issue_date >= t.date - timedelta(days=1), Document.issue_date <= t.date + timedelta(days=1)))
        if t.project_id:
            q = q.filter(Allocation.project_id == t.project_id)
        if not q.first():
            out.append({"timesheet_id": t.id, "date": t.date.isoformat(), "worker": workers.get(t.worker_id),
                        "project": projects.get(t.project_id), "message":
                        f"{t.date:%d.%m.%Y} {workers.get(t.worker_id, '')} – nákup materiálu na zákazku "
                        f"{projects.get(t.project_id, '?')} bez dokladu"})
    return out


def monthly_check(db: Session, company: Company, year: int, month: int) -> dict:
    from app.services.bank import missing_report
    d_from = date(year, month, 1)
    d_to = date(year, month, calendar.monthrange(year, month)[1])
    cid = company.id
    no_original = [{"id": d.id, "date": serialize(d.issue_date), "partner": d.partner_name,
                    "total_gross": serialize(d.total_gross)}
                   for d in db.query(Document).filter(Document.company_id == cid, Document.doc_type == "receipt",
                                                      Document.physical_original.is_(False),
                                                      Document.is_electronic.is_(False),
                                                      Document.duplicate_of_id.is_(None),
                                                      Document.issue_date >= d_from, Document.issue_date <= d_to)
                   .order_by(Document.issue_date)]
    review = [{"id": d.id, "doc_type": d.doc_type, "date": serialize(d.issue_date), "partner": d.partner_name,
               "total_gross": serialize(d.total_gross)}
              for d in db.query(Document).filter(Document.company_id == cid, Document.status == "review",
                                                 Document.duplicate_of_id.is_(None)).order_by(Document.issue_date)]
    incomplete = [{"id": t.id, "date": serialize(t.date), "worker": w.name if w else None}
                  for t, w in db.query(TimesheetEntry, Worker).outerjoin(Worker, Worker.id == TimesheetEntry.worker_id)
                  .filter(TimesheetEntry.company_id == cid, TimesheetEntry.date >= d_from, TimesheetEntry.date <= d_to,
                          or_(TimesheetEntry.project_id.is_(None), TimesheetEntry.hours.is_(None)))]
    bank = missing_report(db, cid, d_from, d_to)
    errors = [{"id": f.id, "name": f.original_name, "error": f.error}
              for f in db.query(SourceFile).filter(SourceFile.company_id == cid, SourceFile.status == "error")]
    return {
        "period": f"{year}-{month:02d}",
        "missing_recurring": missing_recurring(db, cid, year, month),
        "receipts_without_original": no_original,
        "documents_in_review": review,
        "material_without_document": material_without_document(db, cid, d_from, d_to),
        "incomplete_timesheets": incomplete,
        "bank_without_document": bank["transactions_without_document"],
        "documents_without_payment": [d for d in bank["documents_without_payment"] if d["overdue"]],
        "amount_mismatches": bank["amount_mismatches"],
        "fleet_alerts": fleet_alerts(db, cid),
        "file_errors": errors,
    }


def dashboard(db: Session, company: Company, is_admin: bool) -> dict:
    today = date.today()
    mc = monthly_check(db, company, today.year, today.month)
    counts = {k: len(v) for k, v in mc.items() if isinstance(v, list)}
    out = {"counts": counts, "fleet_alerts": mc["fleet_alerts"], "missing_recurring": mc["missing_recurring"],
           "material_without_document": mc["material_without_document"][:20]}
    if is_admin:
        first = date(today.year, today.month, 1)
        costs = project_costs(db, company, None, None)
        month_costs = {r["project_id"]: r for r in project_costs(db, company, first, today)["rows"]}
        out["projects"] = [dict(r, month_total=month_costs.get(r["project_id"], {}).get("total", 0))
                           for r in costs["rows"] if r["status"] == "in_progress" and not r["is_overhead"]]
        out["new_files"] = db.query(SourceFile).filter(SourceFile.company_id == company.id,
                                                       SourceFile.status == "new").count()
    _ = (case, BankTransaction)
    return out
