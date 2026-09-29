import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require
from app.core.search import like_pattern
from app.modules.bookings.schemas import BookingOut
from app.modules.customers import service
from app.modules.customers.models import Customer
from app.modules.customers.schemas import (
    ConvertLeadRequest,
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
)
from app.modules.leads.schemas import ActivityOut
from app.modules.leads.service import get_lead_scoped
from app.modules.properties.schemas import CustomerPropertyOut

router = APIRouter(prefix="/customers", tags=["customers"])
convert_router = APIRouter(prefix="/leads", tags=["customers"])


@router.get("")
def list_customers(
    q: str | None = None,
    city: str | None = None,
    assigned_to: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx=Depends(require("customers", "read")),
    db: Session = Depends(get_db, scope="function"),
):
    query = service.scoped_query(db, ctx)
    if q:
        like = like_pattern(q)
        query = query.where(
            or_(
                Customer.full_name.ilike(like, escape="\\"),
                Customer.email.ilike(like, escape="\\"),
                Customer.phone.ilike(like, escape="\\"),
            )
        )
    if city:
        query = query.where(Customer.city.ilike(f"%{city}%"))
    if assigned_to:
        query = query.where(Customer.assigned_to == assigned_to)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Customer.updated_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "data": [CustomerOut.model_validate(r).model_dump() for r in rows],
        "meta": {"total": total, "limit": limit, "offset": offset,
                 "pages": math.ceil((total or 0) / limit)},
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_customer(
    body: CustomerCreate, ctx=Depends(require("customers", "create")),
    db: Session = Depends(get_db, scope="function"),
):
    customer = service.create_customer(db, ctx, body.model_dump(exclude_unset=True))
    return {"data": CustomerOut.model_validate(customer).model_dump()}


@router.get("/{customer_id}")
def get_customer(
    customer_id: str, ctx=Depends(require("customers", "read")), db: Session = Depends(get_db, scope="function")
):
    customer = service.get_customer_scoped(db, ctx, customer_id)
    return {"data": CustomerOut.model_validate(customer).model_dump()}


@router.get("/{customer_id}/360")
def customer_360(
    customer_id: str, ctx=Depends(require("customers", "read")), db: Session = Depends(get_db, scope="function")
):
    from app.modules.documents.router import DocumentOut

    agg = service.customer_360(db, ctx, customer_id)
    return {
        "data": {
            "customer": CustomerOut.model_validate(agg["customer"]).model_dump(),
            "properties": [
                CustomerPropertyOut.model_validate(p).model_dump() for p in agg["properties"]
            ],
            "bookings": [BookingOut.model_validate(b).model_dump() for b in agg["bookings"]],
            "documents": [DocumentOut.model_validate(d).model_dump() for d in agg["documents"]],
            "timeline": [ActivityOut.model_validate(a).model_dump() for a in agg["activities"]],
        }
    }


@router.patch("/{customer_id}")
def update_customer(
    customer_id: str,
    body: CustomerUpdate,
    ctx=Depends(require("customers", "update")),
    db: Session = Depends(get_db, scope="function"),
):
    customer = service.update_customer(db, ctx, customer_id, body.model_dump(exclude_unset=True))
    return {"data": CustomerOut.model_validate(customer).model_dump()}


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: str, ctx=Depends(require("customers", "delete")), db: Session = Depends(get_db, scope="function")
):
    service.delete_customer(db, ctx, customer_id)
    return {"data": {"message": "Customer deleted"}}


@convert_router.post("/{lead_id}/convert", status_code=status.HTTP_201_CREATED)
def convert_lead(
    lead_id: str,
    body: ConvertLeadRequest,
    ctx=Depends(require("customers", "create")),
    db: Session = Depends(get_db, scope="function"),
):
    lead = get_lead_scoped(db, ctx, lead_id)
    customer = service.convert_lead(db, ctx, lead, body.model_dump(exclude_unset=True))
    return {"data": CustomerOut.model_validate(customer).model_dump()}
