"""Investor-event marketing module: landing page, registrations, speakers,
agenda (CMS), QR check-in, referrals. Registrations feed the CRM by creating
a real Lead (source="event") via leads.service.create_lead — they inherit
auto-assignment, AI scoring, and pipeline tracking for free rather than
duplicating that machinery here."""
import secrets
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EventStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    COMPLETED = "completed"


class Event(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "events"

    name: Mapped[str] = mapped_column(String(200))
    # Globally unique (not per-tenant): the public landing page is looked up
    # by slug alone with no tenant context (/events/[slug]), so two tenants
    # publishing the same instance can't collide on the same public URL.
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default=EventStatus.DRAFT.value, index=True)
    hero_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cta_text: Mapped[str] = mapped_column(String(100), default="Register now")
    total_ad_spend: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    follow_up_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    speakers: Mapped[list["Speaker"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin",
        order_by="Speaker.sort_order",
    )
    agenda_items: Mapped[list["AgendaItem"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin",
        order_by="AgendaItem.start_time",
    )


class Speaker(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "event_speakers"

    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    event: Mapped[Event] = relationship(back_populates="speakers")


class AgendaItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "event_agenda_items"

    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    speaker_id: Mapped[str | None] = mapped_column(ForeignKey("event_speakers.id"), nullable=True)

    event: Mapped[Event] = relationship(back_populates="agenda_items")
    speaker: Mapped[Speaker | None] = relationship(lazy="joined")


class RegistrationStage(StrEnum):
    REGISTERED = "registered"
    RSVP_CONFIRMED = "rsvp_confirmed"
    ATTENDED = "attended"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


def _new_referral_code() -> str:
    return secrets.token_hex(4)  # short, URL-friendly, unique enough for a ?ref= param


def _new_checkin_token() -> str:
    return secrets.token_urlsafe(16)


class EventRegistration(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "email", name="uq_event_registration_email"),
    )

    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    investment_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="event")
    utm_campaign: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stage: Mapped[str] = mapped_column(
        String(20), default=RegistrationStage.REGISTERED.value, index=True
    )
    checkin_token: Mapped[str] = mapped_column(String(64), unique=True, default=_new_checkin_token)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    badge_printed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    referral_code: Mapped[str] = mapped_column(
        String(20), unique=True, default=_new_referral_code
    )
    referred_by_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # Dedup markers for the pre-event reminder sweep — same pattern as
    # Event.follow_up_sent_at, one column per reminder so each fires exactly once.
    reminder_48h_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminder_24h_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    event: Mapped[Event] = relationship(lazy="joined")
