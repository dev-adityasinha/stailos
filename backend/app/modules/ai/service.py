"""AI service: assembles scoped CRM context, invokes the provider, persists
insights, and applies side effects (e.g. lead score updates)."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import AccessContext
from app.core.errors import AppError
from app.modules.ai import grading, ranking, tenant_config
from app.modules.ai.models import AIInsight
from app.modules.ai.provider import get_provider
from app.modules.auth.models import Tenant
from app.modules.bookings.models import Booking
from app.modules.customers.service import get_customer_scoped
from app.modules.leads.service import get_lead_scoped
from app.modules.properties.models import (
    CustomerProperty,
    PropertyProject,
    PropertyUnit,
    UnitStatus,
)
from app.modules.properties.service import provider as property_provider
from app.modules.timeline.models import Activity, log_activity

WIDGETS = {
    "lead-summary": "lead_summary",
    "customer-summary": "customer_summary",
    "suggestions": "suggestions",
    "next-best-action": "next_best_action",
    "investment-insights": "investment_insights",
    "sales-tips": "sales_tips",
    "property-recommendations": "property_recommendations",
}

COMPONENTS = {
    "lead-qualification": "lead_qualification",
    "buyer-assistant": "buyer_assistant",
    "property-recommendation": "property_recommendation",
    "follow-up": "follow_up",
    "email-generator": "email_generator",
    "whatsapp-assistant": "whatsapp_assistant",
    "call-summary": "call_summary",
    "customer-insights": "customer_insights",
}


def _lead_ctx(db: Session, ctx: AccessContext, lead_id: str) -> dict:
    lead = get_lead_scoped(db, ctx, lead_id)
    activities = db.scalars(
        select(Activity)
        .where(Activity.entity_type == "lead", Activity.entity_id == lead.id)
        .order_by(Activity.created_at.desc())
        .limit(20)
    ).all()
    days_since_update = (
        datetime.now(timezone.utc).replace(tzinfo=None) - lead.updated_at
    ).days
    return {
        "lead": {
            "id": lead.id, "full_name": lead.full_name, "email": lead.email,
            "phone": lead.phone, "source": lead.source, "stage": lead.stage,
            "budget_min": float(lead.budget_min) if lead.budget_min else None,
            "budget_max": float(lead.budget_max) if lead.budget_max else None,
            "location_preference": lead.location_preference,
            "property_type": lead.property_type,
            "requirements": lead.requirements,
        },
        "activities": [
            {"type": a.type, "title": a.title, "at": a.created_at.isoformat()}
            for a in activities
        ],
        "notes_count": len(lead.notes),
        "days_since_update": days_since_update,
        "entity_id": lead.id,
        "_lead_obj": lead,
    }


def _customer_ctx(db: Session, ctx: AccessContext, customer_id: str) -> dict:
    customer = get_customer_scoped(db, ctx, customer_id)
    bookings = db.scalars(select(Booking).where(Booking.customer_id == customer.id)).all()
    links = db.scalars(
        select(CustomerProperty).where(CustomerProperty.customer_id == customer.id)
    ).all()
    activities = db.scalars(
        select(Activity)
        .where(Activity.entity_type == "customer", Activity.entity_id == customer.id)
        .order_by(Activity.created_at.desc())
        .limit(50)
    ).all()
    return {
        "customer": {
            "id": customer.id, "full_name": customer.full_name, "email": customer.email,
            "phone": customer.phone, "city": customer.city,
            "occupation": customer.occupation, "company": customer.company,
            "budget_min": float(customer.budget_min) if customer.budget_min else None,
            "budget_max": float(customer.budget_max) if customer.budget_max else None,
            "family_info": customer.family_info,
            "preferences": customer.preferences,
        },
        "bookings": [{"id": b.id, "stage": b.stage, "status": b.status} for b in bookings],
        "shortlist_count": sum(1 for l in links if l.relation == "shortlisted"),
        "activities": [
            {"type": a.type, "title": a.title, "at": a.created_at.isoformat()}
            for a in activities
        ],
        "entity_id": customer.id,
        "_customer_obj": customer,
    }


def _available_units(db: Session, tenant_id: str) -> list[dict]:
    """Live inventory flattened into the plain dicts the ranker consumes."""
    units = property_provider.search_units(
        db, tenant_id, {"status": UnitStatus.AVAILABLE.value}
    )
    return [
        {
            "unit_id": unit.id,
            "project": unit.project.name,
            "project_status": unit.project.status,
            "unit_number": unit.unit_number,
            "unit_type": unit.unit_type,
            "price": float(unit.price) if unit.price is not None else None,
            "location": unit.project.location,
            "city": unit.project.city,
            "carpet_area_sqft": (
                float(unit.carpet_area_sqft) if unit.carpet_area_sqft is not None else None
            ),
            "amenities": unit.project.amenities or [],
            "created_at": unit.created_at,
        }
        for unit in units
    ]


def _recommend_units(
    db: Session, tenant_id: str, *, budget_min, budget_max, property_type, location,
    purpose=None, limit: int = 5,
) -> list[dict]:
    """Composite-scored recommender over live inventory (see `ranking.py`)."""
    return ranking.rank_units(
        _available_units(db, tenant_id),
        {
            "budget_min": budget_min, "budget_max": budget_max,
            "property_type": property_type, "location": location, "purpose": purpose,
        },
        limit=limit,
    )


def _inventory_summary(db: Session, tenant_id: str) -> dict:
    """Aggregate facts about live inventory, computed in the database.

    Every AI request needs these (the price band and stocked configurations feed
    lead grading; the cities and localities feed geography scoring and free-text
    location extraction). Deriving them by loading every available unit into
    Python — as this first did — means a builder with thousands of units pays a
    full table scan for each click of "Summarize". Five aggregates over an
    indexed status column cost the same at any inventory size.
    """
    from sqlalchemy import distinct

    price_row = db.execute(
        select(
            func.count(PropertyUnit.id),
            func.min(PropertyUnit.price),
            func.max(PropertyUnit.price),
        )
        .select_from(PropertyUnit)
        .join(PropertyProject)
        .where(
            PropertyProject.tenant_id == tenant_id,
            PropertyUnit.status == UnitStatus.AVAILABLE.value,
        )
    ).one()

    def _distinct(column) -> list[str]:
        rows = db.scalars(
            select(distinct(column))
            .select_from(PropertyUnit)
            .join(PropertyProject)
            .where(
                PropertyProject.tenant_id == tenant_id,
                PropertyUnit.status == UnitStatus.AVAILABLE.value,
                column.is_not(None),
                column != "",
            )
        ).all()
        return sorted(str(r) for r in rows)

    return {
        "unit_count": price_row[0] or 0,
        "min_price": float(price_row[1]) if price_row[1] is not None else None,
        "max_price": float(price_row[2]) if price_row[2] is not None else None,
        "unit_types": _distinct(PropertyUnit.unit_type),
        "cities": _distinct(PropertyProject.city),
        # Localities let free-text extraction recognise "Whitefield" without a
        # hardcoded gazetteer — it only has to know where this builder sells.
        "localities": _distinct(PropertyProject.location),
    }


def _tenant_ctx(db: Session, tenant_id: str) -> dict:
    """Tenant-level facts the scoring engines need: what you sell, where, and
    the rubric the admin configured during onboarding.

    Without this, every workspace would be graded against one hardcoded rubric
    and the onboarding forms would be decoration. The ICP and company profile
    are also handed to the LLM so its narrative knows who this builder is.
    """
    tenant = db.get(Tenant, tenant_id)
    onboarding = (tenant.onboarding_data if tenant else None) or {}

    inventory = _inventory_summary(db, tenant_id)

    company = onboarding.get("1") or {}
    presence = onboarding.get("1c") or {}
    icp = onboarding.get("4") or {}
    # Operating cities: what the admin declared, plus wherever inventory actually
    # is — a project in a city they forgot to list is still their footprint.
    declared = presence.get("cities") or icp.get("preferredCities") or []
    if isinstance(declared, str):
        declared = [c.strip() for c in declared.split(",") if c.strip()]
    head_office = company.get("headOffice") or company.get("headquartersCity")
    # Localities count as footprint too. A buyer who names the exact locality of a
    # live project ("Whitefield") was being scored as outside the footprint,
    # because only city names were compared — the most on-target lead possible
    # scored worse than one who vaguely said "Bengaluru".
    operating_cities = sorted(
        {c for c in [*declared, *inventory["cities"], *inventory["localities"],
                     head_office] if c}
    )

    return {
        "inventory": inventory,
        "operating_cities": operating_cities,
        "scoring_config": grading.resolve_config(onboarding),
        "company": {
            "name": tenant.name if tenant else None,
            "brand": company.get("brandName"),
            "rera": company.get("rera"),
            "business_types": presence.get("businessTypes") or [],
            "property_types": presence.get("propertyTypes") or [],
        },
        "icp": icp,
    }


def run_widget(db: Session, ctx: AccessContext, widget: str, body: dict) -> dict:
    if widget not in WIDGETS:
        raise AppError(f"Unknown widget '{widget}'", code="unknown_widget", status_code=404)
    agent = WIDGETS[widget]
    tenant_config.enforce(tenant_config.load_policy(db, ctx.user.tenant_id), agent)
    lead_id, customer_id = body.get("lead_id"), body.get("customer_id")

    if agent in ("lead_summary", "suggestions", "next_best_action", "sales_tips") or (
        agent in ("investment_insights", "property_recommendations") and lead_id
    ):
        if not lead_id:
            raise AppError("lead_id is required for this widget", code="missing_lead_id")
        context = _lead_ctx(db, ctx, lead_id)
        entity_type, entity_id = "lead", lead_id
    elif agent == "customer_summary" or customer_id:
        if not customer_id:
            raise AppError("customer_id is required for this widget", code="missing_customer_id")
        context = _customer_ctx(db, ctx, customer_id)
        entity_type, entity_id = "customer", customer_id
    else:
        raise AppError("lead_id or customer_id is required", code="missing_entity")

    context.update(_tenant_ctx(db, ctx.user.tenant_id))

    profile = context.get("lead") or context.get("customer") or {}
    if agent in ("investment_insights", "property_recommendations"):
        prefs = profile.get("preferences") or {}
        recs = _recommend_units(
            db, ctx.user.tenant_id,
            budget_min=profile.get("budget_min"), budget_max=profile.get("budget_max"),
            property_type=profile.get("property_type") or prefs.get("property_type"),
            location=profile.get("location_preference") or prefs.get("location"),
            purpose=prefs.get("purpose"),
        )
        context["recommendations"] = recs
        context["matching_units"] = recs
        context["budget_max"] = profile.get("budget_max")

    ai = get_provider()
    payload = ai.generate(agent, {k: v for k, v in context.items() if not k.startswith("_")})
    insight = AIInsight(
        tenant_id=ctx.user.tenant_id, entity_type=entity_type, entity_id=entity_id,
        agent_name=agent, provider=ai.name, requested_by=ctx.user.id, payload=payload,
    )
    db.add(insight)
    db.flush()
    return {"agent": agent, "provider": ai.name, "insight_id": insight.id, "result": payload}


def run_component(db: Session, ctx: AccessContext, component: str, body: dict) -> dict:
    if component not in COMPONENTS:
        raise AppError(f"Unknown component '{component}'", code="unknown_component",
                       status_code=404)
    agent = COMPONENTS[component]
    tenant_config.enforce(tenant_config.load_policy(db, ctx.user.tenant_id), agent)
    lead_id, customer_id = body.get("lead_id"), body.get("customer_id")
    context: dict = {k: v for k, v in body.items() if k not in ("lead_id", "customer_id")}
    entity_type, entity_id = "system", ctx.user.id
    lead_obj = None

    if lead_id:
        lead_context = _lead_ctx(db, ctx, lead_id)
        lead_obj = lead_context.pop("_lead_obj")
        context.update(lead_context)
        entity_type, entity_id = "lead", lead_id
    elif customer_id:
        customer_context = _customer_ctx(db, ctx, customer_id)
        customer_context.pop("_customer_obj")
        context.update(customer_context)
        entity_type, entity_id = "customer", customer_id

    context.update(_tenant_ctx(db, ctx.user.tenant_id))

    if agent == "property_recommendation":
        profile = context.get("lead") or context.get("customer") or {}
        prefs = profile.get("preferences") or {}
        context["recommendations"] = _recommend_units(
            db, ctx.user.tenant_id,
            budget_min=body.get("budget_min", profile.get("budget_min")),
            budget_max=body.get("budget_max", profile.get("budget_max")),
            property_type=body.get("property_type",
                                   profile.get("property_type") or prefs.get("property_type")),
            location=body.get("location",
                              profile.get("location_preference") or prefs.get("location")),
            purpose=body.get("purpose", prefs.get("purpose")),
        )

    ai = get_provider()
    payload = ai.generate(agent, context)

    # Side effect: qualification writes the score back onto the lead (PRD §4.2 step 8).
    if agent == "lead_qualification" and lead_obj is not None:
        previous_band = lead_obj.score_band
        lead_obj.ai_score = payload["ai_score"]
        lead_obj.score_band = payload["score_band"]
        log_activity(
            db, tenant_id=lead_obj.tenant_id, entity_type="lead", entity_id=lead_obj.id,
            type="ai_recommendation",
            title=f"AI scored {payload['ai_score']}/100 ({payload['score_band']})",
            detail={"explanation": payload["explanation"]},
        )
        # Task 12: AI-suggestion notification when a lead first turns hot.
        if payload["score_band"] == "hot" and previous_band != "hot" and lead_obj.assigned_to:
            from app.modules.notifications.models import NotificationType
            from app.modules.notifications.service import notify

            notify(
                db, tenant_id=lead_obj.tenant_id, user_id=lead_obj.assigned_to,
                type=NotificationType.AI_SUGGESTION,
                title=f"Hot lead: {lead_obj.full_name} scored {payload['ai_score']}/100",
                body="Pappu suggests contacting within the SLA window.",
                entity_type="lead", entity_id=lead_obj.id,
                dedupe_key=f"hot_lead:{lead_obj.id}",
            )

    insight = AIInsight(
        tenant_id=ctx.user.tenant_id, entity_type=entity_type, entity_id=entity_id,
        agent_name=agent, provider=ai.name, requested_by=ctx.user.id, payload=payload,
    )
    db.add(insight)
    db.flush()
    return {"agent": agent, "provider": ai.name, "insight_id": insight.id, "result": payload}


def chat(
    db: Session, ctx: AccessContext, *, message: str, lead_id: str | None = None,
    history: list[dict] | None = None,
) -> dict:
    """Conversational turn against the buyer-assistant agent.

    The equivalent of STAIL's `POST /api/v1/agents/chat`, minus the microservice
    hop. Returns a reply a chat UI can render plus the structured extraction, so
    the caller can act on it without re-parsing prose.
    """
    result = run_component(
        db, ctx, "buyer-assistant",
        {"message": message, "lead_id": lead_id,
         "conversation_history": history or []},
    )
    payload = result["result"]
    captured = payload.get("captured_requirements") or {}
    if payload.get("next_question"):
        reply = payload["next_question"]
        if captured:
            reply = (
                "Got it — "
                + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in captured.items())
                + f". {reply}"
            )
    elif captured:
        reply = (
            "I have everything I need: "
            + ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in captured.items())
            + ". Let me pull matching options."
        )
    else:
        reply = "Tell me a bit about what you're looking for — area, budget, and size."
    return {**result, "reply": reply}


def orchestrate(
    db: Session, ctx: AccessContext, *, message: str, lead_id: str | None = None,
) -> dict:
    """Run the full lead pipeline on one natural-language message.

    Extract requirements → rank live inventory against them → grade the lead →
    write the result back to the CRM. Each stage reports its own latency and
    confidence, and a stage that cannot run (no lead attached, say) is reported as
    skipped rather than silently dropped.
    """
    import time

    steps: list[dict] = []
    # Consent is checked once, up front: a workspace that declined must not get a
    # partial pipeline, it must get a clear refusal. Individual features being
    # switched off is different — those stages are skipped and reported.
    policy = tenant_config.load_policy(db, ctx.user.tenant_id)
    tenant_config.enforce(policy, "buyer_assistant")

    def _skip(name: str, reason: str):
        steps.append({"agent": name, "status": "skipped", "latency_ms": 0,
                      "reason": reason})

    def _run(name: str, fn):
        started = time.monotonic()
        try:
            output = fn()
            status = "ok"
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001 — one bad stage must not void the rest
            output, status = {"error": str(exc)}, "failed"
        steps.append({
            "agent": name, "status": status,
            "latency_ms": int((time.monotonic() - started) * 1000),
        })
        return output

    # 1. Extract structured requirements from the buyer's own words.
    extraction = _run(
        "buyer_assistant",
        lambda: run_component(
            db, ctx, "buyer-assistant", {"message": message, "lead_id": lead_id}
        )["result"],
    )
    prefs = {
        "budget_min": extraction.get("budget_min"),
        "budget_max": extraction.get("budget_max"),
        "property_type": extraction.get("property_type"),
        "location": extraction.get("location"),
        "purpose": extraction.get("purpose"),
    }

    # 2 + 3. Rank live inventory against the extraction and annotate the top hits.
    if tenant_config.is_agent_enabled(policy, "property_recommendation"):
        recommendation = _run(
            "property_recommendation",
            lambda: run_component(
                db, ctx, "property-recommendation", {"lead_id": lead_id, **prefs}
            )["result"],
        )
    else:
        recommendation = None
        _skip("property_recommendation", "property recommendation is not enabled")

    # 4. Persist first: fill blank lead fields from the extraction and log the turn.
    #
    # STAIL grades before persisting (AGT-02 then AGT-06) because their CRM agent
    # writes to a different service over HTTP. Here the grading engine reads the
    # very rows crm_sync writes, so grading first means grading a lead the pipeline
    # has already learned three facts about but not yet recorded — it reported
    # "cold" for a buyer whose stated budget and configuration were an exact match.
    if lead_id:
        crm = _run("crm_sync", lambda: _sync_lead_from_extraction(
            db, ctx, lead_id, prefs, message, recommendation,
        ))
    else:
        crm = {"updated_fields": [], "activity_logged": False}
        _skip("crm_sync", "no lead_id supplied")

    # 5. Grade — now seeing everything this turn learned.
    if not lead_id:
        qualification = None
        _skip("lead_qualification", "no lead_id supplied")
    elif not tenant_config.is_agent_enabled(policy, "lead_qualification"):
        qualification = None
        _skip("lead_qualification", "AI lead scoring is not enabled")
    else:
        qualification = _run(
            "lead_qualification",
            lambda: run_component(
                db, ctx, "lead-qualification", {"lead_id": lead_id}
            )["result"],
        )

    return {
        "message": message,
        "pipeline": steps,
        "preferences": prefs,
        "extraction": extraction,
        "recommendations": (recommendation or {}).get("recommendations") or [],
        "qualification": qualification,
        "crm": crm,
        "provider": get_provider().name,
    }


def _sync_lead_from_extraction(
    db: Session, ctx: AccessContext, lead_id: str, prefs: dict, message: str,
    recommendation: dict | None,
) -> dict:
    """Write the conversation's findings back onto the lead.

    Only *blank* fields are filled. An AI extraction never overwrites something a
    human already entered — that would quietly destroy verified data on the
    strength of one ambiguous sentence.
    """
    lead = get_lead_scoped(db, ctx, lead_id)
    updated: list[str] = []

    if prefs.get("budget_max") and not lead.budget_max:
        lead.budget_max = prefs["budget_max"]
        updated.append("budget_max")
    if prefs.get("budget_min") and not lead.budget_min:
        lead.budget_min = prefs["budget_min"]
        updated.append("budget_min")
    if prefs.get("location") and not lead.location_preference:
        lead.location_preference = str(prefs["location"])[:200]
        updated.append("location_preference")
    if prefs.get("property_type") and not lead.property_type:
        lead.property_type = str(prefs["property_type"])[:100]
        updated.append("property_type")

    top = ((recommendation or {}).get("recommendations") or [])[:3]
    log_activity(
        db, tenant_id=lead.tenant_id, entity_type="lead", entity_id=lead.id,
        type="ai_recommendation",
        title="AI pipeline processed a conversation turn",
        detail={
            "message": message[:500],
            "extracted": {k: v for k, v in prefs.items() if v},
            "fields_filled": updated,
            "top_matches": [
                {"unit_id": u.get("unit_id"), "project": u.get("project"),
                 "match_score": u.get("match_score")}
                for u in top
            ],
        },
        actor=ctx.user,
    )
    db.flush()
    return {"lead_id": lead.id, "updated_fields": updated, "activity_logged": True,
            "matches_logged": len(top)}


def list_insights(db: Session, ctx: AccessContext, entity_type: str, entity_id: str):
    return db.scalars(
        select(AIInsight)
        .where(
            AIInsight.tenant_id == ctx.user.tenant_id,
            AIInsight.entity_type == entity_type,
            AIInsight.entity_id == entity_id,
        )
        .order_by(AIInsight.created_at.desc())
        .limit(50)
    ).all()
