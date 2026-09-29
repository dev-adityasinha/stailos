"""Regression tests for defects found in the production-readiness audit."""
import io

from tests.conftest import auth_headers, create_user_as_admin
from tests.test_leads import make_lead
from tests.test_phase3 import make_customer, make_project


class TestCustomer360Documents:
    def test_360_includes_customer_and_booking_documents(self, client, admin):
        make_project(client, admin)
        unit = client.get("/api/v1/properties", headers=admin).json()["data"][0]
        customer = make_customer(client, admin).json()["data"]
        booking = client.post(
            "/api/v1/bookings", headers=admin,
            json={"customer_id": customer["id"], "unit_id": unit["id"],
                  "total_value": 7500000},
        ).json()["data"]

        for title, etype, eid in [
            ("KYC PAN", "customer", customer["id"]),
            ("Booking agreement", "booking", booking["id"]),
        ]:
            resp = client.post(
                "/api/v1/documents/upload", headers=admin,
                data={"title": title, "category": "kyc", "entity_type": etype,
                      "entity_id": eid},
                files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
            )
            assert resp.status_code == 201, resp.text

        full = client.get(
            f"/api/v1/customers/{customer['id']}/360", headers=admin
        ).json()["data"]
        titles = {d["title"] for d in full["documents"]}
        assert titles == {"KYC PAN", "Booking agreement"}


class TestHotLeadAISuggestion:
    def test_hot_lead_creates_ai_suggestion_notification_once(self, client, admin):
        rep = create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        rep_h = auth_headers(client, "rep@stail.com")
        lead = make_lead(client, rep_h).json()["data"]
        # Push the lead into a hot-scoring state (stage weight makes it ≥70).
        client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=rep_h,
            json={"stage": "negotiation"},
        )
        for _ in range(2):  # second run must not duplicate (dedupe key)
            resp = client.post(
                "/api/v1/ai/components/lead-qualification", headers=rep_h,
                json={"lead_id": lead["id"]},
            )
            assert resp.json()["data"]["result"]["score_band"] == "hot"
        notifications = client.get("/api/v1/notifications", headers=rep_h).json()["data"]
        ai_notes = [n for n in notifications if n["type"] == "ai_suggestion"]
        assert len(ai_notes) == 1
        assert "Hot lead" in ai_notes[0]["title"]
