"use client";

import { useApiSWR } from "@/lib/useApiSWR";
import { Card, PageHeader, SkeletonRows } from "@/components/ui";
import { STAGE_COLORS, STAGE_LABELS, formatINR } from "@/lib/format";

interface TargetRow {
  metric: string; target: number; actual: number; progress_pct: number;
}
interface Overview {
  total_leads: number; active_leads: number; converted_leads: number;
  conversion_rate: number; bookings_total: number; bookings_active: number;
  revenue_collected: number; pipeline_value: number; site_visits: number;
  hot_leads: number;
  month_to_date: Record<string, number>;
  /** From the monthly targets set during onboarding. Empty when none were set. */
  targets: TargetRow[];
}

const TARGET_LABELS: Record<string, string> = {
  leads: "Leads", site_visits: "Site visits", bookings: "Bookings",
  revenue: "Revenue",
};
interface FunnelRow { stage: string; count: number }
interface RevenueRow { month: string; revenue: number }
interface TeamRow {
  user_id: string; name: string; role: string; leads: number;
  converted: number; bookings: number; revenue: number;
}
interface SourceRow {
  source: string; leads: number; converted: number; booked: number;
  conversion_rate: number;
}

export default function AnalyticsPage() {
  const { data: overviewData } = useApiSWR<{ data: Overview }>("/analytics/overview");
  const { data: funnelData } = useApiSWR<{ data: FunnelRow[] }>("/analytics/funnel");
  const { data: revenueData } = useApiSWR<{ data: RevenueRow[] }>("/analytics/revenue?months=6");
  const { data: teamData } = useApiSWR<{ data: TeamRow[] }>("/analytics/team");
  const { data: sourcesData } = useApiSWR<{ data: SourceRow[] }>("/analytics/sources");

  const overview = overviewData?.data;
  const funnel = funnelData?.data ?? [];
  const revenue = revenueData?.data ?? [];
  const team = teamData?.data ?? [];
  const sources = sourcesData?.data ?? [];

  if (!overview) return <SkeletonRows rows={4} height={90} />;

  const revenueMax = Math.max(1, ...revenue.map((r) => r.revenue));
  const funnelMax = Math.max(1, ...funnel.map((f) => f.count));

  return (
    <div className="fade-up">
      <PageHeader title="Analytics" subtitle="Live metrics computed from CRM data — scoped to your role" />

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {[
          ["Total leads", overview.total_leads],
          ["Active leads", overview.active_leads],
          ["Conversion", `${overview.conversion_rate}%`],
          ["Site visits", overview.site_visits],
          ["Bookings", overview.bookings_total],
          ["Revenue", formatINR(overview.revenue_collected)],
        ].map(([label, value]) => (
          <Card key={label as string} className="p-3">
            <p className="text-[10px] uppercase tracking-wide text-faint">{label}</p>
            <p className="mt-1 text-lg font-semibold">{value}</p>
          </Card>
        ))}
      </div>

      {/* Month-to-date progress against the targets set during onboarding.
          Rendered only when targets exist — never invents a goal of zero. */}
      {overview.targets.length > 0 && (
        <Card className="mt-4 p-4">
          <p className="mb-1 text-xs font-semibold">This month vs target</p>
          <p className="mb-4 text-[10px] text-faint">
            Targets from workspace setup · editable under Settings → Company profile
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {overview.targets.map((t) => {
              const format = (n: number) =>
                t.metric === "revenue" ? formatINR(n) : String(n);
              return (
                <div key={t.metric}>
                  <div className="flex items-baseline justify-between text-xs">
                    <span className="font-medium">
                      {TARGET_LABELS[t.metric] ?? t.metric.replace(/_/g, " ")}
                    </span>
                    <span className="tabular-nums text-muted">
                      {format(t.actual)}
                      <span className="text-faint"> / {format(t.target)}</span>
                    </span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-raised">
                    <div
                      className={t.progress_pct >= 100 ? "h-full bg-success" : "h-full bg-primary"}
                      style={{ width: `${Math.min(t.progress_pct, 100)}%` }}
                    />
                  </div>
                  <p className="mt-1 text-[10px] text-faint">
                    {t.progress_pct}% of the monthly target
                  </p>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {/* Revenue bar chart */}
        <Card className="p-4">
          <p className="mb-4 text-xs font-semibold">Revenue — last 6 months</p>
          <div className="flex h-44 items-end gap-3 px-2">
            {revenue.map((r) => (
              <div key={r.month} className="flex flex-1 flex-col items-center gap-1.5">
                <span className="text-[9px] text-muted">
                  {r.revenue > 0 ? formatINR(r.revenue) : ""}
                </span>
                <div
                  className="w-full rounded-t bg-success/80 transition-all hover:bg-success"
                  style={{ height: `${(r.revenue / revenueMax) * 130}px`, minHeight: r.revenue > 0 ? 4 : 1 }}
                  title={`${r.month}: ${formatINR(r.revenue)}`}
                />
                <span className="text-[9px] text-faint">{r.month.slice(5)}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Funnel */}
        <Card className="p-4">
          <p className="mb-4 text-xs font-semibold">Sales funnel</p>
          <div className="space-y-1.5">
            {funnel.map((row) => (
              <div key={row.stage} className="flex items-center gap-2">
                <span className="w-36 shrink-0 text-[11px] text-muted">{STAGE_LABELS[row.stage]}</span>
                <div className="h-4 flex-1 overflow-hidden rounded bg-raised">
                  <div className="h-full rounded"
                       style={{ width: `${(row.count / funnelMax) * 100}%`,
                                backgroundColor: STAGE_COLORS[row.stage],
                                minWidth: row.count ? 16 : 0 }} />
                </div>
                <span className="w-6 text-right text-xs font-medium">{row.count}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Team performance */}
        <Card className="p-4">
          <p className="mb-3 text-xs font-semibold">Team performance</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[26rem] text-left text-xs">
              <thead>
                <tr className="border-b border-edge text-[10px] uppercase text-faint">
                  <th className="py-1.5 font-medium">Member</th>
                  <th className="py-1.5 text-right font-medium">Leads</th>
                  <th className="py-1.5 text-right font-medium">Converted</th>
                  <th className="py-1.5 text-right font-medium">Bookings</th>
                  <th className="py-1.5 text-right font-medium">Revenue</th>
                </tr>
              </thead>
              <tbody>
                {team.map((row) => (
                  <tr key={row.user_id} className="border-b border-edge/50 last:border-0">
                    <td className="py-2">
                      <p className="font-medium">{row.name}</p>
                      <p className="text-[10px] text-faint">{row.role.replace(/_/g, " ")}</p>
                    </td>
                    <td className="py-2 text-right">{row.leads}</td>
                    <td className="py-2 text-right">{row.converted}</td>
                    <td className="py-2 text-right">{row.bookings}</td>
                    <td className="py-2 text-right font-medium text-success">{formatINR(row.revenue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Source performance */}
        <Card className="p-4">
          <p className="mb-3 text-xs font-semibold">Source performance</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[26rem] text-left text-xs">
              <thead>
                <tr className="border-b border-edge text-[10px] uppercase text-faint">
                  <th className="py-1.5 font-medium">Source</th>
                  <th className="py-1.5 text-right font-medium">Leads</th>
                  <th className="py-1.5 text-right font-medium">Converted</th>
                  <th className="py-1.5 text-right font-medium">Booked</th>
                  <th className="py-1.5 text-right font-medium">Conv. rate</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((row) => (
                  <tr key={row.source} className="border-b border-edge/50 last:border-0">
                    <td className="py-2 font-medium">{row.source.replace(/_/g, " ")}</td>
                    <td className="py-2 text-right">{row.leads}</td>
                    <td className="py-2 text-right">{row.converted}</td>
                    <td className="py-2 text-right">{row.booked}</td>
                    <td className="py-2 text-right">{row.conversion_rate}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
