"""Inbox processing pipeline: source file -> document in the review queue.

Order: hash dedupe -> PDF text / image prep -> QR (eKasa ID) -> duplicate check -> eKasa -> Claude API ->
validation -> company check -> project suggestion -> review queue.
"""
import json
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import (
    Allocation, Company, Document, DocumentLine, DocumentSource, InvoiceSeries, Project, RecurringInvoiceRule, SourceFile,
)
from app.services import documents as ds
from app.services import ekasa, extraction, prep, storage
from app.services.calc import money
from app.services.extraction import ExtractedDocument
from app.services.settings import get_param

log = logging.getLogger(__name__)
BANK_EXT = (".xml", ".csv", ".xlsx", ".xls", ".sta", ".gpc")


def _norm(s: str | None) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


# --------------------------------------------------------------------------- project suggestion
def match_project_in_text(db: Session, company_id: int, text: str) -> Project | None:
    t = _norm(text)
    if not t.strip():
        return None
    best: tuple[int, Project] | None = None
    for p in db.query(Project).filter(Project.company_id == company_id, Project.active.is_(True)):
        names = [p.name] + [a.strip() for a in (p.aliases or "").split(",") if a.strip()]
        for n in names:
            nn = _norm(n)
            if len(nn) >= 3 and re.search(r"(?<![a-z0-9])" + re.escape(nn) + r"(?![a-z0-9])", t):
                if best is None or len(nn) > best[0]:
                    best = (len(nn), p)
    return best[1] if best else None


def is_overhead_supplier(db: Session, company_id: int, name: str | None, lines: list[str]) -> bool:
    kws = [_norm(k) for k in (get_param(db, "overhead_keywords", company_id) or [])]
    hay = _norm(name)
    if any(k and k in hay for k in kws):
        return True
    return bool(lines) and all(any(k and k in _norm(ln) for k in kws) for ln in lines)


def recurring_rule_for(db: Session, company_id: int, ico: str | None, name: str | None) -> RecurringInvoiceRule | None:
    for r in db.query(RecurringInvoiceRule).filter(RecurringInvoiceRule.company_id == company_id,
                                                   RecurringInvoiceRule.active.is_(True)):
        if r.supplier_ico and ico and _digits(r.supplier_ico) == _digits(ico):
            return r
        needle = _norm(r.match_text or r.supplier_name)
        if needle and name and needle in _norm(name):
            return r
    return None


def project_from_history(db: Session, company_id: int, ico: str | None) -> Project | None:
    if not ico:
        return None
    row = (db.query(Allocation.project_id, func.count().label("n"))
           .join(Document, Document.id == Allocation.document_id)
           .filter(Document.company_id == company_id, Document.partner_ico == ico, Document.status == "confirmed",
                   Allocation.direction == "cost")
           .group_by(Allocation.project_id).order_by(func.count().desc()).first())
    if row:
        p = db.get(Project, row.project_id)
        if p and p.active:
            return p
    return None


def series_for_number(db: Session, company_id: int, number: str | None) -> InvoiceSeries | None:
    if not number:
        return None
    best = None
    for s in db.query(InvoiceSeries).filter(InvoiceSeries.company_id == company_id, InvoiceSeries.active.is_(True)):
        if number.upper().startswith(s.prefix.upper()) and (best is None or len(s.prefix) > len(best.prefix)):
            best = s
    return best


# --------------------------------------------------------------------------- duplicates
def find_duplicate(db: Session, company_id: int, ex: ExtractedDocument, exclude_id: int | None = None) -> Document | None:
    q = db.query(Document).filter(Document.company_id == company_id, Document.duplicate_of_id.is_(None))
    if exclude_id:
        q = q.filter(Document.id != exclude_id)
    if ex.ekasa_receipt_id:
        d = q.filter(func.upper(Document.ekasa_id) == ex.ekasa_receipt_id.upper()).first()
        if d:
            return d
    if ex.doc_type in ("invoice_in", "invoice_out") and ex.number and ex.partner_ico:
        d = q.filter(Document.number == ex.number, Document.partner_ico == ex.partner_ico,
                     Document.doc_type == ex.doc_type).first()
        if d:
            return d
    if ex.partner_ico and ex.issue_date and ex.total_gross is not None:
        try:
            d_date = date.fromisoformat(ex.issue_date)
        except ValueError:
            return None
        cands = q.filter(Document.partner_ico == ex.partner_ico, Document.issue_date == d_date,
                         Document.total_gross == money(ex.total_gross)).all()
        if ex.issue_time:
            tol = int(get_param(db, "duplicate_time_tolerance_min", company_id) or 2)
            t = _parse_time(ex.issue_time)
            for c in cands:
                if c.issue_time and t:
                    diff = abs((datetime.combine(d_date, c.issue_time) - datetime.combine(d_date, t)).total_seconds())
                    if diff <= tol * 60:
                        return c
                elif c.issue_time is None:
                    return c
        elif cands:
            return cands[0]
    return None


