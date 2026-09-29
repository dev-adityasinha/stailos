"""Auth domain: tenants, users, refresh-token sessions, login attempts, email outbox."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    plan_tier: Mapped[str] = mapped_column(String(50), default="standard")
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    onboarding_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role: Mapped[str] = mapped_column(String(50), index=True)
    manager_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    avatar_color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="users")
    manager: Mapped["User | None"] = relationship(remote_side="User.id")


class RefreshToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per issued refresh token. A `family_id` groups rotations of the
    same login session; reuse of a revoked token revokes the whole family
    (PRD §7.1 refresh-rotation reuse detection)."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    replaced_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship()


class LoginAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "login_attempts"

    email: Mapped[str] = mapped_column(String(255), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)


class EmailOutbox(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Development mailbox: every outbound email (verification, reset, alerts)
    is persisted here. An SMTP provider can replace the console sender via env
    config without touching calling code."""

    __tablename__ = "email_outbox"

    to_email: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(String(5000))
    category: Mapped[str] = mapped_column(String(50), index=True)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)


class AuthExchangeCode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One-time exchange code for cross-domain SSO."""

    __tablename__ = "auth_exchange_codes"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    
    user: Mapped[User] = relationship()
