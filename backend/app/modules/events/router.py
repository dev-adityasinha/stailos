from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require
from app.modules.events import service
from app.modules.events.schemas import (
    AgendaItemIn,
    AgendaItemOut,
    CheckinRequest,
    EventCreate,
    EventDashboard,
    EventOut,
    EventUpdate,
    RegistrationCreate,
    RegistrationOut,
    SpeakerIn,
    SpeakerOut,
)

router = APIRouter(prefix="/events", tags=["events"])


# --------------------------------------------------------------------- public
# No auth dependency on any route in this block — same pattern as
# auth/router.py's register/login (deps.py has no "optional auth" helper;
# public means simply not calling Depends(get_current_user)/require(...)).


@router.get("/public/{slug}")
def public_event(slug: str, db: Session = Depends(get_db)):
    event = service.get_published_event(db, slug)
    return {"data": EventOut.model_validate(event).model_dump()}


@router.post("/public/{slug}/register", status_code=status.HTTP_201_CREATED)
def public_register(slug: str, body: RegistrationCreate, db: Session = Depends(get_db)):
    event = service.get_published_event(db, slug)
    registration = service.register_for_event(db, event, body.model_dump())
    return {"data": RegistrationOut.model_validate(registration).model_dump()}


@router.post("/public/{slug}/rsvp")
def public_confirm_rsvp(slug: str, body: CheckinRequest, db: Session = Depends(get_db)):
    registration = service.confirm_rsvp_public(db, slug, body.token)
    return {"data": RegistrationOut.model_validate(registration).model_dump()}


@router.get("/public/{slug}/qr")
def public_qr(slug: str, token: str, db: Session = Depends(get_db)):
    png = service.get_qr_png_for_token(db, slug, token)
    return Response(content=png, media_type="image/png")


@router.get("/public/{slug}/referrals/{code}/count")
def public_referral_count(slug: str, code: str, db: Session = Depends(get_db)):
    event = service.get_published_event(db, slug)
    return {"data": {"count": service.count_referrals(db, event.id, code)}}


# ---------------------------------------------------------------------- admin


@router.get("")
def list_events(ctx=Depends(require("events", "read")), db: Session = Depends(get_db)):
    rows = service.list_events(db, ctx)
    return {"data": [EventOut.model_validate(e).model_dump() for e in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventCreate, ctx=Depends(require("events", "create")), db: Session = Depends(get_db)
):
    event = service.create_event(db, ctx, body.model_dump())
    return {"data": EventOut.model_validate(event).model_dump()}


@router.get("/{event_id}")
def get_event(
    event_id: str, ctx=Depends(require("events", "read")), db: Session = Depends(get_db)
):
    event = service.get_event_scoped(db, ctx, event_id)
    return {"data": EventOut.model_validate(event).model_dump()}


@router.patch("/{event_id}")
def update_event(
    event_id: str, body: EventUpdate,
    ctx=Depends(require("events", "update")), db: Session = Depends(get_db),
):
    event = service.update_event(db, ctx, event_id, body.model_dump(exclude_unset=True))
    return {"data": EventOut.model_validate(event).model_dump()}


@router.delete("/{event_id}")
def delete_event(
    event_id: str, ctx=Depends(require("events", "delete")), db: Session = Depends(get_db)
):
    service.delete_event(db, ctx, event_id)
    return {"data": {"message": "Event deleted"}}


@router.post("/{event_id}/speakers", status_code=status.HTTP_201_CREATED)
def add_speaker(
    event_id: str, body: SpeakerIn,
    ctx=Depends(require("events", "update")), db: Session = Depends(get_db),
):
    speaker = service.add_speaker(db, ctx, event_id, body.model_dump())
    return {"data": SpeakerOut.model_validate(speaker).model_dump()}


@router.patch("/{event_id}/speakers/{speaker_id}")
def update_speaker(
    event_id: str, speaker_id: str, body: SpeakerIn,
    ctx=Depends(require("events", "update")), db: Session = Depends(get_db),
):
    speaker = service.update_speaker(db, ctx, event_id, speaker_id, body.model_dump())
    return {"data": SpeakerOut.model_validate(speaker).model_dump()}


@router.delete("/{event_id}/speakers/{speaker_id}")
def delete_speaker(
    event_id: str, speaker_id: str,
    ctx=Depends(require("events", "update")), db: Session = Depends(get_db),
):
    service.delete_speaker(db, ctx, event_id, speaker_id)
    return {"data": {"message": "Speaker deleted"}}


@router.post("/{event_id}/agenda", status_code=status.HTTP_201_CREATED)
def add_agenda_item(
    event_id: str, body: AgendaItemIn,
    ctx=Depends(require("events", "update")), db: Session = Depends(get_db),
):
    item = service.add_agenda_item(db, ctx, event_id, body.model_dump())
    return {"data": AgendaItemOut.model_validate(item).model_dump()}


@router.patch("/{event_id}/agenda/{item_id}")
def update_agenda_item(
    event_id: str, item_id: str, body: AgendaItemIn,
    ctx=Depends(require("events", "update")), db: Session = Depends(get_db),
):
    item = service.update_agenda_item(db, ctx, event_id, item_id, body.model_dump())
    return {"data": AgendaItemOut.model_validate(item).model_dump()}


@router.delete("/{event_id}/agenda/{item_id}")
def delete_agenda_item(
    event_id: str, item_id: str,
    ctx=Depends(require("events", "update")), db: Session = Depends(get_db),
):
    service.delete_agenda_item(db, ctx, event_id, item_id)
    return {"data": {"message": "Agenda item deleted"}}


@router.get("/{event_id}/registrations")
def list_registrations(
    event_id: str, ctx=Depends(require("events", "read")), db: Session = Depends(get_db)
):
    rows = service.list_registrations(db, ctx, event_id)
    return {"data": [RegistrationOut.model_validate(r).model_dump() for r in rows]}


@router.post("/{event_id}/checkin")
def check_in(
    event_id: str, body: CheckinRequest,
    ctx=Depends(require("events", "update")), db: Session = Depends(get_db),
):
    registration = service.check_in(db, ctx, event_id, body.token)
    return {"data": RegistrationOut.model_validate(registration).model_dump()}


@router.get("/{event_id}/registrations/{registration_id}/badge.pdf")
def badge_pdf(
    event_id: str, registration_id: str,
    ctx=Depends(require("events", "read")), db: Session = Depends(get_db),
):
    content = service.generate_badge_pdf(db, ctx, event_id, registration_id)
    return Response(
        content=content, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="badge_{registration_id}.pdf"'},
    )


@router.get("/{event_id}/dashboard")
def dashboard(
    event_id: str, ctx=Depends(require("events", "read")), db: Session = Depends(get_db)
):
    data = service.get_dashboard(db, ctx, event_id)
    return {"data": EventDashboard(**data).model_dump()}
