"""Bank import + matching, billing statements, monthly check, VAT, fleet alerts."""
from datetime import date, timedelta

from tests.conftest import create

CAMT = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
 <BkToCstmrStmt><Stmt>
  <Acct><Id><IBAN>SK3112000000198742637541</IBAN></Id><Ccy>EUR</Ccy></Acct>
  <FrToDt><FrDtTm>2026-11-01T00:00:00</FrDtTm><ToDtTm>2026-11-30T23:59:59</ToDtTm></FrToDt>
  <Ntry><Amt Ccy="EUR">123.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-11-05</Dt></BookgDt>
   <NtryDtls><TxDtls><Refs><AcctSvcrRef>REF1</AcctSvcrRef><EndToEndId>/VS2026111/SS/KS0308</EndToEndId></Refs>
   <RltdPties><Cdtr><Nm>Hagard s.r.o.</Nm></Cdtr><CdtrAcct><Id><IBAN>SK1111000000000000000001</IBAN></Id></CdtrAcct></RltdPties>
   <RmtInf><Ustrd>Faktura 2026111</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
  <Ntry><Amt Ccy="EUR">45.90</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-11-06</Dt></BookgDt>
   <BkTxCd><Domn><Fmly><SubFmlyCd>CCRD</SubFmlyCd></Fmly></Domn></BkTxCd>
   <NtryDtls><TxDtls><Refs><AcctSvcrRef>REF2</AcctSvcrRef></Refs><RmtInf><Ustrd>OBI Bratislava platba kartou</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
  <Ntry><Amt Ccy="EUR">3.50</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-11-30</Dt></BookgDt>
   <NtryDtls><TxDtls><Refs><AcctSvcrRef>REF3</AcctSvcrRef></Refs><RmtInf><Ustrd>Poplatok za vedenie uctu</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
 </Stmt></BkToCstmrStmt></Document>"""


def _invoice(admin, number="2026111", total=123, doc_type="invoice_in", d="2026-11-01"):
    doc = admin.post("/api/documents/manual", json={"doc_type": doc_type}).json()
    admin.put(f"/api/documents/{doc['id']}/full", json={"header": {
        "number": number, "vs": number, "partner_name": "Hagard s.r.o.", "issue_date": d, "due_date": "2026-11-15",
        "total_net": round(total / 1.23, 2), "total_vat": round(total - total / 1.23, 2), "total_gross": total}})
    return doc["id"]


def test_bank_import_match_and_missing(admin):
    create(admin, "bank_accounts", {"iban": "SK31 1200 0000 1987 4263 7541"})
    create(admin, "transaction_rules", {"name": "Poplatky", "cond_text": "poplatok", "action": "no_document"})
    inv = _invoice(admin)
    r = admin.post("/api/bank/import", files={"file": ("vypis.xml", CAMT.encode(), "application/xml")})
    assert r.status_code == 200, r.text
    rows = {x["counterparty_name"] or x["message"]: x for x in
            admin.get("/api/data/bank_transactions", params={"columns": "counterparty_name,message,status,vs,tx_type,amount"}).json()["rows"]}
    assert rows["Hagard s.r.o."]["status"] == "matched" and rows["Hagard s.r.o."]["vs"] == "2026111"
    assert rows["Poplatok za vedenie uctu"]["status"] == "no_document"
    assert rows["OBI Bratislava platba kartou"]["status"] == "unmatched"
    assert rows["OBI Bratislava platba kartou"]["tx_type"] == "card"
    doc = admin.get(f"/api/documents/{inv}/full").json()
    assert doc["payment_status"] == "paid"
    # re-import same statement -> nothing new
    r = admin.post("/api/bank/import", files={"file": ("vypis.xml", CAMT.encode(), "application/xml")}).json()
    assert r.get("duplicate") is True
    missing = admin.get("/api/bank/missing").json()
    assert [t["message"] for t in missing["transactions_without_document"]] == ["OBI Bratislava platba kartou"]
    # manual match of the card payment to a receipt
    rec = admin.post("/api/documents/manual", json={"doc_type": "receipt"}).json()
    admin.put(f"/api/documents/{rec['id']}/full", json={"header": {"partner_name": "OBI", "issue_date": "2026-11-06",
                                                                   "total_gross": 45.9}})
    tx_id = next(x["id"] for x in admin.get("/api/data/bank_transactions").json()["rows"] if x["tx_type"] == "card")
    det = admin.post(f"/api/bank/transactions/{tx_id}/match", json={"document_id": rec["id"]}).json()
    assert det["status"] == "matched"


def test_bank_foreign_iban_rejected(admin, setup):
    admin.headers["X-Company-Id"] = str(setup["c2"])
    create(admin, "bank_accounts", {"iban": "SK3112000000198742637541"})
    admin.headers["X-Company-Id"] = str(setup["c1"])
    r = admin.post("/api/bank/import", files={"file": ("vypis.xml", CAMT.encode(), "application/xml")})
    assert r.status_code == 422 and "nepatrí aktívnej firme" in r.json()["detail"]


def test_bank_csv(admin):
    create(admin, "bank_accounts", {"iban": "SK3112000000198742637541"})
    csv_text = ("Dátum;Suma;Mena;Protistrana;IBAN protistrany;VS;Správa pre prijímateľa\n"
                "05.11.2026;-123,00;EUR;Hagard s.r.o.;SK1111000000000000000001;2026111;Faktura\n"
                "07.11.2026;1 230,00;EUR;Ján Novák;;P2026001;Úhrada faktúry\n")
    r = admin.post("/api/bank/import", files={"file": ("vypis.csv", csv_text.encode("cp1250"), "text/csv")})
    assert r.status_code == 200, r.text
    rows = admin.get("/api/data/bank_transactions", params={"sort": "booking_date:asc"}).json()["rows"]
    assert [x["amount"] for x in rows] == [-123.0, 1230.0]


def test_billing_statement_flow(admin):
    p = create(admin, "projects", {"name": "Sikorky", "bill_transport": True, "transport_rate_per_km": 0.5,
                                   "material_markup_pct": 10, "default_km_one_way": 10})
    w = create(admin, "workers", {"name": "Jano"})
    create(admin, "worker_rates", {"worker_id": w["id"], "cost_rate": 15, "billing_rate": 25})
    t1 = create(admin, "timesheets", {"worker_id": w["id"], "project_id": p["id"], "date": "2026-11-02", "hours": 8})
    create(admin, "timesheets", {"worker_id": w["id"], "project_id": p["id"], "date": "2026-11-03", "hours": 2,
                                 "billable": False})
    v = create(admin, "vehicles", {"name": "Auto", "initial_rate_per_km": 0.3})
    create(admin, "trips", {"vehicle_id": v["id"], "project_id": p["id"], "date": "2026-11-02"})
    doc = admin.post("/api/documents/manual", json={"doc_type": "receipt"}).json()
    admin.put(f"/api/documents/{doc['id']}/full", json={"header": {"issue_date": "2026-11-02", "total_net": 100,
                                                                   "total_vat": 23, "total_gross": 123}})
    admin.post("/api/data/documents/actions/set_project", json={"ids": [doc["id"]], "payload": {"project_id": p["id"]}})
    admin.post(f"/api/documents/{doc['id']}/confirm")
    body = {"project_id": p["id"], "date_from": "2026-11-01", "date_to": "2026-11-30"}
    prev = admin.post("/api/billing/preview", json=body).json()
    # 8 h × 25 = 200; material 100 × 1.1 = 110; transport 22 km × 0.5 = 11
    assert prev["total_net"] == 321.0 and prev["total_vat"] == 73.83
    st = admin.post("/api/billing", json=body).json()
    assert admin.get(f"/api/billing/{st['id']}/export", params={"format": "pdf"}).content[:4] == b"%PDF"
    assert admin.get(f"/api/billing/{st['id']}/export", params={"format": "xlsx"}).content[:2] == b"PK"
    assert admin.post(f"/api/billing/{st['id']}/close").status_code == 200
    # billed items are locked and no longer offered
    r = admin.patch(f"/api/data/timesheets/{t1['id']}", json={"hours": 9})
    assert r.status_code == 409
    assert admin.post("/api/billing/preview", json=body).json()["lines"] == []
    assert admin.post("/api/billing", json=body).status_code == 422
    prof = admin.get("/api/reports/profitability").json()
    assert prof["rows"][0]["wip"] == 0
    assert admin.post(f"/api/billing/{st['id']}/reopen").status_code == 200
    assert admin.patch(f"/api/data/timesheets/{t1['id']}", json={"hours": 9}).status_code == 200


def test_worker_statement_pdf(admin):
    p = create(admin, "projects", {"name": "Sikorky"})
    w = create(admin, "workers", {"name": "Jano Kováč", "relation_type": "contractor"})
    create(admin, "worker_rates", {"worker_id": w["id"], "cost_rate": 15})
    create(admin, "timesheets", {"worker_id": w["id"], "project_id": p["id"], "date": "2026-11-02",
                                 "time_from": "07:00", "time_to": "15:00", "description": "Obklady – kúpeľňa"})
    q = {"worker_id": w["id"], "date_from": "2026-11-01", "date_to": "2026-11-30"}
    d = admin.get("/api/worker-statement", params=q).json()
    assert d["total_hours"] == 8 and d["total_amount"] == 120
    pdf = admin.get("/api/worker-statement/export", params={**q, "format": "pdf"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_monthly_check_and_vat(admin):
    create(admin, "recurring_rules", {"supplier_name": "Orange Slovensko", "supplier_ico": "35697270"})
    p = create(admin, "projects", {"name": "Sikorky"})
    w = create(admin, "workers", {"name": "Jano"})
    old = (date.today() - timedelta(days=20)).isoformat()
    create(admin, "timesheets", {"worker_id": w["id"], "project_id": p["id"], "date": old, "hours": 1,
                                 "material_bought": True})
    y, m = int(old[:4]), int(old[5:7])
    mc = admin.get("/api/reports/monthly-check", params={"year": y, "month": m}).json()
    assert mc["missing_recurring"][0]["supplier"] == "Orange Slovensko"
    assert len(mc["material_without_document"]) == 1
    inv = _invoice(admin, number="OR1", total=24.6, d=old)
    admin.put(f"/api/documents/{inv}/full", json={"header": {"partner_ico": "35697270", "partner_name": "Orange"}})
    mc = admin.get("/api/reports/monthly-check", params={"year": y, "month": m}).json()
    assert mc["missing_recurring"] == []
    admin.post("/api/data/documents/actions/set_overhead", json={"ids": [inv]})
    admin.post(f"/api/documents/{inv}/confirm")
    vat = admin.get("/api/reports/vat", params={"year": y, "month": m}).json()
    assert vat["input_vat"] == 4.6


def test_fleet_alerts(admin):
    v = create(admin, "vehicles", {"name": "Transit", "plate": "BA1",
                                   "stk_valid_to": (date.today() + timedelta(days=5)).isoformat(),
                                   "ek_valid_to": (date.today() - timedelta(days=1)).isoformat()})
    create(admin, "vehicle_insurance", {"vehicle_id": v["id"], "insurer": "Allianz", "premium": 400,
                                        "valid_to": (date.today() + timedelta(days=300)).isoformat()})
    alerts = {a["kind"]: a for a in admin.get("/api/fleet/alerts").json()}
    assert alerts["stk"]["severity"] == "warning" and alerts["ek"]["severity"] == "error"
    assert "pzp" not in alerts and alerts["vignette"]["message"].endswith("chýba evidencia platnosti")
    chk = create(admin, "vehicle_checks", {"vehicle_id": v["id"], "service": "pzp", "result": "valid"})
    assert chk["matches"] is True
