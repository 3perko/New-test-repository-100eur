"""Master data, rates, timesheets, trips, list engine, roles."""
import json

from tests.conftest import create, make_client


def _base(admin):
    p = create(admin, "projects", {"name": "Sikorky", "aliases": "Sikorky RD", "default_km_one_way": 25,
                                   "billing_type": "hourly", "cost_budget": 10000})
    w = create(admin, "workers", {"name": "Diesel", "relation_type": "contractor"})
    create(admin, "worker_rates", {"worker_id": w["id"], "cost_rate": 12, "billing_rate": 22})
    create(admin, "worker_rates", {"worker_id": w["id"], "project_id": p["id"], "cost_rate": 10})
    return p, w


def test_login_and_csrf(setup):
    c = make_client(company_id=setup["c1"])
    assert c.get("/api/auth/me").json()["role"] == "admin"
    del c.headers["X-Requested-With"]
    assert c.post("/api/data/projects", json={"name": "X"}).status_code == 403


def test_overhead_project_created_with_company(admin):
    comp = create(admin, "companies", {"name": "Gama s.r.o.", "vat_payer": True})
    admin.headers["X-Company-Id"] = str(comp["id"])
    rows = admin.get("/api/data/projects").json()["rows"]
    assert [r["name"] for r in rows] == ["Réžia"]


def test_rate_lookup_and_hours(admin):
    p, w = _base(admin)
    t = create(admin, "timesheets", {"worker_id": w["id"], "project_id": p["id"], "date": "2026-11-02",
                                     "time_from": "07:00", "time_to": "15:30", "description": "murovanie"})
    assert t["hours"] == 8.5
    assert t["cost_rate"] == 10.0  # worker + project
    assert t["billing_rate"] == 22.0  # falls back to worker default
    assert t["cost_amount"] == 85.0 and t["billable_amount"] == 187.0
    # over midnight + rounding to 0.25
    t2 = create(admin, "timesheets", {"worker_id": w["id"], "project_id": p["id"], "date": "2026-11-03",
                                      "time_from": "22:00", "time_to": "01:10"})
    assert t2["hours"] == 3.25
    # explicit hours win
    t3 = create(admin, "timesheets", {"worker_id": w["id"], "project_id": p["id"], "date": "2026-11-03", "hours": 2})
    assert t3["hours"] == 2.0 and t3["cost_amount"] == 20.0


def test_rate_snapshot_and_recalc(admin):
    p, w = _base(admin)
    t = create(admin, "timesheets", {"worker_id": w["id"], "project_id": p["id"], "date": "2026-11-02", "hours": 10})
    rates = admin.get("/api/data/worker_rates").json()["rows"]
    proj_rate = next(r for r in rates if r["project_id"])
    admin.patch(f"/api/data/worker_rates/{proj_rate['id']}", json={"cost_rate": 15})
    # description edit does not change the snapshot
    t = admin.patch(f"/api/data/timesheets/{t['id']}", json={"description": "x"}).json()
    assert t["cost_amount"] == 100.0
    r = admin.post("/api/data/timesheets/actions/recalc", json={"ids": [t["id"]]})
    assert r.status_code == 200, r.text
    t = admin.get(f"/api/data/timesheets/{t['id']}").json()
    assert t["cost_amount"] == 150.0
    hist = admin.get(f"/api/history/timesheets/{t['id']}").json()
    assert any(h["action"] == "recalculate" for h in hist)


def test_trip_km_default(admin):
    p, w = _base(admin)
    v = create(admin, "vehicles", {"name": "Transit", "plate": "BA123AA", "initial_rate_per_km": "0,35"})
    t = create(admin, "trips", {"vehicle_id": v["id"], "project_id": p["id"], "date": "2026-11-02",
                                "driver_id": w["id"], "crew_ids": [w["id"]]})
    assert t["km_effective"] == 55.0 and t["km_computed"] is True
    assert t["cost_amount"] == 19.25
    assert t["crew_ids"] == [w["id"]]
    t = admin.patch(f"/api/data/trips/{t['id']}", json={"km": 60}).json()
    assert t["km_effective"] == 60.0 and t["cost_amount"] == 21.0


def test_project_must_belong_to_active_company(admin, setup):
    p, w = _base(admin)
    admin.headers["X-Company-Id"] = str(setup["c2"])
    r = admin.post("/api/data/timesheets", json={"worker_id": w["id"], "project_id": p["id"], "date": "2026-11-02",
                                                 "hours": 1})
    assert r.status_code == 422


