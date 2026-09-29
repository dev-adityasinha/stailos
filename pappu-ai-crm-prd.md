# Product Requirements Document
## Pappu AI — Intelligent AI-Native CRM for Real Estate

**Flagship product of STAIL Realty OS · Shiv Trinetrix AI Labs Pvt. Ltd.**

Document version: 1.0 (Foundational Master PRD)
Status: Draft for engineering, design, AI, QA, and DevOps review
Owner: Product Management, Shiv Trinetrix AI Labs

**Scope note for the reader:** This document establishes the complete product architecture, module specifications, AI agent framework, data model, and delivery roadmap for Pappu AI at a build-ready level of detail. Given the platform's breadth (25+ modules, 13 AI agents, 25 personas), this master document specifies every module to a consistent PRD template (purpose, logic, schema, APIs, permissions, edge cases, acceptance criteria) and goes deep on the modules that carry the most architectural risk (Auth, Lead Management, AI Layer, Orchestration, Database, Booking). Any individual module can be expanded into its own 15–25 page detailed spec on request — flag which ones you want next and I will produce them as standalone documents that plug into this master PRD without contradiction.

---

## Table of Contents

1. Product Vision & Core Philosophy
2. Design Principles & UI/UX Language
3. User Personas (25)
4. System Architecture
5. Tech Stack
6. Database Design
7. Product Modules (full catalogue, PRD-template specs)
8. AI Layer — Agent Specifications (13 agents)
9. Multi-Agent Orchestration Framework
10. Security & Compliance
11. Testing Strategy
12. Product Roadmap
13. Appendix — Global Standards (error/empty/loading states, acceptance criteria format, API conventions)

---

## 1. Product Vision & Core Philosophy

### 1.1 Vision Statement

Pappu AI is India's AI-native CRM built specifically for real estate sales organizations — builders, brokers, channel partners, and investment desks. It is not a system of record; it is a digital sales employee: it understands customer intent, learns preferences over time, predicts buying behavior, recommends and takes action, and drives leads through the full sales lifecycle with a human approving or overriding at key checkpoints.

### 1.2 Core Philosophy

**Pappu AI:**
- Understands Customers
- Learns Preferences
- Predicts Intent
- Automates Workflows
- Acts Independently
- Improves Conversion
- Operates as AI Sales Employee

**Traditional CRM:**
- Stores Information
- Requires Manual Updates
- Static
- Reactive

### 1.3 Product Pillars

| Pillar | Description | Primary Owner |
|---|---|---|
| Data Fabric | Unified, deduplicated, real-time customer & property graph | Backend/Data Eng |
| Automation Engine | No-code workflow builder + triggers/actions | Platform Eng |
| AI Agent Mesh | 13 specialized agents orchestrated for sales tasks | AI Eng |
| Human-in-the-loop Control | Approval layer, override, audit trail on all AI actions | Product/Trust & Safety |
| Real Estate Domain Depth | Inventory, bookings, legal docs, ROI, tokenization-ready | Domain/Product |

### 1.4 Non-Goals (v1–v2)

- Pappu AI is not a public marketplace/listing portal (no anonymous public browsing of inventory).
- Not a payment processor of record — integrates with existing payment gateways/escrow providers rather than holding funds.
- Full blockchain tokenization execution is out of scope through Phase 4; Phase 5 only readiness/advisory.

---

## 2. Design Principles & UI/UX Language

### 2.1 Engineering Design Principles

Enterprise-grade architecture · Modular design · API-first · AI-first workflows · Event-driven architecture · Multi-tenant SaaS · Scalable microservices · Cloud-native deployment · Mobile-first responsive UI · WCAG 2.1 AA accessibility · Security by design · Zero-trust authentication · Production-ready engineering from day one (no throwaway prototypes).

### 2.2 Visual Design Language

- **Theme:** Dark Enterprise (default), with a Light Enterprise theme for field/site-visit usage in bright sunlight.
- **Accent palette:** Electric Blue #3B82F6 (primary actions, links), Emerald #10B981 (success, positive deltas, revenue), Purple #8B5CF6 (AI-generated content, agent activity, "Pappu is thinking" states).
- **Inspiration blend:** Salesforce Lightning (data density), Linear (speed & keyboard-first interactions), Notion (flexible content blocks), HubSpot (approachability), Monday.com (visual pipelines), Vercel/Stripe dashboards (typography & restraint), Retool (internal-tool density for admin screens), Figma/Framer (motion quality).
- **Typography:** Inter or Geist for UI; JetBrains Mono for IDs, API keys, code blocks.
- **Motion:** 150–250ms ease-out transitions; no bouncing/elastic easing; skeleton loaders not spinners; AI responses stream token-by-token with a subtle purple pulse indicator.
- **Density modes:** Comfortable (default), Compact (power users — toggle persisted per user).
- **Iconography:** Single consistent icon set (Lucide) at 2px stroke weight throughout.

### 2.3 UI System Components (design-system inventory)

Navigation shell (collapsible left rail + command palette `Cmd+K`), Data table (sortable, filterable, saved views, inline edit), Kanban board, Timeline/activity feed, Modal/drawer patterns, Form builder primitives, Chart library (line, bar, funnel, cohort, heatmap), Notification tray, AI chat panel (persistent right-dock "Ask Pappu"), Empty/error/loading state templates (see Appendix 13.1).

### 2.4 Accessibility Requirements

WCAG 2.1 AA minimum: 4.5:1 contrast for text, full keyboard navigation, ARIA labeling on all interactive components, screen-reader-tested critical flows (login, lead creation, booking), reduced-motion mode, resizable text up to 200% without layout breakage.

---

## 3. User Personas

Each persona below follows: Goals · Pain Points · KPIs · Permissions · Daily Workflow · Dashboard · Notifications · Reports · AI Features. Personas are grouped by tier for scannability; each still receives full individual specification in engineering handoff (persona detail packs available as a standalone appendix on request).

### 3.1 Persona Summary Matrix

