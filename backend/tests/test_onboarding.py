"""Onboarding module: step save/state, completion side effects (properties, team invites)."""
import re

from sqlalchemy import select

from app.db.base import SessionLocal
from app.modules.auth.models import EmailOutbox
from tests.conftest import STRONG_PASSWORD, auth_headers, create_user_as_admin
from tests.conftest import admin  # noqa: F401  (fixture)


class TestOnboardingStepPersistence:
    def test_multiple_steps_accumulate(self, client, admin):
        # Regression test: update_onboarding_step used to alias
        # `tenant.onboarding_data` instead of copying it, then mutate that
        # alias in place before reassigning — which corrupted SQLAlchemy's
        # change-tracking baseline and silently dropped every step after the
        # first one saved. Two sequential PATCHes must both persist.
        resp = client.patch(
            "/api/v1/onboarding/step",
            headers=admin,
            json={"step_id": 1, "data": {"companyName": "Multi Step Co"}},
        )
        assert resp.status_code == 200, resp.text

        resp = client.patch(
            "/api/v1/onboarding/step",
            headers=admin,
            json={"step_id": 2, "data": {"projects": [{"name": "Regression Tower"}]}},
        )
        assert resp.status_code == 200, resp.text

        state = client.get("/api/v1/onboarding/state", headers=admin).json()["data"]
        assert state["onboarding_data"]["1"]["companyName"] == "Multi Step Co"
        assert state["onboarding_data"]["2"]["projects"][0]["name"] == "Regression Tower"


class TestOnboardingCompletion:
    def test_team_invite_creates_real_user(self, client, admin):
        # Regression test: complete_onboarding used to call register_user() with a
        # mismatched signature (extra `user_agent`, missing `company_name`), which
        # raised TypeError on every invite and was silently swallowed.
        resp = client.patch(
            "/api/v1/onboarding/step",
            headers=admin,
            json={
                "step_id": 11,
                "data": {
                    "teamInvites": ["newteammate@stail.com"],
                    "permissionLevel": "Sales",
                },
            },
        )
        assert resp.status_code == 200, resp.text

        resp = client.post("/api/v1/onboarding/complete", headers=admin)
        assert resp.status_code == 200, resp.text

        users = client.get("/api/v1/users", headers=admin).json()["data"]
        emails = {u["email"] for u in users}
        assert "newteammate@stail.com" in emails
        invited = next(u for u in users if u["email"] == "newteammate@stail.com")
        assert invited["role"] == "sales_executive"

    def test_full_flow_creates_property_lead_customer_and_invite(self, client, admin):
        # Regression test: complete_onboarding previously 500'd on any CSV import
        # because it imported `normalize_phone` from a module that doesn't exist
        # (app.core.formatters — the real function lives in leads.service), and
        # separately, Customer creation raised TypeError from a `status="active"`
        # kwarg that isn't a field on the Customer model at all. Both were inside
        # try/except blocks that silently swallowed the failures. This exercises
        # every onboarding-completion side effect together, end to end.
        client.patch(
            "/api/v1/onboarding/step",
            headers=admin,
            json={"step_id": 1, "data": {"companyName": "Full Flow Realty"}},
        )
        client.patch(
            "/api/v1/onboarding/step",
            headers=admin,
            json={
                "step_id": 2,
                "data": {"projects": [{"name": "Full Flow Tower", "location": "Test City"}]},
            },
        )
        client.patch(
            "/api/v1/onboarding/step",
            headers=admin,
            json={
                "step_id": 7,
                "data": {
                    "importLeads": [
                        {
                            "first_name": "Flow",
                            "last_name": "Lead",
                            "email": "flowlead@stail.com",
                            "phone": "9999911111",
                        }
                    ],
                    "importCustomers": [
                        {
                            "first_name": "Flow",
                            "last_name": "Customer",
                            "email": "flowcustomer@stail.com",
                            "phone": "9999922222",
                        }
                    ],
                },
            },
        )

        resp = client.post("/api/v1/onboarding/complete", headers=admin)
        assert resp.status_code == 200, resp.text

        properties = client.get("/api/v1/properties", headers=admin).json()
        assert properties["meta"]["total"] == 1
        assert properties["data"][0]["project"]["name"] == "Full Flow Tower"

        leads = client.get("/api/v1/leads", headers=admin).json()["data"]
        assert any(l["full_name"] == "Flow Lead" for l in leads)

        customers = client.get("/api/v1/customers", headers=admin).json()["data"]
        assert any(c["full_name"] == "Flow Customer" for c in customers)


