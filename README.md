# Pappu AI — Intelligent Real Estate CRM

AI-native CRM MVP for STAIL Realty OS, built to the specs in
[`pappu-ai-crm-prd.md`](pappu-ai-crm-prd.md) and [`task_list_zaid.md`](task_list_zaid.md).

**Stack:** FastAPI (Python) · SQLAlchemy 2 · Next.js 16 + TypeScript + Tailwind v4 ·
JWT auth with rotating refresh tokens · SQLite (dev) / PostgreSQL 16 (prod).

## Modules delivered

Authentication with 8-role RBAC · User management · Lead management (CRUD, CSV
import/export, tags, notes, assignment) · 9-stage Kanban pipeline with drag &
drop · Duplicate detection (normalized phone / email / fuzzy name with
create-anyway prompt) · Customer 360 profiles + lead conversion · Property
inventory (browse, shortlist, favourite, attach, compare; provider seam for
external property APIs) · Booking workflow (Site Visit → Booking →
Documentation → Payment → Possession) with payments, receipts and stage
history · Task management with comments & attachments · Calendar with team
view · Notification center (in-app + event-driven alerts + due-soon
reminders) · AI layer — 7 widgets + 8 components behind a pluggable provider
(deterministic mock now, external agent service later) · Timeline
intelligence with filtering · Analytics dashboards (live, auto-refreshing) ·
Reports (CSV / Excel / PDF, incl. campaign ROI) · Document management with
version tracking · Immutable audit log · Workload-balanced lead
auto-assignment · Lead pipeline stage history with reopen guard · Site-visit
scheduler with calendar events + ICS email invites · Scheduled reminder
engine (in-app + email) · Sentry-ready error monitoring · HTTPS enforcement ·
cross-browser (Chromium/Firefox/WebKit) e2e suite · CI/CD + scheduled DB
backups via GitHub Actions · **Events module** — public event landing pages
(GA4/Meta Pixel/Google Ads-ready) with registration that auto-creates a
scored/assigned CRM Lead, WhatsApp + email RSVP confirmations, QR check-in
with camera scanning, printable PDF badges, referral tracking, a
speakers/agenda CMS, live registration/CPL dashboards, and automated
post-event follow-up sequences.

## Quick start (local dev)

