"""Bank statement parsers: CAMT.053 (ISO 20022), CSV, XLSX. Output: neutral dicts."""
import csv
import io
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class ParseError(Exception):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el, path: str):
    """Namespace-agnostic find by local names, path like 'Ntry/Amt'."""
    cur = [el]
    for part in path.split("/"):
        nxt = []
        for c in cur:
            nxt.extend(ch for ch in c if _local(ch.tag) == part)
        cur = nxt
        if not cur:
            return None
    return cur[0]


def _findall(el, name: str):
    return [ch for ch in el.iter() if _local(ch.tag) == name]


def _text(el, path: str) -> str | None:
    f = _find(el, path)
    return f.text.strip() if f is not None and f.text else None


def _symbols_from_text(text: str) -> dict:
    out = {}
    for key, pat in (("vs", r"(?:VS|/VS)[:\s]*([0-9]{1,10})"), ("ss", r"(?:SS|/SS)[:\s]*([0-9]{1,10})"),
                     ("ks", r"(?:KS|/KS)[:\s]*([0-9]{1,4})")):
        m = re.search(pat, text or "", re.IGNORECASE)
        if m:
            out[key] = m.group(1).lstrip("0") or "0"
    return out


def parse_camt053(data: bytes) -> dict:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ParseError(f"Neplatné XML: {exc}") from exc
    stmts = _findall(root, "Stmt")
    if not stmts:
        raise ParseError("XML neobsahuje výpis CAMT.053 (element Stmt).")
    result = {"iban": None, "currency": None, "period_from": None, "period_to": None, "transactions": []}
    for st in stmts:
        result["iban"] = result["iban"] or _text(st, "Acct/Id/IBAN")
        result["currency"] = result["currency"] or _text(st, "Acct/Ccy")
        fr, to = _text(st, "FrToDt/FrDtTm"), _text(st, "FrToDt/ToDtTm")
        if fr:
            result["period_from"] = date.fromisoformat(fr[:10])
        if to:
            result["period_to"] = date.fromisoformat(to[:10])
        for n in [ch for ch in st if _local(ch.tag) == "Ntry"]:
            amt_el = _find(n, "Amt")
            amount = Decimal(amt_el.text.strip())
            if _text(n, "CdtDbtInd") == "DBIT":
                amount = -amount
            booking = _text(n, "BookgDt/Dt") or (_text(n, "BookgDt/DtTm") or "")[:10]
            value = _text(n, "ValDt/Dt") or (_text(n, "ValDt/DtTm") or "")[:10]
            dbit = amount < 0
            tx = _find(n, "NtryDtls/TxDtls")
            cp_name = cp_iban = msg = ref = None
            e2e = None
            if tx is not None:
                party = "Cdtr" if dbit else "Dbtr"
                cp_name = _text(tx, f"RltdPties/{party}/Nm") or _text(tx, f"RltdPties/{party}/Pty/Nm")
                cp_iban = _text(tx, f"RltdPties/{party}Acct/Id/IBAN")
                msg = " ".join(e.text.strip() for e in _findall(tx, "Ustrd") if e.text)
                e2e = _text(tx, "Refs/EndToEndId")
                ref = _text(tx, "Refs/AcctSvcrRef") or _text(tx, "Refs/TxId")
            ref = ref or _text(n, "AcctSvcrRef") or _text(n, "NtryRef")
            addtl = _text(n, "AddtlNtryInf") or ""
            symbols = _symbols_from_text(f"{e2e or ''} {msg or ''} {addtl}")
            if e2e and e2e.upper() != "NOTPROVIDED":
                m = re.match(r"^/?VS(\d+)/SS(\d*)/KS(\d*)", e2e.replace(" ", ""), re.IGNORECASE)
                if m:
                    symbols = {"vs": m.group(1).lstrip("0"), "ss": m.group(2).lstrip("0") or None,
                               "ks": m.group(3).lstrip("0") or None}
            domain = (_text(n, "BkTxCd/Domn/Fmly/SubFmlyCd") or "") + " " + (_text(n, "BkTxCd/Prtry/Cd") or "")
            result["transactions"].append({
                "booking_date": date.fromisoformat(booking) if booking else None,
                "value_date": date.fromisoformat(value) if value else None,
                "amount": amount, "currency": amt_el.get("Ccy") or result["currency"] or "EUR",
                "counterparty_name": cp_name, "counterparty_iban": cp_iban,
                "message": (msg or addtl or None), "bank_ref": ref, **symbols,
                "tx_type": classify(domain + " " + (msg or "") + " " + addtl, cp_name),
            })
    return result


def classify(text: str, counterparty: str | None = None) -> str:
    t = (text or "").lower()
    if any(k in t for k in ("ccrd", "pos", "karta", "kartou", "card", "platba kartou", "debit card")):
        return "card"
    if any(k in t for k in ("chrg", "poplatok", "fee", "vedenie účtu", "vedenie uctu")):
        return "fee"
    if any(k in t for k in ("trf", "prevod", "úhrada", "uhrada", "transfer", "sepa", "dmct", "rcdt")):
        return "transfer"
    return "other"