class TestOnboardingRBAC:
    def test_non_admin_cannot_touch_onboarding(self, client, admin):
        create_user_as_admin(client, admin, "caller@stail.com", "telecaller")
        caller = auth_headers(client, "caller@stail.com")

        assert client.get("/api/v1/onboarding/state", headers=caller).status_code == 403
        resp = client.patch(
            "/api/v1/onboarding/step", headers=caller,
            json={"step_id": 1, "data": {"companyName": "Hijacked Name"}},
        )
        assert resp.status_code == 403
        assert client.post("/api/v1/onboarding/complete", headers=caller).status_code == 403

        # Tenant name must be untouched by the failed rename attempt.
        me = client.get("/api/v1/auth/me", headers=admin).json()["data"]
        assert me["tenant_name"] != "Hijacked Name"


class TestTenantContextOnAuth:
    def test_me_and_login_include_tenant_fields(self, client, admin):
        me = client.get("/api/v1/auth/me", headers=admin).json()["data"]
        assert me["tenant_name"] is not None
        assert me["onboarding_completed"] is False  # fresh tenant, not onboarded

        client.post("/api/v1/onboarding/complete", headers=admin)
        me = client.get("/api/v1/auth/me", headers=admin).json()["data"]
        assert me["onboarding_completed"] is True

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@stail.com", "password": STRONG_PASSWORD},
        ).json()["data"]
        assert login["user"]["tenant_name"] is not None
        assert login["user"]["onboarding_completed"] is True


class TestTeamInviteEmail:
    def test_invitee_gets_invite_email_and_can_set_password_and_login(self, client, admin):
        client.patch(
            "/api/v1/onboarding/step", headers=admin,
            json={
                "step_id": 11,
                "data": {"teamInvites": ["invitee@stail.com"], "permissionLevel": "Manager"},
            },
        )
        resp = client.post("/api/v1/onboarding/complete", headers=admin)
        assert resp.status_code == 200, resp.text

        with SessionLocal() as db:
            invite = db.scalars(
                select(EmailOutbox).where(
                    EmailOutbox.category == "team_invite",
                    EmailOutbox.to_email == "invitee@stail.com",
                )
            ).first()
            assert invite is not None and invite.sent is True
            match = re.search(r"reset-password\?token=([\w.\-]+)", invite.body)
            assert match, invite.body
            token = match.group(1)

        # The link must actually work: set a password, then log in with it.
        resp = client.post(
            "/api/v1/auth/password/reset",
            json={"token": token, "new_password": "Invitee!Pass123"},
        )
        assert resp.status_code == 200, resp.text

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "invitee@stail.com", "password": "Invitee!Pass123"},
        )
        assert login.status_code == 200, login.text
        assert login.json()["data"]["user"]["role"] == "sales_manager"

    def test_inviting_existing_email_is_surfaced_not_silent(self, client, admin):
        # Emails are globally unique (one account = one workspace). Inviting
        # an address that already has an account must not fail silently — the
        # completion response tells the admin exactly which invites were
        # skipped and why.
        create_user_as_admin(client, admin, "taken@stail.com", "sales_executive")
        client.patch(
            "/api/v1/onboarding/step", headers=admin,
            json={
                "step_id": 11,
                "data": {
                    "teamInvites": ["taken@stail.com", "fresh@stail.com"],
                    "permissionLevel": "Sales",
                },
            },
        )
        resp = client.post("/api/v1/onboarding/complete", headers=admin)
        assert resp.status_code == 200, resp.text
        invites = resp.json()["data"]["invites"]
        assert invites["already_exists"] == ["taken@stail.com"]
        assert invites["sent"] == ["fresh@stail.com"]
        assert invites["failed"] == []
