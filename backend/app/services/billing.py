"""Billing statement for the customer (podklad k fakturácii) and worker statement (podklad pre pracovníka)."""
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_, true

from app.models import (
    Allocation, BillingStatement, BillingStatementLine, Company, Customer, Document, Project, TimesheetEntry, Trip,
    Vehicle, Worker,
)
from app.registry.base import serialize
from app.services import audit
from app.services.calc import money
from app.services.settings import get_param


def _project(ctx, project_id: int) -> Project:
    p = ctx.db.get(Project, project_id)
    if not p or p.company_id != ctx.company_id:
        raise HTTPException(404, "Zákazka neexistuje v aktívnej firme.")
    return p


def _open_statement_ids(db, company_id: int, exclude: int | None = None) -> set[int]:
    q = db.query(BillingStatement.id).filter(BillingStatement.company_id == company_id, BillingStatement.status == "closed")
    return {r.id for r in q if r.id != exclude}


def collect_lines(ctx, project: Project, d_from: date, d_to: date, exclude_statement: int | None = None) -> list[dict]:
    """Unbilled billable items of the project in the period."""
    db = ctx.db
    company = db.get(Company, project.company_id)
    fixed = project.billing_type == "fixed"
    closed = _open_statement_ids(db, project.company_id)
    lines: list[dict] = []

    def unbilled(col):
        return or_(col.is_(None), col.notin_(closed)) if closed else true()

    ts = (db.query(TimesheetEntry).filter(TimesheetEntry.project_id == project.id, TimesheetEntry.billable.is_(True),
                                          TimesheetEntry.date >= d_from, TimesheetEntry.date <= d_to,
                                          unbilled(TimesheetEntry.billing_statement_id))
          .order_by(TimesheetEntry.date, TimesheetEntry.time_from).all())
    workers = {w.id: w.name for w in db.query(Worker)}
    for t in ts:
        if not t.hours:
            continue
        rate = Decimal(t.billing_rate or 0)
        lines.append({"line_type": "hours", "timesheet_id": t.id, "date": t.date, "worker_name": workers.get(t.worker_id),
                      "description": t.description, "quantity": Decimal(t.hours), "unit": "h",
                      "rate": None if fixed else rate, "markup_pct": None,
                      "amount": Decimal(0) if fixed else money(Decimal(t.hours) * rate)})
    markup = project.material_markup_pct
    if markup is None:
        markup = Decimal(str(get_param(db, "material_markup_pct", project.company_id) or 0))
    allocs = (db.query(Allocation, Document).join(Document, Document.id == Allocation.document_id)
              .filter(Allocation.project_id == project.id, Allocation.direction == "cost", Document.status == "confirmed",
                      Document.issue_date >= d_from, Document.issue_date <= d_to,
                      unbilled(Allocation.billing_statement_id))
              .order_by(Document.issue_date).all())
    from app.models import DocumentLine
    for a, d in allocs:
        base = Decimal(a.amount_net if company.vat_payer else a.amount_gross)
        desc = d.partner_name or ""
        if a.line_id:
            ln = db.get(DocumentLine, a.line_id)
            desc = f"{desc}: {ln.description}" if ln else desc
        desc = f"{desc} (doklad {d.number or d.id})"
        lines.append({"line_type": "material", "allocation_id": a.id, "date": d.issue_date, "description": desc,
                      "quantity": Decimal(1), "unit": "ks", "rate": base, "markup_pct": Decimal(markup),
                      "amount": Decimal(0) if fixed else money(base * (1 + Decimal(markup) / 100))})
    if project.bill_transport:
        trips = (db.query(Trip).filter(Trip.project_id == project.id, Trip.date >= d_from, Trip.date <= d_to,
                                       unbilled(Trip.billing_statement_id)).order_by(Trip.date).all())
        vehicles = {v.id: v for v in db.query(Vehicle)}
        for t in trips:
            rate = Decimal(t.billing_rate_per_km or project.transport_rate_per_km or 0)
            v = vehicles.get(t.vehicle_id)
            lines.append({"line_type": "transport", "trip_id": t.id, "date": t.date,
                          "description": f"Doprava {v.name if v else ''} {v.plate or '' if v else ''}".strip(),
                          "quantity": Decimal(t.km_effective or 0), "unit": "km", "rate": None if fixed else rate,
                          "markup_pct": None, "amount": Decimal(0) if fixed else money(Decimal(t.km_effective or 0) * rate)})
    return lines


def _totals(lines, vat_rate: Decimal, vat_payer: bool) -> tuple[Decimal, Decimal, Decimal]:
    net = money(sum((Decimal(ln["amount"]) for ln in lines), Decimal(0)))
    vat = money(net * vat_rate / 100) if vat_payer else Decimal("0.00")
    return net, vat, money(net + vat)


