"""Demo seed data: users for every role, property inventory, leads across all
pipeline stages, a converted customer with booking + payment, tasks, events.

Run:  .venv/bin/python -m app.db.seed
Idempotent: skips if the admin user already exists.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.main import app  # noqa: F401  (ensures models are registered + tables exist)
from app.core.security import hash_password
from app.db.base import SessionLocal
from app.modules.auth.models import Tenant, User
from app.modules.bookings.models import Booking, BookingStageEvent, Payment
from app.modules.calendar.models import CalendarEvent
from app.modules.customers.models import Customer
from app.modules.leads.models import Lead, LeadNote, Tag
from app.modules.leads.service import normalize_phone
from app.modules.notifications.models import Notification
from app.modules.properties.models import PropertyProject, PropertyUnit
from app.modules.tasks.models import CrmTask
from app.modules.timeline.models import log_activity

PASSWORD = "Demo!Pass2026"

USERS = [
    ("admin@pappuai.com", "Aarav Mehta", "super_admin", None),
    ("owner@pappuai.com", "Kavita Rao", "company_admin", None),
    ("manager@pappuai.com", "Rohan Iyer", "sales_manager", None),
    ("exec1@pappuai.com", "Sneha Kulkarni", "sales_executive", "manager@pappuai.com"),
    ("exec2@pappuai.com", "Arjun Nair", "sales_executive", "manager@pappuai.com"),
    ("caller@pappuai.com", "Pooja Singh", "telecaller", "manager@pappuai.com"),
    ("marketing@pappuai.com", "Dev Sharma", "marketing_executive", None),
    ("partner@pappuai.com", "Nisha Chandra", "channel_partner", None),
    ("support@pappuai.com", "Vikas Joshi", "customer_support", None),
]

PROJECTS = [
    {
        "name": "Prestige Lakeside Habitat", "builder_name": "Prestige Group",
        "location": "Varthur Road, Whitefield", "city": "Bangalore",
        "description": "Premium lakeside township with 80% open space.",
        "amenities": ["Clubhouse", "Pool", "Gym", "Tennis", "Kids play area"],
        "status": "ready_to_move", "rera_id": "PRM/KA/RERA/1251/446",
        "units": [
            ("A-101", 1, "2BHK", 1050, 7500000, "East"),
            ("A-102", 1, "3BHK", 1450, 11000000, "North"),
            ("B-201", 2, "3BHK", 1500, 12000000, "East"),
            ("B-502", 5, "4BHK", 2100, 18500000, "West"),
        ],
    },
    {
        "name": "Sobha Dream Acres", "builder_name": "Sobha Ltd",
        "location": "Panathur Road, Balagere", "city": "Bangalore",
        "description": "Smart homes with precision engineering.",
        "amenities": ["Pool", "Gym", "Amphitheatre", "Jogging track"],
        "status": "under_construction", "rera_id": "PRM/KA/RERA/1250/303",
        "possession_date": "2027-06",
        "units": [
            ("T1-304", 3, "1BHK", 650, 4500000, "North"),
            ("T1-902", 9, "2BHK", 1000, 6800000, "East"),
            ("T2-1204", 12, "2BHK", 1010, 7100000, "South"),
        ],
    },
    {
        "name": "Godrej Park Retreat", "builder_name": "Godrej Properties",
        "location": "Sarjapur Road", "city": "Bangalore",
        "description": "Forest-themed living, 2.5 acres of parks.",
        "amenities": ["Clubhouse", "Pet park", "Co-working lounge"],
        "status": "under_construction", "rera_id": "PRM/KA/RERA/1268/012",
        "possession_date": "2026-12",
        "units": [
            ("PR-701", 7, "3BHK", 1380, 9800000, "East"),
            ("PR-702", 7, "3BHK", 1380, 9900000, "West"),
            ("PR-1101", 11, "Villa", 2600, 26000000, "East"),
        ],
    },
]

LEADS = [
    ("Rahul Sharma", "9876543210", "rahul.s@example.com", "website", "new",
     5000000, 8000000, "Whitefield", "3BHK Apartment", "exec1@pappuai.com"),
    ("Priya Patel", "9812345670", "priya.p@example.com", "meta_ads", "contacted",
     6000000, 9000000, "Sarjapur Road", "3BHK", "exec1@pappuai.com"),
    ("Amit Desai", "9898989898", "amit.d@example.com", "google_ads", "qualified",
     4000000, 7000000, "Balagere", "2BHK", "exec2@pappuai.com"),
    ("Neha Gupta", "9765432109", "neha.g@example.com", "referral", "interested",
     10000000, 15000000, "Whitefield", "3BHK", "exec2@pappuai.com"),
    ("Suresh Reddy", "9654321098", None, "walk_in", "site_visit_scheduled",
     8000000, 12000000, "Varthur", "3BHK", "exec1@pappuai.com"),
    ("Anita Krishnan", "9543210987", "anita.k@example.com", "channel_partner",
     "negotiation", 15000000, 20000000, "Whitefield", "4BHK", "manager@pappuai.com"),
    ("Vikram Malhotra", "9432109876", "vikram.m@example.com", "property_portal",
     "booked", 9000000, 12000000, "Whitefield", "3BHK", "exec2@pappuai.com"),
    ("Deepa Menon", "9321098765", "deepa.m@example.com", "whatsapp", "lost",
     3000000, 4500000, "Electronic City", "2BHK", "caller@pappuai.com"),
    ("Kiran Kumar", "9210987654", "kiran.k@example.com", "event", "new",
     5500000, 7500000, "Panathur", "2BHK", "caller@pappuai.com"),
    ("Meera Joshi", "9109876543", "meera.j@example.com", "meta_ads", "contacted",
     7000000, 10000000, "Sarjapur", "3BHK", "exec1@pappuai.com"),
]


def run() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        if db.query(User).filter(User.email == "admin@pappuai.com").first():
            print("Seed data already present — skipping.")
            return

        tenant = db.query(Tenant).first()
        if tenant is None:
            tenant = Tenant(name="STAIL Realty", slug="stail-realty", plan_tier="enterprise")
            db.add(tenant)
            db.flush()
        # Demo tenant counts as onboarded — otherwise the in-app onboarding
        # gate would trap every seeded demo login in the setup wizard.
        tenant.onboarding_completed = True
        tenant.onboarding_data = tenant.onboarding_data or {
            "1": {"companyName": "STAIL Realty", "headOffice": "Bengaluru"}
        }

        users: dict[str, User] = {}
        for email, name, role, manager_email in USERS:
            user = User(
                tenant_id=tenant.id, email=email, password_hash=hash_password(PASSWORD),
                full_name=name, role=role, email_verified=True,
                manager_id=users[manager_email].id if manager_email else None,
                avatar_color=["#3B82F6", "#10B981", "#8B5CF6", "#F59E0B",
                              "#EF4444", "#06B6D4"][len(users) % 6],
            )
            db.add(user)
            db.flush()
            users[email] = user

        units_by_number: dict[str, PropertyUnit] = {}
        for p in PROJECTS:
            unit_rows = p.pop("units")
            project = PropertyProject(tenant_id=tenant.id, **p)
            db.add(project)
            db.flush()
            for number, floor, utype, area, price, facing in unit_rows:
                unit = PropertyUnit(
                    project_id=project.id, unit_number=number, floor=floor,
                    unit_type=utype, carpet_area_sqft=area, price=price, facing=facing,
                )
                db.add(unit)
                db.flush()
                units_by_number[number] = unit

        hot_tag = Tag(tenant_id=tenant.id, name="hot", color="#EF4444")
        nri_tag = Tag(tenant_id=tenant.id, name="nri", color="#3B82F6")
        db.add_all([hot_tag, nri_tag])
        db.flush()

        leads: list[Lead] = []
        for i, (name, phone, email, source, stage, bmin, bmax, loc, ptype,
                owner_email) in enumerate(LEADS):
            owner = users[owner_email]
            lead = Lead(
                tenant_id=tenant.id, full_name=name, phone=phone,
                phone_normalized=normalize_phone(phone), email=email, source=source,
                stage=stage, assigned_to=owner.id, created_by=owner.id,
                budget_min=bmin, budget_max=bmax, location_preference=loc,
                property_type=ptype,
                created_at=now - timedelta(days=20 - i * 2),
            )
            if stage in ("negotiation", "booked"):
                lead.tags.append(hot_tag)
                lead.ai_score, lead.score_band = 82.0, "hot"
            elif stage in ("qualified", "interested", "site_visit_scheduled"):
                lead.ai_score, lead.score_band = 58.0, "warm"
            db.add(lead)
            db.flush()
            log_activity(db, tenant_id=tenant.id, entity_type="lead", entity_id=lead.id,
                         type="created", title=f"Lead created via {source}", actor=owner)
            leads.append(lead)

        db.add(LeadNote(lead_id=leads[4].id, author_id=users["exec1@pappuai.com"].id,
                        author_name="Sneha Kulkarni",
                        body="Confirmed Saturday 11am site visit; arrange cab pickup."))

        # Converted customer + booking + payment for Vikram (booked lead).
        vikram = leads[6]
        customer = Customer(
            tenant_id=tenant.id, full_name=vikram.full_name, email=vikram.email,
            phone=vikram.phone, phone_normalized=vikram.phone_normalized,
            city="Bangalore", occupation="Product Manager", company="Flipkart",
            budget_min=vikram.budget_min, budget_max=vikram.budget_max,
            preferences={"location": "Whitefield", "property_type": "3BHK",
                         "facing": "East"},
            family_info=[{"name": "Ritu Malhotra", "relation": "spouse", "age": 34}],
            assigned_to=vikram.assigned_to, created_by=vikram.assigned_to,
            lead_id=vikram.id,
        )
        db.add(customer)
        db.flush()
        vikram.customer_id = customer.id
        log_activity(db, tenant_id=tenant.id, entity_type="customer",
                     entity_id=customer.id, type="created",
                     title="Created by converting lead")

        unit = units_by_number["B-201"]
        unit.status = "booked"
        booking = Booking(
            tenant_id=tenant.id, customer_id=customer.id, lead_id=vikram.id,
            unit_id=unit.id, stage="payment", status="active",
            token_amount=Decimal("500000"), total_value=Decimal("12000000"),
            assigned_to=vikram.assigned_to, created_by=vikram.assigned_to,
        )
        db.add(booking)
        db.flush()
        for i, (frm, to) in enumerate([(None, "site_visit"), ("site_visit", "booking"),
                                       ("booking", "documentation"),
                                       ("documentation", "payment")]):
            db.add(BookingStageEvent(
                booking_id=booking.id, from_stage=frm, to_stage=to,
                actor_name="Arjun Nair",
                created_at=now - timedelta(days=8 - i * 2),
            ))
        db.add(Payment(booking_id=booking.id, amount=Decimal("500000"),
                       method="upi", receipt_number="RCPT-000001",
                       milestone="Token", recorded_by=vikram.assigned_to,
                       created_at=now - timedelta(days=6)))
        db.add(Payment(booking_id=booking.id, amount=Decimal("2500000"),
                       method="bank_transfer", receipt_number="RCPT-000002",
                       milestone="Down payment", recorded_by=vikram.assigned_to,
                       created_at=now - timedelta(days=2)))

        for title, owner_email, days, priority in [
            ("Call Rahul Sharma — first contact", "exec1@pappuai.com", 0, "urgent"),
            ("Send Sobha brochure to Amit", "exec2@pappuai.com", 1, "high"),
            ("Prepare payment-plan comparison for Anita", "manager@pappuai.com", 2, "high"),
            ("Collect KYC documents from Vikram", "exec2@pappuai.com", 3, "medium"),
        ]:
            db.add(CrmTask(
                tenant_id=tenant.id, title=title, assigned_to=users[owner_email].id,
                created_by=users["manager@pappuai.com"].id,
                due_date=now + timedelta(days=days), priority=priority,
            ))

        for title, etype, owner_email, days_ahead in [
            ("Site visit — Suresh Reddy @ Prestige Lakeside", "site_visit",
             "exec1@pappuai.com", 1),
            ("Negotiation call — Anita Krishnan", "call", "manager@pappuai.com", 2),
            ("Weekly pipeline review", "meeting", "manager@pappuai.com", 3),
        ]:
            db.add(CalendarEvent(
                tenant_id=tenant.id, title=title, type=etype,
                owner_id=users[owner_email].id,
                start_at=now + timedelta(days=days_ahead, hours=10),
                end_at=now + timedelta(days=days_ahead, hours=11),
            ))

        db.add(Notification(
            tenant_id=tenant.id, user_id=users["exec1@pappuai.com"].id,
            type="assignment", title="Lead assigned to you: Rahul Sharma",
            entity_type="lead", entity_id=leads[0].id,
        ))

        db.commit()
        print(f"Seeded: {len(USERS)} users, {len(PROJECTS)} projects, "
              f"{len(LEADS)} leads, 1 customer, 1 booking, 4 tasks, 3 events.")
        print(f"All demo accounts use password: {PASSWORD}")


if __name__ == "__main__":
    run()
