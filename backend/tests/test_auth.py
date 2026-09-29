"""Phase 1 verification: authentication, sessions, RBAC."""
from sqlalchemy import select

from app.db.base import SessionLocal
from app.modules.auth.models import EmailOutbox
from tests.conftest import (
    STRONG_PASSWORD,
    auth_headers,
    create_user_as_admin,
    login,
    register,
)


class TestRegistration:
    def test_public_registration_creates_company_admin(self, client):
        resp = register(client)
        assert resp.status_code == 201
        assert resp.json()["data"]["role"] == "company_admin"

    def test_subsequent_public_registration_creates_new_tenant(self, client):
        register(client)
        resp = register(client, email="rep@stail.com", name="Rep One")
        assert resp.status_code == 201
        assert resp.json()["data"]["role"] == "company_admin"

    def test_duplicate_email_rejected(self, client):
        register(client)
        resp = register(client)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "email_taken"

    def test_weak_password_rejected(self, client):
        for weak in ["short1!A", "alllowercase123!", "NoSymbols123", "NoNumbers!!!ab"]:
            resp = register(client, email="x@y.com", password=weak)
            assert resp.status_code == 422, weak

    def test_verification_email_sent(self, client):
        register(client)
        with SessionLocal() as db:
            mail = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "email_verification")
            ).first()
            assert mail is not None
            assert "verify-email?token=" in mail.body

    def test_email_verification_flow(self, client):
        register(client)
        with SessionLocal() as db:
            mail = db.scalars(select(EmailOutbox)).first()
            token = mail.body.split("token=")[1].split()[0]
        resp = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert resp.status_code == 200
        resp = client.post("/api/v1/auth/verify-email", json={"token": "garbage"})
        assert resp.status_code == 401


class TestLogin:
    def test_login_returns_tokens_and_cookie(self, client):
        register(client)
        resp = login(client)
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["access_token"]
        assert body["data"]["user"]["email"] == "admin@stail.com"
        assert "pappu_refresh" in resp.cookies

    def test_wrong_password_rejected(self, client):
        register(client)
        resp = login(client, password="Wrong!Passw0rd1")
        assert resp.status_code == 401

    def test_unknown_email_same_error_as_wrong_password(self, client):
        register(client)
        r1 = login(client, password="Wrong!Passw0rd1")
        r2 = login(client, email="ghost@nowhere.com")
        assert r1.json()["error"]["code"] == r2.json()["error"]["code"]

    def test_lockout_after_failed_attempts(self, client):
        register(client)
        for _ in range(5):
            login(client, password="Wrong!Passw0rd1")
        resp = login(client)  # correct password, but locked now
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "account_locked"
        with SessionLocal() as db:
            alert = db.scalars(
                select(EmailOutbox).where(EmailOutbox.category == "security_alert")
            ).first()
            assert alert is not None

    def test_me_requires_auth(self, client):
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_me_with_token(self, client, admin):
        resp = client.get("/api/v1/auth/me", headers=admin)
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "company_admin"


class TestRefreshRotation:
    def test_refresh_rotates_token(self, client):
        register(client)
        refresh1 = login(client).json()["refresh_token"]
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
        assert resp.status_code == 200
        refresh2 = resp.json()["refresh_token"]
        assert refresh2 != refresh1

    def test_reuse_of_rotated_token_revokes_family(self, client):
        register(client)
        refresh1 = login(client).json()["refresh_token"]
        refresh2 = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh1}
        ).json()["refresh_token"]
        # Reusing the old token = theft signal → whole family dies.
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "refresh_reuse"
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh2})
        assert resp.status_code == 401

    def test_logout_revokes_refresh(self, client):
        register(client)
        refresh1 = login(client).json()["refresh_token"]
        client.post("/api/v1/auth/logout", json={"refresh_token": refresh1})
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
        assert resp.status_code == 401


