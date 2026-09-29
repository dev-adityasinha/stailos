"""ICS (iCalendar) invite generation for calendar events — RFC 5545 via the
free/open-source `icalendar` package, attached to invite emails so attendees
can add the event to any calendar app (Google/Outlook/Apple all support it)."""
from datetime import datetime, timezone

from icalendar import Calendar, Event, vCalAddress, vText

from app.core.email import Attachment
from app.modules.calendar.models import CalendarEvent


def _as_utc(dt: datetime) -> datetime:
    """CalendarEvent timestamps are stored naive-but-already-UTC (see
    calendar/router.py:_naive / leads/service.py:_naive_utc). Handing a
    naive datetime to icalendar serializes a timezone-less "floating" time
    that calendar apps render in the *viewer's* local zone instead of UTC —
    attach tzinfo explicitly so DTSTART/DTEND/DTSTAMP emit a real `Z` UTC
    timestamp."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build_ics(event: CalendarEvent, *, organizer_email: str) -> Attachment:
    cal = Calendar()
    cal.add("prodid", "-//Pappu AI CRM//Calendar//EN")
    cal.add("version", "2.0")
    cal.add("method", "REQUEST")

    vevent = Event()
    vevent.add("uid", f"{event.id}@pappuai.crm")
    vevent.add("summary", event.title)
    vevent.add("dtstart", _as_utc(event.start_at))
    vevent.add("dtend", _as_utc(event.end_at or event.start_at))
    vevent.add("dtstamp", _as_utc(event.created_at))
    if event.description:
        vevent.add("description", event.description)
    if event.location:
        vevent.add("location", event.location)

    organizer = vCalAddress(f"MAILTO:{organizer_email}")
    organizer.params["cn"] = vText(event.owner.full_name if event.owner else organizer_email)
    vevent["organizer"] = organizer

    for attendee_user in event.attendees:
        if not attendee_user.email:
            continue
        attendee = vCalAddress(f"MAILTO:{attendee_user.email}")
        attendee.params["cn"] = vText(attendee_user.full_name)
        attendee.params["role"] = vText("REQ-PARTICIPANT")
        vevent.add("attendee", attendee, encode=0)

    cal.add_component(vevent)
    return Attachment(filename="invite.ics", content=cal.to_ical(), mimetype="text/calendar")


def build_event_ics(
    *, uid: str, title: str, start_at: datetime, end_at: datetime,
    description: str | None, location: str | None,
    organizer_email: str, attendee_email: str, attendee_name: str,
) -> Attachment:
    """Standalone ICS builder for investor events (events/service.py) — the
    marketing Event/EventRegistration models don't map onto CalendarEvent's
    owner/attendees relationships, so this takes plain fields instead of an
    ORM object. Same RFC 5545 shape as build_ics() otherwise."""
    cal = Calendar()
    cal.add("prodid", "-//Pappu AI CRM//Events//EN")
    cal.add("version", "2.0")
    cal.add("method", "REQUEST")

    vevent = Event()
    vevent.add("uid", f"{uid}@pappuai.crm")
    vevent.add("summary", title)
    vevent.add("dtstart", _as_utc(start_at))
    vevent.add("dtend", _as_utc(end_at))
    vevent.add("dtstamp", _as_utc(datetime.now(timezone.utc)))
    if description:
        vevent.add("description", description)
    if location:
        vevent.add("location", location)

    organizer = vCalAddress(f"MAILTO:{organizer_email}")
    organizer.params["cn"] = vText(title)
    vevent["organizer"] = organizer

    attendee = vCalAddress(f"MAILTO:{attendee_email}")
    attendee.params["cn"] = vText(attendee_name)
    attendee.params["role"] = vText("REQ-PARTICIPANT")
    vevent.add("attendee", attendee, encode=0)

    cal.add_component(vevent)
    return Attachment(
        filename="event_invite.ics", content=cal.to_ical(), mimetype="text/calendar"
    )
