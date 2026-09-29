"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Download, Plus, Search, Upload } from "lucide-react";
import { api, downloadFile } from "@/lib/api";
import {
  Badge, Button, Card, EmptyState, PageHeader, Select, SkeletonRows, Spinner,
} from "@/components/ui";
import { LeadFormModal } from "@/components/lead-form";
import {
  STAGE_COLORS, STAGE_LABELS, STAGE_ORDER, formatINR, timeAgo,
} from "@/lib/format";

interface Lead {
  id: string;
  full_name: string;
  phone: string;
  email: string | null;
  source: string;
  stage: string;
  score_band: string | null;
  ai_score: number | null;
  budget_min: string | null;
  budget_max: string | null;
  assignee: { full_name: string } | null;
  tags: { id: string; name: string; color: string | null }[];
  updated_at: string;
}

const BAND_COLORS: Record<string, string> = {
  hot: "#ef4444", warm: "#f59e0b", cold: "#8b98ac",
};

function LeadsInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [stage, setStage] = useState("");
  const [source, setSource] = useState("");
  const [showNew, setShowNew] = useState(searchParams.get("new") === "1");
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<string>("");
  const limit = 25;

  // Keep in sync with header search / quick actions when already on this page.
  useEffect(() => {
    const urlQ = searchParams.get("q");
    if (urlQ !== null) setQ(urlQ);
    if (searchParams.get("new") === "1") setShowNew(true);
  }, [searchParams]);

  const load = useCallback(async () => {
    const res = await api<{ data: Lead[]; meta: { total: number } }>("/leads", {
      params: { q, stage, source, limit, offset: page * limit },
    });
    setLeads(res.data);
    setTotal(res.meta.total);
  }, [q, stage, source, page]);

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  async function onImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportResult("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api<{ data: { imported: number; skipped_duplicates: number; errors: unknown[] } }>(
        "/leads/import",
        { method: "POST", formData: fd }
      );
      setImportResult(
        `Imported ${res.data.imported}, skipped ${res.data.skipped_duplicates} duplicates, ${res.data.errors?.length ?? 0} errors.`
      );
      load();
    } catch {
      setImportResult("Import failed — check the CSV format.");
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  }

  return (
    <div className="fade-up">
      <PageHeader
        title="Leads"
        subtitle={`${total} lead${total === 1 ? "" : "s"} in view`}
        actions={
          <>
            <label className="cursor-pointer">
              <input type="file" accept=".csv" className="hidden" onChange={onImport} />
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-edge-strong bg-raised px-3.5 py-2 text-sm font-medium text-ink hover:bg-edge">
                {importing ? <Spinner size={14} /> : <Upload size={14} />} Import CSV
              </span>
            </label>
            <Button variant="secondary" onClick={() => downloadFile("/leads/export", {}, "leads.csv")}>
              <Download size={14} /> Export
            </Button>
            <Button onClick={() => setShowNew(true)}>
              <Plus size={14} /> Add lead
            </Button>
          </>
        }
      />

      {importResult && (
        <p className="mb-3 rounded-lg border border-edge bg-raised px-3 py-2 text-xs text-muted">
          {importResult}
        </p>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative">
          <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <input
            value={q}
            onChange={(e) => { setQ(e.target.value); setPage(0); }}
            placeholder="Search name, phone, email…"
            className="w-60 rounded-lg border border-edge-strong bg-surface py-2 pl-8 pr-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <Select value={stage} onChange={(e) => { setStage(e.target.value); setPage(0); }} className="w-44">
          <option value="">All stages</option>
          {STAGE_ORDER.map((s) => <option key={s} value={s}>{STAGE_LABELS[s]}</option>)}
        </Select>
        <Select value={source} onChange={(e) => { setSource(e.target.value); setPage(0); }} className="w-40">
          <option value="">All sources</option>
          {["website", "walk_in", "referral", "channel_partner", "meta_ads", "google_ads",
            "whatsapp", "phone_inquiry", "property_portal", "event", "csv_import", "other"]
            .map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
        </Select>
      </div>

      <Card>
        {leads === null ? (
          <SkeletonRows />
        ) : leads.length === 0 ? (
          <EmptyState
            title="No leads found"
            hint="Add a lead manually or import a CSV to get started."
            action={<Button size="sm" onClick={() => setShowNew(true)}><Plus size={13} /> Add lead</Button>}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge text-[11px] uppercase tracking-wide text-faint">
                  <th className="px-4 py-2.5 font-medium">Lead</th>
                  <th className="px-4 py-2.5 font-medium">Stage</th>
                  <th className="px-4 py-2.5 font-medium">Score</th>
                  <th className="px-4 py-2.5 font-medium">Budget</th>
                  <th className="px-4 py-2.5 font-medium">Source</th>
                  <th className="px-4 py-2.5 font-medium">Owner</th>
                  <th className="px-4 py-2.5 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr
                    key={lead.id}
                    onClick={() => router.push(`/leads/${lead.id}`)}
                    className="cursor-pointer border-b border-edge/60 transition-colors last:border-0 hover:bg-raised/60"
                  >
                    <td className="px-4 py-3">
                      <p className="font-medium text-ink">{lead.full_name}</p>
                      <p className="mt-0.5 text-[11px] text-faint">{lead.phone}</p>
                    </td>
                    <td className="px-4 py-3">
                      <Badge color={STAGE_COLORS[lead.stage]}>{STAGE_LABELS[lead.stage]}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      {lead.score_band ? (
                        <Badge color={BAND_COLORS[lead.score_band]}>
                          {lead.score_band} {lead.ai_score != null ? `· ${lead.ai_score}` : ""}
                        </Badge>
                      ) : (
                        <span className="text-faint">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted">
                      {formatINR(lead.budget_min)} – {formatINR(lead.budget_max)}
                    </td>
                    <td className="px-4 py-3 text-muted">{lead.source.replace(/_/g, " ")}</td>
                    <td className="px-4 py-3 text-muted">{lead.assignee?.full_name ?? "—"}</td>
                    <td className="px-4 py-3 text-faint">{timeAgo(lead.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {total > limit && (
        <div className="mt-3 flex items-center justify-end gap-2 text-xs text-muted">
          <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <span>Page {page + 1} of {Math.ceil(total / limit)}</span>
          <Button size="sm" variant="secondary" disabled={(page + 1) * limit >= total} onClick={() => setPage((p) => p + 1)}>
            Next
          </Button>
        </div>
      )}

      <LeadFormModal open={showNew} onClose={() => setShowNew(false)} onCreated={load} />
    </div>
  );
}

export default function LeadsPage() {
  return (
    <Suspense fallback={<SkeletonRows />}>
      <LeadsInner />
    </Suspense>
  );
}
