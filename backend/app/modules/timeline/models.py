"""Shared activity timeline — chronological events against any CRM entity
(leads, customers, bookings). Powers lead timelines (Task 4) and customer
timeline intelligence (Task 15)."""
from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

ACTIVITY_TYPES = {
    "created", "updated", "stage_change", "assigned", "note", "call", "email",
    "meeting", "site_visit", "whatsapp", "document", "task", "booking",
    "payment", "ai_recommendation", "converted", "merged",
}


class Activity(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "activities"

    entity_type: Mapped[str] = mapped_column(String(30), index=True)  # lead|customer|booking
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    type: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


def log_activity(
    db: Session,
    *,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    type: str,
    title: str,
    actor=None,
    detail: dict[str, Any] | None = None,
) -> Activity:
    activity = Activity(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=getattr(actor, "id", None),
        actor_name=getattr(actor, "full_name", None),
        type=type if type in ACTIVITY_TYPES else "updated",
        title=title,
        detail=detail,
    )
    db.add(activity)
    return activity
