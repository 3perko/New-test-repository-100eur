"""Document (receipt / invoice) operations: full read/write, allocations, confirmation."""
import json
from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Allocation, BillingStatement, Company, Customer, Document, DocumentLine, DocumentSource, InvoiceSeries, Project,
    SourceFile, TransactionMatch,
)
from app.registry.base import serialize
from app.services import audit
from app.services.calc import money

CENT = Decimal("0.01")
HEADER_FIELDS = {
    "doc_type": "text", "partner_name": "text", "partner_ico": "text", "partner_dic": "text", "partner_ic_dph": "text",
    "partner_iban": "text", "partner_address": "text", "buyer_ico": "text", "customer_id": "int", "number": "text",
    "series_id": "int", "ekasa_id": "text", "issue_date": "date", "issue_time": "time", "due_date": "date",
    "tax_date": "date", "vs": "text", "currency": "text", "total_net": "money", "total_vat": "money",
    "total_gross": "money", "is_electronic": "bool", "physical_original": "bool", "physical_original_at": "date",
    "note": "text", "mixed": "bool",
}


def _parse(kind: str, v):
    if v is None or v == "":
        return None
    if kind == "int":
        return int(v)
    if kind == "money":
        return money(Decimal(str(v).replace(",", ".").replace(" ", "")))
    if kind == "date":
        return date.fromisoformat(str(v)[:10])
    if kind == "time":
        return time.fromisoformat(str(v)[:5])
    if kind == "bool":
        return bool(v)
    s = str(v).strip()
    return s or None


def _dec(v) -> Decimal | None:
    if v is None or v == "":
        return None
    return Decimal(str(v).replace(",", ".").replace(" ", ""))


def direction_for(doc: Document) -> str:
    return "revenue" if doc.doc_type == "invoice_out" else "cost"


def overhead_project(db: Session, company_id: int) -> Project:
    p = db.query(Project).filter(Project.company_id == company_id, Project.is_overhead.is_(True)).first()
    if p is None:
        p = Project(company_id=company_id, name="Réžia", is_overhead=True, status="in_progress", aliases="rezia, réžia")
        db.add(p)
        db.flush()
    return p


def get_warnings(doc: Document) -> list[str]:
    try:
        return json.loads(doc.warnings) if doc.warnings else []
    except json.JSONDecodeError:
        return [doc.warnings]


def set_warnings(doc: Document, warnings: list[str]) -> None:
    uniq = list(dict.fromkeys(w for w in warnings if w))
    doc.warnings = json.dumps(uniq, ensure_ascii=False) if uniq else None


def load_doc(ctx, doc_id: int) -> Document:
    doc = ctx.db.get(Document, doc_id)
    if doc is None or doc.company_id != ctx.company_id:
        raise HTTPException(404, "Doklad neexistuje v aktívnej firme.")
    return doc


def _line_total(line: DocumentLine, basis_net: bool) -> Decimal:
    if basis_net:
        return Decimal(line.total_net if line.total_net is not None else (line.total_gross or 0))
    return Decimal(line.total_gross if line.total_gross is not None else (line.total_net or 0))


def billed_allocations(db: Session, doc: Document) -> list[Allocation]:
    out = []
    for a in doc.allocations:
        if a.billing_statement_id:
            st = db.get(BillingStatement, a.billing_statement_id)
            if st and st.status == "closed":
                out.append(a)
    return out


