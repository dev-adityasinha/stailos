"""The AI engine ported from STAIL: grading, ranking, extraction, the pipeline,
and the LLM / external providers."""
import pytest

from app.modules.ai import grading, ranking
from app.modules.ai.llm import LLMError, extract_json, mentions_any, parse_inr
from app.modules.ai.provider import (
    ExternalAIProvider,
    LLMAIProvider,
    MockAIProvider,
)
from tests.conftest import auth_headers, create_user_as_admin
from tests.conftest import admin  # noqa: F401  (fixture)


# ────────────────────────────── INR / JSON helpers ───────────────────────────

class TestInrParsing:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("1.5Cr", 15_000_000),
            ("2 crore", 20_000_000),
            ("50L", 5_000_000),
            ("80 lakh", 8_000_000),
            ("₹ 1.2 Cr", 12_000_000),
            ("8000000", 8_000_000),
            ("1,50,00,000", 15_000_000),
            ("500k", 500_000),
            ("", None),
            (None, None),
            ("expensive", None),
        ],
    )
    def test_indian_shorthand(self, text, expected):
        assert parse_inr(text) == expected


class TestJsonExtraction:
    def test_extracts_from_markdown_fence(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_extracts_from_prose(self):
        assert extract_json('Sure! Here you go: {"a": 1} — hope that helps.') == {"a": 1}

    def test_rejects_non_object(self):
        with pytest.raises(LLMError):
            extract_json("[1, 2, 3]")

    def test_rejects_empty(self):
        with pytest.raises(LLMError):
            extract_json("   ")

    def test_hallucination_guard(self):
        assert mentions_any("Great value in Whitefield", ["Whitefield", None])
        assert not mentions_any("A wonderful home for your family", ["Whitefield", "Pune"])


# ──────────────────────────────── lead grading ───────────────────────────────

FULL_LEAD = {
    "full_name": "Asha Rao", "email": "asha@example.com", "phone": "9999900000",
    "stage": "site_visit_scheduled", "budget_max": 12_000_000,
    "location_preference": "Whitefield, Bengaluru", "property_type": "3BHK",
    "requirements": "Need to move within 3 months",
}
INVENTORY = {"min_price": 9_000_000, "max_price": 20_000_000, "unit_types": ["3BHK", "2BHK"]}


class TestGrading:
    def test_strong_lead_grades_hot(self):
        result = grading.grade_lead(
            FULL_LEAD, activity_count=4, notes_count=2,
            inventory=INVENTORY, operating_cities=["Bengaluru"],
        )
        assert result["score_band"] == "hot"
        assert result["grade"] in ("A", "B")
        assert result["needs_human_review"] is False
        assert set(result["breakdown"]) == set(grading.DEFAULT_WEIGHTS)
        # Every dimension must justify itself — an unexplained score is unusable.
        for dimension in result["breakdown"].values():
            assert dimension["contributing_factors"]
            assert 0 <= dimension["score"] <= 100

    def test_empty_lead_grades_cold_and_flags_review(self):
        result = grading.grade_lead({"stage": "new"}, inventory=INVENTORY)
        assert result["score_band"] == "cold"
        assert result["grade"] == "D"
        assert result["needs_human_review"] is True
        assert result["extraction_confidence"] < 0.5

    def test_budget_below_entry_price_is_penalised_but_not_zeroed(self):
        low = grading.grade_lead({**FULL_LEAD, "budget_max": 2_000_000}, inventory=INVENTORY)
        high = grading.grade_lead(FULL_LEAD, inventory=INVENTORY)
        assert low["breakdown"]["budget"]["rule_applied"] == "budget_mismatch"
        assert 0 < low["breakdown"]["budget"]["score"] < high["breakdown"]["budget"]["score"]

    def test_budget_above_ceiling_is_not_penalised(self):
        # An over-budget buyer is an upsell, never a downgrade.
        result = grading.grade_lead({**FULL_LEAD, "budget_max": 99_000_000}, inventory=INVENTORY)
        assert result["breakdown"]["budget"]["score"] == 100

    def test_stated_timeline_beats_early_stage(self):
        urgent = grading.grade_lead(
            {**FULL_LEAD, "stage": "new", "requirements": "Need it immediately, urgent"},
            inventory=INVENTORY,
        )
        vague = grading.grade_lead(
            {**FULL_LEAD, "stage": "new", "requirements": "just researching"},
            inventory=INVENTORY,
        )
        assert urgent["breakdown"]["intent"]["score"] > vague["breakdown"]["intent"]["score"]

    def test_location_outside_footprint_scores_lower(self):
        inside = grading.grade_lead(FULL_LEAD, inventory=INVENTORY,
                                    operating_cities=["Bengaluru"])
        outside = grading.grade_lead(FULL_LEAD, inventory=INVENTORY,
                                     operating_cities=["Chennai"])
        assert (inside["breakdown"]["geography"]["score"]
                > outside["breakdown"]["geography"]["score"])


class TestGradingConfig:
    def test_tenant_weights_are_renormalised(self):
        config = grading.resolve_config(
            {"5": {"scoringWeights": {k: 10 for k in grading.DEFAULT_WEIGHTS}}}
        )
        assert pytest.approx(sum(config["weights"].values()), abs=1e-6) == 1.0
        assert len(set(config["weights"].values())) == 1  # equal weighting

    def test_garbage_weights_fall_back_to_defaults(self):
        config = grading.resolve_config({"5": {"scoringWeights": {"budget": "abc"}}})
        assert config["weights"]["budget"] == pytest.approx(
            grading.DEFAULT_WEIGHTS["budget"], abs=1e-6
        )

    def test_all_zero_weights_fall_back_rather_than_dividing_by_zero(self):
        config = grading.resolve_config(
            {"5": {"scoringWeights": {k: 0 for k in grading.DEFAULT_WEIGHTS}}}
        )
        assert config["weights"] == grading.DEFAULT_WEIGHTS

    def test_inverted_thresholds_are_rejected(self):
        config = grading.resolve_config({"5": {"leadBands": {"hot": 20, "warm": 80}}})
        assert config["thresholds"] == grading.DEFAULT_THRESHOLDS

    def test_custom_thresholds_change_the_band(self):
        kwargs = dict(activity_count=4, inventory=INVENTORY, operating_cities=["Bengaluru"])
        assert grading.grade_lead(FULL_LEAD, **kwargs)["score_band"] == "hot"
        # Same lead, near-unreachable thresholds — a workspace can demand more.
        strict = grading.resolve_config({"5": {"leadBands": {"hot": 100, "warm": 99}}})
        assert grading.grade_lead(FULL_LEAD, config=strict, **kwargs)["score_band"] == "cold"

    def test_weights_actually_shift_the_composite(self):
        lead = {**FULL_LEAD, "budget_max": 1_000_000}  # bad budget, everything else good
        budget_heavy = grading.resolve_config({"5": {"scoringWeights": {
            "budget": 90, "intent": 2, "geography": 2, "property_fit": 2,
            "engagement": 2, "contactability": 2,
        }}})
        intent_heavy = grading.resolve_config({"5": {"scoringWeights": {
            "budget": 2, "intent": 90, "geography": 2, "property_fit": 2,
            "engagement": 2, "contactability": 2,
        }}})
        assert (
            grading.grade_lead(lead, inventory=INVENTORY, config=budget_heavy)["ai_score"]
            < grading.grade_lead(lead, inventory=INVENTORY, config=intent_heavy)["ai_score"]
        )


# ─────────────────────────────── property ranking ────────────────────────────

UNITS = [
    {"unit_id": "u-match", "project": "Palm Grove", "unit_number": "A-101",
     "unit_type": "3BHK", "price": 11_000_000, "location": "Whitefield",
     "city": "Bengaluru", "amenities": ["Gym", "Pool"], "project_status": "ready_to_move"},
    {"unit_id": "u-pricey", "project": "Sky Towers", "unit_number": "B-900",
     "unit_type": "3BHK", "price": 45_000_000, "location": "Whitefield",
     "city": "Bengaluru", "amenities": [], "project_status": "under_construction"},
    {"unit_id": "u-elsewhere", "project": "Coast Villas", "unit_number": "V-1",
     "unit_type": "villa", "price": 10_000_000, "location": "Panjim",
     "city": "Goa", "amenities": [], "project_status": "under_construction"},
]
PREFS = {"budget_max": 12_000_000, "property_type": "3BHK",
         "location": "Whitefield, Bengaluru", "purpose": "end_use"}


class TestRanking:
    def test_best_match_ranks_first(self):
        ranked = ranking.rank_units(UNITS, PREFS)
        assert ranked[0]["unit_id"] == "u-match"

    def test_nothing_is_filtered_out(self):
        # The previous implementation dropped any unit that missed a preference,
        # hiding sellable inventory from the salesperson entirely.
        ranked = ranking.rank_units(UNITS, PREFS, limit=10)
        assert {u["unit_id"] for u in ranked} == {u["unit_id"] for u in UNITS}

    def test_every_result_explains_itself(self):
        for unit in ranking.rank_units(UNITS, PREFS, limit=10):
            assert unit["rationale"]
            assert 0.0 <= unit["match_score"] <= 1.0
            assert set(unit["score_breakdown"]) == {"relevance", "market_appeal", "buyer_fit"}

    def test_slight_overshoot_counts_as_a_stretch_not_a_miss(self):
        stretch = ranking.score_unit(
            {**UNITS[0], "price": 13_000_000}, PREFS  # 8% over budget
        )
        assert "budget (stretch)" in stretch["match_reasons"]
        assert "budget" not in stretch["gap_reasons"]

    def test_affordable_unit_outranks_an_unaffordable_better_match(self):
        # A ₹4.5Cr 3BHK matches the configuration but is 3.7x the stated budget;
        # a ₹1.1Cr 3BHK in the same locality must come first.
        ranked = ranking.rank_units(UNITS, PREFS, limit=10)
        order = [u["unit_id"] for u in ranked]
        assert order.index("u-match") < order.index("u-pricey")

    def test_hard_overshoot_is_penalised_not_merely_uncredited(self):
        affordable = ranking.score_unit(UNITS[0], PREFS)
        unaffordable = ranking.score_unit(UNITS[1], PREFS)
        assert "budget" in unaffordable["gap_reasons"]
        assert unaffordable["match_score"] < affordable["match_score"]

    def test_relevance_never_goes_negative(self):
        # Over budget and matching nothing else: the penalty must not push the
        # component below zero and scramble the ordering.
        result = ranking.score_unit(
            {"unit_id": "u-bad", "unit_type": "plot", "price": 90_000_000,
             "location": "Nowhere", "city": "Nowhere", "amenities": []},
            PREFS,
        )
        assert result["score_breakdown"]["relevance"] == 0.0
        assert result["match_score"] >= 0.0

    def test_investor_fit_ignores_amenity_depth(self):
        end_use = ranking.score_unit(UNITS[0], {**PREFS, "purpose": "end_use"})
        investor = ranking.score_unit(UNITS[0], {**PREFS, "purpose": "investment"})
        assert end_use["score_breakdown"]["buyer_fit"] != investor["score_breakdown"]["buyer_fit"]

    def test_limit_is_respected(self):
        assert len(ranking.rank_units(UNITS, PREFS, limit=2)) == 2

    def test_no_preferences_still_ranks_on_appeal(self):
        ranked = ranking.rank_units(UNITS, {}, limit=10)
        assert ranked[0]["unit_id"] == "u-match"  # ready-to-move wins on market appeal
        assert all(u["rationale"] for u in ranked)

    def test_unpriced_unit_does_not_crash_the_sort(self):
        ranked = ranking.rank_units([*UNITS, {**UNITS[0], "unit_id": "u-null", "price": None}],
                                    PREFS, limit=10)
        assert len(ranked) == 4


# ───────────────────────── deterministic extraction ──────────────────────────

class TestFreeTextExtraction:
    def test_mines_budget_config_timeline_and_purpose(self):
        result = MockAIProvider().generate(
            "buyer_assistant",
            {"message": "Looking for a 3BHK in Whitefield under 1.2Cr to live in, "
                        "need it within 3 months"},
        )
        assert result["budget_max"] == 12_000_000
        assert result["property_type"] == "3BHK"
        assert result["timeline"] == "3 months"
        assert result["purpose"] == "end_use"

    def test_vague_message_asks_the_next_question(self):
        result = MockAIProvider().generate("buyer_assistant", {"message": "I want a property"})
        assert result["ready_for_matching"] is False
        assert result["next_question"]
        assert result["confidence"] < 0.5

    def test_explicit_values_beat_mined_ones(self):
        result = MockAIProvider().generate(
            "buyer_assistant",
            {"message": "2BHK under 50L", "requirements": {"property_type": "villa"}},
        )
        assert result["property_type"] == "villa"

    def test_location_is_mined_against_this_workspaces_own_places(self):
        # No hardcoded gazetteer: the recognisable places are wherever this
        # builder actually sells, so a market STAIL never listed still works.
        result = MockAIProvider().generate(
            "buyer_assistant",
            {"message": "something in Kakkanad please",
             "operating_cities": ["Kochi"],
             "inventory": {"localities": ["Kakkanad", "Edappally"]}},
        )
        assert result["location"] == "Kakkanad"

    def test_unknown_place_is_not_guessed(self):
        result = MockAIProvider().generate(
            "buyer_assistant",
            {"message": "somewhere in Reykjavik", "operating_cities": ["Kochi"]},
        )
        assert result["location"] is None
        assert "location" in result["missing_fields"]

    def test_more_specific_locality_wins_over_the_city(self):
        result = MockAIProvider().generate(
            "buyer_assistant",
            {"message": "3BHK in Whitefield, Bengaluru",
             "operating_cities": ["Bengaluru"],
             "inventory": {"localities": ["Whitefield, Bengaluru", "Bengaluru"]}},
        )
        assert result["location"] == "Whitefield, Bengaluru"

    def test_investment_intent_detected(self):
        result = MockAIProvider().generate(
            "buyer_assistant", {"message": "Plot in Goa for investment, good rental yield"}
        )
        assert result["purpose"] == "investment"
        assert result["property_type"] == "plot"


# ─────────────────────────────── LLM provider ────────────────────────────────

class FakeLLM:
    """Stands in for LLMClient. Records prompts, replays scripted replies."""

    model = "fake-model-1"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat_json(self, system, user, **kwargs):
        self.calls.append({"system": system, "user": user})
        reply = self.replies.pop(0) if self.replies else {}
        if isinstance(reply, Exception):
            raise reply
        return reply


class TestLLMProvider:
    def test_narrative_is_replaced(self):
        provider = LLMAIProvider(FakeLLM([
            {"summary": "Asha is a hot 3BHK buyer in Whitefield.",
             "talking_points": ["Confirm the site visit"]},
        ]))
        result = provider.generate(
            "lead_summary",
            {"lead": {**FULL_LEAD, "source": "website"}, "activities": [], "notes_count": 0},
        )
        assert result["summary"] == "Asha is a hot 3BHK buyer in Whitefield."
        assert result["talking_points"] == ["Confirm the site visit"]
        assert result["provider_model"] == "fake-model-1"
        # Computed engagement data must survive untouched.
        assert result["engagement"]["total_activities"] == 0

    def test_model_cannot_move_the_score(self):
        # The single most important guarantee here: a chatty or adversarial
        # completion must not be able to promote a cold lead to hot.
        provider = LLMAIProvider(FakeLLM([{
            "reasoning_summary": "Looks great!",
            "ai_score": 100, "score_band": "hot", "grade": "A",
            "breakdown": {"budget": {"score": 100}},
        }]))
        baseline = MockAIProvider().generate("lead_qualification", {"lead": {"stage": "new"}})
        result = provider.generate("lead_qualification", {"lead": {"stage": "new"}})
        assert result["ai_score"] == baseline["ai_score"]
        assert result["score_band"] == baseline["score_band"] == "cold"
        assert result["grade"] == baseline["grade"]
        assert result["breakdown"] == baseline["breakdown"]
        assert result["reasoning_summary"] == "Looks great!"  # allow-listed field did change

    def test_unknown_keys_are_dropped(self):
        provider = LLMAIProvider(FakeLLM([
            {"action": "Call now", "reason": "Hot", "injected_field": "should not appear"},
        ]))
        result = provider.generate("next_best_action", {"lead": {"stage": "new"}})
        assert result["action"] == "Call now"
        assert "injected_field" not in result

    def test_wrong_type_is_rejected_in_favour_of_the_baseline(self):
        provider = LLMAIProvider(FakeLLM([{"tips": "not a list"}]))
        result = provider.generate("sales_tips", {"lead": {"stage": "new"}, "entity_id": "x"})
        assert isinstance(result["tips"], list)

    def test_failure_degrades_instead_of_raising(self):
        provider = LLMAIProvider(FakeLLM([LLMError("gateway 429")]))
        result = provider.generate(
            "lead_summary",
            {"lead": {**FULL_LEAD, "source": "website"}, "activities": [], "notes_count": 0},
        )
        assert "ai_degraded" in result
        assert result["summary"]  # deterministic summary still present

    def test_extraction_reconciles_derived_slots(self):
        provider = LLMAIProvider(FakeLLM([{
            "budget_max": 15_000_000, "location": "Bandra, Mumbai",
            "property_type": "3BHK", "timeline": "6 months", "purpose": "end_use",
            "confidence": 0.9, "next_question": None,
        }]))
        result = provider.generate("buyer_assistant", {"message": "vague words"})
        assert result["ready_for_matching"] is True
        assert result["missing_fields"] == []
        assert set(result["captured_requirements"]) == {
            "budget", "location", "property_type", "timeline"
        }

    def test_extraction_prompt_gets_the_raw_message(self):
        fake = FakeLLM([{"budget_max": 5_000_000, "confidence": 0.6}])
        LLMAIProvider(fake).generate("buyer_assistant", {"message": "50L flat in Pune"})
        assert "50L flat in Pune" in fake.calls[0]["user"]

    def test_annotation_hallucination_is_discarded(self):
        provider = LLMAIProvider(FakeLLM([
            {"annotation": "A truly wonderful investment for any family."},  # names nothing
        ]))
        result = provider.generate(
            "property_recommendation",
            {"recommendations": [dict(ranking.score_unit(UNITS[0], PREFS))],
             "lead": FULL_LEAD},
        )
        annotation = result["recommendations"][0]["annotation"]
        assert "wonderful investment" not in annotation
        assert annotation == result["recommendations"][0]["rationale"]

    def test_grounded_annotation_is_kept(self):
        provider = LLMAIProvider(FakeLLM([
            {"annotation": "Palm Grove is ready to move and sits inside your budget."},
        ]))
        result = provider.generate(
            "property_recommendation",
            {"recommendations": [dict(ranking.score_unit(UNITS[0], PREFS))],
             "lead": FULL_LEAD},
        )
        assert result["recommendations"][0]["annotation"].startswith("Palm Grove")


# ────────────────────────── external (STAIL) provider ────────────────────────

class TestExternalProvider:
    def test_stail_reply_is_folded_into_our_schema(self, monkeypatch):
        import httpx

        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "agent_id": "AGT-03",
                    "response": "I've understood you're looking for a 3BHK in Mumbai.",
                    "confidence_score": 0.88,
                    "escalated": False,
                    "latency_ms": 412,
                    "metadata": {"preferences": {
                        "budget_max": 15_000_000, "cities": ["Mumbai"],
                        "bhk_type": ["3BHK"], "timeline_months": 6,
                        "investment_goal": "end_use",
                    }},
                }

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["body"] = kwargs.get("json")
            return FakeResponse()

        monkeypatch.setattr(httpx, "post", fake_post)
        result = ExternalAIProvider("http://stail:8000").generate(
            "buyer_assistant", {"message": "3BHK in Mumbai under 1.5Cr"}
        )

        # Must hit STAIL's real route with their real request shape.
        assert captured["url"] == "http://stail:8000/api/v1/agents/chat"
        assert captured["body"]["agent_id"] == "AGT-03"
        assert captured["body"]["message"] == "3BHK in Mumbai under 1.5Cr"

        assert result["budget_max"] == 15_000_000
        assert result["location"] == "Mumbai"
        assert result["property_type"] == "3BHK"
        assert result["timeline"] == "6 months"
        assert result["confidence"] == 0.88
        assert result["ready_for_matching"] is True

    def test_unreachable_service_degrades(self, monkeypatch):
        import httpx

        def fake_post(url, **kwargs):
            raise httpx.ConnectError("no route to host")

        monkeypatch.setattr(httpx, "post", fake_post)
        result = ExternalAIProvider("http://stail:8000").generate(
            "buyer_assistant", {"message": "3BHK in Mumbai"}
        )
        assert "ai_degraded" in result
        assert result["next_question"] or result["ready_for_matching"] is True

    def test_agents_without_a_stail_counterpart_stay_local(self, monkeypatch):
        import httpx

        def fail(*args, **kwargs):
            raise AssertionError("must not call the agent service for this agent")

        monkeypatch.setattr(httpx, "post", fail)
        result = ExternalAIProvider("http://stail:8000").generate(
            "call_summary", {"transcript": "He will send the brochure. Sounds great."}
        )
        assert result["summary"]


