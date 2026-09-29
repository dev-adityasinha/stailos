from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.events.models import EventStatus, RegistrationStage


class SpeakerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    bio: str | None = Field(default=None, max_length=2000)
    photo_url: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class AgendaItemIn(BaseModel):
    start_time: datetime
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=1000)
    speaker_id: str | None = None


class EventCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=220, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = Field(default=None, max_length=4000)
    venue: str | None = Field(default=None, max_length=300)
    start_at: datetime
    end_at: datetime
    hero_image_url: str | None = Field(default=None, max_length=500)
    cta_text: str = Field(default="Register now", max_length=100)

    @field_validator("end_at")
    @classmethod
    def _end_after_start(cls, v: datetime, info) -> datetime:
        start = info.data.get("start_at")
        if start and v <= start:
            raise ValueError("end_at must be after start_at")
        return v


class EventUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    venue: str | None = Field(default=None, max_length=300)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: EventStatus | None = None
    hero_image_url: str | None = Field(default=None, max_length=500)
    cta_text: str | None = Field(default=None, max_length=100)
    total_ad_spend: Decimal | None = Field(default=None, ge=0)


class SpeakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    title: str | None
    bio: str | None
    photo_url: str | None
    sort_order: int


class AgendaItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    start_time: datetime
    title: str
    description: str | None
    speaker_id: str | None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    slug: str
    description: str | None
    venue: str | None
    start_at: datetime
    end_at: datetime
    status: EventStatus
    hero_image_url: str | None
    cta_text: str
    total_ad_spend: Decimal | None
    speakers: list[SpeakerOut]
    agenda_items: list[AgendaItemOut]
    created_at: datetime


class RegistrationCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)  # required: WhatsApp confirmations need it
    company: str | None = Field(default=None, max_length=200)
    investment_budget: Decimal | None = Field(default=None, ge=0)
    utm_campaign: str | None = Field(default=None, max_length=200)
    ref: str | None = Field(default=None, max_length=20)  # referral code from ?ref=


class RegistrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str
    email: str
    phone: str | None
    company: str | None
    stage: RegistrationStage
    checked_in_at: datetime | None
    referral_code: str
    referred_by_code: str | None
    lead_id: str | None
    # Only meaningful to the registrant themselves (knowledge-of-secret, not
    # an ID) — used to fetch their own QR badge via GET .../qr?token=...;
    # admins also see it here for manual check-in entry if a scan fails.
    checkin_token: str
    created_at: datetime


class RegistrationStageUpdate(BaseModel):
    stage: RegistrationStage


class CheckinRequest(BaseModel):
    token: str = Field(min_length=1, max_length=64)


class EventDashboard(BaseModel):
    total_registrations: int
    rsvp_confirmed: int
    attended: int
    no_show: int
    rsvp_rate: float
    attendance_rate: float
    checkin_rate: float
    total_ad_spend: Decimal | None
    cost_per_lead: Decimal | None
    by_source: dict[str, int]