class TestPasswordReset:
    def _get_reset_token(self):
        with SessionLocal() as db:
            mail = db.scalars(
                select(EmailOutbox)
                .where(EmailOutbox.category == "password_reset")
                .order_by(EmailOutbox.created_at.desc())
            ).first()
            return mail.body.split("token=")[1].split()[0]

    def test_full_reset_flow(self, client):
        register(client)
        resp = client.post("/api/v1/auth/password/forgot", json={"email": "admin@stail.com"})
        assert resp.status_code == 200
        token = self._get_reset_token()
        new_password = "N3w!Passw0rd##"
        resp = client.post(
            "/api/v1/auth/password/reset", json={"token": token, "new_password": new_password}
        )
        assert resp.status_code == 200
        assert login(client).status_code == 401  # old password dead
        assert login(client, password=new_password).status_code == 200

    def test_reset_token_single_use(self, client):
        register(client)
        client.post("/api/v1/auth/password/forgot", json={"email": "admin@stail.com"})
        token = self._get_reset_token()
        client.post(
            "/api/v1/auth/password/reset",
            json={"token": token, "new_password": "N3w!Passw0rd##"},
        )
        resp = client.post(
            "/api/v1/auth/password/reset",
            json={"token": token, "new_password": "An0ther!Pass##"},
        )
        assert resp.status_code == 401

    def test_forgot_password_does_not_reveal_accounts(self, client):
        resp = client.post("/api/v1/auth/password/forgot", json={"email": "ghost@x.com"})
        assert resp.status_code == 200

    def test_reset_revokes_all_sessions(self, client):
        register(client)
        refresh1 = login(client).json()["refresh_token"]
        client.post("/api/v1/auth/password/forgot", json={"email": "admin@stail.com"})
        token = self._get_reset_token()
        client.post(
            "/api/v1/auth/password/reset",
            json={"token": token, "new_password": "N3w!Passw0rd##"},
        )
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
        assert resp.status_code == 401


class TestSessions:
    def test_list_and_revoke_sessions(self, client):
        register(client)
        login(client)
        headers = auth_headers(client)
        resp = client.get("/api/v1/auth/sessions", headers=headers)
        assert resp.status_code == 200
        sessions = resp.json()["data"]
        assert len(sessions) == 2
        sid = sessions[0]["id"]
        resp = client.delete(f"/api/v1/auth/sessions/{sid}", headers=headers)
        assert resp.status_code == 200
        remaining = client.get("/api/v1/auth/sessions", headers=headers).json()["data"]
        assert len(remaining) == 1


class TestRBAC:
    def test_admin_creates_users_with_roles(self, client, admin):
        user = create_user_as_admin(client, admin, "mgr@stail.com", "sales_manager")
        assert user["role"] == "sales_manager"

    def test_sales_executive_cannot_manage_users(self, client, admin):
        create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        rep_headers = auth_headers(client, "rep@stail.com")
        assert client.get("/api/v1/users", headers=rep_headers).status_code == 403
        resp = client.post(
            "/api/v1/users",
            headers=rep_headers,
            json={
                "email": "evil@x.com",
                "password": STRONG_PASSWORD,
                "full_name": "Evil User",
                "role": "super_admin",
            },
        )
        assert resp.status_code == 403

    def test_self_registration_cannot_grant_admin_role(self, client, admin):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": "sneaky@x.com",
                "password": STRONG_PASSWORD,
                "full_name": "Sneaky User",
                "role": "super_admin",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["role"] == "company_admin"

    def test_admin_can_change_role_and_deactivate(self, client, admin):
        user = create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        resp = client.patch(
            f"/api/v1/users/{user['id']}/role", headers=admin, json={"role": "telecaller"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "telecaller"
        resp = client.delete(f"/api/v1/users/{user['id']}", headers=admin)
        assert resp.status_code == 200
        assert login(client, "rep@stail.com").status_code == 401  # deactivated

    def test_admin_cannot_deactivate_self(self, client, admin):
        me = client.get("/api/v1/auth/me", headers=admin).json()["data"]
        resp = client.delete(f"/api/v1/users/{me['id']}", headers=admin)
        assert resp.status_code == 403

    def test_admin_cannot_see_or_manage_other_tenants_users(self, client, admin):
        # `admin` bootstraps tenant A via public registration; register a second,
        # unrelated user via the same public endpoint to create isolated tenant B.
        resp = register(client, email="otherco-admin@stail.com", name="Other Co Admin")
        assert resp.status_code == 201
        other_user_id = resp.json()["data"]["id"]

        # Tenant A's admin must not see tenant B's user in the list...
        listed_ids = {u["id"] for u in client.get("/api/v1/users", headers=admin).json()["data"]}
        assert other_user_id not in listed_ids

        # ...nor fetch, edit the role of, or deactivate it directly by id.
        assert client.get(f"/api/v1/users/{other_user_id}", headers=admin).status_code == 404
        assert (
            client.patch(
                f"/api/v1/users/{other_user_id}/role", headers=admin, json={"role": "telecaller"}
            ).status_code
            == 404
        )
        assert client.delete(f"/api/v1/users/{other_user_id}", headers=admin).status_code == 404


class TestRateLimiting:
    def test_auth_endpoints_rate_limited(self, client):
        register(client)
        last = None
        for _ in range(25):
            last = client.post(
                "/api/v1/auth/login",
                json={"email": "admin@stail.com", "password": "Wrong!Passw0rd1"},
            )
        assert last.status_code == 429


class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        resp = client.get("/api/health")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
