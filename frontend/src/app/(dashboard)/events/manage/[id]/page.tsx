"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ExternalLink, Plus, QrCode, Trash2 } from "lucide-react";
import { API_BASE, api, errorMessage } from "@/lib/api";
import { useApiSWR } from "@/lib/useApiSWR";
import { Badge, Button, Card, Input, Spinner, Textarea } from "@/components/ui";
import { formatDateTime } from "@/lib/format";

interface Speaker {
  id: string; name: string; title: string | null; bio: string | null;
}
interface AgendaItem {
  id: string; start_time: string; title: string; description: string | null;
}
interface EventDetail {
  id: string; name: string; slug: string; description: string | null; venue: string | null;
  start_at: string; end_at: string; status: "draft" | "published" | "completed";
  cta_text: string; total_ad_spend: string | null;
  speakers: Speaker[]; agenda_items: AgendaItem[];
}
interface Registration {
  id: string; full_name: string; email: string; phone: string | null; company: string | null;
  stage: string; checked_in_at: string | null; referral_code: string; referred_by_code: string | null;
  lead_id: string | null;
}
interface Dashboard {
  total_registrations: number; rsvp_confirmed: number; attended: number; no_show: number;
  rsvp_rate: number; attendance_rate: number; checkin_rate: number;
  total_ad_spend: string | null; cost_per_lead: string | null; by_source: Record<string, number>;
}

const TABS = ["Overview", "Registrations", "Check-in", "Dashboard"] as const;
type Tab = (typeof TABS)[number];

