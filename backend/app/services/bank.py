"""Bank statements: import, dedupe, rules, deterministic matching against documents, 'what is missing'."""
import hashlib
import logging
import re
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import (
    BankAccount, BankStatement, BankTransaction, Company, Document, SourceFile, TransactionMatch, TransactionRule,
)
from app.services import audit, bank_parsers
from app.services.calc import money
from app.services.settings import get_param

log = logging.getLogger(__name__)


class BankImportError(Exception):
    pass


def _norm(s: str | None) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in s if not unicodedata.combining(c)))


def _iban(s: str | None) -> str:
    return (s or "").replace(" ", "").upper()


# ----------------------------------------------------------------------------- PDF statements via Claude
class _PdfTx(BaseModel):
    booking_date: str
    amount: float
    counterparty_name: str | None = None
    counterparty_iban: str | None = None
    vs: str | None = None
    ss: str | None = None
    ks: str | None = None
    message: str | None = None
    tx_type: str | None = None


class _PdfStatement(BaseModel):
    iban: str | None = None
    period_from: str | None = None
    period_to: str | None = None
    transactions: list[_PdfTx] = []


def _parse_pdf(data: bytes) -> dict:
    from app.config import get_config
    cfg = get_config()
    if not cfg.anthropic_api_key:
        raise BankImportError("PDF výpis vyžaduje Claude API (ANTHROPIC_API_KEY). Použite radšej CAMT.053/CSV/XLSX.")
    import anthropic
    from app.services.extraction import b64
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    try:
        resp = client.messages.parse(
            model=cfg.claude_model, max_tokens=32000,
            system="Vyextrahuj všetky pohyby z bankového výpisu. Výdavky ako záporné sumy. Dátumy YYYY-MM-DD.",
            messages=[{"role": "user", "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64(data)}},
                {"type": "text", "text": "Vráť IBAN účtu, obdobie a všetky pohyby."}]}],
            output_format=_PdfStatement, output_config={"effort": "low"},
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"}, extra_body={"fallbacks": "default"})
    except anthropic.APIError as exc:
        raise BankImportError(f"Claude API chyba: {exc}") from exc
    st = resp.parsed_output
    if st is None:
        raise BankImportError("Z PDF sa nepodarilo načítať pohyby.")
    txs = []
    for t in st.transactions:
        try:
            d = date.fromisoformat(t.booking_date[:10])
        except ValueError:
            continue
        txs.append({"booking_date": d, "value_date": None, "amount": Decimal(str(t.amount)), "currency": "EUR",
                    "counterparty_name": t.counterparty_name, "counterparty_iban": _iban(t.counterparty_iban) or None,
                    "vs": t.vs, "ss": t.ss, "ks": t.ks, "message": t.message, "bank_ref": None,
                    "tx_type": bank_parsers.classify(f"{t.tx_type or ''} {t.message or ''}")})
    return {"iban": _iban(st.iban) or None,
            "period_from": date.fromisoformat(st.period_from[:10]) if st.period_from else None,
            "period_to": date.fromisoformat(st.period_to[:10]) if st.period_to else None, "transactions": txs}


# ----------------------------------------------------------------------------- import
def dedupe_key(tx: dict, account_id: int | None) -> str:
    base = "|".join(str(x) for x in (account_id, tx["booking_date"], money(tx["amount"]), tx.get("bank_ref") or "",
                                       tx.get("vs") or "", _norm(tx.get("counterparty_name"))[:40],
                                       _norm(tx.get("message"))[:60]))
    return hashlib.sha1(base.encode()).hexdigest()


