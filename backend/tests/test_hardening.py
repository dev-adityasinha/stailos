"""Verification for the production-hardening pass: workload-balanced
auto-assignment, lead stage history + reopen guard, campaign reports, and
the site-visit scheduler (calendar event + ICS invite email)."""
import io

from sqlalchemy import event, select

from app.db.base import SessionLocal, engine
from app.modules.auth.models import EmailOutbox
from tests.conftest import auth_headers, create_user_as_admin
from tests.test_leads import make_lead
from tests.test_phase3 import make_customer, make_project


class TestAutoAssignment:
    def test_workload_balanced_assignment(self, client, admin):
        rep_a = create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        rep_b = create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")
        leads = [
            make_lead(
                client, admin, phone=f"90000000{i:02d}", email=f"x{i}@y.com", force=True
            ).json()["data"]
            for i in range(4)
        ]
        counts: dict[str, int] = {}
        for lead in leads:
            counts[lead["assigned_to"]] = counts.get(lead["assigned_to"], 0) + 1
        assert set(counts) == {rep_a["id"], rep_b["id"]}
        assert counts[rep_a["id"]] == 2
        assert counts[rep_b["id"]] == 2

    def test_explicit_assignment_still_honored_for_admin(self, client, admin):
        rep = create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        lead = make_lead(client, admin, assigned_to=rep["id"]).json()["data"]
        assert lead["assigned_to"] == rep["id"]

    def test_non_manager_self_assigns_regardless_of_auto_assign(self, client, admin):
        rep = create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")
        rep_h = auth_headers(client, "repa@stail.com")
        lead = make_lead(
            client, rep_h, phone="9000000099", email="z@z.com"
        ).json()["data"]
        assert lead["assigned_to"] == rep["id"]

    def test_no_eligible_candidates_falls_back_to_creator(self, client, admin):
        # No sales_executive/telecaller users exist yet — creator keeps the lead.
        lead = make_lead(client, admin).json()["data"]
        assert lead["assigned_to"] is not None

    def test_csv_import_distributes_with_batched_assignment_pool(self, client, admin):
        """CSV import must still balance correctly when using a pre-built,
        shared assignment pool instead of querying per row."""
        rep_a = create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        rep_b = create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")

        rows = "\n".join(f"Import Lead {i},90000{i:05d},i{i}@x.com,website" for i in range(10))
        csv_content = "full_name,phone,email,source\n" + rows + "\n"

        resp = client.post(
            "/api/v1/leads/import", headers=admin,
            files={"file": ("leads.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["imported"] == 10

        leads = client.get("/api/v1/leads?limit=25", headers=admin).json()["data"]
        counts: dict[str, int] = {}
        for lead in leads:
            if lead["assigned_to"] in (rep_a["id"], rep_b["id"]):
                counts[lead["assigned_to"]] = counts.get(lead["assigned_to"], 0) + 1
        assert counts.get(rep_a["id"], 0) == 5
        assert counts.get(rep_b["id"], 0) == 5

    def test_assignment_pool_is_queried_once_not_per_pick(self, client, admin):
        """The old implementation issued 2 fresh queries (candidates +
        workload counts) on every single `_pick_auto_assignee()` call — for
        a 50,000-row CSV import that's up to 100,000 extra queries. Verify
        directly, at the unit level (isolated from the rest of a request's
        query traffic), that once a pool is built, repeated picks issue zero
        additional queries and still balance correctly."""
        from app.core.deps import AccessContext
        from app.core.permissions import Scope
        from app.modules.auth.models import User
        from app.modules.leads.service import build_auto_assign_pool, _pick_auto_assignee

        rep_a = create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        rep_b = create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")

        with SessionLocal() as db:
            admin_user = db.scalars(
                select(User).where(User.email == "admin@stail.com")
            ).first()
            ctx = AccessContext(user=admin_user, scope=Scope.ALL)

            pool = build_auto_assign_pool(db, ctx)
            assert pool is not None
            candidates, _ = pool
            assert set(candidates) == {rep_a["id"], rep_b["id"]}

            query_count = 0

            def _count(*_args, **_kwargs):
                nonlocal query_count
                query_count += 1

            event.listen(engine, "before_cursor_execute", _count)
            try:
                picks = [_pick_auto_assignee(db, ctx, pool=pool) for _ in range(10)]
            finally:
                event.remove(engine, "before_cursor_execute", _count)

            assert query_count == 0, f"expected zero queries reusing a pool, got {query_count}"
            assert picks.count(rep_a["id"]) == 5
            assert picks.count(rep_b["id"]) == 5


class TestStageHistoryAndReopen:
    def test_stage_history_recorded_in_order(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
            json={"stage": "contacted"},
        )
        client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
            json={"stage": "qualified"},
        )
        history = client.get(
            f"/api/v1/pipeline/leads/{lead['id']}/stage-history", headers=admin
        ).json()["data"]
        assert [h["to_stage"] for h in history] == ["contacted", "qualified"]
        assert history[0]["from_stage"] == "new"

    def test_reopen_required_to_leave_terminal_stage(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
            json={"stage": "lost", "lost_reason": "No budget"},
        )
        blocked = client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
            json={"stage": "contacted"},
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "lead_reopen_required"

        reopened = client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
            json={"stage": "contacted", "reopen": True},
        )
        assert reopened.status_code == 200
        assert reopened.json()["data"]["stage"] == "contacted"


class TestCampaignReport:
    def test_campaign_report_groups_by_source(self, client, admin):
        make_lead(client, admin, source="meta_ads", campaign="summer-2026")
        make_lead(
            client, admin, source="meta_ads", campaign="summer-2026",
            phone="9000000005", email="c@c.com", force=True,
        )
        make_lead(
            client, admin, source="referral", phone="9000000006", email="d@d.com", force=True,
        )
        resp = client.post(
            "/api/v1/reports/generate", headers=admin,
            json={"type": "campaign", "format": "csv"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["x-row-count"] == "2"
        body = resp.text
        assert "meta_ads" in body and "referral" in body

    def test_catalog_lists_campaign_type(self, client, admin):
        resp = client.get("/api/v1/reports/catalog", headers=admin)
        assert "campaign" in resp.json()["data"]["types"]


class TestSiteVisitScheduler:
    def test_schedule_site_visit_creates_event_advances_stage_and_emails_ics(
        self, client, admin
    ):
        lead = make_lead(client, admin).json()["data"]
        resp = client.post(
            f"/api/v1/leads/{lead['id']}/schedule-site-visit", headers=admin,
            json={
                "start_at": "2026-08-01T10:00:00Z",
                "end_at": "2026-08-01T11:00:00Z",
                "location": "Model flat, Tower B",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["lead"]["stage"] == "site_visit_scheduled"
        assert data["event"]["type"] == "site_visit"
        assert data["event"]["location"] == "Model flat, Tower B"

        with SessionLocal() as db:
            invite = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "calendar_invite")
            ).first()
            assert invite is not None
            assert invite.sent is True

        history = client.get(
            f"/api/v1/pipeline/leads/{lead['id']}/stage-history", headers=admin
        ).json()["data"]
        assert history[-1]["to_stage"] == "site_visit_scheduled"

    def test_schedule_site_visit_on_closed_lead_does_not_reopen_pipeline(
        self, client, admin
    ):
        lead = make_lead(client, admin).json()["data"]
        client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
            json={"stage": "lost", "lost_reason": "not interested"},
        )
        resp = client.post(
            f"/api/v1/leads/{lead['id']}/schedule-site-visit", headers=admin,
            json={"start_at": "2026-08-01T10:00:00Z"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["lead"]["stage"] == "lost"


class TestBookingStageHistorySync:
    """The booking workflow drives a lead's stage as a side effect
    (site_visit_scheduled on create, booked/completed on advance) without
    going through the pipeline endpoint — it must still write LeadStageEvent
    rows so GET stage-history stays complete for leads reached via bookings."""

    def _setup_booking(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        make_project(client, admin)
        unit = client.get("/api/v1/properties", headers=admin).json()["data"][0]
        customer = make_customer(client, admin).json()["data"]
        booking = client.post(
            "/api/v1/bookings", headers=admin,
            json={
                "customer_id": customer["id"], "unit_id": unit["id"],
                "lead_id": lead["id"], "total_value": 11000000, "token_amount": 500000,
            },
        ).json()["data"]
        return lead, booking

    def test_booking_create_writes_stage_history(self, client, admin):
        lead, booking = self._setup_booking(client, admin)
        assert booking["stage"] == "site_visit"

        updated_lead = client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]
        assert updated_lead["stage"] == "site_visit_scheduled"

        history = client.get(
            f"/api/v1/pipeline/leads/{lead['id']}/stage-history", headers=admin
        ).json()["data"]
        assert [h["to_stage"] for h in history] == ["site_visit_scheduled"]
        assert history[0]["from_stage"] == "new"

    def test_booking_advance_to_booked_and_completed_writes_stage_history(
        self, client, admin
    ):
        lead, booking = self._setup_booking(client, admin)
        client.post(
            f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={}
        )
        history = client.get(
            f"/api/v1/pipeline/leads/{lead['id']}/stage-history", headers=admin
        ).json()["data"]
        assert [h["to_stage"] for h in history] == ["site_visit_scheduled", "booked"]

        updated_lead = client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]
        assert updated_lead["stage"] == "booked"

    def test_booking_bypasses_reopen_guard_by_design(self, client, admin):
        """Booking progression is a distinct, already-authorized workflow —
        it intentionally does not enforce the pipeline's reopen guard, so a
        lead marked lost can still be carried through an active booking."""
        lead = make_lead(client, admin).json()["data"]
        client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
            json={"stage": "lost", "lost_reason": "changed mind"},
        )
        make_project(client, admin)
        unit = client.get("/api/v1/properties", headers=admin).json()["data"][0]
        customer = make_customer(client, admin).json()["data"]
        resp = client.post(
            "/api/v1/bookings", headers=admin,
            json={
                "customer_id": customer["id"], "unit_id": unit["id"],
                "lead_id": lead["id"], "total_value": 11000000, "token_amount": 500000,
            },
        )
        assert resp.status_code == 201, resp.text
        updated_lead = client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]
        assert updated_lead["stage"] == "site_visit_scheduled"


class TestReminderSweepIsolation:
    def test_one_users_failure_does_not_block_reminders_for_others(
        self, client, admin, monkeypatch
    ):
        """The scheduler sweep used to wrap every user in one try/except with
        a single commit at the end — one bad row rolled back (and silently
        dropped) reminders already staged for every other user that cycle.
        Verify a per-user exception doesn't stop the sweep from reaching
        subsequent users."""
        from app.modules import notifications
        from app.modules.notifications.service import run_due_reminders_for_all_users

        create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")

        seen: list[str] = []
        real = notifications.service.generate_due_reminders

        def flaky(db, user):
            seen.append(user.email)
            if user.email == "admin@stail.com":
                raise RuntimeError("simulated failure for this user only")
            return real(db, user)

        monkeypatch.setattr(notifications.service, "generate_due_reminders", flaky)

        run_due_reminders_for_all_users()

        assert set(seen) == {"admin@stail.com", "repa@stail.com"}
