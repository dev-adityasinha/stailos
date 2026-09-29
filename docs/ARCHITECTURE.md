# Pappu AI Intelligent CRM — Architecture Document

**Project:** Pappu AI — AI-Native Real Estate CRM (STAIL Realty OS)
**Scope:** Week-2 MVP per `task_list_zaid.md`, aligned with master PRD (`pappu-ai-crm-prd.md`)
**Status:** Living document — updated as phases land

---

## 1. Architectural Approach

The master PRD targets a multi-service, multi-tenant platform. For the Week-2 MVP the system is built as a **modular monolith with microservice-ready seams**:

- One FastAPI application; every CRM module is an isolated package (`app/modules/<name>/`) with its own models, schemas, service layer, and router. Any module can be lifted into a standalone service later without touching its neighbours (the PRD's "modular, API-first" requirement).
- One Next.js application for all UI, consuming only the versioned REST API — no server-side coupling to the backend.
- Async event hooks (in-process event bus now, queue-compatible interface) carry the PRD's event-driven pattern (`LeadCreated` → scoring → notification) without requiring RabbitMQ in the MVP.
- The AI layer is a **provider abstraction**: every AI endpoint returns structured JSON from an `AIProvider` interface. The default `MockAIProvider` produces deterministic, schema-valid output; Aditya's real agent services plug in by implementing the same interface (or via the HTTP provider pointing at his endpoints). No UI or API contract changes needed at swap time.

### Tech stack (MVP)

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js (App Router), TypeScript, TailwindCSS, shadcn/ui | PRD §5; dark enterprise theme per PRD §2.2 |
| Backend | FastAPI, Python 3.14, Pydantic v2, SQLAlchemy 2.0 | PRD §5 |
| Database | PostgreSQL 16 (Docker) — SQLite fallback for zero-dep dev/tests | Same SQLAlchemy models either way |
| Auth | JWT access (15 min) + rotating refresh token (7 d, httpOnly cookie), argon2 password hashing | PRD §7.1 |
| Background work | FastAPI async tasks + in-process event bus (queue-ready interface) | Celery/RabbitMQ deferred post-MVP |
| Files | Local disk storage adapter behind a `Storage` interface (S3-compatible swap) | PRD §5 |
| Testing | pytest (backend), Playwright/manual scripts (E2E) | PRD §11 |

---

## 2. Module Flow

```
                            ┌────────────────────────────┐
                            │        Authentication       │
                            │  (JWT, roles, sessions)     │
                            └──────────────┬─────────────┘
                                           │ every request
        ┌──────────────────────────────────┼───────────────────────────────────┐
        ▼                                  ▼                                   ▼
┌───────────────┐   convert    ┌────────────────┐    deal/booking   ┌────────────────┐
│ Lead Mgmt     │─────────────▶│ Customer Mgmt  │──────────────────▶│ Booking Module │
│ capture,      │              │ 360 profile,   │                   │ site visit →   │
│ dedupe,       │              │ docs, history  │                   │ … → possession │
│ pipeline      │              └───────┬────────┘                   └───────┬────────┘
└──────┬────────┘                      │ attach/shortlist                   │ payments,
       │ events                        ▼                                    │ documents
       │              ┌────────────────────────┐                            ▼
       │              │ Property Module        │                  ┌────────────────┐
       │              │ (integration adapter)  │                  │ Document Mgmt  │
       │              └────────────────────────┘                  └────────────────┘
       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Cross-cutting: Tasks · Calendar · Notifications · AI Layer · Analytics ·      │
│ Reports · Audit Log — all subscribe to module events and read module APIs     │
└──────────────────────────────────────────────────────────────────────────────┘
```

Lifecycle spine (PRD §7.3 / task list Task 9):
`Lead → Contacted/Qualified → Site Visit → Negotiation → Booked (Deal won) → Booking → Documentation → Payment → Possession`

## 3. Navigation Flow (frontend)

```
/login  /register  /forgot-password  /reset-password  /verify-email
   └── on auth ──▶ /dashboard  (role-appropriate widgets)
                     ├── /leads            (table + saved filters)
                     │     ├── /leads/pipeline   (Kanban, drag-drop)
                     │     └── /leads/[id]       (detail: profile | timeline | AI panel)
                     ├── /customers        (list) → /customers/[id]  (360 view)
                     ├── /properties       (browse/shortlist/compare)
                     ├── /bookings         (list) → /bookings/[id]   (stepper)
                     ├── /tasks            (list + my tasks)
                     ├── /calendar         (month/week; team toggle)
                     ├── /analytics        (charts)
                     ├── /reports          (generate + export)
                     ├── /documents        (library, versions)
                     ├── /notifications    (center)
                     └── /settings         (profile, sessions, team & roles [admin])
```

Shell: collapsible sidebar + header (global search, quick actions, notification tray, user menu). Responsive desktop/tablet.

## 4. Entity-Relationship Diagram

```
TENANT ─┬─< USER ────< SESSION / REFRESH_TOKEN
        │      │
        │      └──assigned──< LEAD >──source── LEAD_SOURCE
        │                      │ │
        │                      │ ├──< LEAD_NOTE, LEAD_TAG (M:N via lead_tags)
        │                      │ ├──< ACTIVITY (timeline: calls, emails, meetings,
        │                      │ │              site visits, notes, docs, AI recs)
        │                      │ └──converts──▶ CUSTOMER
        │                      │                   │
        │                      │                   ├──< CUSTOMER_PROPERTY (shortlist/
        │                      │                   │      favourite/attached) >── PROPERTY
        │                      │                   ├──< DEAL >── PROPERTY(unit)
        │                      │                   │      └──▶ BOOKING
        │                      │                   │             ├──< BOOKING_STAGE_EVENT
        │                      │                   │             ├──< PAYMENT
        │                      │                   │             └──< DOCUMENT (M:N)
        │                      │                   └──< DOCUMENT
        ├─< PROPERTY_PROJECT ──< PROPERTY (unit)
        ├─< TASK  (assignee: USER; optional link to LEAD/CUSTOMER/BOOKING)
        │     └──< TASK_COMMENT, TASK_ATTACHMENT
        ├─< CALENDAR_EVENT (owner + attendees M:N USER; optional entity link)
        ├─< NOTIFICATION (recipient USER)
        ├─< AI_INSIGHT (entity_type + entity_id polymorphic; agent_name; payload jsonb)
        ├─< DOCUMENT ──< DOCUMENT_VERSION
        └─< AUDIT_LOG (actor, action, entity, before/after, ip, ts)
```

Conventions: UUID PKs, `tenant_id` on every tenant-scoped table (single-tenant seeded in MVP, multi-tenant-ready), `created_at`/`updated_at` UTC, soft delete (`deleted_at`) on Lead/Customer/Task/Document, monetary values as `Numeric` (never float), enum-typed statuses.

## 5. User Permissions

Roles (task list Task 2): **Super Admin, Company Admin, Sales Manager, Sales Executive, Telecaller, Marketing Executive, Channel Partner, Customer Support**.

Permission model: role → set of `resource:action:scope` permissions, enforced by FastAPI dependencies at the route layer and re-checked in services (defense in depth, PRD §10). Scopes: `all` (tenant-wide), `team`, `own`.

| Resource | Super Admin | Company Admin | Sales Manager | Sales Executive | Telecaller | Marketing Exec | Channel Partner | Customer Support |
|---|---|---|---|---|---|---|---|---|
| Users/Roles | CRUD all | CRUD tenant | read team | — | — | — | — | — |
| Leads | CRUD all | CRUD all | CRUD team + reassign | CRUD own, read team | CRUD own (create/update status/notes) | read all, edit source/campaign | create referred, read own referred | read all |
| Customers | CRUD all | CRUD all | CRUD team | CRUD own | read own | read all | — | read + notes |
| Properties | CRUD all | CRUD all | read | read + shortlist | read | read | read | read |
| Deals/Bookings | CRUD all | CRUD all | CRUD team | create + read own | — | — | read own referred | read |
| Payments | CRUD all | CRUD all | read team | read own (amounts read-only) | — | — | — | — |
| Tasks | CRUD all | CRUD all | CRUD team + assign | CRUD own | CRUD own | CRUD own | — | CRUD own |
| Calendar | CRUD all | CRUD all | CRUD team | CRUD own | CRUD own | CRUD own | — | CRUD own |
| Analytics/Reports | all | all | team | own | own | marketing | own referred | support |
| Documents | CRUD all | CRUD all | CRUD team | CRUD own | read own | read | — | read |
| Notifications | own | own + broadcast | own + team alerts | own | own | own | own | own |
| Audit log | read all | read tenant | — | — | — | — | — | — |
| AI widgets | all | all | team scope | own scope | own scope | marketing scope | own scope | support scope |

## 6. Folder Structure

```
mentamind/
├── docs/                      # architecture, API mapping, schema, manuals
├── backend/
│   ├── app/
│   │   ├── main.py            # app factory, middleware, router mounting
│   │   ├── core/              # settings, security (jwt/hash), deps, permissions,
│   │   │                      #   events (bus), errors, pagination, audit
│   │   ├── db/                # engine/session, base model, seed
│   │   └── modules/
│   │       ├── auth/          # + users, roles, sessions
│   │       ├── leads/         # + pipeline, dedupe, import/export
│   │       ├── customers/
│   │       ├── properties/    # + integration adapter (mock ⇄ Aditya API)
│   │       ├── bookings/      # + payments, stage workflow
│   │       ├── tasks/
│   │       ├── calendar/
│   │       ├── notifications/
│   │       ├── ai/            # provider interface, mock provider, widgets
│   │       ├── analytics/
│   │       ├── reports/       # csv/xlsx/pdf export
│   │       └── documents/     # storage adapter, versions
│   │   # each module: models.py · schemas.py · service.py · router.py
│   ├── tests/                 # pytest per module + integration
│   ├── alembic/  (migrations) # once Postgres is primary
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/app/               # App Router route groups: (auth)/ (dashboard)/
│   ├── src/components/        # ui/ (shadcn) + module components
│   ├── src/lib/               # api client, auth context, utils
│   └── package.json
├── docker-compose.yml         # postgres (+ app services)
└── README.md
```

## 7. API Structure

REST under `/api/v1/`, JSON envelope `{ data, meta }` on success, `{ error: { code, message, correlation_id } }` on failure (PRD §13.2). Cursor/offset pagination via `limit`/`offset`. OpenAPI auto-generated at `/api/docs`.

```
/api/v1/auth        POST register · login · logout · refresh · password/forgot ·
                    password/reset · verify-email    GET/DELETE sessions
/api/v1/users       GET list · GET/PATCH/DELETE {id} · PATCH {id}/role (admin)
/api/v1/leads       CRUD · POST {id}/assign · {id}/notes · {id}/tags ·
                    GET {id}/timeline · POST check-duplicates · import · GET export
/api/v1/pipeline    GET board · PATCH leads/{id}/stage
/api/v1/customers   CRUD · GET {id}/360 · {id}/documents · {id}/timeline
/api/v1/properties  GET list/search · GET {id} · POST {id}/shortlist ·
                    {id}/favourite · {id}/attach · POST compare
/api/v1/bookings    CRUD · POST {id}/advance-stage · {id}/payments ·
                    GET {id}/payments · POST {id}/cancel
/api/v1/tasks       CRUD · POST {id}/comments · {id}/attachments
/api/v1/calendar    CRUD events · GET team view
/api/v1/notifications  GET list · PATCH {id}/read · POST read-all · prefs
/api/v1/ai          POST widgets/{widget} (lead-summary, customer-summary,
                    suggestions, next-best-action, investment-insights,
                    sales-tips, property-recommendations) ·
                    POST components/{component} (lead-qualification,
                    buyer-assistant, property-recommendation, follow-up,
                    email-generator, whatsapp-assistant, call-summary,
                    customer-insights)
/api/v1/analytics   GET overview · funnel · revenue · team · sources
/api/v1/reports     POST generate (type + format csv|xlsx|pdf) · GET {id}/download
/api/v1/documents   POST upload · GET list · GET {id}/versions · POST {id}/version
/api/v1/audit       GET list (admin)
```

Security: all non-auth routes require `Authorization: Bearer <access>`; RBAC dependency per route; rate limiting on auth endpoints; CORS locked to frontend origin; security headers middleware; input validation via Pydantic everywhere; audit log on mutating actions.
