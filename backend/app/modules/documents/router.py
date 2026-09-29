from datetime import datetime

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.deps import get_db, require
from app.core.errors import AppError, NotFoundError
from app.core.storage import read_file, save_file
from app.modules.documents.models import DOCUMENT_CATEGORIES, Document, DocumentVersion
from app.modules.timeline.models import log_activity

router = APIRouter(prefix="/documents", tags=["documents"])


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_number: int
    filename: str
    size: int
    content_type: str | None
    uploaded_by: str | None
    note: str | None
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    category: str
    entity_type: str | None
    entity_id: str | None
    current_version: int
    versions: list[VersionOut]
    created_at: datetime
    updated_at: datetime


def _check_entity_scope(db: Session, ctx, entity_type: str | None, entity_id: str | None):
    """Documents attached to a lead/customer/booking inherit that record's scope."""
    if not entity_type or not entity_id:
        return
    if entity_type == "tenant":
        # Workspace assets (logo, brochures, AI knowledge base) belong to the
        # tenant. Nothing to inherit, but the id must be the caller's own tenant —
        # otherwise a user could file documents against someone else's workspace.
        if entity_id != ctx.user.tenant_id:
            raise NotFoundError("Workspace not found")
        return
    if entity_type == "lead":
        from app.modules.leads.service import get_lead_scoped

        get_lead_scoped(db, ctx, entity_id)
    elif entity_type == "customer":
        from app.modules.customers.service import get_customer_scoped

        get_customer_scoped(db, ctx, entity_id)
    elif entity_type == "booking":
        from app.modules.bookings.service import get_booking_scoped

        get_booking_scoped(db, ctx, entity_id)
    else:
        raise AppError(f"Unknown entity_type '{entity_type}'", code="invalid_entity_type")


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile,
    title: str = Form(min_length=2, max_length=300),
    category: str = Form(default="other"),
    entity_type: str | None = Form(default=None),
    entity_id: str | None = Form(default=None),
    ctx=Depends(require("documents", "create")),
    db: Session = Depends(get_db, scope="function"),
):
    if category not in DOCUMENT_CATEGORIES:
        category = "other"
    _check_entity_scope(db, ctx, entity_type, entity_id)
    content = await file.read()
    stored = save_file("documents", file.filename or "document", content)
    doc = Document(
        tenant_id=ctx.user.tenant_id, title=title, category=category,
        entity_type=entity_type, entity_id=entity_id, created_by=ctx.user.id,
    )
    db.add(doc)
    db.flush()
    db.add(DocumentVersion(
        document_id=doc.id, version_number=1, filename=stored["filename"],
        stored_path=stored["stored_path"], size=stored["size"],
        content_type=file.content_type, uploaded_by=ctx.user.id,
    ))
    db.flush()
    if entity_type and entity_id:
        log_activity(
            db, tenant_id=ctx.user.tenant_id, entity_type=entity_type,
            entity_id=entity_id, type="document",
            title=f"Document uploaded: {title}", actor=ctx.user,
            detail={"document_id": doc.id, "category": category},
        )
    record_audit(
        db, tenant_id=ctx.user.tenant_id, action="document.upload",
        actor_id=ctx.user.id, actor_email=ctx.user.email,
        entity_type="document", entity_id=doc.id,
    )
    db.refresh(doc)
    return {"data": DocumentOut.model_validate(doc).model_dump()}


@router.get("")
def list_documents(
    entity_type: str | None = None,
    entity_id: str | None = None,
    category: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx=Depends(require("documents", "read")),
    db: Session = Depends(get_db, scope="function"),
):
    if entity_type and entity_id:
        _check_entity_scope(db, ctx, entity_type, entity_id)
    q = select(Document).where(Document.tenant_id == ctx.user.tenant_id)
    if entity_type:
        q = q.where(Document.entity_type == entity_type)
    if entity_id:
        q = q.where(Document.entity_id == entity_id)
    if category:
        q = q.where(Document.category == category)
    from app.core.permissions import Scope

    if ctx.scope == Scope.OWN:
        q = q.where(Document.created_by == ctx.user.id)
    elif ctx.scope == Scope.TEAM:
        from app.core.deps import team_user_ids

        q = q.where(Document.created_by.in_(team_user_ids(db, ctx.user)))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(
        q.order_by(Document.updated_at.desc()).limit(limit).offset(offset)
    ).all()
    return {"data": [DocumentOut.model_validate(d).model_dump() for d in rows],
            "meta": {"total": total, "categories": DOCUMENT_CATEGORIES}}


def _get_document(db: Session, ctx, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.tenant_id != ctx.user.tenant_id:
        raise NotFoundError("Document not found")
    from app.core.permissions import Scope

    if ctx.scope == Scope.OWN and doc.created_by != ctx.user.id:
        raise NotFoundError("Document not found")
    return doc


@router.get("/{document_id}")
def get_document(
    document_id: str, ctx=Depends(require("documents", "read")),
    db: Session = Depends(get_db, scope="function"),
):
    doc = _get_document(db, ctx, document_id)
    return {"data": DocumentOut.model_validate(doc).model_dump()}


@router.post("/{document_id}/version", status_code=status.HTTP_201_CREATED)
async def add_version(
    document_id: str,
    file: UploadFile,
    note: str | None = Form(default=None),
    ctx=Depends(require("documents", "update")),
    db: Session = Depends(get_db, scope="function"),
):
    doc = _get_document(db, ctx, document_id)
    content = await file.read()
    stored = save_file("documents", file.filename or "document", content)
    doc.current_version += 1
    db.add(DocumentVersion(
        document_id=doc.id, version_number=doc.current_version,
        filename=stored["filename"], stored_path=stored["stored_path"],
        size=stored["size"], content_type=file.content_type,
        uploaded_by=ctx.user.id, note=note,
    ))
    db.flush()
    db.refresh(doc)
    record_audit(
        db, tenant_id=ctx.user.tenant_id, action="document.new_version",
        actor_id=ctx.user.id, actor_email=ctx.user.email,
        entity_type="document", entity_id=doc.id,
        detail={"version": doc.current_version},
    )
    return {"data": DocumentOut.model_validate(doc).model_dump()}


@router.get("/{document_id}/download")
def download(
    document_id: str,
    version: int | None = None,
    ctx=Depends(require("documents", "read")),
    db: Session = Depends(get_db, scope="function"),
):
    doc = _get_document(db, ctx, document_id)
    wanted = version or doc.current_version
    row = next((v for v in doc.versions if v.version_number == wanted), None)
    if row is None:
        raise NotFoundError(f"Version {wanted} not found")
    content = read_file(row.stored_path)
    return Response(
        content=content,
        media_type=row.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row.filename}"'},
    )
