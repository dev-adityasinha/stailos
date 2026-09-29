"""AI provider abstraction.

Every AI widget/component calls `get_provider().generate(agent, context)` and
receives structured JSON. Three providers, all returning the same schemas, so the
frontend never changes when you swap them (`AI_PROVIDER=…`):

* ``mock`` — deterministic, rule-based output computed from the real CRM context.
  No network, no key, no cost. Still the default, and still the floor every other
  provider falls back to.
* ``llm`` — real generation via any OpenAI-compatible endpoint (Groq by default,
  matching the STAIL Realty OS agents). The deterministic payload is computed
  first, then the model is asked to enrich a fixed allow-list of narrative fields.
  Scores are never model-generated.
* ``external`` — proxies to a running STAIL agent service
  (``POST {base}/api/v1/agents/chat``), mapping our agent names onto their AGT-xx
  ids and folding the reply back into our schema.
"""
import logging
from typing import Any, Protocol

from app.core.config import get_settings
from app.modules.ai import grading, prompts
from app.modules.ai.llm import LLMClient, LLMError, mentions_any, parse_inr

logger = logging.getLogger("crm.ai.provider")

STAGE_ACTIONS: dict[str, dict[str, str]] = {
    "new": {"action": "Make first contact call",
            "reason": "Lead is new — first contact within 15 minutes lifts conversion sharply."},
    "contacted": {"action": "Send a shortlist of 3 matching properties",
                  "reason": "Contact made; concrete options keep momentum."},
    "qualified": {"action": "Schedule a discovery call to lock budget and timeline",
                  "reason": "Qualification done; move to needs-mapping."},
    "interested": {"action": "Propose two site-visit slots this week",
                   "reason": "Interest expressed; site visits convert ~3x better."},
    "site_visit_scheduled": {"action": "Confirm the site visit 24h ahead and arrange pickup",
                             "reason": "Confirmed visits show up ~40% more often."},
    "negotiation": {"action": "Prepare a payment-plan comparison and request approval room",
                    "reason": "Deals in negotiation stall without concrete numbers."},
    "booked": {"action": "Start documentation checklist and collect KYC",
               "reason": "Fast documentation shortens time-to-agreement."},
    "completed": {"action": "Ask for a referral and a review",
                  "reason": "Post-sale is the best moment for referrals."},
    "lost": {"action": "Schedule a 90-day re-engagement reminder",
             "reason": "Lost leads often re-enter the market within a quarter."},
}

SALES_TIPS = [
    "Lead with the location story — commute, schools, appreciation — before the spec sheet.",
    "Quote all-in prices (registration + GST + amenities) to build trust early.",
    "Always offer exactly two site-visit slots; open-ended scheduling stalls deals.",
    "Mirror the buyer's channel: WhatsApp buyers rarely answer cold calls.",
    "Anchor with the higher-priced unit first; the target unit then feels attainable.",
    "Log every objection in notes — patterns across leads reveal inventory issues.",
]


class AIProvider(Protocol):
    name: str

    def generate(self, agent: str, context: dict[str, Any]) -> dict[str, Any]: ...


