"""Customer business logic: scoped CRUD, lead conversion, 360 aggregation."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import events
from app.core.audit import record_audit
from app.core.deps import AccessContext, team_user_ids
from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import Scope
from app.db.base import utcnow
from app.modules.customers.models import Customer
from app.modules.leads.models import Lead
from app.modules.leads.service import normalize_phone
from app.modules.timeline.models import Activity, log_activity


def scoped_query(db: Session, ctx: AccessContext):
    q = select(Customer).where(
        Customer.tenant_id == ctx.user.tenant_id, Customer.deleted_at.is_(None)
    )
    if ctx.scope == Scope.TEAM:
        ids = team_user_ids(db, ctx.user)
        q = q.where(or_(Customer.assigned_to.in_(ids), Customer.created_by.in_(ids)))
    elif ctx.scope == Scope.OWN:
        q = q.where(
            or_(Customer.assigned_to == ctx.user.id, Customer.created_by == ctx.user.id)
        )
    return q


def get_customer_scoped(db: Session, ctx: AccessContext, customer_id: str) -> Customer:
    customer = db.scalars(scoped_query(db, ctx).where(Customer.id == customer_id)).first()
    if customer is None:
        raise NotFoundError("Customer not found")
    return customer


def create_customer(db: Session, ctx: AccessContext, data: dict) -> Customer:
    customer = Customer(
        tenant_id=ctx.user.tenant_id,
        phone_normalized=normalize_phone(data["phone"]),
        created_by=ctx.user.id,
        **{k: v for k, v in data.items() if k != "assigned_to"},
        assigned_to=data.get("assigned_to") or ctx.user.id,
    )
    db.add(customer)
    db.flush()
    log_activity(
        db, tenant_id=customer.tenant_id, entity_type="customer", entity_id=customer.id,
        type="created", title="Customer profile created", actor=ctx.user,
    )
    record_audit(
        db, tenant_id=customer.tenant_id, action="customer.create", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="customer", entity_id=customer.id,
    )
    return customer


def update_customer(db: Session, ctx: AccessContext, customer_id: str, changes: dict) -> Customer:
    customer = get_customer_scoped(db, ctx, customer_id)
    if "phone" in changes and changes["phone"]:
        customer.phone_normalized = normalize_phone(changes["phone"])
    for field, value in changes.items():
        setattr(customer, field, value)
    log_activity(
        db, tenant_id=customer.tenant_id, entity_type="customer", entity_id=customer.id,
        type="updated", title="Profile updated", actor=ctx.user,
        detail={"fields": sorted(changes.keys())},
    )
    record_audit(
        db, tenant_id=customer.tenant_id, action="customer.update", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="customer", entity_id=customer.id,
    )
    return customer


def delete_customer(db: Session, ctx: AccessContext, customer_id: str) -> None:
    customer = get_customer_scoped(db, ctx, customer_id)
    customer.deleted_at = utcnow().replace(tzinfo=None)
    record_audit(
        db, tenant_id=customer.tenant_id, action="customer.delete", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="customer", entity_id=customer.id,
    )


def convert_lead(db: Session, ctx: AccessContext, lead: Lead, extra: dict) -> Customer:
    if lead.customer_id:
        raise ConflictError("Lead is already converted", code="already_converted")
    customer = Customer(
        tenant_id=lead.tenant_id,
        full_name=lead.full_name,
        email=lead.email,
        phone=lead.phone,
        phone_normalized=lead.phone_normalized,
        budget_min=lead.budget_min,
        budget_max=lead.budget_max,
        preferences={
            "location": lead.location_preference,
            "property_type": lead.property_type,
            "requirements": lead.requirements,
            **(extra.get("preferences") or {}),
        },
        address=extra.get("address"),
        city=extra.get("city"),
        occupation=extra.get("occupation"),
        family_info=extra.get("family_info"),
        assigned_to=lead.assigned_to or ctx.user.id,
        created_by=ctx.user.id,
        lead_id=lead.id,
    )
    db.add(customer)
    db.flush()
    lead.customer_id = customer.id
    log_activity(
        db, tenant_id=lead.tenant_id, entity_type="lead", entity_id=lead.id,
        type="converted", title=f"Converted to customer {customer.full_name}",
        actor=ctx.user, detail={"customer_id": customer.id},
    )
    log_activity(
        db, tenant_id=lead.tenant_id, entity_type="customer", entity_id=customer.id,
        type="created", title="Created by converting lead", actor=ctx.user,
        detail={"lead_id": lead.id},
    )
    record_audit(
        db, tenant_id=lead.tenant_id, action="lead.convert", actor_id=ctx.user.id,
        actor_email=ctx.user.email, entity_type="customer", entity_id=customer.id,
    )
    events.publish(
        "lead.converted",
        {"lead_id": lead.id, "customer_id": customer.id, "tenant_id": lead.tenant_id,
         "assigned_to": customer.assigned_to}, db=db,
    )
    return customer


def customer_360(db: Session, ctx: AccessContext, customer_id: str) -> dict:
    """Aggregate profile + properties + bookings + documents + timeline in one call."""
    from app.modules.bookings.models import Booking
    from app.modules.documents.models import Document
    from app.modules.properties.models import CustomerProperty

    customer = get_customer_scoped(db, ctx, customer_id)
    properties = db.scalars(
        select(CustomerProperty).where(CustomerProperty.customer_id == customer.id)
    ).all()
    bookings = db.scalars(
        select(Booking).where(Booking.customer_id == customer.id)
    ).all()
    booking_ids = [b.id for b in bookings]
    doc_filter = (Document.entity_type == "customer") & (Document.entity_id == customer.id)
    if booking_ids:
        doc_filter = doc_filter | (
            (Document.entity_type == "booking") & (Document.entity_id.in_(booking_ids))
        )
    documents = db.scalars(
        select(Document)
        .where(Document.tenant_id == ctx.user.tenant_id, doc_filter)
        .order_by(Document.updated_at.desc())
    ).all()
    activities = db.scalars(
        select(Activity)
        .where(Activity.entity_type == "customer", Activity.entity_id == customer.id)
        .order_by(Activity.created_at.desc())
        .limit(100)
    ).all()
    return {
        "customer": customer,
        "properties": properties,
        "bookings": bookings,
        "documents": documents,
        "activities": activities,
    }
