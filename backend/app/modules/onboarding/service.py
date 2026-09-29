import logging

from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.audit import record_audit
from app.core.errors import AppError, NotFoundError
from app.core.storage import save_file
from app.modules.auth.models import Tenant, User
from app.modules.documents.models import (
    DOCUMENT_CATEGORIES,
    Document,
    DocumentVersion,
    WORKSPACE_CATEGORIES,
)

logger = logging.getLogger("crm.onboarding")


# ─────────────────────────────── workspace assets ────────────────────────────

def store_onboarding_asset(
    db: Session, user: User, *, filename: str | None, content: bytes,
    content_type: str | None, category: str, title: str | None = None,
) -> dict:
    """Persist an onboarding upload as a real, tenant-scoped document."""
    if category not in DOCUMENT_CATEGORIES:
        raise AppError(
            f"Unknown document category '{category}'", code="invalid_category"
        )
    stored = save_file("onboarding", filename or "upload", content)
    document = Document(
        tenant_id=user.tenant_id,
        title=(title or stored["filename"])[:300],
        category=category,
        entity_type="tenant",
        entity_id=user.tenant_id,
        created_by=user.id,
    )
    db.add(document)
    db.flush()
    db.add(DocumentVersion(
        document_id=document.id, version_number=1, filename=stored["filename"],
        stored_path=stored["stored_path"], size=stored["size"],
        content_type=content_type, uploaded_by=user.id,
    ))
    record_audit(
        db, tenant_id=user.tenant_id, action="onboarding.upload",
        actor_id=user.id, actor_email=user.email,
        entity_type="document", entity_id=document.id,
        detail={"category": category, "filename": stored["filename"]},
    )
    db.commit()
    return {
        "document_id": document.id,
        "title": document.title,
        "category": category,
        "filename": stored["filename"],
        "size": stored["size"],
        # Authenticated download through the documents API — not a public URL.
        "download_path": f"/documents/{document.id}/download",
    }


def list_onboarding_assets(db: Session, user: User) -> list[dict]:
    rows = db.scalars(
        select(Document)
        .where(
            Document.tenant_id == user.tenant_id,
            Document.entity_type == "tenant",
            Document.category.in_(WORKSPACE_CATEGORIES),
        )
        .order_by(Document.created_at.desc())
    ).all()
    return [
        {
            "document_id": d.id, "title": d.title, "category": d.category,
            "filename": d.versions[-1].filename if d.versions else None,
            "size": d.versions[-1].size if d.versions else 0,
            "download_path": f"/documents/{d.id}/download",
            "created_at": d.created_at.isoformat(),
        }
        for d in rows
    ]


def delete_onboarding_asset(db: Session, user: User, document_id: str) -> None:
    document = db.get(Document, document_id)
    if (
        document is None
        or document.tenant_id != user.tenant_id
        or document.entity_type != "tenant"
    ):
        raise NotFoundError("Document not found")
    record_audit(
        db, tenant_id=user.tenant_id, action="onboarding.upload_deleted",
        actor_id=user.id, actor_email=user.email,
        entity_type="document", entity_id=document.id,
    )
    # Rows go; the blob on disk is left in place deliberately — orphan cleanup is
    # a maintenance job, and deleting eagerly would break any older version row
    # that happens to point at the same stored path.
    db.delete(document)
    db.commit()