class MockAIProvider:
    """Deterministic, rule-based generation over real CRM context."""

    name = "mock"

    def generate(self, agent: str, context: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_{agent}", None)
        if handler is None:
            raise ValueError(f"Unknown AI agent '{agent}'")
        return handler(context)

    # ------------------------------------------------------------- widgets

    def _lead_summary(self, ctx: dict) -> dict:
        lead = ctx["lead"]
        acts = ctx.get("activities", [])
        budget = self._budget_text(lead.get("budget_min"), lead.get("budget_max"))
        highlights = []
        if lead.get("property_type"):
            highlights.append(f"Looking for a {lead['property_type']}")
        if lead.get("location_preference"):
            highlights.append(f"preferred area: {lead['location_preference']}")
        if budget:
            highlights.append(f"budget {budget}")
        return {
            "summary": (
                f"{lead['full_name']} ({lead['source'].replace('_', ' ')} lead, "
                f"stage: {lead['stage'].replace('_', ' ')}). "
                + (". ".join(highlights) + "." if highlights else "Profile is sparse — qualify on the next call.")
            ),
            "engagement": {
                "total_activities": len(acts),
                "last_activity": acts[0]["title"] if acts else None,
                "notes_count": ctx.get("notes_count", 0),
            },
            "data_gaps": [
                field for field, present in [
                    ("email", bool(lead.get("email"))),
                    ("budget", bool(lead.get("budget_min") or lead.get("budget_max"))),
                    ("location_preference", bool(lead.get("location_preference"))),
                    ("property_type", bool(lead.get("property_type"))),
                ] if not present
            ],
        }

    def _customer_summary(self, ctx: dict) -> dict:
        c = ctx["customer"]
        bookings = ctx.get("bookings", [])
        active = [b for b in bookings if b["status"] == "active"]
        return {
            "summary": (
                f"{c['full_name']}"
                + (f", {c['occupation']}" if c.get("occupation") else "")
                + (f" at {c['company']}" if c.get("company") else "")
                + (f", based in {c['city']}" if c.get("city") else "")
                + f". {len(bookings)} booking(s), {len(active)} active. "
                + (f"Budget {self._budget_text(c.get('budget_min'), c.get('budget_max'))}."
                   if c.get("budget_min") or c.get("budget_max") else "")
            ).strip(),
            "relationship": {
                "bookings_total": len(bookings),
                "bookings_active": len(active),
                "properties_shortlisted": ctx.get("shortlist_count", 0),
                "family_size": len(c.get("family_info") or []),
            },
            "preferences": c.get("preferences") or {},
        }

    def _suggestions(self, ctx: dict) -> dict:
        stage = (ctx.get("lead") or {}).get("stage", "new")
        base = STAGE_ACTIONS.get(stage, STAGE_ACTIONS["new"])
        items = [{"suggestion": base["action"], "reason": base["reason"], "priority": "high"}]
        lead = ctx.get("lead") or {}
        if not lead.get("email"):
            items.append({"suggestion": "Capture the email address on the next touchpoint",
                          "reason": "Enables document sharing and drip campaigns.",
                          "priority": "medium"})
        if ctx.get("days_since_update", 0) > 5:
            items.append({"suggestion": "Re-engage — no activity for over 5 days",
                          "reason": "Stale leads decay fast; a nudge keeps you top of mind.",
                          "priority": "high"})
        return {"suggestions": items}

    def _next_best_action(self, ctx: dict) -> dict:
        stage = (ctx.get("lead") or {}).get("stage", "new")
        base = STAGE_ACTIONS.get(stage, STAGE_ACTIONS["new"])
        return {"action": base["action"], "reason": base["reason"],
                "stage": stage, "confidence": 0.8}

    def _investment_insights(self, ctx: dict) -> dict:
        units = ctx.get("matching_units", [])
        budget_max = ctx.get("budget_max")
        # Ranked units are never filtered out now, so a unit with an unpriced
        # (₹0/None) placeholder can appear — exclude it from the average rather
        # than dragging the whole snapshot toward zero.
        prices = [u["price"] for u in units if u.get("price")]
        avg_price = (sum(prices) / len(prices)) if prices else None
        return {
            "market_snapshot": {
                "matching_inventory": len(units),
                "avg_matching_price": round(avg_price, 2) if avg_price else None,
                "price_band_fit": (
                    "within budget" if avg_price and budget_max and avg_price <= budget_max
                    else "stretch" if avg_price else "unknown"
                ),
            },
            "assumptions": {
                "gross_rental_yield_pct": 3.0,
                "capital_appreciation_pct_pa": 6.5,
                "note": "Indicative city-level assumptions — informational only, "
                        "not licensed financial advice.",
            },
            "estimated_rental_income_monthly": (
                round(avg_price * 0.03 / 12, 0) if avg_price else None
            ),
        }

    def _sales_tips(self, ctx: dict) -> dict:
        """Generic playbook tips, plus tips built from this workspace's own ICP.

        The ideal-customer step collects the objections and triggers this builder
        actually hears. Those were stored and never used, so every workspace saw
        the same six generic lines — the tips now lead with the seller's own
        answers, which is the whole point of having asked.
        """
        stage = (ctx.get("lead") or {}).get("stage")
        icp = ctx.get("icp") or {}
        tips: list[str] = []

        objections = [str(o) for o in (icp.get("objections") or []) if o]
        if objections:
            tips.append(
                f"Pre-empt your most common objection — {objections[0].lower()} — "
                "before they raise it; you lose the frame once they say it first."
            )
        triggers = [str(t) for t in (icp.get("triggers") or []) if t]
        if triggers:
            tips.append(
                f"Lead with what moves your buyers: {', '.join(t.lower() for t in triggers[:2])}."
            )
        pains = [str(p) for p in (icp.get("painPoints") or []) if p]
        if pains:
            tips.append(
                f"Have proof ready for {pains[0].lower()} — it is the doubt your "
                "segment brings to every call."
            )

        idx = sum(ord(ch) for ch in (ctx.get("entity_id") or "x")) % len(SALES_TIPS)
        rotated = SALES_TIPS[idx:] + SALES_TIPS[:idx]
        tips.extend(rotated)
        return {"tips": tips[:3], "stage_context": stage,
                "grounded_in_icp": bool(objections or triggers or pains)}

    def _property_recommendations(self, ctx: dict) -> dict:
        return {"recommendations": ctx.get("recommendations", [])}

    # ---------------------------------------------------------- components

    def _lead_qualification(self, ctx: dict) -> dict:
        """Weighted, per-dimension grading (see `grading.py`).

        The tenant's own scoring weights and band thresholds — set during
        onboarding — drive this, so two workspaces selling very different
        inventory don't share one hardcoded rubric.
        """
        return grading.grade_lead(
            ctx["lead"],
            activity_count=len(ctx.get("activities", [])),
            notes_count=ctx.get("notes_count", 0),
            inventory=ctx.get("inventory"),
            operating_cities=ctx.get("operating_cities") or [],
            config=ctx.get("scoring_config") or grading.resolve_config(None),
        )

    def _buyer_assistant(self, ctx: dict) -> dict:
        """Slot-filling over whatever the buyer has told us so far.

        `requirements` may arrive as a structured dict (from a form) or as free
        text (from a chat turn); free text is mined with the same shorthand
        parser the STAIL buyer agent uses as its regex fallback.
        """
        req = ctx.get("requirements") or {}
        if isinstance(req, str):
            req = self._mine_requirements(req)
        elif not isinstance(req, dict):
            req = {}
        message = ctx.get("message") or ""
        if message:
            # Places are matched against this workspace's own cities and localities
            # rather than a hardcoded city list (STAIL's fallback hardcoded ten
            # Indian cities, so it silently ignored every other market).
            inventory = ctx.get("inventory") or {}
            places = [
                *(ctx.get("operating_cities") or []),
                *(inventory.get("cities") or []),
                *(inventory.get("localities") or []),
            ]
            # Never let a mined value overwrite one that was stated explicitly.
            mined = self._mine_requirements(message, places)
            req = {**mined, **{k: v for k, v in req.items() if v}}

        slots = ["budget", "location", "property_type", "timeline"]
        captured = {s: req.get(s) for s in slots if req.get(s)}
        missing = [s for s in slots if not req.get(s)]
        questions = {
            "budget": "What budget range are you comfortable with?",
            "location": "Which areas or neighbourhoods do you prefer?",
            "property_type": "Are you looking for an apartment, villa, or plot?",
            "timeline": "When are you planning to move or invest?",
        }
        return {
            "captured_requirements": captured,
            "budget_min": req.get("budget_min"),
            "budget_max": req.get("budget_max"),
            "location": req.get("location"),
            "property_type": req.get("property_type"),
            "timeline": req.get("timeline"),
            "purpose": req.get("purpose"),
            "confidence": round(len(captured) / len(slots), 2),
            "missing_fields": missing,
            "next_question": questions[missing[0]] if missing else None,
            "ready_for_matching": not missing,
            "disclosure": "This assistant is AI-powered.",
        }

    @staticmethod
    def _mine_requirements(text: str, places: list[str] | None = None) -> dict:
        """Regex extraction of budget / config / location / timeline from free text.

        Ported from `BuyerAgent._deterministic_fallback` in STAIL. Deliberately
        conservative: it only claims a field when the pattern is unambiguous, so
        the LLM path (or the next question) still handles everything else.
        """
        import re

        mined: dict[str, Any] = {}
        lowered = text.lower()

        # Longest first, so "Whitefield, Bengaluru" wins over bare "Bengaluru".
        # Each place is also tried by its leading segment, because inventory
        # stores "Whitefield, Bengaluru" while buyers just say "Whitefield" —
        # the canonical stored value is what gets recorded either way.
        for place in sorted({p for p in (places or []) if p}, key=len, reverse=True):
            needles = {place.lower(), place.lower().split(",")[0].strip()}
            if any(re.search(rf"\b{re.escape(n)}\b", lowered) for n in needles if n):
                mined["location"] = place
                break

        budget = re.search(
            r"(?:under|below|upto|up to|max|budget|around|about)?\s*₹?\s*"
            r"([\d.]+)\s*(cr|crore|crores|l|lakh|lakhs|lac|lacs)\b",
            lowered,
        )
        if budget:
            value = parse_inr(budget.group(1) + budget.group(2))
            if value:
                mined["budget_max"] = value
                mined["budget"] = f"up to ₹{value:,}"

        config = re.search(r"\b([1-5])\s*(?:bhk|bedroom)", lowered)
        if config:
            mined["property_type"] = f"{config.group(1)}BHK"
        else:
            for kind in ("villa", "plot", "penthouse", "studio", "office", "shop", "warehouse"):
                if kind in lowered:
                    mined["property_type"] = kind
                    break

        for words, label in [
            (("immediate", "asap", "urgent", "right away"), "immediate"),
            (("3 month", "three month", "quarter"), "3 months"),
            (("6 month", "six month"), "6 months"),
            (("1 year", "one year", "next year"), "1 year"),
            (("just looking", "researching", "exploring"), "researching"),
        ]:
            if any(w in lowered for w in words):
                mined["timeline"] = label
                break

        if any(w in lowered for w in ("investment", "invest", "rental yield", "roi")):
            mined["purpose"] = "investment"
        elif any(w in lowered for w in ("live in", "self use", "family", "end use", "move in")):
            mined["purpose"] = "end_use"

        return mined

    def _property_recommendation(self, ctx: dict) -> dict:
        return {"recommendations": ctx.get("recommendations", []),
                "disclosure": "Ranked by preference match; rationale shown per item."}

    def _follow_up(self, ctx: dict) -> dict:
        lead = ctx.get("lead") or ctx.get("customer") or {}
        name = (lead.get("full_name") or "there").split()[0]
        stage = lead.get("stage", "contacted")
        drafts = {
            "whatsapp": f"Hi {name}! Following up on our conversation — I've found a few "
                        f"options that fit what you described. When would be a good time "
                        f"for a quick call?",
            "email_subject": "Your property shortlist is ready",
            "email_body": f"Dear {name},\n\nThank you for your time. Based on your "
                          f"requirements I have prepared a shortlist that matches your "
                          f"preferences. Could we schedule 15 minutes this week to walk "
                          f"through them?\n\nBest regards",
            "call_script_opener": f"Hi {name}, this is a quick follow-up on your property "
                                  f"search — is now a good time?",
        }
        return {"drafts": drafts, "stage": stage,
                "requires_human_approval": True}

    def _email_generator(self, ctx: dict) -> dict:
        recipient = (ctx.get("recipient_name") or "Customer").split()[0]
        purpose = ctx.get("purpose", "follow_up")
        subject_map = {
            "follow_up": "Following up on your property search",
            "site_visit": "Your site visit is confirmed",
            "booking": "Next steps for your booking",
            "payment_reminder": "Payment milestone reminder",
        }
        subject = subject_map.get(purpose, subject_map["follow_up"])
        body = (
            f"Dear {recipient},\n\n"
            + ctx.get("key_points_text",
                      "Thank you for your continued interest. Please find the details below.")
            + "\n\nWarm regards,\n" + (ctx.get("sender_name") or "Sales Team")
        )
        return {"subject": subject, "body": body, "requires_human_approval": True}

    def _whatsapp_assistant(self, ctx: dict) -> dict:
        recipient = (ctx.get("recipient_name") or "there").split()[0]
        intent = ctx.get("intent", "follow_up")
        messages = {
            "follow_up": f"Hi {recipient}! Just checking in on your property search. "
                         f"Any questions I can help with?",
            "site_visit_reminder": f"Hi {recipient}, reminder: your site visit is scheduled "
                                   f"for tomorrow. Shall I arrange a pickup?",
            "new_options": f"Hi {recipient}! Two new units matching your budget just came "
                           f"up. Want me to send the details?",
        }
        return {"message": messages.get(intent, messages["follow_up"]),
                "intent": intent, "requires_human_approval": True}

    def _call_summary(self, ctx: dict) -> dict:
        transcript = (ctx.get("transcript") or "").strip()
        if not transcript:
            return {"summary": None, "action_items": [], "sentiment": "unknown",
                    "error": "Empty transcript"}
        sentences = [s.strip() for s in transcript.replace("\n", " ").split(".") if s.strip()]
        action_markers = ("will ", "follow up", "send ", "schedule", "share", "call back")
        actions = [s for s in sentences if any(m in s.lower() for m in action_markers)][:5]
        positive = sum(w in transcript.lower() for w in
                       ("interested", "great", "good", "yes", "sure", "perfect"))
        negative = sum(w in transcript.lower() for w in
                       ("not interested", "expensive", "no ", "later", "busy", "cancel"))
        sentiment = "positive" if positive > negative else "negative" if negative > positive else "neutral"
        return {
            "summary": ". ".join(sentences[:3]) + ("." if sentences else ""),
            "action_items": actions,
            "sentiment": sentiment,
            "duration_estimate_words": len(transcript.split()),
        }

    def _customer_insights(self, ctx: dict) -> dict:
        acts = ctx.get("activities", [])
        by_type: dict[str, int] = {}
        for a in acts:
            by_type[a["type"]] = by_type.get(a["type"], 0) + 1
        bookings = ctx.get("bookings", [])
        return {
            "engagement_by_type": by_type,
            "total_touchpoints": len(acts),
            "bookings": {"total": len(bookings),
                         "active": sum(1 for b in bookings if b["status"] == "active")},
            "health": "engaged" if len(acts) >= 5 else "developing" if acts else "dormant",
        }

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _budget_text(lo, hi) -> str | None:
        def fmt(v):
            v = float(v)
            return f"₹{v / 1e7:.2f} Cr" if v >= 1e7 else f"₹{v / 1e5:.0f} L"

        if lo and hi:
            return f"{fmt(lo)}–{fmt(hi)}"
        if hi:
            return f"up to {fmt(hi)}"
        if lo:
            return f"from {fmt(lo)}"
        return None


class LLMAIProvider(MockAIProvider):
    """Real generation, deterministic floor.

    Every request computes the rule-based payload first, then asks the model to
    rewrite only the narrative fields listed in `prompts.AGENT_PROMPTS`. Three
    consequences worth stating plainly:

    * Scores, counts, grades and rankings are never model-generated. The model
      explains them; it cannot move them.
    * The response shape is fixed by the deterministic payload, so a truncated or
      malformed completion degrades to mock output instead of a broken widget.
    * Any LLM failure is recorded on the payload as `ai_degraded` rather than
      raised, because a salesperson opening a lead should not see a 500 because a
      third-party gateway is rate-limiting.
    """

    name = "llm"

    def __init__(self, client: LLMClient):
        self.client = client

    def generate(self, agent: str, context: dict[str, Any]) -> dict[str, Any]:
        payload = super().generate(agent, context)
        if agent in ("property_recommendation", "property_recommendations"):
            # Ranking is deterministic; only the per-unit blurb is generated.
            payload = dict(payload)
            self._annotate(payload, context)
            payload["provider_model"] = self.client.model
            return payload

        spec = prompts.AGENT_PROMPTS.get(agent)
        if spec is None:
            return payload  # no prompt for this agent — deterministic output is the answer
        system, allowed = spec

        try:
            generated = self.client.chat_json(
                system, self._user_message(agent, context, payload), max_tokens=900
            )
        except LLMError as exc:
            logger.warning("LLM enrichment failed for agent=%s: %s", agent, exc)
            return {**payload, "ai_degraded": f"Model unavailable: {exc}"}

        merged = self._merge(agent, payload, generated, allowed)
        merged["provider_model"] = self.client.model
        return merged

    # ---------------------------------------------------------------- internals

    @staticmethod
    def _user_message(agent: str, context: dict[str, Any], payload: dict[str, Any]) -> str:
        """Hand the model the CRM context plus what the rules already concluded.

        Showing the deterministic payload matters: without it the model re-derives
        (and contradicts) scores that are already final.
        """
        import json

        if agent == "buyer_assistant":
            # Extraction must see the buyer's own words, not our parse of them.
            raw = context.get("message") or context.get("requirements") or ""
            return f"Buyer said:\n{raw if isinstance(raw, str) else json.dumps(raw, default=str)}"

        trimmed = {
            k: v for k, v in context.items()
            if not k.startswith("_") and k not in ("scoring_config", "weights")
        }
        return (
            "CRM context:\n"
            + json.dumps(trimmed, default=str)[:6000]
            + "\n\nAlready computed (final — explain, do not change):\n"
            + json.dumps(payload, default=str)[:3000]
        )

    def _merge(
        self, agent: str, payload: dict[str, Any], generated: dict[str, Any],
        allowed: tuple[str, ...],
    ) -> dict[str, Any]:
        """Copy allow-listed keys across, coercing to the deterministic type."""
        merged = dict(payload)
        for key in allowed:
            if key not in generated:
                continue
            value = generated[key]
            if value in (None, "", [], {}):
                continue
            baseline = payload.get(key)
            if isinstance(baseline, str) and not isinstance(value, str):
                continue
            if isinstance(baseline, list) and not isinstance(value, list):
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
            merged[key] = value

        if agent == "buyer_assistant":
            self._reconcile_buyer_slots(merged)
        return merged

    @staticmethod
    def _reconcile_buyer_slots(merged: dict[str, Any]) -> None:
        """Keep the derived slot fields consistent with the extracted values.

        The model fills `budget_max`/`location`/`property_type`/`timeline`; the
        `captured_requirements`, `missing_fields` and `ready_for_matching` fields
        the UI drives off are recomputed from those rather than trusted from the
        completion.
        """
        slots = ("budget", "location", "property_type", "timeline")
        budget_max = merged.get("budget_max")
        if isinstance(budget_max, (int, float)) and budget_max > 0:
            merged["budget"] = f"up to ₹{int(budget_max):,}"
        captured = {slot: merged[slot] for slot in slots if merged.get(slot)}
        merged["captured_requirements"] = captured
        merged["missing_fields"] = [slot for slot in slots if slot not in captured]
        merged["ready_for_matching"] = not merged["missing_fields"]
        confidence = merged.get("confidence")
        if not isinstance(confidence, (int, float)):
            merged["confidence"] = round(len(captured) / len(slots), 2)

    def _annotate(self, payload: dict[str, Any], context: dict[str, Any]) -> None:
        """Add a per-unit blurb to the top recommendations.

        Guarded exactly as STAIL's recommendation agent guards it: a blurb that
        names nothing real about the unit is thrown away for a template, because
        an invented amenity in a shortlist is worse than a boring sentence.
        """
        recommendations = payload.get("recommendations") or []
        profile = context.get("lead") or context.get("customer") or {}
        buyer = ", ".join(
            str(v) for v in [
                profile.get("property_type"),
                profile.get("location_preference"),
                f"budget up to ₹{int(profile['budget_max']):,}"
                if profile.get("budget_max") else None,
            ] if v
        ) or "unstated requirements"

        for unit in recommendations[:5]:
            facts = (
                f"Project: {unit.get('project')}, unit {unit.get('unit_number')}, "
                f"{unit.get('unit_type')}, ₹{unit.get('price') or 0:,.0f}, "
                f"{unit.get('location') or 'location unknown'}, "
                f"amenities: {', '.join(unit.get('amenities') or []) or 'none listed'}"
            )
            try:
                result = self.client.chat_json(
                    prompts.PROPERTY_ANNOTATION,
                    f"Unit facts:\n{facts}\n\nBuyer wants: {buyer}",
                    max_tokens=200,
                )
                annotation = str(result.get("annotation") or "").strip()
            except LLMError as exc:
                logger.info("annotation failed for unit=%s: %s", unit.get("unit_id"), exc)
                annotation = ""
            if not annotation or not mentions_any(
                annotation,
                [unit.get("project"), unit.get("city"), unit.get("location"),
                 unit.get("unit_type")],
            ):
                annotation = unit.get("rationale") or "Matches your stated requirements."
            unit["annotation"] = annotation


# Our agent names → STAIL Realty OS agent ids, for the `external` provider.
# Agents with no STAIL counterpart stay local (deterministic) rather than being
# proxied to an id that service does not implement.
STAIL_AGENT_IDS: dict[str, str] = {
    "buyer_assistant": "AGT-03",
    "lead_qualification": "AGT-02",
    "property_recommendation": "AGT-05",
    "property_recommendations": "AGT-05",
    "follow_up": "AGT-06",
}


class ExternalAIProvider(MockAIProvider):
    """Proxies to a running STAIL Realty OS backend.

    Speaks STAIL's actual contract — `POST {base}/api/v1/agents/chat` with an
    `AgentChatRequest` body, replying with `AgentChatResponse` (see
    `agents/shared/shared/schemas.py` in that repo). Their reply is narrative plus
    a free-form `metadata` bag, so it is folded into our deterministic payload the
    same way the LLM provider folds in a completion: the schema stays ours.
    """

    name = "external"

    def __init__(self, base_url: str, *, token: str | None = None, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def generate(self, agent: str, context: dict[str, Any]) -> dict[str, Any]:
        payload = super().generate(agent, context)
        agent_id = STAIL_AGENT_IDS.get(agent)
        if agent_id is None:
            return payload

        import httpx

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = {
            "agent_id": agent_id,
            "message": self._message_for(agent, context),
            "context": {k: v for k, v in context.items() if not k.startswith("_")},
            "conversation_history": context.get("conversation_history") or [],
        }
        try:
            response = httpx.post(
                f"{self.base_url}/api/v1/agents/chat",
                json=body, headers=headers, timeout=self.timeout,
            )
            response.raise_for_status()
            reply = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("external agent %s failed: %s", agent_id, exc)
            return {**payload, "ai_degraded": f"Agent service unavailable: {exc}"}

        metadata = reply.get("metadata") or {}
        merged = {
            **payload,
            "agent_id": agent_id,
            "agent_response": reply.get("response"),
            "confidence": reply.get("confidence_score"),
            "escalated": bool(reply.get("escalated")),
            "escalation_reason": reply.get("escalation_reason"),
            "latency_ms": reply.get("latency_ms"),
        }
        # Their AGT-03 returns extracted preferences; map the ones we model.
        preferences = metadata.get("preferences") or {}
        if agent == "buyer_assistant" and preferences:
            for source, target in (
                ("budget_min", "budget_min"), ("budget_max", "budget_max"),
                ("investment_goal", "purpose"),
            ):
                if preferences.get(source):
                    merged[target] = preferences[source]
            months = preferences.get("timeline_months")
            if months:
                # They model this as an int; our slot is a human-readable string.
                merged["timeline"] = f"{months} month{'s' if months != 1 else ''}"
            if preferences.get("cities"):
                merged["location"] = ", ".join(preferences["cities"])
            if preferences.get("bhk_type"):
                merged["property_type"] = "/".join(preferences["bhk_type"])
            LLMAIProvider._reconcile_buyer_slots(merged)
        return merged

    @staticmethod
    def _message_for(agent: str, context: dict[str, Any]) -> str:
        if context.get("message"):
            return str(context["message"])
        profile = context.get("lead") or context.get("customer") or {}
        return (
            f"Agent task: {agent}. Subject: {profile.get('full_name') or 'unknown'}, "
            f"stage {profile.get('stage') or 'n/a'}."
        )


def get_provider() -> AIProvider:
    """Build the configured provider, degrading to `mock` rather than failing.

    A missing key or base URL is a misconfiguration, not a reason for every lead
    page in the product to start returning 500s — so it logs loudly and serves
    deterministic output.
    """
    settings = get_settings()
    choice = (settings.ai_provider or "mock").lower()

    if choice == "external":
        if settings.ai_provider_base_url:
            return ExternalAIProvider(
                settings.ai_provider_base_url, token=settings.ai_provider_token
            )
        logger.warning("AI_PROVIDER=external but AI_PROVIDER_BASE_URL is unset — using mock")
        return MockAIProvider()

    if choice in ("llm", "groq", "openai"):
        try:
            return LLMAIProvider(LLMClient.from_settings())
        except LLMError as exc:
            logger.warning("AI_PROVIDER=%s but LLM is not configured (%s) — using mock",
                           choice, exc)
            return MockAIProvider()

    return MockAIProvider()
