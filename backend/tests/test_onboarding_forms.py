"""The expanded onboarding: real asset uploads, and completion side effects that
turn the wizard's answers into inventory, a company profile, and a scoring rubric."""
from sqlalchemy import select

from app.db.base import SessionLocal
from app.modules.auth.models import Tenant
from app.modules.properties.models import PropertyProject, PropertyUnit
from tests.conftest import auth_headers, create_user_as_admin
from tests.conftest import admin  # noqa: F401  (fixture)

PDF_BYTES = b"%PDF-1.4\n% a small but genuinely non-empty file\n"


def _upload(client, headers, *, name="brochure.pdf", content=PDF_BYTES,
            category="brochure", content_type="application/pdf", title=None):
    data = {"category": category}
    if title:
        data["title"] = title
    return client.post(
        "/api/v1/onboarding/upload",
        headers=headers,
        files={"file": (name, content, content_type)},
        data=data,
    )


class TestOnboardingUploads:
    def test_upload_is_actually_stored_and_downloadable(self, client, admin):
        """Regression: this endpoint used to return a fabricated
        `https://storage.stail.ai/mock/<name>` URL and write nothing at all — the
        wizard showed success, the bytes were dropped, and the link 404'd."""
        resp = _upload(client, admin, title="Palm Grove Brochure")
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]

        assert data["document_id"]
        assert data["size"] == len(PDF_BYTES)
        assert data["category"] == "brochure"
        assert data["title"] == "Palm Grove Brochure"
        # Not a made-up public URL — an authenticated path inside this API.
        assert data["download_path"] == f"/documents/{data['document_id']}/download"
        assert "storage.stail.ai" not in str(data)

        download = client.get(f"/api/v1{data['download_path']}", headers=admin)
        assert download.status_code == 200, download.text
        assert download.content == PDF_BYTES

    def test_uploads_are_listed_for_the_wizard_to_show_on_revisit(self, client, admin):
        _upload(client, admin, name="logo.png", content=b"\x89PNG\r\n\x1a\nfake",
                category="logo", content_type="image/png")
        _upload(client, admin, name="faqs.pdf", category="knowledge_base")

        listed = client.get("/api/v1/onboarding/documents", headers=admin)
        assert listed.status_code == 200, listed.text
        by_category = {d["category"]: d for d in listed.json()["data"]}
        assert set(by_category) == {"logo", "knowledge_base"}
        assert by_category["knowledge_base"]["filename"] == "faqs.pdf"
        assert by_category["logo"]["size"] > 0

    def test_upload_also_appears_in_the_documents_module(self, client, admin):
        """Onboarding assets are ordinary documents — they must not be a silo."""
        doc_id = _upload(client, admin).json()["data"]["document_id"]
        docs = client.get("/api/v1/documents", headers=admin).json()["data"]
        assert any(d["id"] == doc_id and d["entity_type"] == "tenant" for d in docs)

    def test_delete_removes_it(self, client, admin):
        doc_id = _upload(client, admin).json()["data"]["document_id"]
        resp = client.delete(f"/api/v1/onboarding/documents/{doc_id}", headers=admin)
        assert resp.status_code == 204, resp.text
        assert client.get("/api/v1/onboarding/documents", headers=admin).json()["data"] == []
        assert client.get(f"/api/v1/documents/{doc_id}", headers=admin).status_code == 404

    def test_deleting_someone_elses_document_404s(self, client, admin):
        doc_id = _upload(client, admin).json()["data"]["document_id"]

        register = client.post(
            "/api/v1/auth/register",
            json={"email": "other@rival.com", "password": "Str0ng!Passw0rd",
                  "full_name": "Other Admin", "company_name": "Rival Realty"},
        )
        assert register.status_code == 201, register.text
        other = auth_headers(client, "other@rival.com")

        resp = client.delete(f"/api/v1/onboarding/documents/{doc_id}", headers=other)
        assert resp.status_code == 404
        # Still there for its real owner.
        assert client.get(f"/api/v1/documents/{doc_id}", headers=admin).status_code == 200