# ----------------------------------------------------------------------------- CSV / XLSX
HEADER_MAP = {
    "booking_date": ["dátum zaúčtovania", "datum zauctovania", "dátum", "datum", "date", "booking date",
                     "dátum transakcie", "datum transakcie", "dátum operácie", "datum operacie", "zaúčtované"],
    "value_date": ["dátum valuty", "datum valuty", "value date", "valuta"],
    "amount": ["suma", "čiastka", "ciastka", "amount", "objem", "suma v mene účtu", "suma transakcie"],
    "debit": ["debet", "výdavok", "vydavok", "debit", "odpísané", "odpisane"],
    "credit": ["kredit", "príjem", "prijem", "credit", "pripísané", "pripisane"],
    "currency": ["mena", "currency"],
    "counterparty_name": ["protistrana", "názov protistrany", "nazov protistrany", "názov účtu protistrany",
                          "príjemca", "prijemca", "platiteľ", "platitel", "obchodník", "counterparty", "partner",
                          "meno protistrany", "popis protistrany"],
    "counterparty_iban": ["iban protistrany", "účet protistrany", "ucet protistrany", "protiúčet", "protiucet",
                          "counterparty account", "číslo účtu protistrany", "iban"],
    "vs": ["vs", "variabilný symbol", "variabilny symbol"],
    "ss": ["ss", "špecifický symbol", "specificky symbol"],
    "ks": ["ks", "konštantný symbol", "konstantny symbol"],
    "message": ["správa pre prijímateľa", "sprava pre prijimatela", "správa", "sprava", "popis", "poznámka",
                "poznamka", "informácia pre príjemcu", "detail", "description", "účel", "ucel", "referencia platiteľa"],
    "tx_type": ["typ transakcie", "typ", "druh transakcie", "type"],
    "bank_ref": ["referencia", "id transakcie", "transaction id", "reference", "identifikácia transakcie"],
}


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _map_headers(headers: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    normed = [_norm(h) for h in headers]
    for key, names in HEADER_MAP.items():
        cand = [_norm(n) for n in names]
        for i, h in enumerate(normed):
            if h in cand and key not in out and i not in out.values():
                out[key] = i
    if "amount" not in out and not ("debit" in out or "credit" in out):
        for i, h in enumerate(normed):
            if "suma" in h or "amount" in h:
                out["amount"] = i
                break
    if "booking_date" not in out:
        for i, h in enumerate(normed):
            if "datum" in h or "date" in h:
                out["booking_date"] = i
                break
    return out


def _parse_amount(v) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    s = str(v).strip().replace("\xa0", "").replace(" ", "").replace("EUR", "").replace("€", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10]
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y", "%Y%m%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _rows_to_result(rows: list[list]) -> dict:
    # find the header row (first row that maps a date and an amount)
    for idx, row in enumerate(rows[:30]):
        hm = _map_headers([str(c or "") for c in row])
        if "booking_date" in hm and ("amount" in hm or "debit" in hm or "credit" in hm):
            break
    else:
        raise ParseError("Nepodarilo sa nájsť hlavičku s dátumom a sumou.")
    txs = []
    iban = None
    for row in rows[idx + 1:]:
        if not row or all(c in (None, "") for c in row):
            continue

        def g(k):
            i = hm.get(k)
            return row[i] if i is not None and i < len(row) else None
        d = _parse_date(g("booking_date"))
        amount = _parse_amount(g("amount"))
        if amount is None:
            deb, cre = _parse_amount(g("debit")), _parse_amount(g("credit"))
            if deb:
                amount = -abs(deb)
            elif cre:
                amount = abs(cre)
        if d is None or amount is None:
            continue
        msg = str(g("message") or "").strip() or None
        sym = {k: (str(g(k)).strip().lstrip("0") or None) if g(k) not in (None, "") else None for k in ("vs", "ss", "ks")}
        if not sym["vs"]:
            sym.update({k: v for k, v in _symbols_from_text(msg or "").items() if v})
        typ_raw = str(g("tx_type") or "")
        txs.append({
            "booking_date": d, "value_date": _parse_date(g("value_date")), "amount": amount,
            "currency": str(g("currency") or "EUR").strip()[:3] or "EUR",
            "counterparty_name": (str(g("counterparty_name")).strip() or None) if g("counterparty_name") else None,
            "counterparty_iban": (str(g("counterparty_iban")).replace(" ", "").upper() or None) if g("counterparty_iban") else None,
            "message": msg, "bank_ref": (str(g("bank_ref")).strip() or None) if g("bank_ref") else None,
            "tx_type": classify(typ_raw + " " + (msg or ""), None), **sym,
        })
    # IBAN of own account often appears in the preamble
    for row in rows[:idx]:
        for c in row:
            m = re.search(r"\b[A-Z]{2}\d{2}(?:\s?[0-9A-Z]{4}){4,7}\b", str(c or ""))
            if m:
                iban = m.group(0).replace(" ", "")
                break
        if iban:
            break
    if not txs:
        raise ParseError("Súbor neobsahuje žiadne pohyby.")
    dates = [t["booking_date"] for t in txs]
    return {"iban": iban, "currency": None, "period_from": min(dates), "period_to": max(dates), "transactions": txs}


def parse_csv(data: bytes) -> dict:
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:5000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    return _rows_to_result(rows)


def parse_xlsx(data: bytes) -> dict:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Neplatný XLSX: {exc}") from exc
    ws = wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    return _rows_to_result(rows)


def parse_any(name: str, data: bytes) -> tuple[str, dict]:
    head = data[:200].lstrip()
    lname = name.lower()
    if head.startswith(b"<?xml") or lname.endswith(".xml") or b"<Document" in head:
        return "camt053", parse_camt053(data)
    if data[:2] == b"PK" or lname.endswith(".xlsx"):
        return "xlsx", parse_xlsx(data)
    if data[:4] == b"%PDF":
        raise ParseError("PDF výpis – použije sa extrakcia cez Claude API.")
    return "csv", parse_csv(data)