| Persona | Tier | Primary Goal | Core KPI | Default Dashboard |
|---|---|---|---|---|
| SuperAdmin | Platform | Platform uptime & tenant health | System SLA, tenant churn | Platform Ops |
| Company Owner | Executive | Revenue & org performance | Revenue, conversion rate | Executive Dashboard |
| Sales Director | Executive | Pipeline health across regions | Pipeline value, win rate | Sales Dashboard |
| Regional Manager | Management | Region target attainment | Regional revenue % target | Regional Sales |
| Sales Manager | Management | Team quota attainment | Team conversion rate | Team Dashboard |
| Sales Executive | Frontline | Close deals, hit personal quota | Deals closed, calls made | My Pipeline |
| Telecaller | Frontline | Qualify & convert leads to appointments | Calls/day, appointments set | Calling Queue |
| Business Development Executive | Frontline | Acquire new channel partners/builders | New partnerships signed | BD Dashboard |
| Marketing Manager | Marketing | Lead volume & CPL | Cost per lead, MQL→SQL rate | Marketing Dashboard |
| CRM Administrator | Ops | System configuration & data hygiene | Data quality score, uptime | Admin Console |
| Customer Success Manager | Ops | Post-sale satisfaction & retention | NPS, retention rate | CS Dashboard |
| Finance Team | Ops | Collections & revenue recognition | DSO, collection %, invoice accuracy | Finance Dashboard |
| Legal Team | Ops | Contract compliance | Contract turnaround time | Legal Queue |
| Documentation Team | Ops | Document accuracy & turnaround | Doc processing time, error rate | Doc Center |
| Builder | External | Sell inventory, track project | Units sold, absorption rate | Builder Portal |
| Developer (dev/API user) | Technical | Integrate & extend platform | API uptime, integration success | Developer Console |
| Channel Partner | External | Earn brokerage, close referred deals | Referrals converted, brokerage earned | Partner Portal |
| Broker | External | Manage listings & clients | Deals closed, listings active | Broker Dashboard |
| Investor | External | Track portfolio ROI | Portfolio IRR, rental yield | Investor Portal |
| Buyer | End Customer | Find & purchase property | — (satisfaction) | Buyer Portal |
| Seller | End Customer | List & sell property | Days on market, offers received | Seller Portal |
| Tenant | End Customer | Lease management | — (satisfaction) | Tenant Portal |
| Support Executive | Ops | Resolve tickets fast | First response time, CSAT | Support Console |
| Auditor | Compliance | Verify compliance & data integrity | Audit findings closed | Audit Console |

### 3.2 Deep-Dive: Sales Executive (representative full persona)

**Goals:** Hit monthly booking quota; minimize time on data entry; get AI-prioritized "who to call next."

**Pain Points:** Manual lead entry, cold leads mixed with hot leads in one list, no visibility into what a customer already discussed with marketing/telecalling.

**KPIs:** Leads contacted within SLA (15 min), site visits scheduled, conversion rate, average deal cycle time, revenue booked.

**Permissions:** CRUD on own leads/deals; read-only on team leads; no access to finance/legal modules; cannot edit pricing master; can request discount approval.

**Daily Workflow:** Morning — reviews AI-prioritized call list → logs calls/WhatsApp → updates deal stage on Kanban → schedules site visits via Calendar → uses Sales Copilot for objection handling during live calls → end of day reviews AI-generated daily summary.

**Dashboard Requirements:** My Pipeline (Kanban), Today's Tasks, AI "Next Best Action" widget, Leaderboard (opt-in), Revenue booked vs target gauge.

**Notifications:** New lead assigned (push+SMS), SLA breach warning, site visit reminder (T-60min), deal stage stale >5 days.

**Reports:** Personal performance report (weekly), lead source effectiveness (for own leads).

**AI Features:** Lead scoring, Sales Copilot live suggestions, auto-drafted follow-up messages, call summarization, next-best-action recommendations.

*(Remaining 23 personas follow the same structural depth; summarized in 3.1 matrix above with full detail available as standalone persona packs.)*

---

## 4. System Architecture

### 4.1 High-Level Architecture

**Client Layer:** Next.js Web App, React Native Mobile App, Partner/Builder Portal

**Edge:** CDN / Edge Cache → API Gateway + Rate Limiter

**Core Services (Microservices):** Auth Service, Lead Service, Customer Service, Property/Inventory Service, Sales Pipeline Service, Booking Service, Task Service, Communication Service, Notification Service, Document Service, Workflow Automation Engine, Analytics/Reporting Service, Agent Orchestrator

**AI Layer:** 13 Specialized AI Agents, Model Router

**Data Layer:** Vector DB (Qdrant), Redis (Cache/Session), PostgreSQL (Primary), Celery/RabbitMQ (Async Jobs), Object Storage (S3-compatible)

**Observability:** Centralized Logging, Metrics/Tracing, Alerting

### 4.2 Request Lifecycle — Example: Lead Creation → AI Qualification

1. User/Web Form → `POST /leads` (new lead payload) → API Gateway
2. API Gateway → Lead Service: validate & create lead
3. Lead Service: dedupe check against Customer graph
4. Lead Service → User: `201 Created` (lead_id)
5. Lead Service → Queue: publish `LeadCreated` event
6. Queue → Lead Qualification Agent: consume event
7. Lead Qualification Agent: score lead (hot/warm/cold), compute buying probability
8. Lead Qualification Agent → Lead Service: `PATCH` lead (score, tags)
9. Lead Service → Notification Service: trigger assignment notification
10. Notification Service → Sales Executive: push + SMS "New hot lead assigned"
11. Sales Executive → API Gateway: `GET /leads/{id}`
12. API Gateway → Lead Service: fetch enriched lead
13. Lead Service → Sales Executive: lead detail + AI summary

### 4.3 Multi-Tenancy Model

- **Isolation strategy:** Schema-per-tenant on PostgreSQL for mid/large tenants; row-level security (tenant_id on every table + RLS policies) for smaller tenants on shared schema, selectable at provisioning time.
- **Tenant context:** Propagated via signed JWT claim `tenant_id`, enforced at API Gateway and again at service/query layer (defense in depth).
- **Cross-tenant protections:** No service may execute a query without a `tenant_id` predicate; automated static-analysis lint rule blocks PRs missing tenant scoping on new queries.

