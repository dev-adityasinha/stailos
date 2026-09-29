"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Building2, Download, FileText, Sparkles, Wallet } from "lucide-react";
import { api, downloadFile } from "@/lib/api";
import {
  AIPanel, Badge, Button, Card, ErrorNote, SkeletonRows, Spinner,
} from "@/components/ui";
import {
  BOOKING_STAGE_LABELS, formatDateTime, formatINR, timeAgo,
} from "@/lib/format";

interface C360 {
  customer: {
    id: string; full_name: string; phone: string; email: string | null;
    city: string | null; address: string | null; occupation: string | null;
    company: string | null; budget_min: string | null; budget_max: string | null;
    family_info: { name: string; relation: string; age?: number }[] | null;
    preferences: Record<string, string> | null;
    investment_history: Record<string, unknown>[] | null;
    lead_id: string | null;
    created_at: string;
  };
  properties: {
    id: string; relation: string;
    unit: { id: string; unit_number: string; unit_type: string; price: string;
            project: { name: string; location: string } };
  }[];
  bookings: {
    id: string; stage: string; status: string; total_value: string;
    unit: { unit_number: string; project: { name: string } };
  }[];
  documents: {
    id: string; title: string; category: string; current_version: number;
    updated_at: string;
  }[];
  timeline: { id: string; type: string; title: string; actor_name: string | null; created_at: string }[];
}

const RELATION_COLORS: Record<string, string> = {
  shortlisted: "#3b82f6", favourite: "#f59e0b", attached: "#10b981",
};

const DOC_CATEGORY_COLORS: Record<string, string> = {
  kyc: "#f59e0b", agreement: "#3b82f6", payment_receipt: "#10b981",
  booking_form: "#06b6d4", brochure: "#8b5cf6", floor_plan: "#ec4899",
  legal: "#ef4444", other: "#8b98ac",
};

