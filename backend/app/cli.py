"""Command line helpers.

  python -m app.cli create-admin --email admin@firma.sk --password heslo123 [--name "Meno"]
  python -m app.cli seed-demo        # optional demo data for trying the app (two companies, projects, hours…)
  python -m app.cli run-inbox        # process inboxes of all companies now
"""
import argparse
import sys
from datetime import date, time, timedelta
from decimal import Decimal

import app.registry.entities  # noqa: F401
from app.db import SessionLocal
from app.models import (
    BankAccount, Company, Customer, InvoiceSeries, Project, RecurringInvoiceRule, TimesheetEntry, Trip, User, Vehicle,
    VehicleInsurance, VehicleRate, VehicleService, VehicleVignette, Worker, WorkerRate,
)
from app.security import hash_password
from app.services import calc


def create_admin(email: str, password: str, name: str) -> None:
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == email.lower()).first()
        if u:
            u.password_hash = hash_password(password)
            u.role, u.active = "admin", True
            print(f"Používateľ {email} existoval – heslo a rola admin boli nastavené.")
        else:
            db.add(User(email=email.lower(), name=name, role="admin", password_hash=hash_password(password)))
            print(f"Vytvorený admin {email}.")
        db.commit()


def seed_demo() -> None:
    with SessionLocal() as db:
        if db.query(Company).filter(Company.name == "Demo Stavby s.r.o.").first():
            print("Demo dáta už existujú.")
            return
        c1 = Company(name="Demo Stavby s.r.o.", ico="12345678", ic_dph="SK2023456789", vat_payer=True,
                     address="Hlavná 1, 811 01 Bratislava")
        c2 = Company(name="Demo Servis s.r.o.", ico="87654321", vat_payer=False, address="Dlhá 5, 900 01 Modra")
        db.add_all([c1, c2])
        db.flush()
        for c in (c1, c2):
            db.add(Project(company_id=c.id, name="Réžia", is_overhead=True, aliases="rezia, réžia"))
        db.add(BankAccount(company_id=c1.id, iban="SK3112000000198742637541", bank_name="Demo banka"))
        cust = Customer(company_id=c1.id, name="Ján Novák", ico=None, address="Sikorky 12, Bratislava")
        cust2 = Customer(company_id=c1.id, name="Bytové družstvo Lúky", ico="11223344")
        db.add_all([cust, cust2])
        db.flush()
        sik = Project(company_id=c1.id, name="Sikorky", aliases="Sikorky RD, sikorky", customer_id=cust.id,
                      cost_budget=Decimal(25000), billing_type="hourly", default_km_one_way=Decimal(25),
                      status="in_progress", bill_transport=True, transport_rate_per_km=Decimal("0.45"))
        luky = Project(company_id=c1.id, name="Lúky – strecha", aliases="Luky, strecha", customer_id=cust2.id,
                       cost_budget=Decimal(18000), contract_price=Decimal(24000), billing_type="fixed",
                       default_km_one_way=Decimal(12), status="in_progress")
        modra = Project(company_id=c2.id, name="Modra – kúpeľňa", default_km_one_way=Decimal(8), status="in_progress")
        db.add_all([sik, luky, modra])
        db.add(InvoiceSeries(company_id=c1.id, prefix="2026", name="Firma – hlavný rad"))
        db.add(InvoiceSeries(company_id=c1.id, prefix="P2026", name="Peter – vlastný rad"))
        db.add(RecurringInvoiceRule(company_id=c1.id, supplier_name="Orange Slovensko", supplier_ico="35697270"))
        db.add(RecurringInvoiceRule(company_id=c1.id, supplier_name="Nájom dielne", match_text="nájom"))
        w1 = Worker(name="Peter Kováč", aliases="Peťo", relation_type="employee")
        w2 = Worker(name="Diesel", aliases="Dízel", relation_type="contractor", ico="44556677")
        w3 = Worker(name="Marek Horváth", relation_type="contractor")
        db.add_all([w1, w2, w3])
        db.flush()
        w1.companies = [c1, c2]
        w2.companies = [c1]
        w3.companies = [c1]
        db.add_all([
            WorkerRate(worker_id=w1.id, cost_rate=Decimal(14), billing_rate=Decimal(25)),
            WorkerRate(worker_id=w2.id, cost_rate=Decimal(12), billing_rate=Decimal(22)),
            WorkerRate(worker_id=w2.id, project_id=sik.id, company_id=c1.id, cost_rate=Decimal(11)),
            WorkerRate(worker_id=w3.id, cost_rate=Decimal(16), billing_rate=Decimal(28)),
            WorkerRate(worker_id=w1.id, company_id=c2.id, cost_rate=Decimal(15), billing_rate=Decimal(24)),
        ])
        v1 = Vehicle(company_id=c1.id, name="Transit", manufacturer="Ford", model="Transit", plate="BA123XY",
                     stk_valid_to=date.today() + timedelta(days=20), ek_valid_to=date.today() + timedelta(days=200),
                     odometer=184500)
        v2 = Vehicle(company_id=c1.id, name="Octavia", manufacturer="Škoda", model="Octavia Combi", plate="BA987ZZ",
                     stk_valid_to=date.today() + timedelta(days=400), ek_valid_to=date.today() + timedelta(days=400),
                     odometer=95000)
        db.add_all([v1, v2])
        db.flush()
        db.add_all([VehicleRate(vehicle_id=v1.id, rate_per_km=Decimal("0.35")),
                    VehicleRate(vehicle_id=v2.id, rate_per_km=Decimal("0.25")),
                    VehicleInsurance(vehicle_id=v1.id, insurance_type="pzp", insurer="Allianz", contract_no="PZP-001",
                                     premium=Decimal(420), payment_period="annual",
                                     valid_from=date.today() - timedelta(days=300),
                                     valid_to=date.today() + timedelta(days=65)),
                    VehicleVignette(vehicle_id=v1.id, country="SK", vignette_type="annual", plate="BA123XY",
                                    valid_from=date(date.today().year, 1, 1), valid_to=date(date.today().year, 12, 31),
                                    price=Decimal(90)),
                    VehicleService(vehicle_id=v1.id, date=date.today() - timedelta(days=200), odometer=170000,
                                   service_type="regular", description="Výmena oleja", supplier="Autoservis",
                                   price=Decimal(180), next_service_km=185000)])
        today = date.today()
        for i in range(10):
            d = today - timedelta(days=i * 2)
            for w, p, t1, t2 in ((w1, sik, time(7, 0), time(15, 30)), (w2, sik, time(7, 30), time(16, 0)),
                                 (w3, luky, time(8, 0), time(14, 0))):
                e = TimesheetEntry(company_id=c1.id, worker_id=w.id, project_id=p.id, date=d, time_from=t1,
                                   time_to=t2, description="Murárske práce" if p is sik else "Pokrývačské práce",
                                   material_bought=(i == 0 and w is w1), billable=True, source="web")
                db.add(e)
                db.flush()
                calc.apply_timesheet(db, e, refresh_rates=True, hours_explicit=False)
            tr = Trip(company_id=c1.id, vehicle_id=v1.id, project_id=sik.id, date=d, driver_id=w1.id, source="web")
            db.add(tr)
            db.flush()
            tr.crew = [w2]
            calc.apply_trip(db, tr, refresh_rates=True)
        db.commit()
        print("Demo dáta vytvorené: firmy Demo Stavby s.r.o. a Demo Servis s.r.o.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ca = sub.add_parser("create-admin")
    ca.add_argument("--email", required=True)
    ca.add_argument("--password", required=True)
    ca.add_argument("--name", default="Administrátor")
    sub.add_parser("seed-demo")
    sub.add_parser("run-inbox")
    args = parser.parse_args(argv)
    if args.cmd == "create-admin":
        if len(args.password) < 8:
            print("Heslo musí mať aspoň 8 znakov.")
            sys.exit(1)
        create_admin(args.email, args.password, args.name)
    elif args.cmd == "seed-demo":
        seed_demo()
    elif args.cmd == "run-inbox":
        from app.services import jobs
        with SessionLocal() as db:
            for r in jobs.run_all(db):
                print(r)


if __name__ == "__main__":
    main()
