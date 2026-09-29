import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import events
from app.core.deps import get_db, require, team_user_ids
from app.core.errors import NotFoundError
from app.core.permissions import Scope
from app.core.storage import save_file
from app.db.base import utcnow
from app.modules.auth.models import User
from app.modules.leads.schemas import UserBrief
from app.modules.tasks.models import (
    CrmTask,
    TaskAttachment,
    TaskComment,
    TaskPriority,
    TaskStatus,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _naive_utc(dt: datetime | None) -> datetime | None:
    """Store naive UTC: convert aware datetimes to UTC before stripping tzinfo."""
    if dt is None:
        return None
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    assigned_to: str | None = None
    due_date: datetime | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    entity_type: str | None = Field(default=None, max_length=30)
    entity_id: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    assigned_to: str | None = None
    due_date: datetime | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    author_id: str | None
    author_name: str | None
    body: str
    created_at: datetime


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    size: int
    content_type: str | None
    created_at: datetime


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    description: str | None
    assigned_to: str | None
    assignee: UserBrief | None
    created_by: str | None
    due_date: datetime | None
    priority: TaskPriority
    status: TaskStatus
    entity_type: str | None
    entity_id: str | None
    completed_at: datetime | None
    comments: list[CommentOut]
    attachments: list[AttachmentOut]
    created_at: datetime
    updated_at: datetime


def _scoped(db: Session, ctx):
    q = select(CrmTask).where(
        CrmTask.tenant_id == ctx.user.tenant_id, CrmTask.deleted_at.is_(None)
    )
    if ctx.scope == Scope.TEAM:
        ids = team_user_ids(db, ctx.user)
        q = q.where(or_(CrmTask.assigned_to.in_(ids), CrmTask.created_by.in_(ids)))
    elif ctx.scope == Scope.OWN:
        q = q.where(
            or_(CrmTask.assigned_to == ctx.user.id, CrmTask.created_by == ctx.user.id)
        )
    return q


def _get(db: Session, ctx, task_id: str) -> CrmTask:
    task = db.scalars(_scoped(db, ctx).where(CrmTask.id == task_id)).first()
    if task is None:
        raise NotFoundError("Task not found")
    return task


def _valid_assignee(db: Session, ctx, user_id: str | None) -> str | None:
    """A client-supplied assignee must belong to the caller's own tenant —
    same posture as leads.service.create_lead's equivalent check. Returns
    None (falls back to the caller) rather than 404ing on a bad hint."""
    if not user_id:
        return None
    target = db.get(User, user_id)
    if target is None or not target.is_active or target.tenant_id != ctx.user.tenant_id:
        return None
    return target.id


@router.get("")
def list_tasks(
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = None,
    assigned_to: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    overdue: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx=Depends(require("tasks", "read")),
    db: Session = Depends(get_db, scope="function"),
):
    q = _scoped(db, ctx)
    if status_filter:
        q = q.where(CrmTask.status == status_filter.value)
    if priority:
        q = q.where(CrmTask.priority == priority.value)
    if assigned_to:
        q = q.where(CrmTask.assigned_to == assigned_to)
    if entity_type and entity_id:
        q = q.where(CrmTask.entity_type == entity_type, CrmTask.entity_id == entity_id)
    if overdue:
        q = q.where(
            CrmTask.due_date < utcnow().replace(tzinfo=None),
            CrmTask.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
        )
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(
        q.order_by(CrmTask.due_date.is_(None), CrmTask.due_date, CrmTask.created_at.desc())
        .limit(limit).offset(offset)
    ).all()
    return {
        "data": [TaskOut.model_validate(t).model_dump() for t in rows],
        "meta": {"total": total, "limit": limit, "offset": offset,
                 "pages": math.ceil((total or 0) / limit)},
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(
    body: TaskCreate, ctx=Depends(require("tasks", "create")), db: Session = Depends(get_db, scope="function")
):
    task = CrmTask(
        tenant_id=ctx.user.tenant_id,
        created_by=ctx.user.id,
        assigned_to=_valid_assignee(db, ctx, body.assigned_to) or ctx.user.id,
        title=body.title,
        description=body.description,
        due_date=_naive_utc(body.due_date),
        priority=body.priority.value,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )
    db.add(task)
    db.flush()
    events.publish(
        "task.assigned",
        {"task_id": task.id, "tenant_id": task.tenant_id, "assigned_to": task.assigned_to,
         "assigned_by": ctx.user.id, "title": task.title}, db=db,
    )
    return {"data": TaskOut.model_validate(task).model_dump()}


@router.get("/{task_id}")
def get_task(task_id: str, ctx=Depends(require("tasks", "read")), db: Session = Depends(get_db, scope="function")):
    return {"data": TaskOut.model_validate(_get(db, ctx, task_id)).model_dump()}


@router.patch("/{task_id}")
def update_task(
    task_id: str,
    body: TaskUpdate,
    ctx=Depends(require("tasks", "update")),
    db: Session = Depends(get_db, scope="function"),
):
    task = _get(db, ctx, task_id)
    changes = body.model_dump(exclude_unset=True)
    old_assignee = task.assigned_to
    if changes.get("assigned_to"):
        # Invalid/cross-tenant assignee: leave the field untouched rather
        # than nulling it out (which would silently unassign the task). An
        # explicit `assigned_to: null` (falsy) is a legitimate unassign and
        # passes through unchanged below.
        valid = _valid_assignee(db, ctx, changes["assigned_to"])
        if valid is None:
            del changes["assigned_to"]
        else:
            changes["assigned_to"] = valid
    for field, value in changes.items():
        if field in ("priority", "status") and value is not None:
            value = value.value
        if field == "due_date" and value is not None:
            value = _naive_utc(value)
        setattr(task, field, value)
    if task.status == TaskStatus.DONE.value and task.completed_at is None:
        task.completed_at = utcnow().replace(tzinfo=None)
    if "assigned_to" in changes and task.assigned_to != old_assignee:
        events.publish(
            "task.assigned",
            {"task_id": task.id, "tenant_id": task.tenant_id,
             "assigned_to": task.assigned_to, "assigned_by": ctx.user.id,
             "title": task.title}, db=db,
    )
    return {"data": TaskOut.model_validate(task).model_dump()}


@router.delete("/{task_id}")
def delete_task(
    task_id: str, ctx=Depends(require("tasks", "delete")), db: Session = Depends(get_db, scope="function")
):
    task = _get(db, ctx, task_id)
    task.deleted_at = utcnow().replace(tzinfo=None)
    return {"data": {"message": "Task deleted"}}


@router.post("/{task_id}/comments", status_code=status.HTTP_201_CREATED)
def add_comment(
    task_id: str,
    body: CommentCreate,
    ctx=Depends(require("tasks", "update")),
    db: Session = Depends(get_db, scope="function"),
):
    task = _get(db, ctx, task_id)
    comment = TaskComment(
        task_id=task.id, author_id=ctx.user.id, author_name=ctx.user.full_name,
        body=body.body,
    )
    db.add(comment)
    db.flush()
    return {"data": CommentOut.model_validate(comment).model_dump()}


@router.post("/{task_id}/attachments", status_code=status.HTTP_201_CREATED)
async def add_attachment(
    task_id: str,
    file: UploadFile,
    ctx=Depends(require("tasks", "update")),
    db: Session = Depends(get_db, scope="function"),
):
    task = _get(db, ctx, task_id)
    content = await file.read()
    stored = save_file("task_attachments", file.filename or "file", content)
    attachment = TaskAttachment(
        task_id=task.id, filename=stored["filename"], stored_path=stored["stored_path"],
        size=stored["size"], content_type=file.content_type, uploaded_by=ctx.user.id,
    )
    db.add(attachment)
    db.flush()
    return {"data": AttachmentOut.model_validate(attachment).model_dump()}