def doc_to_dict(db: Session, doc: Document) -> dict:
    company = db.get(Company, doc.company_id)
    files = []
    for ds in db.query(DocumentSource).filter(DocumentSource.document_id == doc.id).order_by(DocumentSource.id):
        sf = db.get(SourceFile, ds.source_file_id)
        if sf:
            files.append({"id": sf.id, "name": sf.original_name, "mime": sf.mime, "role": ds.role,
                          "source": sf.source, "added_at": serialize(ds.added_at), "note": ds.note})
    duplicates = [{"id": d.id, "created_at": serialize(d.created_at)} for d in
                  db.query(Document).filter(Document.duplicate_of_id == doc.id)]
    matches = []
    from app.models import BankTransaction
    for m in db.query(TransactionMatch).filter(TransactionMatch.document_id == doc.id):
        tx = db.get(BankTransaction, m.transaction_id)
        matches.append({"id": m.id, "transaction_id": m.transaction_id, "amount": serialize(m.amount),
                        "method": m.method, "confirmed": m.confirmed,
                        "date": serialize(tx.booking_date) if tx else None,
                        "counterparty": tx.counterparty_name if tx else None})
    projects = {p.id: p.name for p in db.query(Project).filter(Project.company_id == doc.company_id)}
    billed = {a.id for a in billed_allocations(db, doc)}
    return {
        "id": doc.id, "company_id": doc.company_id, "vat_payer": company.vat_payer if company else True,
        "status": doc.status, "extraction_source": doc.extraction_source, "extraction_log": doc.extraction_log,
        "payment_status": doc.payment_status, "paid_amount": serialize(doc.paid_amount),
        "duplicate_of_id": doc.duplicate_of_id, "source_file_id": doc.source_file_id,
        "recurring_rule_id": doc.recurring_rule_id, "warnings": get_warnings(doc),
        "confirmed_at": serialize(doc.confirmed_at), "created_at": serialize(doc.created_at),
        "vat_breakdown": json.loads(doc.vat_breakdown) if doc.vat_breakdown else [],
        **{k: serialize(getattr(doc, k)) for k in HEADER_FIELDS},
        "lines": [{"id": ln.id, "position": ln.position, "description": ln.description,
                   "quantity": serialize(ln.quantity), "unit": ln.unit, "unit_price": serialize(ln.unit_price),
                   "vat_rate": serialize(ln.vat_rate), "total_net": serialize(ln.total_net),
                   "total_vat": serialize(ln.total_vat), "total_gross": serialize(ln.total_gross)} for ln in doc.lines],
        "allocations": [{"id": a.id, "line_id": a.line_id, "project_id": a.project_id,
                         "project_name": projects.get(a.project_id), "direction": a.direction,
                         "share_pct": serialize(a.share_pct), "quantity": serialize(a.quantity),
                         "amount_net": serialize(a.amount_net), "amount_gross": serialize(a.amount_gross),
                         "billed": a.id in billed, "note": a.note} for a in doc.allocations],
        "files": files, "duplicates": duplicates, "bank_matches": matches,
    }


def _fill_line(ln: DocumentLine, doc_vat_payer: bool = True) -> None:
    """Derive missing net/vat/gross values on a line."""
    rate = Decimal(ln.vat_rate) if ln.vat_rate is not None else None
    if ln.total_gross is None and ln.quantity is not None and ln.unit_price is not None:
        ln.total_gross = money(Decimal(ln.quantity) * Decimal(ln.unit_price))
    if ln.total_gross is not None and ln.total_net is None:
        if rate is not None:
            ln.total_net = money(Decimal(ln.total_gross) / (1 + rate / 100))
        else:
            ln.total_net = money(ln.total_gross)
    if ln.total_net is not None and ln.total_gross is None:
        ln.total_gross = money(Decimal(ln.total_net) * (1 + (rate or 0) / 100))
    if ln.total_gross is not None and ln.total_net is not None:
        ln.total_vat = money(Decimal(ln.total_gross) - Decimal(ln.total_net))


def recompute_totals_from_lines(doc: Document) -> None:
    if not doc.lines:
        return
    if doc.total_gross is None:
        doc.total_gross = money(sum(Decimal(ln.total_gross or 0) for ln in doc.lines))
    if doc.total_net is None:
        doc.total_net = money(sum(Decimal(ln.total_net or 0) for ln in doc.lines))
    if doc.total_vat is None and doc.total_gross is not None and doc.total_net is not None:
        doc.total_vat = money(Decimal(doc.total_gross) - Decimal(doc.total_net))


def vat_breakdown_from_lines(doc: Document) -> list[dict]:
    agg: dict[str, dict] = {}
    for ln in doc.lines:
        key = str(Decimal(ln.vat_rate).normalize()) if ln.vat_rate is not None else "?"
        a = agg.setdefault(key, {"rate": float(ln.vat_rate) if ln.vat_rate is not None else None, "base": Decimal(0),
                                 "vat": Decimal(0)})
        a["base"] += Decimal(ln.total_net or 0)
        a["vat"] += Decimal(ln.total_vat or 0)
    return [{"rate": v["rate"], "base": float(money(v["base"])), "vat": float(money(v["vat"]))} for v in agg.values()]


