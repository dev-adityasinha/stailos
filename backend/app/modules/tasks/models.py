"""Task management: assignments, deadlines, priorities, comments, attachments."""
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class CrmTask(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "crm_tasks"

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    priority: Mapped[str] = mapped_column(
        String(10), default=TaskPriority.MEDIUM.value, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=TaskStatus.TODO.value, index=True
    )
    # Optional link to the CRM record this task is about
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    assignee = relationship("User", foreign_keys=[assigned_to], lazy="joined")
    comments: Mapped[list["TaskComment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", lazy="selectin",
        order_by="TaskComment.created_at",
    )
    attachments: Mapped[list["TaskAttachment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", lazy="selectin",
    )


class TaskComment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "task_comments"

    task_id: Mapped[str] = mapped_column(ForeignKey("crm_tasks.id"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(String(4000))

    task: Mapped[CrmTask] = relationship(back_populates="comments")


class TaskAttachment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "task_attachments"

    task_id: Mapped[str] = mapped_column(ForeignKey("crm_tasks.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(default=0)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    task: Mapped[CrmTask] = relationship(back_populates="attachments")
