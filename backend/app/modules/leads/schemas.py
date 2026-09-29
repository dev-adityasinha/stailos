from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.leads.models import LEAD_SOURCES, LeadStage


class LeadCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=7, max_length=20)
    email: EmailStr | None = None
    source: str = "other"
    campaign: str | None = Field(default=None, max_length=200)
    stage: LeadStage = LeadStage.NEW
    assigned_to: str | None = None
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    location_preference: str | None = Field(default=None, max_length=300)
    property_type: str | None = Field(default=None, max_length=100)
    requirements: str | None = Field(default=None, max_length=2000)
    custom_fields: dict | None = None
    force: bool = False  # create even when duplicates were reported

    @field_validator("source")
    @classmethod
    def _known_source(cls, v: str) -> str:
        return v if v in LEAD_SOURCES else "other"


class LeadUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    email: EmailStr | None = None
    source: str | None = None
    campaign: str | None = Field(default=None, max_length=200)
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    location_preference: str | None = Field(default=None, max_length=300)
    property_type: str | None = Field(default=None, max_length=100)
    requirements: str | None = Field(default=None, max_length=2000)
    custom_fields: dict | None = None
    lost_reason: str | None = Field(default=None, max_length=500)


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    color: str | None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    author_id: str | None
    author_name: str | None
    body: str
    created_at: datetime


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str
    email: str
    avatar_color: str | None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: str | None
    phone: str
    source: str
    campaign: str | None
    stage: LeadStage
    assigned_to: str | None
    assignee: UserBrief | None
    created_by: str | None
    budget_min: Decimal | None
    budget_max: Decimal | None
    location_preference: str | None
    property_type: str | None
    requirements: str | None
    ai_score: float | None
    score_band: str | None
    custom_fields: dict | None
    customer_id: str | None
    lost_reason: str | None
    tags: list[TagOut]
    created_at: datetime
    updated_at: datetime


class LeadDetailOut(LeadOut):
    notes: list[NoteOut]


class DuplicateMatch(BaseModel):
    lead_id: str
    full_name: str
    phone: str
    email: str | None
    stage: str
    assigned_to: str | None
    match_type: str  # phone | email | name


class DuplicateCheckRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class AssignRequest(BaseModel):
    user_id: str


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class TagRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class StageChangeRequest(BaseModel):
    stage: LeadStage
    lost_reason: str | None = Field(default=None, max_length=500)
    reopen: bool = False  # required to move a lead out of completed/lost


class ScheduleSiteVisitRequest(BaseModel):
    start_at: datetime
    end_at: datetime | None = None
    location: str | None = Field(default=None, max_length=300)
    attendee_ids: list[str] = []


class LeadStageEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    from_stage: str | None
    to_stage: str
    note: str | None
    actor_id: str | None
    actor_name: str | None
    created_at: datetime


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    entity_type: str
    entity_id: str
    actor_id: str | None
    actor_name: str | None
    type: str
    title: str
    detail: dict | None
    created_at: datetime
