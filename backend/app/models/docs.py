"""Source files, documents (receipts, invoices), allocations, billing, bank."""
import datetime as dt
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.core import MONEY, RATE, TimestampMixin


class SourceFile(Base):
    __tablename__ = "source_file"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(500))
    storage_path: Mapped[str] = mapped_column(String(1000))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20), default="upload")  # upload | drive | email | bank_inbox | whatsapp
    kind_hint: Mapped[str] = mapped_column(String(20), default="auto")  # auto | receipt | invoice_in | invoice_out | bank
    physical: Mapped[bool] = mapped_column(Boolean, default=False)  # scan of a physical original
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | processed | duplicate | error | skipped
    error: Mapped[str | None] = mapped_column(Text)
    drive_file_id: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))


class Document(TimestampMixin, Base):
    __tablename__ = "document"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(20), index=True)  # receipt | invoice_in | invoice_out
    partner_name: Mapped[str | None] = mapped_column(String(300))
    partner_ico: Mapped[str | None] = mapped_column(String(20), index=True)
    partner_dic: Mapped[str | None] = mapped_column(String(20))
    partner_ic_dph: Mapped[str | None] = mapped_column(String(20))
    partner_iban: Mapped[str | None] = mapped_column(String(40))
    partner_address: Mapped[str | None] = mapped_column(Text)
    buyer_ico: Mapped[str | None] = mapped_column(String(20))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"))
    number: Mapped[str | None] = mapped_column(String(100), index=True)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_series.id"))
    ekasa_id: Mapped[str | None] = mapped_column(String(100), index=True)
    issue_date: Mapped[dt.date | None] = mapped_column(Date, index=True)
    issue_time: Mapped[time | None] = mapped_column(Time)
    due_date: Mapped[dt.date | None] = mapped_column(Date)
    tax_date: Mapped[dt.date | None] = mapped_column(Date)
    vs: Mapped[str | None] = mapped_column(String(40), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    total_net: Mapped[Decimal | None] = mapped_column(MONEY)
    total_vat: Mapped[Decimal | None] = mapped_column(MONEY)
    total_gross: Mapped[Decimal | None] = mapped_column(MONEY)
    vat_breakdown: Mapped[str | None] = mapped_column(Text)  # JSON [{rate, base, vat}]
    extraction_source: Mapped[str] = mapped_column(String(20), default="manual")  # ekasa | claude | pdf_text | manual
    extraction_log: Mapped[str | None] = mapped_column(Text)  # what was tried / what worked
    status: Mapped[str] = mapped_column(String(20), default="review", index=True)  # review | confirmed
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid")  # unpaid | partial | paid
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, default=0)
    is_electronic: Mapped[bool] = mapped_column(Boolean, default=False)
    physical_original: Mapped[bool] = mapped_column(Boolean, default=False)
    physical_original_at: Mapped[dt.date | None] = mapped_column(Date)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("document.id", ondelete="SET NULL"))
    source_file_id: Mapped[int | None] = mapped_column(ForeignKey("source_file.id", ondelete="SET NULL"))
    recurring_rule_id: Mapped[int | None] = mapped_column(ForeignKey("recurring_invoice_rule.id", ondelete="SET NULL"))
    billing_statement_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_statement.id", ondelete="SET NULL", use_alter=True, name="fk_document_billing_statement"))
    mixed: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings: Mapped[str | None] = mapped_column(Text)  # JSON list of strings
    note: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))

    lines = relationship("DocumentLine", order_by="DocumentLine.position", cascade="all, delete-orphan")
    allocations = relationship("Allocation", cascade="all, delete-orphan")


class DocumentSource(Base):
    """All files attached to a document (worker photo, physical scan, e-mail PDF, …)."""
    __tablename__ = "document_source"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), index=True)
    source_file_id: Mapped[int] = mapped_column(ForeignKey("source_file.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), default="original")  # original | physical_scan | duplicate
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text)


class DocumentLine(Base):
    __tablename__ = "document_line"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    unit: Mapped[str | None] = mapped_column(String(20))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))  # gross unit price
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    total_net: Mapped[Decimal | None] = mapped_column(MONEY)
    total_vat: Mapped[Decimal | None] = mapped_column(MONEY)
    total_gross: Mapped[Decimal | None] = mapped_column(MONEY)