class TestOnboardingUploadValidation:
    def test_unknown_category_rejected(self, client, admin):
        resp = _upload(client, admin, category="totally_made_up")
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] == "invalid_category"

    def test_empty_file_rejected(self, client, admin):
        resp = _upload(client, admin, content=b"")
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] == "empty_file"

    def test_dangerous_extension_rejected(self, client, admin):
        resp = _upload(client, admin, name="payload.svg", content=b"<svg onload=alert(1)>",
                       category="logo", content_type="image/svg+xml")
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] == "unsupported_file_type"

    def test_video_and_deck_formats_are_accepted(self, client, admin):
        # §16 of the developer onboarding form asks for videos, drone footage
        # and sales decks; the old allow-list rejected all three.
        for name, category, content_type in [
            ("walkthrough.mp4", "video", "video/mp4"),
            ("sales.pptx", "sales_deck",
             "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ]:
            resp = _upload(client, admin, name=name, content=b"binary-ish payload",
                           category=category, content_type=content_type)
            assert resp.status_code == 201, f"{name}: {resp.text}"

    def test_non_admin_cannot_upload(self, client, admin):
        create_user_as_admin(client, admin, "caller@stail.com", "telecaller")
        caller = auth_headers(client, "caller@stail.com")
        assert _upload(client, caller).status_code == 403
        assert client.get("/api/v1/onboarding/documents", headers=caller).status_code == 403

    def test_cannot_file_documents_against_another_workspace(self, client, admin):
        resp = client.post(
            "/api/v1/documents/upload", headers=admin,
            files={"file": ("x.pdf", PDF_BYTES, "application/pdf")},
            data={"title": "Sneaky", "category": "brochure",
                  "entity_type": "tenant", "entity_id": "not-my-tenant-id"},
        )
        assert resp.status_code == 404, resp.text


class TestStepRegistry:
    def test_registry_lists_every_form_page(self, client, admin):
        resp = client.get("/api/v1/onboarding/steps", headers=admin)
        assert resp.status_code == 200, resp.text
        steps = resp.json()["data"]
        keys = [s["key"] for s in steps]
        # The original StailOS keys must survive so part-finished setups keep
        # their saved answers.
        assert {"1", "2", "4", "7", "11"} <= set(keys)
        assert len(keys) == len(set(keys))
        for step in steps:
            assert step["title"] and step["source"] and step["effect"]

    def test_primary_contact_step_renames_the_admin(self, client, admin):
        resp = client.patch(
            "/api/v1/onboarding/step", headers=admin,
            json={"step_id": "1b", "data": {"fullName": "Ramesh Iyer",
                                            "designation": "Sales Head"}},
        )
        assert resp.status_code == 200, resp.text
        me = client.get("/api/v1/auth/me", headers=admin).json()["data"]
        assert me["full_name"] == "Ramesh Iyer"

    def test_new_steps_accumulate_alongside_the_old_ones(self, client, admin):
        for key, data in [
            ("1", {"companyName": "Grove Developers"}),
            ("1c", {"cities": ["Bengaluru", "Pune"], "businessTypes": ["Residential"]}),
            ("5", {"leadBands": {"hot": 75, "warm": 45}}),
            ("12", {"marketingConsent": True, "aiUsageConsent": True}),
        ]:
            resp = client.patch("/api/v1/onboarding/step", headers=admin,
                                json={"step_id": key, "data": data})
            assert resp.status_code == 200, resp.text

        state = client.get("/api/v1/onboarding/state", headers=admin).json()["data"]
        assert set(state["onboarding_data"]) == {"1", "1c", "5", "12"}
        assert state["onboarding_data"]["1c"]["cities"] == ["Bengaluru", "Pune"]


class TestProjectCreationOnLaunch:
    def test_each_configuration_becomes_a_priced_unit(self, client, admin):
        """Regression: completion used to create one placeholder per project —
        "Unit-1", 1BHK, 0 sq ft, ₹0 — and hardcode the city to "Unknown". A ₹0
        unit fits every budget, so it won every recommendation, and the fake city
        broke every city-filtered inventory search."""
        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "2",
            "data": {"projects": [{
                "name": "Palm Grove", "location": "Whitefield, Bengaluru",
                "priceRange": "₹1.2Cr – ₹3.2Cr",
                "configurations": ["2BHK", "3BHK", "4BHK"],
                "amenities": ["Gym", "Pool"], "possession": "Dec 2027",
                "rera": "PRM/KA/RERA/1251", "status": "ready_to_move",
                "usp": "Lake-facing towers",
            }]},
        })
        assert client.post("/api/v1/onboarding/complete", headers=admin).status_code == 200

        with SessionLocal() as db:
            project = db.scalars(select(PropertyProject)).one()
            assert project.name == "Palm Grove"
            assert project.city == "Bengaluru"          # derived, not "Unknown"
            assert project.amenities == ["Gym", "Pool"]  # a real list, not a string
            assert project.rera_id == "PRM/KA/RERA/1251"
            assert project.possession_date == "Dec 2027"
            assert project.status == "ready_to_move"
            assert project.description == "Lake-facing towers"

            units = db.scalars(
                select(PropertyUnit).where(PropertyUnit.project_id == project.id)
            ).all()
            assert {u.unit_type for u in units} == {"2BHK", "3BHK", "4BHK"}
            prices = sorted(float(u.price) for u in units)
            assert prices[0] == 12_000_000    # range floor
            assert prices[-1] == 32_000_000   # range ceiling
            assert all(p > 0 for p in prices)
            assert all(u.carpet_area_sqft and float(u.carpet_area_sqft) > 0 for u in units)

    def test_new_inventory_is_immediately_searchable_by_city(self, client, admin):
        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "2",
            "data": {"projects": [{"name": "Coast Villas", "city": "Goa",
                                   "location": "Panjim", "priceRange": "80L to 1.5Cr",
                                   "configurations": ["villa"]}]},
        })
        client.post("/api/v1/onboarding/complete", headers=admin)

        found = client.get("/api/v1/properties", headers=admin, params={"city": "Goa"})
        assert found.status_code == 200, found.text
        assert found.json()["meta"]["total"] == 1
        assert float(found.json()["data"][0]["price"]) > 0

    def test_single_configuration_uses_the_range_floor(self, client, admin):
        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "2",
            "data": {"projects": [{"name": "Solo Tower", "city": "Pune",
                                   "location": "Baner", "priceRange": "95 lakh",
                                   "configurations": ["2BHK"]}]},
        })
        client.post("/api/v1/onboarding/complete", headers=admin)
        with SessionLocal() as db:
            unit = db.scalars(select(PropertyUnit)).one()
            assert float(unit.price) == 9_500_000

    def test_unnamed_and_malformed_projects_are_skipped_not_crashed_on(self, client, admin):
        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "2",
            "data": {"projects": [
                {"name": "   "},                 # blank name
                "not-even-an-object",            # wrong type
                {"name": "Real One", "city": "Pune", "priceRange": "not a price"},
            ]},
        })
        assert client.post("/api/v1/onboarding/complete", headers=admin).status_code == 200
        with SessionLocal() as db:
            projects = db.scalars(select(PropertyProject)).all()
            assert [p.name for p in projects] == ["Real One"]


