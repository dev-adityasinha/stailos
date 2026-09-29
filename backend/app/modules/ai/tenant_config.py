"""Turns the onboarding answers into an enforced AI policy.

Two things the setup wizard collects were previously recorded and then ignored:

* **AI usage consent** (§22 of AI_Developer_Onboarding_Form.md). The wizard
  refuses to launch without it, but nothing checked it afterwards — so a
  workspace that answered "No" still had every agent running over its customer
  data. That is the one answer on the form with a compliance meaning, and it is
  now enforced on every generation path.
* **AI features required** (§10). "Select all that apply" implied the unselected
  ones stay off. They didn't.

Both are deliberately fail-open for workspaces that never answered: a tenant that
skipped onboarding, or predates these fields, keeps working exactly as before.
Only an explicit "No" disables anything.
"""
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError
from app.modules.auth.models import Tenant

# Feature label (as shown in the wizard, see frontend/src/app/onboarding/steps.ts)
# → the agents it switches on. Labels are matched case-insensitively so a
# re-worded checkbox doesn't silently disable an agent.
FEATURE_AGENTS: dict[str, tuple[str, ...]] = {
    "ai lead scoring": ("lead_qualification",),
    "buying intent detection": ("lead_qualification",),
    "ai follow-up": ("follow_up",),
    "ai email assistant": ("email_generator",),
    "ai whatsapp assistant": ("whatsapp_assistant",),
    "ai calling assistant": ("call_summary",),
    "property recommendation": ("property_recommendation", "property_recommendations"),
    "affordability prediction": ("investment_insights",),
}

# Agents that are part of the core CRM experience rather than an opt-in feature.
# They stay on regardless of what was ticked, so a workspace can never end up
# with a lead page that has no AI at all because of one unticked box.
ALWAYS_ON_AGENTS = frozenset({
    "lead_summary", "customer_summary", "suggestions", "next_best_action",
    "sales_tips", "buyer_assistant", "customer_insights",
})

# Every agent some feature can govern.
_GOVERNED_AGENTS = frozenset(a for agents in FEATURE_AGENTS.values() for a in agents)


def _selected_features(onboarding: dict) -> set[str]:
    """All AI feature labels ticked across the wizard's feature groups."""
    step = onboarding.get("6") or {}
    selected: set[str] = set()
    for key, value in step.items():
        if key == "integrations" or not isinstance(value, list):
            continue
        selected.update(str(v).strip().lower() for v in value if str(v).strip())
    return selected


def load_policy(db: Session, tenant_id: str) -> dict[str, Any]:
    """Read the tenant's AI policy. Cheap enough to call per request."""
    tenant = db.get(Tenant, tenant_id)
    onboarding = (tenant.onboarding_data if tenant else None) or {}
    consent_step = onboarding.get("12") or {}

    # Absent means "never asked" — not "refused".
    consent_recorded = "aiUsageConsent" in consent_step
    ai_consent = bool(consent_step.get("aiUsageConsent")) if consent_recorded else True

    selected = _selected_features(onboarding)
    if selected:
        enabled_governed = {
            agent
            for label, agents in FEATURE_AGENTS.items()
            if label in selected
            for agent in agents
        }
    else:
        # Nothing ticked (or the step was skipped) — everything stays available.
        enabled_governed = set(_GOVERNED_AGENTS)

    return {
        "ai_consent": ai_consent,
        "consent_recorded": consent_recorded,
        "selected_features": sorted(selected),
        "enabled_agents": sorted(ALWAYS_ON_AGENTS | enabled_governed),
    }


def is_agent_enabled(policy: dict[str, Any], agent: str) -> bool:
    if agent in ALWAYS_ON_AGENTS or agent not in _GOVERNED_AGENTS:
        return True
    return agent in policy["enabled_agents"]


def enforce(policy: dict[str, Any], agent: str) -> None:
    """Raise unless this tenant may run this agent right now."""
    if not policy["ai_consent"]:
        raise PermissionDeniedError(
            "AI features are switched off for this workspace: AI usage consent was "
            "declined during setup. An admin can change this under "
            "Settings → Company profile.",
            code="ai_consent_declined",
        )
    if not is_agent_enabled(policy, agent):
        raise PermissionDeniedError(
            f"The AI feature behind '{agent.replace('_', ' ')}' is not enabled for "
            "this workspace. An admin can enable it under "
            "Settings → Company profile.",
            code="ai_feature_disabled",
        )
