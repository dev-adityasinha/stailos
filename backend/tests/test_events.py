"""Verification for the Events module: admin CRUD/CMS, public landing +
registration (creates a real CRM Lead), referrals, QR check-in, badges,
live dashboard metrics, and post-event follow-up automation."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.base import SessionLocal
from app.modules.auth.models import EmailOutbox
from app.modules.events.models import Event, EventRegistration
from app.modules.events.service import run_event_reminders, run_post_event_followups
from app.core.whatsapp import WhatsAppOutbox
from tests.conftest import auth_headers, create_user_as_admin


def make_event(client, headers, **overrides):
    payload = {
        "name": "Investor Meet 2026",
        "slug": "investor-meet-2026",
        "venue": "Taj Bangalore",
        "start_at": "2026-08-01T10:00:00Z",
        "end_at": "2026-08-01T13:00:00Z",
    }
    payload.update(overrides)
    return client.post("/api/v1/events", headers=headers, json=payload)


def publish(client, headers, event_id):
    return client.patch(f"/api/v1/events/{event_id}", headers=headers, json={"status": "published"})


def register_public(client, slug="investor-meet-2026", **overrides):
    payload = {
        "full_name": "Priya Investor", "email": "priya@x.com", "phone": "9876543210",
    }
    payload.update(overrides)
    return client.post(f"/api/v1/events/public/{slug}/register", json=payload)


def get_checkin_token(registration_id: str) -> str:
    with SessionLocal() as db:
        reg = db.get(EventRegistration, registration_id)
        return reg.checkin_token


class TestEventCRUD:
    def test_create_defaults_to_draft_and_public_page_404s(self, client, admin):
        event = make_event(client, admin).json()["data"]
        assert event["status"] == "draft"
        resp = client.get("/api/v1/events/public/investor-meet-2026")
        assert resp.status_code == 404

    def test_publish_makes_it_public(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        resp = client.get("/api/v1/events/public/investor-meet-2026")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "published"

    def test_slug_must_be_unique(self, client, admin):
        make_event(client, admin)
        resp = make_event(client, admin, name="Another Event")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "slug_taken"

    def test_slug_is_immutable(self, client, admin):
        event = make_event(client, admin).json()["data"]
        resp = client.patch(
            f"/api/v1/events/{event['id']}", headers=admin, json={"slug": "changed-slug"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["slug"] == "investor-meet-2026"

    def test_speakers_and_agenda_cms(self, client, admin):
        event = make_event(client, admin).json()["data"]
        speaker = client.post(
            f"/api/v1/events/{event['id']}/speakers", headers=admin,
            json={"name": "Aditya Rao", "title": "Chief Investment Officer"},
        ).json()["data"]
        assert speaker["name"] == "Aditya Rao"

        agenda = client.post(
            f"/api/v1/events/{event['id']}/agenda", headers=admin,
            json={
                "start_time": "2026-08-01T10:30:00Z", "title": "Keynote",
                "speaker_id": speaker["id"],
            },
        ).json()["data"]
        assert agenda["title"] == "Keynote"

        publish(client, admin, event["id"])
        public = client.get("/api/v1/events/public/investor-meet-2026").json()["data"]
        assert public["speakers"][0]["name"] == "Aditya Rao"
        assert public["agenda_items"][0]["title"] == "Keynote"

        client.delete(f"/api/v1/events/{event['id']}/speakers/{speaker['id']}", headers=admin)
        after = client.get(f"/api/v1/events/{event['id']}", headers=admin).json()["data"]
        assert after["speakers"] == []


class TestPublicRegistration:
    def test_register_creates_a_crm_lead(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])

        resp = register_public(client)
        assert resp.status_code == 201, resp.text
        registration = resp.json()["data"]
        assert registration["stage"] == "registered"
        assert registration["lead_id"] is not None

        lead = client.get(f"/api/v1/leads/{registration['lead_id']}", headers=admin).json()["data"]
        assert lead["source"] == "event"
        assert lead["campaign"] == "Investor Meet 2026"
        assert lead["full_name"] == "Priya Investor"

    def test_duplicate_email_blocked(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        register_public(client)
        resp = register_public(client, full_name="Someone Else")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "already_registered"

    def test_confirmation_email_and_whatsapp_sent(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        register_public(client)

        with SessionLocal() as db:
            email = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "event_confirmation")
            ).first()
            assert email is not None and email.sent is True
            wa = db.scalars(
                select(WhatsAppOutbox).where(WhatsAppOutbox.category == "event_confirmation")
            ).first()
            assert wa is not None and wa.sent is True

    def test_confirmation_email_has_a_valid_ics_calendar_invite(self, client, admin, monkeypatch):
        from app.modules import events as events_pkg

        captured = {}
        real_send_email = events_pkg.service.send_email

        def spy_send_email(db, *, to, subject, body, category, attachment=None):
            if category == "event_confirmation":
                captured["attachment"] = attachment
            return real_send_email(
                db, to=to, subject=subject, body=body, category=category, attachment=attachment
            )

        monkeypatch.setattr(events_pkg.service, "send_email", spy_send_email)

        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        register_public(client)

        attachment = captured.get("attachment")
        assert attachment is not None
        assert attachment.filename == "event_invite.ics"
        assert attachment.mimetype == "text/calendar"

        from icalendar import Calendar
        parsed = Calendar.from_ical(attachment.content)
        vevent = next(iter(parsed.walk("VEVENT")))
        assert str(vevent["summary"]) == "Investor Meet 2026"
        assert vevent["dtstart"].dt.tzinfo is not None  # real UTC, not a floating time

    def test_referral_linkage_and_count(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        referrer = register_public(client).json()["data"]

        resp = register_public(
            client, full_name="Rahul Friend", email="rahul@x.com", phone="9876500001",
            ref=referrer["referral_code"],
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["referred_by_code"] == referrer["referral_code"]

        count = client.get(
            f"/api/v1/events/public/investor-meet-2026/referrals/{referrer['referral_code']}/count"
        ).json()["data"]["count"]
        assert count == 1

    def test_public_qr_lookup_by_own_token(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        registration = register_public(client).json()["data"]

        resp = client.get(
            f"/api/v1/events/public/investor-meet-2026/qr",
            params={"token": registration["checkin_token"]},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_public_qr_lookup_rejects_bad_token(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        register_public(client)

        resp = client.get(
            "/api/v1/events/public/investor-meet-2026/qr", params={"token": "not-a-real-token"}
        )
        assert resp.status_code == 404

    def test_rsvp_confirm_public(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        registration = register_public(client).json()["data"]
        token = get_checkin_token(registration["id"])

        resp = client.post(
            "/api/v1/events/public/investor-meet-2026/rsvp", json={"token": token}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["stage"] == "rsvp_confirmed"


class TestCheckinAndBadges:
    def _setup(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        registration = register_public(client).json()["data"]
        return event, registration

    def test_checkin_marks_attended_and_advances_lead(self, client, admin):
        event, registration = self._setup(client, admin)
        token = get_checkin_token(registration["id"])

        resp = client.post(
            f"/api/v1/events/{event['id']}/checkin", headers=admin, json={"token": token}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["stage"] == "attended"
        assert resp.json()["data"]["checked_in_at"] is not None

        lead = client.get(
            f"/api/v1/leads/{registration['lead_id']}", headers=admin
        ).json()["data"]
        assert lead["stage"] == "interested"

    def test_checkin_is_idempotent(self, client, admin):
        event, registration = self._setup(client, admin)
        token = get_checkin_token(registration["id"])

        first = client.post(
            f"/api/v1/events/{event['id']}/checkin", headers=admin, json={"token": token}
        ).json()["data"]
        second = client.post(
            f"/api/v1/events/{event['id']}/checkin", headers=admin, json={"token": token}
        ).json()["data"]
        assert first["checked_in_at"] == second["checked_in_at"]

    def test_checkin_unknown_token_404s(self, client, admin):
        event, _ = self._setup(client, admin)
        resp = client.post(
            f"/api/v1/events/{event['id']}/checkin", headers=admin, json={"token": "bogus"}
        )
        assert resp.status_code == 404

    def test_badge_pdf_generated(self, client, admin):
        event, registration = self._setup(client, admin)
        resp = client.get(
            f"/api/v1/events/{event['id']}/registrations/{registration['id']}/badge.pdf",
            headers=admin,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"


class TestDashboard:
    def test_metrics_and_cost_per_lead(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        client.patch(
            f"/api/v1/events/{event['id']}", headers=admin, json={"total_ad_spend": 10000}
        )

        reg_a = register_public(client).json()["data"]
        register_public(client, full_name="Rahul", email="rahul@x.com", phone="9876500001")

        token = get_checkin_token(reg_a["id"])
        client.post(f"/api/v1/events/{event['id']}/checkin", headers=admin, json={"token": token})

        dash = client.get(f"/api/v1/events/{event['id']}/dashboard", headers=admin).json()["data"]
        assert dash["total_registrations"] == 2
        assert dash["attended"] == 1
        assert dash["attendance_rate"] == 50.0
        assert float(dash["cost_per_lead"]) == 5000.0
        assert dash["by_source"] == {"event": 2}


class TestPermissions:
    def test_sales_executive_can_checkin_but_not_create_event(self, client, admin):
        create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        rep_h = auth_headers(client, "rep@stail.com")

        blocked = make_event(client, rep_h)
        assert blocked.status_code == 403

        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        registration = register_public(client).json()["data"]
        token = get_checkin_token(registration["id"])

        allowed = client.post(
            f"/api/v1/events/{event['id']}/checkin", headers=rep_h, json={"token": token}
        )
        assert allowed.status_code == 200

    def test_public_endpoints_need_no_auth(self, client, admin):
        event = make_event(client, admin).json()["data"]
        publish(client, admin, event["id"])
        # No Authorization header at all.
        resp = client.get("/api/v1/events/public/investor-meet-2026")
        assert resp.status_code == 200


class TestPostEventFollowUp:
    def test_no_shows_marked_and_followups_sent(self, client, admin):
        event_resp = make_event(
            client, admin,
            start_at="2020-01-01T10:00:00Z", end_at="2020-01-01T13:00:00Z",
        )
        event = event_resp.json()["data"]
        publish(client, admin, event["id"])

        attendee = register_public(client).json()["data"]
        no_show = register_public(
            client, full_name="Ghost", email="ghost@x.com", phone="9876500002"
        ).json()["data"]

        token = get_checkin_token(attendee["id"])
        client.post(f"/api/v1/events/{event['id']}/checkin", headers=admin, json={"token": token})

        run_post_event_followups()

        with SessionLocal() as db:
            ev = db.get(Event, event["id"])
            assert ev.follow_up_sent_at is not None
            assert ev.status == "completed"

            reg_no_show = db.get(EventRegistration, no_show["id"])
            assert reg_no_show.stage == "no_show"

            followups = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "event_followup")
            ).all()
            assert len(followups) == 2
            subjects = {f.subject for f in followups}
            assert any("Thanks for attending" in s for s in subjects)
            assert any("missed you" in s for s in subjects)

    def test_does_not_reprocess_already_followed_up_events(self, client, admin):
        event = make_event(
            client, admin,
            start_at="2020-01-01T10:00:00Z", end_at="2020-01-01T13:00:00Z",
        ).json()["data"]
        publish(client, admin, event["id"])
        register_public(client)

        run_post_event_followups()
        run_post_event_followups()  # second sweep must be a no-op

        with SessionLocal() as db:
            count = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "event_followup")
            ).all()
            assert len(count) == 1  # not doubled


def _iso(hours_from_now: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours_from_now)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


class TestEventReminders:
    def test_48h_reminder_fires_once_for_event_36h_out(self, client, admin):
        event = make_event(
            client, admin, start_at=_iso(36), end_at=_iso(39),
        ).json()["data"]
        publish(client, admin, event["id"])
        register_public(client)

        run_event_reminders()

        with SessionLocal() as db:
            reg = db.scalars(
                select(EventRegistration).where(EventRegistration.event_id == event["id"])
            ).first()
            assert reg.reminder_48h_sent_at is not None
            assert reg.reminder_24h_sent_at is None
            reminders = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "event_reminder")
            ).all()
            assert len(reminders) == 1

        run_event_reminders()  # second sweep must not re-send
        with SessionLocal() as db:
            reminders = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "event_reminder")
            ).all()
            assert len(reminders) == 1

    def test_event_12h_out_gets_exactly_one_reminder_with_correct_copy(self, client, admin):
        # A late registrant (or post-downtime sweep) must get ONE reminder
        # matching actual proximity — never a stale "48 hours" plus a
        # "24 hours" back-to-back.
        event = make_event(
            client, admin, start_at=_iso(12), end_at=_iso(15),
        ).json()["data"]
        publish(client, admin, event["id"])
        register_public(client)

        run_event_reminders()

        with SessionLocal() as db:
            reg = db.scalars(
                select(EventRegistration).where(EventRegistration.event_id == event["id"])
            ).first()
            assert reg.reminder_24h_sent_at is not None
            assert reg.reminder_48h_sent_at is not None  # marked superseded, not pending
            reminders = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "event_reminder")
            ).all()
            assert len(reminders) == 1
            assert "24 hours" in reminders[0].subject

        run_event_reminders()  # still exactly one after another sweep
        with SessionLocal() as db:
            reminders = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "event_reminder")
            ).all()
            assert len(reminders) == 1

    def test_reminder_skipped_once_checked_in(self, client, admin):
        event = make_event(
            client, admin, start_at=_iso(12), end_at=_iso(15),
        ).json()["data"]
        publish(client, admin, event["id"])
        registration = register_public(client).json()["data"]
        token = get_checkin_token(registration["id"])
        client.post(f"/api/v1/events/{event['id']}/checkin", headers=admin, json={"token": token})

        run_event_reminders()

        with SessionLocal() as db:
            reminders = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "event_reminder")
            ).all()
            assert len(reminders) == 0

    def test_no_reminder_for_event_more_than_48h_out(self, client, admin):
        event = make_event(
            client, admin, start_at=_iso(72), end_at=_iso(75),
        ).json()["data"]
        publish(client, admin, event["id"])
        register_public(client)

        run_event_reminders()

        with SessionLocal() as db:
            reminders = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "event_reminder")
            ).all()
            assert len(reminders) == 0