class TestCompanyProfilePromotion:
    def test_answers_land_in_tenant_settings(self, client, admin):
        steps = {
            "1": {"companyName": "Grove Developers", "legalName": "Grove Developers Pvt Ltd",
                  "brandName": "Grove", "gst": "29ABCDE1234F1Z5", "rera": "RERA-001",
                  "website": "https://grove.example", "headOffice": "Bengaluru",
                  "yearEstablished": 2009},
            "1b": {"fullName": "Ramesh Iyer", "designation": "Sales Head",
                   "mobile": "9800000000", "preferredChannel": "WhatsApp"},
            "1c": {"cities": ["Bengaluru", "Mysuru"], "businessTypes": ["Residential"],
                   "propertyTypes": ["Apartments", "Villas"], "employees": 120},
            "4": {"buyerSegments": ["HNIs", "NRIs"], "purchaseTimeline": "Within 6 Months"},
            "6": {"salesAi": ["AI Lead Scoring", "AI Follow-up"]},
            "9": {"responseTimeMinutes": 15, "monthlyBookingTarget": 12},
            "12": {"marketingConsent": True, "aiUsageConsent": True,
                   "integrations": ["WhatsApp Business"]},
        }
        for key, data in steps.items():
            client.patch("/api/v1/onboarding/step", headers=admin,
                         json={"step_id": key, "data": data})
        assert client.post("/api/v1/onboarding/complete", headers=admin).status_code == 200

        with SessionLocal() as db:
            tenant = db.scalars(select(Tenant)).one()
            assert tenant.name == "Grove Developers"
            settings = tenant.settings or {}
            assert settings["company"]["legal_name"] == "Grove Developers Pvt Ltd"
            assert settings["company"]["gst"] == "29ABCDE1234F1Z5"
            assert settings["company"]["cities"] == ["Bengaluru", "Mysuru"]
            assert settings["primary_contact"]["designation"] == "Sales Head"
            assert settings["icp"]["buyerSegments"] == ["HNIs", "NRIs"]
            assert settings["ai_features"]["salesAi"] == ["AI Lead Scoring", "AI Follow-up"]
            assert settings["sales_process"]["responseTimeMinutes"] == 15
            assert settings["consents"] == {
                "marketing": True, "ai_usage": True,
                "integrations": ["WhatsApp Business"],
            }
            # Empty answers must not be stored as empty strings.
            assert "pan" not in settings["company"]

    def test_declared_cities_drive_geographic_lead_scoring(self, client, admin):
        """The footprint step is not decoration: it changes the score."""
        lead = client.post(
            "/api/v1/leads", headers=admin,
            json={"full_name": "Asha Rao", "phone": "9999900000", "source": "website",
                  "location_preference": "Whitefield, Bengaluru"},
        ).json()["data"]["id"]

        def geography_score():
            resp = client.post("/api/v1/ai/components/lead-qualification",
                               headers=admin, json={"lead_id": lead})
            assert resp.status_code == 200, resp.text
            return resp.json()["data"]["result"]["breakdown"]["geography"]["score"]

        client.patch("/api/v1/onboarding/step", headers=admin,
                     json={"step_id": "1c", "data": {"cities": ["Chennai"]}})
        outside = geography_score()

        client.patch("/api/v1/onboarding/step", headers=admin,
                     json={"step_id": "1c", "data": {"cities": ["Bengaluru"]}})
        inside = geography_score()

        assert inside > outside

    def test_completion_is_idempotent(self, client, admin):
        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "2",
            "data": {"projects": [{"name": "Once Only", "city": "Pune",
                                   "priceRange": "1Cr", "configurations": ["2BHK"]}]},
        })
        assert client.post("/api/v1/onboarding/complete", headers=admin).status_code == 200
        assert client.post("/api/v1/onboarding/complete", headers=admin).status_code == 200
        with SessionLocal() as db:
            # Completing twice must not duplicate inventory.
            assert len(db.scalars(select(PropertyProject)).all()) == 1


