"""Report generation with CSV / Excel / PDF export."""
import csv
import io
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import AccessContext
from app.core.errors import AppError
from app.modules.auth.models import User
from app.modules.bookings.models import Booking, Payment
from app.modules.leads.models import Lead
from app.modules.leads.service import scoped_query as leads_scoped
from app.modules.properties.models import PropertyProject, PropertyUnit

REPORT_TYPES = ["lead", "sales", "agent", "booking", "property", "revenue", "campaign"]
FORMATS = ["csv", "xlsx", "pdf"]


def _rows_lead(db: Session, ctx: AccessContext):
    header = ["Name", "Phone", "Email", "Source", "Stage", "Score band",
              "Assigned to", "Created"]
    rows = []
    for lead in db.scalars(leads_scoped(db, ctx).order_by(Lead.created_at)).all():
        rows.append([
            lead.full_name, lead.phone, lead.email or "", lead.source, lead.stage,
            lead.score_band or "", lead.assignee.full_name if lead.assignee else "",
            lead.created_at.strftime("%Y-%m-%d"),
        ])
    return header, rows


def _bookings_visible(db: Session, ctx: AccessContext):
    from app.modules.bookings.service import scoped_query as bookings_scoped

    return db.scalars(bookings_scoped(db, ctx).order_by(Booking.created_at)).all()


def _rows_sales(db: Session, ctx: AccessContext):
    header = ["Customer", "Project", "Unit", "Stage", "Status", "Total value",
              "Paid", "Outstanding"]
    rows = []
    for b in _bookings_visible(db, ctx):
        paid = float(
            db.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.booking_id == b.id
                )
            )
        )
        total = float(b.total_value or 0) - float(b.discount or 0)
        rows.append([
            b.customer.full_name, b.unit.project.name, b.unit.unit_number, b.stage,
            b.status, total, paid, total - paid,
        ])
    return header, rows


def _rows_agent(db: Session, ctx: AccessContext):
    header = ["Agent", "Role", "Leads", "Converted", "Bookings", "Revenue"]
    rows = []
    users = db.scalars(
        select(User).where(User.tenant_id == ctx.user.tenant_id, User.is_active.is_(True))
    ).all()
    for member in users:
        # Defense-in-depth: assigned_to should always imply same-tenant, but
        # don't trust that invariant blindly in an aggregate report — filter
        # by tenant_id explicitly too.
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
        revenue = 0.0
        if bookings:
            revenue = float(
                db.scalar(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.booking_id.in_([b.id for b in bookings])
                    )
                )
            )
        rows.append([
            member.full_name, member.role, len(leads),
            sum(1 for l in leads if l.customer_id), len(bookings), revenue,
        ])
    return header, rows


def _rows_booking(db: Session, ctx: AccessContext):
    header = ["Customer", "Unit", "Stage", "Status", "Token", "Total value", "Created"]
    rows = [
        [b.customer.full_name, f"{b.unit.project.name} #{b.unit.unit_number}", b.stage,
         b.status, float(b.token_amount or 0), float(b.total_value or 0),
         b.created_at.strftime("%Y-%m-%d")]
        for b in _bookings_visible(db, ctx)
    ]
    return header, rows


def _rows_property(db: Session, ctx: AccessContext):
    header = ["Project", "City", "Unit", "Type", "Area sqft", "Price", "Status"]
    units = db.scalars(
        select(PropertyUnit).join(PropertyProject).where(
            PropertyProject.tenant_id == ctx.user.tenant_id
        )
    ).all()
    rows = [
        [u.project.name, u.project.city, u.unit_number, u.unit_type,
         float(u.carpet_area_sqft or 0), float(u.price), u.status]
        for u in units
    ]
    return header, rows


def _rows_revenue(db: Session, ctx: AccessContext):
    header = ["Receipt", "Customer", "Unit", "Milestone", "Method", "Amount", "Date"]
    rows = []
    for b in _bookings_visible(db, ctx):
        for p in b.payments:
            rows.append([
                p.receipt_number, b.customer.full_name,
                f"{b.unit.project.name} #{b.unit.unit_number}", p.milestone or "",
                p.method, float(p.amount), p.created_at.strftime("%Y-%m-%d"),
            ])
    return header, rows


def _rows_campaign(db: Session, ctx: AccessContext):
    """ROI/conversion by lead source+campaign — same aggregation shape as
    _rows_agent, grouped by acquisition channel instead of user. Booking.lead_id
    is a loose string column (not an ORM FK), so revenue attribution joins by
    value rather than relationship."""
    header = ["Source", "Campaign", "Leads", "Converted", "Conversion rate %", "Revenue"]
    groups: dict[tuple[str, str], list[Lead]] = {}
    for lead in db.scalars(leads_scoped(db, ctx)).all():
        groups.setdefault((lead.source, lead.campaign or ""), []).append(lead)

    rows = []
    for (source, campaign), group_leads in sorted(groups.items()):
        lead_ids = [l.id for l in group_leads]
        converted = sum(1 for l in group_leads if l.customer_id)
        conversion_rate = round(converted / len(group_leads) * 100, 1) if group_leads else 0.0
        booking_ids = db.scalars(select(Booking.id).where(Booking.lead_id.in_(lead_ids))).all()
        revenue = 0.0
        if booking_ids:
            revenue = float(
                db.scalar(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.booking_id.in_(booking_ids)
                    )
                )
            )
        rows.append([source, campaign, len(group_leads), converted, conversion_rate, revenue])
    return header, rows


_BUILDERS = {
    "lead": _rows_lead, "sales": _rows_sales, "agent": _rows_agent,
    "booking": _rows_booking, "property": _rows_property, "revenue": _rows_revenue,
    "campaign": _rows_campaign,
}


def _to_csv(title: str, header: list, rows: list) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _to_xlsx(title: str, header: list, rows: list) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    for i, col in enumerate(header, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(
            14, len(str(col)) + 4
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _to_pdf(title: str, header: list, rows: list) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1 * cm, rightMargin=1 * cm)
    styles = getSampleStyleSheet()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    elements = [
        Paragraph(f"Pappu AI CRM — {title}", styles["Title"]),
        Paragraph(f"Generated {generated}", styles["Normal"]),
        Spacer(1, 12),
    ]
    data = [header] + [[str(c) for c in row] for row in rows[:1000]]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    elements.append(table)
    doc.build(elements)
    return buf.getvalue()


_RENDERERS = {"csv": _to_csv, "xlsx": _to_xlsx, "pdf": _to_pdf}

MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def generate(db: Session, ctx: AccessContext, report_type: str, format: str) -> dict:
    if report_type not in REPORT_TYPES:
        raise AppError(f"Unknown report type '{report_type}'", code="unknown_report")
    if format not in FORMATS:
        raise AppError(f"Unsupported format '{format}'", code="unsupported_format")
    header, rows = _BUILDERS[report_type](db, ctx)
    title = f"{report_type.title()} Report"
    content = _RENDERERS[format](title, header, rows)
    return {
        "content": content,
        "filename": f"{report_type}_report_{datetime.now(timezone.utc):%Y%m%d_%H%M}.{format}",
        "media_type": MEDIA_TYPES[format],
        "row_count": len(rows),
    }
