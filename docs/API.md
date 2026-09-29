# API Mapping

Base URL `/api/v1` · JSON envelope `{ data, meta }` / `{ error: { code, message, correlation_id } }` ·
Interactive OpenAPI docs at `/api/docs`. All endpoints require `Authorization: Bearer <access>`
unless marked public. RBAC scope (ALL / TEAM / OWN) is applied per role — see
`docs/ARCHITECTURE.md` §5.

| Module | Method & Path | Purpose |
|---|---|---|
| Auth | POST `/auth/register` (public) | Self-registration (first user → Super Admin, others → Sales Executive) |
| | POST `/auth/login` (public) | Login → access token + rotating refresh cookie; lockout after 5 failures/10 min |
| | POST `/auth/refresh` (public+cookie) | Rotate refresh token (reuse detection revokes family) |
| | POST `/auth/logout` | Revoke session family |
| | POST `/auth/password/forgot` · `/auth/password/reset` (public) | Reset flow, 15-min single-use links |
| | POST `/auth/verify-email` (public) | Email verification |
| | GET `/auth/me` · GET/DELETE `/auth/sessions[/{id}]` | Profile, session list & revocation |
| Users | GET/POST `/users` · GET/PATCH/DELETE `/users/{id}` · PATCH `/users/{id}/role` | Admin user management |
| Leads | GET/POST `/leads` · GET/PATCH/DELETE `/leads/{id}` | CRUD with filters (`q`, `stage`, `source`, `assigned_to`, `score_band`) |
| | POST `/leads/check-duplicates` | Pre-create duplicate probe (phone/email/fuzzy name) |
| | POST `/leads/import` · GET `/leads/export` | CSV import (row errors, dedupe skip) / export |
| | POST `/leads/{id}/assign` · `/{id}/notes` · `/{id}/tags` · DELETE `/{id}/tags/{tagId}` | Assignment, notes, tags |
| | GET `/leads/{id}/timeline` · POST `/leads/{id}/convert` | Activity timeline, convert to customer |
| Pipeline | GET `/pipeline/board` · PATCH `/pipeline/leads/{id}/stage` | Kanban board & stage moves |
| Customers | GET/POST `/customers` · GET/PATCH/DELETE `/customers/{id}` · GET `/customers/{id}/360` | Profiles + aggregated 360 view |
| Properties | GET `/properties` · GET `/properties/{id}` · POST `/properties/projects` (admin) | Inventory search & management |
| | POST `/properties/{id}/shortlist|favourite|attach` · DELETE `/properties/links/{id}` | Customer-property relations |
| | POST `/properties/compare` · GET `/properties/customer/{id}` | Unit comparison, customer links |
| Bookings | GET/POST `/bookings` · GET `/bookings/{id}` | Booking workflow records |
| | POST `/bookings/{id}/advance-stage` · `/{id}/payments` · `/{id}/cancel` · GET `/{id}/payments` | Stage machine, payments (receipts, overpayment guard), cancellation |
| Tasks | GET/POST `/tasks` · GET/PATCH/DELETE `/tasks/{id}` · POST `/tasks/{id}/comments` · `/{id}/attachments` | Task management |
| Calendar | GET/POST `/calendar` · PATCH/DELETE `/calendar/{id}` | Events; `?team=true` for team view, `start`/`end` range |
| Notifications | GET `/notifications` · PATCH `/notifications/{id}/read` · POST `/notifications/read-all` | In-app center (lazy due-soon reminders) |
| AI | GET `/ai/catalog` | What this workspace may run (`widgets`/`components`), the full catalogue (`all_*`), the active provider, and the tenant's AI consent state. `no-store` — it is a policy answer |
| | POST `/ai/widgets/{widget}` | lead-summary, customer-summary, suggestions, next-best-action, investment-insights, sales-tips, property-recommendations |
| | POST `/ai/components/{component}` | lead-qualification, buyer-assistant, property-recommendation, follow-up, email-generator, whatsapp-assistant, call-summary, customer-insights |
| | POST `/ai/chat` | One conversational turn — extracts requirements, replies with the gap (STAIL `agents/chat`) |
| | POST `/ai/orchestrate` | Full pipeline: extract → rank inventory → grade → write back (STAIL `agents/orchestrate`) |
| | GET `/ai/insights/{entity_type}/{entity_id}` | Persisted insight history |
| Onboarding | GET `/onboarding/steps` (admin) | The 12-page form registry, each mapped to its source spec |
| | GET `/onboarding/state` · PATCH `/onboarding/step` | Read/save one form page |
| | POST `/onboarding/upload` · GET/DELETE `/onboarding/documents[/{id}]` | Workspace assets → tenant-scoped documents |
| | POST `/onboarding/complete` | Creates inventory, imports the pipeline, sends invites |
| Timeline | GET `/timeline/{entity_type}/{entity_id}?types=` | Filterable chronological activity (Task 15) |
| Analytics | GET `/analytics/overview` · `/funnel` · `/revenue` · `/team` · `/sources` | Live dashboards; `overview` also returns `month_to_date` and `targets` (month-to-date progress against the onboarding targets, empty when none were set) |
| Reports | GET `/reports/catalog` · POST `/reports/generate` | 6 report types × csv/xlsx/pdf (file response) |
| Documents | POST `/documents/upload` · GET `/documents[/{id}]` · POST `/documents/{id}/version` · GET `/documents/{id}/download?version=` | Versioned document store |
| Audit | GET `/audit` (admin) | Immutable audit trail |
| Health | GET `/api/health` (public) | Liveness probe |