def import_statement_file(db: Session, company: Company, sf: SourceFile, data: bytes) -> BankStatement:
    try:
        fmt, parsed = bank_parsers.parse_any(sf.original_name, data)
    except bank_parsers.ParseError as exc:
        if data[:4] == b"%PDF":
            fmt, parsed = "pdf", _parse_pdf(data)
        else:
            raise BankImportError(str(exc)) from exc
    iban = _iban(parsed.get("iban"))
    account = None
    if iban:
        account = db.query(BankAccount).filter(func.replace(func.upper(BankAccount.iban), " ", "") == iban).first()
        if account is None:
            raise BankImportError(f"IBAN {iban} nie je evidovaný pri žiadnej firme. Pridajte ho v Číselníky → Bankové účty.")
        if account.company_id != company.id:
            raise BankImportError(f"IBAN {iban} nepatrí aktívnej firme – výpis sa nespracoval.")
    else:
        accounts = db.query(BankAccount).filter(BankAccount.company_id == company.id, BankAccount.active.is_(True)).all()
        if len(accounts) == 1:
            account = accounts[0]
        else:
            raise BankImportError("Výpis neobsahuje IBAN a firma nemá práve jeden aktívny účet – nedá sa priradiť.")
    st = BankStatement(company_id=company.id, bank_account_id=account.id, period_from=parsed.get("period_from"),
                       period_to=parsed.get("period_to"), source_file_id=sf.id, format=fmt)
    db.add(st)
    db.flush()
    new = 0
    seen = set()
    for tx in parsed["transactions"]:
        if tx.get("booking_date") is None:
            continue
        key = dedupe_key(tx, account.id)
        if key in seen:
            # identical rows in one statement are legitimate (e.g. two equal card payments) – make them unique
            n = 2
            while f"{key}#{n}" in seen:
                n += 1
            key = f"{key}#{n}"
        seen.add(key)
        if db.query(BankTransaction.id).filter(BankTransaction.company_id == company.id,
                                               BankTransaction.dedupe_key == key).first():
            continue
        db.add(BankTransaction(
            company_id=company.id, statement_id=st.id, bank_account_id=account.id, booking_date=tx["booking_date"],
            value_date=tx.get("value_date"), amount=money(tx["amount"]), currency=tx.get("currency") or "EUR",
            counterparty_name=(tx.get("counterparty_name") or None), counterparty_iban=_iban(tx.get("counterparty_iban")) or None,
            vs=tx.get("vs"), ss=tx.get("ss"), ks=tx.get("ks"), message=tx.get("message"),
            tx_type=tx.get("tx_type") or "other", bank_ref=tx.get("bank_ref"), dedupe_key=key))
        new += 1
    st.tx_count = len(parsed["transactions"])
    st.new_tx_count = new
    db.flush()
    apply_rules(db, company.id)
    match_company(db, company.id)
    return st


# ----------------------------------------------------------------------------- rules
def rule_matches(rule: TransactionRule, tx: BankTransaction) -> bool:
    conds = []
    if rule.cond_counterparty:
        conds.append(_norm(rule.cond_counterparty).strip() in _norm(tx.counterparty_name))
    if rule.cond_iban:
        conds.append(_iban(rule.cond_iban) == _iban(tx.counterparty_iban))
    if rule.cond_text:
        conds.append(_norm(rule.cond_text).strip() in _norm(f"{tx.message or ''} {tx.counterparty_name or ''}"))
    if rule.cond_type:
        conds.append(rule.cond_type == tx.tx_type)
    return bool(conds) and all(conds)


def apply_rules(db: Session, company_id: int) -> int:
    rules = db.query(TransactionRule).filter(TransactionRule.company_id == company_id,
                                             TransactionRule.active.is_(True)).all()
    n = 0
    for tx in db.query(BankTransaction).filter(BankTransaction.company_id == company_id,
                                               BankTransaction.status == "unmatched"):
        for r in rules:
            if rule_matches(r, tx):
                tx.rule_id = r.id
                if r.action == "no_document":
                    tx.status = "no_document"
                    n += 1
                else:
                    tx.note = (tx.note or "") + f" [{r.name}: {r.action_value or ''}]"
                break
    return n


