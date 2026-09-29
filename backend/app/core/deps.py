"""Shared FastAPI dependencies: DB session, current user, RBAC enforcement."""
from dataclasses import dataclass
from typing import Generator

import jwt as pyjwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AuthError, PermissionDeniedError
from app.core.permissions import MANAGER_ROLES, Role, Scope, get_scope
from app.core.security import decode_token, hash_opaque_token, is_api_key
from app.db.base import SessionLocal, utcnow
from app.modules.auth.models import ApiKey, User

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """Request-wide session, committed when the endpoint returns.

    Always depend on it as ``Depends(get_db, scope="function")``. With the
    default request scope FastAPI runs the code after ``yield`` only once the
    response has been sent, so the client could read stale data (or be told a
    write succeeded whose commit then failed). Every use must share the same
    scope, or one request gets two separate sessions.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _touch(api_key_id: str) -> None:
    """Record that a key was used, in its own committed transaction.

    Deliberately not on the request's session. That session is rolled back
    whenever the endpoint raises, so writing there meant the timestamp survived
    only on success: a key used exclusively for requests that fail - RBAC
    denials, probing for endpoints it cannot reach - reported "never used",
    which is the one signal an admin reads when deciding whether a key is
    dormant or being attacked.

    Swallows everything. Recording use must never be the reason a request fails.
    """
    try:
        with SessionLocal() as session:
            session.query(ApiKey).filter(ApiKey.id == api_key_id).update(
                {"last_used_at": utcnow()}, synchronize_session=False
            )
            session.commit()
    except Exception:  # noqa: BLE001 - telemetry must not break authentication
        pass


def _user_from_api_key(db: Session, key: str) -> User:
    """Resolve an API key to the user it acts as.

    Deliberately resolves to a User rather than to some parallel "machine
    identity". Every rule in permissions.py, every tenant filter and every
    scoped query then applies unchanged, with no second authorization path that
    could drift out of step with the first.
    """
    row = db.scalars(select(ApiKey).where(ApiKey.key_hash == hash_opaque_token(key))).first()
    # One message for unknown and for revoked. Whoever holds a key that does not
    # work cannot act on the difference between them.
    if row is None or row.revoked_at is not None:
        raise AuthError("Invalid API key", code="invalid_api_key")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AuthError("User inactive or not found")
    _touch(row.id)
    return user


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db, scope="function"),
) -> User:
    if credentials is None:
        raise AuthError("Not authenticated")
    # Both arrive as `Authorization: Bearer ...`; the prefix says which is which.
    # How the caller authenticated is recorded because it changes what they may
    # do: see get_interactive_user below.
    if is_api_key(credentials.credentials):
        request.state.auth_method = "api_key"
        return _user_from_api_key(db, credentials.credentials)
    request.state.auth_method = "session"
    try:
        payload = decode_token(credentials.credentials, "access")
    except pyjwt.ExpiredSignatureError:
        raise AuthError("Token expired", code="token_expired")
    except pyjwt.InvalidTokenError:
        raise AuthError("Invalid token")
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise AuthError("User inactive or not found")
    return user


def get_interactive_user(
    request: Request, user: User = Depends(get_current_user)
) -> User:
    """Authenticate, but refuse a caller holding only an API key.

    An API key acts as its user, which is right for doing that user's work and
    wrong for changing who that user is. Without this, a key is strictly more
    powerful than the credential it was issued from:

      * /auth/exchange/issue would hand a key holder a code redeemable, on an
        endpoint that needs no auth at all, for a JWT and a 7-day rotating
        refresh family. Revoking the key does not touch that family, so the
        session outlives the credential that created it and renews itself
        indefinitely, invisible in the API-keys list.
      * creating keys or users would let a key mint its own successors, so
        revoking the leaked one closes nothing.

    Those are the paths that mint credentials or identities. They stay with the
    person, at a keyboard, holding a password. Everything else - reading and
    writing the tenant's actual data - an API key may do.
    """
    if getattr(request.state, "auth_method", None) == "api_key":
        raise PermissionDeniedError(
            "an API key cannot be used here; sign in with your account for this action"
        )
    return user


@dataclass
class AccessContext:
    user: User
    scope: Scope

    @property
    def is_admin(self) -> bool:
        return Role(self.user.role) in MANAGER_ROLES


def team_user_ids(db: Session, user: User) -> list[str]:
    """User ids visible under TEAM scope: self + direct reports + own manager's team."""
    ids = {user.id}
    reports = db.scalars(select(User.id).where(User.manager_id == user.id)).all()
    ids.update(reports)
    if user.manager_id:
        siblings = db.scalars(select(User.id).where(User.manager_id == user.manager_id)).all()
        ids.update(siblings)
        ids.add(user.manager_id)
    return list(ids)


def require(resource: str, action: str):
    """Route dependency enforcing RBAC; yields the user plus granted scope."""

    def dependency(user: User = Depends(get_current_user)) -> AccessContext:
        scope = get_scope(user.role, resource, action)
        if scope is None:
            raise PermissionDeniedError(
                f"Role '{user.role}' cannot perform {resource}:{action}"
            )
        return AccessContext(user=user, scope=scope)

    return dependency


def get_client_ip(request: Request) -> str | None:
    if request.client:
        return request.client.host
    return None
