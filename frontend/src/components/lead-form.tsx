"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, ErrorNote, Input, Modal, Select, Textarea } from "@/components/ui";
import { STAGE_LABELS } from "@/lib/format";

const SOURCES = [
  "website", "walk_in", "referral", "channel_partner", "meta_ads", "google_ads",
  "whatsapp", "phone_inquiry", "property_portal", "event", "other",
];

interface DuplicateMatch {
  lead_id: string;
  full_name: string;
  phone: string;
  email: string | null;
  stage: string;
  match_type: string;
}

export function LeadFormModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const empty = {
    full_name: "", phone: "", email: "", source: "website", campaign: "",
    budget_min: "", budget_max: "", location_preference: "", property_type: "",
    requirements: "",
  };
  const [form, setForm] = useState(empty);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [duplicates, setDuplicates] = useState<DuplicateMatch[] | null>(null);

  const set = (k: string) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(force: boolean) {
    setError("");
    setBusy(true);
    try {
      if (!force) {
        // Duplicate pre-check → prompt user before creating (Task 6).
        const check = await api<{ data: DuplicateMatch[] }>("/leads/check-duplicates", {
          method: "POST",
          body: { phone: form.phone, email: form.email || null, full_name: form.full_name },
        });
        if (check.data.length > 0) {
          setDuplicates(check.data);
          setBusy(false);
          return;
        }
      }
      await api("/leads", {
        method: "POST",
        body: {
          ...form,
          email: form.email || null,
          campaign: form.campaign || null,
          budget_min: form.budget_min || null,
          budget_max: form.budget_max || null,
          location_preference: form.location_preference || null,
          property_type: form.property_type || null,
          requirements: form.requirements || null,
          force,
        },
      });
      setForm(empty);
      setDuplicates(null);
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create lead.");
      setDuplicates(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add lead" wide>
      {duplicates ? (
        <div className="space-y-4">
          <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-3">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" />
            <div className="text-xs">
              <p className="font-medium text-warning">Possible duplicate lead</p>
              <p className="mt-1 text-muted">
                {duplicates.length} existing lead(s) match this entry. Create anyway?
              </p>
            </div>
          </div>
          <ul className="space-y-2">
            {duplicates.map((d) => (
              <li key={d.lead_id} className="flex items-center justify-between rounded-lg border border-edge px-3 py-2 text-xs">
                <span>
                  <b>{d.full_name}</b> · {d.phone} {d.email ? `· ${d.email}` : ""}
                </span>
                <span className="text-faint">
                  matched by {d.match_type} · {STAGE_LABELS[d.stage] ?? d.stage}
                </span>
              </li>
            ))}
          </ul>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDuplicates(null)}>Back</Button>
            <Button variant="danger" disabled={busy} onClick={() => submit(true)}>
              Create duplicate anyway
            </Button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(false);
          }}
          className="space-y-4"
        >
          {error && <ErrorNote message={error} />}
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Full name *" required minLength={2} value={form.full_name}
                   onChange={set("full_name")} />
            <Input label="Phone *" required minLength={7} value={form.phone}
                   onChange={set("phone")} placeholder="98765 43210" />
            <Input label="Email" type="email" value={form.email} onChange={set("email")} />
            <Select label="Source" value={form.source} onChange={set("source")}>
              {SOURCES.map((s) => (
                <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
              ))}
            </Select>
            <Input label="Budget min (₹)" type="number" min={0} value={form.budget_min}
                   onChange={set("budget_min")} />
            <Input label="Budget max (₹)" type="number" min={0} value={form.budget_max}
                   onChange={set("budget_max")} />
            <Input label="Preferred location" value={form.location_preference}
                   onChange={set("location_preference")} placeholder="Whitefield, Bangalore" />
            <Input label="Property type" value={form.property_type}
                   onChange={set("property_type")} placeholder="3BHK Apartment" />
          </div>
          <Input label="Campaign" value={form.campaign} onChange={set("campaign")}
                 placeholder="summer-2026 (optional)" />
          <Textarea label="Requirements" value={form.requirements}
                    onChange={set("requirements")}
                    placeholder="East-facing, near schools…" />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Checking…" : "Create lead"}</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