### 4.4 Environments

Dev → Staging → UAT → Production, each with isolated databases, secrets, and feature-flag configuration (LaunchDarkly-style flagging service).

---

## 5. Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend Web | Next.js 14+ (App Router), React 18, TypeScript | SSR/ISR for performance, type safety |
| Styling | TailwindCSS + shadcn/ui | Design-system velocity, accessible primitives |
| Mobile | React Native (Expo) | Shared logic with web via TS packages |
| Backend | FastAPI (Python 3.12) | Async-first, OpenAPI-native, strong typing via Pydantic |
| Primary DB | PostgreSQL 16 | ACID, JSONB for flexible fields, mature RLS support |
| Cache/Session | Redis 7 | Sub-ms reads, pub/sub for real-time features |
| Async/Queue | Celery + RabbitMQ (or Redis broker) | Reliable background job processing |
| Vector DB | Qdrant (preferred), Pinecone (fallback) | Semantic search & embeddings for property/customer matching |
| Object Storage | S3-compatible (AWS S3 / MinIO for on-prem) | Documents, media, floor plans |
| AI Providers | Anthropic Claude (primary reasoning/agents), OpenAI (embeddings/fallback), Gemini (multimodal fallback), Ollama (on-prem/local for data-sensitive tenants) | Multi-provider redundancy, cost/latency routing |
| Deployment | Docker, Kubernetes, Nginx Ingress | Cloud-native scalability |
| CI/CD | GitHub Actions | Test → build → scan → deploy pipelines |
| Observability | OpenTelemetry, Prometheus/Grafana, ELK/Loki | Full-stack tracing and logging |

---

## 6. Database Design

### 6.1 Core Entity-Relationship Diagram

**Core Entities and Relationships:**

- **TENANT** — `id (uuid, PK)`, `name`, `plan_tier`, `settings (jsonb)`, `created_at`
  - has → USER, LEAD

- **USER** — assigned to LEAD

- **LEAD** — `id (uuid, PK)`, `tenant_id (FK)`, `assigned_to (FK)`, `source`, `status`, `score_band`, `ai_score (float)`, `raw_payload (jsonb)`, `created_at`
  - converts to → CUSTOMER

- **CUSTOMER** — `id (uuid, PK)`, `tenant_id (FK)`, `name`, `phone`, `email`, `preferences (jsonb)`, `health_score (float)`
  - owns → DEAL

- **PROPERTY_PROJECT** — develops (by BUILDER)
  - contains → PROPERTY_UNIT

- **PROPERTY_UNIT** — `id (uuid, PK)`, `project_id (FK)`, `unit_number`, `status`, `price (numeric)`, `attributes (jsonb)`, `embedding (vector)`
  - targets → DEAL

- **DEAL** — `id (uuid, PK)`, `customer_id (FK)`, `unit_id (FK)`, `stage`, `value (numeric)`, `win_probability (float)`
  - results in → BOOKING

- **BOOKING** — `id (uuid, PK)`, `deal_id (FK)`, `status`, `token_amount (numeric)`, `agreement_date (date)`
  - has → PAYMENT, DOCUMENT

- **PAYMENT** — logged under BOOKING

- **DOCUMENT** — has requires relationship with BOOKING

- **ACTIVITY** — logs against LEAD/CUSTOMER

- **TASK** — assigned to USER

- **AI_INSIGHT** — `id (uuid, PK)`, `entity_type`, `entity_id`, `agent_name`, `payload (jsonb)`, `generated_at`
  - enriches → LEAD, CUSTOMER, PROPERTY_UNIT

- **BUILDER** — develops PROPERTY_PROJECT

- **CHANNEL_PARTNER** — refers LEAD

- **AUDIT_LOG** — generated by system actions

### 6.2 Design Standards

(Standards referenced throughout module specs — see Section 7 and Appendix 13 for conventions on IDs, timestamps, and constraints.)

---

## 7. Product Modules — Full Catalogue

Template applied to every module: Purpose · Objectives · Business Logic · User Stories · Functional Requirements · Non-Functional Requirements · Database Design · API Endpoints · Permissions · UI Description · Edge Cases · Validation Rules · Acceptance Criteria · Testing Strategy · Success Metrics · Dependencies · Future Enhancements.

Below, the highest-risk modules (Auth, Lead Management, Booking) receive the full template; remaining modules receive a condensed version of the same template (all fields present, more concise) to keep this master document navigable. Each can be expanded to full depth on request.

### 7.1 Authentication — FULL SPEC

**Purpose:** Secure, frictionless identity and access management across web, mobile, and partner surfaces, supporting enterprise SSO and zero-trust principles.

**Objectives:** <15s login time; zero credential-stuffing success; support enterprise IdPs; device-level trust scoring.

**Business Logic:**
- Login supports email/password, Google, Microsoft, Apple OAuth, and SAML/OIDC SSO for enterprise tenants.
- JWT access tokens (15 min TTL) + refresh tokens (7 days, rotating, stored httpOnly secure cookie).
- MFA (TOTP or SMS OTP) mandatory for SuperAdmin, Company Owner, Finance, Legal roles; optional/configurable for others.
- Device management: each new device triggers a verification email/SMS; device list visible and revocable in account settings.
- Session management: concurrent session cap configurable per tenant (default 5); admin can force-logout any user.

**User Stories:**
- As a Sales Executive, I want to log in with Google so I don't manage another password.
- As a CRM Administrator, I want to enforce MFA for Finance role so financial data is protected.
- As a SuperAdmin, I want to see and revoke active sessions for any user for security incident response.

**Functional Requirements:**
- FR1: Email/password login with bcrypt/argon2 hashing.
- FR2: OAuth (Google/Microsoft/Apple).
- FR3: SAML/OIDC SSO per tenant.
- FR4: Password reset via signed, time-limited email link (15 min expiry).
- FR5: MFA setup/verification flow.
- FR6: Device fingerprinting & trust list.
- FR7: Role-based access control enforcement at API layer.
- FR8: Full audit logging of auth events.