def validation_messages(doc: Document) -> list[str]:
    """Deterministic consistency checks (sum of lines, VAT)."""
    msgs = []
    if doc.lines and doc.total_gross is not None:
        s = money(sum(Decimal(ln.total_gross or 0) for ln in doc.lines))
        if abs(s - Decimal(doc.total_gross)) > Decimal("0.02"):
            msgs.append(f"Súčet položiek ({s}) nesedí so sumou dokladu ({doc.total_gross}).")
    if doc.total_net is not None and doc.total_vat is not None and doc.total_gross is not None:
        if abs(Decimal(doc.total_net) + Decimal(doc.total_vat) - Decimal(doc.total_gross)) > Decimal("0.02"):
            msgs.append("Základ + DPH nesedí so sumou s DPH.")
    return msgs


def _alloc_amounts(doc: Document, line: DocumentLine | None, share_pct, amount_net, amount_gross, quantity):
    if line is not None:
        base_net = Decimal(line.total_net if line.total_net is not None else line.total_gross or 0)
        base_gross = Decimal(line.total_gross if line.total_gross is not None else line.total_net or 0)
        base_qty = Decimal(line.quantity) if line.quantity else None
    else:
        base_net = Decimal(doc.total_net if doc.total_net is not None else doc.total_gross or 0)
        base_gross = Decimal(doc.total_gross if doc.total_gross is not None else doc.total_net or 0)
        base_qty = None
    ratio = None
    if share_pct is not None:
        ratio = Decimal(share_pct) / 100
    elif quantity is not None and base_qty:
        ratio = Decimal(quantity) / base_qty
    if amount_net is None and amount_gross is None:
        ratio = Decimal(1) if ratio is None else ratio
        return money(base_net * ratio), money(base_gross * ratio)
    if amount_net is not None and amount_gross is None:
        amount_gross = money(Decimal(amount_net) * base_gross / base_net) if base_net else amount_net
    if amount_gross is not None and amount_net is None:
        amount_net = money(Decimal(amount_gross) * base_net / base_gross) if base_gross else amount_gross
    return money(amount_net), money(amount_gross)


def allocation_errors(db: Session, doc: Document) -> list[str]:
    errs = []
    if not doc.allocations:
        return ["Doklad nemá priradenú žiadnu zákazku."]
    company = db.get(Company, doc.company_id)
    for a in doc.allocations:
        p = db.get(Project, a.project_id)
        if not p or p.company_id != doc.company_id:
            errs.append("Priradená zákazka nepatrí firme dokladu.")
    doc_level = [a for a in doc.allocations if a.line_id is None]
    line_level = [a for a in doc.allocations if a.line_id is not None]
    total_gross = Decimal(doc.total_gross or 0)
    if doc_level and line_level:
        errs.append("Doklad nemôže mať súčasne priradenie celého dokladu aj priradenie po položkách.")
    elif doc_level:
        s = sum(Decimal(a.amount_gross) for a in doc_level)
        if abs(s - total_gross) > Decimal("0.02"):
            errs.append(f"Súčet rozdelení ({money(s)}) sa nerovná sume dokladu ({money(total_gross)}).")
    else:
        lines = {ln.id: ln for ln in doc.lines}
        for lid, ln in lines.items():
            s = sum(Decimal(a.amount_gross) for a in line_level if a.line_id == lid)
            target = _line_total(ln, basis_net=False)
            if abs(s - target) > Decimal("0.02"):
                errs.append(f"Položka „{(ln.description or '')[:40]}“: súčet rozdelení ({money(s)}) "
                            f"≠ suma položky ({money(target)}).")
    _ = company
    return errs