def _parse_time(v: str | None) -> time | None:
    if not v:
        return None
    try:
        return time.fromisoformat(v[:5])
    except ValueError:
        return None


def _parse_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def attach_file(db: Session, doc: Document, sf: SourceFile, role: str, note: str | None = None) -> None:
    exists = db.query(DocumentSource).filter(DocumentSource.document_id == doc.id,
                                             DocumentSource.source_file_id == sf.id).first()
    if not exists:
        db.add(DocumentSource(document_id=doc.id, source_file_id=sf.id, role=role, note=note))


# --------------------------------------------------------------------------- main processing
class ProcessResult(dict):
    pass


def _apply_extracted(db: Session, doc: Document, ex: ExtractedDocument) -> None:
    doc.partner_name = ex.partner_name
    doc.partner_ico = _digits(ex.partner_ico) or None
    doc.partner_dic = _digits(ex.partner_dic) or None
    doc.partner_ic_dph = (ex.partner_ic_dph or "").replace(" ", "") or None
    doc.partner_iban = (ex.partner_iban or "").replace(" ", "").upper() or None
    doc.partner_address = ex.partner_address
    doc.buyer_ico = _digits(ex.buyer_ico) or None
    doc.number = ex.number
    doc.ekasa_id = ex.ekasa_receipt_id.upper() if ex.ekasa_receipt_id else None
    doc.issue_date = _parse_date(ex.issue_date)
    doc.issue_time = _parse_time(ex.issue_time)
    doc.due_date = _parse_date(ex.due_date)
    doc.tax_date = _parse_date(ex.tax_date)
    doc.vs = _digits(ex.vs) or None
    doc.currency = (ex.currency or "EUR")[:3].upper()
    doc.total_net = money(ex.total_net) if ex.total_net is not None else None
    doc.total_vat = money(ex.total_vat) if ex.total_vat is not None else None
    doc.total_gross = money(ex.total_gross) if ex.total_gross is not None else None
    doc.lines.clear()
    for i, ln in enumerate(ex.lines):
        dl = DocumentLine(position=i, description=ln.description,
                          quantity=Decimal(str(ln.quantity)) if ln.quantity is not None else None, unit=ln.unit,
                          unit_price=Decimal(str(ln.unit_price)) if ln.unit_price is not None else None,
                          vat_rate=Decimal(str(ln.vat_rate)) if ln.vat_rate is not None else None,
                          total_net=money(ln.total_net) if ln.total_net is not None else None,
                          total_gross=money(ln.total_gross) if ln.total_gross is not None else None)
        ds._fill_line(dl)
        doc.lines.append(dl)
    if ex.vat_breakdown:
        doc.vat_breakdown = json.dumps([v.model_dump() for v in ex.vat_breakdown])
    elif doc.lines:
        doc.vat_breakdown = json.dumps(ds.vat_breakdown_from_lines(doc))
    if doc.total_gross is None or doc.total_net is None:
        ds.recompute_totals_from_lines(doc)
    if doc.total_vat is None and doc.total_gross is not None and doc.total_net is not None:
        doc.total_vat = money(doc.total_gross - doc.total_net)
    if doc.total_net is None and doc.total_gross is not None:
        doc.total_net = doc.total_gross
        doc.total_vat = Decimal("0.00")


