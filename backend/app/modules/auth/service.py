"""Auth business logic: registration, login with lockout, refresh rotation with
reuse detection, password reset, email verification, session management."""
import random
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import events
from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.email import send_email
from app.core.errors import AppError, AuthError, ConflictError, NotFoundError
from app.core.permissions import Role
from app.core.security import (
    create_access_token,
    create_token,
    decode_token,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)
from app.db.base import new_uuid, utcnow
from app.modules.auth.models import LoginAttempt, RefreshToken, Tenant, User, AuthExchangeCode

AVATAR_COLORS = ["#3B82F6", "#10B981", "#8B5CF6", "#F59E0B", "#EF4444", "#06B6D4"]


def _naive_utc(dt: datetime | None = None) -> datetime:
    """SQLite stores naive datetimes; compare consistently in UTC. Every
    current caller only ever passes an already-UTC-aware or already-naive
    value, but converting to UTC before stripping tzinfo (rather than just
    stripping) keeps this correct if that ever changes — a naive strip alone
    would silently misread a non-UTC-aware datetime as UTC."""
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def get_or_create_default_tenant(db: Session) -> Tenant:
    tenant = db.scalars(select(Tenant)).first()
    if tenant is None:
        tenant = Tenant(name="STAIL Realty", plan_tier="enterprise")
        db.add(tenant)
        db.flush()
    return tenant


def _generate_slug(db: Session, base_name: str, *, suffix: str | None = None) -> str:
    import re
    base = re.sub(r'[^a-z0-9]+', '-', base_name.lower()).strip('-')
    if not base:
        base = "company"
    if suffix:
        return f"{base}-{suffix}"
    slug = base
    n = 1
    while db.scalars(select(Tenant).where(Tenant.slug == slug)).first():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _create_tenant_with_unique_slug(db: Session, tenant_name: str) -> Tenant:
    """The obvious "check slug exists, then insert" has a TOCTOU race: two
    concurrent registrations can both see the slug free and both insert,
    and the loser gets an unhandled IntegrityError. The DB's unique
    constraint is the real source of truth here, so on a collision we roll
    back and retry with a fresh (random-suffixed on retry) slug rather than
    trusting the pre-check alone."""
    for attempt in range(5):
        suffix = new_uuid()[:8] if attempt > 0 else None
        tenant = Tenant(
            name=tenant_name, slug=_generate_slug(db, tenant_name, suffix=suffix),
            plan_tier="standard",
        )
        db.add(tenant)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            continue
        return tenant
    raise AppError(
        "Could not provision a workspace right now — please try again.",
        code="tenant_provision_failed",
    )

def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    phone: str | None,
    company_name: str | None,
    requested_role: Role | None,
    created_by: User | None = None,
    ip: str | None = None,
    send_verification: bool = True,
) -> User:
    """`send_verification=False` is for flows that deliver their own ownership-
    proving link. Team invites do: the invite email carries a set-password token,
    so also sending "verify your account" gave the invitee two emails, the first
    of which they cannot usefully act on because they have no password yet."""
    email = email.lower().strip()
    if db.scalars(select(User).where(User.email == email)).first():
        raise ConflictError("An account with this email already exists", code="email_taken")

    if created_by is None:
        # Public self-registration (e.g. from StailOS)
        # Create a new isolated tenant
        tenant_name = company_name.strip() if company_name and company_name.strip() else "My Workspace"
        tenant = _create_tenant_with_unique_slug(db, tenant_name)
        tenant_id = tenant.id
        role = Role.COMPANY_ADMIN
    else:
        # Invited by an existing user
        tenant_id = created_by.tenant_id
        role = requested_role if requested_role else Role.SALES_EXECUTIVE

    user = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        phone=phone,
        role=role.value,
        avatar_color=random.choice(AVATAR_COLORS),
    )
    db.add(user)
    db.flush()

    settings = get_settings()
    if send_verification:
        verify_token = create_token(
            user.id, "email_verify", timedelta(hours=settings.email_verification_expire_hours)
        )
        send_email(
            db,
            to=user.email,
            subject="Verify your Pappu AI CRM account",
            body=(
                f"Welcome {user.full_name}!\n\nVerify your email by opening:\n"
                f"{settings.frontend_origin}/verify-email?token={verify_token}\n\n"
                f"The link expires in {settings.email_verification_expire_hours} hours."
            ),
            category="email_verification",
        )
    record_audit(
        db,
        tenant_id=tenant_id,
        action="auth.register",
        actor_id=(created_by or user).id,
        actor_email=(created_by or user).email,
        entity_type="user",
        entity_id=user.id,
        ip_address=ip,
    )
    events.publish("user.registered", {"user_id": user.id, "email": user.email},
        db=db,
    )
    return user


