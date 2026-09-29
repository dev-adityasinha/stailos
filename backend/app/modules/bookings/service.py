"""Booking workflow logic with strict stage sequencing and payment integrity."""
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import events
from app.core.audit import record_audit
from app.core.deps import AccessContext, team_user_ids
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.permissions import Scope
from app.modules.bookings.models import (
    BOOKING_STAGE_ORDER,
    Booking,
    BookingStage,
    BookingStageEvent,
    BookingStatus,
    Payment,
)
from app.modules.customers.service import get_customer_scoped
from app.modules.leads.models import Lead, LeadStage
from app.modules.leads.service import get_lead_scoped, record_stage_transition
from app.modules.properties.models import UnitStatus
from app.modules.properties.service import get_unit_or_404
from app.modules.timeline.models import log_activity


def scoped_query(db: Session, ctx: AccessContext):
    q = select(Booking).where(Booking.tenant_id == ctx.user.tenant_id)
    if ctx.scope == Scope.TEAM:
        ids = team_user_ids(db, ctx.user)
        q = q.where(or_(Booking.assigned_to.in_(ids), Booking.created_by.in_(ids)))
    elif ctx.scope == Scope.OWN:
        q = q.where(
            or_(Booking.assigned_to == ctx.user.id, Booking.created_by == ctx.user.id)
        )
    return q


def get_booking_scoped(db: Session, ctx: AccessContext, booking_id: str) -> Booking:
    booking = db.scalars(scoped_query(db, ctx).where(Booking.id == booking_id)).first()
    if booking is None:
        raise NotFoundError("Booking not found")
    return booking


def _log_stage_event(
    db: Session, booking: Booking, *, from_stage: str | None, to_stage: str,
    actor, note: str | None = None,
) -> None:
    db.add(
        BookingStageEvent(
            booking_id=booking.id, from_stage=from_stage, to_stage=to_stage,
            note=note, actor_id=getattr(actor, "id", None),
            actor_name=getattr(actor, "full_name", None),
        )
    )


def create_booking(db: Session, ctx: AccessContext, data: dict) -> Booking:
    customer = get_customer_scoped(db, ctx, data["customer_id"])
    unit = get_unit_or_404(db, ctx.user.tenant_id, data["unit_id"])
    # A cross-tenant lead_id must be rejected outright (same posture as
    # customer_id/unit_id above), not silently dropped — get_lead_scoped
    # already 404s on tenant mismatch or out-of-scope leads.
    if data.get("lead_id"):
        get_lead_scoped(db, ctx, data["lead_id"])
    if unit.status in (UnitStatus.BOOKED.value, UnitStatus.SOLD.value):
        raise ConflictError(
            f"Unit {unit.unit_number} is already {unit.status}", code="unit_unavailable"
        )
    active_for_unit = db.scalars(
        select(Booking).where(
            Booking.unit_id == unit.id, Booking.status == BookingStatus.ACTIVE.value
        )
    ).first()
    if active_for_unit:
        raise ConflictError("Unit already has an active booking", code="unit_unavailable")

    booking = Booking(
        tenant_id=ctx.user.tenant_id,
        customer_id=customer.id,
        lead_id=data.get("lead_id"),
        unit_id=unit.id,
        token_amount=data.get("token_amount"),
        total_value=data["total_value"],
        discount=data.get("discount"),
        assigned_to=ctx.user.id,
        created_by=ctx.user.id,
    )
    db.add(booking)
    db.flush()
    _log_stage_event(
        db, booking, from_stage=None, to_stage=booking.stage, actor=ctx.user,
        note="Booking workflow started",
    )
    log_activity(
        db, tenant_id=booking.tenant_id, entity_type="customer", entity_id=customer.id,
        type="booking", title=f"Booking started for {unit.project.name} #{unit.unit_number}",
        actor=ctx.user, detail={"booking_id": booking.id},
    )
    if booking.lead_id:
        lead = db.get(Lead, booking.lead_id)
        if lead:
            record_stage_transition(
                db, lead, LeadStage.SITE_VISIT_SCHEDULED,
                actor_id=ctx.user.id, actor_name=ctx.user.full_name,
            )
    record_audit(
        db, tenant_id=booking.tenant_id, action="booking.create", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="booking", entity_id=booking.id,
    )
    events.publish(
        "booking.created",
        {"booking_id": booking.id, "tenant_id": booking.tenant_id,
         "customer_name": customer.full_name, "assigned_to": booking.assigned_to}, db=db,
    )
    return booking