# ──────────────────────────── API: chat + pipeline ───────────────────────────

def _seed_inventory(client, admin_headers):
    project = client.post(
        "/api/v1/properties/projects", headers=admin_headers,
        json={"name": "Palm Grove", "builder_name": "Test Builder",
              "location": "Whitefield, Bengaluru", "city": "Bengaluru",
              "amenities": ["Gym", "Pool"], "status": "ready_to_move",
              "units": [{"unit_number": "A-101", "unit_type": "3BHK",
                         "carpet_area_sqft": 1400, "price": 11000000}]},
    )
    assert project.status_code == 201, project.text
    return project.json()["data"]["id"]


def _seed_lead(client, admin_headers):
    resp = client.post(
        "/api/v1/leads", headers=admin_headers,
        json={"full_name": "Asha Rao", "phone": "9999900000", "source": "website"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


class TestAiChatEndpoint:
    def test_chat_extracts_and_replies(self, client, admin):
        lead_id = _seed_lead(client, admin)
        resp = client.post(
            "/api/v1/ai/chat", headers=admin,
            json={"message": "Need a 3BHK in Whitefield under 1.2Cr", "lead_id": lead_id},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["reply"]
        assert data["result"]["budget_max"] == 12_000_000
        assert data["result"]["property_type"] == "3BHK"

    def test_catalog_reports_the_active_provider(self, client, admin):
        data = client.get("/api/v1/ai/catalog", headers=admin).json()["data"]
        assert data["provider"] == "mock"
        assert "buyer_assistant" in data["pipeline"]

    def test_empty_message_rejected(self, client, admin):
        resp = client.post("/api/v1/ai/chat", headers=admin, json={"message": ""})
        assert resp.status_code == 422


class TestOrchestration:
    def test_full_pipeline_runs_and_writes_back(self, client, admin):
        _seed_inventory(client, admin)
        lead_id = _seed_lead(client, admin)

        resp = client.post(
            "/api/v1/ai/orchestrate", headers=admin,
            json={"message": "Looking for a 3BHK in Whitefield under 1.2Cr to live in, "
                             "need it within 3 months",
                  "lead_id": lead_id},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        stages = {step["agent"]: step for step in data["pipeline"]}
        assert set(stages) == {
            "buyer_assistant", "property_recommendation", "lead_qualification", "crm_sync"
        }
        assert all(step["status"] == "ok" for step in stages.values()), stages

        assert data["preferences"]["budget_max"] == 12_000_000
        assert data["recommendations"][0]["project"] == "Palm Grove"
        assert data["qualification"]["score_band"] in ("hot", "warm", "cold")

        # The pipeline must actually persist what it learned — including the
        # locality, recognised from this workspace's own inventory.
        assert set(data["crm"]["updated_fields"]) >= {
            "budget_max", "property_type", "location_preference"
        }
        lead = client.get(f"/api/v1/leads/{lead_id}", headers=admin).json()["data"]
        assert float(lead["budget_max"]) == 12_000_000
        assert lead["property_type"] == "3BHK"
        assert "Whitefield" in lead["location_preference"]

        timeline = client.get(f"/api/v1/timeline/lead/{lead_id}", headers=admin).json()["data"]
        assert any("AI pipeline" in a["title"] for a in timeline)

    def test_grade_reflects_what_the_turn_just_learned(self, client, admin):
        """Regression: the pipeline used to grade before persisting, so it
        reported "cold" for a lead whose budget and configuration it had just
        established were an exact match. Re-scoring a second later jumped the
        band — the pipeline's own answer was stale on arrival."""
        _seed_inventory(client, admin)
        lead_id = _seed_lead(client, admin)

        resp = client.post(
            "/api/v1/ai/orchestrate", headers=admin,
            json={"message": "3BHK in Whitefield, budget up to 2.5Cr, to live in",
                  "lead_id": lead_id},
        )
        assert resp.status_code == 200, resp.text
        pipeline_grade = resp.json()["data"]["qualification"]

        # crm_sync must run before lead_qualification.
        order = [s["agent"] for s in resp.json()["data"]["pipeline"]]
        assert order.index("crm_sync") < order.index("lead_qualification")

        # Scoring again immediately must land on the same band. The composite can
        # drift a point or two because every scoring run logs its own activity,
        # which legitimately lifts the engagement dimension — but the verdict a
        # salesperson acts on must not change.
        rescore = client.post(
            "/api/v1/ai/components/lead-qualification", headers=admin,
            json={"lead_id": lead_id},
        ).json()["data"]["result"]
        assert rescore["score_band"] == pipeline_grade["score_band"]
        assert abs(rescore["ai_score"] - pipeline_grade["ai_score"]) <= 5

        # And the facts the turn established must actually have moved the needle.
        assert pipeline_grade["breakdown"]["budget"]["score"] == 100
        assert pipeline_grade["breakdown"]["property_fit"]["score"] == 100
        assert pipeline_grade["score_band"] != "cold"

    def test_locality_of_a_live_project_counts_as_footprint(self, client, admin):
        """Naming the exact locality of one of your own projects is the most
        on-target a lead can be; it used to score as "outside footprint" because
        only city names were compared."""
        _seed_inventory(client, admin)  # Palm Grove, Whitefield, Bengaluru
        lead_id = _seed_lead(client, admin)
        client.patch(f"/api/v1/leads/{lead_id}", headers=admin,
                     json={"location_preference": "Whitefield"})

        result = client.post(
            "/api/v1/ai/components/lead-qualification", headers=admin,
            json={"lead_id": lead_id},
        ).json()["data"]["result"]
        geography = result["breakdown"]["geography"]
        assert geography["rule_applied"] == "location_in_footprint"
        assert geography["score"] == 100

    def test_extraction_never_overwrites_human_entered_data(self, client, admin):
        _seed_inventory(client, admin)
        resp = client.post(
            "/api/v1/leads", headers=admin,
            json={"full_name": "Vikram S", "phone": "9888800000", "source": "website",
                  "budget_max": 25000000, "property_type": "villa"},
        )
        lead_id = resp.json()["data"]["id"]

        client.post(
            "/api/v1/ai/orchestrate", headers=admin,
            json={"message": "actually just a 2BHK under 50L", "lead_id": lead_id},
        )
        lead = client.get(f"/api/v1/leads/{lead_id}", headers=admin).json()["data"]
        assert float(lead["budget_max"]) == 25000000
        assert lead["property_type"] == "villa"

    def test_pipeline_without_a_lead_skips_persistence_explicitly(self, client, admin):
        _seed_inventory(client, admin)
        resp = client.post(
            "/api/v1/ai/orchestrate", headers=admin,
            json={"message": "3BHK in Whitefield under 1.2Cr"},
        )
        assert resp.status_code == 200, resp.text
        stages = {s["agent"]: s for s in resp.json()["data"]["pipeline"]}
        assert stages["lead_qualification"]["status"] == "skipped"
        assert stages["crm_sync"]["status"] == "skipped"
        assert stages["crm_sync"]["reason"]

    def test_pipeline_respects_lead_scope(self, client, admin):
        """A telecaller must not orchestrate against someone else's lead."""
        lead_id = _seed_lead(client, admin)  # owned by the admin
        create_user_as_admin(client, admin, "caller@stail.com", "telecaller")
        caller = auth_headers(client, "caller@stail.com")

        resp = client.post(
            "/api/v1/ai/orchestrate", headers=caller,
            json={"message": "3BHK under 1Cr", "lead_id": lead_id},
        )
        assert resp.status_code == 404, resp.text


class TestQualificationUsesTenantConfig:
    def test_onboarding_thresholds_change_the_band(self, client, admin):
        _seed_inventory(client, admin)
        lead_id = _seed_lead(client, admin)
        client.patch(
            "/api/v1/leads/" + lead_id, headers=admin,
            json={"budget_max": 11000000, "location_preference": "Whitefield, Bengaluru",
                  "property_type": "3BHK", "stage": "site_visit_scheduled"},
        )

        def band():
            resp = client.post(
                "/api/v1/ai/components/lead-qualification", headers=admin,
                json={"lead_id": lead_id},
            )
            assert resp.status_code == 200, resp.text
            return resp.json()["data"]["result"]["score_band"]

        assert band() == "hot"

        # Same lead, stricter rubric configured during onboarding.
        client.patch(
            "/api/v1/onboarding/step", headers=admin,
            json={"step_id": "5", "data": {"leadBands": {"hot": 100, "warm": 99}}},
        )
        assert band() == "cold"


class TestInventorySummary:
    """The AI context needs a price band, stocked configurations, and the
    workspace's cities/localities on every request. Computing them in SQL rather
    than by loading every unit keeps the cost flat as inventory grows — but the
    numbers must stay identical, because grading reads them."""

    def test_summary_matches_a_row_by_row_computation(self, client, admin):
        from app.db.base import SessionLocal
        from app.modules.ai.service import _available_units, _inventory_summary

        client.post(
            "/api/v1/properties/projects", headers=admin,
            json={"name": "Palm Grove", "builder_name": "B",
                  "location": "Whitefield", "city": "Bengaluru",
                  "status": "ready_to_move",
                  "units": [
                      {"unit_number": "A-1", "unit_type": "2BHK", "price": 12000000},
                      {"unit_number": "A-2", "unit_type": "3BHK", "price": 22000000},
                      {"unit_number": "A-3", "unit_type": "3BHK", "price": 24000000},
                  ]},
        )
        me = client.get("/api/v1/auth/me", headers=admin).json()["data"]

        from app.modules.auth.models import User

        with SessionLocal() as db:
            tenant_id = db.get(User, me["id"]).tenant_id
            units = _available_units(db, tenant_id)
            prices = [u["price"] for u in units if u.get("price")]
            expected = {
                "unit_count": len(units),
                "min_price": min(prices), "max_price": max(prices),
                "unit_types": sorted({u["unit_type"] for u in units}),
                "cities": sorted({u["city"] for u in units}),
                "localities": sorted({u["location"] for u in units}),
            }
            assert _inventory_summary(db, tenant_id) == expected

    def test_empty_inventory_is_not_a_crash(self, client, admin):
        from app.db.base import SessionLocal
        from app.modules.ai.service import _inventory_summary
        from app.modules.auth.models import User

        me = client.get("/api/v1/auth/me", headers=admin).json()["data"]
        with SessionLocal() as db:
            summary = _inventory_summary(db, db.get(User, me["id"]).tenant_id)
        assert summary["unit_count"] == 0
        assert summary["min_price"] is None and summary["max_price"] is None
        assert summary["unit_types"] == [] and summary["localities"] == []
