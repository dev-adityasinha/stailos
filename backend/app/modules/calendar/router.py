from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require, team_user_ids
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import Scope
from app.modules.calendar.models import CalendarEvent, EventType, event_attendees
from app.modules.leads.schemas import UserBrief

router = APIRouter(prefix="/calendar", tags=["calendar"])


class EventCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    type: EventType = EventType.MEETING
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=300)
    start_at: datetime
    end_at: datetime | None = None
    all_day: bool = False
    attendee_ids: list[str] = []
    entity_type: str | None = Field(default=None, max_length=30)
    entity_id: str | None = None

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end_at and self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    type: EventType | None = None
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=300)
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    status: str | None = Field(default=None, pattern="^(scheduled|done|cancelled)$")
    attendee_ids: list[str] | None = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    type: EventType
    description: str | None
    location: str | None
    start_at: datetime
    end_at: datetime | None
    all_day: bool
    owner_id: str
    owner: UserBrief
    attendees: list[UserBrief]
    entity_type: str | None
    entity_id: str | None
    status: str
    created_at: datetime


def _naive(dt: datetime | None) -> datetime | None:
    """Store naive UTC: convert aware datetimes to UTC before stripping tzinfo."""
    if dt is None:
        return None
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _visible_query(db: Session, ctx):
    q = select(CalendarEvent).where(CalendarEvent.tenant_id == ctx.user.tenant_id)
    attending = select(event_attendees.c.event_id).where(
        event_attendees.c.user_id == ctx.user.id
    )
    if ctx.scope == Scope.TEAM:
        ids = team_user_ids(db, ctx.user)
        q = q.where(
            or_(CalendarEvent.owner_id.in_(ids), CalendarEvent.id.in_(attending))
        )
    elif ctx.scope == Scope.OWN:
        q = q.where(
            or_(CalendarEvent.owner_id == ctx.user.id, CalendarEvent.id.in_(attending))
        )
    return q


@router.get("")
def list_events(
    start: datetime | None = None,
    end: datetime | None = None,
    type_filter: EventType | None = Query(default=None, alias="type"),
    team: bool = False,
    ctx=Depends(require("calendar", "read")),
    db: Session = Depends(get_db, scope="function"),
):
    q = _visible_query(db, ctx)
    if not team:  # personal view: only own/attending regardless of role scope
        attending = select(event_attendees.c.event_id).where(
            event_attendees.c.user_id == ctx.user.id
        )
        q = q.where(
            or_(CalendarEvent.owner_id == ctx.user.id, CalendarEvent.id.in_(attending))
        )
    if start:
        q = q.where(CalendarEvent.start_at >= _naive(start))
    if end:
        q = q.where(CalendarEvent.start_at <= _naive(end))
    if type_filter:
        q = q.where(CalendarEvent.type == type_filter.value)
    rows = db.scalars(q.order_by(CalendarEvent.start_at)).all()
    return {"data": [EventOut.model_validate(e).model_dump() for e in rows],
            "meta": {"total": len(rows)}}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventCreate, ctx=Depends(require("calendar", "create")),
    db: Session = Depends(get_db, scope="function"),
):
    from app.modules.auth.models import User

    event = CalendarEvent(
        tenant_id=ctx.user.tenant_id,
        owner_id=ctx.user.id,
        title=body.title,
        type=body.type.value,
        description=body.description,
        location=body.location,
        start_at=_naive(body.start_at),
        end_at=_naive(body.end_at),
        all_day=body.all_day,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )
    for uid in body.attendee_ids:
        attendee = db.get(User, uid)
        if attendee and attendee.tenant_id == ctx.user.tenant_id:
            event.attendees.append(attendee)
    db.add(event)
    db.flush()
    return {"data": EventOut.model_validate(event).model_dump()}


def _get_editable(db: Session, ctx, event_id: str) -> CalendarEvent:
    event = db.scalars(
        _visible_query(db, ctx).where(CalendarEvent.id == event_id)
    ).first()
    if event is None:
        raise NotFoundError("Event not found")
    if event.owner_id != ctx.user.id and ctx.scope not in (Scope.ALL, Scope.TEAM):
        raise PermissionDeniedError("Only the owner can modify this event")
    return event


@router.patch("/{event_id}")
def update_event(
    event_id: str,
    body: EventUpdate,
    ctx=Depends(require("calendar", "update")),
    db: Session = Depends(get_db, scope="function"),
):
    from app.modules.auth.models import User

    event = _get_editable(db, ctx, event_id)
    changes = body.model_dump(exclude_unset=True)
    attendee_ids = changes.pop("attendee_ids", None)
    for field, value in changes.items():
        if field == "type" and value is not None:
            value = value.value
        if field in ("start_at", "end_at"):
            value = _naive(value)
        setattr(event, field, value)
    if event.end_at and event.end_at <= event.start_at:
        from app.core.errors import AppError

        raise AppError("end_at must be after start_at", code="invalid_range")
    if attendee_ids is not None:
        event.attendees = [
            u for uid in attendee_ids
            if (u := db.get(User, uid)) and u.tenant_id == ctx.user.tenant_id
        ]
    return {"data": EventOut.model_validate(event).model_dump()}


@router.delete("/{event_id}")
def delete_event(
    event_id: str, ctx=Depends(require("calendar", "delete")), db: Session = Depends(get_db, scope="function")
):
    event = _get_editable(db, ctx, event_id)
    db.delete(event)
    return {"data": {"message": "Event deleted"}}
