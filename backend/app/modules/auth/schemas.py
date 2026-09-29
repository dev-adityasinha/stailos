from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.permissions import Role
from app.core.security import PASSWORD_POLICY_MESSAGE, validate_password_strength


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    company_name: str | None = Field(default=None, max_length=200)
    # Role is accepted at registration only for the first (bootstrap) user or
    # when created by an admin; self-registration defaults to sales_executive.
    role: Role | None = None

    @field_validator("password")
    @classmethod
    def _strong(cls, v: str) -> str:
        if not validate_password_strength(v):
            raise ValueError(PASSWORD_POLICY_MESSAGE)
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class RefreshRequest(BaseModel):
    refresh_token: str | None = None  # falls back to httpOnly cookie


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _strong(cls, v: str) -> str:
        if not validate_password_strength(v):
            raise ValueError(PASSWORD_POLICY_MESSAGE)
        return v


class VerifyEmailRequest(BaseModel):
    token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    phone: str | None
    role: Role
    manager_id: str | None
    is_active: bool
    email_verified: bool
    avatar_color: str | None
    last_login_at: datetime | None
    created_at: datetime
    # Tenant context, populated only on auth responses (me/login/refresh/
    # exchange) — optional so plain UserOut.model_validate(user) call sites
    # (user lists etc.) keep working without a tenant lookup.
    tenant_name: str | None = None
    onboarding_completed: bool | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    manager_id: str | None = None
    is_active: bool | None = None


class RoleUpdate(BaseModel):
    role: Role


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    family_id: str
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime
    revoked: bool

class ExchangeRedeemRequest(BaseModel):
    code: str

class ExchangeIssueResponse(BaseModel):
    code: str
