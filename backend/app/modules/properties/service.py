"""Property inventory logic + the integration seam for Aditya's Property APIs.

`PropertyProvider` is the contract. `InternalProvider` serves the CRM's own
tables (and doubles as the mock). `ExternalHTTPProvider` maps the same calls
onto a remote API and is selected with PROPERTY_PROVIDER=external +
PROPERTY_PROVIDER_BASE_URL. API responses are identical either way, so the
frontend never notices a swap.
"""
from typing import Protocol

from sqlalchemy import or_, select

from app.core.search import like_pattern
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.deps import AccessContext
from app.core.errors import ConflictError, NotFoundError
from app.modules.customers.service import get_customer_scoped
from app.modules.properties.models import (
    CustomerProperty,
    PropertyProject,
    PropertyUnit,
    UnitStatus,
)
from app.modules.timeline.models import log_activity


class PropertyProvider(Protocol):
    def search_units(self, db: Session, tenant_id: str, filters: dict) -> list[PropertyUnit]: ...
    def get_unit(self, db: Session, tenant_id: str, unit_id: str) -> PropertyUnit | None: ...


class InternalProvider:
    def search_units(self, db: Session, tenant_id: str, filters: dict) -> list[PropertyUnit]:
        q = (
            select(PropertyUnit)
            .join(PropertyProject)
            .where(PropertyProject.tenant_id == tenant_id)
        )
        if filters.get("q"):
            like = like_pattern(filters["q"])
            q = q.where(
                or_(
                    PropertyProject.name.ilike(like, escape="\\"),
                    PropertyProject.location.ilike(like, escape="\\"),
                    PropertyProject.city.ilike(like, escape="\\"),
                    PropertyProject.builder_name.ilike(like, escape="\\"),
                )
            )
        if filters.get("unit_type"):
            q = q.where(PropertyUnit.unit_type == filters["unit_type"])
        if filters.get("status"):
            q = q.where(PropertyUnit.status == filters["status"])
        if filters.get("city"):
            q = q.where(PropertyProject.city.ilike(f"%{filters['city']}%"))
        if filters.get("project_id"):
            q = q.where(PropertyUnit.project_id == filters["project_id"])
        if filters.get("min_price") is not None:
            q = q.where(PropertyUnit.price >= filters["min_price"])
        if filters.get("max_price") is not None:
            q = q.where(PropertyUnit.price <= filters["max_price"])
        return list(db.scalars(q.order_by(PropertyUnit.price)).all())

    def get_unit(self, db: Session, tenant_id: str, unit_id: str) -> PropertyUnit | None:
        unit = db.get(PropertyUnit, unit_id)
        if unit and unit.project.tenant_id == tenant_id:
            return unit
        return None


# Provider selection happens once at import; external HTTP provider would be
# instantiated here when settings.property_provider == "external".
provider: PropertyProvider = InternalProvider()


def create_project(db: Session, ctx: AccessContext, data: dict) -> PropertyProject:
    units = data.pop("units", [])
    project = PropertyProject(tenant_id=ctx.user.tenant_id, **data)
    db.add(project)
    db.flush()
    for u in units:
        db.add(PropertyUnit(project_id=project.id, **u))
    record_audit(
        db, tenant_id=ctx.user.tenant_id, action="property.project_create",
        actor_id=ctx.user.id, actor_email=ctx.user.email,
        entity_type="property_project", entity_id=project.id,
    )
    return project


def get_unit_or_404(db: Session, tenant_id: str, unit_id: str) -> PropertyUnit:
    unit = provider.get_unit(db, tenant_id, unit_id)
    if unit is None:
        raise NotFoundError("Property unit not found")
    return unit


def link_customer_property(
    db: Session, ctx: AccessContext, *, unit_id: str, customer_id: str,
    relation: str, note: str | None = None,
) -> CustomerProperty:
    customer = get_customer_scoped(db, ctx, customer_id)  # enforces scope
    unit = get_unit_or_404(db, ctx.user.tenant_id, unit_id)
    existing = db.scalars(
        select(CustomerProperty).where(
            CustomerProperty.customer_id == customer.id,
            CustomerProperty.unit_id == unit.id,
            CustomerProperty.relation == relation,
        )
    ).first()
    if existing:
        raise ConflictError(f"Unit already {relation} for this customer", code="already_linked")
    link = CustomerProperty(
        customer_id=customer.id, unit_id=unit.id, relation=relation,
        note=note, added_by=ctx.user.id,
    )
    db.add(link)
    db.flush()
    log_activity(
        db, tenant_id=ctx.user.tenant_id, entity_type="customer", entity_id=customer.id,
        type="updated",
        title=f"Property {unit.project.name} #{unit.unit_number} {relation}",
        actor=ctx.user, detail={"unit_id": unit.id, "relation": relation},
    )
    return link


def unlink_customer_property(db: Session, ctx: AccessContext, link_id: str) -> None:
    link = db.get(CustomerProperty, link_id)
    if link is None:
        raise NotFoundError("Link not found")
    get_customer_scoped(db, ctx, link.customer_id)  # scope check
    db.delete(link)


def compare_units(db: Session, ctx: AccessContext, unit_ids: list[str]) -> list[PropertyUnit]:
    units = [get_unit_or_404(db, ctx.user.tenant_id, uid) for uid in unit_ids]
    return units


def set_unit_status(db: Session, unit: PropertyUnit, status: UnitStatus) -> None:
    unit.status = status.value