def process_source_file(db: Session, sf: SourceFile) -> dict:
    """Process one source file. Returns a summary dict. Commits are left to the caller."""
    company = db.get(Company, sf.company_id)
    data = storage.read_file(sf)
    name_lower = sf.original_name.lower()
    log_lines: list[str] = []

    # ---- bank statements are a separate flow
    if sf.kind_hint == "bank" or (sf.kind_hint == "auto" and name_lower.endswith(BANK_EXT)):
        from app.services import bank
        try:
            st = bank.import_statement_file(db, company, sf, data)
            sf.status = "processed"
            sf.error = f"Bankový výpis: {st.tx_count} pohybov, nových {st.new_tx_count}"
        except bank.BankImportError as exc:
            sf.status = "error"
            sf.error = str(exc)
        sf.processed_at = datetime.now(timezone.utc)
        return {"file": sf.original_name, "status": sf.status, "info": sf.error}

    # ---- prepare text / images
    text = ""
    images: list[tuple[bytes, str]] = []
    pdf_bytes = None
    is_pdf = data[:4] == b"%PDF"
    if is_pdf:
        text = prep.pdf_text(data)
        if len(text) >= 40:
            log_lines.append("PDF s textovou vrstvou – čítané priamo bez OCR")
        else:
            text = ""
            log_lines.append("PDF bez textovej vrstvy – konverzia na obrázky")
        rendered = prep.pdf_to_images(data, max_pages=3)
        images = [(img, "image/png") for img in rendered]
        pdf_bytes = data
    else:
        try:
            img, mime = prep.normalize_image(data)
            images = [(img, mime)]
        except Exception as exc:  # noqa: BLE001
            sf.status = "error"
            sf.error = f"Nepodporovaný formát súboru: {exc}"
            sf.processed_at = datetime.now(timezone.utc)
            return {"file": sf.original_name, "status": "error", "info": sf.error}

    # ---- QR / eKasa id (deterministic)
    qr_payloads: list[str] = []
    for img, _ in images:
        qr_payloads += prep.decode_qr(img)
    if not is_pdf:
        qr_payloads += prep.decode_qr(data)
    ekasa_id = prep.find_ekasa_id(qr_payloads + [text, sf.original_name])
    if ekasa_id:
        log_lines.append(f"ID dokladu z QR/textu: {ekasa_id}")
    elif qr_payloads:
        log_lines.append("QR nájdený, ale neobsahuje online ID eKasa")
    else:
        log_lines.append("QR kód nenájdený")

    ex: ExtractedDocument | None = None
    source = "manual"

    def try_ekasa(rid: str) -> ExtractedDocument | None:
        try:
            receipt = ekasa.fetch_receipt(rid)
            log_lines.append("eKasa: doklad načítaný")
            return ekasa.receipt_to_extracted(receipt)
        except ekasa.EkasaError as exc:
            log_lines.append(f"eKasa: {exc}")
            return None

    # ---- duplicate check by eKasa id before any API call
    if ekasa_id:
        dup = find_duplicate(db, sf.company_id, ExtractedDocument(ekasa_receipt_id=ekasa_id))
        if dup:
            return _register_duplicate(db, sf, dup, log_lines)
        if sf.kind_hint in ("auto", "receipt"):
            ex = try_ekasa(ekasa_id)
            if ex:
                source = "ekasa"

    # ---- Claude API
    if ex is None:
        if extraction.is_available():
            projects = [p.name + (f" ({p.aliases})" if p.aliases else "") for p in
                        db.query(Project).filter(Project.company_id == sf.company_id, Project.active.is_(True))]
            try:
                if text:
                    ex = extraction.extract(text=text, company_name=company.name, company_ico=company.ico or "",
                                            projects=projects, filename=sf.original_name)
                    source = "pdf_text"
                elif pdf_bytes is not None:
                    ex = extraction.extract(pdf=pdf_bytes, company_name=company.name, company_ico=company.ico or "",
                                            projects=projects, filename=sf.original_name)
                    source = "claude"
                else:
                    ex = extraction.extract(images=images[:3], company_name=company.name,
                                            company_ico=company.ico or "", projects=projects, filename=sf.original_name)
                    source = "claude"
                log_lines.append("Claude API: údaje vyextrahované")
            except RuntimeError as exc:
                log_lines.append(f"Claude API: {exc}")
        else:
            log_lines.append("Claude API nie je nakonfigurované – údaje treba doplniť ručne")
        # second chance for eKasa with the id read by Claude
        if ex is not None and ex.ekasa_receipt_id and not ekasa_id:
            rid = ex.ekasa_receipt_id.strip().upper()
            if prep.EKASA_ID_RE.fullmatch(rid):
                dup = find_duplicate(db, sf.company_id, ExtractedDocument(ekasa_receipt_id=rid))
                if dup:
                    return _register_duplicate(db, sf, dup, log_lines)
                ex2 = try_ekasa(rid)
                if ex2:
                    ex2.handwritten_note = ex.handwritten_note
                    ex2.project_hint = ex.project_hint
                    ex, source = ex2, "ekasa"
        if ex is not None and ekasa_id and not ex.ekasa_receipt_id:
            ex.ekasa_receipt_id = ekasa_id

    if ex is None:
        ex = ExtractedDocument(doc_type={"invoice_in": "invoice_in", "invoice_out": "invoice_out"}.get(sf.kind_hint, "receipt"),
                               ekasa_receipt_id=ekasa_id)

    if sf.kind_hint in ("receipt", "invoice_in", "invoice_out"):
        ex.doc_type = sf.kind_hint
    if ex.doc_type == "other":
        ex.doc_type = "invoice_in"

    # ---- fallback duplicate (IČO + date + time + amount)
    dup = find_duplicate(db, sf.company_id, ex)
    if dup:
        return _register_duplicate(db, sf, dup, log_lines)

    # ---- create document
    doc = Document(company_id=sf.company_id, doc_type=ex.doc_type, status="review", extraction_source=source,
                   source_file_id=sf.id, is_electronic=bool(is_pdf and text) or sf.source == "email")
    db.add(doc)
    db.flush()
    _apply_extracted(db, doc, ex)
    if doc.doc_type == "receipt" and sf.physical:
        doc.physical_original = True
        doc.physical_original_at = date.today()
    attach_file(db, doc, sf, "physical_scan" if sf.physical else "original")

    warnings = ds.validation_messages(doc)
    if source == "manual":
        warnings.append("Údaje sa nepodarilo načítať automaticky – doplňte ich ručne.")
    # company check: IČO of the buyer must be the active company
    comp_ico = _digits(company.ico)
    if doc.doc_type in ("receipt", "invoice_in") and doc.buyer_ico and comp_ico and _digits(doc.buyer_ico) != comp_ico:
        warnings.append(f"IČO odberateľa na doklade ({doc.buyer_ico}) nesedí s aktívnou firmou ({company.ico}).")
    if doc.doc_type == "invoice_out" and doc.partner_ico and comp_ico and _digits(doc.partner_ico) == comp_ico:
        warnings.append("Vystavená faktúra má ako odberateľa našu firmu – skontrolujte typ dokladu.")
    if doc.doc_type == "invoice_in" and doc.partner_ico and comp_ico and _digits(doc.partner_ico) == comp_ico:
        doc.doc_type = "invoice_out"
        warnings.append("Dodávateľom je naša firma – doklad bol zaradený ako vystavená faktúra.")

    # ---- project suggestion
    project, reason = suggest_project(db, doc, ex, sf)
    if doc.doc_type == "invoice_out":
        series = series_for_number(db, sf.company_id, doc.number)
        if series:
            doc.series_id = series.id
            if series.project_id and project is None:
                project, reason = db.get(Project, series.project_id), f"číselný rad {series.prefix}"
    if project is not None:
        ds.set_whole_project(_SysCtx(db, sf.uploaded_by), doc, project.id)
        log_lines.append(f"Návrh zákazky: {project.name} ({reason})")
    else:
        warnings.append("Zákazku sa nepodarilo určiť – priraďte ju ručne.")
    ds.set_warnings(doc, warnings)
    doc.extraction_log = "\n".join(log_lines)
    if ex.handwritten_note:
        doc.note = f"Poznámka na doklade: {ex.handwritten_note}"
    sf.status = "processed"
    sf.document_id = doc.id
    sf.error = None
    sf.processed_at = datetime.now(timezone.utc)
    return {"file": sf.original_name, "status": "processed", "document_id": doc.id, "source": source}


