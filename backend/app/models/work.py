"""Timesheets, trips and fleet."""
import datetime as dt
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Table, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.core import MONEY, RATE, TimestampMixin


class TimesheetEntry(TimestampMixin, Base):
    __tablename__ = "timesheet_entry"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("worker.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    time_from: Mapped[time | None] = mapped_column(Time)
    time_to: Mapped[time | None] = mapped_column(Time)
    hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    description: Mapped[str | None] = mapped_column(Text)
    material_bought: Mapped[bool] = mapped_column(Boolean, default=False)
    billable: Mapped[bool] = mapped_column(Boolean, default=True)
    cost_rate: Mapped[Decimal | None] = mapped_column(RATE)
    billing_rate: Mapped[Decimal | None] = mapped_column(RATE)
    cost_amount: Mapped[Decimal] = mapped_column(MONEY, default=0)
    billable_amount: Mapped[Decimal] = mapped_column(MONEY, default=0)
    billing_statement_id: Mapped[int | None] = mapped_column(ForeignKey("billing_statement.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(20), default="web")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))


trip_crew = Table(
    "trip_crew",
    Base.metadata,
    Column("trip_id", ForeignKey("trip.id", ondelete="CASCADE"), primary_key=True),
    Column("worker_id", ForeignKey("worker.id", ondelete="CASCADE"), primary_key=True),
)


class Trip(TimestampMixin, Base):
    __tablename__ = "trip"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)  # company of the project
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("worker.id"))
    km: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    km_effective: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    km_computed: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_per_km: Mapped[Decimal | None] = mapped_column(RATE)
    cost_amount: Mapped[Decimal] = mapped_column(MONEY, default=0)
    billing_rate_per_km: Mapped[Decimal | None] = mapped_column(RATE)
    billable_amount: Mapped[Decimal] = mapped_column(MONEY, default=0)
    billing_statement_id: Mapped[int | None] = mapped_column(ForeignKey("billing_statement.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="web")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))

    crew = relationship("Worker", secondary=trip_crew)


class Vehicle(TimestampMixin, Base):
    __tablename__ = "vehicle"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    plate: Mapped[str | None] = mapped_column(String(20))
    vin: Mapped[str | None] = mapped_column(String(40))
    stk_valid_to: Mapped[dt.date | None] = mapped_column(Date)
    ek_valid_to: Mapped[dt.date | None] = mapped_column(Date)
    odometer: Mapped[int | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class VehicleRate(TimestampMixin, Base):
    __tablename__ = "vehicle_rate"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id", ondelete="CASCADE"), index=True)
    rate_per_km: Mapped[Decimal] = mapped_column(RATE)
    valid_from: Mapped[dt.date | None] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)


class VehicleInsurance(TimestampMixin, Base):
    __tablename__ = "vehicle_insurance"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id", ondelete="CASCADE"), index=True)
    insurance_type: Mapped[str] = mapped_column(String(20), default="pzp")  # pzp | havarijne
    insurer: Mapped[str | None] = mapped_column(String(200))
    contract_no: Mapped[str | None] = mapped_column(String(100))
    premium: Mapped[Decimal | None] = mapped_column(MONEY)
    payment_period: Mapped[str | None] = mapped_column(String(20))  # annual | semiannual | quarterly | monthly
    valid_from: Mapped[dt.date | None] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)


class VehicleVignette(TimestampMixin, Base):
    __tablename__ = "vehicle_vignette"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id", ondelete="CASCADE"), index=True)
    country: Mapped[str] = mapped_column(String(2), default="SK")
    vignette_type: Mapped[str] = mapped_column(String(20), default="annual")  # annual | 30d | 10d | other
    plate: Mapped[str | None] = mapped_column(String(20))
    valid_from: Mapped[dt.date | None] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)


class VehicleService(TimestampMixin, Base):
    __tablename__ = "vehicle_service"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id", ondelete="CASCADE"), index=True)
    date: Mapped[dt.date] = mapped_column(Date)
    odometer: Mapped[int | None] = mapped_column()
    service_type: Mapped[str] = mapped_column(String(20), default="regular")  # regular | repair | tires | other
    description: Mapped[str | None] = mapped_column(Text)
    supplier: Mapped[str | None] = mapped_column(String(200))
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id", ondelete="SET NULL"))
    next_service_date: Mapped[dt.date | None] = mapped_column(Date)
    next_service_km: Mapped[int | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)


class VehicleCheck(Base):
    __tablename__ = "vehicle_check"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id", ondelete="CASCADE"), index=True)
    service: Mapped[str] = mapped_column(String(20))  # vignette | pzp | stk | ek
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    method: Mapped[str] = mapped_column(String(20), default="manual")  # api | manual
    result: Mapped[str] = mapped_column(String(20))  # valid | invalid | unknown | error
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    found_data: Mapped[str | None] = mapped_column(Text)
    matches: Mapped[bool | None] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(Text)
    checked_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
