"""Composite property ranking.

A port of STAIL's `agents/recommendation-agent` scoring (relevance 60% +
market appeal 20% + buyer fit 20%) onto this CRM's own inventory model, replacing
the earlier all-or-nothing preference filter that dropped a unit entirely the
moment one preference missed.

Every component returns 0.0–1.0 and every unit gets a `match_reasons` /
`gap_reasons` pair, so the ranking a salesperson sees is always explainable.
"""
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any

# Weights on the three components of the composite score.
W_RELEVANCE = 0.60
W_MARKET_APPEAL = 0.20
W_BUYER_FIT = 0.20

# Project statuses that make a unit intrinsically more sellable.
APPEALING_STATUSES = {"ready_to_move", "ready", "nearing_possession", "oc_received"}


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(Decimal(str(value)))
    except (ValueError, ArithmeticError):
        return None


def _relevance(unit: dict, prefs: dict) -> tuple[float, list[str], list[str]]:
    """How well the unit matches what the buyer asked for."""
    score = 0.0
    matched: list[str] = []
    missed: list[str] = []

    location = (prefs.get("location") or "").strip().lower()
    haystack = f"{unit.get('location') or ''} {unit.get('city') or ''}".lower()
    if location:
        # Compare the first comma-separated part word-by-word: "Whitefield,
        # Bengaluru" should still match a project stored as just "Whitefield".
        tokens = [t for t in location.split(",")[0].split() if len(t) > 2]
        if tokens and any(t in haystack for t in tokens):
            score += 0.30
            matched.append("location")
        else:
            missed.append("location")

    wanted_type = (prefs.get("property_type") or "").strip().lower().replace(" ", "")
    unit_type = (unit.get("unit_type") or "").strip().lower().replace(" ", "")
    if wanted_type:
        if unit_type and (wanted_type in unit_type or unit_type in wanted_type):
            score += 0.30
            matched.append("property type")
        else:
            missed.append("property type")

    budget_max = _as_float(prefs.get("budget_max"))
    budget_min = _as_float(prefs.get("budget_min"))
    price = _as_float(unit.get("price"))
    if budget_max and price:
        if price <= budget_max:
            score += 0.25
            matched.append("budget")
        elif price <= budget_max * 1.20:
            # Within 20% is a negotiation away — worth surfacing, flagged as a stretch.
            score += 0.12
            matched.append("budget (stretch)")
        else:
            # Actively penalised, not merely uncredited. Scoring an unaffordable
            # unit as a plain zero let a ₹2.2Cr flat outrank an in-budget ₹1.2Cr
            # one purely on a configuration match — the shortlist led with
            # something the buyer cannot buy.
            score -= 0.20
            missed.append("budget")
    elif budget_min and price and price >= budget_min:
        score += 0.15
        matched.append("budget floor")

    min_area = _as_float(prefs.get("min_carpet_area_sqft"))
    area = _as_float(unit.get("carpet_area_sqft"))
    if min_area and area:
        if area >= min_area:
            score += 0.15
            matched.append("carpet area")
        else:
            missed.append("carpet area")

    # Clamped at both ends: the over-budget penalty can drive an otherwise
    # unmatched unit negative, and a negative relevance would break the ordering
    # against units that simply have no signal either way.
    return max(0.0, min(score, 1.0)), matched, missed


def _market_appeal(unit: dict) -> float:
    """Intrinsic sellability, independent of this particular buyer."""
    score = 0.30  # base floor, as in STAIL
    if (unit.get("project_status") or "").lower() in APPEALING_STATUSES:
        score += 0.40
    created_at = unit.get("created_at")
    if created_at:
        try:
            listed = (
                datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                if isinstance(created_at, str) else created_at
            )
            if listed.tzinfo is None:
                listed = listed.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - listed).days < 30:
                score += 0.30
        except (ValueError, TypeError):
            pass
    return min(score, 1.0)


def _buyer_fit(unit: dict, prefs: dict) -> float:
    """Lifestyle fit — amenity depth matters to end users, not to investors."""
    purpose = (prefs.get("purpose") or prefs.get("investment_goal") or "").lower()
    amenities = unit.get("amenities") or []
    if purpose in ("investment", "rental", "rental_income"):
        return 0.5  # neutral: yield, not amenities, drives the decision
    if isinstance(amenities, list) and amenities:
        return min(len(amenities) * 0.2, 1.0)
    return 0.3


def score_unit(unit: dict, prefs: dict) -> dict[str, Any]:
    """Score one unit and return it annotated with the full breakdown."""
    relevance, matched, missed = _relevance(unit, prefs)
    appeal = _market_appeal(unit)
    fit = _buyer_fit(unit, prefs)
    composite = min(
        relevance * W_RELEVANCE + appeal * W_MARKET_APPEAL + fit * W_BUYER_FIT, 1.0
    )

    if matched:
        rationale = f"Matches {', '.join(matched)}"
        if missed:
            rationale += f"; misses {', '.join(missed)}"
    elif missed:
        rationale = f"Misses {', '.join(missed)}"
    else:
        rationale = "No stated preferences — ranked on market appeal"

    return {
        "unit_id": unit.get("unit_id"),
        "project": unit.get("project"),
        "unit_number": unit.get("unit_number"),
        "unit_type": unit.get("unit_type"),
        "price": _as_float(unit.get("price")),
        "location": unit.get("location"),
        "city": unit.get("city"),
        "carpet_area_sqft": _as_float(unit.get("carpet_area_sqft")),
        "amenities": unit.get("amenities") or [],
        "match_score": round(composite, 2),
        "score_breakdown": {
            "relevance": round(relevance, 2),
            "market_appeal": round(appeal, 2),
            "buyer_fit": round(fit, 2),
        },
        "match_reasons": matched,
        "gap_reasons": missed,
        "rationale": rationale,
    }


def rank_units(units: list[dict], prefs: dict, *, limit: int = 5) -> list[dict]:
    """Rank every unit; return the best `limit`.

    Nothing is filtered out. A unit that misses on budget but nails location is
    still a real option for a salesperson to pitch — it just ranks lower. The
    previous implementation discarded it silently.
    """
    scored = [score_unit(u, prefs) for u in units]
    scored.sort(key=lambda r: (-r["match_score"], r["price"] or 0.0))
    return scored[:limit]