def _check_lockout(db: Session, email: str) -> None:
    settings = get_settings()
    user = db.scalars(select(User).where(User.email == email)).first()
    if user and user.locked_until and _naive_utc(user.locked_until) > _naive_utc():
        raise AuthError(
            "Account temporarily locked due to failed login attempts. Try again later.",
            code="account_locked",
        )


def _register_failed_attempt(db: Session, email: str, ip: str | None) -> None:
    settings = get_settings()
    db.add(LoginAttempt(email=email, success=False, ip_address=ip))
    db.flush()
    window_start = _naive_utc() - timedelta(minutes=settings.login_attempt_window_minutes)
    recent_failures = db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.email == email,
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= window_start,
        )
    )
    if recent_failures >= settings.login_max_attempts:
        user = db.scalars(select(User).where(User.email == email)).first()
        if user:
            user.locked_until = _naive_utc() + timedelta(minutes=settings.login_lockout_minutes)
            send_email(
                db,
                to=user.email,
                subject="Account temporarily locked",
                body=(
                    f"Your account was locked for {settings.login_lockout_minutes} minutes "
                    f"after {settings.login_max_attempts} failed login attempts."
                ),
                category="security_alert",
            )
    # Must survive the AuthError raised by the caller — the request transaction
    # rolls back on error, which would otherwise erase the attempt and the lock.
    db.commit()


def login(
    db: Session, *, email: str, password: str, user_agent: str | None, ip: str | None
) -> tuple[User, str, str]:
    """Returns (user, access_token, refresh_token_plain)."""
    email = email.lower().strip()
    _check_lockout(db, email)

    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None or not verify_password(password, user.password_hash):
        _register_failed_attempt(db, email, ip)
        raise AuthError("Invalid email or password", code="invalid_credentials")
    if not user.is_active:
        raise AuthError("Account is deactivated", code="account_disabled")

    # Migrate hashes created under the old (much slower) argon2 parameters
    # to the tuned ones — the plaintext was just verified, so this is the
    # one safe moment to re-hash.
    from app.core.security import password_needs_rehash

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.locked_until = None
    user.last_login_at = _naive_utc()
    db.add(LoginAttempt(email=email, success=True, ip_address=ip))

    access = create_access_token(user.id, user.role, user.tenant_id)
    refresh_plain = _issue_refresh_token(
        db, user, family_id=new_uuid(), user_agent=user_agent, ip=ip
    )
    record_audit(
        db, tenant_id=user.tenant_id, action="auth.login", actor_id=user.id,
        actor_email=user.email, ip_address=ip,
    )
    return user, access, refresh_plain


def _issue_refresh_token(
    db: Session, user: User, *, family_id: str, user_agent: str | None, ip: str | None
) -> str:
    settings = get_settings()
    plain = generate_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_opaque_token(plain),
            family_id=family_id,
            expires_at=_naive_utc() + timedelta(days=settings.refresh_token_expire_days),
            user_agent=(user_agent or "")[:400] or None,
            ip_address=ip,
        )
    )
    return plain


def refresh_session(
    db: Session, *, refresh_token_plain: str, user_agent: str | None, ip: str | None
) -> tuple[User, str, str]:
    """Rotate the refresh token. Reuse of an already-rotated token revokes the
    whole family (stolen-token defense, PRD §7.1)."""
    token_hash = hash_opaque_token(refresh_token_plain)
    row = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).first()
    if row is None:
        raise AuthError("Invalid refresh token", code="invalid_refresh")
    if row.revoked or row.replaced_by is not None:
        family = db.scalars(
            select(RefreshToken).where(RefreshToken.family_id == row.family_id)
        ).all()
        for t in family:
            t.revoked = True
        record_audit(
            db, tenant_id=row.user.tenant_id, action="auth.refresh_reuse_detected",
            actor_id=row.user_id, entity_type="refresh_family", entity_id=row.family_id,
            ip_address=ip,
        )
        # Persist the family revocation despite the error we are about to raise.
        db.commit()
        raise AuthError("Refresh token reuse detected; session revoked", code="refresh_reuse")
    if _naive_utc(row.expires_at) < _naive_utc():
        raise AuthError("Refresh token expired", code="refresh_expired")

    user = row.user
    if not user.is_active:
        raise AuthError("Account is deactivated", code="account_disabled")

    new_plain = _issue_refresh_token(db, user, family_id=row.family_id, user_agent=user_agent, ip=ip)
    row.revoked = True
    row.replaced_by = hash_opaque_token(new_plain)[:36]
    access = create_access_token(user.id, user.role, user.tenant_id)
    return user, access, new_plain


