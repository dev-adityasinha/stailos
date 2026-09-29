from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_client_ip, get_current_user, get_db, require
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import ADMIN_ROLES, Role
from app.modules.auth import service
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    RoleUpdate,
    SessionOut,
    TokenResponse,
    UserOut,
    UserUpdate,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])

REFRESH_COOKIE = "pappu_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="none" if settings.cookie_secure else "lax",
        domain=settings.cookie_domain,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


def _user_out_with_tenant(db: Session, user: User) -> UserOut:
    """UserOut enriched with tenant context — used on auth responses so the
    frontend can show the workspace name and gate on onboarding status."""
    from app.modules.auth.models import Tenant

    out = UserOut.model_validate(user)
    tenant = db.get(Tenant, user.tenant_id)
    if tenant:
        out.tenant_name = tenant.name
        out.onboarding_completed = tenant.onboarding_completed
    return out


def _token_response(db: Session, user: User, access: str) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=access,
        expires_in=settings.access_token_expire_minutes * 60,
        user=_user_out_with_tenant(db, user),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    user = service.register_user(
        db,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        phone=body.phone,
        company_name=body.company_name,
        requested_role=None,  # self-registration never grants elevated roles
        ip=get_client_ip(request),
    )
    return {"data": UserOut.model_validate(user).model_dump()}


@router.post("/login")
def login(
    body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
):
    user, access, refresh = service.login(
        db,
        email=body.email,
        password=body.password,
        user_agent=request.headers.get("user-agent"),
        ip=get_client_ip(request),
    )
    _set_refresh_cookie(response, refresh)
    return {"data": _token_response(db, user, access).model_dump(), "refresh_token": refresh}


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: Session = Depends(get_db),
):
    token = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if not token:
        from app.core.errors import AuthError

        raise AuthError("Missing refresh token", code="missing_refresh")
    user, access, new_refresh = service.refresh_session(
        db,
        refresh_token_plain=token,
        user_agent=request.headers.get("user-agent"),
        ip=get_client_ip(request),
    )
    _set_refresh_cookie(response, new_refresh)
    return {"data": _token_response(db, user, access).model_dump(), "refresh_token": new_refresh}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: Session = Depends(get_db),
):
    token = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    service.logout(db, refresh_token_plain=token, user=None)
    _clear_refresh_cookie(response)
    return {"data": {"message": "Logged out"}}


@router.post("/password/forgot")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    service.forgot_password(db, email=body.email)
    return {"data": {"message": "If the account exists, a reset link has been sent."}}


@router.post("/password/reset")
def reset_password(body: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    service.reset_password(
        db, token=body.token, new_password=body.new_password, ip=get_client_ip(request)
    )
    return {"data": {"message": "Password updated. Please log in again."}}


@router.post("/verify-email")
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = service.verify_email(db, token=body.token)
    return {"data": {"message": "Email verified", "email": user.email}}

from app.modules.auth.schemas import ExchangeIssueResponse, ExchangeRedeemRequest

@router.post("/exchange/issue")
def issue_exchange_code(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    code = service.issue_exchange_code(db, user)
    return {"data": ExchangeIssueResponse(code=code).model_dump()}

@router.post("/exchange/redeem")
def redeem_exchange_code(
    body: ExchangeRedeemRequest, request: Request, response: Response, db: Session = Depends(get_db)
):
    user, access, refresh = service.redeem_exchange_code(
        db,
        code=body.code,
        user_agent=request.headers.get("user-agent"),
        ip=get_client_ip(request),
    )
    _set_refresh_cookie(response, refresh)
    return {"data": _token_response(db, user, access).model_dump(), "refresh_token": refresh}

@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"data": _user_out_with_tenant(db, user).model_dump()}


@router.get("/sessions")
def sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = service.list_sessions(db, user)
    return {"data": [SessionOut.model_validate(r).model_dump() for r in rows]}


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    service.revoke_session(db, user, session_id)
    return {"data": {"message": "Session revoked"}}


# ---------------------------------------------------------------- users admin


def _get_user_scoped(db: Session, ctx, user_id: str) -> User:
    """Fetch a user by id, scoped to the caller's tenant (never cross-tenant)."""
    user = db.get(User, user_id)
    if user is None or user.tenant_id != ctx.user.tenant_id:
        raise NotFoundError("User not found")
    return user


@users_router.get("")
def list_users(ctx=Depends(require("users", "read")), db: Session = Depends(get_db)):
    from app.core.deps import team_user_ids
    from app.core.permissions import Scope

    q = select(User).where(User.tenant_id == ctx.user.tenant_id).order_by(User.created_at)
    if ctx.scope == Scope.TEAM:
        q = q.where(User.id.in_(team_user_ids(db, ctx.user)))
    rows = db.scalars(q).all()
    return {"data": [UserOut.model_validate(u).model_dump() for u in rows]}


@users_router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    body: RegisterRequest,
    request: Request,
    ctx=Depends(require("users", "create")),
    db: Session = Depends(get_db),
):
    user = service.register_user(
        db,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        phone=body.phone,
        company_name=body.company_name,
        requested_role=body.role or Role.SALES_EXECUTIVE,
        created_by=ctx.user,
        ip=get_client_ip(request),
    )
    return {"data": UserOut.model_validate(user).model_dump()}


@users_router.get("/{user_id}")
def get_user(user_id: str, ctx=Depends(require("users", "read")), db: Session = Depends(get_db)):
    user = _get_user_scoped(db, ctx, user_id)
    return {"data": UserOut.model_validate(user).model_dump()}


@users_router.patch("/{user_id}")
def update_user(
    user_id: str,
    body: UserUpdate,
    ctx=Depends(require("users", "update")),
    db: Session = Depends(get_db),
):
    user = _get_user_scoped(db, ctx, user_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    return {"data": UserOut.model_validate(user).model_dump()}


@users_router.patch("/{user_id}/role")
def update_role(
    user_id: str,
    body: RoleUpdate,
    ctx=Depends(require("users", "update")),
    db: Session = Depends(get_db),
):
    if Role(ctx.user.role) not in ADMIN_ROLES:
        raise PermissionDeniedError("Only admins can change roles")
    user = _get_user_scoped(db, ctx, user_id)
    if user.id == ctx.user.id and body.role not in ADMIN_ROLES:
        raise PermissionDeniedError("You cannot demote your own admin account")
    user.role = body.role.value
    return {"data": UserOut.model_validate(user).model_dump()}


@users_router.delete("/{user_id}")
def deactivate_user(
    user_id: str, ctx=Depends(require("users", "delete")), db: Session = Depends(get_db)
):
    user = _get_user_scoped(db, ctx, user_id)
    if user.id == ctx.user.id:
        raise PermissionDeniedError("You cannot deactivate your own account")
    user.is_active = False
    return {"data": {"message": "User deactivated"}}
