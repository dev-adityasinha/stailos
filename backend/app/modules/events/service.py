"""Investor-event marketing: admin CRUD for events/speakers/agenda, public
registration (creates a real Lead via leads.service.create_lead so it
inherits auto-assignment/scoring/pipeline for free), QR check-in, badge
PDFs, referral tracking, live dashboard metrics, and post-event follow-up."""
import io
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import events as event_bus
from app.core.audit import record_audit
from app.core.deps import AccessContext
from app.core.email import send_email
from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import Scope
from app.core.ics import build_event_ics
from app.core.qr import build_qr_png
from app.core.whatsapp import send_whatsapp
from app.db.base import SessionLocal
from app.modules.auth.models import User
from app.modules.events.models import (
    AgendaItem,
    Event,
    EventRegistration,
    EventStatus,
    RegistrationStage,
    Speaker,
)
from app.modules.leads import service as leads_service
from app.modules.leads.models import Lead, LeadStage

logger = logging.getLogger("crm.events")


def _naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


# ------------------------------------------------------------------ admin: events

def scoped_query(db: Session, ctx: AccessContext):
    return select(Event).where(Event.tenant_id == ctx.user.tenant_id)


def get_event_scoped(db: Session, ctx: AccessContext, event_id: str) -> Event:
    event = db.scalars(scoped_query(db, ctx).where(Event.id == event_id)).first()
    if event is None:
        raise NotFoundError("Event not found")
    return event


def list_events(db: Session, ctx: AccessContext) -> list[Event]:
    return list(db.scalars(scoped_query(db, ctx).order_by(Event.start_at.desc())).all())


def create_event(db: Session, ctx: AccessContext, data: dict) -> Event:
    if db.scalars(select(Event).where(Event.slug == data["slug"])).first():
        raise ConflictError("An event with this slug already exists", code="slug_taken")
    event = Event(
        tenant_id=ctx.user.tenant_id,
        name=data["name"], slug=data["slug"], description=data.get("description"),
        venue=data.get("venue"), start_at=_naive(data["start_at"]), end_at=_naive(data["end_at"]),
        hero_image_url=data.get("hero_image_url"), cta_text=data.get("cta_text") or "Register now",
        created_by=ctx.user.id,
    )
    db.add(event)
    db.flush()
    record_audit(
        db, tenant_id=event.tenant_id, action="event.create", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="event", entity_id=event.id,
    )
    return event


def update_event(db: Session, ctx: AccessContext, event_id: str, changes: dict) -> Event:
    event = get_event_scoped(db, ctx, event_id)
    changes.pop("slug", None)  # immutable once created — public URLs may already be shared
    for field, value in changes.items():
        if field == "status" and value is not None:
            value = value.value
        if field in ("start_at", "end_at"):
            value = _naive(value)
        setattr(event, field, value)
    record_audit(
        db, tenant_id=event.tenant_id, action="event.update", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="event", entity_id=event.id,
        detail={"fields": sorted(changes.keys())},
    )
    return event


def delete_event(db: Session, ctx: AccessContext, event_id: str) -> None:
    event = get_event_scoped(db, ctx, event_id)
    db.delete(event)


def add_speaker(db: Session, ctx: AccessContext, event_id: str, data: dict) -> Speaker:
    event = get_event_scoped(db, ctx, event_id)
    speaker = Speaker(event_id=event.id, **data)
    db.add(speaker)
    db.flush()
    return speaker


def _get_speaker_or_404(event: Event, speaker_id: str) -> Speaker:
    speaker = next((s for s in event.speakers if s.id == speaker_id), None)
    if speaker is None:
        raise NotFoundError("Speaker not found")
    return speaker


def update_speaker(
    db: Session, ctx: AccessContext, event_id: str, speaker_id: str, changes: dict
) -> Speaker:
    event = get_event_scoped(db, ctx, event_id)
    speaker = _get_speaker_or_404(event, speaker_id)
    for field, value in changes.items():
        setattr(speaker, field, value)
    return speaker


def delete_speaker(db: Session, ctx: AccessContext, event_id: str, speaker_id: str) -> None:
    event = get_event_scoped(db, ctx, event_id)
    speaker = _get_speaker_or_404(event, speaker_id)
    # AgendaItem.speaker_id has no ON DELETE behavior at the DB level —
    # unlink any agenda items pointing at this speaker first, or the FK
    # constraint rejects the delete.
    for item in event.agenda_items:
        if item.speaker_id == speaker_id:
            item.speaker_id = None
    db.delete(speaker)


def add_agenda_item(db: Session, ctx: AccessContext, event_id: str, data: dict) -> AgendaItem:
    event = get_event_scoped(db, ctx, event_id)
    item = AgendaItem(event_id=event.id, **{**data, "start_time": _naive(data["start_time"])})
    db.add(item)
    db.flush()
    return item


