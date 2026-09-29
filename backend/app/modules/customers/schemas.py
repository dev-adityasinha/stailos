from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.leads.schemas import UserBrief


class CustomerCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=7, max_length=20)
    email: EmailStr | None = None
    alt_phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    occupation: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    family_info: list[dict] | None = None
    preferences: dict | None = None
    investment_history: list[dict] | None = None
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    assigned_to: str | None = None


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    email: EmailStr | None = None
    alt_phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    occupation: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    family_info: list[dict] | None = None
    preferences: dict | None = None
    investment_history: list[dict] | None = None
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    assigned_to: str | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: str | None
    phone: str
    alt_phone: str | None
    address: str | None
    city: str | None
    occupation: str | None
    company: str | None
    family_info: list | None
    preferences: dict | None
    investment_history: list | None
    budget_min: Decimal | None
    budget_max: Decimal | None
    assigned_to: str | None
    assignee: UserBrief | None
    lead_id: str | None
    created_at: datetime
    updated_at: datetime


class ConvertLeadRequest(BaseModel):
    # Optional extra profile data collected at conversion time
    address: str | None = None
    city: str | None = None
    occupation: str | None = None
    family_info: list[dict] | None = None
    preferences: dict | None = None
