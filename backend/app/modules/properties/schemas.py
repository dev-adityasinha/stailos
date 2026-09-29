from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class UnitCreate(BaseModel):
    unit_number: str = Field(max_length=50)
    floor: int | None = None
    unit_type: str = Field(max_length=50)
    carpet_area_sqft: Decimal | None = Field(default=None, ge=0)
    price: Decimal = Field(ge=0)
    facing: str | None = Field(default=None, max_length=30)
    attributes: dict | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    builder_name: str = Field(max_length=200)
    location: str = Field(max_length=300)
    city: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    amenities: list[str] | None = None
    status: str = "under_construction"
    rera_id: str | None = Field(default=None, max_length=100)
    possession_date: str | None = None
    units: list[UnitCreate] = []


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    builder_name: str
    location: str
    city: str
    description: str | None
    amenities: list | None
    status: str
    rera_id: str | None
    possession_date: str | None


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    unit_number: str
    floor: int | None
    unit_type: str
    carpet_area_sqft: Decimal | None
    price: Decimal
    status: str
    facing: str | None
    attributes: dict | None
    project: ProjectOut


class LinkRequest(BaseModel):
    customer_id: str
    note: str | None = Field(default=None, max_length=500)


class CompareRequest(BaseModel):
    unit_ids: list[str] = Field(min_length=2, max_length=5)


class CustomerPropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    customer_id: str
    unit_id: str
    relation: str
    note: str | None
    created_at: datetime
    unit: UnitOut