export default function Customer360Page() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<C360 | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [aiSummary, setAiSummary] = useState("");
  const [aiBusy, setAiBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api<{ data: C360 }>(`/customers/${id}/360`);
      setData(res.data);
    } catch {
      setError("Customer not found or not in your scope.");
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function summarize() {
    setAiBusy(true);
    try {
      const res = await api<{ data: { result: { summary: string } } }>(
        "/ai/widgets/customer-summary",
        { method: "POST", body: { customer_id: id } }
      );
      setAiSummary(res.data.result.summary);
    } finally {
      setAiBusy(false);
    }
  }

  if (error) return <ErrorNote message={error} />;
  if (!data) return <SkeletonRows rows={6} height={60} />;
  const { customer } = data;

  const timeline = filter
    ? data.timeline.filter((a) => a.type === filter)
    : data.timeline;
  const types = [...new Set(data.timeline.map((a) => a.type))];

  return (
    <div className="fade-up">
      <div className="mb-4 flex items-center gap-3">
        <Link href="/customers" className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-ink">
          <ArrowLeft size={16} />
        </Link>
        <div>
          <h1 className="text-lg font-semibold">{customer.full_name}</h1>
          <p className="text-xs text-muted">
            {customer.phone} {customer.email ? `· ${customer.email}` : ""}
            {customer.city ? ` · ${customer.city}` : ""}
          </p>
        </div>
        {customer.lead_id && (
          <Link href={`/leads/${customer.lead_id}`} className="text-[11px] text-primary hover:underline">
            View origin lead →
          </Link>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {/* Profile */}
          <Card className="grid grid-cols-2 gap-x-6 gap-y-3 p-4 sm:grid-cols-3">
            {[
              ["Occupation", customer.occupation ?? "—"],
              ["Company", customer.company ?? "—"],
              ["Budget", `${formatINR(customer.budget_min)} – ${formatINR(customer.budget_max)}`],
              ["Address", customer.address ?? "—"],
              ["Customer since", formatDateTime(customer.created_at)],
            ].map(([label, value]) => (
              <div key={label as string}>
                <p className="text-[10px] uppercase tracking-wide text-faint">{label}</p>
                <p className="mt-0.5 text-xs">{value}</p>
              </div>
            ))}
            {customer.preferences && Object.keys(customer.preferences).length > 0 && (
              <div className="col-span-full">
                <p className="text-[10px] uppercase tracking-wide text-faint">Preferences</p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {Object.entries(customer.preferences)
                    .filter(([, v]) => v)
                    .map(([k, v]) => (
                      <Badge key={k} color="#8b5cf6">{k.replace(/_/g, " ")}: {String(v)}</Badge>
                    ))}
                </div>
              </div>
            )}
            {customer.family_info && customer.family_info.length > 0 && (
              <div className="col-span-full">
                <p className="text-[10px] uppercase tracking-wide text-faint">Family</p>
                <p className="mt-0.5 text-xs text-muted">
                  {customer.family_info
                    .map((m) => `${m.name} (${m.relation}${m.age ? `, ${m.age}` : ""})`)
                    .join(" · ")}
                </p>
              </div>
            )}
          </Card>

          {/* Bookings */}
          <Card className="p-4">
            <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold">
              <Wallet size={13} /> Bookings ({data.bookings.length})
            </p>
            {data.bookings.length === 0 ? (
              <p className="text-xs text-faint">
                No bookings yet — start one from the Bookings page.
              </p>
            ) : (
              <ul className="space-y-2">
                {data.bookings.map((b) => (
                  <li key={b.id}>
                    <Link
                      href={`/bookings/${b.id}`}
                      className="flex items-center justify-between rounded-lg border border-edge px-3 py-2 text-xs hover:border-primary"
                    >
                      <span>{b.unit.project.name} · #{b.unit.unit_number}</span>
                      <span className="flex items-center gap-2">
                        <Badge color={b.status === "active" ? "#10b981" : b.status === "cancelled" ? "#ef4444" : "#8b98ac"}>
                          {BOOKING_STAGE_LABELS[b.stage] ?? b.stage} · {b.status}
                        </Badge>
                        <span className="text-muted">{formatINR(b.total_value)}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Linked properties */}
          <Card className="p-4">
            <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold">
              <Building2 size={13} /> Properties ({data.properties.length})
            </p>
            {data.properties.length === 0 ? (
              <p className="text-xs text-faint">
                Shortlist or attach inventory from the Properties page.
              </p>
            ) : (
              <ul className="space-y-2">
                {data.properties.map((p) => (
                  <li key={p.id} className="flex items-center justify-between rounded-lg border border-edge px-3 py-2 text-xs">
                    <span>
                      {p.unit.project.name} · #{p.unit.unit_number} ({p.unit.unit_type})
                    </span>
                    <span className="flex items-center gap-2">
                      <Badge color={RELATION_COLORS[p.relation]}>{p.relation}</Badge>
                      <span className="text-muted">{formatINR(p.unit.price)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Documents (customer KYC + booking paperwork) */}
          <Card className="p-4">
            <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold">
              <FileText size={13} /> Documents ({data.documents.length})
            </p>
            {data.documents.length === 0 ? (
              <p className="text-xs text-faint">
                No documents yet — upload KYC or agreements from the Documents page.
              </p>
            ) : (
              <ul className="space-y-2">
                {data.documents.map((d) => (
                  <li
                    key={d.id}
                    className="flex items-center justify-between rounded-lg border border-edge px-3 py-2 text-xs"
                  >
                    <span className="min-w-0 truncate">
                      {d.title}
                      <span className="ml-1 text-faint">v{d.current_version} · {timeAgo(d.updated_at)}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <Badge color={DOC_CATEGORY_COLORS[d.category] ?? DOC_CATEGORY_COLORS.other}>
                        {d.category.replace(/_/g, " ")}
                      </Badge>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => downloadFile(`/documents/${d.id}/download`, {}, d.title)}
                      >
                        <Download size={13} />
                      </Button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Timeline with filtering (Task 15) */}
          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-xs font-semibold">Timeline</p>
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="rounded-lg border border-edge bg-surface px-2 py-1 text-[11px] outline-none"
              >
                <option value="">All activity</option>
                {types.map((t) => (
                  <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                ))}
              </select>
            </div>
            {timeline.length === 0 ? (
              <p className="text-xs text-faint">No activity recorded.</p>
            ) : (
              <ol className="relative ml-2 space-y-3 border-l border-edge pl-4">
                {timeline.map((a) => (
                  <li key={a.id} className="relative">
                    <span
                      className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-surface"
                      style={{ backgroundColor: a.type === "ai_recommendation" ? "#8b5cf6" : a.type === "payment" ? "#10b981" : "#3b82f6" }}
                    />
                    <p className="text-xs">{a.title}</p>
                    <p className="text-[10px] text-faint">
                      {a.actor_name ? `${a.actor_name} · ` : ""}{timeAgo(a.created_at)}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>

        <div className="space-y-3">
          <AIPanel title="Ask Pappu">
            <Button size="sm" variant="ai" disabled={aiBusy} onClick={summarize}>
              {aiBusy ? <Spinner size={12} /> : <Sparkles size={12} />} Summarize customer
            </Button>
            {aiSummary && (
              <p className="mt-3 rounded-lg bg-bg/60 p-3 text-xs leading-relaxed text-muted">
                {aiSummary}
              </p>
            )}
          </AIPanel>
        </div>
      </div>
    </div>
  );
}