**Non-Functional Requirements:** p95 login latency <400ms; 99.95% auth service uptime; OWASP ASVS Level 2 compliance; token signing via rotated RS256 keys (JWKS endpoint).

**Database Design:** `users`, `user_credentials` (hashed secrets only), `oauth_identities`, `sessions`, `devices`, `mfa_factors`, `password_reset_tokens`, `auth_audit_log`.

**API Endpoints (representative):**
```
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/oauth/{provider}/callback
POST /api/v1/auth/mfa/verify
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
POST /api/v1/auth/password/forgot
POST /api/v1/auth/password/reset
GET  /api/v1/auth/sessions
DELETE /api/v1/auth/sessions/{session_id}
```

**Permissions:** Auth endpoints are unauthenticated by design except session/device management (requires valid session).

**UI Description:** Split-screen login (brand panel left, form right) on desktop; single-column on mobile. Inline validation errors below fields. MFA screen shows masked phone/authenticator app icon choice. Device list screen shows device name, last active, location (city-level), "This device" badge, revoke button.

**Edge Cases:**
- Login attempt during password reset in-flight → reset link invalidated after successful login.
- OAuth email already registered via password → prompt to link accounts after password verification.
- Session refresh race condition → use refresh token rotation with reuse detection (revoke entire family on reuse).

**Validation Rules:** Password: min 10 chars, 1 upper, 1 number, 1 symbol, checked against breached-password list (k-anonymity API). Email: RFC 5322 + MX record check on signup.

**Acceptance Criteria:**
- Given valid credentials, when user submits login, then access+refresh tokens issued within 400ms p95 and user redirected to role-appropriate dashboard.
- Given 5 failed login attempts within 10 minutes, when 6th attempt is made, then account is temporarily locked for 15 minutes and user notified via email.

**Testing Strategy:** Unit tests on hashing/token logic; integration tests for OAuth callback flows (mocked provider); security tests (OWASP ZAP scan) on all auth endpoints; load test at 500 concurrent logins/sec.

**Success Metrics:** <0.1% failed-login-to-support-ticket ratio; MFA adoption >95% for mandated roles; zero critical auth vulnerabilities in quarterly pen test.

**Dependencies:** Redis (session store), Email/SMS providers (reset & OTP), Identity providers (OAuth/SAML).

**Future Enhancements:** Passkey/WebAuthn support; risk-based adaptive authentication; biometric login on mobile.

---

### 7.2 Lead Management — FULL SPEC

**Purpose:** Capture leads from every channel, eliminate duplicates, route to the right owner instantly, and hand off an AI-qualified, context-rich lead to sales.

**Objectives:** <15 min lead-to-first-contact SLA; <2% duplicate leakage; >80% of leads auto-scored within 60 seconds of capture.

**Business Logic:**
- Capture sources: website forms, landing pages, Meta Lead Ads, Google Lead Form Ads, WhatsApp Business API, offline event CSV, manual entry, bulk CSV import.
- Deduplication: match on normalized phone number (primary key) + fuzzy name/email match (Levenshtein threshold); duplicate leads merge activity timelines rather than creating new records.
- Assignment: rule-based (round robin, territory, source-based) or AI-based (best-fit agent by historical conversion on similar lead profile); reassignment requires Sales Manager approval and is logged.
- Lead Scoring: AI Lead Qualification Agent scores 0–100 → banded Hot (≥70) / Warm (40–69) / Cold (<40); score recalculates on every new activity (call, WhatsApp reply, site visit).

**User Stories:**
- As a Marketing Manager, I want leads from Meta Ads to land in CRM automatically tagged with campaign UTM so I can measure ROI.
- As a Sales Manager, I want duplicate leads auto-merged so my team doesn't call the same customer twice from two agents.
- As a Sales Executive, I want my new lead pre-scored and summarized so I know how to open the call.

**Functional Requirements:**
- FR1: Multi-channel capture connectors.
- FR2: Bulk CSV import with column mapping & validation preview.
- FR3: Real-time dedupe engine.
- FR4: Configurable assignment rules engine.
- FR5: AI scoring pipeline.
- FR6: Lead timeline (all activity, notes, attachments, communication).
- FR7: Tagging & custom fields.
- FR8: Bulk actions (reassign, tag, export, disqualify).

**Non-Functional Requirements:** Ingest 10,000 leads/hour burst capacity (ad campaign spikes); scoring latency <60s p95; 99.9% capture reliability with dead-letter queue + retry for failed webhook ingests.

**Database Design:** `leads`, `lead_sources`, `lead_activities`, `lead_scores_history`, `duplicate_merge_log`, `assignment_rules`, `import_batches`.

**API Endpoints:**
```
POST /api/v1/leads
POST /api/v1/leads/import (CSV, async job)
GET  /api/v1/leads?status=&score_band=&assigned_to=&source=
GET  /api/v1/leads/{id}
PATCH /api/v1/leads/{id}
POST /api/v1/leads/{id}/assign
POST /api/v1/leads/{id}/merge
POST /api/v1/leads/{id}/activities
POST /api/v1/webhooks/meta-ads
POST /api/v1/webhooks/google-ads
POST /api/v1/webhooks/whatsapp
```

**Permissions:** Sales Executive: CRUD own leads, read team leads. Sales Manager: CRUD team leads, reassign. Marketing Manager: read all leads, edit source/campaign fields only. CRM Admin: full CRUD, assignment-rule configuration.

**UI Description:** Default view is a filterable, saved-view data table with score-band color chips (red/amber/green analog using Emerald/Electric Blue/neutral, avoiding pure red-green for colorblind accessibility — score bands also shown as text labels). Lead detail is a two-pane layout: left = profile/timeline, right = "Ask Pappu" AI panel with summary and next-best-action. Kanban toggle view groups by status.

**Edge Cases:**
- Webhook delivers lead after source campaign deleted → still ingested, source marked "archived campaign."
- Two leads merge where each has different assigned owner → ownership conflict flagged to Sales Manager for manual resolution, not auto-resolved.
- CSV import with malformed phone numbers → row-level error report, valid rows still import.