const STAGE_COLORS: Record<string, string> = {
  registered: "#8b98ac", rsvp_confirmed: "#3b82f6", attended: "#10b981",
  no_show: "#ef4444", cancelled: "#8b98ac",
};

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<Tab>("Overview");
  const { data, mutate } = useApiSWR<{ data: EventDetail }>(`/events/${id}`);
  const event = data?.data;

  if (!event) return <Spinner />;

  return (
    <div className="fade-up">
      <div className="mb-4 flex items-center gap-3">
        <Link href="/events" className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-ink">
          <ArrowLeft size={16} />
        </Link>
        <div className="flex-1">
          <h1 className="text-lg font-semibold">{event.name}</h1>
          <p className="text-xs text-muted">/events/{event.slug}</p>
        </div>
        <Badge color={event.status === "published" ? "#10b981" : event.status === "completed" ? "#3b82f6" : "#8b98ac"}>
          {event.status}
        </Badge>
        {event.status === "published" && (
          <a href={`/events/${event.slug}`} target="_blank" rel="noreferrer">
            <Button variant="secondary" size="sm"><ExternalLink size={12} /> View live page</Button>
          </a>
        )}
      </div>

      <div className="mb-4 flex gap-1 border-b border-edge">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`border-b-2 px-3 py-2 text-xs font-medium transition-colors ${
              tab === t ? "border-primary text-primary" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && <OverviewTab event={event} onChanged={() => mutate()} />}
      {tab === "Registrations" && <RegistrationsTab eventId={event.id} />}
      {tab === "Check-in" && <CheckinTab eventId={event.id} />}
      {tab === "Dashboard" && <DashboardTab eventId={event.id} />}
    </div>
  );
}

/* --------------------------------------------------------------- Overview */

function OverviewTab({ event, onChanged }: { event: EventDetail; onChanged: () => void }) {
  const [form, setForm] = useState({
    name: event.name, description: event.description ?? "", venue: event.venue ?? "",
    cta_text: event.cta_text, total_ad_spend: event.total_ad_spend ?? "",
    status: event.status,
  });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [speakerForm, setSpeakerForm] = useState({ name: "", title: "" });
  const [agendaForm, setAgendaForm] = useState({ start_time: "", title: "" });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api(`/events/${event.id}`, {
        method: "PATCH",
        body: {
          ...form,
          total_ad_spend: form.total_ad_spend ? Number(form.total_ad_spend) : null,
        },
      });
      onChanged();
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(errorMessage(err, "Failed to save."));
    }
  }

  async function addSpeaker(e: React.FormEvent) {
    e.preventDefault();
    if (!speakerForm.name.trim()) return;
    await api(`/events/${event.id}/speakers`, { method: "POST", body: speakerForm });
    setSpeakerForm({ name: "", title: "" });
    onChanged();
  }

  async function removeSpeaker(speakerId: string) {
    await api(`/events/${event.id}/speakers/${speakerId}`, { method: "DELETE" });
    onChanged();
  }

  async function addAgendaItem(e: React.FormEvent) {
    e.preventDefault();
    if (!agendaForm.title.trim() || !agendaForm.start_time) return;
    await api(`/events/${event.id}/agenda`, {
      method: "POST",
      body: { ...agendaForm, start_time: new Date(agendaForm.start_time).toISOString() },
    });
    setAgendaForm({ start_time: "", title: "" });
    onChanged();
  }

  async function removeAgendaItem(itemId: string) {
    await api(`/events/${event.id}/agenda/${itemId}`, { method: "DELETE" });
    onChanged();
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="space-y-3 p-4">
        <p className="text-xs font-semibold">Event details</p>
        <form onSubmit={save} className="space-y-3">
          {error && <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>}
          <Input label="Name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          <Textarea label="Description" value={form.description}
                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          <Input label="Venue" value={form.venue} onChange={(e) => setForm((f) => ({ ...f, venue: e.target.value }))} />
          <Input label="Registration button text" value={form.cta_text}
                 onChange={(e) => setForm((f) => ({ ...f, cta_text: e.target.value }))} />
          <Input label="Total ad spend, ₹ (for cost-per-lead)" type="number" min={0}
                 value={form.total_ad_spend}
                 onChange={(e) => setForm((f) => ({ ...f, total_ad_spend: e.target.value }))} />
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-muted">Status</span>
            <select
              value={form.status}
              onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as EventDetail["status"] }))}
              className="w-full rounded-lg border border-edge-strong bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-primary focus:ring-2 focus:ring-primary/25"
            >
              <option value="draft">Draft (not public)</option>
              <option value="published">Published (public)</option>
              <option value="completed">Completed</option>
            </select>
          </label>
          <div className="flex items-center gap-2">
            <Button type="submit">Save changes</Button>
            {saved && <span className="text-xs text-success">Saved</span>}
          </div>
        </form>
      </Card>

      <div className="space-y-4">
        <Card className="p-4">
          <p className="mb-3 text-xs font-semibold">Speakers</p>
          <ul className="mb-3 space-y-2">
            {event.speakers.map((s) => (
              <li key={s.id} className="flex items-center justify-between rounded-lg border border-edge px-3 py-2">
                <div>
                  <p className="text-xs font-medium">{s.name}</p>
                  {s.title && <p className="text-[10px] text-faint">{s.title}</p>}
                </div>
                <button onClick={() => removeSpeaker(s.id)} className="text-faint hover:text-danger">
                  <Trash2 size={13} />
                </button>
              </li>
            ))}
          </ul>
          <form onSubmit={addSpeaker} className="flex gap-2">
            <input
              placeholder="Name" value={speakerForm.name}
              onChange={(e) => setSpeakerForm((f) => ({ ...f, name: e.target.value }))}
              className="flex-1 rounded-lg border border-edge-strong bg-bg px-2.5 py-1.5 text-xs outline-none focus:border-primary"
            />
            <input
              placeholder="Title" value={speakerForm.title}
              onChange={(e) => setSpeakerForm((f) => ({ ...f, title: e.target.value }))}
              className="flex-1 rounded-lg border border-edge-strong bg-bg px-2.5 py-1.5 text-xs outline-none focus:border-primary"
            />
            <Button size="sm" type="submit"><Plus size={12} /></Button>
          </form>
        </Card>

        <Card className="p-4">
          <p className="mb-3 text-xs font-semibold">Agenda</p>
          <ul className="mb-3 space-y-2">
            {event.agenda_items.map((a) => (
              <li key={a.id} className="flex items-center justify-between rounded-lg border border-edge px-3 py-2">
                <div>
                  <p className="text-[10px] text-primary">{formatDateTime(a.start_time)}</p>
                  <p className="text-xs font-medium">{a.title}</p>
                </div>
                <button onClick={() => removeAgendaItem(a.id)} className="text-faint hover:text-danger">
                  <Trash2 size={13} />
                </button>
              </li>
            ))}
          </ul>
          <form onSubmit={addAgendaItem} className="flex gap-2">
            <input
              type="datetime-local" value={agendaForm.start_time}
              onChange={(e) => setAgendaForm((f) => ({ ...f, start_time: e.target.value }))}
              className="rounded-lg border border-edge-strong bg-bg px-2.5 py-1.5 text-xs outline-none focus:border-primary"
            />
            <input
              placeholder="Title" value={agendaForm.title}
              onChange={(e) => setAgendaForm((f) => ({ ...f, title: e.target.value }))}
              className="flex-1 rounded-lg border border-edge-strong bg-bg px-2.5 py-1.5 text-xs outline-none focus:border-primary"
            />
            <Button size="sm" type="submit"><Plus size={12} /></Button>
          </form>
        </Card>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- Registrations */

function RegistrationsTab({ eventId }: { eventId: string }) {
  const { data } = useApiSWR<{ data: Registration[] }>(`/events/${eventId}/registrations`);
  const rows = data?.data ?? [];

  return (
    <Card className="overflow-x-auto p-4">
      <table className="w-full min-w-[50rem] text-left text-xs">
        <thead>
          <tr className="border-b border-edge text-[10px] uppercase text-faint">
            <th className="py-1.5 font-medium">Name</th>
            <th className="py-1.5 font-medium">Contact</th>
            <th className="py-1.5 font-medium">Company</th>
            <th className="py-1.5 font-medium">Stage</th>
            <th className="py-1.5 font-medium">Referral</th>
            <th className="py-1.5 font-medium">Lead</th>
            <th className="py-1.5 font-medium">Badge</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-edge/50 last:border-0">
              <td className="py-2 font-medium">{r.full_name}</td>
              <td className="py-2 text-muted">{r.email}<br />{r.phone}</td>
              <td className="py-2 text-muted">{r.company ?? "—"}</td>
              <td className="py-2"><Badge color={STAGE_COLORS[r.stage]}>{r.stage.replace(/_/g, " ")}</Badge></td>
              <td className="py-2 text-muted">
                {r.referral_code}
                {r.referred_by_code && <span className="block text-[10px] text-faint">via {r.referred_by_code}</span>}
              </td>
              <td className="py-2">
                {r.lead_id ? (
                  <Link href={`/leads/${r.lead_id}`} className="text-primary hover:underline">View lead</Link>
                ) : "—"}
              </td>
              <td className="py-2">
                <a
                  href={`${API_BASE}/events/${eventId}/registrations/${r.id}/badge.pdf`}
                  target="_blank" rel="noreferrer" className="text-primary hover:underline"
                >
                  Print badge
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="py-8 text-center text-xs text-faint">No registrations yet.</p>}
    </Card>
  );
}

/* --------------------------------------------------------------- Check-in */

function CheckinTab({ eventId }: { eventId: string }) {
  const [status, setStatus] = useState<{ kind: "idle" | "ok" | "error"; message: string }>({
    kind: "idle", message: "Point the camera at an attendee's QR code.",
  });
  const [manualToken, setManualToken] = useState("");
  const scannerRef = useRef<import("html5-qrcode").Html5Qrcode | null>(null);
  const lastScanned = useRef<string>("");

  const checkIn = useCallback(async (token: string) => {
    if (!token || token === lastScanned.current) return;
    lastScanned.current = token;
    try {
      const res = await api<{ data: Registration }>(`/events/${eventId}/checkin`, {
        method: "POST", body: { token },
      });
      setStatus({ kind: "ok", message: `Checked in: ${res.data.full_name}` });
    } catch (err) {
      setStatus({ kind: "error", message: errorMessage(err, "Check-in failed.") });
    } finally {
      setTimeout(() => (lastScanned.current = ""), 3000); // allow re-scanning after a pause
    }
  }, [eventId]);

  useEffect(() => {
    let cancelled = false;
    let started = false;
    import("html5-qrcode").then(({ Html5Qrcode }) => {
      if (cancelled) return;
      const scanner = new Html5Qrcode("checkin-scanner");
      scannerRef.current = scanner;
      scanner
        .start(
          { facingMode: "environment" },
          { fps: 10, qrbox: 220 },
          (decodedText) => checkIn(decodedText),
          () => {}
        )
        .then(() => {
          started = true;
        })
        .catch(() =>
          setStatus({ kind: "error", message: "Camera unavailable — use manual entry below instead." })
        );
    });
    return () => {
      cancelled = true;
      // .stop() throws (and logs) if the camera never actually started —
      // e.g. no camera present/permission denied — so only call it once
      // start() has genuinely resolved.
      if (started) scannerRef.current?.stop().catch(() => {});
    };
  }, [checkIn]);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-4">
        <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold"><QrCode size={14} /> Scan QR code</p>
        <div id="checkin-scanner" className="overflow-hidden rounded-lg bg-black" />
        <p
          className={`mt-3 text-xs ${
            status.kind === "ok" ? "text-success" : status.kind === "error" ? "text-danger" : "text-muted"
          }`}
        >
          {status.message}
        </p>
      </Card>
      <Card className="p-4">
        <p className="mb-3 text-xs font-semibold">Manual entry</p>
        <p className="mb-2 text-[11px] text-faint">If the camera can&apos;t scan, paste the check-in code from the registrations tab.</p>
        <form
          onSubmit={(e) => { e.preventDefault(); checkIn(manualToken); setManualToken(""); }}
          className="flex gap-2"
        >
          <input
            value={manualToken} onChange={(e) => setManualToken(e.target.value)}
            placeholder="Check-in code"
            className="flex-1 rounded-lg border border-edge-strong bg-bg px-3 py-2 text-xs outline-none focus:border-primary"
          />
          <Button size="sm" type="submit">Check in</Button>
        </form>
      </Card>
    </div>
  );
}

/* --------------------------------------------------------------- Dashboard */

function DashboardTab({ eventId }: { eventId: string }) {
  const { data } = useApiSWR<{ data: Dashboard }>(`/events/${eventId}/dashboard`);
  const dash = data?.data;
  if (!dash) return <Spinner />;

  const stats: [string, string | number][] = [
    ["Registrations", dash.total_registrations],
    ["RSVP rate", `${dash.rsvp_rate}%`],
    ["Attendance rate", `${dash.attendance_rate}%`],
    ["Check-in rate", `${dash.checkin_rate}%`],
    ["No-shows", dash.no_show],
    ["Cost per lead", dash.cost_per_lead ? `₹${Number(dash.cost_per_lead).toLocaleString("en-IN")}` : "—"],
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {stats.map(([label, value]) => (
          <Card key={label} className="p-3">
            <p className="text-[10px] uppercase tracking-wide text-faint">{label}</p>
            <p className="mt-1 text-lg font-semibold">{value}</p>
          </Card>
        ))}
      </div>
      <Card className="p-4">
        <p className="mb-3 text-xs font-semibold">Registrations by source</p>
        <div className="space-y-1.5">
          {Object.entries(dash.by_source).map(([source, count]) => (
            <div key={source} className="flex items-center justify-between text-xs">
              <span className="text-muted">{source.replace(/_/g, " ")}</span>
              <span className="font-medium">{count}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
