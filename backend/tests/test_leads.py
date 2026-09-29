"""Phase 2 verification: lead management, pipeline, dedupe, import/export, scoping."""
import io

from tests.conftest import auth_headers, create_user_as_admin


def make_lead(client, headers, **overrides):
    payload = {
        "full_name": "Rahul Sharma",
        "phone": "9876543210",
        "email": "rahul@example.com",
        "source": "website",
        "budget_min": 5000000,
        "budget_max": 8000000,
        "location_preference": "Whitefield, Bangalore",
        "property_type": "3BHK Apartment",
    }
    payload.update(overrides)
    return client.post("/api/v1/leads", headers=headers, json=payload)


class TestLeadCRUD:
    def test_create_and_get(self, client, admin):
        resp = make_lead(client, admin)
        assert resp.status_code == 201, resp.text
        lead = resp.json()["data"]
        assert lead["stage"] == "new"
        assert lead["assigned_to"] is not None
        detail = client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]
        assert detail["full_name"] == "Rahul Sharma"

    def test_update(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        resp = client.patch(
            f"/api/v1/leads/{lead['id']}", headers=admin,
            json={"budget_max": 9000000, "requirements": "Needs east-facing"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["requirements"] == "Needs east-facing"

    def test_soft_delete(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        assert client.delete(f"/api/v1/leads/{lead['id']}", headers=admin).status_code == 200
        assert client.get(f"/api/v1/leads/{lead['id']}", headers=admin).status_code == 404

    def test_list_filters_and_search(self, client, admin):
        make_lead(client, admin)
        make_lead(client, admin, full_name="Priya Patel", phone="9123456780",
                  email="priya@example.com", source="meta_ads", force=True)
        all_leads = client.get("/api/v1/leads", headers=admin).json()
        assert all_leads["meta"]["total"] == 2
        by_source = client.get("/api/v1/leads?source=meta_ads", headers=admin).json()
        assert by_source["meta"]["total"] == 1
        by_q = client.get("/api/v1/leads?q=priya", headers=admin).json()
        assert by_q["meta"]["total"] == 1
        assert by_q["data"][0]["full_name"] == "Priya Patel"

    def test_requires_auth(self, client):
        assert client.get("/api/v1/leads").status_code == 401


class TestDuplicateDetection:
    def test_same_phone_blocked_without_force(self, client, admin):
        make_lead(client, admin)
        resp = make_lead(client, admin, full_name="Different Name", email="other@x.com")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "duplicate_lead"

    def test_phone_normalization_variants_detected(self, client, admin):
        make_lead(client, admin, phone="9876543210")
        for variant in ["+91 98765 43210", "098765-43210", "919876543210"]:
            resp = make_lead(client, admin, phone=variant, email="v@x.com",
                             full_name="Someone Else")
            assert resp.status_code == 409, variant

    def test_force_creates_anyway(self, client, admin):
        make_lead(client, admin)
        resp = make_lead(client, admin, force=True)
        assert resp.status_code == 201

    def test_check_duplicates_endpoint(self, client, admin):
        make_lead(client, admin)
        resp = client.post(
            "/api/v1/leads/check-duplicates", headers=admin,
            json={"phone": "9876543210"},
        )
        matches = resp.json()["data"]
        assert len(matches) == 1 and matches[0]["match_type"] == "phone"
        resp = client.post(
            "/api/v1/leads/check-duplicates", headers=admin,
            json={"full_name": "Rahul Sharm"},  # fuzzy
        )
        assert any(m["match_type"] == "name" for m in resp.json()["data"])
        resp = client.post(
            "/api/v1/leads/check-duplicates", headers=admin,
            json={"email": "RAHUL@EXAMPLE.COM"},
        )
        assert any(m["match_type"] == "email" for m in resp.json()["data"])


class TestPipeline:
    def test_board_has_all_stages(self, client, admin):
        make_lead(client, admin)
        board = client.get("/api/v1/pipeline/board", headers=admin).json()
        assert board["meta"]["stage_order"][0] == "new"
        assert len(board["data"]) == 9
        assert len(board["data"]["new"]) == 1

    def test_stage_move_logged_in_timeline(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        resp = client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
            json={"stage": "contacted"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["stage"] == "contacted"
        timeline = client.get(
            f"/api/v1/leads/{lead['id']}/timeline", headers=admin
        ).json()["data"]
        types = [a["type"] for a in timeline]
        assert "stage_change" in types and "created" in types

    def test_lost_stage_records_reason(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        resp = client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin,
            json={"stage": "lost", "lost_reason": "Budget mismatch"},
        )
        assert resp.json()["data"]["lost_reason"] == "Budget mismatch"


class TestNotesAndTags:
    def test_notes(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        resp = client.post(
            f"/api/v1/leads/{lead['id']}/notes", headers=admin,
            json={"body": "Called; interested in a site visit next week."},
        )
        assert resp.status_code == 201
        detail = client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]
        assert len(detail["notes"]) == 1

    def test_tags_add_remove(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        resp = client.post(
            f"/api/v1/leads/{lead['id']}/tags", headers=admin,
            json={"name": "NRI", "color": "#3B82F6"},
        )
        tags = resp.json()["data"]["tags"]
        assert len(tags) == 1 and tags[0]["name"] == "nri"
        resp = client.delete(
            f"/api/v1/leads/{lead['id']}/tags/{tags[0]['id']}", headers=admin
        )
        assert resp.json()["data"]["tags"] == []


class TestScoping:
    def test_own_scope_isolation_and_team_read(self, client, admin):
        create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")
        rep_a = auth_headers(client, "repa@stail.com")
        rep_b = auth_headers(client, "repb@stail.com")
        lead = make_lead(client, rep_a).json()["data"]
        # B has read TEAM scope but A and B share no manager → not same team.
        assert client.get("/api/v1/leads", headers=rep_b).json()["meta"]["total"] == 0
        # B cannot update A's lead (update scope is OWN).
        resp = client.patch(
            f"/api/v1/leads/{lead['id']}", headers=rep_b, json={"campaign": "hijack"}
        )
        assert resp.status_code == 404
        # Admin sees everything.
        assert client.get("/api/v1/leads", headers=admin).json()["meta"]["total"] == 1

    def test_team_scope_via_shared_manager(self, client, admin):
        mgr = create_user_as_admin(client, admin, "mgr@stail.com", "sales_manager")
        rep_a = create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        rep_b = create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")
        for rep in (rep_a, rep_b):
            client.patch(
                f"/api/v1/users/{rep['id']}", headers=admin, json={"manager_id": mgr["id"]}
            )
        rep_a_h = auth_headers(client, "repa@stail.com")
        rep_b_h = auth_headers(client, "repb@stail.com")
        mgr_h = auth_headers(client, "mgr@stail.com")
        make_lead(client, rep_a_h)
        # Teammate (same manager) can read but manager can also reassign.
        assert client.get("/api/v1/leads", headers=rep_b_h).json()["meta"]["total"] == 1
        assert client.get("/api/v1/leads", headers=mgr_h).json()["meta"]["total"] == 1
        lead_id = client.get("/api/v1/leads", headers=mgr_h).json()["data"][0]["id"]
        resp = client.post(
            f"/api/v1/leads/{lead_id}/assign", headers=mgr_h, json={"user_id": rep_b["id"]}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["assigned_to"] == rep_b["id"]

    def test_sales_executive_cannot_reassign(self, client, admin):
        rep = create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        rep_h = auth_headers(client, "repa@stail.com")
        lead = make_lead(client, rep_h).json()["data"]
        resp = client.post(
            f"/api/v1/leads/{lead['id']}/assign", headers=rep_h, json={"user_id": rep["id"]}
        )
        assert resp.status_code == 403  # no leads:assign permission

    def test_marketing_can_only_edit_source_fields(self, client, admin):
        create_user_as_admin(client, admin, "mkt@stail.com", "marketing_executive")
        mkt_h = auth_headers(client, "mkt@stail.com")
        lead = make_lead(client, admin).json()["data"]
        ok = client.patch(
            f"/api/v1/leads/{lead['id']}", headers=mkt_h,
            json={"source": "google_ads", "campaign": "summer-2026"},
        )
        assert ok.status_code == 200
        blocked = client.patch(
            f"/api/v1/leads/{lead['id']}", headers=mkt_h, json={"budget_max": 1}
        )
        assert blocked.status_code == 403


class TestImportExport:
    def test_csv_import_with_errors_and_dedupe(self, client, admin):
        make_lead(client, admin)  # pre-existing → row duplicates get skipped
        csv_content = (
            "full_name,phone,email,source\n"
            "Rahul Sharma,9876543210,rahul@example.com,website\n"  # dup → skip
            "Anita Desai,9000000001,anita@example.com,event\n"
            "Missing Phone,,x@y.com,website\n"                     # error row
            "Vikram Rao,9000000002,,referral\n"
        )
        resp = client.post(
            "/api/v1/leads/import", headers=admin,
            files={"file": ("leads.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()["data"]
        assert result["imported"] == 2
        assert result["skipped_duplicates"] == 1
        assert len(result["errors"]) == 1
        assert result["batch_id"]  # persisted batch id must be returned, not null
        assert client.get("/api/v1/leads", headers=admin).json()["meta"]["total"] == 3

    def test_csv_import_adapts_camelcase_export_headers(self, client, admin):
        # Shaped like a real export from another CRM: camelCase headers, extra
        # columns, quoted cells, Indian budget bands.
        csv_content = (
            '"id","createdAt","fullName","email","phone","budget","propertyType","hearAbout"\n'
            '"x1","2026-07-18","Aditya Sinha","a@ex.com","+919999900001","1-2Cr","Villa","Referral"\n'
            '"x2","2026-07-18","Priya Nair","p@ex.com","+919999900002","Under 50L","Apartment","Instagram"\n'
            '"x3","2026-07-18","Rohan Mehta","r@ex.com","+919999900003","5Cr+","Land","Friend"\n'
        )
        resp = client.post(
            "/api/v1/leads/import", headers=admin,
            files={"file": ("export.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()["data"]
        assert result["imported"] == 3, result["errors"]
        assert result["errors"] == []
        leads = client.get("/api/v1/leads", headers=admin).json()["data"]
        aditya = next(l for l in leads if l["full_name"] == "Aditya Sinha")
        assert float(aditya["budget_min"]) == 10_000_000
        assert float(aditya["budget_max"]) == 20_000_000
        assert aditya["property_type"] == "Villa"
        assert aditya["source"] == "Referral"

    def test_csv_import_header_aliases(self, client, admin):
        csv_content = (
            "Customer Name,Mobile No,Email Address,Notes\n"
            "Sunil Gupta,9876500001,s@ex.com,Wants sea view\n"
        )
        resp = client.post(
            "/api/v1/leads/import", headers=admin,
            files={"file": ("sheet.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["imported"] == 1
        leads = client.get("/api/v1/leads", headers=admin).json()["data"]
        sunil = next(l for l in leads if l["full_name"] == "Sunil Gupta")
        assert sunil["phone"] == "9876500001"
        assert sunil["requirements"] == "Wants sea view"

    def test_budget_range_parsing(self):
        from app.modules.leads.service import _parse_budget_range as parse

        assert parse("1-2Cr") == (10_000_000, 20_000_000)
        assert parse("2-5Cr") == (20_000_000, 50_000_000)
        assert parse("50L-1Cr") == (5_000_000, 10_000_000)
        assert parse("Under 50L") == (None, 5_000_000)
        assert parse("5Cr+") == (50_000_000, None)
        assert parse("₹75,00,000") == (7_500_000, 7_500_000)
        assert parse("negotiable") == (None, None)

    def test_non_csv_rejected(self, client, admin):
        resp = client.post(
            "/api/v1/leads/import", headers=admin,
            files={"file": ("leads.xlsx", io.BytesIO(b"junk"), "application/xlsx")},
        )
        assert resp.status_code == 400

    def test_export(self, client, admin):
        make_lead(client, admin)
        resp = client.get("/api/v1/leads/export", headers=admin)
        assert resp.status_code == 200
        assert "Rahul Sharma" in resp.text
        assert resp.headers["content-disposition"].startswith("attachment")
