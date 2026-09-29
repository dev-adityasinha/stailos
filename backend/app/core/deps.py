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
from app.core.security import decode_token
from app.db.base import SessionLocal
from app.modules.auth.models import User

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AuthError("Not authenticated")
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