def update_onboarding_step(db: Session, user: User, step_id: str, data: dict):
    tenant = db.get(Tenant, user.tenant_id)
    if not tenant:
        return None
    
    # Copy (not alias) the existing dict: mutating tenant.onboarding_data's
    # underlying object in place, before reassigning it, corrupts SQLAlchemy's
    # change-tracking baseline for this JSON column and silently drops the
    # write on commit — every step after the first was lost this way.
    current_data = dict(tenant.onboarding_data or {})
    current_data[str(step_id)] = data
    
    # Company identity (step 1) renames the workspace; the primary-contact step
    # renames the admin. "fullName" is still honoured on step 1 for the older
    # wizard, which collected both on one page.
    key = str(step_id)
    if key == "1":
        if data.get("companyName"):
            tenant.name = str(data["companyName"]).strip()[:200]
        if data.get("fullName"):
            user.full_name = str(data["fullName"]).strip()[:200]
    elif key == "1b" and data.get("fullName"):
        user.full_name = str(data["fullName"]).strip()[:200]


    tenant.onboarding_data = dict(current_data)
    # Re-derive the flat tenant.settings view on every save, not only at
    # completion. Otherwise an admin editing AI features or consent from
    # Settings → Company profile leaves settings holding a stale second copy of
    # answers the rest of the app reads live from onboarding_data.
    _apply_company_profile(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant

# ──────────────────────── completion side effects (helpers) ─────────────────

# Project status the admin picks in the wizard → the value the properties module
# stores. Anything unrecognised stays "under_construction" rather than writing a
# status the inventory filters don't understand.
PROJECT_STATUSES = {
    "pre_launch": "pre_launch",
    "launched": "launched",
    "under_construction": "under_construction",
    "nearing_possession": "nearing_possession",
    "ready_to_move": "ready_to_move",
    "completed": "ready_to_move",
    "sold_out": "sold_out",
}

# Fallback carpet areas (sq ft) used only to give a brand-new unit a plausible
# size when the admin didn't type one. Wide enough to be honest, not precise.
CONFIG_AREAS = {
    "studio": 400.0, "1bhk": 600.0, "2bhk": 950.0, "3bhk": 1400.0,
    "4bhk": 2000.0, "5bhk": 2800.0, "villa": 2500.0, "plot": 1200.0,
}


def _parse_price_range(text) -> tuple[float | None, float | None]:
    """Read "₹1.2Cr – ₹3.4Cr" (or "80L to 1.2 crore", or a plain number) into a pair.

    The wizard collects a human-typed range because that is what builders quote;
    parsing it here is what turns it into inventory the matching engine can rank.
    """
    from app.modules.ai.llm import parse_inr

    if isinstance(text, (int, float)):
        value = float(text)
        return (value, value) if value > 0 else (None, None)
    if not text or not isinstance(text, str):
        return None, None
    import re

    parts = [p for p in re.split(r"\s*(?:-|–|—|to|and)\s*", text, flags=re.IGNORECASE) if p.strip()]
    values = [v for v in (parse_inr(p) for p in parts) if v]
    if not values:
        return None, None
    return float(min(values)), float(max(values))


def _create_projects(db: Session, tenant: Tenant, projects: list) -> list:
    """Turn the wizard's project forms into real inventory.

    Previously every project got one hardcoded placeholder — "Unit-1", 1BHK, 0 sq ft,
    ₹0 — which made the property module look populated while being useless: a ₹0
    unit matches every budget and ranks first in every recommendation. Now each
    configuration the admin listed becomes its own unit, priced from the stated
    range, so matching and the investment widgets have real numbers to work with.
    """
    from app.modules.properties.models import PropertyProject, PropertyUnit

    created = []
    for entry in projects:
        if not isinstance(entry, dict) or not (entry.get("name") or "").strip():
            continue
        low, high = _parse_price_range(entry.get("priceRange"))
        amenities = entry.get("amenities") or []
        if isinstance(amenities, str):
            amenities = [a.strip() for a in amenities.split(",") if a.strip()]

        project = PropertyProject(
            tenant_id=tenant.id,
            name=entry["name"].strip()[:200],
            builder_name=(entry.get("builderName") or tenant.name)[:200],
            location=(entry.get("location") or "")[:300],
            # City used to be hardcoded "Unknown", which broke every
            # city-filtered inventory search for onboarded projects.
            city=(entry.get("city") or _city_from_location(entry.get("location")) or "")[:100],
            description=(entry.get("usp") or entry.get("description") or None),
            amenities=amenities or None,
            status=PROJECT_STATUSES.get(
                str(entry.get("status") or "").lower(), "under_construction"
            ),
            rera_id=(entry.get("rera") or None),
            possession_date=(entry.get("possession") or None),
        )
        db.add(project)
        db.flush()

        configurations = entry.get("configurations") or []
        if isinstance(configurations, str):
            configurations = [c.strip() for c in configurations.split(",") if c.strip()]
        if not configurations:
            configurations = ["Unit"]

        for index, configuration in enumerate(configurations):
            label = str(configuration).strip()[:50] or "Unit"
            # Spread the stated range across configurations so a 2BHK isn't priced
            # like the penthouse: smallest config at the floor, largest at the top.
            if low is not None and high is not None and len(configurations) > 1:
                step = (high - low) / (len(configurations) - 1)
                price = low + step * index
            else:
                price = low or high or 0.0
            db.add(PropertyUnit(
                project_id=project.id,
                unit_number=f"{label}-01",
                unit_type=label,
                carpet_area_sqft=CONFIG_AREAS.get(label.lower().replace(" ", "")),
                price=round(price, 2),
                status="available",
            ))
        created.append(project)
    return created


def _city_from_location(location) -> str | None:
    """Best-effort city from a "Locality, City" string the wizard collects."""
    if not location or not isinstance(location, str):
        return None
    parts = [p.strip() for p in location.split(",") if p.strip()]
    return parts[-1][:100] if parts else None


def _apply_company_profile(tenant: Tenant) -> None:
    """Promote the onboarding answers the rest of the app reads into tenant.settings.

    `onboarding_data` is the raw wizard transcript keyed by step. Everything that
    other modules consume (company identity, ICP, AI feature flags, consents) is
    copied into a stable, flat shape here so no other module has to know step
    numbers — the AI scoring config is the one exception, read straight from
    step "5" by `ai/grading.py`.
    """
    data = tenant.onboarding_data or {}
    company = data.get("1") or {}
    contact = data.get("1b") or {}
    profile = data.get("1c") or {}
    icp = data.get("4") or {}
    features = data.get("6") or {}
    process = data.get("9") or {}
    consent = data.get("12") or {}

    settings = dict(tenant.settings or {})
    settings["company"] = {
        k: v for k, v in {
            "legal_name": company.get("legalName"),
            "brand_name": company.get("brandName"),
            "cin": company.get("cin"),
            "gst": company.get("gst"),
            "pan": company.get("pan"),
            "rera": company.get("rera"),
            "year_established": company.get("yearEstablished"),
            "website": company.get("website"),
            "linkedin": company.get("linkedin"),
            "address": company.get("address"),
            "head_office": company.get("headOffice"),
            "state": company.get("state"),
            "country": company.get("country"),
            "business_types": profile.get("businessTypes"),
            "property_types": profile.get("propertyTypes"),
            "cities": profile.get("cities"),
            "employees": profile.get("employees"),
            "years_in_real_estate": profile.get("yearsInRealEstate"),
        }.items() if v not in (None, "", [])
    }
    settings["primary_contact"] = {
        k: v for k, v in {
            "full_name": contact.get("fullName"),
            "designation": contact.get("designation"),
            "mobile": contact.get("mobile"),
            "whatsapp": contact.get("whatsapp"),
            "email": contact.get("email"),
            "preferred_channel": contact.get("preferredChannel"),
        }.items() if v
    }
    if icp:
        settings["icp"] = icp
    if features:
        settings["ai_features"] = features
    if process:
        settings["sales_process"] = process
    settings["consents"] = {
        "marketing": bool(consent.get("marketingConsent")),
        "ai_usage": bool(consent.get("aiUsageConsent")),
        "integrations": consent.get("integrations") or [],
    }
    tenant.settings = settings


def get_onboarding_state(db: Session, tenant_id: str):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        return None
    return {
        "onboarding_data": tenant.onboarding_data,
        "onboarding_completed": tenant.onboarding_completed
    }

def complete_onboarding(db: Session, tenant_id: str, actor: User | None = None):
    """Returns a result dict: {"invites": {"sent": [...], "already_exists":
    [...], "failed": [...]}} — the caller surfaces these to the admin so a
    skipped invite (e.g. an email that already has an account elsewhere;
    emails are globally unique, one account = one workspace) is never
    silent."""
    invite_results = {"sent": [], "already_exists": [], "failed": []}
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        return None

    if not tenant.onboarding_completed and tenant.onboarding_data:
        _apply_company_profile(tenant)
        _create_projects(db, tenant, (tenant.onboarding_data.get("2") or {}).get("projects") or [])

        # Extract team invites from step 11
        step_11 = tenant.onboarding_data.get("11", {})
        team_invites = step_11.get("teamInvites", [])
        permission_level = step_11.get("permissionLevel", "Sales")
        
        # Map StailOS role strings to Role enums
        from app.core.permissions import Role
        role_map = {
            "Admin": Role.COMPANY_ADMIN,
            "Manager": Role.SALES_MANAGER,
            "Sales": Role.SALES_EXECUTIVE,
            "Marketing": Role.MARKETING_EXECUTIVE,
            "CRM": Role.CUSTOMER_SUPPORT,
            "Support": Role.CUSTOMER_SUPPORT,
        }
        mapped_role = role_map.get(permission_level, Role.SALES_EXECUTIVE)
        
        if team_invites:
            from datetime import timedelta
            import secrets

            from app.core.config import get_settings
            from app.core.email import send_email
            from app.core.security import create_token
            from app.modules.auth.service import register_user

            settings = get_settings()
            # Attribute invites to the authenticated caller; fall back to any
            # active company admin of this tenant. Never invite with
            # created_by=None — register_user would then treat each invitee
            # as a public self-registration and fork a brand-new tenant.
            admin_user = actor or db.scalars(
                select(User).where(
                    User.tenant_id == tenant.id,
                    User.role == Role.COMPANY_ADMIN.value,
                    User.is_active.is_(True),
                )
            ).first()
            if admin_user is None:
                logger.error(
                    "skipping %d team invite(s) for tenant %s: no admin to attribute them to",
                    len(team_invites), tenant.id,
                )
                team_invites = []

            from app.core.errors import ConflictError

            for email in team_invites:
                try:
                    # Random placeholder password — the invite email below
                    # carries a set-your-password link (same token/route as
                    # the normal reset flow), which is the only way the
                    # invitee ever gets in. The SAVEPOINT confines a failed
                    # insert to this one invite: without it, one bad email
                    # poisons the session, every later invite "fails", and
                    # the final commit 500s while the already-sent emails
                    # point at rolled-back users.
                    temp_password = secrets.token_urlsafe(16)
                    with db.begin_nested():
                        invited = register_user(
                            db=db,
                            email=email,
                            password=temp_password,
                            full_name=email.split('@')[0].capitalize(),
                            phone="",
                            company_name=None,
                            created_by=admin_user,
                            requested_role=mapped_role,
                            ip="0.0.0.0",
                            # The invite email below carries the set-password
                            # link; a separate "verify your account" mail would
                            # just be a second, unusable message.
                            send_verification=False,
                        )
                    # Only reached when the invitee's row flushed cleanly.
                    invite_token = create_token(
                        invited.id, "password_reset", timedelta(hours=72)
                    )
                    send_email(
                        db,
                        to=invited.email,
                        subject=f"You've been invited to {tenant.name} on Pappu AI CRM",
                        body=(
                            f"{admin_user.full_name} invited you to join {tenant.name}.\n\n"
                            "Set your password to get started:\n"
                            f"{settings.frontend_origin}/reset-password?token={invite_token}\n\n"
                            "The link expires in 72 hours."
                        ),
                        category="team_invite",
                    )
                    invite_results["sent"].append(email)
                except ConflictError:
                    # Emails are globally unique — this address already has an
                    # account (in this workspace or another). Not an error,
                    # but the admin must see it, not just a server log.
                    logger.info("team invite skipped, email already registered: %s", email)
                    invite_results["already_exists"].append(email)
                except Exception:
                    logger.exception("team invite failed for email=%s", email)
                    invite_results["failed"].append(email)
        
        # Extract leads and customers from step 7
        step_7 = tenant.onboarding_data.get("7", {})
        import_leads = step_7.get("importLeads", [])
        import_customers = step_7.get("importCustomers", [])
        
        if import_leads or import_customers:
            from app.modules.leads.models import Lead, LeadStage
            from app.modules.customers.models import Customer
            from app.modules.leads.service import normalize_phone
            
            # Import Leads
            for l in import_leads:
                try:
                    first = l.get("first_name", "").strip()
                    last = l.get("last_name", "").strip()
                    full_name = f"{first} {last}".strip() or "Unnamed Lead"
                    phone = l.get("phone", "").strip()
                    
                    if phone:
                        db.add(Lead(
                            tenant_id=tenant.id,
                            full_name=full_name,
                            email=l.get("email", "").strip() or None,
                            phone=phone,
                            phone_normalized=normalize_phone(phone) or phone,
                            source="csv_import",
                            stage=LeadStage.NEW.value,
                            requirements=l.get("project_interest", "")
                        ))
                except Exception:
                    pass

            # Import Customers
            for c in import_customers:
                try:
                    first = c.get("first_name", "").strip()
                    last = c.get("last_name", "").strip()
                    full_name = f"{first} {last}".strip() or "Unnamed Customer"
                    phone = c.get("phone", "").strip()
                    
                    if phone:
                        db.add(Customer(
                            tenant_id=tenant.id,
                            full_name=full_name,
                            email=c.get("email", "").strip() or None,
                            phone=phone,
                            phone_normalized=normalize_phone(phone) or phone,
                        ))
                except Exception:
                    pass

    tenant.onboarding_completed = True
    db.commit()
    db.refresh(tenant)
    return {"tenant": tenant, "invites": invite_results}