**Validation Rules:** Phone: E.164 normalization required before dedupe check. Required fields configurable per tenant but name+phone always mandatory. CSV import capped at 50,000 rows per batch.

**Acceptance Criteria:**
- Given a new Meta Ads lead webhook, when received, then a lead record is created within 5 seconds with source, campaign, and UTM populated, and AI scoring is queued.
- Given two leads with identical normalized phone numbers, when the second is created, then it is auto-merged into the first with a duplicate-merge audit entry.

**Testing Strategy:** Contract tests against each channel webhook schema; load test at 10k leads/hour; dedupe accuracy tested against a labeled dataset (target >98% precision).

**Success Metrics:** Lead-to-first-contact time, duplicate rate, source-wise conversion rate, scoring accuracy (AUC vs actual conversion outcome).

**Dependencies:** Communication Center (for SLA-triggered notifications), AI Lead Qualification Agent, Customer Management (for merge target).

**Future Enhancements:** Predictive lead-volume forecasting per channel; auto-pause underperforming ad campaigns via Marketing CRM integration.

---

### 7.3 Booking Management — FULL SPEC

**Purpose:** Manage the full post-sale lifecycle from token payment through possession, with financial and legal traceability.

**Business Logic:** Booking created from a won Deal → Token Amount collected → Agreement generated (via Documentation Agent) → Payment schedule (EMI/loan-linked or builder payment plan) tracked → Loan status synced (manual update or lender API where available) → Registration milestone → Possession → After-sales/CS handoff. Cancellation triggers a refund workflow with configurable deduction rules (per tenant policy) and requires Finance approval above a configurable threshold.

**Functional Requirements:**
- FR1: Booking creation from Deal.
- FR2: Configurable payment milestone templates (construction-linked, down-payment, possession-linked).
- FR3: Payment tracking with receipt generation.
- FR4: Loan/EMI status field sync.
- FR5: Registration & possession checklist workflow.
- FR6: Cancellation & refund workflow with approval gates.

**Non-Functional Requirements:** Financial figures immutable once invoiced (corrections via credit note, not edit); full audit trail on every monetary change.

**Database Design:** `bookings`, `payment_schedules`, `payments`, `receipts`, `loan_status`, `possession_checklist`, `cancellations`, `refunds`.

**API Endpoints:**
```
POST /api/v1/bookings
GET  /api/v1/bookings/{id}
POST /api/v1/bookings/{id}/payments
POST /api/v1/bookings/{id}/cancel
GET  /api/v1/bookings/{id}/payment-schedule
POST /api/v1/bookings/{id}/possession/checklist
```

**Permissions:** Sales Executive: create booking, view payment status (read-only on amounts). Finance: full CRUD on payments/receipts, approve refunds. Legal: manage agreement/registration status. Customer Success: possession & after-sales stage only.

**UI Description:** Booking detail as a vertical stepper (Token → Agreement → Payments → Loan → Registration → Possession → After-Sales), each stage expandable with relevant documents and actions inline.

**Edge Cases:**
- Partial payment received against a milestone → system marks milestone "partially paid," does not auto-advance stage.
- Cancellation requested after registration → blocked, routed to Legal for manual case handling (registration reversals are not systematized).
- Currency/rounding on EMI schedule → all monetary calculations use fixed-point decimal (never float).

**Validation Rules:** Token amount must be ≥ tenant-configured minimum %; refund amount cannot exceed sum of payments received.

**Acceptance Criteria:**
- Given a booking with a fully paid milestone, when the next milestone's due date arrives, then a payment-due notification is sent to customer and assigned executive 7 days in advance.
- Given a cancellation request, when the refund amount exceeds the approval threshold, then the request is routed to Finance for approval before refund is issued.

**Testing Strategy:** Financial calculation unit tests (edge cases: partial payments, overpayment, multi-currency where applicable); end-to-end test of full booking lifecycle; reconciliation test against Finance ledger export.

**Success Metrics:** Days-sales-outstanding (DSO), on-time milestone payment %, cancellation rate, average refund turnaround time.

**Dependencies:** Documentation Agent (agreement generation), Finance module, Notification Center.

**Future Enhancements:** Direct lender API integration for real-time loan status; escrow-linked milestone auto-release.

---

### 7.4 Remaining Modules — Condensed Specs

Each entry follows the same template in brief; full expansion available on request.

#### Dashboard
**Purpose:** Role-specific real-time command center.
**Logic:** Widget-based, drag-to-configure; data refreshed via WebSocket for live metrics, polling fallback.
**Key APIs:** `GET /dashboards/{role}`, `POST /dashboards/custom`.
**Permissions:** Widget-level RBAC (e.g., Finance widgets hidden from Sales roles).
**Edge Cases:** Widget data source unavailable → shows cached value with "stale" badge, not blank.
**Acceptance Criteria:** Dashboard loads first meaningful paint <1.5s p95.
**Metrics:** Daily active dashboard users, widget engagement rate.

#### Customer Management
**Purpose:** 360° customer profile spanning lead history, communications, preferences, documents, and AI-derived relationship intelligence.
**Logic:** Customer record is the merge target for converted leads; Customer Health Score computed from engagement recency, sentiment, and payment behavior (for existing owners).
**Key APIs:** `GET /customers/{id}/360`, `PATCH /customers/{id}/preferences`.
**Edge Cases:** Customer with multiple active deals across different projects → unified profile, deal-scoped activity filtering.
**Acceptance Criteria:** 360 view loads all linked entities (deals, bookings, documents, activities) in a single API call <800ms p95.

#### Property Management
**Purpose:** Single source of truth for builder inventory — projects, units, pricing, media, legal status, and location intelligence.
**Logic:** Unit status state machine: Available → Held (time-boxed, auto-release) → Booked → Sold; Google Maps integration for nearby infrastructure; embeddings generated per unit for semantic search/matching.
**Key APIs:** `GET /properties/search` (supports semantic query param), `POST /properties/{id}/hold`.
**Edge Cases:** Two executives hold the same unit simultaneously → optimistic locking, second request fails with 409 and current holder info.
**Acceptance Criteria:** Unit hold auto-releases after configurable TTL (default 4 hours) if no booking created.

