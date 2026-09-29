"""Notification creation + event subscribers + due-reminders.

Domain events (lead.assigned, booking.stage_changed, …) fan out here into
per-user notifications. Reminders for due-soon tasks/events are generated
both lazily (deduped, when a user fetches their notifications) and by a
periodic APScheduler job (`app.core.scheduler`, `run_due_reminders_for_all_users`)
so they surface even if nobody has the app open — each reminder is also
emailed via `core.email.send_email`, deduped by the same `dedupe_key`.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import events
from app.core.email import send_email
from app.db.base import SessionLocal
from app.modules.auth.models import User
from app.modules.notifications.models import Notification, NotificationType

logger = logging.getLogger("crm.reminders")


def notify(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    type: NotificationType,
    title: str,
    body: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    dedupe_key: str | None = None,
) -> Notification | None:
    if dedupe_key:
        existing = db.scalars(
            select(Notification).where(
                Notification.user_id == user_id, Notification.dedupe_key == dedupe_key
            )
        ).first()
        if existing:
            return None
    n = Notification(
        tenant_id=tenant_id, user_id=user_id, type=type.value, title=title, body=body,
        entity_type=entity_type, entity_id=entity_id, dedupe_key=dedupe_key,
    )
    db.add(n)
    return n


def _naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_due_reminders(db: Session, user: User) -> None:
    """Create follow-up reminders for tasks due within 24h and events starting
    within 60 minutes. Idempotent via dedupe_key."""
    from app.modules.calendar.models import CalendarEvent
    from app.modules.tasks.models import CrmTask, TaskStatus

    now = _naive_now()
    due_tasks = db.scalars(
        select(CrmTask).where(
            CrmTask.assigned_to == user.id,
            CrmTask.deleted_at.is_(None),
            CrmTask.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
            CrmTask.due_date.is_not(None),
            CrmTask.due_date <= now + timedelta(hours=24),
        )
    ).all()
    for task in due_tasks:
        overdue = task.due_date < now
        title = ("Overdue: " if overdue else "Due soon: ") + task.title
        created = notify(
            db, tenant_id=task.tenant_id, user_id=user.id,
            type=NotificationType.FOLLOW_UP,
            title=title,
            entity_type="task", entity_id=task.id,
            dedupe_key=f"task_due:{task.id}:{'overdue' if overdue else 'soon'}",
        )
        if created and user.email:
            send_email(
                db, to=user.email, subject=title,
                body=f"Task \"{task.title}\" is {'overdue' if overdue else 'due within 24 hours'}.",
                category="reminder",
            )
    upcoming = db.scalars(
        select(CalendarEvent).where(
            CalendarEvent.owner_id == user.id,
            CalendarEvent.status == "scheduled",
            CalendarEvent.start_at > now,
            CalendarEvent.start_at <= now + timedelta(minutes=60),
        )
    ).all()
    for event in upcoming:
        title = f"Starting soon: {event.title}"
        body = f"{event.type.replace('_', ' ').title()} at {event.start_at:%H:%M}"
        created = notify(
            db, tenant_id=event.tenant_id, user_id=user.id,
            type=NotificationType.FOLLOW_UP,
            title=title,
            body=body,
            entity_type="calendar_event", entity_id=event.id,
            dedupe_key=f"event_soon:{event.id}",
        )
        if created and user.email:
            send_email(db, to=user.email, subject=title, body=body, category="reminder")


def run_due_reminders_for_all_users() -> None:
    """Periodic entry point for the APScheduler job — scans every active user
    across every tenant. Runs in its own session/thread (no request context).
    Commits per-user rather than once at the end: one user's failure must not
    roll back (and silently drop) reminders already staged for every other
    user in the same 5-minute sweep."""
    with SessionLocal() as db:
        users = db.scalars(select(User).where(User.is_active.is_(True))).all()
        for u in users:
            try:
                generate_due_reminders(db, u)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("generate_due_reminders failed for user_id=%s", u.id)


# ------------------------------------------------------------ event handlers
# In-process delivery joins the publisher's request session (payload["_db"]).
# Queue-based consumers won't have one and open their own session instead.


def _with_session(fn):
    def wrapper(payload: dict) -> None:
        request_db = payload.get("_db")
        if request_db is not None:
            fn(request_db, payload)
            return
        with SessionLocal() as db:
            fn(db, payload)
            db.commit()

    return wrapper


@_with_session
def _on_lead_assigned(db: Session, p: dict) -> None:
    if p.get("assigned_to") and p["assigned_to"] != p.get("assigned_by"):
        notify(
            db, tenant_id=p["tenant_id"], user_id=p["assigned_to"],
            type=NotificationType.ASSIGNMENT,
            title=f"Lead assigned to you: {p.get('lead_name', 'New lead')}",
            entity_type="lead", entity_id=p["lead_id"],
        )


@_with_session
def _on_booking_created(db: Session, p: dict) -> None:
    if p.get("assigned_to"):
        notify(
            db, tenant_id=p["tenant_id"], user_id=p["assigned_to"],
            type=NotificationType.BOOKING_UPDATE,
            title=f"Booking started for {p.get('customer_name', 'customer')}",
            entity_type="booking", entity_id=p["booking_id"],
        )


@_with_session
def _on_booking_stage(db: Session, p: dict) -> None:
    if p.get("assigned_to"):
        notify(
            db, tenant_id=p["tenant_id"], user_id=p["assigned_to"],
            type=NotificationType.BOOKING_UPDATE,
            title=f"Booking moved to {p['to'].replace('_', ' ')}",
            body=f"Customer: {p.get('customer_name', '')}",
            entity_type="booking", entity_id=p["booking_id"],
        )


@_with_session
def _on_task_assigned(db: Session, p: dict) -> None:
    if p.get("assigned_to") and p["assigned_to"] != p.get("assigned_by"):
        notify(
            db, tenant_id=p["tenant_id"], user_id=p["assigned_to"],
            type=NotificationType.TASK,
            title=f"Task assigned to you: {p.get('title', '')}",
            entity_type="task", entity_id=p["task_id"],
        )


def register_subscribers() -> None:
    events.subscribe("lead.assigned", _on_lead_assigned)
    events.subscribe("booking.created", _on_booking_created)
    events.subscribe("booking.stage_changed", _on_booking_stage)
    events.subscribe("task.assigned", _on_task_assigned)
