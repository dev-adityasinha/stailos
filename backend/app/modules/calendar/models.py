"""Calendar: meetings, site visits, calls, reminders, follow-ups, team view."""
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EventType(StrEnum):
    MEETING = "meeting"
    SITE_VISIT = "site_visit"
    CALL = "call"
    REMINDER = "reminder"
    FOLLOW_UP = "follow_up"


event_attendees = Table(
    "event_attendees",
    Base.metadata,
    Column("event_id", ForeignKey("calendar_events.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)


class CalendarEvent(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "calendar_events"

    title: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(20), default=EventType.MEETING.value, index=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled|done|cancelled

    owner = relationship("User", foreign_keys=[owner_id], lazy="joined")
    attendees = relationship("User", secondary=event_attendees, lazy="selectin")