def save_full(ctx, doc: Document, payload: dict) -> Document:
    db = ctx.db
    if billed_allocations(db, doc) and ("allocations" in payload or "lines" in payload):
        raise HTTPException(409, "Doklad je už vyfakturovaný v uzavretom podklade – položky a priradenia sa nedajú meniť.")
    changes = {}
    header = payload.get("header", {})
    for k, kind in HEADER_FIELDS.items():
        if k in header:
            try:
                v = _parse(kind, header[k])
            except (ValueError, ArithmeticError) as exc:
                raise HTTPException(422, f"Neplatná hodnota: {k}") from exc
            old = getattr(doc, k)
            if old != v:
                changes[k] = (old, v)
                setattr(doc, k, v)
    if doc.customer_id:
        c = db.get(Customer, doc.customer_id)
        if not c or c.company_id != doc.company_id:
            raise HTTPException(422, "Odberateľ nepatrí aktívnej firme.")
    if doc.series_id:
        s = db.get(InvoiceSeries, doc.series_id)
        if not s or s.company_id != doc.company_id:
            raise HTTPException(422, "Číselný rad nepatrí aktívnej firme.")

    line_map: dict[str, DocumentLine] = {}
    if "lines" in payload:
        existing = {ln.id: ln for ln in doc.lines}
        keep = []
        for pos, ld in enumerate(payload["lines"]):
            ln = existing.get(ld.get("id")) if ld.get("id") else None
            if ln is None:
                ln = DocumentLine(document_id=doc.id)
                doc.lines.append(ln)
            ln.position = pos
            ln.description = ld.get("description")
            ln.quantity = _dec(ld.get("quantity"))
            ln.unit = ld.get("unit")
            ln.unit_price = _dec(ld.get("unit_price"))
            ln.vat_rate = _dec(ld.get("vat_rate"))
            ln.total_net = money(_dec(ld.get("total_net"))) if _dec(ld.get("total_net")) is not None else None
            ln.total_gross = money(_dec(ld.get("total_gross"))) if _dec(ld.get("total_gross")) is not None else None
            ln.total_vat = None
            _fill_line(ln)
            keep.append(ln)
            line_map[str(ld.get("id") or ld.get("tmp_id") or f"idx:{pos}")] = ln
            line_map[f"idx:{pos}"] = ln
        for lid, ln in existing.items():
            if ln not in keep:
                doc.lines.remove(ln)
        changes["lines"] = (None, f"{len(keep)} položiek")
        db.flush()
    else:
        for ln in doc.lines:
            line_map[str(ln.id)] = ln

    if doc.lines:
        if doc.vat_breakdown is None or "lines" in payload:
            doc.vat_breakdown = json.dumps(vat_breakdown_from_lines(doc))
        recompute_totals_from_lines(doc)  # fills only missing header totals
    elif doc.total_gross is not None and doc.total_net is None and doc.total_vat is not None:
        doc.total_net = money(Decimal(doc.total_gross) - Decimal(doc.total_vat))

    if "allocations" in payload:
        doc.allocations.clear()
        db.flush()
        direction = direction_for(doc)
        for ad in payload["allocations"]:
            if not ad.get("project_id"):
                continue
            ref = ad.get("line_ref") or (str(ad["line_id"]) if ad.get("line_id") else None)
            line = line_map.get(ref) if ref else None
            if ref and line is None:
                raise HTTPException(422, "Priradenie odkazuje na neexistujúcu položku.")
            p = db.get(Project, int(ad["project_id"]))
            if not p or p.company_id != doc.company_id:
                raise HTTPException(422, "Zákazka nepatrí aktívnej firme.")
            net, gross = _alloc_amounts(doc, line, _dec(ad.get("share_pct")), _dec(ad.get("amount_net")),
                                        _dec(ad.get("amount_gross")), _dec(ad.get("quantity")))
            doc.allocations.append(Allocation(
                company_id=doc.company_id, line_id=line.id if line else None, project_id=p.id, direction=direction,
                share_pct=_dec(ad.get("share_pct")), quantity=_dec(ad.get("quantity")), amount_net=net,
                amount_gross=gross, note=ad.get("note")))
        doc.mixed = any(a.line_id for a in doc.allocations)
        changes["allocations"] = (None, ", ".join(f"{a.project_id}:{a.amount_gross}" for a in doc.allocations))
    warnings = [w for w in get_warnings(doc) if not w.startswith("Súčet položiek") and not w.startswith("Základ + DPH")]
    set_warnings(doc, warnings + validation_messages(doc))
    db.flush()
    audit.log(db, user_id=ctx.user.id, company_id=doc.company_id, entity="documents", entity_id=doc.id,
              action="update", changes=changes)
    return doc


def confirm(ctx, doc: Document) -> None:
    errs = allocation_errors(ctx.db, doc)
    if doc.total_gross is None:
        errs.insert(0, "Doklad nemá vyplnenú sumu.")
    if doc.issue_date is None:
        errs.insert(0, "Doklad nemá vyplnený dátum.")
    if errs:
        raise HTTPException(422, " ".join(errs))
    doc.status = "confirmed"
    doc.confirmed_at = datetime.now(timezone.utc)
    doc.confirmed_by = ctx.user.id
    audit.log(ctx.db, user_id=ctx.user.id, company_id=doc.company_id, entity="documents", entity_id=doc.id,
              action="confirm")


