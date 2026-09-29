"""Deterministic, explainable lead grading.

A port of STAIL's `agents/lead-qualification-agent/scoring/` engine (per-dimension
sub-scores → weighted composite → letter grade → recommended action → human-review
flag), rebuilt around the dimensions this CRM actually has data for, and driven by
the weights and thresholds the admin sets during onboarding (the "AI lead scoring
configuration" step, which mirrors §8–§9 of AI_Lead_Generation_Configuration_Form.md).

Zero LLM calls live here. The LLM provider layers narrative on top of this, but the
numbers a salesperson acts on are always reproducible and auditable.
"""
from typing import Any

# Six dimensions, each scored 0–100 before weighting. Weights must sum to 1.0;
# `resolve_config` renormalises whatever the tenant supplies.
DEFAULT_WEIGHTS: dict[str, float] = {
    "budget": 0.25,
    "intent": 0.25,
    "geography": 0.15,
    "property_fit": 0.15,
    "engagement": 0.10,
    "contactability": 0.10,
}

# Composite score at or above which a lead earns each band / letter grade.
DEFAULT_THRESHOLDS: dict[str, int] = {"hot": 70, "warm": 40}
DEFAULT_GRADES: dict[str, int] = {"A": 80, "B": 60, "C": 40, "D": 0}

# Pipeline stage → intent sub-score. A lead deep in the funnel has demonstrated
# intent regardless of what it wrote on the enquiry form.
STAGE_INTENT: dict[str, int] = {
    "new": 20,
    "contacted": 35,
    "qualified": 55,
    "interested": 70,
    "site_visit_scheduled": 85,
    "negotiation": 95,
    "booked": 100,
    "completed": 100,
    "lost": 5,
}

# Timeline words in the free-text requirement, strongest first.
TIMELINE_SIGNALS: list[tuple[tuple[str, ...], int, str]] = [
    (("immediate", "urgent", "asap", "this month", "ready to buy"), 100, "immediate timeline"),
    (("1 month", "30 days", "within a month"), 90, "within a month"),
    (("3 month", "quarter", "90 days"), 75, "within 3 months"),
    (("6 month", "half year"), 55, "within 6 months"),
    (("1 year", "12 month", "next year"), 35, "within a year"),
    (("just looking", "researching", "exploring", "no hurry"), 10, "researching only"),
]

RECOMMENDED_ACTIONS: dict[str, str] = {
    "A": "Call within 15 minutes and offer two site-visit slots today.",
    "B": "Call today, send a matched shortlist, and book a site visit this week.",
    "C": "Add to a nurture sequence and re-qualify budget and timeline on the next touch.",
    "D": "Keep in long-term drip; revisit in 90 days unless the lead re-engages.",
}

# Below this, the inputs were too sparse to trust the grade unreviewed.
DEFAULT_REVIEW_THRESHOLD = 0.5


def resolve_config(onboarding_data: dict | None) -> dict[str, Any]:
    """Read scoring weights and band thresholds out of the tenant's onboarding data.

    Falls back to the defaults for anything missing or unusable, so a tenant that
    skipped the step still gets sane grading. Weights are renormalised rather than
    validated: an admin who types 30/30/30/30/30/30 in the UI means "equal", not
    "invalid".
    """
    config = (onboarding_data or {}).get("5") or {}
    raw_weights = config.get("scoringWeights") or {}
    weights: dict[str, float] = {}
    for dimension, default in DEFAULT_WEIGHTS.items():
        try:
            value = float(raw_weights.get(dimension, default))
        except (TypeError, ValueError):
            value = default
        weights[dimension] = max(value, 0.0)
    total = sum(weights.values())
    if total <= 0:
        weights = dict(DEFAULT_WEIGHTS)
    else:
        weights = {k: v / total for k, v in weights.items()}

    raw_bands = config.get("leadBands") or {}
    thresholds: dict[str, int] = {}
    for band, default in DEFAULT_THRESHOLDS.items():
        try:
            thresholds[band] = int(raw_bands.get(band, default))
        except (TypeError, ValueError):
            thresholds[band] = default
    # A "hot" floor below the "warm" floor would make warm unreachable.
    if thresholds["hot"] <= thresholds["warm"]:
        thresholds = dict(DEFAULT_THRESHOLDS)

    return {"weights": weights, "thresholds": thresholds, "grades": dict(DEFAULT_GRADES)}


def _sub(score: int, rule: str, factors: list[str]) -> dict[str, Any]:
    return {"score": max(0, min(100, int(score))), "rule_applied": rule,
            "contributing_factors": factors}


def _score_budget(lead: dict, inventory: dict | None) -> dict[str, Any]:
    low, high = lead.get("budget_min"), lead.get("budget_max")
    if not low and not high:
        return _sub(15, "budget_not_disclosed", ["No budget captured yet"])

    stated = float(high or low)
    if not inventory or not inventory.get("min_price"):
        return _sub(70, "budget_disclosed_no_inventory_band",
                    ["Budget disclosed; no live inventory to compare against"])

    # Only the entry price matters. A budget above the top of the range is an
    # upsell opportunity, never a penalty — the same call STAIL's BudgetScorer makes.
    floor = float(inventory["min_price"])
    if stated >= floor:
        return _sub(100, "budget_fit",
                    [f"Budget reaches available inventory (from {floor:,.0f})"])
    if stated >= floor * 0.7:
        return _sub(60, "budget_stretch",
                    [f"Budget is within 30% of the entry price ({floor:,.0f})"])
    return _sub(20, "budget_mismatch",
                [f"Budget is well below the entry price ({floor:,.0f})"])


