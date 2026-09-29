"""Booking workflow: Lead → Site Visit → Booking → Documentation → Payment →
Possession (task list Task 9), with payment records and full stage history."""
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class BookingStage(StrEnum):
    SITE_VISIT = "site_visit"
    BOOKING = "booking"
    DOCUMENTATION = "documentation"
    PAYMENT = "payment"
    POSSESSION = "possession"
    COMPLETED = "completed"


BOOKING_STAGE_ORDER = [s.value for s in BookingStage]


class BookingStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Booking(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "bookings"

    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("property_units.id"), index=True)
    stage: Mapped[str] = mapped_column(
        String(30), default=BookingStage.SITE_VISIT.value, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=BookingStatus.ACTIVE.value, index=True
    )
    token_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_value: Mapped[float] = mapped_column(Numeric(14, 2))
    discount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    agreement_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    possession_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    customer = relationship("Customer", lazy="joined")
    unit = relationship("PropertyUnit", lazy="joined")
    stage_events: Mapped[list["BookingStageEvent"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan", lazy="selectin",
        order_by="BookingStageEvent.created_at",
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan", lazy="selectin",
        order_by="Payment.created_at",
    )


class BookingStageEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "booking_stage_events"

    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    from_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    booking: Mapped[Booking] = relationship(back_populates="stage_events")


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payments"

    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    method: Mapped[str] = mapped_column(String(30), default="bank_transfer")
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    receipt_number: Mapped[str] = mapped_column(String(50), unique=True)
    milestone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recorded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    booking: Mapped[Booking] = relationship(back_populates="payments")