# ----------------------------------------------------------------------------- matching
def _doc_open_amount(db: Session, doc: Document) -> Decimal:
    paid = db.query(func.coalesce(func.sum(TransactionMatch.amount), 0)).filter(
        TransactionMatch.document_id == doc.id, TransactionMatch.confirmed.is_(True)).scalar()
    return Decimal(doc.total_gross or 0) - Decimal(paid or 0)


def _vs_match(tx: BankTransaction, doc: Document) -> bool:
    if not tx.vs:
        return False
    vs = tx.vs.lstrip("0")
    cands = {(doc.vs or "").lstrip("0"), re.sub(r"\D", "", doc.number or "").lstrip("0")}
    return bool(vs) and vs in cands


def _name_match(a: str | None, b: str | None) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na.strip() or not nb.strip():
        return False
    ta = {w for w in na.split() if len(w) >= 3 and w not in ("sro", "spol", "a s", "s r o")}
    tb = {w for w in nb.split() if len(w) >= 3}
    return bool(ta & tb)


def candidates_for(db: Session, tx: BankTransaction, tolerance_days: int) -> list[tuple[Document, int, str]]:
    """Return candidate documents with a score and reason (higher = better)."""
    amount = abs(Decimal(tx.amount))
    if tx.amount < 0:
        types = ("invoice_in", "receipt")
    else:
        types = ("invoice_out",)
    q = db.query(Document).filter(Document.company_id == tx.company_id, Document.doc_type.in_(types),
                                  Document.duplicate_of_id.is_(None), Document.payment_status != "paid")
    out = []
    lo = tx.booking_date - timedelta(days=120)
    hi = tx.booking_date + timedelta(days=tolerance_days)
    for doc in q.filter(or_(Document.issue_date.is_(None), Document.issue_date.between(lo, hi))):
        open_amt = _doc_open_amount(db, doc)
        if open_amt <= 0:
            continue
        amt_eq = abs(open_amt - amount) <= Decimal("0.01")
        score, why = 0, []
        if _vs_match(tx, doc):
            score += 60
            why.append("VS")
        if amt_eq:
            score += 30
            why.append("suma")
        if doc.partner_iban and _iban(doc.partner_iban) == _iban(tx.counterparty_iban):
            score += 25
            why.append("IBAN")
        if _name_match(doc.partner_name, tx.counterparty_name) or _name_match(doc.partner_name, tx.message):
            score += 15
            why.append("názov")
        if doc.issue_date:
            ref = doc.due_date or doc.issue_date
            if doc.issue_date - timedelta(days=tolerance_days) <= tx.booking_date <= ref + timedelta(days=tolerance_days):
                score += 10
                why.append("dátum")
            if doc.doc_type == "receipt" and abs((tx.booking_date - doc.issue_date).days) > tolerance_days:
                continue  # card payments are booked within a few days
        if score >= 30 and (amt_eq or "VS" in why):
            out.append((doc, score, ", ".join(why)))
    out.sort(key=lambda x: -x[1])
    return out


def _add_match(db: Session, tx: BankTransaction, doc: Document, amount: Decimal, method: str, reason: str,
               confirmed: bool) -> TransactionMatch:
    m = TransactionMatch(company_id=tx.company_id, transaction_id=tx.id, document_id=doc.id, amount=money(amount),
                         method=method, reason=reason, confirmed=confirmed)
    db.add(m)
    db.flush()
    return m


def refresh_tx(db: Session, tx: BankTransaction) -> None:
    ms = db.query(TransactionMatch).filter(TransactionMatch.transaction_id == tx.id).all()
    confirmed = sum((Decimal(m.amount) for m in ms if m.confirmed), Decimal(0))
    tx.matched_amount = money(confirmed)
    if tx.status == "no_document":
        return
    if confirmed > 0:
        tx.status = "matched"
    elif ms:
        tx.status = "suggested"
    else:
        tx.status = "unmatched"


