"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Plus, Users } from "lucide-react";
import { api } from "@/lib/api";
import {
  Badge, Button, Card, Input, Modal, PageHeader, Select, SkeletonRows,
  Textarea, cx,
} from "@/components/ui";
import { formatDateTime } from "@/lib/format";

interface CalEvent {
  id: string;
  title: string;
  type: string;
  location: string | null;
  start_at: string;
  end_at: string | null;
  status: string;
  owner: { full_name: string };
}

const TYPE_COLORS: Record<string, string> = {
  meeting: "#3b82f6", site_visit: "#f59e0b", call: "#10b981",
  reminder: "#8b5cf6", follow_up: "#06b6d4",
};

function toUTC(iso: string): Date {
  return new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
}

function CalendarInner() {
  const searchParams = useSearchParams();
  const [cursor, setCursor] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const [events, setEvents] = useState<CalEvent[] | null>(null);
  const [team, setTeam] = useState(false);
  const [showNew, setShowNew] = useState(searchParams.get("new") === "1");
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "", type: "meeting", start_at: "", end_at: "", location: "", description: "",
  });

  useEffect(() => {
    if (searchParams.get("new") === "1") setShowNew(true);
  }, [searchParams]);

  const load = useCallback(async () => {
    const start = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const end = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
    const res = await api<{ data: CalEvent[] }>("/calendar", {
      params: { start: start.toISOString(), end: end.toISOString(), team },
    });
    setEvents(res.data);
  }, [cursor, team]);

  useEffect(() => { load(); }, [load]);

  const days = useMemo(() => {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const startWeekday = (first.getDay() + 6) % 7; // Monday first
    const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
    const cells: (string | null)[] = Array(startWeekday).fill(null);
    for (let d = 1; d <= daysInMonth; d++) {
      cells.push(
        `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`
      );
    }
    return cells;
  }, [cursor]);

  const byDay = useMemo(() => {
    const map: Record<string, CalEvent[]> = {};
    for (const e of events ?? []) {
      const local = toUTC(e.start_at);
      const key = `${local.getFullYear()}-${String(local.getMonth() + 1).padStart(2, "0")}-${String(local.getDate()).padStart(2, "0")}`;
      (map[key] ??= []).push(e);
    }
    return map;
  }, [events]);

  async function createEvent(e: React.FormEvent) {
    e.preventDefault();
    await api("/calendar", {
      method: "POST",
      body: {
        title: form.title,
        type: form.type,
        start_at: new Date(form.start_at).toISOString(),
        end_at: form.end_at ? new Date(form.end_at).toISOString() : null,
        location: form.location || null,
        description: form.description || null,
      },
    });
    setShowNew(false);
    setForm({ title: "", type: "meeting", start_at: "", end_at: "", location: "", description: "" });
    load();
  }

  const todayKey = (() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  })();

  return (
    <div className="fade-up">
      <PageHeader
        title="Calendar"
        actions={
          <>
            <Button variant={team ? "primary" : "secondary"} size="sm" onClick={() => setTeam((t) => !t)}>
              <Users size={13} /> Team view
            </Button>
            <Button onClick={() => setShowNew(true)}><Plus size={14} /> New event</Button>
          </>
        }
      />
      <Card className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-semibold">
            {cursor.toLocaleDateString("en-IN", { month: "long", year: "numeric" })}
          </p>
          <div className="flex gap-1">
            <Button size="sm" variant="ghost"
                    onClick={() => setCursor((c) => new Date(c.getFullYear(), c.getMonth() - 1, 1))}>
              <ChevronLeft size={15} />
            </Button>
            <Button size="sm" variant="secondary"
                    onClick={() => setCursor(new Date(new Date().getFullYear(), new Date().getMonth(), 1))}>
              Today
            </Button>
            <Button size="sm" variant="ghost"
                    onClick={() => setCursor((c) => new Date(c.getFullYear(), c.getMonth() + 1, 1))}>
              <ChevronRight size={15} />
            </Button>
          </div>
        </div>
        {events === null ? (
          <SkeletonRows rows={4} height={70} />
        ) : (
          <>
            <div className="grid grid-cols-7 gap-px text-center text-[10px] uppercase text-faint">
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
                <div key={d} className="py-1">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg bg-edge">
              {days.map((day, i) => (
                <button
                  key={i}
                  disabled={!day}
                  onClick={() => day && setSelectedDay(day)}
                  className={cx(
                    "min-h-20 bg-surface p-1.5 text-left align-top transition-colors",
                    day && "hover:bg-raised",
                    day === todayKey && "ring-1 ring-inset ring-primary"
                  )}
                >
                  {day && (
                    <>
                      <span className={cx("text-[10px]",
                        day === todayKey ? "font-bold text-primary" : "text-faint")}>
                        {Number(day.slice(-2))}
                      </span>
                      <div className="mt-0.5 space-y-0.5">
                        {(byDay[day] ?? []).slice(0, 3).map((e) => (
                          <div
                            key={e.id}
                            className="truncate rounded px-1 py-0.5 text-[9px] leading-tight"
                            style={{ backgroundColor: `${TYPE_COLORS[e.type]}26`, color: TYPE_COLORS[e.type] }}
                          >
                            {e.title}
                          </div>
                        ))}
                        {(byDay[day]?.length ?? 0) > 3 && (
                          <p className="text-[9px] text-faint">+{byDay[day].length - 3} more</p>
                        )}
                      </div>
                    </>
                  )}
                </button>
              ))}
            </div>
          </>
        )}
      </Card>

      {/* Day detail */}
      <Modal open={!!selectedDay} onClose={() => setSelectedDay(null)}
             title={selectedDay ? new Date(selectedDay).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" }) : ""}>
        {selectedDay && (byDay[selectedDay]?.length ? (
          <ul className="space-y-2">
            {byDay[selectedDay].map((e) => (
              <li key={e.id} className="rounded-lg border border-edge px-3 py-2">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium">{e.title}</p>
                  <Badge color={TYPE_COLORS[e.type]}>{e.type.replace(/_/g, " ")}</Badge>
                </div>
                <p className="mt-1 text-[11px] text-muted">
                  {formatDateTime(e.start_at)}
                  {e.end_at ? ` – ${formatDateTime(e.end_at)}` : ""}
                  {e.location ? ` · ${e.location}` : ""} · {e.owner.full_name}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-faint">No events this day.</p>
        ))}
      </Modal>

      {/* New event */}
      <Modal open={showNew} onClose={() => setShowNew(false)} title="New event">
        <form onSubmit={createEvent} className="space-y-4">
          <Input label="Title *" required minLength={2} value={form.title}
                 onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
          <Select label="Type" value={form.type}
                  onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}>
            {Object.keys(TYPE_COLORS).map((t) => (
              <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
            ))}
          </Select>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Starts *" type="datetime-local" required value={form.start_at}
                   onChange={(e) => setForm((f) => ({ ...f, start_at: e.target.value }))} />
            <Input label="Ends" type="datetime-local" value={form.end_at}
                   onChange={(e) => setForm((f) => ({ ...f, end_at: e.target.value }))} />
          </div>
          <Input label="Location" value={form.location}
                 onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))} />
          <Textarea label="Description" value={form.description}
                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setShowNew(false)}>Cancel</Button>
            <Button type="submit">Create event</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default function CalendarPage() {
  return (
    <Suspense fallback={<SkeletonRows />}>
      <CalendarInner />
    </Suspense>
  );
}
