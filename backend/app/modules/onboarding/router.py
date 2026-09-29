from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.core.errors import PermissionDeniedError
from app.core.permissions import ADMIN_ROLES, Role
from app.modules.auth.models import User
from app.modules.onboarding import service
from app.modules.onboarding.schemas import ONBOARDING_STEPS, OnboardingStepUpdate

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Onboarding reads/writes tenant-wide state (renames the tenant, holds
    GST/billing details, creates projects and invites users on complete) —
    company/super admins only."""
    if Role(user.role) not in ADMIN_ROLES:
        raise PermissionDeniedError("Only workspace admins can manage onboarding")
    return user


@router.get("/steps")
def list_steps(user: User = Depends(require_admin)):
    """The canonical step registry — what each page collects and what it changes."""
    return {"data": ONBOARDING_STEPS}


@router.get("/state")
def get_onboarding_state(
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(require_admin),
):
    tenant = service.get_onboarding_state(db, user.tenant_id)
    return {"data": tenant}


@router.patch("/step")
def update_step(
    body: OnboardingStepUpdate,
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(require_admin),
):
    tenant = service.update_onboarding_step(db, user, str(body.step_id), body.data)
    return {"data": {"message": "Step updated", "onboarding_data": tenant.onboarding_data if tenant else None}}


@router.post("/complete")
def complete_onboarding(
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(require_admin),
):
    # Pass the caller: invites must be attributed to a real admin in THIS
    # tenant, never inferred (an inferred lookup could come up empty and
    # silently turn invitees into brand-new standalone workspaces).
    result = service.complete_onboarding(db, user.tenant_id, actor=user)
    invites = result["invites"] if result else {"sent": [], "already_exists": [], "failed": []}
    return {"data": {"message": "Onboarding completed successfully", "invites": invites}}


@router.post("/upload", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    category: str = Form(default="other"),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(require_admin),
):
    """Store a workspace asset (logo, brochure, RERA certificate, AI knowledge base…).

    This used to return `https://storage.stail.ai/mock/<filename>` without writing
    anything: the wizard reported success, the file was discarded, and the URL 404'd
    forever. Uploads now go through the same storage layer and `documents` tables as
    the rest of the CRM, filed against the tenant, so they are listable,
    downloadable, versioned, and audited like any other document.
    """
    content = await file.read()
    return {"data": service.store_onboarding_asset(
        db, user, filename=file.filename, content=content,
        content_type=file.content_type, category=category, title=title,
    )}


@router.get("/documents")
def list_onboarding_documents(
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(require_admin),
):
    """What has actually been uploaded — so the wizard can show it on revisit."""
    return {"data": service.list_onboarding_assets(db, user)}


@router.delete("/documents/{document_id}", status_code=204)
def delete_onboarding_document(
    document_id: str,
    db: Session = Depends(get_db, scope="function"),
    user: User = Depends(require_admin),
):
    service.delete_onboarding_asset(db, user, document_id)
    return Response(status_code=204)
