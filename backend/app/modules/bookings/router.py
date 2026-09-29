import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require
from app.modules.bookings import service
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import (
    AdvanceStageRequest,
    BookingCreate,
    BookingDetailOut,
    BookingOut,
    CancelRequest,
    PaymentCreate,
    PaymentOut,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("")
def list_bookings(
    stage: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    customer_id: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx=Depends(require("bookings", "read")),
    db: Session = Depends(get_db),
):
    query = service.scoped_query(db, ctx)
    if stage:
        query = query.where(Booking.stage == stage)
    if status_filter:
        query = query.where(Booking.status == status_filter)
    if customer_id:
        query = query.where(Booking.customer_id == customer_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Booking.updated_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "data": [BookingOut.model_validate(r).model_dump() for r in rows],
        "meta": {"total": total, "limit": limit, "offset": offset,
                 "pages": math.ceil((total or 0) / limit)},
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_booking(
    body: BookingCreate, ctx=Depends(require("bookings", "create")),
    db: Session = Depends(get_db),
):
    booking = service.create_booking(db, ctx, body.model_dump())
    return {"data": BookingDetailOut.model_validate(booking).model_dump()}


@router.get("/{booking_id}")
def get_booking(
    booking_id: str, ctx=Depends(require("bookings", "read")), db: Session = Depends(get_db)
):
    booking = service.get_booking_scoped(db, ctx, booking_id)
    return {"data": BookingDetailOut.model_validate(booking).model_dump()}


@router.post("/{booking_id}/advance-stage")
def advance_stage(
    booking_id: str,
    body: AdvanceStageRequest,
    ctx=Depends(require("bookings", "update")),
    db: Session = Depends(get_db),
):
    booking = service.advance_stage(db, ctx, booking_id, body.note)
    return {"data": BookingDetailOut.model_validate(booking).model_dump()}


@router.post("/{booking_id}/payments", status_code=status.HTTP_201_CREATED)
def record_payment(
    booking_id: str,
    body: PaymentCreate,
    ctx=Depends(require("bookings", "update")),
    db: Session = Depends(get_db),
):
    payment = service.record_payment(db, ctx, booking_id, body.model_dump())
    return {"data": PaymentOut.model_validate(payment).model_dump()}


@router.get("/{booking_id}/payments")
def list_payments(
    booking_id: str, ctx=Depends(require("payments", "read")), db: Session = Depends(get_db)
):
    booking = service.get_booking_scoped(db, ctx, booking_id)
    return {"data": [PaymentOut.model_validate(p).model_dump() for p in booking.payments]}


@router.post("/{booking_id}/cancel")
def cancel_booking(
    booking_id: str,
    body: CancelRequest,
    ctx=Depends(require("bookings", "update")),
    db: Session = Depends(get_db),
):
    booking = service.cancel_booking(db, ctx, booking_id, body.reason)
    return {"data": BookingDetailOut.model_validate(booking).model_dump()}
