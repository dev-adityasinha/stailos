from datetime import datetime

from fastapi import APIRouter, Body, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require
from app.modules.ai import service
from app.modules.ai.models import AIInsight
from app.modules.timeline.models import ACTIVITY_TYPES, Activity

router = APIRouter(prefix="/ai", tags=["ai"])
timeline_router = APIRouter(prefix="/timeline", tags=["ai"])


class InsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_type: str
    entity_id: str
    agent_name: str
    provider: str
    payload: dict
    created_at: datetime


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    lead_id: str | None = None
    conversation_history: list[dict[str, str]] = Field(default_factory=list, max_length=40)


@router.get("/catalog")
def catalog(
    response: Response,
    ctx=Depends(require("ai", "read")),
    db: Session = Depends(get_db, scope="function"),
):
    """What this workspace can actually run — not just what the code implements.

    `widgets`/`components` list only what the tenant's onboarding answers allow,
    so a UI that hides disabled actions and the server that refuses them agree.
    `all_*` keeps the full catalogue visible for admins wondering what they turned
    off.
    """
    from app.modules.ai.provider import get_provider
    from app.modules.ai import tenant_config

    # This response decides which AI actions the UI offers. A browser that
    # heuristically caches it (Safari/WebKit does, absent an explicit header)
    # keeps showing actions an admin has just switched off, and the user gets a
    # 403 on click. Policy answers must never come from cache.
    response.headers["Cache-Control"] = "no-store"

    policy = tenant_config.load_policy(db, ctx.user.tenant_id)
    allowed = {
        name: agent for name, agent in
        [*service.WIDGETS.items(), *service.COMPONENTS.items()]
        if policy["ai_consent"] and tenant_config.is_agent_enabled(policy, agent)
    }
    return {"data": {
        "widgets": sorted(w for w in service.WIDGETS if w in allowed),
        "components": sorted(c for c in service.COMPONENTS if c in allowed),
        "all_widgets": sorted(service.WIDGETS),
        "all_components": sorted(service.COMPONENTS),
        "provider": get_provider().name,
        "ai_consent": policy["ai_consent"],
        "selected_features": policy["selected_features"],
        "pipeline": ["buyer_assistant", "property_recommendation",
                     "crm_sync", "lead_qualification"],
    }}


@router.post("/chat")
def chat(
    body: ChatRequest,
    ctx=Depends(require("ai", "create")),
    db: Session = Depends(get_db, scope="function"),
):
    """One conversational turn: extract requirements and reply with the gap."""
    return {"data": service.chat(
        db, ctx, message=body.message, lead_id=body.lead_id,
        history=body.conversation_history,
    )}


@router.post("/orchestrate")
def orchestrate(
    body: ChatRequest,
    ctx=Depends(require("ai", "create")),
    db: Session = Depends(get_db, scope="function"),
):
    """Run the full pipeline: extract → match inventory → grade → write back."""
    return {"data": service.orchestrate(db, ctx, message=body.message, lead_id=body.lead_id)}


@router.post("/widgets/{widget}")
def run_widget(
    widget: str,
    body: dict = Body(default={}),
    ctx=Depends(require("ai", "create")),
    db: Session = Depends(get_db, scope="function"),
):
    return {"data": service.run_widget(db, ctx, widget, body)}


@router.post("/components/{component}")
def run_component(
    component: str,
    body: dict = Body(default={}),
    ctx=Depends(require("ai", "create")),
    db: Session = Depends(get_db, scope="function"),
):
    return {"data": service.run_component(db, ctx, component, body)}


@router.get("/insights/{entity_type}/{entity_id}")
def insights(
    entity_type: str,
    entity_id: str,
    ctx=Depends(require("ai", "read")),
    db: Session = Depends(get_db, scope="function"),
):
    rows = service.list_insights(db, ctx, entity_type, entity_id)
    return {"data": [InsightOut.model_validate(i).model_dump() for i in rows]}


@timeline_router.get("/{entity_type}/{entity_id}")
def entity_timeline(
    entity_type: str,
    entity_id: str,
    types: str | None = Query(default=None, description="comma-separated activity types"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx=Depends(require("ai", "read")),
    db: Session = Depends(get_db, scope="function"),
):
    """Timeline intelligence (Task 15): chronological events with type filtering.
    Scope enforcement mirrors the entity's own module."""
    from app.modules.leads.schemas import ActivityOut

    if entity_type == "lead":
        from app.modules.leads.service import get_lead_scoped

        get_lead_scoped(db, ctx, entity_id)
    elif entity_type == "customer":
        from app.modules.customers.service import get_customer_scoped

        get_customer_scoped(db, ctx, entity_id)

    q = select(Activity).where(
        Activity.tenant_id == ctx.user.tenant_id,
        Activity.entity_type == entity_type,
        Activity.entity_id == entity_id,
    )
    if types:
        wanted = [t.strip() for t in types.split(",") if t.strip() in ACTIVITY_TYPES]
        if wanted:
            q = q.where(Activity.type.in_(wanted))
    rows = db.scalars(
        q.order_by(Activity.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {"data": [ActivityOut.model_validate(a).model_dump() for a in rows],
            "meta": {"available_types": sorted(ACTIVITY_TYPES)}}
