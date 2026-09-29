"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Check, ChevronRight, Receipt, XCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import {
  Badge, Button, Card, ErrorNote, Input, Modal, Select, SkeletonRows, cx,
} from "@/components/ui";
import {
  BOOKING_STAGES, BOOKING_STAGE_LABELS, formatDateTime, formatINR,
} from "@/lib/format";

interface BookingDetail {
  id: string;
  stage: string;
  status: string;
  total_value: string;
  token_amount: string | null;
  discount: string | null;
  cancellation_reason: string | null;
  customer: { id: string; full_name: string; phone: string };
  unit: { unit_number: string; unit_type: string; price: string;
          project: { name: string; location: string } };
  stage_events: { id: string; from_stage: string | null; to_stage: string;
                  note: string | null; actor_name: string | null; created_at: string }[];
  payments: { id: string; amount: string; method: string; receipt_number: string;
              milestone: string | null; created_at: string }[];
}

export default function BookingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [booking, setBooking] = useState<BookingDetail | null>(null);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [showPayment, setShowPayment] = useState(false);
  const [payForm, setPayForm] = useState({ amount: "", method: "bank_transfer", milestone: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api<{ data: BookingDetail }>(`/bookings/${id}`);
      setBooking(res.data);
    } catch {
      setError("Booking not found or not in your scope.");
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function advance() {
    setActionError("");
    try {
      await api(`/bookings/${id}/advance-stage`, { method: "POST", body: {} });
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Failed to advance stage.");
    }
  }

  async function cancel() {
    const reason = prompt("Cancellation reason?");
    if (!reason) return;
    setActionError("");
    try {
      await api(`/bookings/${id}/cancel`, { method: "POST", body: { reason } });
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Failed to cancel.");
    }
  }

  async function recordPayment(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setActionError("");
    try {
      await api(`/bookings/${id}/payments`, {
        method: "POST",
        body: { amount: payForm.amount, method: payForm.method,
                milestone: payForm.milestone || null },
      });
      setShowPayment(false);
      setPayForm({ amount: "", method: "bank_transfer", milestone: "" });
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Payment failed.");
      setShowPayment(false);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorNote message={error} />;
  if (!booking) return <SkeletonRows rows={6} height={60} />;

  const paid = booking.payments.reduce((sum, p) => sum + Number(p.amount), 0);
  const payable = Number(booking.total_value) - Number(booking.discount ?? 0);
  const stageIndex = BOOKING_STAGES.indexOf(booking.stage);
  const isActive = booking.status === "active";

  return (
    <div className="fade-up">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link href="/bookings" className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-ink">
            <ArrowLeft size={16} />
          </Link>
          <div>
            <h1 className="text-lg font-semibold">
              {booking.unit.project.name} · #{booking.unit.unit_number}
            </h1>
            <p className="text-xs text-muted">
              <Link href={`/customers/${booking.customer.id}`} className="text-primary hover:underline">
                {booking.customer.full_name}
              </Link>{" "}
              · {booking.customer.phone} · {booking.unit.unit_type} · {booking.unit.project.location}
            </p>
          </div>
          <Badge color={{ active: "#10b981", cancelled: "#ef4444", completed: "#3b82f6" }[booking.status]}>
            {booking.status}
          </Badge>
        </div>
        <div className="flex gap-2">
          {isActive && booking.stage === "payment" && (
            <Button variant="secondary" onClick={() => setShowPayment(true)}>
              <Receipt size={14} /> Record payment
            </Button>
          )}
          {isActive && (
            <>
              <Button onClick={advance}>
                Advance stage <ChevronRight size={14} />
              </Button>
              <Button variant="danger" onClick={cancel}>
                <XCircle size={14} /> Cancel
              </Button>
            </>
          )}
        </div>
      </div>

      {actionError && <div className="mb-3"><ErrorNote message={actionError} /></div>}
      {booking.cancellation_reason && (
        <p className="mb-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          Cancelled: {booking.cancellation_reason}
        </p>
      )}

      {/* Stage stepper (PRD §7.3: visual progress) */}
      <Card className="mb-4 p-5">
        <div className="flex items-center">
          {BOOKING_STAGES.map((stage, i) => {
            const done = i < stageIndex || booking.status === "completed";
            const current = i === stageIndex && booking.status === "active";
            return (
              <div key={stage} className={cx("flex items-center", i < BOOKING_STAGES.length - 1 && "flex-1")}>
                <div className="flex flex-col items-center">
                  <span
                    className={cx(
                      "flex h-7 w-7 items-center justify-center rounded-full border-2 text-[10px] font-bold",
                      done && "border-success bg-success text-white",
                      current && "border-primary bg-primary/20 text-primary",
                      !done && !current && "border-edge-strong text-faint"
                    )}
                  >
                    {done ? <Check size={13} /> : i + 1}
                  </span>
                  <span className={cx(
                    "mt-1.5 whitespace-nowrap text-[10px]",
                    current ? "font-semibold text-primary" : done ? "text-success" : "text-faint"
                  )}>
                    {BOOKING_STAGE_LABELS[stage]}
                  </span>
                </div>
                {i < BOOKING_STAGES.length - 1 && (
                  <div className={cx("mx-2 mb-5 h-0.5 flex-1 rounded",
                                     i < stageIndex ? "bg-success" : "bg-edge")} />
                )}
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Payments */}
        <Card className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-semibold">Payments</p>
            <p className="text-xs text-muted">
              <span className="font-semibold text-success">{formatINR(paid)}</span>
              {" of "}{formatINR(payable)}
            </p>
          </div>
          <div className="mb-3 h-2 overflow-hidden rounded-full bg-raised">
            <div
              className="h-full rounded-full bg-success transition-all"
              style={{ width: `${Math.min(100, (paid / payable) * 100)}%` }}
            />
          </div>
          {booking.payments.length === 0 ? (
            <p className="text-xs text-faint">No payments recorded yet.</p>
          ) : (
            <ul className="space-y-2">
              {booking.payments.map((p) => (
                <li key={p.id} className="flex items-center justify-between rounded-lg border border-edge px-3 py-2 text-xs">
                  <span>
                    <span className="font-mono text-[10px] text-faint">{p.receipt_number}</span>
                    {p.milestone && <span className="ml-2 text-muted">{p.milestone}</span>}
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="text-faint">{p.method.replace(/_/g, " ")}</span>
                    <span className="font-semibold text-success">{formatINR(p.amount)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Stage history */}
        <Card className="p-4">
          <p className="mb-3 text-xs font-semibold">Stage history</p>
          <ol className="relative ml-2 space-y-3 border-l border-edge pl-4">
            {[...booking.stage_events].reverse().map((e) => (
              <li key={e.id} className="relative">
                <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-surface bg-primary" />
                <p className="text-xs">
                  {e.from_stage ? `${BOOKING_STAGE_LABELS[e.from_stage] ?? e.from_stage} → ` : ""}
                  <b>{BOOKING_STAGE_LABELS[e.to_stage] ?? e.to_stage}</b>
                </p>
                {e.note && <p className="text-[11px] text-muted">{e.note}</p>}
                <p className="text-[10px] text-faint">
                  {e.actor_name ? `${e.actor_name} · ` : ""}{formatDateTime(e.created_at)}
                </p>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <Modal open={showPayment} onClose={() => setShowPayment(false)} title="Record payment">
        <form onSubmit={recordPayment} className="space-y-4">
          <Input label={`Amount (₹) — outstanding ${formatINR(payable - paid)}`} type="number"
                 required min={1} value={payForm.amount}
                 onChange={(e) => setPayForm((f) => ({ ...f, amount: e.target.value }))} />
          <Select label="Method" value={payForm.method}
                  onChange={(e) => setPayForm((f) => ({ ...f, method: e.target.value }))}>
            {["bank_transfer", "upi", "cheque", "cash", "loan_disbursement"].map((m) => (
              <option key={m} value={m}>{m.replace(/_/g, " ")}</option>
            ))}
          </Select>
          <Input label="Milestone (optional)" value={payForm.milestone}
                 onChange={(e) => setPayForm((f) => ({ ...f, milestone: e.target.value }))}
                 placeholder="Down payment, Slab 3, Possession…" />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setShowPayment(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Recording…" : "Record payment"}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