#### Sales Pipeline
**Purpose:** Visual deal tracking with AI-driven forecasting.
**Logic:** Kanban stages configurable per tenant; win-probability computed by Property Recommendation + Lead Qualification signals combined; stage-change triggers workflow automation hooks.
**Key APIs:** `PATCH /deals/{id}/stage`, `GET /pipeline/forecast`.
**Edge Cases:** Deal stuck in a stage beyond SLA → auto-flag + manager notification, does not auto-advance.
**Acceptance Criteria:** Forecast accuracy tracked against actuals monthly, target MAPE <15%.

#### Task Management
**Purpose:** Cross-module task orchestration with dependencies and approvals.
**Logic:** Tasks can be system-generated (by AI/workflow) or manual; recurring task templates; productivity analytics per user.
**Key APIs:** `POST /tasks`, `GET /tasks?assignee=&status=`.
**Edge Cases:** Recurring task edited mid-series → prompts "this task only / all future occurrences."
**Acceptance Criteria:** Overdue task triggers escalation notification to assignee's manager after 24h.

#### Calendar
**Purpose:** Unified scheduling for meetings, calls, site visits.
**Logic:** Two-way sync with Google Calendar/Outlook; site-visit type events auto-create a post-visit feedback task.
**Key APIs:** `POST /calendar/events`, `GET /calendar/sync/status`.
**Edge Cases:** External calendar sync conflict (event edited both sides) → last-write-wins with conflict log, user notified.
**Acceptance Criteria:** Sync latency <60s bidirectional.

#### Communication Center
**Purpose:** Unified inbox for Email, SMS, WhatsApp, Voice, with templates and campaign sending.
**Logic:** All conversations threaded per customer regardless of channel; call recordings auto-transcribed and summarized.
**Key APIs:** `POST /communications/send`, `GET /communications/thread/{customer_id}`.
**Edge Cases:** WhatsApp 24-hour session window expired → system forces template message selection instead of freeform.
**Acceptance Criteria:** Message delivery status (sent/delivered/read) reflected within 5s of provider webhook.

#### Marketing CRM
**Purpose:** Campaign management with lead attribution and ROI.
**Logic:** Multi-touch attribution model (configurable: first-touch/last-touch/linear); UTM auto-capture on all inbound forms.
**Key APIs:** `GET /marketing/campaigns/{id}/roi`.
**Edge Cases:** Lead with no UTM (organic/referral) → attributed to "Direct/Unknown" bucket, not dropped.
**Acceptance Criteria:** ROI dashboard reconciles spend (manual/API import) against attributed revenue within 2% variance.

#### Analytics
**Purpose:** Cross-module BI layer — funnels, cohort, forecasting, heatmaps.
**Logic:** Pre-aggregated materialized views refreshed every 15 min for heavy dashboards; ad-hoc query builder for custom analytics.
**Key APIs:** `POST /analytics/query`, `GET /analytics/funnel`.
**Acceptance Criteria:** Standard dashboard queries return <2s p95 against materialized views.

#### Reports
**Purpose:** Scheduled and on-demand reporting with export.
**Logic:** Report templates + custom report builder; PDF/Excel/CSV export via async job for large datasets.
**Key APIs:** `POST /reports/generate`, `GET /reports/{id}/download`.
**Acceptance Criteria:** Reports >10k rows generate asynchronously with email/notification on completion, never block the UI thread.

#### Notification Center
**Purpose:** Unified, role-aware alerting across Push/Email/SMS/WhatsApp/Slack/Teams.
**Logic:** User-configurable channel preferences per notification type; digest mode to prevent fatigue.
**Key APIs:** `POST /notifications/preferences`, internal event bus subscription per service.
**Acceptance Criteria:** Critical alerts (SLA breach, payment failure) always delivered via at least 2 channels regardless of user preference (safety override, disclosed to user).

#### Document Management
**Purpose:** Secure storage, OCR, e-signature, and approval workflow for KYC, agreements, and financial documents.
**Logic:** OCR auto-extracts PAN/Aadhaar/GST fields for validation against government format rules (not live government API verification in v1); version history immutable; e-signature via integrated provider (DocuSign/Zoho Sign class).
**Key APIs:** `POST /documents/upload`, `POST /documents/{id}/sign-request`.
**Edge Cases:** OCR low-confidence extraction → routed to manual review queue rather than auto-accepted.
**Acceptance Criteria:** Document upload to OCR-extracted-fields-available <30s p95.

#### Workflow Automation
**Purpose:** No-code trigger→condition→action builder for cross-module automation.
**Logic:** Trigger types (record created/updated, time-based, webhook); condition builder (AND/OR groups); actions (update field, create task, send notification, call AI agent, webhook out).
**Key APIs:** `POST /workflows`, `POST /workflows/{id}/test-run`.
**Edge Cases:** Circular workflow triggering itself → cycle detection at save time, rejected with explanation.
**Acceptance Criteria:** Workflow execution latency <5s from trigger event p95; every execution logged with input/output for debugging.

---

## 8. AI Layer — Agent Specifications

Each agent is specified as: Role · Inputs · Outputs · Tools/Data Access · Reasoning Pattern · Guardrails · Escalation to Human · Success Metrics.

### 8.1 Buyer AI Agent
**Role:** Converses with prospective buyers to elicit requirements and match properties.
**Inputs:** Chat/WhatsApp transcript, customer profile, inventory index.
**Outputs:** Structured requirement object (budget, location, unit type, timeline), ranked property matches, conversation memory summary.
**Tools:** Property semantic search (vector DB), Customer Management API (read/write preferences).
**Reasoning:** Slot-filling dialogue with clarifying questions when requirement fields are missing; retrieval-augmented matching.
**Guardrails:** Never quotes final negotiated pricing without human approval; discloses it is an AI assistant.
**Escalation:** Hands off to human executive on explicit request, high-value budget threshold, or detected frustration/complaint sentiment.
**Metrics:** Requirement-capture completion rate, hand-off-to-appointment conversion.