class TestAiUsageConsentIsEnforced:
    """§22 consent was collected, gated the wizard, then was never checked again —
    a workspace that answered "No" still had every agent running on its data."""

    def _lead(self, client, admin_headers):
        return client.post(
            "/api/v1/leads", headers=admin_headers,
            json={"full_name": "Asha Rao", "phone": "9999900000", "source": "website"},
        ).json()["data"]["id"]

    def test_declining_consent_blocks_generation(self, client, admin):
        lead_id = self._lead(client, admin)
        assert client.post("/api/v1/ai/widgets/lead-summary", headers=admin,
                           json={"lead_id": lead_id}).status_code == 200

        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "12",
            "data": {"marketingConsent": True, "aiUsageConsent": False},
        })

        resp = client.post("/api/v1/ai/widgets/lead-summary", headers=admin,
                           json={"lead_id": lead_id})
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["code"] == "ai_consent_declined"

        # Every generation path, not just widgets.
        assert client.post("/api/v1/ai/components/lead-qualification", headers=admin,
                           json={"lead_id": lead_id}).status_code == 403
        assert client.post("/api/v1/ai/chat", headers=admin,
                           json={"message": "3BHK under 1Cr"}).status_code == 403
        assert client.post("/api/v1/ai/orchestrate", headers=admin,
                           json={"message": "3BHK under 1Cr", "lead_id": lead_id}
                           ).status_code == 403

    def test_granting_consent_restores_it(self, client, admin):
        lead_id = self._lead(client, admin)
        client.patch("/api/v1/onboarding/step", headers=admin,
                     json={"step_id": "12", "data": {"aiUsageConsent": False}})
        assert client.post("/api/v1/ai/widgets/lead-summary", headers=admin,
                           json={"lead_id": lead_id}).status_code == 403
        client.patch("/api/v1/onboarding/step", headers=admin,
                     json={"step_id": "12", "data": {"aiUsageConsent": True}})
        assert client.post("/api/v1/ai/widgets/lead-summary", headers=admin,
                           json={"lead_id": lead_id}).status_code == 200

    def test_never_asked_means_allowed_not_refused(self, client, admin):
        """A workspace that skipped onboarding must keep working."""
        lead_id = self._lead(client, admin)
        state = client.get("/api/v1/onboarding/state", headers=admin).json()["data"]
        assert "12" not in (state["onboarding_data"] or {})
        assert client.post("/api/v1/ai/widgets/lead-summary", headers=admin,
                           json={"lead_id": lead_id}).status_code == 200

    def test_catalog_reports_the_consent_state(self, client, admin):
        client.patch("/api/v1/onboarding/step", headers=admin,
                     json={"step_id": "12", "data": {"aiUsageConsent": False}})
        data = client.get("/api/v1/ai/catalog", headers=admin).json()["data"]
        assert data["ai_consent"] is False
        assert data["widgets"] == [] and data["components"] == []
        # The full catalogue stays visible so an admin can see what they turned off.
        assert "lead-summary" in data["all_widgets"]


