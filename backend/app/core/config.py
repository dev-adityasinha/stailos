"""Application settings, loaded from environment / .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Pappu AI CRM"
    environment: str = "development"  # development | staging | production

    # Security
    secret_key: str  # required — no default so it can never ship with a known key
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    password_reset_expire_minutes: int = 15
    email_verification_expire_hours: int = 48
    login_max_attempts: int = 5
    login_attempt_window_minutes: int = 10
    login_lockout_minutes: int = 15

    # IP-based rate limits on unauthenticated write endpoints (main.py's
    # auth_rate_limit middleware). Env-overridable so CI running many
    # browsers' worth of e2e register/login calls against one shared
    # backend can raise the ceiling without weakening the production default.
    auth_rate_limit_requests: int = 20
    auth_rate_limit_window_seconds: int = 60
    event_public_rate_limit_requests: int = 10
    event_public_rate_limit_window_seconds: int = 600

    # Database — SQLite by default; set DATABASE_URL for PostgreSQL
    database_url: str = f"sqlite:///{BACKEND_DIR / 'crm.db'}"

    # Email delivery: "console" (outbox table + logs only), "smtp" or "brevo"
    email_provider: str = "console"
    email_from: str = "Pappu AI CRM <no-reply@example.com>"

    # Brevo transactional API (used when email_provider="brevo"). HTTP-based,
    # so it works on hosts that block outbound SMTP ports. The EMAIL_FROM
    # address must be a verified sender in the Brevo account.
    brevo_api_key: str | None = None

    # SMTP delivery (used when email_provider="smtp")
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True

    # CORS
    frontend_origin: str = "http://localhost:3000"
    stailos_origin: str = "http://localhost:5173"

    # Cookies
    cookie_secure: bool = False  # True behind HTTPS in production
    cookie_domain: str | None = None

    # File storage
    storage_dir: Path = BACKEND_DIR / "storage" / "uploads"
    max_upload_mb: int = 20

    # AI provider:
    #   "mock"     — deterministic rule-based output (default; no key, no cost)
    #   "llm"      — real generation via an OpenAI-compatible endpoint (see ai_llm_*)
    #   "external" — proxy to a running STAIL Realty OS agent service
    # Anything misconfigured falls back to "mock" with a startup/request warning
    # rather than breaking every AI widget.
    ai_provider: str = "mock"
    ai_provider_base_url: str | None = None
    ai_provider_token: str | None = None  # bearer token for the external agent service

    # LLM settings (ai_provider="llm"). The default base URL is Groq's, because
    # that is what the STAIL agents use and it is OpenAI-compatible — any other
    # compatible gateway works by pointing ai_llm_base_url at it.
    ai_llm_api_key: str | None = None
    ai_llm_base_url: str = "https://api.groq.com/openai/v1"
    ai_llm_model: str = "llama-3.1-8b-instant"
    ai_llm_timeout_seconds: float = 20.0

    # Property integration: "internal" (own inventory) or external API base URL
    property_provider: str = "internal"
    property_provider_base_url: str | None = None

    # Lead auto-assignment: workload-balanced across active users with these roles
    lead_auto_assign_enabled: bool = True
    lead_auto_assign_roles: list[str] = ["sales_executive", "telecaller"]

    # Reminder engine: how often the background scheduler scans for due reminders
    reminder_interval_minutes: int = 5
    reminder_scheduler_enabled: bool = True

    # Post-event follow-up automation: how often to check for events whose
    # end_at has passed and dispatch attended/no-show sequences
    event_followup_interval_minutes: int = 60

    # Error monitoring: "none" or "sentry"
    error_monitoring_provider: str = "none"
    sentry_dsn: str | None = None

    # WhatsApp delivery: "console" (outbox table + logs only) or "meta_cloud"
    # (WhatsApp Cloud API — free tier, 1000 conversations/month)
    whatsapp_provider: str = "console"
    whatsapp_phone_number_id: str | None = None
    whatsapp_access_token: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
