# Deployment Notes

## Environments

| | Dev | Production |
|---|---|---|
| Database | SQLite (`backend/crm.db`, zero-config) | PostgreSQL 16 (`DATABASE_URL`) |
| Servers | `uvicorn --reload` + `next dev` | Docker Compose (Postgres + API + Web) or K8s |
| Secrets | `backend/.env` (generated, git-ignored) | Injected env vars / secret manager |
| Email | Console + `email_outbox` table | `EMAIL_PROVIDER=brevo` (or `smtp`) |
| Rate limiting | In-memory per-process | Move to Redis (interface in `app/core/ratelimit.py`) |

## Backend environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SECRET_KEY` | **yes** | — | `openssl rand -hex 32`; no default by design |
| `DATABASE_URL` | no | SQLite file | e.g. `postgresql+psycopg://crm:crm@db:5432/pappu_crm` |
| `ENVIRONMENT` | no | `development` | `production` enables HSTS |
| `FRONTEND_ORIGIN` | no | `http://localhost:3000` | CORS + email link base |
| `COOKIE_SECURE` | no | `false` | set `true` behind HTTPS |
| `AI_PROVIDER` | no | `mock` | `mock` \| `llm` \| `external`; anything misconfigured falls back to `mock` with a warning |
| `AI_LLM_API_KEY` / `AI_LLM_BASE_URL` / `AI_LLM_MODEL` | if `llm` | — / Groq / `llama-3.1-8b-instant` | any OpenAI-compatible `/chat/completions` gateway |
| `AI_PROVIDER_BASE_URL` / `AI_PROVIDER_TOKEN` | if `external` | — | STAIL Realty OS agent service base URL |
| `PROPERTY_PROVIDER` / `PROPERTY_PROVIDER_BASE_URL` | no | `internal` | external property API seam |
| `MAX_UPLOAD_MB` | no | `20` | file upload cap |
| `EMAIL_PROVIDER` | no | `console` | `console` \| `brevo` \| `smtp` |
| `BREVO_API_KEY` | if `brevo` | — | Brevo transactional API key (app.brevo.com → Settings → API keys); `EMAIL_FROM` must be a verified sender in the Brevo account |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_USE_TLS` | if `smtp` | port `587`, TLS `true` | any standard SMTP server (Gmail with an App Password, Office 365, etc.) |
| `LEAD_AUTO_ASSIGN_ENABLED` / `LEAD_AUTO_ASSIGN_ROLES` | no | `true` / `["sales_executive","telecaller"]` | workload-balanced auto-assignment on lead create/import |
| `REMINDER_INTERVAL_MINUTES` / `REMINDER_SCHEDULER_ENABLED` | no | `5` / `true` | in-process APScheduler sweep for due tasks/events |
| `ERROR_MONITORING_PROVIDER` / `SENTRY_DSN` | no | `none` | set to `sentry` + a free-tier DSN (sentry.io, 5k events/mo) for exception tracking |
| `WHATSAPP_PROVIDER` | no | `console` | `console` \| `meta_cloud` |
| `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_ACCESS_TOKEN` | if `meta_cloud` | — | WhatsApp Cloud API (Meta's free tier, 1000 conversations/mo) — event registration confirmations/reminders/follow-ups |
| `EVENT_FOLLOWUP_INTERVAL_MINUTES` | no | `60` | how often the scheduler checks for events past `end_at` needing post-event follow-up |

Frontend: `NEXT_PUBLIC_API_BASE` (build-time), e.g. `https://api.example.com/api/v1`.
Optional: `NEXT_PUBLIC_SENTRY_DSN` enables client-side error reporting (no-op if unset).
Optional (public event landing pages only, no-op if unset): `NEXT_PUBLIC_GA4_ID`, `NEXT_PUBLIC_META_PIXEL_ID`, `NEXT_PUBLIC_GOOGLE_ADS_ID` / `NEXT_PUBLIC_GOOGLE_ADS_CONVERSION_LABEL`.

## Production checklist

- [x] `ENVIRONMENT=production` enforces HTTPS redirects (`enforce_https` middleware) and HSTS
- [ ] `SECRET_KEY` from a secret manager; rotate on incident
- [ ] `COOKIE_SECURE=true`; TLS termination is free via Render/Vercel/Fly's automatic Let's Encrypt certs on custom domains — no in-app cert handling needed
- [ ] PostgreSQL with backups; run schema creation on first boot (tables auto-create; move to Alembic migrations before the first breaking schema change)
- [x] Backups: `.github/workflows/backup.yml` runs `scripts/backup_db.sh` (pg_dump + gzip) daily as a free GitHub Actions artifact. Set the `DATABASE_URL` repo secret to enable it. If using Neon/Supabase, their free tiers already include point-in-time recovery — this is a second, independent layer.
- [ ] Object storage: swap `app/core/storage.py` local adapter for S3 (same interface)
- [x] Email: `EMAIL_PROVIDER=brevo` + `BREVO_API_KEY` (HTTP API, works where outbound SMTP is blocked; 300 emails/day free) — `smtp` remains available for any standard SMTP host
- [ ] Rate limiter + notification event bus → Redis when running >1 API replica
- [x] Log aggregation: app logs are stdout with unhandled exceptions now logged via `logger.exception` (previously silently swallowed); error responses carry `correlation_id`. Ship stdout to your collector, or set `ERROR_MONITORING_PROVIDER=sentry` for a free hosted alternative.
- [x] Cron/worker: `generate_due_reminders` now runs on an in-process APScheduler job (`REMINDER_INTERVAL_MINUTES`, default 5) in addition to the lazy on-request path, and emails each reminder via `core/email.py`. Move to Celery beat / K8s CronJob only once running >1 API replica (APScheduler is per-process).
- [x] CI: `.github/workflows/ci.yml` runs backend pytest, frontend lint/build, and cross-browser (Chromium/Firefox/WebKit) Playwright e2e on every PR
- [x] Deploy automation: `.github/workflows/deploy.yml` triggers Render/Vercel's free deploy-hook URLs on push to `main` — see `render.yaml` / `frontend/vercel.json` for the blueprint configs

## Known MVP boundaries (documented, intentional)

- Single-tenant seeded; every table carries `tenant_id` so multi-tenant activation is a provisioning + JWT-claim change, not a remodel (PRD §4.3).
- OAuth/SSO, MFA, and device fingerprinting from PRD §7.1 are deferred (email/password + sessions implemented); the auth module isolates where they land.
- AI ships on the deterministic provider by default. `AI_PROVIDER=llm` (+ a Groq or other OpenAI-compatible key) turns on real generation; `AI_PROVIDER=external` proxies to a running STAIL agent service. All three return identical schemas, and scores stay engine-computed under every one.
- Uploaded files live on local disk under `STORAGE_DIR`. `docker-compose.yml` mounts a named volume for this; on Render's free tier the filesystem is ephemeral, so point `STORAGE_DIR` at a persistent disk (or swap `app/core/storage.py` for S3) before relying on onboarding document uploads in production.
- Browser push uses polling + the Notification API; WebSocket/Web-Push channel is a drop-in behind the same notifications table.