def _get_agenda_item_or_404(event: Event, item_id: str) -> AgendaItem:
    item = next((a for a in event.agenda_items if a.id == item_id), None)
    if item is None:
        raise NotFoundError("Agenda item not found")
    return item


def update_agenda_item(
    db: Session, ctx: AccessContext, event_id: str, item_id: str, changes: dict
) -> AgendaItem:
    event = get_event_scoped(db, ctx, event_id)
    item = _get_agenda_item_or_404(event, item_id)
    for field, value in changes.items():
        if field == "start_time":
            value = _naive(value)
        setattr(item, field, value)
    return item


def delete_agenda_item(db: Session, ctx: AccessContext, event_id: str, item_id: str) -> None:
    event = get_event_scoped(db, ctx, event_id)
    db.delete(_get_agenda_item_or_404(event, item_id))


# --------------------------------------------------------------- admin: registrations

def list_registrations(db: Session, ctx: AccessContext, event_id: str) -> list[EventRegistration]:
    event = get_event_scoped(db, ctx, event_id)
    return list(
        db.scalars(
            select(EventRegistration)
            .where(EventRegistration.event_id == event.id)
            .order_by(EventRegistration.created_at.desc())
        ).all()
    )


def get_registration_scoped(
    db: Session, ctx: AccessContext, event_id: str, registration_id: str
) -> EventRegistration:
    event = get_event_scoped(db, ctx, event_id)
    reg = db.scalars(
        select(EventRegistration).where(
            EventRegistration.event_id == event.id, EventRegistration.id == registration_id
        )
    ).first()
    if reg is None:
        raise NotFoundError("Registration not found")
    return reg


def check_in(db: Session, ctx: AccessContext, event_id: str, token: str) -> EventRegistration:
    event = get_event_scoped(db, ctx, event_id)
    registration = db.scalars(
        select(EventRegistration).where(
            EventRegistration.event_id == event.id, EventRegistration.checkin_token == token
        )
    ).first()
    if registration is None:
        raise NotFoundError("No registration matches this QR code for this event")
    if registration.checked_in_at is not None:
        return registration  # idempotent — re-scanning is a no-op, not an error

    registration.checked_in_at = _naive_now()
    registration.stage = RegistrationStage.ATTENDED.value
    if registration.lead_id:
        lead = db.get(Lead, registration.lead_id)
        if lead and lead.stage not in (LeadStage.COMPLETED.value, LeadStage.LOST.value):
            leads_service.record_stage_transition(
                db, lead, LeadStage.INTERESTED,
                actor_id=ctx.user.id, actor_name=ctx.user.full_name,
            )
    record_audit(
        db, tenant_id=event.tenant_id, action="event.checkin", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="event_registration", entity_id=registration.id,
    )
    return registration


def generate_badge_pdf(db: Session, ctx: AccessContext, event_id: str, registration_id: str) -> bytes:
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    event = get_event_scoped(db, ctx, event_id)
    registration = get_registration_scoped(db, ctx, event_id, registration_id)

    qr_reader = ImageReader(io.BytesIO(build_qr_png(registration.checkin_token)))
    buf = io.BytesIO()
    width, height = A6
    c = canvas.Canvas(buf, pagesize=A6)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 20 * mm, registration.full_name[:40])
    c.setFont("Helvetica", 11)
    c.drawCentredString(width / 2, height - 28 * mm, (registration.company or "")[:40])
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, height - 38 * mm, event.name[:40])
    c.drawImage(qr_reader, width / 2 - 25 * mm, 15 * mm, 50 * mm, 50 * mm)
    c.showPage()
    c.save()

    registration.badge_printed_at = _naive_now()
    return buf.getvalue()


def get_dashboard(db: Session, ctx: AccessContext, event_id: str) -> dict:
    event = get_event_scoped(db, ctx, event_id)
    rows = list(
        db.scalars(
            select(EventRegistration).where(EventRegistration.event_id == event.id)
        ).all()
    )
    total = len(rows)
    rsvp = sum(
        1 for r in rows
        if r.stage in (RegistrationStage.RSVP_CONFIRMED.value, RegistrationStage.ATTENDED.value)
    )
    attended = sum(1 for r in rows if r.stage == RegistrationStage.ATTENDED.value)
    no_show = sum(1 for r in rows if r.stage == RegistrationStage.NO_SHOW.value)
    by_source: dict[str, int] = {}
    for r in rows:
        by_source[r.source] = by_source.get(r.source, 0) + 1

    cost_per_lead = None
    if event.total_ad_spend and total:
        cost_per_lead = Decimal(str(event.total_ad_spend)) / total

    def _pct(n: int) -> float:
        return round(n / total * 100, 1) if total else 0.0

    return {
        "total_registrations": total,
        "rsvp_confirmed": rsvp,
        "attended": attended,
        "no_show": no_show,
        "rsvp_rate": _pct(rsvp),
        "attendance_rate": _pct(attended),
        "checkin_rate": _pct(attended),
        "total_ad_spend": event.total_ad_spend,
        "cost_per_lead": cost_per_lead,
        "by_source": by_source,
    }


