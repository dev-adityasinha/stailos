"""Lead management business logic."""
import csv
import difflib
import io
import re
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import events
from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.deps import AccessContext, team_user_ids
from app.core.email import send_email
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.ics import build_ics
from app.core.permissions import Role, Scope
from app.db.base import utcnow
from app.modules.auth.models import User
from app.modules.leads.models import ImportBatch, Lead, LeadNote, LeadStage, LeadStageEvent, Tag
from app.modules.timeline.models import Activity, log_activity

NAME_SIMILARITY_THRESHOLD = 0.85

# Fields a Marketing Executive may edit (PRD §7.2 permissions)
MARKETING_EDITABLE_FIELDS = {"source", "campaign"}


def normalize_phone(phone: str) -> str:
    """E.164-ish normalization; bare 10-digit numbers assumed Indian (+91)."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+91{digits[1:]}"
    return f"+{digits}" if digits else ""


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def find_duplicates(
    db: Session, tenant_id: str, *, phone: str | None, email: str | None, full_name: str | None
) -> list[dict]:
    """Duplicate candidates by phone (exact), email (exact), name (fuzzy)."""
    matches: dict[str, dict] = {}
    active = select(Lead).where(Lead.tenant_id == tenant_id, Lead.deleted_at.is_(None))

    if phone:
        for lead in db.scalars(
            active.where(Lead.phone_normalized == normalize_phone(phone))
        ).all():
            matches[lead.id] = _match(lead, "phone")
    if email:
        for lead in db.scalars(
            active.where(func.lower(Lead.email) == email.lower())
        ).all():
            matches.setdefault(lead.id, _match(lead, "email"))
    if full_name:
        target = _normalize_name(full_name)
        for lead in db.scalars(active).all():
            if lead.id in matches:
                continue
            ratio = difflib.SequenceMatcher(
                None, target, _normalize_name(lead.full_name)
            ).ratio()
            if ratio >= NAME_SIMILARITY_THRESHOLD:
                matches[lead.id] = _match(lead, "name")
    return list(matches.values())


def _match(lead: Lead, match_type: str) -> dict:
    return {
        "lead_id": lead.id,
        "full_name": lead.full_name,
        "phone": lead.phone,
        "email": lead.email,
        "stage": lead.stage,
        "assigned_to": lead.assigned_to,
        "match_type": match_type,
    }


def scoped_query(db: Session, ctx: AccessContext, base=None):
    q = (base if base is not None else select(Lead)).where(
        Lead.tenant_id == ctx.user.tenant_id, Lead.deleted_at.is_(None)
    )
    if ctx.scope == Scope.TEAM:
        ids = team_user_ids(db, ctx.user)
        q = q.where(or_(Lead.assigned_to.in_(ids), Lead.created_by.in_(ids)))
    elif ctx.scope == Scope.OWN:
        q = q.where(
            or_(Lead.assigned_to == ctx.user.id, Lead.created_by == ctx.user.id)
        )
    return q


def get_lead_scoped(db: Session, ctx: AccessContext, lead_id: str) -> Lead:
    lead = db.scalars(scoped_query(db, ctx).where(Lead.id == lead_id)).first()
    if lead is None:
        raise NotFoundError("Lead not found")
    return lead


AssignPool = tuple[list[str], dict[str, int]]


def build_auto_assign_pool(db: Session, ctx: AccessContext) -> AssignPool | None:
    """One-time fetch of (candidates, open-lead-counts) for workload-balanced
    auto-assignment. Callers creating many leads in one request (CSV import)
    should build this once and pass it to every `create_lead()`/
    `_pick_auto_assignee()` call instead of letting each row re-query — a
    50,000-row import would otherwise issue up to 100,000 extra queries."""
    settings = get_settings()
    if not settings.lead_auto_assign_roles:
        return None
    candidates_q = select(User.id).where(
        User.tenant_id == ctx.user.tenant_id,
        User.is_active.is_(True),
        User.role.in_(settings.lead_auto_assign_roles),
    )
    if ctx.scope == Scope.TEAM:
        candidates_q = candidates_q.where(User.id.in_(team_user_ids(db, ctx.user)))
    candidates = list(db.scalars(candidates_q).all())
    if not candidates:
        return None

    open_stages = [
        s.value for s in LeadStage
        if s not in (LeadStage.BOOKED, LeadStage.COMPLETED, LeadStage.LOST)
    ]
    counts = dict(
        db.execute(
            select(Lead.assigned_to, func.count(Lead.id))
            .where(
                Lead.tenant_id == ctx.user.tenant_id,
                Lead.deleted_at.is_(None),
                Lead.assigned_to.in_(candidates),
                Lead.stage.in_(open_stages),
            )
            .group_by(Lead.assigned_to)
        ).all()
    )
    return candidates, {uid: counts.get(uid, 0) for uid in candidates}


def _pick_auto_assignee(
    db: Session, ctx: AccessContext, *, pool: AssignPool | None = None
) -> str | None:
    """Workload-balanced auto-assignment: among active users holding an
    assignable role (config: lead_auto_assign_roles), pick whoever currently
    has the fewest open leads. Self-balancing — no round-robin cursor state
    needed, and it naturally corrects for uneven manual assignment/turnover.
    Pass `pool` (from `build_auto_assign_pool`) to avoid re-querying per call;
    the shared counts dict is updated in place so a caller looping over many
    leads sees each pick reflected in the next one."""
    resolved = pool if pool is not None else build_auto_assign_pool(db, ctx)
    if resolved is None:
        return None
    candidates, open_counts = resolved
    picked = min(candidates, key=lambda uid: (open_counts.get(uid, 0), uid))
    open_counts[picked] = open_counts.get(picked, 0) + 1
    return picked


def create_lead(
    db: Session, ctx: AccessContext, data: dict, *,
    force: bool = False, assignment_pool: AssignPool | None = None,
) -> Lead:
    duplicates = find_duplicates(
        db,
        ctx.user.tenant_id,
        phone=data.get("phone"),
        email=data.get("email"),
        full_name=data.get("full_name"),
    )
    if duplicates and not force:
        raise ConflictError(
            "Possible duplicate lead(s) found. Re-submit with force=true to create anyway.",
            code="duplicate_lead",
        )

    explicit_assignee = data.get("assigned_to")
    if explicit_assignee:
        # A client-supplied assignee must belong to the caller's own tenant —
        # same check assign_lead() already does. Silently ignore rather than
        # 404: an invalid hint shouldn't block lead creation, it should just
        # fall through to auto-assign/self below.
        target = db.get(User, explicit_assignee)
        if target is None or not target.is_active or target.tenant_id != ctx.user.tenant_id:
            explicit_assignee = None

    auto_assigned = False
    if explicit_assignee:
        assigned_to = explicit_assignee
    elif ctx.is_admin and get_settings().lead_auto_assign_enabled:
        picked = _pick_auto_assignee(db, ctx, pool=assignment_pool)
        assigned_to = picked or ctx.user.id
        auto_assigned = picked is not None
    else:
        assigned_to = ctx.user.id
    if assigned_to != ctx.user.id and not ctx.is_admin:
        assigned_to = ctx.user.id  # non-managers can only assign to themselves

    lead = Lead(
        tenant_id=ctx.user.tenant_id,
        full_name=data["full_name"].strip(),
        phone=data["phone"],
        phone_normalized=normalize_phone(data["phone"]),
        email=(data.get("email") or None),
        source=data.get("source", "other"),
        campaign=data.get("campaign"),
        stage=(data.get("stage") or LeadStage.NEW).value
        if isinstance(data.get("stage"), LeadStage)
        else (data.get("stage") or LeadStage.NEW.value),
        assigned_to=assigned_to,
        created_by=ctx.user.id,
        budget_min=data.get("budget_min"),
        budget_max=data.get("budget_max"),
        location_preference=data.get("location_preference"),
        property_type=data.get("property_type"),
        requirements=data.get("requirements"),
        custom_fields=data.get("custom_fields"),
    )
    db.add(lead)
    db.flush()
    log_activity(
        db, tenant_id=lead.tenant_id, entity_type="lead", entity_id=lead.id,
        type="created", title=f"Lead created via {lead.source}", actor=ctx.user,
        detail={"duplicates_overridden": bool(duplicates)},
    )
    record_audit(
        db, tenant_id=lead.tenant_id, action="lead.create", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="lead", entity_id=lead.id,
    )
    events.publish(
        "lead.created",
        {"lead_id": lead.id, "tenant_id": lead.tenant_id, "assigned_to": lead.assigned_to}, db=db,
    )
    if lead.assigned_to != ctx.user.id:
        # Covers both auto-assignment and an admin explicitly assigning to
        # someone else at creation time — either way the assignee should be
        # notified, same as a post-creation reassign via assign_lead().
        record_audit(
            db, tenant_id=lead.tenant_id,
            action="lead.auto_assign" if auto_assigned else "lead.assign",
            actor_id=ctx.user.id, actor_email=ctx.user.email,
            entity_type="lead", entity_id=lead.id,
            detail={"assigned_to": lead.assigned_to},
        )
        events.publish(
            "lead.assigned",
            {"lead_id": lead.id, "tenant_id": lead.tenant_id, "assigned_to": lead.assigned_to,
             "assigned_by": ctx.user.id, "lead_name": lead.full_name}, db=db,
        )
    return lead


def update_lead(db: Session, ctx: AccessContext, lead_id: str, changes: dict) -> Lead:
    lead = get_lead_scoped(db, ctx, lead_id)
    if Role(ctx.user.role) == Role.MARKETING_EXECUTIVE:
        illegal = set(changes) - MARKETING_EDITABLE_FIELDS
        if illegal:
            raise PermissionDeniedError(
                f"Marketing can only edit {sorted(MARKETING_EDITABLE_FIELDS)}"
            )
    if "phone" in changes and changes["phone"]:
        lead.phone_normalized = normalize_phone(changes["phone"])
    for field, value in changes.items():
        setattr(lead, field, value)
    log_activity(
        db, tenant_id=lead.tenant_id, entity_type="lead", entity_id=lead.id,
        type="updated", title="Lead details updated", actor=ctx.user,
        detail={"fields": sorted(changes.keys())},
    )
    record_audit(
        db, tenant_id=lead.tenant_id, action="lead.update", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="lead", entity_id=lead.id,
        detail={"fields": sorted(changes.keys())},
    )
    return lead


def delete_lead(db: Session, ctx: AccessContext, lead_id: str) -> None:
    lead = get_lead_scoped(db, ctx, lead_id)
    lead.deleted_at = utcnow().replace(tzinfo=None)
    record_audit(
        db, tenant_id=lead.tenant_id, action="lead.delete", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="lead", entity_id=lead.id,
    )


def assign_lead(db: Session, ctx: AccessContext, lead_id: str, user_id: str) -> Lead:
    lead = get_lead_scoped(db, ctx, lead_id)
    target = db.get(User, user_id)
    if target is None or not target.is_active or target.tenant_id != ctx.user.tenant_id:
        raise NotFoundError("Assignee not found")
    if ctx.scope == Scope.TEAM and target.id not in team_user_ids(db, ctx.user):
        raise PermissionDeniedError("Assignee is outside your team")
    previous = lead.assignee.full_name if lead.assignee else "Unassigned"
    lead.assigned_to = target.id
    log_activity(
        db, tenant_id=lead.tenant_id, entity_type="lead", entity_id=lead.id,
        type="assigned", title=f"Reassigned from {previous} to {target.full_name}",
        actor=ctx.user,
    )
    record_audit(
        db, tenant_id=lead.tenant_id, action="lead.assign", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="lead", entity_id=lead.id,
        detail={"assigned_to": target.id},
    )
    events.publish(
        "lead.assigned",
        {"lead_id": lead.id, "tenant_id": lead.tenant_id, "assigned_to": target.id,
         "assigned_by": ctx.user.id, "lead_name": lead.full_name}, db=db,
    )
    return lead


TERMINAL_STAGES = {LeadStage.COMPLETED.value, LeadStage.LOST.value}


def record_stage_transition(
    db: Session, lead: Lead, stage: LeadStage, *,
    actor_id: str | None, actor_name: str | None, lost_reason: str | None = None,
) -> str:
    """Writes the LeadStageEvent history row and updates lead.stage/lost_reason.
    Shared by change_stage() (RBAC-guarded pipeline endpoint, enforces the
    reopen guard) and bookings/service.py (which drives a lead's stage as a
    side effect of its own already-guarded booking stage machine — booking
    progression is a distinct authorized workflow, so it deliberately does
    not re-apply the pipeline's reopen guard, but it must still write the
    same history row so GET stage-history stays complete). Returns the
    previous stage."""
    old_stage = lead.stage
    lead.stage = stage.value
    if stage == LeadStage.LOST:
        lead.lost_reason = lost_reason
    elif old_stage == LeadStage.LOST.value:
        lead.lost_reason = None
    db.add(
        LeadStageEvent(
            lead_id=lead.id, from_stage=old_stage, to_stage=stage.value,
            note=lost_reason if stage == LeadStage.LOST else None,
            actor_id=actor_id, actor_name=actor_name,
        )
    )
    return old_stage


def change_stage(
    db: Session, ctx: AccessContext, lead_id: str, stage: LeadStage, lost_reason: str | None,
    *, reopen: bool = False,
) -> Lead:
    lead = get_lead_scoped(db, ctx, lead_id)
    old_stage = lead.stage
    if old_stage in TERMINAL_STAGES and stage.value != old_stage and not reopen:
        raise ConflictError(
            f"Lead is {old_stage}; pass reopen=true to move it to a different stage.",
            code="lead_reopen_required",
        )
    record_stage_transition(
        db, lead, stage, actor_id=ctx.user.id, actor_name=ctx.user.full_name,
        lost_reason=lost_reason,
    )
    log_activity(
        db, tenant_id=lead.tenant_id, entity_type="lead", entity_id=lead.id,
        type="stage_change", title=f"Stage: {old_stage} → {stage.value}", actor=ctx.user,
        detail={"from": old_stage, "to": stage.value, "lost_reason": lost_reason},
    )
    record_audit(
        db, tenant_id=lead.tenant_id, action="lead.stage_change", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="lead", entity_id=lead.id,
        detail={"from": old_stage, "to": stage.value},
    )
    events.publish(
        "lead.stage_changed",
        {"lead_id": lead.id, "tenant_id": lead.tenant_id, "from": old_stage,
         "to": stage.value, "assigned_to": lead.assigned_to, "lead_name": lead.full_name}, db=db,
    )
    return lead


def _naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def schedule_site_visit(
    db: Session, ctx: AccessContext, lead_id: str, *,
    start_at: datetime, end_at: datetime | None, location: str | None,
    attendee_ids: list[str],
) -> tuple[Lead, "CalendarEvent"]:
    """Single source of truth for "schedule a site visit": creates the
    calendar event, advances the lead's pipeline stage, and emails every
    attendee an ICS invite — replaces the old implicit stage-only signal."""
    from app.modules.calendar.models import CalendarEvent

    lead = get_lead_scoped(db, ctx, lead_id)
    event = CalendarEvent(
        tenant_id=lead.tenant_id,
        owner_id=ctx.user.id,
        title=f"Site visit — {lead.full_name}",
        type="site_visit",
        location=location,
        start_at=_naive_utc(start_at),
        end_at=_naive_utc(end_at),
        entity_type="lead",
        entity_id=lead.id,
    )
    for uid in attendee_ids:
        attendee = db.get(User, uid)
        if attendee and attendee.tenant_id == lead.tenant_id and attendee not in event.attendees:
            event.attendees.append(attendee)
    if lead.assignee and lead.assignee not in event.attendees:
        event.attendees.append(lead.assignee)
    db.add(event)
    db.flush()

    if lead.stage not in (LeadStage.COMPLETED.value, LeadStage.LOST.value):
        change_stage(db, ctx, lead_id, LeadStage.SITE_VISIT_SCHEDULED, None)

    ics = build_ics(event, organizer_email=ctx.user.email)
    when = event.start_at.strftime("%Y-%m-%d %H:%M UTC")
    for attendee in event.attendees:
        if attendee.email:
            send_email(
                db, to=attendee.email,
                subject=f"Site visit scheduled: {lead.full_name}",
                body=(
                    f"A site visit has been scheduled for {lead.full_name} on {when}"
                    + (f" at {location}." if location else ".")
                ),
                category="calendar_invite",
                attachment=ics,
            )
    record_audit(
        db, tenant_id=lead.tenant_id, action="lead.schedule_site_visit", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="lead", entity_id=lead.id,
        detail={"calendar_event_id": event.id},
    )
    return lead, event


def add_note(db: Session, ctx: AccessContext, lead_id: str, body: str) -> LeadNote:
    lead = get_lead_scoped(db, ctx, lead_id)
    note = LeadNote(
        lead_id=lead.id, author_id=ctx.user.id, author_name=ctx.user.full_name, body=body
    )
    db.add(note)
    db.flush()  # populate id/created_at before the response is serialized
    log_activity(
        db, tenant_id=lead.tenant_id, entity_type="lead", entity_id=lead.id,
        type="note", title=body[:120], actor=ctx.user,
    )
    return note


def add_tag(db: Session, ctx: AccessContext, lead_id: str, name: str, color: str | None) -> Lead:
    lead = get_lead_scoped(db, ctx, lead_id)
    name = name.strip().lower()
    tag = db.scalars(
        select(Tag).where(Tag.tenant_id == lead.tenant_id, Tag.name == name)
    ).first()
    if tag is None:
        tag = Tag(tenant_id=lead.tenant_id, name=name, color=color)
        db.add(tag)
        db.flush()
    if tag not in lead.tags:
        lead.tags.append(tag)
    return lead


def remove_tag(db: Session, ctx: AccessContext, lead_id: str, tag_id: str) -> Lead:
    lead = get_lead_scoped(db, ctx, lead_id)
    lead.tags = [t for t in lead.tags if t.id != tag_id]
    return lead


def get_timeline(db: Session, ctx: AccessContext, lead_id: str) -> list[Activity]:
    lead = get_lead_scoped(db, ctx, lead_id)  # scope check
    return list(
        db.scalars(
            select(Activity)
            .where(Activity.entity_type == "lead", Activity.entity_id == lead.id)
            .order_by(Activity.created_at.desc())
        ).all()
    )


def get_stage_history(db: Session, ctx: AccessContext, lead_id: str) -> list[LeadStageEvent]:
    lead = get_lead_scoped(db, ctx, lead_id)  # scope check
    return list(
        db.scalars(
            select(LeadStageEvent)
            .where(LeadStageEvent.lead_id == lead.id)
            .order_by(LeadStageEvent.created_at)
        ).all()
    )


def pipeline_board(db: Session, ctx: AccessContext) -> dict:
    leads = db.scalars(scoped_query(db, ctx).order_by(Lead.updated_at.desc())).all()
    columns: dict[str, list] = {s.value: [] for s in LeadStage}
    for lead in leads:
        columns.setdefault(lead.stage, []).append(lead)
    return columns


# ------------------------------------------------------------- import/export

CSV_COLUMNS = ["full_name", "phone", "email", "source", "campaign", "budget_min",
               "budget_max", "location_preference", "property_type", "requirements"]

# Real-world exports rarely match CSV_COLUMNS: other CRMs emit camelCase
# ("fullName"), Excel sheets say "Mobile No", portals write budgets as "1-2Cr".
# Headers are normalised (camelCase/space/hyphen → snake_case), then aliased
# onto canonical names — a canonical header always beats an alias.
HEADER_ALIASES = {
    "lead_name": "full_name", "customer_name": "full_name", "client_name": "full_name",
    "contact_name": "full_name",
    "mobile": "phone", "mobile_no": "phone", "mobile_number": "phone", "phone_no": "phone",
    "phone_number": "phone", "contact": "phone", "contact_no": "phone",
    "contact_number": "phone", "whatsapp": "phone", "whatsapp_number": "phone",
    "email_address": "email", "email_id": "email", "mail": "email",
    "lead_source": "source", "hear_about": "source", "utm_source": "source",
    "utm_campaign": "campaign",
    "location": "location_preference", "preferred_location": "location_preference",
    "property": "property_type",
    "notes": "requirements", "comments": "requirements", "remarks": "requirements",
    "requirement": "requirements",
    "min_budget": "budget_min", "max_budget": "budget_max",
}

_BUDGET_UNITS = {"k": 1_000, "l": 100_000, "lac": 100_000, "lakh": 100_000,
                 "lakhs": 100_000, "cr": 10_000_000, "crore": 10_000_000,
                 "crores": 10_000_000}


def _normalise_header(name: str) -> str:
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", (name or "").strip())
    return re.sub(r"[\s\-]+", "_", name.lower()).strip("_")


def _amount(part: str) -> tuple[float, float | None] | None:
    m = re.fullmatch(r"([\d.]+)\s*([a-z]*)", part.strip())
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    return value, _BUDGET_UNITS.get(m.group(2) or "")


def _parse_budget_range(text: str) -> tuple[float | None, float | None]:
    """Turn "1-2Cr", "Under 50L", "5Cr+" or "75,00,000" into (min, max)."""
    t = re.sub(r"\s+", " ", re.sub(r"[₹,]", "", text.lower())).strip()
    if m := re.fullmatch(r"(?:under|below|upto|up to|max) ?(.+)", t):
        amt = _amount(m.group(1))
        return (None, amt[0] * (amt[1] or 1)) if amt else (None, None)
    if m := re.fullmatch(r"(.+?) ?\+|(?:above|over|min) ?(.+)", t):
        amt = _amount(m.group(1) or m.group(2))
        return (amt[0] * (amt[1] or 1), None) if amt else (None, None)
    if m := re.fullmatch(r"(.+?) ?(?:-|to) ?(.+)", t):
        lo, hi = _amount(m.group(1)), _amount(m.group(2))
        if lo and hi:
            # "1-2Cr": the upper bound's unit applies to a bare lower bound
            return lo[0] * (lo[1] or hi[1] or 1), hi[0] * (hi[1] or 1)
        return None, None
    amt = _amount(t)
    return (amt[0] * (amt[1] or 1),) * 2 if amt else (None, None)


def import_csv(db: Session, ctx: AccessContext, *, filename: str, content: bytes) -> ImportBatch:
    batch = ImportBatch(
        tenant_id=ctx.user.tenant_id, filename=filename[:300], created_by=ctx.user.id
    )
    errors: list[dict] = []
    imported = skipped = total = 0
    # Built once, not per row — a 50,000-row import re-querying auto-assign
    # candidates/workload per lead would otherwise issue ~100k extra queries.
    assignment_pool = (
        build_auto_assign_pool(db, ctx)
        if ctx.is_admin and get_settings().lead_auto_assign_enabled
        else None
    )

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    field_map: dict[str, str] = {}
    for name in reader.fieldnames or []:
        field_map.setdefault(_normalise_header(name), name)
    for alias, target in HEADER_ALIASES.items():
        if target not in field_map and alias in field_map:
            field_map[target] = field_map[alias]

    def cell(row: dict, key: str) -> str | None:
        src = field_map.get(key)
        value = (row.get(src) or "").strip() if src else ""
        return value or None

    for i, row in enumerate(reader, start=2):  # header is line 1
        total += 1
        if total > 50_000:
            errors.append({"row": i, "error": "Batch cap of 50,000 rows exceeded"})
            break
        name = cell(row, "full_name") or cell(row, "name")
        if not name:
            first = cell(row, "first_name") or ""
            last = cell(row, "last_name") or ""
            if first or last:
                name = f"{first} {last}".strip()
                
        phone = cell(row, "phone")
        if not name or not phone:
            errors.append({"row": i, "error": "full_name (or first_name + last_name) and phone are required"})
            continue
        if len(re.sub(r"\D", "", phone)) < 7:
            errors.append({"row": i, "error": f"Invalid phone: {phone}"})
            continue
        if find_duplicates(db, ctx.user.tenant_id, phone=phone, email=cell(row, "email"),
                           full_name=None):
            skipped += 1
            continue
        budget_min, budget_max = cell(row, "budget_min"), cell(row, "budget_max")
        if budget_min is None and budget_max is None and (stated := cell(row, "budget")):
            budget_min, budget_max = _parse_budget_range(stated)
        try:
            create_lead(
                db,
                ctx,
                {
                    "full_name": name,
                    "phone": phone,
                    "email": cell(row, "email"),
                    "source": cell(row, "source") or "csv_import",
                    "campaign": cell(row, "campaign"),
                    "budget_min": budget_min,
                    "budget_max": budget_max,
                    "location_preference": cell(row, "location_preference"),
                    "property_type": cell(row, "property_type"),
                    "requirements": cell(row, "requirements"),
                },
                force=True,  # dedupe already handled above with skip semantics
                assignment_pool=assignment_pool,
            )
            imported += 1
        except Exception as exc:
            errors.append({"row": i, "error": str(exc)[:200]})

    batch.total_rows = total
    batch.imported = imported
    batch.skipped_duplicates = skipped
    batch.errors = errors[:200]
    db.add(batch)
    db.flush()  # populate batch.id so the API response can return it
    record_audit(
        db, tenant_id=ctx.user.tenant_id, action="lead.import", actor_id=ctx.user.id,
        actor_email=ctx.user.email, detail={"imported": imported, "skipped": skipped,
                                            "errors": len(errors)},
    )
    return batch


def export_csv(db: Session, ctx: AccessContext) -> str:
    leads = db.scalars(scoped_query(db, ctx).order_by(Lead.created_at)).all()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["id", *CSV_COLUMNS, "stage", "assigned_to", "ai_score", "created_at"])
    for lead in leads:
        writer.writerow([
            lead.id, lead.full_name, lead.phone, lead.email or "", lead.source,
            lead.campaign or "", lead.budget_min or "", lead.budget_max or "",
            lead.location_preference or "", lead.property_type or "",
            lead.requirements or "", lead.stage,
            lead.assignee.full_name if lead.assignee else "",
            lead.ai_score or "", lead.created_at.isoformat(),
        ])
    return out.getvalue()