def preview(ctx, project_id: int, d_from: date, d_to: date) -> dict:
    p = _project(ctx, project_id)
    company = ctx.db.get(Company, p.company_id)
    lines = collect_lines(ctx, p, d_from, d_to)
    vat_rate = Decimal(str(get_param(ctx.db, "default_vat_rate", p.company_id) or 23))
    net, vat, gross = _totals(lines, vat_rate, company.vat_payer)
    return {"project_id": p.id, "project_name": p.name, "billing_type": p.billing_type, "period_from": d_from.isoformat(),
            "period_to": d_to.isoformat(), "vat_rate": float(vat_rate), "vat_payer": company.vat_payer,
            "total_net": float(net), "total_vat": float(vat), "total_gross": float(gross),
            "lines": [{k: serialize(v) for k, v in ln.items()} for ln in lines]}


def create(ctx, project_id: int, d_from: date, d_to: date, group_by: str = "worker", note: str | None = None) -> BillingStatement:
    p = _project(ctx, project_id)
    company = ctx.db.get(Company, p.company_id)
    lines = collect_lines(ctx, p, d_from, d_to)
    if not lines:
        raise HTTPException(422, "Za obdobie nie sú žiadne nevyfakturované položky.")
    vat_rate = Decimal(str(get_param(ctx.db, "default_vat_rate", p.company_id) or 23))
    net, vat, gross = _totals(lines, vat_rate, company.vat_payer)
    st = BillingStatement(company_id=p.company_id, project_id=p.id, period_from=d_from, period_to=d_to, status="draft",
                          group_by=group_by, vat_rate=vat_rate, total_net=net, total_vat=vat, total_gross=gross,
                          note=note, created_by=ctx.user.id)
    for ln in lines:
        st.lines.append(BillingStatementLine(**ln))
    ctx.db.add(st)
    ctx.db.flush()
    audit.log(ctx.db, user_id=ctx.user.id, company_id=ctx.company_id, entity="billing_statements", entity_id=st.id,
              action="create", changes={"total_net": (None, net)})
    ctx.db.commit()
    return st


def load(ctx, st_id: int) -> BillingStatement:
    st = ctx.db.get(BillingStatement, st_id)
    if not st or st.company_id != ctx.company_id:
        raise HTTPException(404, "Podklad neexistuje v aktívnej firme.")
    return st


def to_dict(ctx, st: BillingStatement) -> dict:
    db = ctx.db
    p = db.get(Project, st.project_id)
    company = db.get(Company, st.company_id)
    cust = db.get(Customer, p.customer_id) if p and p.customer_id else None
    inv = db.get(Document, st.invoice_document_id) if st.invoice_document_id else None
    return {
        "id": st.id, "project_id": st.project_id, "project_name": p.name if p else None,
        "billing_type": p.billing_type if p else None,
        "customer": {"name": cust.name, "ico": cust.ico, "ic_dph": cust.ic_dph, "address": cust.address} if cust else None,
        "company": {"name": company.name, "ico": company.ico, "ic_dph": company.ic_dph, "vat_payer": company.vat_payer},
        "period_from": serialize(st.period_from), "period_to": serialize(st.period_to), "status": st.status,
        "group_by": st.group_by, "vat_rate": serialize(st.vat_rate), "total_net": serialize(st.total_net),
        "total_vat": serialize(st.total_vat), "total_gross": serialize(st.total_gross), "note": st.note,
        "invoice_document_id": st.invoice_document_id,
        "invoice": {"id": inv.id, "number": inv.number, "total_gross": serialize(inv.total_gross)} if inv else None,
        "closed_at": serialize(st.closed_at), "created_at": serialize(st.created_at),
        "lines": [{"id": ln.id, "line_type": ln.line_type, "date": serialize(ln.date), "description": ln.description,
                   "worker_name": ln.worker_name, "quantity": serialize(ln.quantity), "unit": ln.unit,
                   "rate": serialize(ln.rate), "markup_pct": serialize(ln.markup_pct), "amount": serialize(ln.amount),
                   "timesheet_id": ln.timesheet_id, "allocation_id": ln.allocation_id, "trip_id": ln.trip_id}
                  for ln in st.lines],
    }


def update_lines(ctx, st: BillingStatement, payload: dict) -> None:
    """Draft edits: remove lines, change note / vat rate / grouping."""
    if st.status != "draft":
        raise HTTPException(409, "Uzavretý podklad sa nedá meniť.")
    remove = set(payload.get("remove_line_ids") or [])
    for ln in list(st.lines):
        if ln.id in remove:
            st.lines.remove(ln)
    for k in ("note", "group_by"):
        if k in payload:
            setattr(st, k, payload[k])
    if "vat_rate" in payload and payload["vat_rate"] not in (None, ""):
        st.vat_rate = Decimal(str(payload["vat_rate"]))
    company = ctx.db.get(Company, st.company_id)
    net, vat, gross = _totals([{"amount": ln.amount} for ln in st.lines], Decimal(st.vat_rate), company.vat_payer)
    st.total_net, st.total_vat, st.total_gross = net, vat, gross
    audit.log(ctx.db, user_id=ctx.user.id, company_id=ctx.company_id, entity="billing_statements", entity_id=st.id,
              action="update")
    ctx.db.commit()