def advance_stage(
    db: Session, ctx: AccessContext, booking_id: str, note: str | None
) -> Booking:
    booking = get_booking_scoped(db, ctx, booking_id)
    if booking.status != BookingStatus.ACTIVE.value:
        raise AppError(f"Cannot advance a {booking.status} booking", code="booking_not_active")
    idx = BOOKING_STAGE_ORDER.index(booking.stage)
    if idx == len(BOOKING_STAGE_ORDER) - 1:
        raise AppError("Booking is already completed", code="already_completed")
    next_stage = BOOKING_STAGE_ORDER[idx + 1]

    # Guard: cannot move into POSSESSION until the unit is fully paid.
    if next_stage == BookingStage.POSSESSION.value:
        paid = db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.booking_id == booking.id
            )
        )
        payable = Decimal(str(booking.total_value)) - Decimal(str(booking.discount or 0))
        if Decimal(str(paid)) < payable:
            raise AppError(
                f"Cannot move to possession: paid {paid} of {payable}",
                code="payment_incomplete",
            )

    from_stage = booking.stage
    booking.stage = next_stage
    if next_stage == BookingStage.COMPLETED.value:
        booking.status = BookingStatus.COMPLETED.value
        booking.unit.status = UnitStatus.SOLD.value
        if booking.lead_id:
            lead = db.get(Lead, booking.lead_id)
            if lead:
                record_stage_transition(
                    db, lead, LeadStage.COMPLETED,
                    actor_id=ctx.user.id, actor_name=ctx.user.full_name,
                )
    elif next_stage == BookingStage.BOOKING.value:
        booking.unit.status = UnitStatus.BOOKED.value
        if booking.lead_id:
            lead = db.get(Lead, booking.lead_id)
            if lead:
                record_stage_transition(
                    db, lead, LeadStage.BOOKED,
                    actor_id=ctx.user.id, actor_name=ctx.user.full_name,
                )

    _log_stage_event(db, booking, from_stage=from_stage, to_stage=next_stage,
                     actor=ctx.user, note=note)
    log_activity(
        db, tenant_id=booking.tenant_id, entity_type="customer",
        entity_id=booking.customer_id, type="booking",
        title=f"Booking stage: {from_stage} → {next_stage}", actor=ctx.user,
        detail={"booking_id": booking.id},
    )
    record_audit(
        db, tenant_id=booking.tenant_id, action="booking.stage_advance",
        actor_id=ctx.user.id, actor_email=ctx.user.email,
        entity_type="booking", entity_id=booking.id,
        detail={"from": from_stage, "to": next_stage},
    )
    events.publish(
        "booking.stage_changed",
        {"booking_id": booking.id, "tenant_id": booking.tenant_id, "from": from_stage,
         "to": next_stage, "assigned_to": booking.assigned_to,
         "customer_name": booking.customer.full_name}, db=db,
    )
    return booking


def record_payment(db: Session, ctx: AccessContext, booking_id: str, data: dict) -> Payment:
    booking = get_booking_scoped(db, ctx, booking_id)
    if booking.status != BookingStatus.ACTIVE.value:
        raise AppError(f"Cannot record payment on a {booking.status} booking",
                       code="booking_not_active")
    amount = Decimal(str(data["amount"]))
    if amount <= 0:
        raise AppError("Payment amount must be positive", code="invalid_amount")
    paid = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.booking_id == booking.id
        )
    )
    payable = Decimal(str(booking.total_value)) - Decimal(str(booking.discount or 0))
    if Decimal(str(paid)) + amount > payable:
        raise AppError(
            f"Payment would exceed booking value ({paid} + {amount} > {payable})",
            code="overpayment",
        )
    seq = (db.scalar(select(func.count(Payment.id))) or 0) + 1
    payment = Payment(
        booking_id=booking.id,
        amount=amount,
        method=data.get("method", "bank_transfer"),
        reference=data.get("reference"),
        milestone=data.get("milestone"),
        receipt_number=f"RCPT-{seq:06d}",
        recorded_by=ctx.user.id,
    )
    db.add(payment)
    db.flush()
    log_activity(
        db, tenant_id=booking.tenant_id, entity_type="customer",
        entity_id=booking.customer_id, type="payment",
        title=f"Payment ₹{amount:,.2f} received ({payment.receipt_number})",
        actor=ctx.user, detail={"booking_id": booking.id, "payment_id": payment.id},
    )
    record_audit(
        db, tenant_id=booking.tenant_id, action="booking.payment", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="payment", entity_id=payment.id,
        detail={"amount": str(amount), "receipt": payment.receipt_number},
    )
    events.publish(
        "booking.payment_recorded",
        {"booking_id": booking.id, "tenant_id": booking.tenant_id,
         "amount": str(amount), "assigned_to": booking.assigned_to}, db=db,
    )
    return payment


def cancel_booking(db: Session, ctx: AccessContext, booking_id: str, reason: str) -> Booking:
    booking = get_booking_scoped(db, ctx, booking_id)
    if booking.status != BookingStatus.ACTIVE.value:
        raise AppError(f"Booking is already {booking.status}", code="booking_not_active")
    if booking.stage in (BookingStage.POSSESSION.value, BookingStage.COMPLETED.value):
        raise AppError(
            "Bookings at possession stage or later require manual legal handling",
            code="cancellation_blocked",
        )
    booking.status = BookingStatus.CANCELLED.value
    booking.cancellation_reason = reason
    booking.unit.status = UnitStatus.AVAILABLE.value
    _log_stage_event(db, booking, from_stage=booking.stage, to_stage="cancelled",
                     actor=ctx.user, note=reason)
    record_audit(
        db, tenant_id=booking.tenant_id, action="booking.cancel", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="booking", entity_id=booking.id,
        detail={"reason": reason},
    )
    return booking
