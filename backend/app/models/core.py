"""Master data: companies, customers, projects, workers, rates, users."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Table, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

MONEY = Numeric(14, 2)
RATE = Numeric(12, 4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Company(TimestampMixin, Base):
    __tablename__ = "company"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    ico: Mapped[str | None] = mapped_column(String(20))
    dic: Mapped[str | None] = mapped_column(String(20))
    ic_dph: Mapped[str | None] = mapped_column(String(20))
    vat_payer: Mapped[bool] = mapped_column(Boolean, default=True)
    address: Mapped[str | None] = mapped_column(Text)
    invoice_address: Mapped[str | None] = mapped_column(Text)
    drive_inbox_folder_id: Mapped[str | None] = mapped_column(String(200))
    drive_processed_folder_id: Mapped[str | None] = mapped_column(String(200))
    drive_bank_inbox_folder_id: Mapped[str | None] = mapped_column(String(200))
    email_tag_invoices: Mapped[str | None] = mapped_column(String(100))
    email_tag_bank: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class BankAccount(TimestampMixin, Base):
    __tablename__ = "bank_account"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    iban: Mapped[str] = mapped_column(String(40))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(TimestampMixin, Base):
    __tablename__ = "customer"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    ico: Mapped[str | None] = mapped_column(String(20))
    dic: Mapped[str | None] = mapped_column(String(20))
    ic_dph: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Project(TimestampMixin, Base):
    __tablename__ = "project"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[str | None] = mapped_column(Text)  # comma separated
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"))
    cost_budget: Mapped[Decimal | None] = mapped_column(MONEY)
    contract_price: Mapped[Decimal | None] = mapped_column(MONEY)
    billing_type: Mapped[str] = mapped_column(String(20), default="hourly")  # hourly | fixed | combined
    material_markup_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    bill_transport: Mapped[bool] = mapped_column(Boolean, default=False)
    transport_rate_per_km: Mapped[Decimal | None] = mapped_column(RATE)
    default_km_one_way: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    status: Mapped[str] = mapped_column(String(20), default="in_progress")  # planned | in_progress | finished
    is_overhead: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    customer = relationship("Customer")


worker_company = Table(
    "worker_company",
    Base.metadata,
    Column("worker_id", ForeignKey("worker.id", ondelete="CASCADE"), primary_key=True),
    Column("company_id", ForeignKey("company.id", ondelete="CASCADE"), primary_key=True),
)


class Worker(TimestampMixin, Base):
    """Workers are global – one person can work for several companies."""
    __tablename__ = "worker"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[str | None] = mapped_column(Text)
    relation_type: Mapped[str] = mapped_column(String(20), default="employee")  # employee | contractor | other
    ico: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    companies = relationship("Company", secondary=worker_company)


class WorkerRate(TimestampMixin, Base):
    """Rate lookup order: worker+project -> worker+company -> worker default (both null)."""
    __tablename__ = "worker_rate"
    id: Mapped[int] = mapped_column(primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("worker.id"), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), index=True)
    cost_rate: Mapped[Decimal | None] = mapped_column(RATE)
    billing_rate: Mapped[Decimal | None] = mapped_column(RATE)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)


user_company = Table(
    "user_company",
    Base.metadata,
    Column("user_id", ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True),
    Column("company_id", ForeignKey("company.id", ondelete="CASCADE"), primary_key=True),
)


class User(TimestampMixin, Base):
    __tablename__ = "app_user"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="admin")  # admin | worker
    worker_id: Mapped[int | None] = mapped_column(ForeignKey("worker.id"))
    last_company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    companies = relationship("Company", secondary=user_company)


class Setting(Base):
    __tablename__ = "setting"
    __table_args__ = (UniqueConstraint("company_id", "key", name="uq_setting_company_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"))
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[str | None] = mapped_column(Text)  # JSON encoded


class InvoiceSeries(TimestampMixin, Base):
    __tablename__ = "invoice_series"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    prefix: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))  # e.g. person / part of company
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"))
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RecurringInvoiceRule(TimestampMixin, Base):
    __tablename__ = "recurring_invoice_rule"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    supplier_name: Mapped[str] = mapped_column(String(200))
    supplier_ico: Mapped[str | None] = mapped_column(String(20))
    match_text: Mapped[str | None] = mapped_column(String(200))  # alternative name match
    periodicity: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly | quarterly | yearly
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"))
    entity: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(30))
    changes: Mapped[str | None] = mapped_column(Text)  # JSON {field: [old, new]}
    note: Mapped[str | None] = mapped_column(Text)


class TableView(TimestampMixin, Base):
    __tablename__ = "table_view"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    entity: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(200))
    config: Mapped[str] = mapped_column(Text)  # JSON: columns, widths, sort, filters, group_by, q
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    is_last: Mapped[bool] = mapped_column(Boolean, default=False)  # auto-saved last state
