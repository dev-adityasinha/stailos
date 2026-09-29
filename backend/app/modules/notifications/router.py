from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.notifications.models import Notification
from app.modules.notifications.service import generate_due_reminders

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    title: str
    body: str | None
    entity_type: str | None
    entity_id: str | None
    read: bool
    created_at: datetime


@router.get("")
def list_notifications(
    unread: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    generate_due_reminders(db, user)  # lazy follow-up reminder generation
    db.flush()  # autoflush is off; make fresh reminders visible to this query
    q = select(Notification).where(Notification.user_id == user.id)
    if unread:
        q = q.where(Notification.read.is_(False))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    unread_count = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id, Notification.read.is_(False)
        )
    )
    rows = db.scalars(
        q.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "data": [NotificationOut.model_validate(n).model_dump() for n in rows],
        "meta": {"total": total, "unread": unread_count, "limit": limit, "offset": offset},
    }


@router.patch("/{notification_id}/read")
def mark_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise NotFoundError("Notification not found")
    n.read = True
    return {"data": NotificationOut.model_validate(n).model_dump()}


@router.post("/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id, Notification.read.is_(False)
        )
    ).all()
    for n in rows:
        n.read = True
    return {"data": {"marked": len(rows)}}
