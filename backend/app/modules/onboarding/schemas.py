from typing import Any

from pydantic import BaseModel, Field


class OnboardingStepUpdate(BaseModel):
    step_id: int | str
    # 200 keys is far more than any single form page needs; the cap exists so a
    # malformed client can't push an unbounded JSON blob into tenants.onboarding_data.
    data: dict[str, Any] = Field(default_factory=dict, max_length=200)


class OnboardingCompleteRequest(BaseModel):
    pass


# The canonical onboarding step registry.
#
# Keys are strings and deliberately non-sequential: "1", "2", "4", "7" and "11"
# predate this expansion (they came from the StailOS wizard and are consumed by
# `service.complete_onboarding`), so they keep their original meaning and any
# workspace part-way through setup keeps its saved answers. New pages take
# suffixed ("1b", "1c") or unused numbers rather than renumbering the old ones.
#
# `source` names the form in the repo root each page is derived from, so the
# wizard and the specs stay traceable to each other.
ONBOARDING_STEPS: list[dict[str, Any]] = [
    {"key": "1", "title": "Company information",
     "source": "AI_Developer_Onboarding_Form.md §1",
     "effect": "Renames the workspace; fills the company profile."},
    {"key": "1b", "title": "Primary contact",
     "source": "AI_Developer_Onboarding_Form.md §2",
     "effect": "Renames the admin user; sets the escalation contact."},
    {"key": "1c", "title": "Company profile & footprint",
     "source": "AI_Developer_Onboarding_Form.md §3–§5, §11",
     "effect": "Sets operating cities, which drives geographic lead scoring."},
    {"key": "2", "title": "Project portfolio",
     "source": "AI_Property_Information_Form.md §2–§8",
     "effect": "Creates real property projects and units on launch."},
    {"key": "4", "title": "Ideal customer profile",
     "source": "AI_Ideal_Customer_Profile.md",
     "effect": "Grounds AI narrative and segment matching."},
    {"key": "5", "title": "AI lead scoring",
     "source": "AI_Lead_Generation_Configuration_Form.md §8–§9",
     "effect": "Sets the weights and hot/warm thresholds the scoring engine uses."},
    {"key": "6", "title": "AI features & integrations",
     "source": "AI_Developer_Onboarding_Form.md §10, §15",
     "effect": "Records which AI surfaces and integrations the workspace wants."},
    {"key": "7", "title": "Import your pipeline",
     "source": "CRM_Lead_Intake_Form.md",
     "effect": "Creates leads and customers from CSV on launch."},
    {"key": "8", "title": "Documents & AI knowledge base",
     "source": "AI_Developer_Onboarding_Form.md §16–§17",
     "effect": "Uploads are stored immediately as tenant documents."},
    {"key": "9", "title": "Sales process & targets",
     "source": "AI_Developer_Onboarding_Form.md §13, §21",
     "effect": "Records SLAs and monthly targets for reporting."},
    {"key": "11", "title": "Invite your team",
     "source": "AI_Developer_Onboarding_Form.md §18",
     "effect": "Sends set-password invites on launch."},
    {"key": "12", "title": "Compliance & consent",
     "source": "AI_Developer_Onboarding_Form.md §22",
     "effect": "Records marketing and AI-usage consent."},
]

STEP_KEYS = {step["key"] for step in ONBOARDING_STEPS}
