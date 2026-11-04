"""Entity definitions for the field registry (master data, work, fleet, documents, bank, system)."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, func, literal, or_, select
from sqlalchemy.orm import aliased

from app.models import (
    Allocation, AuditLog, BankAccount, BankStatement, BankTransaction, BillingStatement, Company, Customer, Document,
    DocumentLine, InvoiceSeries, Project, RecurringInvoiceRule, SourceFile, TimesheetEntry, TransactionRule, Trip,
    User, Vehicle, VehicleCheck, VehicleInsurance, VehicleRate, VehicleService, VehicleVignette, Worker, WorkerRate,
    trip_crew, user_company, worker_company,
)
from app.registry.base import ADMIN, ALL_ROLES, Action, Entity, F, register, string_agg_names
from app.security import hash_password
from app.services import calc

# ----------------------------------------------------------------------------- option lists (Slovak labels)
BILLING_TYPES = [("hourly", "Hodinovo – podľa výkazu"), ("fixed", "Pevná cena"), ("combined", "Kombinácia")]
PROJECT_STATUS = [("planned", "Pripravovaná"), ("in_progress", "Prebiehajúca"), ("finished", "Ukončená")]
RELATION_TYPES = [("employee", "Zamestnanec"), ("contractor", "Živnostník"), ("other", "Iné")]
ROLES = [("admin", "Admin / klient"), ("worker", "Pracovník")]
DOC_TYPES = [("receipt", "Bloček"), ("invoice_in", "Prijatá faktúra"), ("invoice_out", "Vystavená faktúra")]
DOC_STATUS = [("review", "Na kontrolu"), ("confirmed", "Potvrdený")]
PAYMENT_STATUS = [("unpaid", "Neuhradená"), ("partial", "Čiastočne"), ("paid", "Uhradená")]
EXTRACTION = [("ekasa", "eKasa"), ("claude", "Claude API"), ("pdf_text", "Text z PDF"), ("manual", "Ručne")]
PERIODICITY = [("monthly", "Mesačne"), ("quarterly", "Štvrťročne"), ("yearly", "Ročne")]
INSURANCE_TYPES = [("pzp", "PZP"), ("havarijne", "Havarijné")]
PAYMENT_PERIODS = [("annual", "Ročne"), ("semiannual", "Polročne"), ("quarterly", "Štvrťročne"), ("monthly", "Mesačne")]
VIGNETTE_TYPES = [("annual", "Ročná"), ("30d", "30-dňová"), ("10d", "10-dňová"), ("other", "Iná")]
SERVICE_TYPES = [("regular", "Pravidelný servis"), ("repair", "Oprava"), ("tires", "Pneumatiky"), ("other", "Iné")]
CHECK_SERVICES = [("vignette", "Diaľničná známka"), ("pzp", "PZP"), ("stk", "STK"), ("ek", "EK")]
CHECK_RESULTS = [("valid", "Platné"), ("invalid", "Neplatné"), ("unknown", "Nezistené"), ("error", "Chyba")]
TX_TYPES = [("card", "Platba kartou"), ("transfer", "Prevod"), ("fee", "Poplatok"), ("other", "Iné")]
TX_STATUS = [("unmatched", "Bez dokladu"), ("suggested", "Návrh"), ("matched", "Spárovaný"),
             ("no_document", "Nepotrebuje doklad")]
RULE_ACTIONS = [("no_document", "Nepotrebuje doklad"), ("suggest_project", "Návrh zákazky"),
                ("suggest_supplier", "Návrh dodávateľa")]
FILE_STATUS = [("new", "Nové"), ("processed", "Spracované"), ("duplicate", "Duplicita"), ("error", "Chyba"),
               ("skipped", "Preskočené")]
FILE_SOURCES = [("upload", "Nahraté"), ("drive", "Google Drive"), ("email", "E-mail"), ("bank_inbox", "Bankový inbox"),
                ("whatsapp", "WhatsApp")]
KIND_HINTS = [("auto", "Automaticky"), ("receipt", "Bloček"), ("invoice_in", "Prijatá faktúra"),
              ("invoice_out", "Vystavená faktúra"), ("bank", "Bankový výpis")]
BILLING_STATUS = [("draft", "Návrh"), ("closed", "Uzavretý")]
COUNTRIES = [("SK", "Slovensko"), ("CZ", "Česko"), ("AT", "Rakúsko"), ("HU", "Maďarsko"), ("PL", "Poľsko"),
             ("SI", "Slovinsko"), ("CH", "Švajčiarsko"), ("other", "Iná")]


def _active_field():
    return F("active", "Aktívny", "bool", default_visible=False)


def _note():
    return F("note", "Poznámka", "longtext", default_visible=False)


def _created():
    return F("created_at", "Vytvorené", "datetime", editable=False, default_visible=False)


# ============================================================================= Companies
def _company_scope(ctx):
    from app.deps import accessible_company_ids
    return Company.id.in_(accessible_company_ids(ctx.db, ctx.user))


def _company_after_save(ctx, obj: Company, data, is_new):
    if is_new:
        ctx.db.add(Project(company_id=obj.id, name="Réžia", is_overhead=True, status="in_progress",
                           aliases="rezia, réžia, overhead"))
        if ctx.user.companies:
            ctx.user.companies.append(obj)


register(Entity(
    name="companies", label="Firmy", model=Company, company_scoped=False, base_filter=_company_scope,
    has_active=True, deletable=False, default_sort="name:asc",
    after_save=_company_after_save,
    fields=[
        F("name", "Názov", required=True),
        F("ico", "IČO"), F("dic", "DIČ", default_visible=False), F("ic_dph", "IČ DPH"),
        F("vat_payer", "Platiteľ DPH", "bool"),
        F("address", "Adresa", "longtext", default_visible=False),
        F("invoice_address", "Adresa na faktúry", "longtext", default_visible=False),
        F("drive_inbox_folder_id", "Drive – ID priečinka inbox", default_visible=False,
          help="ID priečinka „na spracovanie“ na Google Drive (časť URL za /folders/)."),
        F("drive_processed_folder_id", "Drive – ID priečinka spracované", default_visible=False),
        F("drive_bank_inbox_folder_id", "Drive – ID bankového inboxu", default_visible=False),
        F("email_tag_invoices", "E-mail tag pre faktúry", default_visible=False,
          help="Časť za + v plus-adrese, napr. „firma1-faktury“ pre meno+firma1-faktury@gmail.com."),
        F("email_tag_bank", "E-mail tag pre výpisy", default_visible=False),
        _note(), _active_field(),
    ],
))

register(Entity(
    name="bank_accounts", label="Bankové účty", model=BankAccount, has_active=True, deletable=False,
    default_sort="iban:asc", title_field="iban",
    fields=[F("iban", "IBAN", required=True), F("bank_name", "Banka"), F("currency", "Mena"), _note(), _active_field()],
))

# ============================================================================= Customers, projects
register(Entity(
    name="customers", label="Odberatelia", model=Customer, has_active=True, deletable=False, default_sort="name:asc",
    fields=[F("name", "Názov", required=True), F("ico", "IČO"), F("dic", "DIČ", default_visible=False),
            F("ic_dph", "IČ DPH"), F("address", "Adresa", "longtext", default_visible=False), F("contact", "Kontakt"),
            F("email", "E-mail"), F("phone", "Telefón", default_visible=False), _active_field()],
))

PCust = aliased(Customer)


def _project_costs_expr(kind: str):
    def expr():
        if kind == "labor":
            return (select(func.coalesce(func.sum(TimesheetEntry.cost_amount), 0))
                    .where(TimesheetEntry.project_id == Project.id).correlate(Project).scalar_subquery())
        if kind == "transport":
            return (select(func.coalesce(func.sum(Trip.cost_amount), 0))
                    .where(Trip.project_id == Project.id).correlate(Project).scalar_subquery())
        if kind == "hours":
            return (select(func.coalesce(func.sum(TimesheetEntry.hours), 0))
                    .where(TimesheetEntry.project_id == Project.id).correlate(Project).scalar_subquery())
        # material: confirmed cost allocations (net for VAT payers)
        amount = case((Company.vat_payer.is_(True), Allocation.amount_net), else_=Allocation.amount_gross)
        return (select(func.coalesce(func.sum(amount), 0))
                .select_from(Allocation.__table__.join(Document, Document.id == Allocation.document_id)
                             .join(Company, Company.id == Allocation.company_id))
                .where(Allocation.project_id == Project.id, Allocation.direction == "cost",
                       Document.status == "confirmed").correlate(Project).scalar_subquery())
    return expr


def _project_before_save(ctx, obj: Project, data, is_new):
    if obj.customer_id:
        c = ctx.db.get(Customer, obj.customer_id)
        if not c or c.company_id != ctx.company_id:
            raise HTTPException(422, "Odberateľ nepatrí aktívnej firme.")
    if not is_new and obj.is_overhead and obj.active is False:
        raise HTTPException(422, "Réžiu nie je možné deaktivovať.")


register(Entity(
    name="projects", label="Zákazky", model=Project, has_active=True, deletable=False, default_sort="name:asc",
    read_roles=ALL_ROLES, before_save=_project_before_save,
    joins=lambda: [(PCust, PCust.id == Project.customer_id)],
    fields=[
        F("name", "Názov", required=True),
        F("aliases", "Aliasy", help="Ako zákazku píšu ľudia, oddelené čiarkou (napr. Sikorky, Sikorky RD)."),
        F("customer_id", "Odberateľ", "ref", ref="customers", label_expr=lambda: PCust.name, roles=ADMIN),
        F("status", "Stav", "select", options=PROJECT_STATUS),
        F("billing_type", "Typ fakturácie", "select", options=BILLING_TYPES, roles=ADMIN),
        F("cost_budget", "Rozpočet nákladov", "money", roles=ADMIN, aggregate=True),
        F("contract_price", "Zmluvná cena", "money", roles=ADMIN),
        F("default_km_one_way", "Vzdialenosť jedným smerom (km)", "number", aggregate=False),
        F("material_markup_pct", "Prirážka na materiál (%)", "number", roles=ADMIN, default_visible=False,
          aggregate=False, help="Prázdne = default z nastavení."),
        F("bill_transport", "Fakturovať dopravu", "bool", roles=ADMIN, default_visible=False),
        F("transport_rate_per_km", "Fakturačná sadzba dopravy (€/km)", "money", roles=ADMIN, default_visible=False,
          aggregate=False),
        F("is_overhead", "Réžia", "bool", editable=False, default_visible=False),
        F("labor_cost", "Náklad práca", "money", expr=_project_costs_expr("labor"), computed=True, roles=ADMIN,
          default_visible=False),
        F("material_cost", "Náklad materiál", "money", expr=_project_costs_expr("material"), computed=True,
          roles=ADMIN, default_visible=False),
        F("transport_cost", "Náklad doprava", "money", expr=_project_costs_expr("transport"), computed=True,
          roles=ADMIN, default_visible=False),
        F("hours_total", "Hodiny spolu", "hours", expr=_project_costs_expr("hours"), computed=True, roles=ADMIN,
          default_visible=False),
        _note(), _active_field(), _created(),
    ],
))

ISProj = aliased(Project)
register(Entity(
    name="invoice_series", label="Číselné rady", model=InvoiceSeries, has_active=True, deletable=False,
    default_sort="prefix:asc", title_field="prefix",
    joins=lambda: [(ISProj, ISProj.id == InvoiceSeries.project_id)],
    fields=[F("prefix", "Predpona čísla faktúry", required=True,
              help="Číslo vystavenej faktúry začínajúce touto predponou patrí do tohto radu."),
            F("name", "Časť firmy / osoba", required=True),
            F("project_id", "Zákazka (voliteľne)", "ref", ref="projects", label_expr=lambda: ISProj.name),
            _note(), _active_field()],
))

# ============================================================================= Workers and rates
WC = aliased(Company)


def _worker_companies_save(ctx, obj: Worker, ids):
    before = [c.id for c in obj.companies]
    obj.companies = [ctx.db.get(Company, i) for i in ids if ctx.db.get(Company, i)]
    return before


register(Entity(
    name="workers", label="Pracovníci", model=Worker, company_scoped=False, has_active=True, deletable=False,
    default_sort="name:asc", read_roles=ADMIN,
    multiref_save={"company_ids": _worker_companies_save},
    fields=[
        F("name", "Meno", required=True), F("aliases", "Aliasy"),
        F("relation_type", "Typ vzťahu", "select", options=RELATION_TYPES),
        F("ico", "IČO (živnostník)", default_visible=False), F("email", "E-mail", default_visible=False),
        F("phone", "Telefón", default_visible=False),
        F("company_ids", "Firmy", "multiref", ref="companies", attr="companies", sortable=False,
          expr=lambda: string_agg_names(WC.name, worker_company, worker_company.c.worker_id, WC,
                                        worker_company.c.company_id, Worker.id),
          label_expr=lambda: string_agg_names(WC.name, worker_company, worker_company.c.worker_id, WC,
                                              worker_company.c.company_id, Worker.id)),
        _note(), _active_field(),
    ],
))

WRWorker, WRProj, WRComp = aliased(Worker), aliased(Project), aliased(Company)


def _rate_before_save(ctx, obj: WorkerRate, data, is_new):
    if obj.project_id:
        p = ctx.db.get(Project, obj.project_id)
        obj.company_id = p.company_id if p else obj.company_id
    if obj.valid_from and obj.valid_to and obj.valid_to < obj.valid_from:
        raise HTTPException(422, "Platnosť do je skôr ako platnosť od.")
    if obj.cost_rate is None and obj.billing_rate is None:
        raise HTTPException(422, "Zadajte aspoň jednu sadzbu.")


register(Entity(
    name="worker_rates", label="Sadzby pracovníkov", model=WorkerRate, company_scoped=False,
    base_filter=lambda ctx: or_(WorkerRate.company_id.is_(None), WorkerRate.company_id == ctx.company_id),
    default_sort="worker_id:asc", before_save=_rate_before_save, title_field="id",
    joins=lambda: [(WRWorker, WRWorker.id == WorkerRate.worker_id), (WRProj, WRProj.id == WorkerRate.project_id),
                   (WRComp, WRComp.id == WorkerRate.company_id)],
    fields=[
        F("worker_id", "Pracovník", "ref", ref="workers", label_expr=lambda: WRWorker.name, required=True),
        F("company_id", "Firma (voliteľne)", "ref", ref="companies", label_expr=lambda: WRComp.name,
          help="Prázdne = platí pre všetky firmy."),
        F("project_id", "Zákazka (voliteľne)", "ref", ref="projects", label_expr=lambda: WRProj.name,
          help="Sadzba len pre túto zákazku."),
        F("cost_rate", "Nákladová sadzba (€/h)", "money", aggregate=False),
        F("billing_rate", "Fakturačná sadzba (€/h)", "money", aggregate=False),
        F("valid_from", "Platí od", "date"), F("valid_to", "Platí do", "date"), _note(),
    ],
))


# ============================================================================= Users
UC = aliased(Company)
UW = aliased(Worker)


def _user_before_save(ctx, obj: User, data, is_new):
    pwd = data.get("password")
    if pwd:
        if len(pwd) < 8:
            raise HTTPException(422, "Heslo musí mať aspoň 8 znakov.")
        obj.password_hash = hash_password(pwd)
    elif is_new:
        raise HTTPException(422, "Zadajte heslo.")
    if obj.email:
        obj.email = obj.email.lower()
    if obj.role == "worker" and not obj.worker_id:
        raise HTTPException(422, "Používateľ s rolou pracovník musí byť prepojený na pracovníka.")
    if obj.id == ctx.user.id and (obj.role != "admin" or not obj.active):
        raise HTTPException(422, "Nemôžete si odobrať rolu admin ani sa deaktivovať.")


def _user_companies_save(ctx, obj: User, ids):
    before = [c.id for c in obj.companies]
    obj.companies = [ctx.db.get(Company, i) for i in ids if ctx.db.get(Company, i)]
    return before


register(Entity(
    name="users", label="Používatelia", model=User, company_scoped=False, has_active=True, deletable=False,
    default_sort="name:asc", before_save=_user_before_save, multiref_save={"company_ids": _user_companies_save},
    joins=lambda: [(UW, UW.id == User.worker_id)],
    fields=[
        F("name", "Meno", required=True), F("email", "E-mail (prihlasovacie meno)", required=True),
        F("role", "Rola", "select", options=ROLES, required=True),
        F("worker_id", "Prepojený pracovník", "ref", ref="workers", label_expr=lambda: UW.name),
        F("company_ids", "Prístup k firmám", "multiref", ref="companies", attr="companies", sortable=False,
          help="Admin bez vybraných firiem má prístup ku všetkým.",
          expr=lambda: string_agg_names(UC.name, user_company, user_company.c.user_id, UC, user_company.c.company_id,
                                        User.id),
          label_expr=lambda: string_agg_names(UC.name, user_company, user_company.c.user_id, UC,
                                              user_company.c.company_id, User.id)),
        F("password", "Nové heslo", "text", expr=lambda: literal(None, String), sortable=False, filterable=False,
          default_visible=False, virtual=True, help="Vyplňte len pri zmene hesla (min. 8 znakov)."),
        _active_field(),
    ],
))

# ============================================================================= Recurring invoices
register(Entity(
    name="recurring_rules", label="Opakujúce sa faktúry", model=RecurringInvoiceRule, has_active=True,
    deletable=False, default_sort="supplier_name:asc", title_field="supplier_name",
    fields=[
        F("supplier_name", "Dodávateľ", required=True), F("supplier_ico", "IČO dodávateľa"),
        F("match_text", "Hľadať aj podľa textu", default_visible=False,
          help="Alternatívny text v názve dodávateľa (ak IČO nie je známe)."),
        F("periodicity", "Periodicita", "select", options=PERIODICITY),
        F("last_occurrence", "Posledný výskyt", "date", computed=True, editable=False,
          expr=lambda: (select(func.max(Document.issue_date)).where(
              Document.company_id == RecurringInvoiceRule.company_id, Document.doc_type == "invoice_in",
              or_(Document.recurring_rule_id == RecurringInvoiceRule.id,
                  and_(RecurringInvoiceRule.supplier_ico.is_not(None),
                       Document.partner_ico == RecurringInvoiceRule.supplier_ico)))
              .correlate(RecurringInvoiceRule).scalar_subquery())),
        _note(), _active_field(),
    ],
))

# ============================================================================= Timesheets
TWorker, TProj, TCust = aliased(Worker), aliased(Project), aliased(Customer)


def _ts_row_filter(ctx):
    if ctx.role == "worker":
        return TimesheetEntry.worker_id == (ctx.user.worker_id or -1)
    return None


def _check_not_billed(ctx, statement_id):
    if statement_id:
        st = ctx.db.get(BillingStatement, statement_id)
        if st and st.status == "closed":
            raise HTTPException(409, "Záznam je vo vyfakturovanom (uzavretom) podklade a nedá sa meniť.")


def _check_project(ctx, project_id):
    if project_id:
        p = ctx.db.get(Project, project_id)
        if not p or p.company_id != ctx.company_id:
            raise HTTPException(422, "Zákazka nepatrí aktívnej firme.")


def _ts_before_save(ctx, obj: TimesheetEntry, data, is_new):
    if not is_new:
        _check_not_billed(ctx, obj.billing_statement_id)
    if ctx.role == "worker":
        obj.worker_id = ctx.user.worker_id
    if not obj.worker_id:
        raise HTTPException(422, "Zadajte pracovníka.")
    _check_project(ctx, obj.project_id)
    obj.company_id = ctx.company_id
    if is_new:
        obj.created_by = ctx.user.id
        obj.source = obj.source or "web"
    hours_explicit = data.get("hours") not in (None, "") and (is_new or "hours" in ctx.changed)
    refresh = is_new or bool({"worker_id", "project_id", "date"} & ctx.changed)
    if not is_new and not hours_explicit and not ({"time_from", "time_to"} & ctx.changed):
        hours_explicit = True  # keep stored hours
    calc.apply_timesheet(ctx.db, obj, refresh_rates=refresh, hours_explicit=hours_explicit)


def _ts_before_delete(ctx, obj):
    _check_not_billed(ctx, obj.billing_statement_id)


def _ts_complete_expr():
    return case((or_(TimesheetEntry.project_id.is_(None), TimesheetEntry.hours.is_(None)), literal(False)),
                else_=literal(True))


def _recalc_action(model_name):
    def handler(ctx, ids, payload):
        from app.services.recalc import recalc_ids
        n = recalc_ids(ctx, model_name, ids)
        return {"message": f"Prepočítané záznamy: {n}"}
    return handler


register(Entity(
    name="timesheets", label="Hodiny", model=TimesheetEntry, read_roles=ALL_ROLES, write_roles=ALL_ROLES,
    row_filter=_ts_row_filter, default_sort="date:desc", before_save=_ts_before_save,
    before_delete=_ts_before_delete, title_field="date",
    joins=lambda: [(TWorker, TWorker.id == TimesheetEntry.worker_id), (TProj, TProj.id == TimesheetEntry.project_id),
                   (TCust, TCust.id == TProj.customer_id)],
    actions=[Action("recalc", "Prepočítať sadzby", _recalc_action("timesheet"),
                    confirm="Prepočítať sadzby podľa aktuálne platných sadzieb? Zmena sa zapíše do audit logu.")],
    fields=[
        F("date", "Dátum", "date", required=True),
        F("worker_id", "Pracovník", "ref", ref="workers", label_expr=lambda: TWorker.name, edit_roles=ADMIN),
        F("project_id", "Zákazka", "ref", ref="projects", label_expr=lambda: TProj.name),
        F("customer_name", "Odberateľ", expr=lambda: TCust.name, computed=True, editable=False, roles=ADMIN,
          default_visible=False),
        F("time_from", "Od", "time"), F("time_to", "Do", "time"),
        F("hours", "Hodiny", "hours", help="Vypočíta sa z času od–do, alebo zadajte priamo."),
        F("description", "Popis práce", "longtext"),
        F("material_bought", "Nakúpený materiál", "bool"),
        F("billable", "Fakturovať zákazníkovi", "bool", roles=ADMIN),
        F("cost_rate", "Nákladová sadzba", "money", editable=False, computed=True, aggregate=False,
          default_visible=False),
        F("cost_amount", "Náklad", "money", editable=False, computed=True),
        F("billing_rate", "Fakturačná sadzba", "money", editable=False, computed=True, roles=ADMIN, aggregate=False,
          default_visible=False),
        F("billable_amount", "Fakturovateľná hodnota", "money", editable=False, computed=True, roles=ADMIN,
          default_visible=False),
        F("complete", "Úplný záznam", "bool", expr=_ts_complete_expr, computed=True, editable=False,
          default_visible=False),
        F("billed", "Vyfakturované", "bool", expr=lambda: TimesheetEntry.billing_statement_id.is_not(None),
          computed=True, editable=False, roles=ADMIN, default_visible=False),
        F("source", "Zdroj", editable=False, default_visible=False),
        _created(),
    ],
))

# ============================================================================= Trips
TrVeh, TrProj, TrDriver, TrW = aliased(Vehicle), aliased(Project), aliased(Worker), aliased(Worker)


def _trip_row_filter(ctx):
    if ctx.role == "worker":
        return or_(Trip.driver_id == (ctx.user.worker_id or -1), Trip.created_by == ctx.user.id)
    return None


def _trip_before_save(ctx, obj: Trip, data, is_new):
    if not is_new:
        _check_not_billed(ctx, obj.billing_statement_id)
    if ctx.role == "worker" and not obj.driver_id:
        obj.driver_id = ctx.user.worker_id
    _check_project(ctx, obj.project_id)
    v = ctx.db.get(Vehicle, obj.vehicle_id) if obj.vehicle_id else None
    if not v:
        raise HTTPException(422, "Zadajte vozidlo.")
    obj.company_id = ctx.company_id
    if is_new:
        obj.created_by = ctx.user.id
    refresh = is_new or bool({"vehicle_id", "project_id", "date"} & ctx.changed)
    calc.apply_trip(ctx.db, obj, refresh_rates=refresh)


def _trip_crew_save(ctx, obj: Trip, ids):
    before = [w.id for w in obj.crew]
    obj.crew = [ctx.db.get(Worker, i) for i in ids if ctx.db.get(Worker, i)]
    return before


register(Entity(
    name="trips", label="Jazdy", model=Trip, read_roles=ALL_ROLES, write_roles=ALL_ROLES,
    row_filter=_trip_row_filter, default_sort="date:desc", before_save=_trip_before_save,
    before_delete=lambda ctx, obj: _check_not_billed(ctx, obj.billing_statement_id),
    multiref_save={"crew_ids": _trip_crew_save}, title_field="date",
    joins=lambda: [(TrVeh, TrVeh.id == Trip.vehicle_id), (TrProj, TrProj.id == Trip.project_id),
                   (TrDriver, TrDriver.id == Trip.driver_id)],
    actions=[Action("recalc", "Prepočítať km a sadzby", _recalc_action("trip"),
                    confirm="Prepočítať km a sadzby podľa aktuálnych údajov? Zmena sa zapíše do audit logu.")],
    fields=[
        F("date", "Dátum", "date", required=True),
        F("vehicle_id", "Vozidlo", "ref", ref="vehicles", label_expr=lambda: func.concat(TrVeh.name, " (", TrVeh.plate, ")"),
          required=True),
        F("project_id", "Zákazka", "ref", ref="projects", label_expr=lambda: TrProj.name),
        F("driver_id", "Vodič", "ref", ref="workers", label_expr=lambda: TrDriver.name),
        F("crew_ids", "Posádka", "multiref", ref="workers", attr="crew", sortable=False,
          expr=lambda: string_agg_names(TrW.name, trip_crew, trip_crew.c.trip_id, TrW, trip_crew.c.worker_id, Trip.id),
          label_expr=lambda: string_agg_names(TrW.name, trip_crew, trip_crew.c.trip_id, TrW, trip_crew.c.worker_id,
                                              Trip.id)),
        F("km", "Km (zadané)", "number", help="Ak nevyplníte, dopočíta sa 2 × vzdialenosť zákazky + prirážka."),
        F("km_effective", "Km (použité)", "number", editable=False, computed=True),
        F("km_computed", "Km dopočítané", "bool", editable=False, computed=True, default_visible=False),
        F("rate_per_km", "Sadzba €/km", "money", editable=False, computed=True, roles=ADMIN, aggregate=False,
          default_visible=False),
        F("cost_amount", "Náklad", "money", editable=False, computed=True, roles=ADMIN),
        F("billable_amount", "Fakturovateľná hodnota", "money", editable=False, computed=True, roles=ADMIN,
          default_visible=False),
        F("note", "Poznámka", "longtext"),
        _created(),
    ],
))

# ============================================================================= Vehicles
VRate = aliased(VehicleRate)


def _vehicle_scope(ctx):
    return Vehicle.company_id == ctx.company_id


def _current_rate_expr():
    today = func.current_date()
    return (select(VRate.rate_per_km).where(
        VRate.vehicle_id == Vehicle.id, or_(VRate.valid_from.is_(None), VRate.valid_from <= today),
        or_(VRate.valid_to.is_(None), VRate.valid_to >= today))
        .order_by(VRate.valid_from.desc().nullslast(), VRate.id.desc()).limit(1)
        .correlate(Vehicle).scalar_subquery())


def _vehicle_after_save(ctx, obj: Vehicle, data, is_new):
    rate = data.get("initial_rate_per_km")
    if is_new and rate not in (None, ""):
        from decimal import Decimal
        ctx.db.add(VehicleRate(vehicle_id=obj.id, rate_per_km=Decimal(str(rate).replace(",", "."))))


register(Entity(
    name="vehicles", label="Vozidlá", model=Vehicle, has_active=True, deletable=False, default_sort="name:asc",
    read_roles=ADMIN, after_save=_vehicle_after_save,
    fields=[
        F("name", "Pomenovanie", required=True), F("manufacturer", "Výrobca"), F("model", "Model"),
        F("plate", "ŠPZ"), F("vin", "VIN", default_visible=False),
        F("current_rate", "Sadzba €/km (aktuálna)", "money", expr=_current_rate_expr, computed=True, editable=False,
          aggregate=False),
        F("initial_rate_per_km", "Sadzba €/km (pri založení)", "money", expr=lambda: literal(None),
          sortable=False, filterable=False, default_visible=False, virtual=True, aggregate=False,
          help="Ďalšie zmeny sadzby zadávajte v časti Sadzby vozidiel (s platnosťou od–do)."),
        F("stk_valid_to", "Platnosť STK", "date"), F("ek_valid_to", "Platnosť EK", "date"),
        F("odometer", "Stav tachometra (km)", "number", aggregate=False),
        _note(), _active_field(),
    ],
))

def _check_before(ctx, obj, data, is_new):
    obj.checked_at = obj.checked_at or datetime.now(timezone.utc)
    obj.method = obj.method or "manual"
    obj.checked_by = ctx.user.id
    from app.services.vehicle_check import compare_with_records
    obj.matches = compare_with_records(ctx.db, obj)


def _vehicle_child(name, label, model, fields, default_sort="id:desc", title="id", extra_before=None):
    V = aliased(Vehicle)

    def before(ctx, obj, data, is_new):
        v = ctx.db.get(Vehicle, obj.vehicle_id) if obj.vehicle_id else None
        if not v or v.company_id != ctx.company_id:
            raise HTTPException(422, "Vozidlo nepatrí aktívnej firme.")
        if getattr(obj, "valid_from", None) and getattr(obj, "valid_to", None) and obj.valid_to < obj.valid_from:
            raise HTTPException(422, "Platnosť do je skôr ako platnosť od.")
        if extra_before:
            extra_before(ctx, obj, data, is_new)

    register(Entity(
        name=name, label=label, model=model, company_scoped=False,
        base_filter=lambda ctx: V.company_id == ctx.company_id, default_sort=default_sort, title_field=title,
        joins=lambda: [(V, V.id == model.vehicle_id)], before_save=before,
        fields=[F("vehicle_id", "Vozidlo", "ref", ref="vehicles", required=True,
                  label_expr=lambda: func.concat(V.name, " (", V.plate, ")"))] + fields,
    ))


_vehicle_child("vehicle_rates", "Sadzby vozidiel", VehicleRate, [
    F("rate_per_km", "Sadzba €/km", "money", required=True, aggregate=False),
    F("valid_from", "Platí od", "date"), F("valid_to", "Platí do", "date"), _note()])
_vehicle_child("vehicle_insurance", "PZP a poistenie", VehicleInsurance, [
    F("insurance_type", "Typ poistenia", "select", options=INSURANCE_TYPES),
    F("insurer", "Poisťovňa"), F("contract_no", "Číslo zmluvy"), F("premium", "Ročné poistné", "money"),
    F("payment_period", "Periodicita platby", "select", options=PAYMENT_PERIODS),
    F("valid_from", "Platnosť od", "date"), F("valid_to", "Platnosť do", "date"),
    F("document_id", "Doklad", "ref", ref="documents", default_visible=False), _note()], "valid_to:desc")
_vehicle_child("vehicle_vignettes", "Diaľničné známky", VehicleVignette, [
    F("country", "Krajina", "select", options=COUNTRIES), F("vignette_type", "Typ", "select", options=VIGNETTE_TYPES),
    F("plate", "ŠPZ na známke"), F("valid_from", "Platnosť od", "date"), F("valid_to", "Platnosť do", "date"),
    F("price", "Cena", "money"), F("document_id", "Doklad", "ref", ref="documents", default_visible=False), _note()],
    "valid_to:desc")
_vehicle_child("vehicle_services", "Servis vozidiel", VehicleService, [
    F("date", "Dátum", "date", required=True), F("odometer", "Stav km", "number", aggregate=False),
    F("service_type", "Typ", "select", options=SERVICE_TYPES), F("description", "Popis", "longtext"),
    F("supplier", "Dodávateľ"), F("price", "Cena", "money"),
    F("document_id", "Doklad", "ref", ref="documents", default_visible=False),
    F("next_service_date", "Ďalší servis – dátum", "date"), F("next_service_km", "Ďalší servis – km", "number",
                                                               aggregate=False), _note()], "date:desc")
_vehicle_child("vehicle_checks", "Overenia vozidiel", VehicleCheck, [
    F("service", "Služba", "select", options=CHECK_SERVICES, required=True),
    F("checked_at", "Čas overenia", "datetime", editable=False),
    F("method", "Spôsob", "select", options=[("api", "Automaticky (API)"), ("manual", "Ručne")], editable=False),
    F("result", "Výsledok", "select", options=CHECK_RESULTS, required=True),
    F("valid_to", "Zistená platnosť do", "date"),
    F("matches", "Zhoda s evidenciou", "bool", editable=False),
    F("found_data", "Nájdené údaje", "longtext", default_visible=False), _note()], "checked_at:desc",
    extra_before=lambda ctx, obj, data, is_new: _check_before(ctx, obj, data, is_new))

# ============================================================================= Documents
DCust, DSeries, DFile = aliased(Customer), aliased(InvoiceSeries), aliased(SourceFile)
AP = aliased(Project)


def _doc_projects_expr():
    return (select(func.string_agg(func.distinct(AP.name), literal(", ")))
            .select_from(Allocation.__table__.join(AP, AP.id == Allocation.project_id))
            .where(Allocation.document_id == Document.id).correlate(Document).scalar_subquery())


def _doc_action(name):
    def handler(ctx, ids, payload):
        from app.services import documents as ds
        return getattr(ds, name)(ctx, ids, payload or {})
    return handler


DOC_FIELDS = [
    F("doc_type", "Typ dokladu", "select", options=DOC_TYPES, required=True),
    F("status", "Stav", "select", options=DOC_STATUS, editable=False),
    F("issue_date", "Dátum", "date"), F("issue_time", "Čas", "time", default_visible=False),
    F("partner_name", "Dodávateľ / odberateľ"), F("partner_ico", "IČO partnera"),
    F("partner_ic_dph", "IČ DPH partnera", default_visible=False),
    F("partner_iban", "IBAN partnera", default_visible=False),
    F("buyer_ico", "IČO odberateľa na doklade", default_visible=False),
    F("customer_id", "Odberateľ (vystavená f.)", "ref", ref="customers", label_expr=lambda: DCust.name,
      default_visible=False),
    F("number", "Číslo dokladu"), F("ekasa_id", "ID dokladu eKasa", default_visible=False),
    F("series_id", "Číselný rad", "ref", ref="invoice_series", label_expr=lambda: DSeries.prefix, default_visible=False),
    F("due_date", "Splatnosť", "date", default_visible=False), F("tax_date", "Dátum DPH", "date", default_visible=False),
    F("vs", "VS", default_visible=False),
    F("total_net", "Základ", "money"), F("total_vat", "DPH", "money"), F("total_gross", "Spolu s DPH", "money"),
    F("projects", "Zákazky", expr=_doc_projects_expr, computed=True, editable=False, sortable=False),
    F("extraction_source", "Zdroj údajov", "select", options=EXTRACTION, editable=False),
    F("payment_status", "Úhrada", "select", options=PAYMENT_STATUS, editable=False, default_visible=False),
    F("paid_amount", "Uhradené", "money", editable=False, default_visible=False),
    F("is_electronic", "Elektronický doklad", "bool", default_visible=False),
    F("physical_original", "Fyzický originál", "bool"),
    F("physical_original_at", "Originál založený dňa", "date", default_visible=False),
    F("duplicate_of_id", "Duplicita k dokladu", "number", editable=False, default_visible=False, aggregate=False),
    F("has_warnings", "Upozornenia", "bool", expr=lambda: and_(Document.warnings.is_not(None), Document.warnings != "[]"),
      computed=True, editable=False, default_visible=False),
    F("warnings", "Text upozornení", "longtext", editable=False, default_visible=False),
    F("file_name", "Súbor", expr=lambda: DFile.original_name, computed=True, editable=False, default_visible=False),
    F("note", "Poznámka", "longtext", default_visible=False),
    _created(),
]

register(Entity(
    name="documents", label="Doklady", model=Document, default_sort="issue_date:desc", title_field="number",
    detail_url="/doklady/{id}", creatable=False,
    joins=lambda: [(DCust, DCust.id == Document.customer_id), (DSeries, DSeries.id == Document.series_id),
                   (DFile, DFile.id == Document.source_file_id)],
    before_delete=lambda ctx, obj: __import__("app.services.documents", fromlist=["x"]).before_delete(ctx, obj),
    actions=[
        Action("confirm", "Potvrdiť", _doc_action("action_confirm")),
        Action("set_project", "Priradiť zákazku (celý doklad)", _doc_action("action_set_project"), payload="project"),
        Action("set_overhead", "Do Réžie", _doc_action("action_set_overhead")),
        Action("mark_physical", "Označiť fyzický originál", _doc_action("action_mark_physical")),
        Action("unconfirm", "Vrátiť na kontrolu", _doc_action("action_unconfirm")),
    ],
    fields=DOC_FIELDS,
))

LDoc, LAP = aliased(Document), aliased(Project)
register(Entity(
    name="document_lines", label="Položky dokladov", model=DocumentLine, company_scoped=False,
    base_filter=lambda ctx: LDoc.company_id == ctx.company_id, default_sort="id:desc", creatable=False,
    write_roles=(), title_field="description",
    joins=lambda: [(LDoc, LDoc.id == DocumentLine.document_id)],
    fields=[
        F("doc_date", "Dátum", "date", expr=lambda: LDoc.issue_date, computed=True),
        F("doc_type", "Typ dokladu", "select", options=DOC_TYPES, expr=lambda: LDoc.doc_type, computed=True),
        F("doc_status", "Stav dokladu", "select", options=DOC_STATUS, expr=lambda: LDoc.status, computed=True),
        F("partner", "Dodávateľ", expr=lambda: LDoc.partner_name, computed=True),
        F("document_id", "Doklad", "number", aggregate=False),
        F("description", "Položka"), F("quantity", "Množstvo", "number", aggregate=False), F("unit", "MJ"),
        F("unit_price", "Jedn. cena", "money", aggregate=False), F("vat_rate", "Sadzba DPH", "number", aggregate=False),
        F("total_net", "Základ", "money"), F("total_gross", "Spolu", "money"),
        F("projects", "Zákazky", computed=True, sortable=False,
          expr=lambda: (select(func.string_agg(func.distinct(LAP.name), literal(", ")))
                        .select_from(Allocation.__table__.join(LAP, LAP.id == Allocation.project_id))
                        .where(or_(Allocation.line_id == DocumentLine.id,
                                   and_(Allocation.document_id == DocumentLine.document_id, Allocation.line_id.is_(None))))
                        .correlate(DocumentLine).scalar_subquery())),
    ],
))

ADoc, AProj = aliased(Document), aliased(Project)
ALine = aliased(DocumentLine)
register(Entity(
    name="allocations", label="Priradenia nákladov a výnosov", model=Allocation, default_sort="id:desc",
    creatable=False, write_roles=(), title_field="id",
    joins=lambda: [(ADoc, ADoc.id == Allocation.document_id), (AProj, AProj.id == Allocation.project_id),
                   (ALine, ALine.id == Allocation.line_id)],
    fields=[
        F("doc_date", "Dátum", "date", expr=lambda: ADoc.issue_date, computed=True),
        F("project_id", "Zákazka", "ref", ref="projects", label_expr=lambda: AProj.name),
        F("direction", "Smer", "select", options=[("cost", "Náklad"), ("revenue", "Výnos")]),
        F("doc_type", "Typ dokladu", "select", options=DOC_TYPES, expr=lambda: ADoc.doc_type, computed=True),
        F("doc_status", "Stav dokladu", "select", options=DOC_STATUS, expr=lambda: ADoc.status, computed=True),
        F("partner", "Partner", expr=lambda: ADoc.partner_name, computed=True),
        F("doc_number", "Číslo dokladu", expr=lambda: ADoc.number, computed=True),
        F("document_id", "ID dokladu", "number", aggregate=False, default_visible=False),
        F("line", "Položka", expr=lambda: ALine.description, computed=True),
        F("share_pct", "Podiel %", "number", aggregate=False, default_visible=False),
        F("amount_net", "Suma bez DPH", "money"), F("amount_gross", "Suma s DPH", "money"),
        F("billed", "Vyfakturované", "bool", expr=lambda: Allocation.billing_statement_id.is_not(None), computed=True),
    ],
))

register(Entity(
    name="source_files", label="Prijaté súbory (inbox)", model=SourceFile, default_sort="created_at:desc",
    creatable=False, title_field="original_name",
    actions=[Action("reprocess", "Spracovať znova", lambda ctx, ids, payload: __import__(
        "app.services.ingest", fromlist=["x"]).reprocess(ctx, ids))],
    fields=[
        F("created_at", "Prijaté", "datetime", editable=False), F("original_name", "Súbor", editable=False),
        F("source", "Zdroj", "select", options=FILE_SOURCES, editable=False),
        F("kind_hint", "Druh", "select", options=KIND_HINTS),
        F("physical", "Sken fyzického originálu", "bool"),
        F("status", "Stav", "select", options=FILE_STATUS, editable=False),
        F("document_id", "Doklad", "number", editable=False, aggregate=False),
        F("error", "Chyba / info", "longtext", editable=False),
        F("size", "Veľkosť (B)", "number", editable=False, default_visible=False, aggregate=False),
        F("note", "Poznámka", "longtext", default_visible=False),
    ],
))

# ============================================================================= Billing statements
BProj = aliased(Project)
register(Entity(
    name="billing_statements", label="Podklady k fakturácii", model=BillingStatement, default_sort="period_to:desc",
    creatable=False, detail_url="/vystupy/fakturacia/{id}", title_field="id",
    joins=lambda: [(BProj, BProj.id == BillingStatement.project_id)],
    before_delete=lambda ctx, obj: __import__("app.services.billing", fromlist=["x"]).before_delete(ctx, obj),
    fields=[
        F("project_id", "Zákazka", "ref", ref="projects", label_expr=lambda: BProj.name, editable=False),
        F("period_from", "Obdobie od", "date", editable=False), F("period_to", "Obdobie do", "date", editable=False),
        F("status", "Stav", "select", options=BILLING_STATUS, editable=False),
        F("total_net", "Bez DPH", "money", editable=False), F("total_vat", "DPH", "money", editable=False),
        F("total_gross", "S DPH", "money", editable=False),
        F("invoice_document_id", "Vystavená faktúra (ID)", "number", editable=False, aggregate=False),
        F("note", "Poznámka", "longtext"), _created(),
    ],
))

# ============================================================================= Bank
BTAcc = aliased(BankAccount)
register(Entity(
    name="bank_statements", label="Bankové výpisy", model=BankStatement, default_sort="created_at:desc",
    creatable=False, write_roles=ADMIN, title_field="id",
    joins=lambda: [(BTAcc, BTAcc.id == BankStatement.bank_account_id)],
    fields=[
        F("created_at", "Importované", "datetime", editable=False),
        F("bank_account_id", "Účet", "ref", ref="bank_accounts", label_expr=lambda: BTAcc.iban, editable=False),
        F("period_from", "Od", "date", editable=False), F("period_to", "Do", "date", editable=False),
        F("format", "Formát", editable=False), F("tx_count", "Pohybov", "number", editable=False),
        F("new_tx_count", "Nových", "number", editable=False),
    ],
))

TAcc, TRule = aliased(BankAccount), aliased(TransactionRule)


def _bank_action(name):
    def handler(ctx, ids, payload):
        from app.services import bank
        return getattr(bank, name)(ctx, ids, payload or {})
    return handler


from app.models import TransactionMatch  # noqa: E402

MDoc = aliased(Document)
register(Entity(
    name="bank_transactions", label="Bankové pohyby", model=BankTransaction, default_sort="booking_date:desc",
    creatable=False, deletable=False, title_field="counterparty_name", detail_url="/financie/banka/pohyb/{id}",
    joins=lambda: [(TAcc, TAcc.id == BankTransaction.bank_account_id), (TRule, TRule.id == BankTransaction.rule_id)],
    actions=[
        Action("no_document", "Nepotrebuje doklad", _bank_action("action_no_document")),
        Action("reset", "Zrušiť označenie / párovanie", _bank_action("action_reset")),
        Action("confirm_suggestions", "Potvrdiť návrhy párovania", _bank_action("action_confirm_suggestions")),
        Action("rematch", "Spárovať znova automaticky", _bank_action("action_rematch")),
    ],
    fields=[
        F("booking_date", "Dátum", "date", editable=False),
        F("amount", "Suma", "money", editable=False),
        F("currency", "Mena", editable=False, default_visible=False),
        F("counterparty_name", "Protistrana", editable=False),
        F("counterparty_iban", "IBAN protistrany", editable=False, default_visible=False),
        F("vs", "VS", editable=False), F("ss", "SS", editable=False, default_visible=False),
        F("ks", "KS", editable=False, default_visible=False),
        F("message", "Správa", "longtext", editable=False),
        F("tx_type", "Typ", "select", options=TX_TYPES, editable=False),
        F("status", "Stav", "select", options=TX_STATUS, editable=False),
        F("matched_docs", "Doklady", computed=True, sortable=False, editable=False,
          expr=lambda: (select(func.string_agg(func.coalesce(MDoc.number, MDoc.partner_name), literal(", ")))
                        .select_from(TransactionMatch.__table__.join(MDoc, MDoc.id == TransactionMatch.document_id))
                        .where(TransactionMatch.transaction_id == BankTransaction.id)
                        .correlate(BankTransaction).scalar_subquery())),
        F("matched_amount", "Spárovaná suma", "money", editable=False, default_visible=False),
        F("bank_account_id", "Účet", "ref", ref="bank_accounts", label_expr=lambda: TAcc.iban, editable=False,
          default_visible=False),
        F("rule", "Pravidlo", expr=lambda: TRule.name, computed=True, default_visible=False),
        F("note", "Poznámka", "longtext"),
    ],
))

register(Entity(
    name="transaction_rules", label="Pravidlá bankových pohybov", model=TransactionRule, has_active=True,
    deletable=True, default_sort="name:asc",
    fields=[
        F("name", "Názov pravidla", required=True),
        F("cond_counterparty", "Protistrana obsahuje"), F("cond_iban", "IBAN protistrany"),
        F("cond_text", "Správa obsahuje"), F("cond_type", "Typ pohybu", "select", options=TX_TYPES),
        F("action", "Akcia", "select", options=RULE_ACTIONS, required=True),
        F("action_value", "Hodnota akcie", help="Pri návrhu zákazky: názov zákazky; pri návrhu dodávateľa: názov."),
        _active_field(),
    ],
))

# ============================================================================= Audit log
AU = aliased(User)
register(Entity(
    name="audit_log", label="Audit log", model=AuditLog, company_scoped=False,
    base_filter=lambda ctx: or_(AuditLog.company_id.is_(None), AuditLog.company_id == ctx.company_id),
    default_sort="ts:desc", creatable=False, write_roles=(), title_field="id",
    joins=lambda: [(AU, AU.id == AuditLog.user_id)],
    fields=[
        F("ts", "Čas", "datetime"), F("user", "Používateľ", expr=lambda: AU.name, computed=True),
        F("entity", "Entita"), F("entity_id", "ID záznamu", "number", aggregate=False), F("action", "Akcia"),
        F("changes", "Zmeny", "longtext"), F("note", "Poznámka", "longtext"),
    ],
))