Backend:

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
printf 'SECRET_KEY=%s\n' "$(openssl rand -hex 32)" > .env
.venv/bin/python -m app.db.seed          # demo data (optional)
.venv/bin/uvicorn app.main:app --port 8000
```

Frontend:

```bash
cd frontend
pnpm install
echo 'NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1' > .env.local
pnpm dev        # http://localhost:3000
```

API docs (OpenAPI): http://localhost:8000/api/docs

### Demo accounts (after seeding)

All passwords: `Demo!Pass2026`

| Email | Role |
|---|---|
| admin@pappuai.com | Super Admin |
| owner@pappuai.com | Company Admin |
| manager@pappuai.com | Sales Manager |
| exec1@pappuai.com / exec2@pappuai.com | Sales Executive |
| caller@pappuai.com | Telecaller |
| marketing@pappuai.com | Marketing Executive |
| partner@pappuai.com | Channel Partner |
| support@pappuai.com | Customer Support |

The first account registered on an empty database bootstraps as Super Admin.

## Docker (production-style)

```bash
export SECRET_KEY=$(openssl rand -hex 32)
docker compose up --build
# web http://localhost:3000 · api http://localhost:8000 · postgres :5432
```

## Tests

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

157 tests: auth/session security (lockout, refresh-token rotation + reuse
detection, password reset), RBAC scope isolation per module, lead dedupe and
import edge cases, booking payment integrity (overpayment, double booking,
payment-gated possession), AI widget scoping, analytics correctness, report
exports, document versioning, a security suite (IDOR, privilege escalation,
hostile input, upload sanitization, authz sweep), the hardening pass
(`tests/test_hardening.py`: workload-balanced auto-assignment, stage-history
reopen guard, campaign reports, site-visit ICS invites), and the events
module (`tests/test_events.py`: public registration → Lead creation, QR
check-in idempotency, referral linkage, badge PDFs, CPL dashboard math,
post-event follow-up automation).

Frontend cross-browser e2e (Playwright, Chromium/Firefox/WebKit):

```bash
cd frontend && pnpm exec playwright install && pnpm test:e2e
```

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module flow, navigation, ERD, permission matrix, folder & API structure
- [`docs/API.md`](docs/API.md) — endpoint-to-module mapping
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — environments, env vars, production notes
- [`docs/MANUAL.md`](docs/MANUAL.md) — user & admin manual, demo walkthrough script

## AI integration

Every AI call flows through `backend/app/modules/ai/provider.py`. All three
providers return identical schemas, so switching between them needs no frontend
or API change:

| `AI_PROVIDER` | What it does | Needs |
|---|---|---|
| `mock` (default) | Deterministic, rule-based output computed from real CRM context. No network, no key, no cost. | — |
| `llm` | Real generation against any OpenAI-compatible endpoint (defaults to Groq, matching the STAIL agents). | `AI_LLM_API_KEY`, optionally `AI_LLM_BASE_URL` / `AI_LLM_MODEL` |
| `external` | Proxies to a running STAIL Realty OS agent service via `POST {base}/api/v1/agents/chat`. | `AI_PROVIDER_BASE_URL`, optionally `AI_PROVIDER_TOKEN` |

Two properties hold regardless of provider:

- **Scores are never model-generated.** `llm` and `external` compute the
  deterministic payload first and let the model rewrite only an allow-list of
  narrative fields. A completion claiming a lead scores 100/hot cannot move a
  score of 15/cold.
- **Failure degrades, it does not raise.** An unreachable gateway, a missing
  key, or a malformed completion returns the deterministic payload with an
  `ai_degraded` note rather than 500ing the page.

What was ported from [STAIL Realty OS](https://github.com/thesilentinvader042/STAIL):

| STAIL | Here |
|---|---|
| `agents/lead-qualification-agent/scoring/` | `ai/grading.py` — weighted per-dimension scoring → composite → A–D grade → recommended action → human-review flag. Weights and thresholds come from the tenant's onboarding answers instead of one hardcoded rubric. |
| `agents/recommendation-agent` | `ai/ranking.py` — composite score (relevance 60% + market appeal 20% + buyer fit 20%). Nothing is filtered out; every result explains itself. |
| `agents/buyer-agent` extraction prompt + INR shorthand parser | `ai/prompts.py`, `ai/llm.py::parse_inr` — "1.5Cr" / "50L" / "₹80 lakh". |
| Recommendation-agent hallucination guard | `LLMAIProvider._annotate` — a blurb that names nothing real about the unit is replaced by a template. |
| `POST /api/v1/agents/chat` | `POST /ai/chat` |
| `POST /api/v1/agents/orchestrate` (AGT-03 → AGT-05 → AGT-02 → AGT-06) | `POST /ai/orchestrate` — same pipeline, one process, no microservice hop. Extracts requirements → ranks live inventory → grades the lead → writes findings back (blank fields only; it never overwrites human-entered data). |

Property inventory has the same provider seam in
`backend/app/modules/properties/service.py` (`PROPERTY_PROVIDER`).

## Onboarding

Twelve form pages derived from the specs in the repo root
(`AI_Developer_Onboarding_Form.md`, `AI_Ideal_Customer_Profile.md`,
`AI_Property_Information_Form.md`, `AI_Lead_Generation_Configuration_Form.md`).
The registry lives in `backend/app/modules/onboarding/schemas.py` and is mirrored
in `frontend/src/app/onboarding/steps.ts`; `GET /onboarding/steps` returns it,
including which spec section each page came from.

The answers are load-bearing, not a survey. Every one of these is enforced or
consumed somewhere, and covered by a test:

| Wizard step | What it actually changes |
|---|---|
| Projects (§2) | Real `property_projects` plus one priced `property_unit` per configuration, spread across the stated price range |
| Operating cities (§1c) | The geography dimension of lead scoring; also lets free-text extraction recognise localities without a hardcoded gazetteer |
| AI lead scoring (§5) | The weights and hot/warm thresholds the grading engine applies |
| AI features (§6 / form §10) | Unticked features are **refused by the API** (`ai_feature_disabled`) and hidden in the UI. Tick nothing and everything stays available |
| Documents (§8) | Immediate upload into the versioned document store (`POST /onboarding/upload` → tenant-scoped `documents` rows) |
| Sales targets (§9 / form §21) | Month-to-date progress bars on the analytics overview |
| Ideal customer profile (§4) | Objections, triggers and pain points lead the sales-tips output instead of generic advice |
| AI usage consent (§12 / form §22) | Declining it stops **every** AI agent in the workspace (`ai_consent_declined`) |

Both AI policy checks fail open for workspaces that never answered — a tenant
that skipped onboarding, or predates these fields, is unaffected. Only an
explicit "No" disables anything. Admins change both under
**Settings → Company profile**, and `GET /ai/catalog` reports exactly what the
workspace may run so the UI and the server never disagree.