def set_whole_project(ctx, doc: Document, project_id: int) -> None:
    db = ctx.db
    if billed_allocations(db, doc):
        raise HTTPException(409, "Doklad je už vyfakturovaný.")
    p = db.get(Project, project_id)
    if not p or p.company_id != doc.company_id:
        raise HTTPException(422, "Zákazka nepatrí aktívnej firme.")
    doc.allocations.clear()
    db.flush()
    doc.allocations.append(Allocation(company_id=doc.company_id, project_id=p.id, direction=direction_for(doc),
                                      share_pct=Decimal(100), amount_net=money(doc.total_net or doc.total_gross or 0),
                                      amount_gross=money(doc.total_gross or doc.total_net or 0)))
    doc.mixed = False
    audit.log(db, user_id=ctx.user.id, company_id=doc.company_id, entity="documents", entity_id=doc.id,
              action="update", changes={"allocations": (None, f"celý doklad → {p.name}")})


def split_even(total: Decimal, n: int) -> list[Decimal]:
    total = money(total)
    if n <= 0:
        return []
    base = (total / n).quantize(CENT, rounding=ROUND_HALF_UP)
    parts = [base] * n
    parts[-1] = total - base * (n - 1)
    return parts


# --------------------------------------------------------------------------- bulk actions (DataTable)
def _each(ctx, ids, fn) -> dict:
    ok, failed = 0, []
    for i in ids:
        try:
            doc = load_doc(ctx, int(i))
            fn(doc)
            ok += 1
        except HTTPException as exc:
            failed.append(f"#{i}: {exc.detail}")
    ctx.db.commit()
    msg = f"Spracované: {ok}"
    if failed:
        msg += f", chyby: {len(failed)} – " + "; ".join(failed[:5])
    return {"message": msg, "ok": ok, "failed": failed}


def action_confirm(ctx, ids, payload):
    return _each(ctx, ids, lambda d: confirm(ctx, d))


def action_unconfirm(ctx, ids, payload):
    def fn(d):
        if billed_allocations(ctx.db, d):
            raise HTTPException(409, "Doklad je vyfakturovaný.")
        d.status = "review"
        audit.log(ctx.db, user_id=ctx.user.id, company_id=d.company_id, entity="documents", entity_id=d.id,
                  action="unconfirm")
    return _each(ctx, ids, fn)


def action_set_project(ctx, ids, payload):
    pid = payload.get("project_id")
    if not pid:
        raise HTTPException(422, "Vyberte zákazku.")
    return _each(ctx, ids, lambda d: set_whole_project(ctx, d, int(pid)))


def action_set_overhead(ctx, ids, payload):
    p = overhead_project(ctx.db, ctx.company_id)
    return _each(ctx, ids, lambda d: set_whole_project(ctx, d, p.id))


def mark_physical(ctx, doc: Document, when: date | None = None) -> None:
    doc.physical_original = True
    doc.physical_original_at = when or date.today()
    audit.log(ctx.db, user_id=ctx.user.id, company_id=doc.company_id, entity="documents", entity_id=doc.id,
              action="mark_physical")


def action_mark_physical(ctx, ids, payload):
    return _each(ctx, ids, lambda d: mark_physical(ctx, d))


def before_delete(ctx, doc: Document) -> None:
    if billed_allocations(ctx.db, doc):
        raise HTTPException(409, "Doklad je vyfakturovaný v uzavretom podklade a nedá sa vymazať.")
    for d in ctx.db.query(Document).filter(Document.duplicate_of_id == doc.id):
        d.duplicate_of_id = None


def create_manual(ctx, doc_type: str) -> Document:
    if doc_type not in ("receipt", "invoice_in", "invoice_out"):
        raise HTTPException(422, "Neplatný typ dokladu.")
    doc = Document(company_id=ctx.company_id, doc_type=doc_type, status="review", extraction_source="manual",
                   issue_date=date.today())
    ctx.db.add(doc)
    ctx.db.flush()
    audit.log(ctx.db, user_id=ctx.user.id, company_id=doc.company_id, entity="documents", entity_id=doc.id,
              action="create")
    return doc
