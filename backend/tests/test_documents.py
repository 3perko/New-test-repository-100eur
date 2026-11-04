"""Documents: manual entry, allocations/splitting, confirmation, inbox processing (QR/eKasa), duplicates."""
import io

import cv2
import numpy as np
import pytest

from tests.conftest import create

RID = "O-0123456789ABCDEF0123456789ABCDEF"


def qr_png(text: str) -> bytes:
    enc = cv2.QRCodeEncoder.create()
    img = enc.encode(text)
    img = cv2.resize(img, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    img = cv2.copyMakeBorder(img, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


EKASA_RECEIPT = {
    "receiptId": RID, "ico": "35815256", "issueDate": "02.11.2026 14:05:31", "receiptNumber": 77,
    "totalPrice": 24.6, "taxBaseBasic": 20.0, "vatAmountBasic": 4.6, "vatRateBasic": 23,
    "organization": {"name": "OBI Bratislava", "ico": "35815256", "dic": "2020000000"},
    "items": [{"name": "Lepiaca páska", "quantity": 2, "vatRate": 23, "price": 6.15},
              {"name": "Silikón", "quantity": 1, "vatRate": 23, "price": 18.45}],
}


@pytest.fixture()
def project(admin):
    return create(admin, "projects", {"name": "Sikorky", "aliases": "sikorky rd"})


@pytest.fixture()
def project2(admin):
    return create(admin, "projects", {"name": "Lúky"})


def _doc_with_lines(admin):
    d = admin.post("/api/documents/manual", json={"doc_type": "receipt"}).json()
    full = admin.put(f"/api/documents/{d['id']}/full", json={
        "header": {"partner_name": "OBI", "partner_ico": "35815256", "issue_date": "2026-11-02", "total_gross": "24,60"},
        "lines": [{"description": "Páska", "quantity": 2, "vat_rate": 23, "total_gross": 6.15},
                  {"description": "Silikón", "quantity": 1, "vat_rate": 23, "total_gross": 18.45}],
    }).json()
    return full


def test_manual_document_split_and_confirm(admin, project, project2):
    full = _doc_with_lines(admin)
    assert full["total_gross"] == 24.6 and full["lines"][0]["total_net"] == 5.0
    l1, l2 = full["lines"]
    # mixed: line 1 split evenly to two projects, line 2 to one project
    r = admin.put(f"/api/documents/{full['id']}/full", json={"allocations": [
        {"line_id": l1["id"], "project_id": project["id"], "amount_gross": 3.08},
        {"line_id": l1["id"], "project_id": project2["id"], "amount_gross": 3.07},
        {"line_id": l2["id"], "project_id": project["id"], "share_pct": 100}]})
    assert r.status_code == 200, r.text
    r = admin.post(f"/api/documents/{full['id']}/confirm")
    assert r.status_code == 200, r.text
    costs = admin.get("/api/reports/project-costs").json()["rows"]
    by = {x["project_name"]: x for x in costs}
    # VAT payer -> net amounts: 15.00 + 2.50 (half of 5.00)
    assert by["Sikorky"]["material_receipts"] == pytest.approx(17.5, abs=0.02)
    assert by["Lúky"]["material_receipts"] == pytest.approx(2.5, abs=0.02)


def test_confirm_rejects_wrong_sum(admin, project):
    full = _doc_with_lines(admin)
    l1 = full["lines"][0]
    admin.put(f"/api/documents/{full['id']}/full", json={"allocations": [
        {"line_id": l1["id"], "project_id": project["id"], "amount_gross": 1}]})
    r = admin.post(f"/api/documents/{full['id']}/confirm")
    assert r.status_code == 422 and "súčet" in r.json()["detail"].lower()


def test_split_even_rounding(admin):
    r = admin.post("/api/documents/split-even", json={"total": 10, "n": 3}).json()
    assert r["parts"] == [3.33, 3.33, 3.34]


def test_bulk_actions(admin, project):
    full = _doc_with_lines(admin)
    r = admin.post("/api/data/documents/actions/set_project", json={"ids": [full["id"]],
                                                                   "payload": {"project_id": project["id"]}})
    assert r.json()["ok"] == 1
    r = admin.post("/api/data/documents/actions/confirm", json={"ids": [full["id"]]})
    assert r.json()["ok"] == 1
    r = admin.post("/api/data/documents/actions/mark_physical", json={"ids": [full["id"]]})
    assert admin.get(f"/api/data/documents/{full['id']}").json()["physical_original"] is True


def test_inbox_qr_ekasa_duplicate_and_physical(admin, project, monkeypatch):
    from app.services import ekasa
    calls = []

    def fake_fetch(rid, client=None):
        calls.append(rid)
        return EKASA_RECEIPT
    monkeypatch.setattr(ekasa, "fetch_receipt", fake_fetch)
    img = qr_png(RID)
    # photo from a worker – file name carries the project
    r = admin.post("/api/inbox/upload", data={"kind": "auto"},
                   files=[("files", ("sikorky_blocek.png", img, "image/png"))]).json()
    res = r["results"][0]
    assert res["status"] == "processed" and res["source"] == "ekasa", r
    doc = admin.get(f"/api/documents/{res['document_id']}/full").json()
    assert doc["ekasa_id"] == RID and doc["partner_name"] == "OBI Bratislava"
    assert doc["total_gross"] == 24.6 and doc["total_net"] == 20.0 and len(doc["lines"]) == 2
    assert doc["allocations"][0]["project_name"] == "Sikorky"
    assert doc["physical_original"] is False
    # same file again -> same hash -> not processed again
    r = admin.post("/api/inbox/upload", files=[("files", ("x.png", img, "image/png"))]).json()
    assert r["stored"][0]["new"] is False
    # physical scan (different image, same QR) -> duplicate detected, original marked physical
    img2 = qr_png(RID)[:-0] + b""
    import cv2 as _cv
    arr = _cv.imdecode(np.frombuffer(qr_png(RID), np.uint8), _cv.IMREAD_GRAYSCALE)
    arr = _cv.copyMakeBorder(arr, 10, 10, 10, 10, _cv.BORDER_CONSTANT, value=255)
    img2 = _cv.imencode(".png", arr)[1].tobytes()
    r = admin.post("/api/inbox/upload", data={"physical": "true"},
                   files=[("files", ("sken.png", img2, "image/png"))]).json()
    assert r["results"][0]["status"] == "duplicate"
    doc = admin.get(f"/api/documents/{res['document_id']}/full").json()
    assert doc["physical_original"] is True
    assert len(doc["files"]) == 2
    assert admin.get("/api/data/documents").json()["total"] == 1
    assert len(calls) == 1  # duplicate detected before calling eKasa
    # quick check
    q = admin.post("/api/receipts/quick-check", data={"ekasa_id": RID}).json()
    assert q["found"] is True and q["document_id"] == res["document_id"]


def test_inbox_without_extraction_goes_to_review(admin, monkeypatch):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (200, 300), "white").save(buf, format="JPEG")
    r = admin.post("/api/inbox/upload", data={"kind": "receipt"},
                   files=[("files", ("blocek.jpg", buf.getvalue(), "image/jpeg"))]).json()
    res = r["results"][0]
    assert res["status"] == "processed"
    doc = admin.get(f"/api/documents/{res['document_id']}/full").json()
    assert doc["status"] == "review" and doc["extraction_source"] == "manual"
    assert any("ručne" in w for w in doc["warnings"])


def test_fuel_goes_to_overhead(admin, monkeypatch):
    from app.services import ekasa
    rec = dict(EKASA_RECEIPT, organization={"name": "SLOVNAFT, a.s.", "ico": "31322832"}, ico="31322832",
               items=[{"name": "Diesel", "quantity": 40, "vatRate": 23, "price": 24.6}])
    monkeypatch.setattr(ekasa, "fetch_receipt", lambda rid, client=None: rec)
    r = admin.post("/api/inbox/upload", files=[("files", ("tank.png", qr_png(RID), "image/png"))]).json()
    doc = admin.get(f"/api/documents/{r['results'][0]['document_id']}/full").json()
    assert doc["allocations"][0]["project_name"] == "Réžia"


def test_issued_invoice_revenue_and_profitability(admin, project):
    create(admin, "invoice_series", {"prefix": "P2026", "name": "Peter", "project_id": project["id"]})
    d = admin.post("/api/documents/manual", json={"doc_type": "invoice_out"}).json()
    admin.put(f"/api/documents/{d['id']}/full", json={"header": {
        "number": "P2026001", "issue_date": "2026-11-03", "total_net": 1000, "total_vat": 230, "total_gross": 1230}})
    admin.post("/api/data/documents/actions/set_project", json={"ids": [d["id"]], "payload": {"project_id": project["id"]}})
    assert admin.post(f"/api/documents/{d['id']}/confirm").status_code == 200
    w = create(admin, "workers", {"name": "Jano"})
    create(admin, "worker_rates", {"worker_id": w["id"], "cost_rate": 15, "billing_rate": 25})
    create(admin, "timesheets", {"worker_id": w["id"], "project_id": project["id"], "date": "2026-11-02", "hours": 20})
    prof = admin.get("/api/reports/profitability").json()
    row = next(r for r in prof["rows"] if r["project_name"] == "Sikorky")
    assert row["revenue"] == 1000 and row["cost"] == 300 and row["profit"] == 700
    assert row["wip"] == 500  # 20 h × 25 unbilled
    assert prof["totals"]["company_profit"] == 700