def refresh_doc_payment(db: Session, doc: Document) -> None:
    paid = db.query(func.coalesce(func.sum(TransactionMatch.amount), 0)).filter(
        TransactionMatch.document_id == doc.id, TransactionMatch.confirmed.is_(True)).scalar() or 0
    doc.paid_amount = money(paid)
    total = Decimal(doc.total_gross or 0)
    if paid <= 0:
        doc.payment_status = "unpaid"
    elif Decimal(paid) + Decimal("0.01") >= total:
        doc.payment_status = "paid"
    else:
        doc.payment_status = "partial"


def match_transaction(db: Session, tx: BankTransaction, tolerance_days: int) -> str:
    if tx.status in ("matched", "no_document"):
        return tx.status
    if db.query(TransactionMatch).filter(TransactionMatch.transaction_id == tx.id).first():
        return tx.status
    cands = candidates_for(db, tx, tolerance_days)
    if not cands:
        tx.status = "unmatched"
        return tx.status
    best, score, why = cands[0]
    unique = len(cands) == 1 or cands[1][1] < score
    strong = ("VS" in why and "suma" in why) or ("suma" in why and ("IBAN" in why or "názov" in why) and unique)
    amount = min(abs(Decimal(tx.amount)), _doc_open_amount(db, best))
    if strong and unique:
        _add_match(db, tx, best, amount, "auto", why, True)
        refresh_doc_payment(db, best)
    else:
        for doc, s, w in cands[:3]:
            _add_match(db, tx, doc, min(abs(Decimal(tx.amount)), _doc_open_amount(db, doc)), "suggested", w, False)
    refresh_tx(db, tx)
    return tx.status


def match_company(db: Session, company_id: int) -> dict:
    tol = int(get_param(db, "bank_match_days", company_id) or 5)
    stats: dict[str, int] = {}
    for tx in (db.query(BankTransaction).filter(BankTransaction.company_id == company_id,
                                                BankTransaction.status.in_(("unmatched",)))
               .order_by(BankTransaction.booking_date)):
        s = match_transaction(db, tx, tol)
        stats[s] = stats.get(s, 0) + 1
    return stats


# ----------------------------------------------------------------------------- manual operations
def _load_tx(ctx, tx_id: int) -> BankTransaction:
    tx = ctx.db.get(BankTransaction, tx_id)
    if not tx or tx.company_id != ctx.company_id:
        raise HTTPException(404, "Pohyb neexistuje v aktívnej firme.")
    return tx


def manual_match(ctx, tx_id: int, document_id: int, amount: Decimal | None) -> None:
    db = ctx.db
    tx = _load_tx(ctx, tx_id)
    doc = db.get(Document, document_id)
    if not doc or doc.company_id != ctx.company_id:
        raise HTTPException(404, "Doklad neexistuje v aktívnej firme.")
    remaining = abs(Decimal(tx.amount)) - Decimal(tx.matched_amount or 0)
    amt = money(amount if amount is not None else min(remaining, _doc_open_amount(db, doc)))
    if amt <= 0:
        raise HTTPException(422, "Suma párovania musí byť kladná.")
    existing = db.query(TransactionMatch).filter(TransactionMatch.transaction_id == tx.id,
                                                 TransactionMatch.document_id == doc.id).first()
    if existing:
        existing.amount, existing.confirmed, existing.method = amt, True, "manual"
    else:
        _add_match(db, tx, doc, amt, "manual", "ručne", True)
    if tx.status == "no_document":
        tx.status = "unmatched"
    refresh_tx(db, tx)
    refresh_doc_payment(db, doc)
    audit.log(db, user_id=ctx.user.id, company_id=ctx.company_id, entity="bank_transactions", entity_id=tx.id,
              action="match", changes={"document_id": (None, doc.id), "amount": (None, amt)})
    db.commit()