# --------------------------------------------------------------------- public

def get_published_event(db: Session, slug: str) -> Event:
    event = db.scalars(
        select(Event).where(Event.slug == slug, Event.status == EventStatus.PUBLISHED.value)
    ).first()
    if event is None:
        raise NotFoundError("Event not found")
    return event


def get_qr_png_for_token(db: Session, slug: str, token: str) -> bytes:
    """Public QR image lookup keyed by the registrant's own opaque
    checkin_token (128 bits of entropy from secrets.token_urlsafe), not a
    guessable registration id — knowing someone else's registration_id must
    not be enough to fetch (and thus reuse) their check-in QR code."""
    event = get_published_event(db, slug)
    registration = db.scalars(
        select(EventRegistration).where(
            EventRegistration.event_id == event.id, EventRegistration.checkin_token == token
        )
    ).first()
    if registration is None:
        raise NotFoundError("Registration not found")
    return build_qr_png(registration.checkin_token)


def count_referrals(db: Session, event_id: str, referral_code: str) -> int:
    return db.scalar(
        select(func.count(EventRegistration.id)).where(
            EventRegistration.event_id == event_id,
            EventRegistration.referred_by_code == referral_code,
        )
    ) or 0


def _send_confirmation(db: Session, event: Event, registration: EventRegistration) -> None:
    body = (
        f"Hi {registration.full_name},\n\n"
        f"You're registered for {event.name} on {event.start_at:%d %b %Y, %H:%M}"
        + (f" at {event.venue}." if event.venue else ".")
        + "\n\nA calendar invite is attached — add it so you don't miss it. "
        + "We'll send reminders as the date gets closer. "
        + f"Share your referral link with friends: use code {registration.referral_code}."
    )
    owner = db.get(User, event.created_by) if event.created_by else None
    ics = build_event_ics(
        uid=f"event-{event.id}-registration-{registration.id}",
        title=event.name, start_at=event.start_at, end_at=event.end_at,
        description=event.description, location=event.venue,
        organizer_email=owner.email if owner else registration.email,
        attendee_email=registration.email, attendee_name=registration.full_name,
    )
    send_email(
        db, to=registration.email, subject=f"You're registered: {event.name}",
        body=body, category="event_confirmation", attachment=ics,
    )
    if registration.phone:
        send_whatsapp(db, to_phone=registration.phone, body=body, category="event_confirmation")


def register_for_event(db: Session, event: Event, data: dict) -> EventRegistration:
    email = data["email"].lower().strip()
    if db.scalars(
        select(EventRegistration).where(
            EventRegistration.event_id == event.id, EventRegistration.email == email
        )
    ).first():
        raise ConflictError(
            "This email is already registered for this event", code="already_registered"
        )

    lead_id = None
    owner = db.get(User, event.created_by) if event.created_by else None
    if owner:
        ctx = AccessContext(user=owner, scope=Scope.ALL)
        lead = leads_service.create_lead(
            db, ctx,
            {
                "full_name": data["full_name"], "phone": data["phone"], "email": email,
                "source": "event", "campaign": event.name,
            },
            force=True,  # duplicate lead detection is orthogonal to event-registration dedupe above
        )
        lead_id = lead.id

    registration = EventRegistration(
        tenant_id=event.tenant_id, event_id=event.id,
        full_name=data["full_name"], email=email, phone=data.get("phone"),
        company=data.get("company"), investment_budget=data.get("investment_budget"),
        utm_campaign=data.get("utm_campaign"), referred_by_code=data.get("ref"),
        lead_id=lead_id,
    )
    db.add(registration)
    db.flush()

    _send_confirmation(db, event, registration)
    record_audit(
        db, tenant_id=event.tenant_id, action="event.register",
        entity_type="event_registration", entity_id=registration.id,
        detail={"event_id": event.id},
    )
    event_bus.publish(
        "event.registered",
        {"event_id": event.id, "registration_id": registration.id, "tenant_id": event.tenant_id},
        db=db,
    )
    return registration


def confirm_rsvp_public(db: Session, slug: str, token: str) -> EventRegistration:
    event = get_published_event(db, slug)
    registration = db.scalars(
        select(EventRegistration).where(
            EventRegistration.event_id == event.id, EventRegistration.checkin_token == token
        )
    ).first()
    if registration is None:
        raise NotFoundError("Registration not found")
    if registration.stage == RegistrationStage.REGISTERED.value:
        registration.stage = RegistrationStage.RSVP_CONFIRMED.value
    return registration


