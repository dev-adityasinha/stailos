"""Role-based access control: role → resource → action → scope.

Scopes: ALL (tenant-wide) > TEAM (manager's team) > OWN (records owned/assigned
to the user). Absence of an entry means the action is denied.
"""
from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    COMPANY_ADMIN = "company_admin"
    SALES_MANAGER = "sales_manager"
    SALES_EXECUTIVE = "sales_executive"
    TELECALLER = "telecaller"
    MARKETING_EXECUTIVE = "marketing_executive"
    CHANNEL_PARTNER = "channel_partner"
    CUSTOMER_SUPPORT = "customer_support"


class Scope(StrEnum):
    ALL = "all"
    TEAM = "team"
    OWN = "own"


READ = "read"
CREATE = "create"
UPDATE = "update"
DELETE = "delete"
ASSIGN = "assign"
EXPORT = "export"

_CRUD_ALL = {READ: Scope.ALL, CREATE: Scope.ALL, UPDATE: Scope.ALL, DELETE: Scope.ALL,
             ASSIGN: Scope.ALL, EXPORT: Scope.ALL}
_CRUD_TEAM = {READ: Scope.TEAM, CREATE: Scope.TEAM, UPDATE: Scope.TEAM, DELETE: Scope.TEAM,
              ASSIGN: Scope.TEAM, EXPORT: Scope.TEAM}
_CRUD_OWN = {READ: Scope.OWN, CREATE: Scope.OWN, UPDATE: Scope.OWN, DELETE: Scope.OWN}

_ADMIN_RESOURCES = [
    "users", "leads", "customers", "properties", "bookings", "payments", "tasks",
    "calendar", "analytics", "reports", "documents", "notifications", "audit", "ai", "events",
]

PERMISSIONS: dict[Role, dict[str, dict[str, Scope]]] = {
    Role.SUPER_ADMIN: {r: dict(_CRUD_ALL) for r in _ADMIN_RESOURCES},
    Role.COMPANY_ADMIN: {r: dict(_CRUD_ALL) for r in _ADMIN_RESOURCES},
    Role.SALES_MANAGER: {
        "users": {READ: Scope.TEAM},
        "leads": dict(_CRUD_TEAM),
        "customers": dict(_CRUD_TEAM),
        "properties": {READ: Scope.ALL},
        "bookings": dict(_CRUD_TEAM),
        "payments": {READ: Scope.TEAM},
        "tasks": dict(_CRUD_TEAM),
        "calendar": dict(_CRUD_TEAM),
        "analytics": {READ: Scope.TEAM},
        "reports": {READ: Scope.TEAM, CREATE: Scope.TEAM, EXPORT: Scope.TEAM},
        "documents": dict(_CRUD_TEAM),
        "notifications": {READ: Scope.OWN, UPDATE: Scope.OWN},
        "ai": {READ: Scope.TEAM, CREATE: Scope.TEAM},
        "events": {READ: Scope.ALL, CREATE: Scope.ALL, UPDATE: Scope.ALL},
    },
    Role.SALES_EXECUTIVE: {
        "leads": {**_CRUD_OWN, READ: Scope.TEAM, EXPORT: Scope.OWN},
        "customers": dict(_CRUD_OWN),
        "properties": {READ: Scope.ALL, UPDATE: Scope.OWN},  # update = shortlist/favourite
        "bookings": {CREATE: Scope.OWN, READ: Scope.OWN, UPDATE: Scope.OWN},
        "payments": {READ: Scope.OWN},
        "tasks": dict(_CRUD_OWN),
        "calendar": dict(_CRUD_OWN),
        "analytics": {READ: Scope.OWN},
        "reports": {READ: Scope.OWN, CREATE: Scope.OWN, EXPORT: Scope.OWN},
        "documents": dict(_CRUD_OWN),
        "notifications": {READ: Scope.OWN, UPDATE: Scope.OWN},
        "ai": {READ: Scope.OWN, CREATE: Scope.OWN},
        "events": {READ: Scope.ALL, UPDATE: Scope.ALL},  # view + check-in at the venue
    },
    Role.TELECALLER: {
        "leads": {CREATE: Scope.OWN, READ: Scope.OWN, UPDATE: Scope.OWN},
        "customers": {READ: Scope.OWN},
        "properties": {READ: Scope.ALL},
        "tasks": dict(_CRUD_OWN),
        "calendar": dict(_CRUD_OWN),
        "analytics": {READ: Scope.OWN},
        "reports": {READ: Scope.OWN, CREATE: Scope.OWN, EXPORT: Scope.OWN},
        "documents": {READ: Scope.OWN},
        "notifications": {READ: Scope.OWN, UPDATE: Scope.OWN},
        "ai": {READ: Scope.OWN, CREATE: Scope.OWN},
    },
    Role.MARKETING_EXECUTIVE: {
        "leads": {READ: Scope.ALL, UPDATE: Scope.ALL},  # update limited to source fields in service
        "customers": {READ: Scope.ALL},
        "properties": {READ: Scope.ALL},
        "tasks": dict(_CRUD_OWN),
        "calendar": dict(_CRUD_OWN),
        "analytics": {READ: Scope.ALL},
        "reports": {READ: Scope.ALL, CREATE: Scope.ALL, EXPORT: Scope.ALL},
        "documents": {READ: Scope.ALL},
        "notifications": {READ: Scope.OWN, UPDATE: Scope.OWN},
        "ai": {READ: Scope.ALL, CREATE: Scope.ALL},
        "events": {READ: Scope.ALL, CREATE: Scope.ALL, UPDATE: Scope.ALL},  # owns campaigns/CMS
    },
    Role.CHANNEL_PARTNER: {
        "leads": {CREATE: Scope.OWN, READ: Scope.OWN},
        "properties": {READ: Scope.ALL},
        "bookings": {READ: Scope.OWN},
        "analytics": {READ: Scope.OWN},
        "notifications": {READ: Scope.OWN, UPDATE: Scope.OWN},
        "ai": {READ: Scope.OWN, CREATE: Scope.OWN},
    },
    Role.CUSTOMER_SUPPORT: {
        "leads": {READ: Scope.ALL},
        "customers": {READ: Scope.ALL, UPDATE: Scope.ALL},  # update limited to notes in service
        "properties": {READ: Scope.ALL},
        "bookings": {READ: Scope.ALL},
        "tasks": dict(_CRUD_OWN),
        "calendar": dict(_CRUD_OWN),
        "documents": {READ: Scope.ALL},
        "notifications": {READ: Scope.OWN, UPDATE: Scope.OWN},
        "ai": {READ: Scope.ALL, CREATE: Scope.ALL},
    },
}

ADMIN_ROLES = {Role.SUPER_ADMIN, Role.COMPANY_ADMIN}
MANAGER_ROLES = ADMIN_ROLES | {Role.SALES_MANAGER}


def granted_actions(role: Role | str) -> dict[str, list[str]]:
    """resource → actions this role may perform at any scope. Sent to the
    frontend so it hides what the server would refuse, from the same table."""
    return {res: sorted(acts) for res, acts in PERMISSIONS.get(Role(role), {}).items()}


def get_scope(role: Role | str, resource: str, action: str) -> Scope | None:
    """Return the widest scope this role has for resource:action, or None if denied."""
    return PERMISSIONS.get(Role(role), {}).get(resource, {}).get(action)