def logout(db: Session, *, refresh_token_plain: str | None, user: User | None) -> None:
    if refresh_token_plain:
        row = db.scalars(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_opaque_token(refresh_token_plain)
            )
        ).first()
        if row:
            for t in db.scalars(
                select(RefreshToken).where(RefreshToken.family_id == row.family_id)
            ).all():
                t.revoked = True
    if user:
        record_audit(
            db, tenant_id=user.tenant_id, action="auth.logout",
            actor_id=user.id, actor_email=user.email,
        )


def forgot_password(db: Session, *, email: str) -> None:
    """Always succeeds outwardly (no account enumeration)."""
    settings = get_settings()
    user = db.scalars(select(User).where(User.email == email.lower().strip())).first()
    if user is None:
        return
    token = create_token(
        user.id, "password_reset", timedelta(minutes=settings.password_reset_expire_minutes)
    )
    send_email(
        db,
        to=user.email,
        subject="Reset your Pappu AI CRM password",
        body=(
            f"Reset your password:\n{settings.frontend_origin}/reset-password?token={token}\n\n"
            f"The link expires in {settings.password_reset_expire_minutes} minutes. "
            "If you didn't request this, ignore this email."
        ),
        category="password_reset",
    )


def reset_password(db: Session, *, token: str, new_password: str, ip: str | None) -> None:
    try:
        payload = decode_token(token, "password_reset")
    except pyjwt.InvalidTokenError:
        raise AuthError("Invalid or expired reset link", code="invalid_reset_token")
    user = db.get(User, payload["sub"])
    if user is None:
        raise NotFoundError("User not found")
    issued_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
    if user.password_changed_at and _naive_utc(user.password_changed_at) >= _naive_utc(issued_at):
        raise AuthError("This reset link has already been used", code="reset_token_used")
    user.password_hash = hash_password(new_password)
    user.password_changed_at = _naive_utc()
    # Changing the password ends every active session.
    for t in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)).all():
        t.revoked = True
    record_audit(
        db, tenant_id=user.tenant_id, action="auth.password_reset",
        actor_id=user.id, actor_email=user.email, ip_address=ip,
    )


def verify_email(db: Session, *, token: str) -> User:
    try:
        payload = decode_token(token, "email_verify")
    except pyjwt.InvalidTokenError:
        raise AuthError("Invalid or expired verification link", code="invalid_verify_token")
    user = db.get(User, payload["sub"])
    if user is None:
        raise NotFoundError("User not found")
    user.email_verified = True
    return user


def list_sessions(db: Session, user: User) -> list[RefreshToken]:
    return list(
        db.scalars(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > _naive_utc(),
            )
            .order_by(RefreshToken.created_at.desc())
        ).all()
    )


def revoke_session(db: Session, user: User, session_id: str) -> None:
    row = db.get(RefreshToken, session_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("Session not found")
    for t in db.scalars(
        select(RefreshToken).where(RefreshToken.family_id == row.family_id)
    ).all():
        t.revoked = True

def issue_exchange_code(db: Session, user: User) -> str:
    """Issue a short-lived one-time code for SSO handoff."""
    import secrets
    code = secrets.token_urlsafe(32)
    record = AuthExchangeCode(
        code=code,
        user_id=user.id,
        expires_at=_naive_utc() + timedelta(minutes=2)
    )
    db.add(record)
    db.commit()
    return code

def redeem_exchange_code(db: Session, code: str, user_agent: str | None, ip: str | None) -> tuple[User, str, str]:
    """Redeem a one-time code for an access token and refresh token."""
    record = db.scalars(select(AuthExchangeCode).where(AuthExchangeCode.code == code)).first()
    if not record:
        raise AuthError("Invalid exchange code", code="invalid_exchange_code")
    if record.used:
        raise AuthError("Exchange code already used", code="exchange_code_used")
    if _naive_utc(record.expires_at) < _naive_utc():
        raise AuthError("Exchange code expired", code="exchange_code_expired")
    
    record.used = True
    user = record.user
    if not user.is_active:
        raise AuthError("Account is deactivated", code="account_disabled")
    
    user.locked_until = None
    user.last_login_at = _naive_utc()
    db.add(LoginAttempt(email=user.email, success=True, ip_address=ip))

    access = create_access_token(user.id, user.role, user.tenant_id)
    refresh_plain = _issue_refresh_token(
        db, user, family_id=new_uuid(), user_agent=user_agent, ip=ip
    )
    record_audit(
        db, tenant_id=user.tenant_id, action="auth.exchange_redeem", actor_id=user.id,
        actor_email=user.email, ip_address=ip,
    )
    db.commit()
    return user, access, refresh_plain
