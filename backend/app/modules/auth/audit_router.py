from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import AuditLog
from app.core.deps import get_db, require

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor_id: str | None
    actor_email: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    detail: dict | None
    ip_address: str | None
    created_at: datetime


@router.get("")
def list_audit(
    action: str | None = None,
    actor_email: str | None = None,
    entity_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx=Depends(require("audit", "read")),  # only admin roles hold audit:read
    db: Session = Depends(get_db, scope="function"),
):
    q = select(AuditLog).where(AuditLog.tenant_id == ctx.user.tenant_id)
    if action:
        q = q.where(AuditLog.action == action)
    if actor_email:
        q = q.where(AuditLog.actor_email == actor_email)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(
        q.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {"data": [AuditOut.model_validate(a).model_dump() for a in rows],
            "meta": {"total": total, "limit": limit, "offset": offset}}
