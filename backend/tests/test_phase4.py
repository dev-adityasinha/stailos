"""Phase 4 verification: tasks, calendar, notifications."""
import io
from datetime import datetime, timedelta, timezone

from tests.conftest import auth_headers, create_user_as_admin
from tests.test_leads import make_lead


def iso(dt: datetime) -> str:
    return dt.isoformat()


NOW = datetime.now(timezone.utc)


class TestTasks:
    def test_crud_with_comments(self, client, admin):
        resp = client.post(
            "/api/v1/tasks", headers=admin,
            json={"title": "Call Rahul about site visit", "priority": "high",
                  "due_date": iso(NOW + timedelta(days=1))},
        )
        assert resp.status_code == 201, resp.text
        task = resp.json()["data"]
        assert task["priority"] == "high" and task["status"] == "todo"

        resp = client.patch(
            f"/api/v1/tasks/{task['id']}", headers=admin, json={"status": "done"}
        )
        assert resp.json()["data"]["completed_at"] is not None

        resp = client.post(
            f"/api/v1/tasks/{task['id']}/comments", headers=admin,
            json={"body": "Done, customer confirmed for Saturday."},
        )
        assert resp.status_code == 201
        task_now = client.get(f"/api/v1/tasks/{task['id']}", headers=admin).json()["data"]
        assert len(task_now["comments"]) == 1

        assert client.delete(f"/api/v1/tasks/{task['id']}", headers=admin).status_code == 200
        assert client.get(f"/api/v1/tasks/{task['id']}", headers=admin).status_code == 404

    def test_attachment_upload_and_type_guard(self, client, admin):
        task = client.post(
            "/api/v1/tasks", headers=admin, json={"title": "Upload brochure"}
        ).json()["data"]
        ok = client.post(
            f"/api/v1/tasks/{task['id']}/attachments", headers=admin,
            files={"file": ("brochure.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
        assert ok.status_code == 201, ok.text
        assert ok.json()["data"]["filename"] == "brochure.pdf"
        bad = client.post(
            f"/api/v1/tasks/{task['id']}/attachments", headers=admin,
            files={"file": ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        )
        assert bad.status_code == 400

    def test_assignment_creates_notification(self, client, admin):
        rep = create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        client.post(
            "/api/v1/tasks", headers=admin,
            json={"title": "Follow up with walk-in", "assigned_to": rep["id"]},
        )
        rep_h = auth_headers(client, "rep@stail.com")
        notifications = client.get("/api/v1/notifications", headers=rep_h).json()
        assert any(
            n["type"] == "task" and "Follow up with walk-in" in n["title"]
            for n in notifications["data"]
        )

    def test_overdue_filter_and_scope(self, client, admin):
        create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        rep_h = auth_headers(client, "rep@stail.com")
        client.post(
            "/api/v1/tasks", headers=rep_h,
            json={"title": "Overdue task", "due_date": iso(NOW - timedelta(days=2))},
        )
        overdue = client.get("/api/v1/tasks?overdue=true", headers=rep_h).json()
        assert overdue["meta"]["total"] == 1
        # Another rep (no shared manager) sees nothing.
        create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")
        rep_b = auth_headers(client, "repb@stail.com")
        assert client.get("/api/v1/tasks", headers=rep_b).json()["meta"]["total"] == 0


class TestCalendar:
    def test_event_crud_and_validation(self, client, admin):
        resp = client.post(
            "/api/v1/calendar", headers=admin,
            json={"title": "Site visit — Prestige Lakeside", "type": "site_visit",
                  "start_at": iso(NOW + timedelta(days=2)),
                  "end_at": iso(NOW + timedelta(days=2, hours=1)),
                  "location": "Whitefield"},
        )
        assert resp.status_code == 201, resp.text
        event = resp.json()["data"]

        bad = client.post(
            "/api/v1/calendar", headers=admin,
            json={"title": "Backwards", "start_at": iso(NOW + timedelta(hours=2)),
                  "end_at": iso(NOW + timedelta(hours=1))},
        )
        assert bad.status_code == 422

        resp = client.patch(
            f"/api/v1/calendar/{event['id']}", headers=admin, json={"status": "done"}
        )
        assert resp.json()["data"]["status"] == "done"
        assert client.delete(f"/api/v1/calendar/{event['id']}", headers=admin).status_code == 200

    def test_range_filter_and_attendees(self, client, admin):
        rep = create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        client.post(
            "/api/v1/calendar", headers=admin,
            json={"title": "Team standup", "type": "meeting",
                  "start_at": iso(NOW + timedelta(days=1)), "attendee_ids": [rep["id"]]},
        )
        client.post(
            "/api/v1/calendar", headers=admin,
            json={"title": "Next month planning", "type": "meeting",
                  "start_at": iso(NOW + timedelta(days=40))},
        )
        week = client.get(
            "/api/v1/calendar",
            params={"start": iso(NOW), "end": iso(NOW + timedelta(days=7))},
            headers=admin,
        ).json()
        assert week["meta"]["total"] == 1
        # Attendee sees the event in their personal view.
        rep_h = auth_headers(client, "rep@stail.com")
        mine = client.get("/api/v1/calendar", headers=rep_h).json()
        assert mine["meta"]["total"] == 1
        assert mine["data"][0]["title"] == "Team standup"

    def test_owner_only_edit_for_own_scope(self, client, admin):
        create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")
        rep_a, rep_b = auth_headers(client, "repa@stail.com"), auth_headers(client, "repb@stail.com")
        event = client.post(
            "/api/v1/calendar", headers=rep_a,
            json={"title": "My call", "type": "call", "start_at": iso(NOW + timedelta(hours=3))},
        ).json()["data"]
        resp = client.patch(
            f"/api/v1/calendar/{event['id']}", headers=rep_b, json={"title": "Hijacked"}
        )
        assert resp.status_code == 404  # not even visible to B


class TestNotifications:
    def test_lead_assignment_notifies_assignee(self, client, admin):
        rep = create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        lead = make_lead(client, admin).json()["data"]
        client.post(
            f"/api/v1/leads/{lead['id']}/assign", headers=admin, json={"user_id": rep["id"]}
        )
        rep_h = auth_headers(client, "rep@stail.com")
        data = client.get("/api/v1/notifications", headers=rep_h).json()
        assert data["meta"]["unread"] >= 1
        assert any(n["type"] == "assignment" for n in data["data"])

    def test_due_soon_reminder_generated_once(self, client, admin):
        client.post(
            "/api/v1/tasks", headers=admin,
            json={"title": "Urgent follow-up", "due_date": iso(NOW + timedelta(hours=2))},
        )
        first = client.get("/api/v1/notifications", headers=admin).json()
        reminders = [n for n in first["data"] if n["type"] == "follow_up"]
        assert len(reminders) == 1
        # Second fetch must not duplicate (dedupe_key).
        second = client.get("/api/v1/notifications", headers=admin).json()
        reminders2 = [n for n in second["data"] if n["type"] == "follow_up"]
        assert len(reminders2) == 1

    def test_mark_read_and_read_all(self, client, admin):
        rep = create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        lead = make_lead(client, admin).json()["data"]
        client.post(
            f"/api/v1/leads/{lead['id']}/assign", headers=admin, json={"user_id": rep["id"]}
        )
        rep_h = auth_headers(client, "rep@stail.com")
        data = client.get("/api/v1/notifications", headers=rep_h).json()
        nid = data["data"][0]["id"]
        resp = client.patch(f"/api/v1/notifications/{nid}/read", headers=rep_h)
        assert resp.json()["data"]["read"] is True
        client.post("/api/v1/notifications/read-all", headers=rep_h)
        after = client.get("/api/v1/notifications", headers=rep_h).json()
        assert after["meta"]["unread"] == 0

    def test_cannot_read_others_notifications(self, client, admin):
        rep = create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        lead = make_lead(client, admin).json()["data"]
        client.post(
            f"/api/v1/leads/{lead['id']}/assign", headers=admin, json={"user_id": rep["id"]}
        )
        rep_h = auth_headers(client, "rep@stail.com")
        nid = client.get("/api/v1/notifications", headers=rep_h).json()["data"][0]["id"]
        # Admin (different user) cannot mark the rep's notification.
        assert client.patch(f"/api/v1/notifications/{nid}/read", headers=admin).status_code == 404

    def test_booking_stage_change_notifies(self, client, admin):
        from tests.test_phase3 import make_customer, make_project

        make_project(client, admin)
        units = client.get("/api/v1/properties", headers=admin).json()["data"]
        customer = make_customer(client, admin).json()["data"]
        booking = client.post(
            "/api/v1/bookings", headers=admin,
            json={"customer_id": customer["id"], "unit_id": units[0]["id"],
                  "total_value": 7500000},
        ).json()["data"]
        client.post(f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={})
        data = client.get("/api/v1/notifications", headers=admin).json()
        assert any(n["type"] == "booking_update" for n in data["data"])
