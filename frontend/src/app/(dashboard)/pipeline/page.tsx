"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge, PageHeader, SkeletonRows, cx } from "@/components/ui";
import { STAGE_COLORS, STAGE_LABELS, formatINR, timeAgo } from "@/lib/format";

interface Lead {
  id: string;
  full_name: string;
  phone: string;
  budget_max: string | null;
  score_band: string | null;
  assignee: { full_name: string } | null;
  updated_at: string;
}

type Board = Record<string, Lead[]>;

export default function PipelinePage() {
  const router = useRouter();
  const [board, setBoard] = useState<Board | null>(null);
  const [order, setOrder] = useState<string[]>([]);
  const [dragging, setDragging] = useState<{ leadId: string; from: string } | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await api<{ data: Board; meta: { stage_order: string[] } }>("/pipeline/board");
    setBoard(res.data);
    setOrder(res.meta.stage_order);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function moveTo(stage: string) {
    if (!dragging || !board || dragging.from === stage) {
      setDragging(null);
      setDropTarget(null);
      return;
    }
    const { leadId, from } = dragging;
    const lead = board[from].find((l) => l.id === leadId);
    setDragging(null);
    setDropTarget(null);
    if (!lead) return;

    const reopen = from === "lost" || from === "completed";
    if (reopen && !confirm(`This lead is ${STAGE_LABELS[from]}. Reopen it and move to ${STAGE_LABELS[stage]}?`)) {
      return;
    }

    // Optimistic move; revert on failure.
    setBoard((b) => b && ({
      ...b,
      [from]: b[from].filter((l) => l.id !== leadId),
      [stage]: [lead, ...b[stage]],
    }));
    try {
      const body: { stage: string; lost_reason?: string; reopen?: boolean } = { stage, reopen };
      if (stage === "lost") {
        body.lost_reason = prompt("Reason for losing this lead?") ?? "Not specified";
      }
      await api(`/pipeline/leads/${leadId}/stage`, { method: "PATCH", body });
    } catch {
      load(); // revert to server truth
    }
  }

  if (!board) return <SkeletonRows rows={4} height={90} />;

  const totalActive = order
    .filter((s) => !["completed", "lost"].includes(s))
    .reduce((n, s) => n + (board[s]?.length ?? 0), 0);

  return (
    <div className="fade-up flex h-[calc(100dvh-110px)] flex-col">
      <PageHeader
        title="Pipeline"
        subtitle={`${totalActive} active leads — drag cards between stages`}
      />
      <div className="flex flex-1 gap-3 overflow-x-auto pb-2">
        {order.map((stage) => (
          <div
            key={stage}
            onDragOver={(e) => {
              e.preventDefault();
              setDropTarget(stage);
            }}
            onDragLeave={() => setDropTarget((t) => (t === stage ? null : t))}
            onDrop={() => moveTo(stage)}
            className={cx(
              "flex w-60 shrink-0 flex-col rounded-xl border bg-surface/60 transition-colors",
              dropTarget === stage ? "border-primary bg-primary/[0.06]" : "border-edge"
            )}
          >
            <div className="flex items-center justify-between px-3 py-2.5">
              <span className="flex items-center gap-1.5 text-[11px] font-semibold">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: STAGE_COLORS[stage] }}
                />
                {STAGE_LABELS[stage]}
              </span>
              <span className="rounded-full bg-raised px-1.5 py-0.5 text-[10px] text-muted">
                {board[stage]?.length ?? 0}
              </span>
            </div>
            <div className="flex-1 space-y-2 overflow-y-auto px-2 pb-2">
              {(board[stage] ?? []).map((lead) => (
                <div
                  key={lead.id}
                  draggable
                  onDragStart={() => setDragging({ leadId: lead.id, from: stage })}
                  onDragEnd={() => { setDragging(null); setDropTarget(null); }}
                  onClick={() => router.push(`/leads/${lead.id}`)}
                  className={cx(
                    "cursor-grab rounded-lg border border-edge bg-surface p-2.5 shadow-sm",
                    "transition-all hover:border-edge-strong active:cursor-grabbing",
                    dragging?.leadId === lead.id && "opacity-40"
                  )}
                >
                  <div className="flex items-start justify-between gap-1">
                    <p className="text-xs font-medium leading-snug">{lead.full_name}</p>
                    {lead.score_band && (
                      <Badge
                        color={{ hot: "#ef4444", warm: "#f59e0b", cold: "#8b98ac" }[lead.score_band] ?? "#8b98ac"}
                      >
                        {lead.score_band}
                      </Badge>
                    )}
                  </div>
                  <p className="mt-1 text-[10px] text-faint">
                    {formatINR(lead.budget_max)} · {lead.assignee?.full_name ?? "Unassigned"}
                  </p>
                  <p className="mt-0.5 text-[10px] text-faint">{timeAgo(lead.updated_at)}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
