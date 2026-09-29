from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.properties.schemas import UnitOut


class BookingCreate(BaseModel):
    customer_id: str
    unit_id: str
    lead_id: str | None = None
    total_value: Decimal = Field(gt=0)
    token_amount: Decimal | None = Field(default=None, ge=0)
    discount: Decimal | None = Field(default=None, ge=0)


class AdvanceStageRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = Field(default="bank_transfer", max_length=30)
    reference: str | None = Field(default=None, max_length=200)
    milestone: str | None = Field(default=None, max_length=100)


class CancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class CustomerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str
    phone: str
    email: str | None


class StageEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    from_stage: str | None
    to_stage: str
    note: str | None
    actor_name: str | None
    created_at: datetime


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    amount: Decimal
    method: str
    reference: str | None
    receipt_number: str
    milestone: str | None
    created_at: datetime


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    customer_id: str
    customer: CustomerBrief
    lead_id: str | None
    unit_id: str
    unit: UnitOut
    stage: str
    status: str
    token_amount: Decimal | None
    total_value: Decimal
    discount: Decimal | None
    cancellation_reason: str | None
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime


class BookingDetailOut(BookingOut):
    stage_events: list[StageEventOut]
    payments: list[PaymentOut]