class _SysCtx:
    """Minimal ctx for service calls made by the pipeline (audit as the uploading user / system)."""

    def __init__(self, db, user_id):
        self.db = db
        self.user = type("U", (), {"id": user_id})()


def suggest_project(db: Session, doc: Document, ex: ExtractedDocument, sf: SourceFile) -> tuple[Project | None, str]:
    cid = doc.company_id
    # 1. manual note on the document or in the file name
    for text, why in ((ex.handwritten_note, "poznámka na doklade"), (sf.note, "poznámka pri nahratí"),
                      (re.sub(r"[_\-.]+", " ", sf.original_name), "názov súboru")):
        if text:
            p = match_project_in_text(db, cid, text)
            if p:
                return p, why
    # 2. recurring invoices -> overhead
    if doc.doc_type == "invoice_in":
        rule = recurring_rule_for(db, cid, doc.partner_ico, doc.partner_name)
        if rule:
            doc.recurring_rule_id = rule.id
            return ds.overhead_project(db, cid), f"opakujúca sa faktúra {rule.supplier_name}"
    # 3. fuel and car costs -> overhead (transport is costed per km)
    if doc.doc_type in ("receipt", "invoice_in") and is_overhead_supplier(
            db, cid, doc.partner_name, [ln.description or "" for ln in doc.lines]):
        return ds.overhead_project(db, cid), "čerpacia stanica / Réžia"
    # 4. AI hint
    if ex.project_hint:
        p = match_project_in_text(db, cid, ex.project_hint)
        if p:
            return p, "návrh AI"
    # 5. supplier history
    p = project_from_history(db, cid, doc.partner_ico)
    if p:
        return p, "história dodávateľa"
    return None, ""