class TestAiFeatureSelectionIsEnforced:
    """§10 "select all that apply" implied the unselected ones stay off."""

    def _lead(self, client, admin_headers):
        return client.post(
            "/api/v1/leads", headers=admin_headers,
            json={"full_name": "Vikram S", "phone": "9888800000", "source": "website"},
        ).json()["data"]["id"]

    def test_unselected_feature_is_refused(self, client, admin):
        lead_id = self._lead(client, admin)
        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "6",
            "data": {"salesAi": ["AI lead scoring"]},  # follow-up deliberately absent
        })

        assert client.post("/api/v1/ai/components/lead-qualification", headers=admin,
                           json={"lead_id": lead_id}).status_code == 200
        resp = client.post("/api/v1/ai/components/follow-up", headers=admin,
                           json={"lead_id": lead_id})
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["code"] == "ai_feature_disabled"

    def test_selecting_nothing_leaves_everything_on(self, client, admin):
        lead_id = self._lead(client, admin)
        client.patch("/api/v1/onboarding/step", headers=admin,
                     json={"step_id": "6", "data": {"integrations": ["WhatsApp Business"]}})
        for component in ("follow-up", "email-generator", "whatsapp-assistant"):
            assert client.post(f"/api/v1/ai/components/{component}", headers=admin,
                               json={"lead_id": lead_id}).status_code == 200, component

    def test_core_agents_survive_a_narrow_selection(self, client, admin):
        """Ticking one box must not leave the lead page with no AI at all."""
        lead_id = self._lead(client, admin)
        client.patch("/api/v1/onboarding/step", headers=admin,
                     json={"step_id": "6", "data": {"salesAi": ["AI lead scoring"]}})
        for widget in ("lead-summary", "next-best-action", "suggestions", "sales-tips"):
            assert client.post(f"/api/v1/ai/widgets/{widget}", headers=admin,
                               json={"lead_id": lead_id}).status_code == 200, widget

    def test_catalog_hides_what_is_disabled(self, client, admin):
        client.patch("/api/v1/onboarding/step", headers=admin,
                     json={"step_id": "6", "data": {"salesAi": ["AI lead scoring"]}})
        data = client.get("/api/v1/ai/catalog", headers=admin).json()["data"]
        assert "lead-qualification" in data["components"]
        assert "follow-up" not in data["components"]
        assert "follow-up" in data["all_components"]
        assert data["selected_features"] == ["ai lead scoring"]

    def test_pipeline_skips_a_disabled_stage_instead_of_failing(self, client, admin):
        lead_id = self._lead(client, admin)
        client.patch("/api/v1/onboarding/step", headers=admin,
                     json={"step_id": "6", "data": {"salesAi": ["AI follow-up"]}})

        resp = client.post("/api/v1/ai/orchestrate", headers=admin,
                           json={"message": "3BHK in Whitefield under 2Cr",
                                 "lead_id": lead_id})
        assert resp.status_code == 200, resp.text
        stages = {s["agent"]: s for s in resp.json()["data"]["pipeline"]}
        assert stages["lead_qualification"]["status"] == "skipped"
        assert "not enabled" in stages["lead_qualification"]["reason"]
        # The rest of the pipeline still did its job.
        assert stages["buyer_assistant"]["status"] == "ok"
        assert stages["crm_sync"]["status"] == "ok"
        assert resp.json()["data"]["qualification"] is None


