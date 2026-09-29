"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import {
  Badge, Button, Card, EmptyState, ErrorNote, Input, Modal, PageHeader, Select,
  SkeletonRows,
} from "@/components/ui";
import { BOOKING_STAGE_LABELS, formatINR, timeAgo } from "@/lib/format";

interface Booking {
  id: string;
  stage: string;
  status: string;
  total_value: string;
  token_amount: string | null;
  customer: { full_name: string };
  unit: { unit_number: string; project: { name: string } };
  updated_at: string;
}

interface Option { id: string; label: string }

const STATUS_COLORS: Record<string, string> = {
  active: "#10b981", cancelled: "#ef4444", completed: "#3b82f6",
};

function NewBookingModal({ open, onClose, onCreated }: {
  open: boolean; onClose: () => void; onCreated: () => void;
}) {
  const [customers, setCustomers] = useState<Option[]>([]);
  const [units, setUnits] = useState<Option[]>([]);
  const [form, setForm] = useState({ customer_id: "", unit_id: "", total_value: "", token_amount: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api<{ data: { id: string; full_name: string; phone: string }[] }>("/customers", {
      params: { limit: 100 },
    }).then((r) =>
      setCustomers(r.data.map((c) => ({ id: c.id, label: `${c.full_name} (${c.phone})` })))
    );
    api<{ data: { id: string; unit_number: string; price: string; status: string;
                  project: { name: string } }[] }>("/properties", {
      params: { status: "available" },
    }).then((r) =>
      setUnits(r.data.map((u) => ({
        id: u.id,
        label: `${u.project.name} #${u.unit_number} — ${formatINR(u.price)}`,
      })))
    );
  }, [open]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/bookings", {
        method: "POST",
        body: {
          customer_id: form.customer_id,
          unit_id: form.unit_id,
          total_value: form.total_value,
          token_amount: form.token_amount || null,
        },
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create booking.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Start booking workflow">
      <form onSubmit={submit} className="space-y-4">
        {error && <ErrorNote message={error} />}
        <Select label="Customer *" required value={form.customer_id}
                onChange={(e) => setForm((f) => ({ ...f, customer_id: e.target.value }))}>
          <option value="">Select customer…</option>
          {customers.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
        </Select>
        <Select label="Unit *" required value={form.unit_id}
                onChange={(e) => setForm((f) => ({ ...f, unit_id: e.target.value }))}>
          <option value="">Select available unit…</option>
          {units.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
        </Select>
        <div className="grid grid-cols-2 gap-4">
          <Input label="Total value (₹) *" type="number" required min={1}
                 value={form.total_value}
                 onChange={(e) => setForm((f) => ({ ...f, total_value: e.target.value }))} />
          <Input label="Token amount (₹)" type="number" min={0}
                 value={form.token_amount}
                 onChange={(e) => setForm((f) => ({ ...f, token_amount: e.target.value }))} />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={busy}>{busy ? "Creating…" : "Start booking"}</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function BookingsPage() {
  const router = useRouter();
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [showNew, setShowNew] = useState(false);

  const load = useCallback(async () => {
    const res = await api<{ data: Booking[] }>("/bookings", {
      params: { status: statusFilter, limit: 100 },
    });
    setBookings(res.data);
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="fade-up">
      <PageHeader
        title="Bookings"
        subtitle="Lead → Site Visit → Booking → Documentation → Payment → Possession"
        actions={<Button onClick={() => setShowNew(true)}><Plus size={14} /> New booking</Button>}
      />
      <div className="mb-4">
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-40">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </Select>
      </div>
      <Card>
        {bookings === null ? (
          <SkeletonRows />
        ) : bookings.length === 0 ? (
          <EmptyState
            title="No bookings"
            hint="Start a booking for a customer and an available unit."
            action={<Button size="sm" onClick={() => setShowNew(true)}><Plus size={13} /> New booking</Button>}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge text-[11px] uppercase tracking-wide text-faint">
                  <th className="px-4 py-2.5 font-medium">Customer</th>
                  <th className="px-4 py-2.5 font-medium">Unit</th>
                  <th className="px-4 py-2.5 font-medium">Stage</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Value</th>
                  <th className="px-4 py-2.5 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {bookings.map((b) => (
                  <tr
                    key={b.id}
                    onClick={() => router.push(`/bookings/${b.id}`)}
                    className="cursor-pointer border-b border-edge/60 last:border-0 hover:bg-raised/60"
                  >
                    <td className="px-4 py-3 font-medium">{b.customer.full_name}</td>
                    <td className="px-4 py-3 text-muted">
                      {b.unit.project.name} · #{b.unit.unit_number}
                    </td>
                    <td className="px-4 py-3">
                      <Badge color="#3b82f6">{BOOKING_STAGE_LABELS[b.stage] ?? b.stage}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge color={STATUS_COLORS[b.status]}>{b.status}</Badge>
                    </td>
                    <td className="px-4 py-3 text-muted">{formatINR(b.total_value)}</td>
                    <td className="px-4 py-3 text-faint">{timeAgo(b.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <NewBookingModal open={showNew} onClose={() => setShowNew(false)} onCreated={load} />
    </div>
  );
}