def confirm_match(ctx, match_id: int) -> None:
    db = ctx.db
    m = db.get(TransactionMatch, match_id)
    if not m or m.company_id != ctx.company_id:
        raise HTTPException(404, "Párovanie neexistuje.")
    m.confirmed = True
    tx = db.get(BankTransaction, m.transaction_id)
    # other suggestions for the same transaction are dropped
    for other in db.query(TransactionMatch).filter(TransactionMatch.transaction_id == tx.id,
                                                   TransactionMatch.confirmed.is_(False)):
        db.delete(other)
    db.flush()
    refresh_tx(db, tx)
    refresh_doc_payment(db, db.get(Document, m.document_id))
    audit.log(db, user_id=ctx.user.id, company_id=ctx.company_id, entity="bank_transactions", entity_id=tx.id,
              action="confirm_match", changes={"document_id": (None, m.document_id)})
    db.commit()


def delete_match(ctx, match_id: int) -> None:
    db = ctx.db
    m = db.get(TransactionMatch, match_id)
    if not m or m.company_id != ctx.company_id:
        raise HTTPException(404, "Párovanie neexistuje.")
    tx = db.get(BankTransaction, m.transaction_id)
    doc = db.get(Document, m.document_id)
    db.delete(m)
    db.flush()
    refresh_tx(db, tx)
    if doc:
        refresh_doc_payment(db, doc)
    audit.log(db, user_id=ctx.user.id, company_id=ctx.company_id, entity="bank_transactions", entity_id=tx.id,
              action="unmatch", changes={"document_id": (m.document_id, None)})
    db.commit()


def action_no_document(ctx, ids, payload):
    db = ctx.db
    n = 0
    for i in ids:
        tx = _load_tx(ctx, int(i))
        if db.query(TransactionMatch).filter(TransactionMatch.transaction_id == tx.id,
                                             TransactionMatch.confirmed.is_(True)).first():
            continue
        db.query(TransactionMatch).filter(TransactionMatch.transaction_id == tx.id).delete()
        tx.status = "no_document"
        n += 1
        if payload.get("create_rule"):
            r = TransactionRule(company_id=ctx.company_id, name=f"Bez dokladu: {tx.counterparty_name or tx.message or ''}"[:200],
                                cond_counterparty=tx.counterparty_name if tx.counterparty_name else None,
                                cond_iban=tx.counterparty_iban if not tx.counterparty_name else None,
                                cond_text=None if (tx.counterparty_name or tx.counterparty_iban) else (tx.message or "")[:200],
                                action="no_document")
            db.add(r)
        audit.log(db, user_id=ctx.user.id, company_id=ctx.company_id, entity="bank_transactions", entity_id=tx.id,
                  action="no_document")
    db.commit()
    return {"message": f"Označené ako bez dokladu: {n}"}


def action_reset(ctx, ids, payload):
    db = ctx.db
    for i in ids:
        tx = _load_tx(ctx, int(i))
        docs = [m.document_id for m in db.query(TransactionMatch).filter(TransactionMatch.transaction_id == tx.id)]
        db.query(TransactionMatch).filter(TransactionMatch.transaction_id == tx.id).delete()
        tx.status = "unmatched"
        tx.rule_id = None
        db.flush()
        refresh_tx(db, tx)
        for d in docs:
            doc = db.get(Document, d)
            if doc:
                refresh_doc_payment(db, doc)
    db.commit()
    return {"message": "Zrušené."}


def action_confirm_suggestions(ctx, ids, payload):
    db = ctx.db
    n = 0
    for i in ids:
        tx = _load_tx(ctx, int(i))
        sug = (db.query(TransactionMatch).filter(TransactionMatch.transaction_id == tx.id,
                                                 TransactionMatch.confirmed.is_(False)).order_by(TransactionMatch.id).first())
        if sug:
            confirm_match(ctx, sug.id)
            n += 1
    return {"message": f"Potvrdené: {n}"}


def action_rematch(ctx, ids, payload):
    db = ctx.db
    apply_rules(db, ctx.company_id)
    stats = match_company(db, ctx.company_id)
    db.commit()
    return {"message": "Párovanie dokončené: " + ", ".join(f"{k}: {v}" for k, v in stats.items())}