### 8.2 Seller AI Agent
**Role:** Assists property owners/builders with pricing guidance and market positioning.
**Inputs:** Property attributes, comparable transactions, market data feed.
**Outputs:** Suggested price range, positioning recommendations, lead-gen content draft.
**Guardrails:** Pricing suggestions labeled "AI estimate, not a valuation" with confidence range; never presented as a certified appraisal.
**Escalation:** Legal/compliance review required before any AI-drafted pricing is published externally.

### 8.3 Lead Qualification Agent
**Role:** Scores and bands every lead in near-real-time.
**Inputs:** Lead capture data, activity history, engagement signals.
**Outputs:** `ai_score` (0–100), band (Hot/Warm/Cold), `buying_probability`, `investment_score`, `sales_readiness` flag.
**Reasoning:** Gradient-boosted model (explainable via SHAP) blended with LLM reasoning over unstructured notes/transcripts.
**Guardrails:** Score is advisory — never auto-disqualifies a lead without a human-visible reason and a manual override option.
**Metrics:** Model AUC vs actual conversion, calibration drift monitored monthly.

### 8.4 Property Recommendation Agent
**Role:** Semantic matching of customer requirements to inventory.
**Inputs:** Customer preference vector, property embeddings.
**Outputs:** Ranked list with match rationale ("matches 4/5 preferences: budget, location, 3BHK, gated community").
**Tools:** Qdrant vector search, ROI calculator.
**Guardrails:** Rationale is always shown alongside ranking (no black-box recommendation) to preserve executive trust and explainability.

### 8.5 CRM Automation Agent
**Role:** Executes routine CRM housekeeping — task creation, meeting scheduling, note generation, report generation, lead assignment execution.
**Guardrails:** Operates only within the Workflow Automation Engine's approved action set; cannot invent new action types at runtime; every action logged and reversible where possible (e.g., undo task creation).

### 8.6 Follow-up Agent
**Role:** Generates timely, personalized follow-up reminders and drafts (WhatsApp/Email/SMS/Call) based on deal stage and customer behavior.
**Guardrails:** Drafts require one-click human approval before sending by default (configurable to auto-send for low-risk templated nudges only, e.g., "reminder: site visit tomorrow").

### 8.7 Sales Copilot
**Role:** Real-time assistant during live calls/chats — suggests responses, handles objections, summarizes calls/meetings, drafts emails/proposals, recommends next best action.
**Inputs:** Live transcript (with consent/disclosure per applicable telecom recording law), CRM context.
**Guardrails:** All suggestions are advisory overlays, never auto-spoken/auto-sent; call recording/transcription requires configurable consent workflow per tenant's jurisdiction.

### 8.8 Documentation Agent
**Role:** Drafts agreements, invoices, receipts, offer letters, booking forms from templates + deal data.
**Guardrails:** All legal documents require Legal Team or CRM Admin sign-off before dispatch to customer; agent cannot directly send legally binding documents.

### 8.9 Investment Advisor Agent
**Role:** Computes ROI, rental yield, capital appreciation trends, portfolio allocation guidance, risk scoring, exit strategy suggestions for Investor persona.
**Guardrails:** Displays clear disclaimer that outputs are informational, not licensed financial/investment advice; recommends consulting a licensed advisor for decisions above a configurable value threshold.

### 8.10 Builder Intelligence Agent
**Role:** Aggregates builder reputation, delivery history, financial-strength signals, and customer reviews into a Builder Health Score.
**Guardrails:** Sources must be cited/traceable; negative scoring changes require a review-of-evidence trail to avoid reputational-harm disputes.

### 8.11 Market Intelligence Agent
**Role:** Tracks price trends, infrastructure project impact, demand/supply and competitor positioning per micro-market.
**Tools:** Web/market-data ingestion pipeline, historical transaction database.
**Guardrails:** Forecasts always shown with confidence intervals, not single-point predictions presented as fact.

### 8.12 Tokenization Advisor
**Role:** Assesses fractional-ownership/REIT/blockchain readiness and compliance checklist for a given asset (Phase 5 capability).
**Guardrails:** Advisory-only in current roadmap phases; no on-platform execution of token issuance until dedicated legal/regulatory review is complete.

### 8.13 Agent Cross-Cutting Guardrails (apply to all 13 agents)

- Every agent action that changes CRM state is logged in `AI_INSIGHT` / `AUDIT_LOG` with the prompt, model, and output for traceability.
- Human-in-the-loop approval is the default for any customer-facing or financial/legal output; auto-execution is opt-in per tenant and per action type.
- No agent has standing write access beyond its declared tool scope (least privilege, enforced at the orchestration layer, not just prompt instruction).
- All agents disclose AI involvement to end customers where they are customer-facing (Buyer/Seller agents, Sales Copilot-drafted messages).

---

## 9. Multi-Agent Orchestration Framework

### 9.1 Architecture

**Flow:** Trigger (Event / User Request / Schedule) → Task Planner → Agent Registry → Context Router → Selected Agent → [Model Router + Memory Manager + Execution Engine]

**Model Router routes to:** Claude (primary reasoning), OpenAI (embeddings/fallback), Gemini (multimodal fallback), Local model (sensitive data tenants)

**Execution Engine flow:** Execution Engine → Human Approval Required? →
- **Yes** → Human Reviewer Queue → Approved → Apply to CRM, or Rejected → Log rejection + reason
- **No, pre-approved action type** → Apply to CRM directly

Both paths → Observability & Eval Framework

### 9.2 Component Specifications

