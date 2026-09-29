"""Password hashing, JWT issuance/verification, token helpers."""
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

# argon2-cffi defaults (t=3, m=64MiB, p=4) are tuned for dedicated modern
# CPUs; on a small shared instance (Render free tier: ~0.1 vCPU, 512MB,
# multiple workers) they make every login/register take seconds and add
# real memory pressure. OWASP's recommended minimum configuration
# (m=19456 KiB, t=2, p=1) keeps hashes strong while staying fast on small
# hardware. Old hashes still verify (params live inside the hash string)
# and are transparently upgraded on next successful login via
# needs_rehash().
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

PASSWORD_POLICY_MESSAGE = (
    "Password must be at least 10 characters and include an uppercase letter, "
    "a number, and a symbol."
)


def validate_password_strength(password: str) -> bool:
    return bool(
        len(password) >= 10
        and re.search(r"[A-Z]", password)
        and re.search(r"[0-9]", password)
        and re.search(r"[^A-Za-z0-9]", password)
    )


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when the stored hash predates the current parameters — callers
    should re-hash with the (verified) plaintext on successful login so old
    expensive hashes migrate to the tuned parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return False


def create_token(
    subject: str,
    token_type: Literal["access", "email_verify", "password_reset"],
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid.uuid4().hex,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_access_token(user_id: str, role: str, tenant_id: str) -> str:
    settings = get_settings()
    return create_token(
        user_id,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        {"role": role, "tenant_id": tenant_id},
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises jwt.InvalidTokenError on any problem."""
    settings = get_settings()
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


def generate_opaque_token() -> str:
    """Opaque token for refresh tokens — only its hash is stored server-side."""
    return secrets.token_urlsafe(48)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