def _score_intent(lead: dict) -> dict[str, Any]:
    stage = lead.get("stage") or "new"
    score = STAGE_INTENT.get(stage, 20)
    factors = [f"Pipeline stage '{stage.replace('_', ' ')}'"]
    rule = f"stage_{stage}"

    requirements = " ".join(
        str(v) for v in [lead.get("requirements"), lead.get("timeline")] if v
    ).lower()
    for words, timeline_score, label in TIMELINE_SIGNALS:
        if any(w in requirements for w in words):
            factors.append(f"Stated {label}")
            # Stage and stated timeline are independent evidence — take the
            # stronger signal rather than averaging one away.
            if timeline_score > score:
                score, rule = timeline_score, f"timeline_{label.replace(' ', '_')}"
            break
    return _sub(score, rule, factors)


def _score_geography(lead: dict, operating_cities: list[str]) -> dict[str, Any]:
    """`operating_cities` is the whole footprint: the cities the admin declared
    plus the cities *and localities* where live inventory actually sits."""
    preference = (lead.get("location_preference") or "").strip()
    if not preference:
        return _sub(20, "location_unknown", ["No location preference captured"])
    if not operating_cities:
        return _sub(70, "location_known_no_footprint",
                    [f"Prefers {preference}; company footprint not configured"])
    needle = preference.lower()
    for city in operating_cities:
        if city and (city.lower() in needle or needle in city.lower()):
            return _sub(100, "location_in_footprint",
                        [f"Prefers {preference} — inside your operating cities"])
    return _sub(35, "location_outside_footprint",
                [f"Prefers {preference} — outside your operating cities"])


def _score_property_fit(lead: dict, inventory: dict | None) -> dict[str, Any]:
    wanted = (lead.get("property_type") or "").strip()
    if not wanted:
        return _sub(20, "property_type_unknown", ["No property type captured"])
    types = [t.lower() for t in ((inventory or {}).get("unit_types") or [])]
    if not types:
        return _sub(70, "property_type_known_no_inventory",
                    [f"Wants {wanted}; no live inventory to compare against"])
    needle = wanted.lower().replace(" ", "")
    if any(needle in t.replace(" ", "") or t.replace(" ", "") in needle for t in types):
        return _sub(100, "property_type_in_stock", [f"{wanted} is in your live inventory"])
    return _sub(40, "property_type_not_in_stock",
                [f"{wanted} is not in your current inventory"])


def _score_engagement(activity_count: int, notes_count: int) -> dict[str, Any]:
    total = activity_count + notes_count
    if total == 0:
        return _sub(10, "no_engagement", ["No logged activity yet"])
    score = min(100, 25 + total * 12)
    return _sub(score, "engagement_logged",
                [f"{activity_count} activity/activities, {notes_count} note(s)"])


def _score_contactability(lead: dict) -> dict[str, Any]:
    factors, score = [], 0
    if lead.get("phone"):
        score += 55
        factors.append("Phone captured")
    if lead.get("email"):
        score += 45
        factors.append("Email captured")
    if not factors:
        return _sub(0, "no_contact_channel", ["Neither phone nor email captured"])
    return _sub(score, "contactable", factors)


def _extraction_confidence(lead: dict) -> float:
    """How much of the qualification surface is actually filled in.

    STAIL derives this from LLM extraction confidence; here the equivalent
    question is how complete the record is, which is what makes a grade
    trustworthy or not.
    """
    fields = [
        bool(lead.get("phone") or lead.get("email")),
        bool(lead.get("budget_min") or lead.get("budget_max")),
        bool(lead.get("location_preference")),
        bool(lead.get("property_type")),
        bool(lead.get("requirements")),
    ]
    return round(sum(fields) / len(fields), 2)


def grade_lead(
    lead: dict,
    *,
    activity_count: int = 0,
    notes_count: int = 0,
    inventory: dict | None = None,
    operating_cities: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score one lead across all six dimensions and return the full breakdown."""
    cfg = config or resolve_config(None)
    weights, thresholds, grades = cfg["weights"], cfg["thresholds"], cfg["grades"]

    breakdown = {
        "budget": _score_budget(lead, inventory),
        "intent": _score_intent(lead),
        "geography": _score_geography(lead, operating_cities or []),
        "property_fit": _score_property_fit(lead, inventory),
        "engagement": _score_engagement(activity_count, notes_count),
        "contactability": _score_contactability(lead),
    }

    composite = sum(breakdown[dim]["score"] * weights[dim] for dim in weights)
    composite = round(composite, 1)

    band = (
        "hot" if composite >= thresholds["hot"]
        else "warm" if composite >= thresholds["warm"]
        else "cold"
    )
    grade = next(
        (g for g, floor in sorted(grades.items(), key=lambda kv: kv[1], reverse=True)
         if composite >= floor),
        "D",
    )
    confidence = _extraction_confidence(lead)

    explanation = [
        f"{dim.replace('_', ' ')}: {breakdown[dim]['score']}/100 "
        f"× {weights[dim]:.0%} — {'; '.join(breakdown[dim]['contributing_factors'])}"
        for dim in weights
    ]

    return {
        "ai_score": composite,
        "score_band": band,
        "grade": grade,
        # Historic field: kept because the leads UI and stored insights read it.
        "buying_probability": round(min(composite / 100 * 0.85, 0.85), 2),
        "sales_readiness": band != "cold",
        "explanation": explanation,
        "breakdown": breakdown,
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "thresholds": thresholds,
        "extraction_confidence": confidence,
        "needs_human_review": confidence < DEFAULT_REVIEW_THRESHOLD,
        "recommended_action": RECOMMENDED_ACTIONS[grade],
        "reasoning_summary": (
            f"Grade {grade} (composite {composite}/100, band {band})."
            + (" Record is sparse — human review recommended."
               if confidence < DEFAULT_REVIEW_THRESHOLD else "")
        ),
    }