class TestSalesTargetsReachAnalytics:
    def test_targets_appear_with_month_to_date_progress(self, client, admin):
        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "9",
            "data": {"monthlyLeadTarget": 4, "monthlyBookingTarget": 2,
                     "monthlyRevenueTarget": 1000000},
        })
        for n in range(2):
            client.post("/api/v1/leads", headers=admin,
                        json={"full_name": f"Lead {n}", "phone": f"988880000{n}",
                              "source": "website"})

        data = client.get("/api/v1/analytics/overview", headers=admin).json()["data"]
        by_metric = {t["metric"]: t for t in data["targets"]}
        assert by_metric["leads"]["target"] == 4
        assert by_metric["leads"]["actual"] == 2
        assert by_metric["leads"]["progress_pct"] == 50.0
        assert by_metric["bookings"]["actual"] == 0
        assert data["month_to_date"]["leads"] == 2

    def test_no_targets_configured_means_no_invented_goals(self, client, admin):
        data = client.get("/api/v1/analytics/overview", headers=admin).json()["data"]
        assert data["targets"] == []
        assert "month_to_date" in data

    def test_zero_and_junk_targets_are_ignored(self, client, admin):
        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "9",
            "data": {"monthlyLeadTarget": 0, "monthlyBookingTarget": "lots",
                     "monthlyRevenueTarget": None, "monthlySiteVisitTarget": 3},
        })
        data = client.get("/api/v1/analytics/overview", headers=admin).json()["data"]
        assert [t["metric"] for t in data["targets"]] == ["site_visits"]


class TestIcpReachesSalesTips:
    def test_tips_lead_with_the_workspaces_own_objections(self, client, admin):
        lead_id = client.post(
            "/api/v1/leads", headers=admin,
            json={"full_name": "Asha Rao", "phone": "9999900000", "source": "website"},
        ).json()["data"]["id"]

        generic = client.post("/api/v1/ai/widgets/sales-tips", headers=admin,
                              json={"lead_id": lead_id}).json()["data"]["result"]
        assert generic["grounded_in_icp"] is False

        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "4",
            "data": {"objections": ["Waiting for market correction"],
                     "triggers": ["Rental yield"], "painPoints": ["Delayed possession"]},
        })
        grounded = client.post("/api/v1/ai/widgets/sales-tips", headers=admin,
                               json={"lead_id": lead_id}).json()["data"]["result"]
        assert grounded["grounded_in_icp"] is True
        joined = " ".join(grounded["tips"]).lower()
        assert "waiting for market correction" in joined
        assert "rental yield" in joined
        assert grounded["tips"] != generic["tips"]


