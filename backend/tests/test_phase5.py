"""Phase 5 verification: AI widgets, components, insights, timeline intelligence."""
from tests.conftest import auth_headers, create_user_as_admin
from tests.test_leads import make_lead
from tests.test_phase3 import make_customer, make_project


class TestWidgets:
    def test_catalog(self, client, admin):
        data = client.get("/api/v1/ai/catalog", headers=admin).json()["data"]
        assert "lead-summary" in data["widgets"]
        assert "call-summary" in data["components"]

    def test_lead_summary_uses_real_data(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        resp = client.post(
            "/api/v1/ai/widgets/lead-summary", headers=admin, json={"lead_id": lead["id"]}
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()["data"]["result"]
        assert "Rahul Sharma" in result["summary"]
        assert "3BHK" in result["summary"]
        assert "email" not in result["data_gaps"]  # email was provided

    def test_next_best_action_follows_stage(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
            json={"stage": "site_visit_scheduled"},
        )
        result = client.post(
            "/api/v1/ai/widgets/next-best-action", headers=admin,
            json={"lead_id": lead["id"]},
        ).json()["data"]["result"]
        assert result["stage"] == "site_visit_scheduled"
        assert "site visit" in result["action"].lower()

    def test_property_recommendations_match_inventory(self, client, admin):
        make_project(client, admin)
        lead = make_lead(client, admin).json()["data"]  # budget 50L–80L, 3BHK
        result = client.post(
            "/api/v1/ai/widgets/property-recommendations", headers=admin,
            json={"lead_id": lead["id"]},
        ).json()["data"]["result"]
        recs = result["recommendations"]
        assert len(recs) >= 1
        # Budget max 80L: the 75L 2BHK fits budget; 1.1Cr+ 3BHKs match type.
        assert all("rationale" in r and "match_score" in r for r in recs)

    def test_customer_summary(self, client, admin):
        customer = make_customer(client, admin).json()["data"]
        result = client.post(
            "/api/v1/ai/widgets/customer-summary", headers=admin,
            json={"customer_id": customer["id"]},
        ).json()["data"]["result"]
        assert "Sunita Verma" in result["summary"]
        assert result["relationship"]["family_size"] == 1

    def test_widget_requires_entity(self, client, admin):
        resp = client.post("/api/v1/ai/widgets/lead-summary", headers=admin, json={})
        assert resp.status_code == 400
        resp = client.post("/api/v1/ai/widgets/nonexistent", headers=admin, json={})
        assert resp.status_code == 404

    def test_widget_respects_lead_scope(self, client, admin):
        create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")
        rep_a, rep_b = auth_headers(client, "repa@stail.com"), auth_headers(client, "repb@stail.com")
        lead = make_lead(client, rep_a).json()["data"]
        resp = client.post(
            "/api/v1/ai/widgets/lead-summary", headers=rep_b, json={"lead_id": lead["id"]}
        )
        assert resp.status_code == 404  # not visible outside scope


class TestComponents:
    def test_lead_qualification_scores_and_persists(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        resp = client.post(
            "/api/v1/ai/components/lead-qualification", headers=admin,
            json={"lead_id": lead["id"]},
        )
        result = resp.json()["data"]["result"]
        assert 0 <= result["ai_score"] <= 100
        assert result["score_band"] in ("hot", "warm", "cold")
        assert len(result["explanation"]) >= 3  # email+budget+location signals
        # Score written back to the lead record.
        lead_now = client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]
        assert lead_now["ai_score"] == result["ai_score"]
        assert lead_now["score_band"] == result["score_band"]
        # Timeline shows the AI recommendation entry.
        timeline = client.get(f"/api/v1/leads/{lead['id']}/timeline", headers=admin).json()
        assert any(a["type"] == "ai_recommendation" for a in timeline["data"])

    def test_buyer_assistant_slot_filling(self, client, admin):
        result = client.post(
            "/api/v1/ai/components/buyer-assistant", headers=admin,
            json={"requirements": {"budget": "80L", "location": "Whitefield"}},
        ).json()["data"]["result"]
        assert set(result["missing_fields"]) == {"property_type", "timeline"}
        assert result["next_question"]
        assert result["ready_for_matching"] is False

    def test_call_summary_extraction(self, client, admin):
        transcript = (
            "Customer said they are interested in the 3BHK at Prestige Lakeside. "
            "Budget is around one crore. I will send the floor plan today. "
            "We agreed to schedule a site visit on Saturday morning."
        )
        result = client.post(
            "/api/v1/ai/components/call-summary", headers=admin,
            json={"transcript": transcript},
        ).json()["data"]["result"]
        assert result["sentiment"] == "positive"
        assert any("floor plan" in a for a in result["action_items"])

    def test_follow_up_and_email_drafts_require_approval(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        follow = client.post(
            "/api/v1/ai/components/follow-up", headers=admin, json={"lead_id": lead["id"]}
        ).json()["data"]["result"]
        assert follow["requires_human_approval"] is True
        assert "Rahul" in follow["drafts"]["whatsapp"]
        email = client.post(
            "/api/v1/ai/components/email-generator", headers=admin,
            json={"recipient_name": "Priya Patel", "purpose": "site_visit"},
        ).json()["data"]["result"]
        assert email["requires_human_approval"] is True
        assert "Priya" in email["body"]

    def test_insights_persisted_and_listable(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        client.post("/api/v1/ai/widgets/lead-summary", headers=admin,
                    json={"lead_id": lead["id"]})
        client.post("/api/v1/ai/components/lead-qualification", headers=admin,
                    json={"lead_id": lead["id"]})
        insights = client.get(
            f"/api/v1/ai/insights/lead/{lead['id']}", headers=admin
        ).json()["data"]
        agents = {i["agent_name"] for i in insights}
        assert {"lead_summary", "lead_qualification"} <= agents


class TestTimelineIntelligence:
    def test_filterable_timeline(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        client.post(f"/api/v1/leads/{lead['id']}/notes", headers=admin,
                    json={"body": "Spoke on phone"})
        client.patch(f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
                     json={"stage": "contacted"})
        all_events = client.get(
            f"/api/v1/timeline/lead/{lead['id']}", headers=admin
        ).json()["data"]
        assert len(all_events) == 3  # created + note + stage_change
        only_notes = client.get(
            f"/api/v1/timeline/lead/{lead['id']}?types=note", headers=admin
        ).json()["data"]
        assert len(only_notes) == 1 and only_notes[0]["type"] == "note"

    def test_timeline_scope_enforced(self, client, admin):
        create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")
        rep_a, rep_b = auth_headers(client, "repa@stail.com"), auth_headers(client, "repb@stail.com")
        lead = make_lead(client, rep_a).json()["data"]
        resp = client.get(f"/api/v1/timeline/lead/{lead['id']}", headers=rep_b)
        assert resp.status_code == 404