# ---------------------------------------------------------- pre-event reminders

def run_event_reminders() -> None:
    """Periodic APScheduler entry point (wired in core/scheduler.py): for
    each published event starting within the next 48 hours, send a reminder
    to every registrant still in registered/rsvp_confirmed at the 48h and
    24h marks — deduped per registration via reminder_48h_sent_at /
    reminder_24h_sent_at so each fires exactly once regardless of how often
    the sweep runs. Commits per-registration so one bad row can't roll back
    reminders already sent to others."""
    with SessionLocal() as db:
        now = _naive_now()
        upcoming_events = list(
            db.scalars(
                select(Event).where(
                    Event.status == EventStatus.PUBLISHED.value,
                    Event.start_at > now,
                    Event.start_at <= now + timedelta(hours=48),
                )
            ).all()
        )
        for event in upcoming_events:
            hours_until = (event.start_at - now).total_seconds() / 3600
            registrations = db.scalars(
                select(EventRegistration).where(
                    EventRegistration.event_id == event.id,
                    EventRegistration.stage.in_([
                        RegistrationStage.REGISTERED.value,
                        RegistrationStage.RSVP_CONFIRMED.value,
                    ]),
                )
            ).all()
            for r in registrations:
                try:
                    # Exclusive windows: a registrant only ever gets the
                    # reminder matching the event's actual proximity. Someone
                    # who registers 5h out (or after scheduler downtime) gets
                    # the 24h reminder once — not a stale "48 hours to go"
                    # plus a "24 hours to go" back-to-back.
                    if hours_until <= 24:
                        if r.reminder_24h_sent_at is None:
                            _send_event_reminder(db, event, r, "24 hours")
                            r.reminder_24h_sent_at = now
                            # The 48h window is behind us — mark it superseded
                            # so nothing else considers it pending.
                            if r.reminder_48h_sent_at is None:
                                r.reminder_48h_sent_at = now
                            db.commit()
                    elif r.reminder_48h_sent_at is None:
                        _send_event_reminder(db, event, r, "48 hours")
                        r.reminder_48h_sent_at = now
                        db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("event reminder failed for registration_id=%s", r.id)


def _send_event_reminder(
    db: Session, event: Event, r: EventRegistration, window: str
) -> None:
    subject = f"Reminder: {event.name} is in {window}"
    body = (
        f"Hi {r.full_name},\n\n"
        f"Just a reminder — {event.name} is coming up in {window}, "
        f"on {event.start_at:%d %b %Y, %H:%M}"
        + (f" at {event.venue}." if event.venue else ".")
        + "\n\nSee you there!"
    )
    send_email(db, to=r.email, subject=subject, body=body, category="event_reminder")
    if r.phone:
        send_whatsapp(db, to_phone=r.phone, body=body, category="event_reminder")


# ------------------------------------------------------- post-event automation

def run_post_event_followups() -> None:
    """Periodic APScheduler entry point (wired in core/scheduler.py): for any
    event whose end_at has passed and hasn't been processed yet, mark stale
    registered/rsvp_confirmed rows as no-show, then send a follow-up
    email+WhatsApp — a thank-you sequence to attendees, a we-missed-you
    sequence to no-shows. Commits per-event so one bad event can't roll back
    follow-ups already sent for others."""
    with SessionLocal() as db:
        now = _naive_now()
        due_events = list(
            db.scalars(
                select(Event).where(Event.end_at < now, Event.follow_up_sent_at.is_(None))
            ).all()
        )
        for event in due_events:
            try:
                _run_followup_for_event(db, event, now)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("post-event follow-up failed for event_id=%s", event.id)


def _run_followup_for_event(db: Session, event: Event, now: datetime) -> None:
    rows = list(
        db.scalars(select(EventRegistration).where(EventRegistration.event_id == event.id)).all()
    )
    for r in rows:
        if r.stage in (RegistrationStage.REGISTERED.value, RegistrationStage.RSVP_CONFIRMED.value):
            r.stage = RegistrationStage.NO_SHOW.value

    for r in rows:
        attended = r.stage == RegistrationStage.ATTENDED.value
        subject = (
            f"Thanks for attending {event.name}!" if attended else f"We missed you at {event.name}"
        )
        body = (
            f"Hi {r.full_name},\n\n"
            + (
                "Thanks for joining us — reach out any time to schedule a site visit or ask "
                "questions about what we covered."
                if attended else
                "Sorry we missed you at the event! Reach out any time to learn more or "
                "schedule a site visit."
            )
        )
        send_email(db, to=r.email, subject=subject, body=body, category="event_followup")
        if r.phone:
            send_whatsapp(db, to_phone=r.phone, body=body, category="event_followup")

    event.follow_up_sent_at = now
    event.status = EventStatus.COMPLETED.value
