"""Lead management domain models."""
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Numeric, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class LeadStage(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    INTERESTED = "interested"
    SITE_VISIT_SCHEDULED = "site_visit_scheduled"
    NEGOTIATION = "negotiation"
    BOOKED = "booked"
    COMPLETED = "completed"
    LOST = "lost"


PIPELINE_ORDER = [s.value for s in LeadStage]

LEAD_SOURCES = [
    "website", "walk_in", "referral", "channel_partner", "meta_ads", "google_ads",
    "whatsapp", "phone_inquiry", "property_portal", "event", "csv_import", "other",
]

lead_tags = Table(
    "lead_tags",
    Base.metadata,
    Column("lead_id", ForeignKey("leads.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)


class Tag(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(50), index=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)


class Lead(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "leads"

    full_name: Mapped[str] = mapped_column(String(200), index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    phone: Mapped[str] = mapped_column(String(20))
    phone_normalized: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(50), default="other", index=True)
    campaign: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stage: Mapped[str] = mapped_column(String(40), default=LeadStage.NEW.value, index=True)
    assigned_to: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    budget_min: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    location_preference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    requirements: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # AI enrichment (populated by the AI layer, Phase 5)
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_band: Mapped[str | None] = mapped_column(String(10), nullable=True)  # hot|warm|cold
    custom_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    assignee = relationship("User", foreign_keys=[assigned_to], lazy="joined")
    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    tags: Mapped[list[Tag]] = relationship(secondary=lead_tags, lazy="selectin")
    notes: Mapped[list["LeadNote"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", lazy="selectin",
        order_by="LeadNote.created_at.desc()",
    )


class LeadNote(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "lead_notes"

    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(String(4000))

    lead: Mapped[Lead] = relationship(back_populates="notes")


class LeadStageEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Auditable pipeline stage history — mirrors bookings' BookingStageEvent.
    Unlike bookings, lead-stage transitions are intentionally not
    order-enforced (real sales pipelines legitimately skip/backtrack stages);
    only leaving a terminal stage (completed/lost) requires an explicit
    reopen, enforced in leads.service.change_stage."""
    __tablename__ = "lead_stage_events"

    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    from_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ImportBatch(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "import_batches"

    filename: Mapped[str] = mapped_column(String(300))
    total_rows: Mapped[int] = mapped_column(default=0)
    imported: Mapped[int] = mapped_column(default=0)
    skipped_duplicates: Mapped[int] = mapped_column(default=0)
    errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
