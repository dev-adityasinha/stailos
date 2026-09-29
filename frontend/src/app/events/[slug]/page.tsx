"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Calendar, MapPin, Users } from "lucide-react";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { initEventTracking, trackEventPageView, trackRegistration } from "@/lib/eventTracking";

interface Speaker {
  id: string;
  name: string;
  title: string | null;
  bio: string | null;
  photo_url: string | null;
}

interface AgendaItem {
  id: string;
  start_time: string;
  title: string;
  description: string | null;
  speaker_id: string | null;
}

interface EventDetail {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  venue: string | null;
  start_at: string;
  end_at: string;
  cta_text: string;
  hero_image_url: string | null;
  speakers: Speaker[];
  agenda_items: AgendaItem[];
}

interface RegistrationResult {
  id: string;
  checkin_token: string;
  referral_code: string;
}

function RegistrationForm({ event }: { event: EventDetail }) {
  const router = useRouter();
  const params = useSearchParams();
  const [form, setForm] = useState({
    full_name: "", email: "", phone: "", company: "", investment_budget: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api<{ data: RegistrationResult }>(
        `/events/public/${event.slug}/register`,
        {
          method: "POST",
          body: {
            full_name: form.full_name,
            email: form.email,
            phone: form.phone,
            company: form.company || undefined,
            investment_budget: form.investment_budget ? Number(form.investment_budget) : undefined,
            utm_campaign: params.get("utm_campaign") || undefined,
            ref: params.get("ref") || undefined,
          },
        }
      );
      trackRegistration(event.name);
      sessionStorage.setItem(`event_reg_${event.slug}`, JSON.stringify(res.data));
      router.push(`/events/${event.slug}/confirmation`);
    } catch (err) {
      setError(errorMessage(err, "Registration failed. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3 rounded-xl border border-edge bg-surface p-5">
      <h3 className="text-base font-semibold">{event.cta_text}</h3>
      {error && <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>}
      <input
        required minLength={2} placeholder="Full name" value={form.full_name}
        onChange={set("full_name")}
        className="w-full rounded-lg border border-edge-strong bg-bg px-3 py-2 text-sm outline-none focus:border-primary"
      />
      <input
        required type="email" placeholder="Email" value={form.email} onChange={set("email")}
        className="w-full rounded-lg border border-edge-strong bg-bg px-3 py-2 text-sm outline-none focus:border-primary"
      />
      <input
        required minLength={7} placeholder="Phone (for WhatsApp confirmation)" value={form.phone}
        onChange={set("phone")}
        className="w-full rounded-lg border border-edge-strong bg-bg px-3 py-2 text-sm outline-none focus:border-primary"
      />
      <input
        placeholder="Company (optional)" value={form.company} onChange={set("company")}
        className="w-full rounded-lg border border-edge-strong bg-bg px-3 py-2 text-sm outline-none focus:border-primary"
      />
      <input
        type="number" min={0} placeholder="Investment budget, ₹ (optional)"
        value={form.investment_budget} onChange={set("investment_budget")}
        className="w-full rounded-lg border border-edge-strong bg-bg px-3 py-2 text-sm outline-none focus:border-primary"
      />
      <button
        type="submit" disabled={busy}
        className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:opacity-50"
      >
        {busy ? "Registering…" : event.cta_text}
      </button>
    </form>
  );
}

function EventLandingContent() {
  const { slug } = useParams<{ slug: string }>();
  const [event, setEvent] = useState<EventDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    initEventTracking();
  }, []);

  useEffect(() => {
    api<{ data: EventDetail }>(`/events/public/${slug}`)
      .then((r) => {
        setEvent(r.data);
        trackEventPageView(r.data.name);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "This event could not be found.")
      );
  }, [slug]);

  if (error) {
    return (
      <div className="mx-auto max-w-lg px-6 py-24 text-center">
        <h1 className="text-lg font-semibold">Event not found</h1>
        <p className="mt-2 text-sm text-muted">{error}</p>
      </div>
    );
  }
  if (!event) {
    return <div className="mx-auto max-w-lg px-6 py-24 text-center text-sm text-muted">Loading…</div>;
  }

  return (
    <div className="min-h-screen bg-bg text-ink">
      {event.hero_image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={event.hero_image_url} alt="" className="h-64 w-full object-cover" />
      )}
      <div className="mx-auto max-w-5xl px-6 py-10">
        <p className="text-xs font-medium uppercase tracking-wide text-primary">Investor Event</p>
        <h1 className="mt-2 text-3xl font-bold">{event.name}</h1>
        <div className="mt-3 flex flex-wrap gap-4 text-sm text-muted">
          <span className="flex items-center gap-1.5"><Calendar size={15} /> {formatDateTime(event.start_at)}</span>
          {event.venue && <span className="flex items-center gap-1.5"><MapPin size={15} /> {event.venue}</span>}
        </div>
        {event.description && <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">{event.description}</p>}

        <div className="mt-8 grid gap-8 lg:grid-cols-3">
          <div className="space-y-8 lg:col-span-2">
            {event.agenda_items.length > 0 && (
              <section>
                <h2 className="mb-3 text-lg font-semibold">Agenda</h2>
                <ol className="space-y-3 border-l border-edge pl-4">
                  {event.agenda_items.map((a) => (
                    <li key={a.id}>
                      <p className="text-xs font-medium text-primary">{formatDateTime(a.start_time)}</p>
                      <p className="text-sm font-medium">{a.title}</p>
                      {a.description && <p className="text-xs text-muted">{a.description}</p>}
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {event.speakers.length > 0 && (
              <section>
                <h2 className="mb-3 flex items-center gap-1.5 text-lg font-semibold">
                  <Users size={17} /> Speakers
                </h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  {event.speakers.map((s) => (
                    <div key={s.id} className="rounded-xl border border-edge bg-surface p-4">
                      <p className="text-sm font-semibold">{s.name}</p>
                      {s.title && <p className="text-xs text-muted">{s.title}</p>}
                      {s.bio && <p className="mt-2 text-xs leading-relaxed text-muted">{s.bio}</p>}
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>

          <div>
            <RegistrationForm event={event} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function EventLandingPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-lg px-6 py-24 text-center text-sm text-muted">Loading…</div>}>
      <EventLandingContent />
    </Suspense>
  );
}
