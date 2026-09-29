from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require
from app.core.errors import PermissionDeniedError
from app.core.permissions import ADMIN_ROLES, Role
from app.modules.properties import service
from app.modules.properties.models import CustomerProperty
from app.modules.properties.schemas import (
    CompareRequest,
    CustomerPropertyOut,
    LinkRequest,
    ProjectCreate,
    ProjectOut,
    UnitOut,
)

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("")
def search_units(
    q: str | None = None,
    unit_type: str | None = None,
    city: str | None = None,
    project_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    ctx=Depends(require("properties", "read")),
    db: Session = Depends(get_db),
):
    units = service.provider.search_units(
        db,
        ctx.user.tenant_id,
        {
            "q": q, "unit_type": unit_type, "city": city, "project_id": project_id,
            "status": status_filter, "min_price": min_price, "max_price": max_price,
        },
    )
    return {"data": [UnitOut.model_validate(u).model_dump() for u in units],
            "meta": {"total": len(units)}}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate, ctx=Depends(require("properties", "create")),
    db: Session = Depends(get_db),
):
    if Role(ctx.user.role) not in ADMIN_ROLES:
        raise PermissionDeniedError("Only admins can create inventory")
    project = service.create_project(db, ctx, body.model_dump())
    return {"data": ProjectOut.model_validate(project).model_dump()}


@router.post("/compare")
def compare(
    body: CompareRequest, ctx=Depends(require("properties", "read")),
    db: Session = Depends(get_db),
):
    units = service.compare_units(db, ctx, body.unit_ids)
    return {"data": [UnitOut.model_validate(u).model_dump() for u in units]}


@router.get("/customer/{customer_id}")
def customer_properties(
    customer_id: str, ctx=Depends(require("customers", "read")),
    db: Session = Depends(get_db),
):
    from app.modules.customers.service import get_customer_scoped

    customer = get_customer_scoped(db, ctx, customer_id)
    links = db.scalars(
        select(CustomerProperty).where(CustomerProperty.customer_id == customer.id)
    ).all()
    return {"data": [CustomerPropertyOut.model_validate(l).model_dump() for l in links]}


@router.get("/{unit_id}")
def get_unit(
    unit_id: str, ctx=Depends(require("properties", "read")), db: Session = Depends(get_db)
):
    unit = service.get_unit_or_404(db, ctx.user.tenant_id, unit_id)
    return {"data": UnitOut.model_validate(unit).model_dump()}


def _link_endpoint(relation: str):
    def endpoint(
        unit_id: str,
        body: LinkRequest,
        ctx=Depends(require("properties", "update")),
        db: Session = Depends(get_db),
    ):
        link = service.link_customer_property(
            db, ctx, unit_id=unit_id, customer_id=body.customer_id,
            relation=relation, note=body.note,
        )
        return {"data": CustomerPropertyOut.model_validate(link).model_dump()}

    return endpoint


router.post("/{unit_id}/shortlist", status_code=201)(_link_endpoint("shortlisted"))
router.post("/{unit_id}/favourite", status_code=201)(_link_endpoint("favourite"))
router.post("/{unit_id}/attach", status_code=201)(_link_endpoint("attached"))


@router.delete("/links/{link_id}")
def unlink(
    link_id: str, ctx=Depends(require("properties", "update")), db: Session = Depends(get_db)
):
    service.unlink_customer_property(db, ctx, link_id)
    return {"data": {"message": "Removed"}}
