"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Calendar, MapPin, Plus } from "lucide-react";
import { api, ApiError, errorMessage } from "@/lib/api";
import {
  Badge, Button, Card, EmptyState, Input, Modal, PageHeader, SkeletonRows,
} from "@/components/ui";
import { formatDateTime } from "@/lib/format";

interface EventRow {
  id: string;
  name: string;
  slug: string;
  venue: string | null;
  start_at: string;
  status: "draft" | "published" | "completed";
}

const STATUS_COLORS: Record<string, string> = {
  draft: "#8b98ac", published: "#10b981", completed: "#3b82f6",
};

function CreateEventModal({ open, onClose, onCreated }: {
  open: boolean; onClose: () => void; onCreated: () => void;
}) {
  const [form, setForm] = useState({
    name: "", slug: "", venue: "", start_at: "", end_at: "", description: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setForm((f) => ({
      ...f, [k]: value,
      // auto-slugify from the name unless the user has already edited slug directly
      ...(k === "name" && !f.slug
        ? { slug: value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") }
        : {}),
    }));
  };

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/events", {
        method: "POST",
        body: {
          ...form,
          start_at: new Date(form.start_at).toISOString(),
          end_at: new Date(form.end_at).toISOString(),
        },
      });
      onCreated();
      onClose();
      setForm({ name: "", slug: "", venue: "", start_at: "", end_at: "", description: "" });
    } catch (err) {
      setError(errorMessage(err, "Failed to create event."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="New event">
      <form onSubmit={onSubmit} className="space-y-3">
        {error && <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>}
        <Input label="Name" required minLength={2} value={form.name} onChange={set("name")} />
        <Input label="Public URL slug" required value={form.slug} onChange={set("slug")}
               pattern="^[a-z0-9]+(-[a-z0-9]+)*$" title="lowercase letters, numbers, hyphens" />
        <Input label="Venue" value={form.venue} onChange={set("venue")} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Start" type="datetime-local" required value={form.start_at} onChange={set("start_at")} />
          <Input label="End" type="datetime-local" required value={form.end_at} onChange={set("end_at")} />
        </div>
        <Button type="submit" disabled={busy} className="w-full justify-center">
          {busy ? "Creating…" : "Create event"}
        </Button>
      </form>
    </Modal>
  );
}

export default function EventsPage() {
  const [events, setEvents] = useState<EventRow[] | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    try {
      const res = await api<{ data: EventRow[] }>("/events");
      setEvents(res.data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load events.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="fade-up">
      <PageHeader
        title="Events"
        subtitle="Investor-event landing pages, registrations, check-in and follow-up"
        actions={<Button size="sm" onClick={() => setShowNew(true)}><Plus size={13} /> New event</Button>}
      />
      {error && <p className="mb-3 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>}
      {!events ? (
        <SkeletonRows rows={3} height={70} />
      ) : events.length === 0 ? (
        <EmptyState
          title="No events yet"
          hint="Create your first investor event to get a public landing page, registration, and check-in."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {events.map((e) => (
            <Link key={e.id} href={`/events/manage/${e.id}`}>
              <Card className="p-4 transition-colors hover:border-primary">
                <div className="mb-2 flex items-center justify-between">
                  <Badge color={STATUS_COLORS[e.status]}>{e.status}</Badge>
                </div>
                <p className="text-sm font-semibold">{e.name}</p>
                <p className="mt-1 flex items-center gap-1.5 text-xs text-muted">
                  <Calendar size={12} /> {formatDateTime(e.start_at)}
                </p>
                {e.venue && (
                  <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
                    <MapPin size={12} /> {e.venue}
                  </p>
                )}
              </Card>
            </Link>
          ))}
        </div>
      )}
      <CreateEventModal open={showNew} onClose={() => setShowNew(false)} onCreated={load} />
    </div>
  );
}
