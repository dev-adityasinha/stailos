"""Pappu AI CRM — application factory."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import RateLimitError, register_error_handlers
from app.core.ratelimit import check_rate_limit
from app.core.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("crm.startup")


def import_all_models() -> None:
    """Import every module's models so Base.metadata knows all tables."""
    from app.core import audit  # noqa: F401
    from app.core import whatsapp as whatsapp_models  # noqa: F401
    from app.modules.auth import models  # noqa: F401
    from app.modules.ai import models as ai_models  # noqa: F401
    from app.modules.bookings import models as booking_models  # noqa: F401
    from app.modules.documents import models as document_models  # noqa: F401
    from app.modules.calendar import models as calendar_models  # noqa: F401
    from app.modules.events import models as event_models  # noqa: F401
    from app.modules.customers import models as customer_models  # noqa: F401
    from app.modules.leads import models as lead_models  # noqa: F401
    from app.modules.notifications import models as notification_models  # noqa: F401
    from app.modules.properties import models as property_models  # noqa: F401
    from app.modules.tasks import models as task_models  # noqa: F401
    from app.modules.timeline import models as timeline_models  # noqa: F401
    # Later phases append their model imports here.


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_production and not settings.cookie_secure:
        logger.warning(
            "ENVIRONMENT=production but COOKIE_SECURE is not set — refresh-token "
            "cookies will be sent over plain HTTP. Set COOKIE_SECURE=true once "
            "the app is served behind HTTPS."
        )
    if settings.email_provider == "smtp" and not settings.smtp_host:
        logger.warning(
            "EMAIL_PROVIDER=smtp but SMTP_HOST is not set — emails will not be "
            "delivered (console-only outbox record instead)."
        )
    if settings.error_monitoring_provider == "sentry":
        if settings.sentry_dsn:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.environment,
                traces_sample_rate=0.1,
            )
        else:
            logger.warning(
                "ERROR_MONITORING_PROVIDER=sentry but SENTRY_DSN is not set — "
                "exceptions will only be logged locally."
            )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        start_scheduler()
        yield
        shutdown_scheduler()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, settings.stailos_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def enforce_https(request: Request, call_next):
        # Free hosts (Render/Vercel/Fly) terminate TLS at their proxy and
        # forward plain HTTP with X-Forwarded-Proto set — redirect any request
        # that reaches us as "http" back out over https instead of serving it.
        if settings.is_production and request.headers.get("x-forwarded-proto") == "http":
            url = request.url.replace(scheme="https")
            return JSONResponse(
                status_code=status.HTTP_308_PERMANENT_REDIRECT,
                content={},
                headers={"Location": str(url)},
            )
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )
        return response

    @app.middleware("http")
    async def auth_rate_limit(request: Request, call_next):
        # Public, unauthenticated POST endpoints — auth flows and event
        # registration — are the only spots without RBAC to lean on, so they
        # get an explicit rate limit instead.
        is_public_event_write = (
            request.url.path.startswith("/api/v1/events/public/") and request.method == "POST"
        )
        if request.url.path.startswith("/api/v1/auth") and request.method == "POST":
            bucket = "auth"
            limit, window = settings.auth_rate_limit_requests, settings.auth_rate_limit_window_seconds
        elif is_public_event_write:
            bucket = "event_public"
            limit, window = (
                settings.event_public_rate_limit_requests,
                settings.event_public_rate_limit_window_seconds,
            )
        else:
            bucket = None
        if bucket:
            try:
                check_rate_limit(request, bucket, limit, window)
            except RateLimitError as exc:
                # Middleware exceptions bypass FastAPI handlers; respond directly.
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"error": {"code": exc.code, "message": exc.message}},
                )
        return await call_next(request)

    register_error_handlers(app)

    from app.modules.auth.audit_router import router as audit_router
    from app.modules.auth.router import api_keys_router
    from app.modules.auth.router import router as auth_router
    from app.modules.auth.router import users_router
    from app.modules.leads.router import pipeline_router
    from app.modules.leads.router import router as leads_router

    from app.modules.bookings.router import router as bookings_router
    from app.modules.customers.router import convert_router
    from app.modules.customers.router import router as customers_router
    from app.modules.events.router import router as events_router
    from app.modules.properties.router import router as properties_router
    from app.modules.onboarding.router import router as onboarding_router

    api_prefix = "/api/v1"
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(onboarding_router, prefix=api_prefix)
    app.include_router(users_router, prefix=api_prefix)
    app.include_router(api_keys_router, prefix=api_prefix)
    app.include_router(leads_router, prefix=api_prefix)
    app.include_router(pipeline_router, prefix=api_prefix)
    from app.modules.calendar.router import router as calendar_router
    from app.modules.notifications.router import router as notifications_router
    from app.modules.notifications.service import register_subscribers
    from app.modules.tasks.router import router as tasks_router

    app.include_router(customers_router, prefix=api_prefix)
    app.include_router(convert_router, prefix=api_prefix)
    app.include_router(properties_router, prefix=api_prefix)
    app.include_router(bookings_router, prefix=api_prefix)
    app.include_router(events_router, prefix=api_prefix)
    from app.modules.ai.router import router as ai_router
    from app.modules.ai.router import timeline_router
    from app.modules.analytics.router import router as analytics_router
    from app.modules.documents.router import router as documents_router
    from app.modules.reports.router import router as reports_router

    app.include_router(tasks_router, prefix=api_prefix)
    app.include_router(calendar_router, prefix=api_prefix)
    app.include_router(notifications_router, prefix=api_prefix)
    app.include_router(ai_router, prefix=api_prefix)
    app.include_router(timeline_router, prefix=api_prefix)
    app.include_router(analytics_router, prefix=api_prefix)
    app.include_router(reports_router, prefix=api_prefix)
    app.include_router(documents_router, prefix=api_prefix)
    app.include_router(audit_router, prefix=api_prefix)
    register_subscribers()
    # Later phases mount their routers here.

    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": settings.app_name}

    import_all_models()
    _init_schema()

    return app