def tx_detail(ctx, tx_id: int) -> dict:
    from app.registry.base import serialize
    db = ctx.db
    tx = _load_tx(ctx, tx_id)
    matches = []
    for m in db.query(TransactionMatch).filter(TransactionMatch.transaction_id == tx.id):
        d = db.get(Document, m.document_id)
        matches.append({"id": m.id, "document_id": m.document_id, "amount": serialize(m.amount), "method": m.method,
                        "reason": m.reason, "confirmed": m.confirmed,
                        "doc": {"number": d.number, "partner_name": d.partner_name, "doc_type": d.doc_type,
                                "issue_date": serialize(d.issue_date), "total_gross": serialize(d.total_gross)} if d else None})
    tol = int(get_param(db, "bank_match_days", ctx.company_id) or 5)
    cands = [{"document_id": d.id, "score": s, "reason": w, "number": d.number, "partner_name": d.partner_name,
              "doc_type": d.doc_type, "issue_date": serialize(d.issue_date), "total_gross": serialize(d.total_gross)}
             for d, s, w in candidates_for(db, tx, tol)[:10]]
    return {"id": tx.id, "booking_date": serialize(tx.booking_date), "amount": serialize(tx.amount),
            "currency": tx.currency, "counterparty_name": tx.counterparty_name,
            "counterparty_iban": tx.counterparty_iban, "vs": tx.vs, "ss": tx.ss, "ks": tx.ks, "message": tx.message,
            "tx_type": tx.tx_type, "status": tx.status, "matched_amount": serialize(tx.matched_amount),
            "note": tx.note, "matches": matches, "candidates": cands}


def missing_report(db: Session, company_id: int, d_from: date | None, d_to: date | None) -> dict:
    """'Čo chýba': transactions without documents, documents without payment, amount mismatches."""
    from app.registry.base import serialize
    q = db.query(BankTransaction).filter(BankTransaction.company_id == company_id,
                                         BankTransaction.status.in_(("unmatched", "suggested")))
    if d_from:
        q = q.filter(BankTransaction.booking_date >= d_from)
    if d_to:
        q = q.filter(BankTransaction.booking_date <= d_to)
    tx_missing = [{"id": t.id, "date": serialize(t.booking_date), "amount": serialize(t.amount),
                   "counterparty": t.counterparty_name, "message": t.message, "type": t.tx_type, "status": t.status}
                  for t in q.order_by(BankTransaction.booking_date)]
    today = date.today()
    dq = db.query(Document).filter(Document.company_id == company_id, Document.doc_type.in_(("invoice_in", "invoice_out")),
                                   Document.payment_status != "paid", Document.duplicate_of_id.is_(None))
    if d_to:
        dq = dq.filter(or_(Document.issue_date.is_(None), Document.issue_date <= d_to))
    unpaid = [{"id": d.id, "doc_type": d.doc_type, "number": d.number, "partner": d.partner_name,
               "issue_date": serialize(d.issue_date), "due_date": serialize(d.due_date),
               "total_gross": serialize(d.total_gross), "paid_amount": serialize(d.paid_amount),
               "overdue": bool(d.due_date and d.due_date < today)} for d in dq.order_by(Document.due_date)]
    mismatches = []
    for t in db.query(BankTransaction).filter(BankTransaction.company_id == company_id, BankTransaction.status == "matched"):
        if abs(abs(Decimal(t.amount)) - Decimal(t.matched_amount or 0)) > Decimal("0.01"):
            if (d_from is None or t.booking_date >= d_from) and (d_to is None or t.booking_date <= d_to):
                mismatches.append({"id": t.id, "date": serialize(t.booking_date), "amount": serialize(t.amount),
                                   "matched_amount": serialize(t.matched_amount), "counterparty": t.counterparty_name})
    return {"transactions_without_document": tx_missing, "documents_without_payment": unpaid,
            "amount_mismatches": mismatches}
