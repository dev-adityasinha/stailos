"""In-app notification center. Browser push is served by the frontend polling
`GET /notifications?unread=true` + the Notification API; a Web-Push/WS channel
plugs in behind the same table."""
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class NotificationType(StrEnum):
    ASSIGNMENT = "assignment"
    FOLLOW_UP = "follow_up"
    BOOKING_UPDATE = "booking_update"
    TASK = "task"
    AI_SUGGESTION = "ai_suggestion"
    SYSTEM = "system"


class Notification(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Dedupe key so lazily-generated reminders are created at most once
    dedupe_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
