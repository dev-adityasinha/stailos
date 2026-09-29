"""Property inventory. The internal tables double as the mock backend for the
provider interface in `providers.py` — swap to Aditya's HTTP API via config
without changing the API surface."""
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class UnitStatus(StrEnum):
    AVAILABLE = "available"
    HELD = "held"
    BOOKED = "booked"
    SOLD = "sold"


class PropertyProject(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "property_projects"

    name: Mapped[str] = mapped_column(String(200), index=True)
    builder_name: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(300))
    city: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    amenities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="under_construction")
    rera_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    possession_date: Mapped[str | None] = mapped_column(String(20), nullable=True)

    units: Mapped[list["PropertyUnit"]] = relationship(
        back_populates="project", lazy="selectin"
    )


class PropertyUnit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "property_units"

    project_id: Mapped[str] = mapped_column(ForeignKey("property_projects.id"), index=True)
    unit_number: Mapped[str] = mapped_column(String(50))
    floor: Mapped[int | None] = mapped_column(nullable=True)
    unit_type: Mapped[str] = mapped_column(String(50), index=True)  # 2BHK, 3BHK, Villa…
    carpet_area_sqft: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(
        String(20), default=UnitStatus.AVAILABLE.value, index=True
    )
    facing: Mapped[str | None] = mapped_column(String(30), nullable=True)
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    project: Mapped[PropertyProject] = relationship(back_populates="units", lazy="joined")


class CustomerProperty(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Shortlist / favourite / attached relations between customers and units."""

    __tablename__ = "customer_properties"

    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("property_units.id"), index=True)
    relation: Mapped[str] = mapped_column(String(20))  # shortlisted | favourite | attached
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    added_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    unit: Mapped[PropertyUnit] = relationship(lazy="joined")