def _register_duplicate(db: Session, sf: SourceFile, dup: Document, log_lines: list[str]) -> dict:
    """Duplicates are not created – the file is attached to the existing document."""
    role = "physical_scan" if sf.physical else "duplicate"
    attach_file(db, dup, sf, role, note="Duplicitný súbor")
    info = f"Duplicita – doklad už existuje (#{dup.id}, prijatý {dup.created_at:%d.%m.%Y})"
    if sf.physical and dup.doc_type == "receipt" and not dup.physical_original:
        dup.physical_original = True
        dup.physical_original_at = date.today()
        info += ", označený ako fyzicky založený"
    sf.status = "duplicate"
    sf.document_id = dup.id
    sf.error = info
    sf.processed_at = datetime.now(timezone.utc)
    dup.extraction_log = ((dup.extraction_log or "") + f"\n{datetime.now():%d.%m.%Y %H:%M}: {info} (súbor {sf.original_name})").strip()
    return {"file": sf.original_name, "status": "duplicate", "document_id": dup.id, "info": info,
            "log": log_lines}


def process_pending(db: Session, company_id: int, limit: int = 200) -> list[dict]:
    results = []
    files = (db.query(SourceFile).filter(SourceFile.company_id == company_id, SourceFile.status == "new")
             .order_by(SourceFile.id).limit(limit).all())
    for sf in files:
        try:
            results.append(process_source_file(db, sf))
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.exception("Processing failed for %s", sf.id)
            sf = db.get(SourceFile, sf.id)
            sf.status = "error"
            sf.error = f"Chyba spracovania: {exc}"
            db.commit()
            results.append({"file": sf.original_name, "status": "error", "info": sf.error})
    return results


def reprocess(ctx, ids: list[int]) -> dict:
    n = 0
    for i in ids:
        sf = ctx.db.get(SourceFile, int(i))
        if sf and sf.company_id == ctx.company_id and sf.status in ("error", "skipped", "new"):
            sf.status = "new"
            n += 1
    ctx.db.commit()
    res = process_pending(ctx.db, ctx.company_id)
    return {"message": f"Znova spracované: {n}", "results": res}


def quick_check(db: Session, company_id: int, *, ekasa_id: str | None = None, image: bytes | None = None) -> dict:
    """Fast physical receipt check: find by QR / ID and tell whether it is already registered."""
    found_ids: list[str] = []
    if image is not None:
        try:
            jpeg, _ = prep.normalize_image(image, max_side=3000)
        except Exception:  # noqa: BLE001
            jpeg = image
        found_ids = prep.decode_qr(jpeg) + prep.decode_qr(image)
    rid = prep.find_ekasa_id(([ekasa_id] if ekasa_id else []) + found_ids)
    if not rid:
        return {"found": False, "ekasa_id": None,
                "message": "QR kód s ID dokladu sa nepodarilo prečítať. Skúste znova alebo zadajte ID ručne."}
    doc = (db.query(Document).filter(Document.company_id == company_id, func.upper(Document.ekasa_id) == rid.upper(),
                                     Document.duplicate_of_id.is_(None)).first())
    if not doc:
        return {"found": False, "ekasa_id": rid, "message": "Bloček ešte nie je zaevidovaný."}
    src = db.get(SourceFile, doc.source_file_id) if doc.source_file_id else None
    return {"found": True, "ekasa_id": rid, "document_id": doc.id, "partner_name": doc.partner_name,
            "total_gross": float(doc.total_gross) if doc.total_gross is not None else None,
            "issue_date": doc.issue_date.isoformat() if doc.issue_date else None,
            "received_at": doc.created_at.isoformat() if doc.created_at else None,
            "received_from": src.source if src else None, "received_file": src.original_name if src else None,
            "physical_original": doc.physical_original,
            "message": "Už máš – bloček je zaevidovaný."}


_ = (or_, timedelta)