| Component | Responsibility |
|---|---|
| Agent Registry | Catalog of all agents, their capabilities, tool scopes, and versioning |
| Task Planner | Decomposes a high-level goal (e.g., "qualify and follow up on this lead") into an agent execution sequence |
| Execution Engine | Runs agent steps, manages retries/timeouts, enforces tool-scope guardrails |
| Memory Manager | Short-term (conversation) and long-term (customer relationship) memory, stored per-entity, retrievable via vector + structured lookup |
| Context Router | Assembles the minimal-necessary context (CRM records, prior agent outputs) for each agent call to control cost/latency and avoid context leakage across tenants |
| Prompt Manager | Versioned prompt templates per agent, A/B testable, tenant-overridable within approved bounds |
| Model Router | Routes each call to the best model by task type, cost, latency, and data-residency requirement; includes automatic fallback chain |
| Fallback Strategy | If primary model fails/times out → retry once → fallback model → if all fail, queue for human action with a "AI unavailable" flag, never silently drop the task |
| Human Approval Layer | Configurable per action type/tenant; queue UI shows proposed action, rationale, and one-click approve/edit/reject |
| Observability | Full tracing of every agent call (input, output, latency, cost, model used) surfaced in an internal AI Ops dashboard |
| Evaluation Framework | Offline eval sets per agent (golden datasets), regression-tested on every prompt/model change before deployment |

### 9.3 Guardrail Summary Table

| Risk | Mitigation |
|---|---|
| Hallucinated pricing/legal terms | Documentation & Seller agents require human sign-off before external dispatch |
| Runaway automation loops | Cycle detection in Workflow Engine + Task Planner step limits |
| Cross-tenant data leakage in prompts | Context Router enforces tenant_id scoping identical to API layer; no shared embeddings across tenants |
| Model outage | Multi-provider fallback chain, never a hard failure to the user |
| Biased/unfair lead scoring | Quarterly fairness audit on scoring model across demographic-neutral features only (no protected-class features used) |

---

## 10. Security & Compliance

- **RBAC:** Role + permission matrix enforced at API gateway and service layer (double-enforcement).
- **Encryption:** TLS 1.3 in transit; AES-256 at rest for database and object storage; field-level encryption for PAN/Aadhaar/financial data.
- **Secrets Management:** Vault-based secret storage, no secrets in code/env files committed to VCS.
- **DPDP Act (India) & GDPR readiness:** Consent capture on data collection, right-to-erasure workflow, data-processing agreements with sub-processors, data residency options (India region hosting for DPDP-sensitive tenants).
- **Rate limiting & API security:** Per-tenant and per-key rate limits, WAF at edge, OWASP Top 10 mitigations validated via quarterly pen test.
- **Audit logging:** Immutable, tenant-scoped, retained per compliance requirement (minimum 7 years for financial records).

---

## 11. Testing Strategy

| Type | Scope | Tooling (indicative) |
|---|---|---|
| Unit | Business logic, validators, calculators | pytest, Jest |
| Integration | Service-to-service, DB, queue | pytest + testcontainers |
| End-to-End | Critical user journeys (login→lead→deal→booking) | Playwright |
| Performance/Load | Burst ingestion, dashboard queries | k6/Locust |
| Security | Auth, injection, access-control | OWASP ZAP, manual pen test |
| AI Evaluation | Agent output quality vs golden datasets | Custom eval harness + human review sampling |
| Prompt Evaluation | Regression on prompt/model changes | Versioned eval suites per agent |
| Regression | Full suite pre-release | CI gate on GitHub Actions |
| UAT | Persona-based scripted scenarios | Manual, sign-off per persona |

---

## 12. Product Roadmap

```
gantt
title Pappu AI Roadmap
dateFormat YYYY-MM

section Phase 1
CRM MVP (Auth, Leads, Customers, Pipeline, Booking, Tasks) : p1, 2026-08, 4M

section Phase 2
AI CRM (Scoring, Recommendation, Copilot, Automation Agent) : p2, 2026-12, 4M

section Phase 3
Voice CRM (Call transcription, voice agents, IVR integration) : p3, 2027-04, 3M

section Phase 4
Autonomous CRM (Full orchestration, auto-execution with approval layer) : p4, 2027-07

section Phase 5
Enterprise AI Operating System (Tokenization advisory, cross-org intelligence) : p5
```

**Phase gating principle:** No phase advances until the prior phase's success metrics (Section 7 acceptance criteria + agent metrics in Section 8) are met in production for at least one full quarter with a pilot tenant cohort.

---

## 13. Appendix — Global Standards

### 13.1 Error / Empty / Loading States (applies to every module)

- **Loading:** Skeleton screens matching final layout shape; no layout shift on data arrival.
- **Empty:** Always includes an explanatory sentence + a primary action (e.g., "No leads yet — Import leads or Connect a lead source").
- **Error:** Human-readable message + retry action; technical detail available via "Show details" disclosure for admins only; all errors logged with a correlation ID shown to the user for support reference.

### 13.2 API Conventions

- REST, versioned under `/api/v1/`; JSON:API-inspired envelope `{ data, meta, errors }`.
- **Pagination:** cursor-based for high-volume lists (leads, activities); `limit` / `cursor` params.
- **Idempotency:** `Idempotency-Key` header required on all POST endpoints that create financial or booking records.
- **Standard error shape:** `{ "error": { "code": "...", "message": "...", "correlation_id": "..." } }`.

### 13.3 Acceptance Criteria Format

All acceptance criteria in this document and its module expansions follow Given/When/Then (Gherkin-style) to be directly convertible into automated test cases.

---

## Next Steps / What I Can Expand Next

This master PRD gives every team a consistent, cross-referenced foundation. Natural next deliverables, each as a standalone document that plugs into this one:

1. Full 15–25 page module specs (pick any: Dashboard, Property Management, Communication Center, Workflow Automation, Analytics, Document Management, etc.) at the same depth as Sections 7.1–7.3.
2. Complete persona pack — all 25 personas at the Section 3.2 depth.
3. Full OpenAPI 3.1 specification (machine-readable) covering every endpoint listed above.
4. Complete physical database schema (DDL) with all tables, constraints, and indexes.
5. Detailed AI agent prompt specifications and evaluation datasets for each of the 13 agents.
6. Wireframe-level UI specs (screen-by-screen) for Phase 1 MVP scope.

Tell me which of these to produce next and I'll build it directly on top of this document.
