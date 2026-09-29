"""Regression tests for confirmed cross-tenant (IDOR-class) bugs: a
client-supplied ID (assigned_to / lead_id) must never let one tenant's data
get linked to, or leak into, another tenant's records."""
import csv
import io

from sqlalchemy import select

from app.db.base import SessionLocal
from app.modules.auth.models import User
from app.modules.leads.models import Lead
from tests.conftest import STRONG_PASSWORD, auth_headers, create_user_as_admin, register
from tests.test_leads import make_lead
from tests.test_phase3 import make_customer, make_project


def register_tenant(client, email, name="Tenant Admin"):
    resp = register(client, email=email, name=name)
    assert resp.status_code == 201, resp.text
    return auth_headers(client, email)


class TestLeadAssignmentIsolation:
    def test_create_lead_ignores_cross_tenant_assigned_to(self, client):
        admin_a = register_tenant(client, "admin-a@tenanta.com")
        admin_b = register_tenant(client, "admin-b@tenantb.com")
        rep_b = create_user_as_admin(client, admin_b, "rep@tenantb.com", "sales_executive")

        # Tenant A admin tries to assign a new lead directly to a Tenant B user.
        lead = make_lead(
            client, admin_a, assigned_to=rep_b["id"], phone="9000001111", email="x1@y.com",
        ).json()["data"]

        assert lead["assigned_to"] != rep_b["id"]
        with SessionLocal() as db:
            row = db.get(Lead, lead["id"])
            assignee = db.get(User, row.assigned_to)
            # The lead's assignee must belong to the same tenant as the lead itself.
            assert assignee.tenant_id == row.tenant_id


class TestTaskAssignmentIsolation:
    def test_create_task_ignores_cross_tenant_assigned_to(self, client):
        admin_a = register_tenant(client, "admin-a2@tenanta.com")
        admin_b = register_tenant(client, "admin-b2@tenantb.com")
        rep_b = create_user_as_admin(client, admin_b, "rep2@tenantb.com", "sales_executive")

        resp = client.post(
            "/api/v1/tasks", headers=admin_a,
            json={"title": "Cross-tenant assignment attempt", "assigned_to": rep_b["id"]},
        )
        assert resp.status_code == 201, resp.text
        task = resp.json()["data"]
        # Falls back to the creator (tenant A admin), never the foreign user.
        assert task["assigned_to"] != rep_b["id"]

    def test_update_task_ignores_cross_tenant_assigned_to(self, client):
        admin_a = register_tenant(client, "admin-a3@tenanta.com")
        admin_b = register_tenant(client, "admin-b3@tenantb.com")
        rep_b = create_user_as_admin(client, admin_b, "rep3@tenantb.com", "sales_executive")

        task = client.post(
            "/api/v1/tasks", headers=admin_a, json={"title": "Task"}
        ).json()["data"]
        original_assignee = task["assigned_to"]

        resp = client.patch(
            f"/api/v1/tasks/{task['id']}", headers=admin_a,
            json={"assigned_to": rep_b["id"]},
        )
        assert resp.status_code == 200
        # Invalid cross-tenant assignee is dropped — original value untouched.
        assert resp.json()["data"]["assigned_to"] == original_assignee

    def test_update_task_can_still_legitimately_unassign(self, client, admin):
        task = client.post(
            "/api/v1/tasks", headers=admin, json={"title": "Task"}
        ).json()["data"]
        resp = client.patch(
            f"/api/v1/tasks/{task['id']}", headers=admin, json={"assigned_to": None}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["assigned_to"] is None


class TestBookingLeadIsolation:
    def test_create_booking_rejects_cross_tenant_lead_id(self, client):
        admin_a = register_tenant(client, "admin-a4@tenanta.com")
        admin_b = register_tenant(client, "admin-b4@tenantb.com")

        # A real lead that belongs to tenant A only.
        lead_a = make_lead(client, admin_a).json()["data"]

        # Tenant B admin sets up a project/unit/customer, then tries to link
        # tenant A's lead_id into their own booking.
        make_project(client, admin_b)
        unit = client.get("/api/v1/properties", headers=admin_b).json()["data"][0]
        customer_b = make_customer(client, admin_b).json()["data"]

        resp = client.post(
            "/api/v1/bookings", headers=admin_b,
            json={
                "customer_id": customer_b["id"], "unit_id": unit["id"],
                "lead_id": lead_a["id"], "total_value": 5000000,
            },
        )
        assert resp.status_code == 404, resp.text

        # Tenant A's lead must be completely untouched by the failed attempt.
        with SessionLocal() as db:
            row = db.get(Lead, lead_a["id"])
            assert row.stage == "new"


def _agent_leads_count(csv_text: str, agent_name: str) -> int:
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    leads_idx = header.index("Leads")
    name_idx = header.index("Agent")
    for row in reader:
        if row[name_idx] == agent_name:
            return int(row[leads_idx])
    raise AssertionError(f"{agent_name} not found in report")


class TestReportingIsolation:
    def test_agent_report_never_counts_cross_tenant_leads_even_if_assigned_to_collides(
        self, client, admin
    ):
        """Defense-in-depth check: even if a Lead row somehow ended up with
        a foreign tenant_id while assigned_to still points at a real,
        same-tenant-as-report user (a state normal API usage can no longer
        produce, per the fixes above — simulated directly at the DB layer),
        the report query must filter by the report's own tenant_id, not
        trust assigned_to alone."""
        me = client.get("/api/v1/auth/me", headers=admin).json()["data"]["full_name"]
        baseline = _agent_leads_count(
            client.post(
                "/api/v1/reports/generate", headers=admin, json={"type": "agent", "format": "csv"},
            ).text,
            me,
        )

        lead = make_lead(client, admin).json()["data"]
        after_real_lead = _agent_leads_count(
            client.post(
                "/api/v1/reports/generate", headers=admin, json={"type": "agent", "format": "csv"},
            ).text,
            me,
        )
        assert after_real_lead == baseline + 1  # sanity: the query does count real same-tenant leads

        with SessionLocal() as db:
            row = db.get(Lead, lead["id"])
            row.tenant_id = "some-other-tenant-id-entirely"  # simulate a foreign-tenant lead
            db.commit()

        after_tamper = _agent_leads_count(
            client.post(
                "/api/v1/reports/generate", headers=admin, json={"type": "agent", "format": "csv"},
            ).text,
            me,
        )
        assert after_tamper == baseline  # the now-foreign-tenant lead must drop out of the count
