import math

from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require
from app.core.errors import AppError
from app.core.search import like_pattern
from app.modules.leads import service
from app.modules.leads.models import Lead, LeadStage
from app.modules.leads.schemas import (
    ActivityOut,
    AssignRequest,
    DuplicateCheckRequest,
    DuplicateMatch,
    LeadCreate,
    LeadDetailOut,
    LeadOut,
    LeadUpdate,
    LeadStageEventOut,
    NoteCreate,
    NoteOut,
    ScheduleSiteVisitRequest,
    StageChangeRequest,
    TagRequest,
)

router = APIRouter(prefix="/leads", tags=["leads"])
pipeline_router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("")
def list_leads(
    stage: LeadStage | None = None,
    source: str | None = None,
    assigned_to: str | None = None,
    score_band: str | None = None,
    q: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx=Depends(require("leads", "read")),
    db: Session = Depends(get_db),
):
    query = service.scoped_query(db, ctx)
    if stage:
        query = query.where(Lead.stage == stage.value)
    if source:
        query = query.where(Lead.source == source)
    if assigned_to:
        query = query.where(Lead.assigned_to == assigned_to)
    if score_band:
        query = query.where(Lead.score_band == score_band)
    if q:
        like = like_pattern(q)
        query = query.where(
            or_(
                Lead.full_name.ilike(like, escape="\\"),
                Lead.email.ilike(like, escape="\\"),
                Lead.phone.ilike(like, escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Lead.updated_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "data": [LeadOut.model_validate(r).model_dump() for r in rows],
        "meta": {"total": total, "limit": limit, "offset": offset,
                 "pages": math.ceil((total or 0) / limit)},
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_lead(
    body: LeadCreate, ctx=Depends(require("leads", "create")), db: Session = Depends(get_db)
):
    data = body.model_dump(exclude={"force"})
    lead = service.create_lead(db, ctx, data, force=body.force)
    return {"data": LeadOut.model_validate(lead).model_dump()}


@router.post("/check-duplicates")
def check_duplicates(
    body: DuplicateCheckRequest,
    ctx=Depends(require("leads", "read")),
    db: Session = Depends(get_db),
):
    matches = service.find_duplicates(
        db, ctx.user.tenant_id, phone=body.phone, email=body.email, full_name=body.full_name
    )
    return {"data": [DuplicateMatch(**m).model_dump() for m in matches]}


@router.post("/import")
async def import_leads(
    file: UploadFile, ctx=Depends(require("leads", "create")), db: Session = Depends(get_db)
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise AppError("Only .csv files are supported", code="unsupported_file")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise AppError("File exceeds 10 MB limit", code="file_too_large")
    batch = service.import_csv(db, ctx, filename=file.filename or "upload.csv", content=content)
    return {
        "data": {
            "batch_id": batch.id,
            "total_rows": batch.total_rows,
            "imported": batch.imported,
            "skipped_duplicates": batch.skipped_duplicates,
            "errors": batch.errors,
        }
    }


@router.get("/export")
def export_leads(ctx=Depends(require("leads", "export")), db: Session = Depends(get_db)):
    csv_text = service.export_csv(db, ctx)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )


@router.get("/{lead_id}")
def get_lead(lead_id: str, ctx=Depends(require("leads", "read")), db: Session = Depends(get_db)):
    lead = service.get_lead_scoped(db, ctx, lead_id)
    return {"data": LeadDetailOut.model_validate(lead).model_dump()}


@router.patch("/{lead_id}")
def update_lead(
    lead_id: str,
    body: LeadUpdate,
    ctx=Depends(require("leads", "update")),
    db: Session = Depends(get_db),
):
    lead = service.update_lead(db, ctx, lead_id, body.model_dump(exclude_unset=True))
    return {"data": LeadOut.model_validate(lead).model_dump()}


@router.delete("/{lead_id}")
def delete_lead(
    lead_id: str, ctx=Depends(require("leads", "delete")), db: Session = Depends(get_db)
):
    service.delete_lead(db, ctx, lead_id)
    return {"data": {"message": "Lead deleted"}}


@router.post("/{lead_id}/assign")
def assign_lead(
    lead_id: str,
    body: AssignRequest,
    ctx=Depends(require("leads", "assign")),
    db: Session = Depends(get_db),
):
    lead = service.assign_lead(db, ctx, lead_id, body.user_id)
    return {"data": LeadOut.model_validate(lead).model_dump()}


@router.post("/{lead_id}/notes", status_code=status.HTTP_201_CREATED)
def add_note(
    lead_id: str,
    body: NoteCreate,
    ctx=Depends(require("leads", "update")),
    db: Session = Depends(get_db),
):
    note = service.add_note(db, ctx, lead_id, body.body)
    return {"data": NoteOut.model_validate(note).model_dump()}


@router.post("/{lead_id}/tags")
def add_tag(
    lead_id: str,
    body: TagRequest,
    ctx=Depends(require("leads", "update")),
    db: Session = Depends(get_db),
):
    lead = service.add_tag(db, ctx, lead_id, body.name, body.color)
    return {"data": LeadOut.model_validate(lead).model_dump()}


@router.delete("/{lead_id}/tags/{tag_id}")
def remove_tag(
    lead_id: str,
    tag_id: str,
    ctx=Depends(require("leads", "update")),
    db: Session = Depends(get_db),
):
    lead = service.remove_tag(db, ctx, lead_id, tag_id)
    return {"data": LeadOut.model_validate(lead).model_dump()}


@router.get("/{lead_id}/timeline")
def lead_timeline(
    lead_id: str, ctx=Depends(require("leads", "read")), db: Session = Depends(get_db)
):
    rows = service.get_timeline(db, ctx, lead_id)
    return {"data": [ActivityOut.model_validate(a).model_dump() for a in rows]}


@router.post("/{lead_id}/schedule-site-visit", status_code=status.HTTP_201_CREATED)
def schedule_site_visit(
    lead_id: str,
    body: ScheduleSiteVisitRequest,
    ctx=Depends(require("leads", "update")),
    db: Session = Depends(get_db),
):
    from app.modules.calendar.router import EventOut

    lead, event = service.schedule_site_visit(
        db, ctx, lead_id,
        start_at=body.start_at, end_at=body.end_at,
        location=body.location, attendee_ids=body.attendee_ids,
    )
    return {
        "data": {
            "lead": LeadOut.model_validate(lead).model_dump(),
            "event": EventOut.model_validate(event).model_dump(),
        }
    }


# ------------------------------------------------------------------ pipeline


@pipeline_router.get("/board")
def board(ctx=Depends(require("leads", "read")), db: Session = Depends(get_db)):
    columns = service.pipeline_board(db, ctx)
    return {
        "data": {
            stage: [LeadOut.model_validate(lead).model_dump() for lead in leads]
            for stage, leads in columns.items()
        },
        "meta": {"stage_order": [s.value for s in LeadStage]},
    }


@pipeline_router.patch("/leads/{lead_id}/stage")
def move_stage(
    lead_id: str,
    body: StageChangeRequest,
    ctx=Depends(require("leads", "update")),
    db: Session = Depends(get_db),
):
    lead = service.change_stage(
        db, ctx, lead_id, body.stage, body.lost_reason, reopen=body.reopen
    )
    return {"data": LeadOut.model_validate(lead).model_dump()}


@pipeline_router.get("/leads/{lead_id}/stage-history")
def stage_history(
    lead_id: str, ctx=Depends(require("leads", "read")), db: Session = Depends(get_db)
):
    rows = service.get_stage_history(db, ctx, lead_id)
    return {"data": [LeadStageEventOut.model_validate(r).model_dump() for r in rows]}
