"""Analytics dashboards — all figures computed from live backend data
(task list Task 16: charts must be dynamic, backend-driven)."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require, team_user_ids
from app.core.permissions import Scope
from app.modules.auth.models import User
from app.modules.bookings.models import Booking, BookingStatus, Payment
from app.modules.calendar.models import CalendarEvent
from app.modules.customers.models import Customer
from app.modules.leads.models import PIPELINE_ORDER, Lead, LeadStage

router = APIRouter(prefix="/analytics", tags=["analytics"])

CLOSED_STAGES = {LeadStage.COMPLETED.value, LeadStage.LOST.value}


def _visible_user_ids(db: Session, ctx) -> list[str] | None:
    """None = no restriction (ALL scope)."""
    if ctx.scope == Scope.TEAM:
        return team_user_ids(db, ctx.user)
    if ctx.scope == Scope.OWN:
        return [ctx.user.id]
    return None


def _monthly_targets(db: Session, tenant_id: str) -> dict:
    """The monthly targets the admin set during onboarding (§21 of
    AI_Developer_Onboarding_Form.md, wizard step "9").

    Recorded but unused until now — the overview reported raw counts with nothing
    to judge them against, which is exactly what the form promised to supply.
    """
    from app.modules.auth.models import Tenant

    tenant = db.get(Tenant, tenant_id)
    step = ((tenant.onboarding_data if tenant else None) or {}).get("9") or {}
    targets: dict[str, float] = {}
    for source, key in [
        ("monthlyLeadTarget", "leads"),
        ("monthlySiteVisitTarget", "site_visits"),
        ("monthlyBookingTarget", "bookings"),
        ("monthlyRevenueTarget", "revenue"),
    ]:
        try:
            value = float(step[source])
        except (KeyError, TypeError, ValueError):
            continue
        if value > 0:
            targets[key] = value
    return targets


def _this_month_start() -> datetime:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _lead_query(db: Session, ctx):
    q = select(Lead).where(Lead.tenant_id == ctx.user.tenant_id, Lead.deleted_at.is_(None))
    ids = _visible_user_ids(db, ctx)
    if ids is not None:
        q = q.where(Lead.assigned_to.in_(ids))
    return q


@router.get("/overview")
def overview(ctx=Depends(require("analytics", "read")), db: Session = Depends(get_db)):
    leads = db.scalars(_lead_query(db, ctx)).all()
    total_leads = len(leads)
    active_leads = sum(1 for l in leads if l.stage not in CLOSED_STAGES)
    converted = sum(1 for l in leads if l.customer_id)
    ids = _visible_user_ids(db, ctx)

    booking_q = select(Booking).where(Booking.tenant_id == ctx.user.tenant_id)
    if ids is not None:
        booking_q = booking_q.where(Booking.assigned_to.in_(ids))
    bookings = db.scalars(booking_q).all()
    booking_ids = [b.id for b in bookings]
    revenue = 0.0
    if booking_ids:
        revenue = float(
            db.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.booking_id.in_(booking_ids)
                )
            )
        )
    site_visit_q = select(func.count(CalendarEvent.id)).where(
        CalendarEvent.tenant_id == ctx.user.tenant_id,
        CalendarEvent.type == "site_visit",
    )
    if ids is not None:
        site_visit_q = site_visit_q.where(CalendarEvent.owner_id.in_(ids))
    site_visits = db.scalar(site_visit_q)

    # Month-to-date actuals, so the onboarding targets have something comparable
    # to sit beside (the totals above are all-time and would never mean anything
    # against a monthly number).
    month_start = _this_month_start()
    month_leads = sum(1 for l in leads if l.created_at >= month_start)
    month_bookings = sum(1 for b in bookings if b.created_at >= month_start)
    month_revenue = 0.0
    if booking_ids:
        month_revenue = float(
            db.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.booking_id.in_(booking_ids),
                    Payment.created_at >= month_start,
                )
            )
        )
    month_site_visit_q = site_visit_q.where(CalendarEvent.created_at >= month_start)
    month_site_visits = db.scalar(month_site_visit_q)

    targets = _monthly_targets(db, ctx.user.tenant_id)
    actuals = {
        "leads": month_leads, "bookings": month_bookings,
        "revenue": month_revenue, "site_visits": month_site_visits,
    }

    return {
        "data": {
            "total_leads": total_leads,
            "active_leads": active_leads,
            "converted_leads": converted,
            "conversion_rate": round(converted / total_leads * 100, 1) if total_leads else 0.0,
            "bookings_total": len(bookings),
            "bookings_active": sum(1 for b in bookings if b.status == BookingStatus.ACTIVE.value),
            "revenue_collected": revenue,
            "pipeline_value": float(sum(b.total_value or 0 for b in bookings
                                        if b.status == BookingStatus.ACTIVE.value)),
            "site_visits": site_visits,
            "hot_leads": sum(1 for l in leads if l.score_band == "hot"),
            "month_to_date": actuals,
            # Empty when the admin set no targets — the UI then shows nothing
            # rather than inventing a goal of zero.
            "targets": [
                {
                    "metric": metric,
                    "target": target,
                    "actual": actuals[metric],
                    "progress_pct": round(actuals[metric] / target * 100, 1),
                }
                for metric, target in targets.items()
            ],
        }
    }


@router.get("/funnel")
def funnel(ctx=Depends(require("analytics", "read")), db: Session = Depends(get_db)):
    leads = db.scalars(_lead_query(db, ctx)).all()
    counts = {stage: 0 for stage in PIPELINE_ORDER}
    for lead in leads:
        counts[lead.stage] = counts.get(lead.stage, 0) + 1
    return {"data": [{"stage": s, "count": counts[s]} for s in PIPELINE_ORDER]}


@router.get("/revenue")
def revenue_series(
    months: int = 6, ctx=Depends(require("analytics", "read")), db: Session = Depends(get_db)
):
    ids = _visible_user_ids(db, ctx)
    booking_q = select(Booking.id).where(Booking.tenant_id == ctx.user.tenant_id)
    if ids is not None:
        booking_q = booking_q.where(Booking.assigned_to.in_(ids))
    booking_ids = db.scalars(booking_q).all()
    payments = []
    if booking_ids:
        payments = db.scalars(
            select(Payment).where(Payment.booking_id.in_(booking_ids))
        ).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    series = []
    for i in range(months - 1, -1, -1):
        anchor = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        key = anchor.strftime("%Y-%m")
        total = sum(float(p.amount) for p in payments if p.created_at.strftime("%Y-%m") == key)
        series.append({"month": key, "revenue": total})
    return {"data": series}


@router.get("/team")
def team_performance(
    ctx=Depends(require("analytics", "read")), db: Session = Depends(get_db)
):
    ids = _visible_user_ids(db, ctx)
    user_q = select(User).where(User.tenant_id == ctx.user.tenant_id, User.is_active.is_(True))
    if ids is not None:
        user_q = user_q.where(User.id.in_(ids))
    users = db.scalars(user_q).all()
    rows = []
    for member in users:
        # Defense-in-depth: don't trust assigned_to alone to imply
        # same-tenant — filter by tenant_id explicitly too.
        leads = db.scalars(
            select(Lead).where(
                Lead.assigned_to == member.id, Lead.tenant_id == ctx.user.tenant_id,
                Lead.deleted_at.is_(None),
            )
        ).all()
        bookings = db.scalars(
            select(Booking).where(
                Booking.assigned_to == member.id, Booking.tenant_id == ctx.user.tenant_id,
            )
        ).all()
        booking_ids = [b.id for b in bookings]
        revenue = 0.0
        if booking_ids:
            revenue = float(
                db.scalar(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.booking_id.in_(booking_ids)
                    )
                )
            )
        rows.append({
            "user_id": member.id,
            "name": member.full_name,
            "role": member.role,
            "leads": len(leads),
            "converted": sum(1 for l in leads if l.customer_id),
            "bookings": len(bookings),
            "revenue": revenue,
        })
    rows.sort(key=lambda r: -r["revenue"])
    return {"data": rows}


@router.get("/sources")
def source_performance(
    ctx=Depends(require("analytics", "read")), db: Session = Depends(get_db)
):
    leads = db.scalars(_lead_query(db, ctx)).all()
    by_source: dict[str, dict] = {}
    for lead in leads:
        row = by_source.setdefault(
            lead.source, {"source": lead.source, "leads": 0, "converted": 0, "booked": 0}
        )
        row["leads"] += 1
        if lead.customer_id:
            row["converted"] += 1
        if lead.stage in (LeadStage.BOOKED.value, LeadStage.COMPLETED.value):
            row["booked"] += 1
    for row in by_source.values():
        row["conversion_rate"] = round(row["converted"] / row["leads"] * 100, 1)
    return {"data": sorted(by_source.values(), key=lambda r: -r["leads"])}