def _add_missing_columns(conn) -> None:
    """Additive schema shim: ``create_all()`` only creates missing *tables*,
    never missing *columns* — so any column added to an existing model (e.g.
    event_registrations.reminder_48h_sent_at, tenants.onboarding_data) would
    crash every SELECT against a database created before it existed. Until
    the project moves to Alembic (documented MVP boundary), this issues
    conservative ``ALTER TABLE … ADD COLUMN`` (nullable, no constraints) for
    any model column missing from an existing table, then backfills simple
    scalar Python-side defaults so old rows behave like new ones.
    """
    import logging

    from sqlalchemy import inspect, text

    from app.db.base import Base

    logger = logging.getLogger("crm.schema")
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all handles brand-new tables
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            col_type = col.type.compile(dialect=conn.dialect)
            conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}'))
            logger.info("schema shim: added %s.%s (%s)", table.name, col.name, col_type)
            default = getattr(col.default, "arg", None)
            if isinstance(default, (bool, int, float, str)):
                conn.execute(
                    text(f"UPDATE {table.name} SET {col.name} = :d WHERE {col.name} IS NULL"),
                    {"d": default},
                )


def _init_schema() -> None:
    """Create missing tables (and additively, missing columns), safely under
    multiple uvicorn workers.

    ``create_all()`` does a reflect-then-CREATE that is not atomic, so two
    workers booting together can race and one crashes with "table already
    exists". On Postgres (production) a transaction-scoped advisory lock
    serializes the workers; on SQLite (single-process dev/test) we retry once
    if a race ever slips through.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError, ProgrammingError

    from app.db.base import Base, engine

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(917283645)"))
            Base.metadata.create_all(bind=conn)
            _add_missing_columns(conn)
        return
    try:
        Base.metadata.create_all(bind=engine)
    except (OperationalError, ProgrammingError):
        Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        _add_missing_columns(conn)


app = create_app()