class Allocation(Base):
    """Assignment of a document (or a line) to a project – for costs (received docs) and revenue (issued invoices)."""
    __tablename__ = "allocation"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), index=True)
    line_id: Mapped[int | None] = mapped_column(ForeignKey("document_line.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    direction: Mapped[str] = mapped_column(String(10), default="cost")  # cost | revenue
    share_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    amount_net: Mapped[Decimal] = mapped_column(MONEY, default=0)
    amount_gross: Mapped[Decimal] = mapped_column(MONEY, default=0)
    billing_statement_id: Mapped[int | None] = mapped_column(ForeignKey("billing_statement.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)


class BillingStatement(TimestampMixin, Base):
    __tablename__ = "billing_statement"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), index=True)
    period_from: Mapped[dt.date] = mapped_column(Date)
    period_to: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | closed
    invoice_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("document.id", ondelete="SET NULL", use_alter=True, name="fk_billing_statement_invoice_document"))
    group_by: Mapped[str] = mapped_column(String(20), default="worker")  # worker | day
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=23)
    total_net: Mapped[Decimal] = mapped_column(MONEY, default=0)
    total_vat: Mapped[Decimal] = mapped_column(MONEY, default=0)
    total_gross: Mapped[Decimal] = mapped_column(MONEY, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))

    lines = relationship("BillingStatementLine", cascade="all, delete-orphan", order_by="BillingStatementLine.id")


class BillingStatementLine(Base):
    __tablename__ = "billing_statement_line"
    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("billing_statement.id", ondelete="CASCADE"), index=True)
    line_type: Mapped[str] = mapped_column(String(20))  # hours | material | transport | other
    timesheet_id: Mapped[int | None] = mapped_column(ForeignKey("timesheet_entry.id", ondelete="SET NULL"))
    allocation_id: Mapped[int | None] = mapped_column(ForeignKey("allocation.id", ondelete="SET NULL"))
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trip.id", ondelete="SET NULL"))
    date: Mapped[dt.date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    worker_name: Mapped[str | None] = mapped_column(String(200))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    unit: Mapped[str | None] = mapped_column(String(20))
    rate: Mapped[Decimal | None] = mapped_column(RATE)
    markup_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    amount: Mapped[Decimal] = mapped_column(MONEY, default=0)


class BankStatement(Base):
    __tablename__ = "bank_statement"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_account.id"))
    period_from: Mapped[dt.date | None] = mapped_column(Date)
    period_to: Mapped[dt.date | None] = mapped_column(Date)
    source_file_id: Mapped[int | None] = mapped_column(ForeignKey("source_file.id", ondelete="SET NULL"))
    format: Mapped[str] = mapped_column(String(20))  # camt053 | csv | xlsx | pdf
    tx_count: Mapped[int] = mapped_column(Integer, default=0)
    new_tx_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BankTransaction(Base):
    __tablename__ = "bank_transaction"
    __table_args__ = (UniqueConstraint("company_id", "dedupe_key", name="uq_bank_tx_dedupe"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    statement_id: Mapped[int | None] = mapped_column(ForeignKey("bank_statement.id", ondelete="SET NULL"))
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_account.id"))
    booking_date: Mapped[dt.date] = mapped_column(Date, index=True)
    value_date: Mapped[dt.date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(MONEY)  # negative = expense
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    counterparty_name: Mapped[str | None] = mapped_column(String(300))
    counterparty_iban: Mapped[str | None] = mapped_column(String(40))
    vs: Mapped[str | None] = mapped_column(String(40))
    ss: Mapped[str | None] = mapped_column(String(40))
    ks: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str | None] = mapped_column(Text)
    tx_type: Mapped[str] = mapped_column(String(20), default="other")  # card | transfer | fee | other
    bank_ref: Mapped[str | None] = mapped_column(String(200))
    dedupe_key: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="unmatched", index=True)  # unmatched | suggested | matched | no_document
    matched_amount: Mapped[Decimal] = mapped_column(MONEY, default=0)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("transaction_rule.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)


class TransactionMatch(Base):
    __tablename__ = "transaction_match"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("bank_transaction.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    method: Mapped[str] = mapped_column(String(20), default="auto")  # auto | manual | suggested
    reason: Mapped[str | None] = mapped_column(String(300))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TransactionRule(TimestampMixin, Base):
    __tablename__ = "transaction_rule"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    cond_counterparty: Mapped[str | None] = mapped_column(String(200))
    cond_iban: Mapped[str | None] = mapped_column(String(40))
    cond_text: Mapped[str | None] = mapped_column(String(200))
    cond_type: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(30), default="no_document")  # no_document | suggest_project | suggest_supplier
    action_value: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
