"use client";

import Link from "next/link";
import { ArrowRight, Flame, IndianRupee, TrendingUp, Users } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useApiSWR } from "@/lib/useApiSWR";
import { Card, PageHeader, SkeletonRows, cx } from "@/components/ui";
import { STAGE_COLORS, STAGE_LABELS, STAGE_ORDER, formatDateTime, formatINR } from "@/lib/format";

interface Overview {
  total_leads: number;
  active_leads: number;
  converted_leads: number;
  conversion_rate: number;
  bookings_total: number;
  bookings_active: number;
  revenue_collected: number;
  pipeline_value: number;
  site_visits: number;
  hot_leads: number;
}

interface FunnelRow { stage: string; count: number }
interface Task { id: string; title: string; due_date: string | null; priority: string; status: string }

const PRIORITY_COLORS: Record<string, string> = {
  urgent: "#ef4444", high: "#f59e0b", medium: "#3b82f6", low: "#8b98ac",
};

function Stat({ label, value, sub, icon: Icon, accent }: {
  label: string; value: string; sub?: string;
  icon: React.ComponentType<{ size?: number }>; accent: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wide text-faint">{label}</p>
          <p className="mt-1 text-xl font-semibold">{value}</p>
          {sub && <p className="mt-0.5 text-[11px] text-muted">{sub}</p>}
        </div>
        <span className="rounded-lg p-2" style={{ backgroundColor: `${accent}22`, color: accent }}>
          <Icon size={16} />
        </span>
      </div>
    </Card>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { data: overviewData } = useApiSWR<{ data: Overview }>("/analytics/overview");
  const { data: funnelData } = useApiSWR<{ data: FunnelRow[] }>("/analytics/funnel");
  const { data: tasksData } = useApiSWR<{ data: Task[] }>("/tasks?status=todo&limit=6");

  const overview = overviewData?.data ?? null;
  const funnel = funnelData?.data ?? [];
  const tasks = tasksData?.data ?? [];

  const funnelMax = Math.max(1, ...funnel.map((f) => f.count));

  return (
    <div className="fade-up">
      <PageHeader
        title={`Good ${new Date().getHours() < 12 ? "morning" : new Date().getHours() < 17 ? "afternoon" : "evening"}, ${user?.full_name.split(" ")[0]}`}
        subtitle="Here's what's moving in your pipeline today."
      />
      {!overview ? (
        <SkeletonRows rows={3} height={80} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Active leads" value={String(overview.active_leads)}
                  sub={`${overview.total_leads} total · ${overview.hot_leads} hot`}
                  icon={Users} accent="#3b82f6" />
            <Stat label="Conversion rate" value={`${overview.conversion_rate}%`}
                  sub={`${overview.converted_leads} converted`}
                  icon={TrendingUp} accent="#8b5cf6" />
            <Stat label="Revenue collected" value={formatINR(overview.revenue_collected)}
                  sub={`Pipeline ${formatINR(overview.pipeline_value)}`}
                  icon={IndianRupee} accent="#10b981" />
            <Stat label="Bookings" value={String(overview.bookings_total)}
                  sub={`${overview.bookings_active} active · ${overview.site_visits} site visits`}
                  icon={Flame} accent="#f59e0b" />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-5">
            {/* Funnel */}
            <Card className="p-4 lg:col-span-3">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-xs font-semibold">Sales funnel</p>
                <Link href="/pipeline" className="flex items-center gap-1 text-[11px] text-primary hover:underline">
                  Open pipeline <ArrowRight size={11} />
                </Link>
              </div>
              <div className="space-y-2">
                {funnel.map((row) => (
                  <div key={row.stage} className="flex items-center gap-2">
                    <span className="w-36 shrink-0 text-[11px] text-muted">
                      {STAGE_LABELS[row.stage]}
                    </span>
                    <div className="h-5 flex-1 overflow-hidden rounded bg-raised">
                      <div
                        className="h-full rounded transition-all"
                        style={{
                          width: `${(row.count / funnelMax) * 100}%`,
                          backgroundColor: STAGE_COLORS[row.stage],
                          minWidth: row.count > 0 ? 20 : 0,
                        }}
                      />
                    </div>
                    <span className="w-6 text-right text-xs font-medium">{row.count}</span>
                  </div>
                ))}
              </div>
            </Card>

            {/* Today's tasks */}
            <Card className="p-4 lg:col-span-2">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-xs font-semibold">Open tasks</p>
                <Link href="/tasks" className="flex items-center gap-1 text-[11px] text-primary hover:underline">
                  All tasks <ArrowRight size={11} />
                </Link>
              </div>
              {tasks.length === 0 ? (
                <p className="py-8 text-center text-xs text-faint">
                  No open tasks — create one from the New menu.
                </p>
              ) : (
                <ul className="space-y-2">
                  {tasks.map((t) => (
                    <li key={t.id} className="flex items-center gap-2 rounded-lg border border-edge px-3 py-2">
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: PRIORITY_COLORS[t.priority] }}
                        title={t.priority}
                      />
                      <span className={cx("flex-1 truncate text-xs")}>{t.title}</span>
                      <span className="shrink-0 text-[10px] text-faint">
                        {t.due_date ? formatDateTime(t.due_date) : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