class TestSettingsViewStaysCurrent:
    def test_editing_a_step_after_launch_refreshes_tenant_settings(self, client, admin):
        """tenant.settings is a derived view of onboarding_data. It used to be
        rebuilt only at completion, so changing AI features or consent afterwards
        left a stale second copy of answers the app reads live."""
        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "12", "data": {"marketingConsent": True, "aiUsageConsent": True},
        })
        client.post("/api/v1/onboarding/complete", headers=admin)

        with SessionLocal() as db:
            assert db.scalars(select(Tenant)).one().settings["consents"]["ai_usage"] is True

        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "12", "data": {"marketingConsent": True, "aiUsageConsent": False},
        })
        with SessionLocal() as db:
            settings = db.scalars(select(Tenant)).one().settings
            assert settings["consents"]["ai_usage"] is False

    def test_settings_view_matches_the_live_policy(self, client, admin):
        client.patch("/api/v1/onboarding/step", headers=admin,
                     json={"step_id": "6", "data": {"salesAi": ["AI lead scoring"]}})
        with SessionLocal() as db:
            assert db.scalars(select(Tenant)).one().settings["ai_features"]["salesAi"] == [
                "AI lead scoring"
            ]
        catalog = client.get("/api/v1/ai/catalog", headers=admin).json()["data"]
        assert "follow-up" not in catalog["components"]


class TestInviteSendsExactlyOneEmail:
    def test_invitee_gets_the_invite_only_not_a_verification_too(self, client, admin):
        """The invite email carries the set-password link, which is what proves
        the invitee owns the mailbox. Sending "verify your account" as well gave
        them two messages, the first unusable because they have no password yet."""
        from app.modules.auth.models import EmailOutbox

        client.patch("/api/v1/onboarding/step", headers=admin, json={
            "step_id": "11",
            "data": {"teamInvites": ["solo@stail.com"], "permissionLevel": "Manager"},
        })
        assert client.post("/api/v1/onboarding/complete", headers=admin).status_code == 200

        with SessionLocal() as db:
            rows = db.scalars(
                select(EmailOutbox).where(EmailOutbox.to_email == "solo@stail.com")
            ).all()
            categories = sorted(r.category for r in rows)
        assert categories == ["team_invite"], categories

    def test_ordinary_self_registration_still_gets_verified(self, client):
        """The suppression must be scoped to invites only."""
        from app.modules.auth.models import EmailOutbox

        resp = client.post("/api/v1/auth/register", json={
            "email": "selfsignup@stail.com", "password": "Str0ng!Passw0rd",
            "full_name": "Self Signup", "company_name": "Self Co",
        })
        assert resp.status_code == 201, resp.text
        with SessionLocal() as db:
            categories = sorted(
                r.category for r in db.scalars(
                    select(EmailOutbox).where(EmailOutbox.to_email == "selfsignup@stail.com")
                ).all()
            )
        assert categories == ["email_verification"], categories

    def test_admin_created_user_still_gets_verified(self, client, admin):
        """Users an admin creates directly get no set-password link, so they do
        still need the verification mail."""
        from app.modules.auth.models import EmailOutbox

        create_user_as_admin(client, admin, "direct@stail.com", "sales_executive")
        with SessionLocal() as db:
            categories = sorted(
                r.category for r in db.scalars(
                    select(EmailOutbox).where(EmailOutbox.to_email == "direct@stail.com")
                ).all()
            )
        assert categories == ["email_verification"], categories
