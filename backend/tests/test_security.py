"""Phase 8 security verification: authz sweep, IDOR, injection smoke, uploads."""
import io

from tests.conftest import STRONG_PASSWORD, auth_headers, create_user_as_admin
from tests.test_leads import make_lead
from tests.test_phase3 import make_customer, make_project

PROTECTED_GET_ENDPOINTS = [
    "/api/v1/users",
    "/api/v1/leads",
    "/api/v1/pipeline/board",
    "/api/v1/customers",
    "/api/v1/properties",
    "/api/v1/bookings",
    "/api/v1/tasks",
    "/api/v1/calendar",
    "/api/v1/notifications",
    "/api/v1/analytics/overview",
    "/api/v1/reports/catalog",
    "/api/v1/documents",
    "/api/v1/audit",
    "/api/v1/ai/catalog",
    "/api/v1/auth/sessions",
]


class TestAuthzSweep:
    def test_every_module_requires_authentication(self, client):
        for path in PROTECTED_GET_ENDPOINTS:
            resp = client.get(path)
            assert resp.status_code == 401, f"{path} returned {resp.status_code}"

    def test_invalid_and_malformed_tokens_rejected(self, client, admin):
        for token in ["garbage", "Bearer", "eyJhbGciOiJIUzI1NiJ9.e30."]:
            resp = client.get("/api/v1/leads", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 401

    def test_audit_admin_only(self, client, admin):
        create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        rep = auth_headers(client, "rep@stail.com")
        assert client.get("/api/v1/audit", headers=rep).status_code == 403
        resp = client.get("/api/v1/audit", headers=admin)
        assert resp.status_code == 200
        actions = {a["action"] for a in resp.json()["data"]}
        assert "auth.login" in actions  # audit trail is being written


class TestIDOR:
    """Cross-user direct-object-reference attempts must 404 (no info leak)."""

    def _two_reps(self, client, admin):
        create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")
        return auth_headers(client, "repa@stail.com"), auth_headers(client, "repb@stail.com")

    def test_booking_idor(self, client, admin):
        rep_a, rep_b = self._two_reps(client, admin)
        make_project(client, admin)
        unit = client.get("/api/v1/properties", headers=admin).json()["data"][0]
        customer = make_customer(client, rep_a).json()["data"]
        booking = client.post(
            "/api/v1/bookings", headers=rep_a,
            json={"customer_id": customer["id"], "unit_id": unit["id"], "total_value": 7500000},
        ).json()["data"]
        assert client.get(f"/api/v1/bookings/{booking['id']}", headers=rep_b).status_code == 404
        assert client.post(
            f"/api/v1/bookings/{booking['id']}/payments", headers=rep_b,
            json={"amount": 1},
        ).status_code == 404

    def test_task_and_note_idor(self, client, admin):
        rep_a, rep_b = self._two_reps(client, admin)
        task = client.post("/api/v1/tasks", headers=rep_a,
                           json={"title": "Private task"}).json()["data"]
        assert client.get(f"/api/v1/tasks/{task['id']}", headers=rep_b).status_code == 404
        assert client.patch(f"/api/v1/tasks/{task['id']}", headers=rep_b,
                            json={"status": "done"}).status_code == 404
        lead = make_lead(client, rep_a).json()["data"]
        assert client.post(f"/api/v1/leads/{lead['id']}/notes", headers=rep_b,
                           json={"body": "injected"}).status_code == 404

    def test_ai_widget_idor(self, client, admin):
        rep_a, rep_b = self._two_reps(client, admin)
        lead = make_lead(client, rep_a).json()["data"]
        resp = client.post("/api/v1/ai/components/lead-qualification", headers=rep_b,
                           json={"lead_id": lead["id"]})
        assert resp.status_code == 404


class TestInjectionAndInputs:
    def test_search_params_with_hostile_input_do_not_error(self, client, admin):
        make_lead(client, admin)
        for payload in ["'; DROP TABLE leads;--", '" OR 1=1 --', "%_%", "<script>x</script>"]:
            resp = client.get("/api/v1/leads", headers=admin, params={"q": payload})
            assert resp.status_code == 200, payload
            assert resp.json()["meta"]["total"] == 0
        # Table intact afterwards.
        assert client.get("/api/v1/leads", headers=admin).json()["meta"]["total"] == 1

    def test_oversized_and_wrong_type_payloads_rejected(self, client, admin):
        resp = client.post("/api/v1/leads", headers=admin,
                           json={"full_name": "x" * 500, "phone": "9876543210"})
        assert resp.status_code == 422
        resp = client.post("/api/v1/leads", headers=admin,
                           json={"full_name": "Valid Name", "phone": "9876500001",
                                 "budget_min": -5})
        assert resp.status_code == 422

    def test_upload_filename_sanitized_and_traversal_blocked(self, client, admin):
        task = client.post("/api/v1/tasks", headers=admin,
                           json={"title": "Upload test"}).json()["data"]
        resp = client.post(
            f"/api/v1/tasks/{task['id']}/attachments", headers=admin,
            files={"file": ("../../../../etc/passwd.txt", io.BytesIO(b"data"), "text/plain")},
        )
        assert resp.status_code == 201
        stored_name = resp.json()["data"]["filename"]
        assert ".." not in stored_name and "/" not in stored_name

    def test_error_envelope_has_correlation_id_and_no_stack(self, client):
        resp = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
        body = resp.json()
        assert "correlation_id" in body["error"]
        assert "Traceback" not in resp.text


class TestPrivilegeEscalation:
    def test_role_change_requires_admin(self, client, admin):
        rep = create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        create_user_as_admin(client, admin, "mgr@stail.com", "sales_manager")
        mgr = auth_headers(client, "mgr@stail.com")
        # Sales manager has users:read TEAM but must not change roles.
        resp = client.patch(f"/api/v1/users/{rep['id']}/role", headers=mgr,
                            json={"role": "company_admin"})
        assert resp.status_code == 403

    def test_non_admin_cannot_create_inventory(self, client, admin):
        create_user_as_admin(client, admin, "mkt@stail.com", "marketing_executive")
        mkt = auth_headers(client, "mkt@stail.com")
        resp = client.post("/api/v1/properties/projects", headers=mkt,
                           json={"name": "Fake Towers", "builder_name": "X",
                                 "location": "Y", "city": "Z", "units": []})
        assert resp.status_code == 403

    def test_channel_partner_minimal_surface(self, client, admin):
        create_user_as_admin(client, admin, "partner@stail.com", "channel_partner")
        partner = auth_headers(client, "partner@stail.com")
        # Can create/read own referred leads and browse inventory…
        assert make_lead(client, partner, phone="9333311111", email=None,
                         full_name="Referred Buyer").status_code == 201
        assert client.get("/api/v1/properties", headers=partner).status_code == 200
        # …but nothing else.
        assert client.get("/api/v1/customers", headers=partner).status_code == 403
        assert client.get("/api/v1/tasks", headers=partner).status_code == 403
        assert client.get("/api/v1/documents", headers=partner).status_code == 403