def test_inactive_hidden_and_never_deleted(admin):
    p, _ = _base(admin)
    assert admin.delete(f"/api/data/projects/{p['id']}").status_code == 200
    names = [r["name"] for r in admin.get("/api/data/projects").json()["rows"]]
    assert "Sikorky" not in names
    names = [r["name"] for r in admin.get("/api/data/projects", params={"include_inactive": True}).json()["rows"]]
    assert "Sikorky" in names
    opts = [o["label"] for o in admin.get("/api/options/projects").json()]
    assert "Sikorky" not in opts


def test_list_engine_filters_totals_groups_export(admin):
    p, w = _base(admin)
    w2 = create(admin, "workers", {"name": "Peter"})
    create(admin, "worker_rates", {"worker_id": w2["id"], "cost_rate": 20, "billing_rate": 30})
    for d, worker, h in (("2026-10-30", w, 8), ("2026-11-02", w, 6), ("2026-11-02", w2, 4)):
        create(admin, "timesheets", {"worker_id": worker["id"], "project_id": p["id"], "date": d, "hours": h})
    flt = json.dumps([{"field": "date", "op": "between", "value": ["2026-11-01", "2026-11-30"]}])
    res = admin.get("/api/data/timesheets", params={"filter": flt, "sort": "hours:desc",
                                                    "columns": "date,worker_id,hours,cost_amount"}).json()
    assert res["total"] == 2 and res["rows"][0]["hours"] == 6
    assert res["totals"]["hours"] == 10 and res["totals"]["cost_amount"] == 140
    assert res["rows"][0]["worker_id__label"] == "Diesel"
    g = admin.get("/api/data/timesheets", params={"group_by": "worker_id"}).json()["groups"]
    assert {x["label"]: x["totals"]["hours"] for x in g} == {"Diesel": 14, "Peter": 4}
    res = admin.get("/api/data/timesheets", params={"q": "Pet"}).json()
    assert res["total"] == 1
    x = admin.get("/api/data/timesheets/export", params={"format": "xlsx", "filter": flt})
    assert x.status_code == 200 and x.content[:2] == b"PK"
    c = admin.get("/api/data/timesheets/export", params={"format": "csv"})
    assert "Pracovník" in c.content.decode("utf-8-sig")


def test_saved_views(admin):
    v = admin.post("/api/views", json={"entity": "timesheets", "name": "Sikorky", "config": {"columns": ["date"]},
                                       "is_default": True}).json()
    admin.put("/api/views/last/timesheets", json={"config": {"sort": "date:asc"}})
    res = admin.get("/api/views", params={"entity": "timesheets"}).json()
    assert res["views"][0]["id"] == v["id"] and res["views"][0]["is_default"]
    assert res["last"]["config"]["sort"] == "date:asc"


def test_worker_role_sees_only_own_and_no_billing_rates(admin, setup):
    p, w = _base(admin)
    other = create(admin, "workers", {"name": "Iný"})
    create(admin, "users", {"name": "Diesel", "email": "diesel@test.sk", "role": "worker", "worker_id": w["id"],
                            "password": "heslo1234", "company_ids": [setup["c1"]]})
    create(admin, "timesheets", {"worker_id": other["id"], "project_id": p["id"], "date": "2026-11-02", "hours": 3})
    wc = make_client("diesel@test.sk", "heslo1234", setup["c1"])
    # worker cannot pick someone else
    t = create(wc, "timesheets", {"worker_id": other["id"], "project_id": p["id"], "date": "2026-11-02", "hours": 5})
    assert t["worker_id"] == w["id"]
    assert "billing_rate" not in t and "billable_amount" not in t
    rows = wc.get("/api/data/timesheets").json()["rows"]
    assert len(rows) == 1
    keys = {f["key"] for f in wc.get("/api/meta/timesheets/fields").json()["fields"]}
    assert "billing_rate" not in keys and "billable" not in keys
    prow = wc.get("/api/data/projects").json()["rows"][0]
    assert "cost_budget" not in prow and "labor_cost" not in prow
    assert wc.get("/api/data/documents").status_code == 403
    assert wc.get("/api/reports/profitability").status_code == 403
    assert wc.get("/api/options/projects").status_code == 200
    ws = wc.get("/api/worker-statement", params={"date_from": "2026-11-01", "date_to": "2026-11-30"}).json()
    assert ws["total_hours"] == 5 and ws["total_amount"] == 50
