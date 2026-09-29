# User & Admin Manual

## Signing in

Open the app → **Sign in**. New users can self-register (they start as Sales
Executive; an admin assigns the real role under **Settings → Team & roles**).
Five failed logins lock the account for 15 minutes. **Forgot password** emails
a 15-minute single-use reset link (in dev, links appear in the API console /
`email_outbox` table).

## Daily flow (Sales Executive)

1. **Dashboard** — KPIs, funnel, and your open tasks.
2. **Leads** — work the table (search/filter), or **Pipeline** for the Kanban
   view; drag cards between stages. Moving to *Lost* asks for a reason.
3. Open a lead → log **notes**, add **tags**, and use the **Ask Pappu** dock:
   - *Summarize* — profile + engagement summary and data gaps
   - *Score lead* — 0–100 with explanation; writes the hot/warm/cold band
   - *Next action* — stage-appropriate recommendation
   - *Draft follow-up* — WhatsApp/email drafts (always review before sending)
4. **Convert to customer** once qualified → the customer 360 page collects
   profile, family, preferences, linked properties, bookings and a filterable
   timeline.
5. **Properties** — browse inventory, *Shortlist/Favourite/Attach* units to a
   customer, select 2–4 units and **Compare**.
6. **Bookings** — *New booking* (customer + available unit + value). Advance
   through Site Visit → Booking → Documentation → Payment → Possession with
   the stepper. Record payments at the Payment stage (receipts auto-numbered;
   possession is blocked until fully paid). Cancelling frees the unit.
7. **Tasks / Calendar** — assignments notify the assignee; due-soon items
   generate reminders in the bell tray.
8. **Documents** — upload KYC/agreements/receipts; every re-upload creates a
   new version with full history.

## Admin guide

- **Settings → Team & roles** — create members with a role, change roles
  (admins only), deactivate users (immediately blocks login).
- **Properties** — admins create projects with units (`POST /properties/projects`
  or via API docs UI).
- **Reports** — six report types exportable as CSV/Excel/PDF, scoped to your role.
- **Audit** — `GET /api/v1/audit` lists every mutating action (who, what, when,
  from which IP): logins, role changes, lead edits, payments, cancellations.
- **Sessions** — Settings shows active sessions per user; revoke any device.
  Password reset revokes all sessions automatically.

## Demo walkthrough script (Task 22)

1. Seed (`python -m app.db.seed`) and sign in as `manager@pappuai.com`.
2. Show role-scoped dashboard, then the **Pipeline** with 10 seeded leads
   across all 9 stages; drag *Rahul Sharma* from New → Contacted.
3. Open the lead → run all four **Ask Pappu** actions; show the score landing
   on the lead and in the timeline.
4. Create a lead with phone `9876543210` → duplicate warning appears → cancel.
5. Import `leads.csv` → show import summary (imported/skipped/errors).
6. Open *Vikram Malhotra* (converted customer) → 360 view: booking at Payment
   stage, ₹30L collected, timeline.
7. Open his **booking** → record the outstanding payment → advance to
   Possession → Completed; unit flips to *sold* in Properties.
8. Show **Analytics** (funnel, revenue, team, sources) reflecting the demo
   actions live, then export a **Sales Report** as PDF.
9. Upload an agreement in **Documents**, upload a second version, download v1.
10. Sign in as `exec1@pappuai.com` in another browser to show scope isolation
    (only own leads) and the assignment notification in the bell tray.