def close(ctx, st: BillingStatement) -> None:
    db = ctx.db
    if st.status == "closed":
        raise HTTPException(409, "Podklad je už uzavretý.")
    closed = _open_statement_ids(db, st.company_id, exclude=st.id)
    for ln in st.lines:
        for model, fk in ((TimesheetEntry, ln.timesheet_id), (Allocation, ln.allocation_id), (Trip, ln.trip_id)):
            if fk:
                obj = db.get(model, fk)
                if obj is None:
                    continue
                if obj.billing_statement_id and obj.billing_statement_id in closed:
                    raise HTTPException(409, f"Položka „{ln.description or ln.line_type}“ je už vyfakturovaná v inom podklade.")
                obj.billing_statement_id = st.id
    st.status = "closed"
    st.closed_at = datetime.now(timezone.utc)
    audit.log(db, user_id=ctx.user.id, company_id=ctx.company_id, entity="billing_statements", entity_id=st.id,
              action="close")
    db.commit()


def reopen(ctx, st: BillingStatement) -> None:
    db = ctx.db
    if st.status != "closed":
        raise HTTPException(409, "Podklad nie je uzavretý.")
    if st.invoice_document_id:
        raise HTTPException(409, "Podklad je naviazaný na vystavenú faktúru – najprv zrušte väzbu.")
    for model in (TimesheetEntry, Allocation, Trip):
        for obj in db.query(model).filter(model.billing_statement_id == st.id):
            obj.billing_statement_id = None
    st.status = "draft"
    st.closed_at = None
    audit.log(db, user_id=ctx.user.id, company_id=ctx.company_id, entity="billing_statements", entity_id=st.id,
              action="reopen")
    db.commit()


def link_invoice(ctx, st: BillingStatement, document_id: int | None) -> None:
    db = ctx.db
    if document_id:
        doc = db.get(Document, document_id)
        if not doc or doc.company_id != ctx.company_id or doc.doc_type != "invoice_out":
            raise HTTPException(422, "Vyberte vystavenú faktúru aktívnej firmy.")
        doc.billing_statement_id = st.id
    elif st.invoice_document_id:
        old = db.get(Document, st.invoice_document_id)
        if old:
            old.billing_statement_id = None
    st.invoice_document_id = document_id
    audit.log(db, user_id=ctx.user.id, company_id=ctx.company_id, entity="billing_statements", entity_id=st.id,
              action="link_invoice", changes={"invoice_document_id": (None, document_id)})
    db.commit()


def before_delete(ctx, st: BillingStatement) -> None:
    if st.status == "closed":
        raise HTTPException(409, "Uzavretý podklad sa nedá vymazať – najprv ho otvorte.")


# ----------------------------------------------------------------------------- worker statement
def worker_statement(ctx, worker_id: int, d_from: date, d_to: date, all_companies: bool = False) -> dict:
    db = ctx.db
    if ctx.role == "worker":
        worker_id = ctx.user.worker_id
        all_companies = False
    w = db.get(Worker, worker_id)
    if not w:
        raise HTTPException(404, "Pracovník neexistuje.")
    q = db.query(TimesheetEntry).filter(TimesheetEntry.worker_id == w.id, TimesheetEntry.date >= d_from,
                                        TimesheetEntry.date <= d_to)
    if not all_companies:
        q = q.filter(TimesheetEntry.company_id == ctx.company_id)
    entries = q.order_by(TimesheetEntry.date, TimesheetEntry.time_from).all()
    projects = {p.id: p.name for p in db.query(Project)}
    companies = {c.id: c.name for c in db.query(Company)}
    rows = []
    by_project: dict[str, dict] = {}
    by_day: dict[str, Decimal] = {}
    total_h, total_amt = Decimal(0), Decimal(0)
    for e in entries:
        h = Decimal(e.hours or 0)
        pname = projects.get(e.project_id, "— bez zákazky —")
        rows.append({"id": e.id, "date": serialize(e.date), "time_from": serialize(e.time_from),
                     "time_to": serialize(e.time_to), "hours": float(h), "project": pname,
                     "company": companies.get(e.company_id), "description": e.description,
                     "cost_rate": serialize(e.cost_rate), "amount": serialize(e.cost_amount)})
        bp = by_project.setdefault(pname, {"project": pname, "hours": Decimal(0), "amount": Decimal(0)})
        bp["hours"] += h
        bp["amount"] += Decimal(e.cost_amount or 0)
        by_day[e.date.isoformat()] = by_day.get(e.date.isoformat(), Decimal(0)) + h
        total_h += h
        total_amt += Decimal(e.cost_amount or 0)
    return {"worker": {"id": w.id, "name": w.name, "relation_type": w.relation_type, "ico": w.ico},
            "period_from": d_from.isoformat(), "period_to": d_to.isoformat(), "rows": rows,
            "by_project": [{"project": v["project"], "hours": float(v["hours"]), "amount": float(money(v["amount"]))}
                           for v in by_project.values()],
            "by_day": [{"date": k, "hours": float(v)} for k, v in sorted(by_day.items())],
            "total_hours": float(total_h), "total_amount": float(money(total_amt)),
            "company": ctx.company.name if ctx.company and not all_companies else "Všetky firmy"}
