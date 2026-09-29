"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft, CalendarPlus, MessageSquare, Sparkles, Tag as TagIcon, UserCheck, Wand2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApiSWR } from "@/lib/useApiSWR";
import { MANAGER_ROLES, useAuth } from "@/lib/auth";
import {
  AIPanel, Badge, Button, Card, ErrorNote, Input, Modal, Select, SkeletonRows,
  Spinner, Textarea,
} from "@/components/ui";
import {
  STAGE_COLORS, STAGE_LABELS, STAGE_ORDER, formatDateTime, formatINR, timeAgo,
} from "@/lib/format";

interface LeadDetail {
  id: string;
  full_name: string;
  phone: string;
  email: string | null;
  source: string;
  campaign: string | null;
  stage: string;
  assigned_to: string | null;
  assignee: { id: string; full_name: string } | null;
  budget_min: string | null;
  budget_max: string | null;
  location_preference: string | null;
  property_type: string | null;
  requirements: string | null;
  ai_score: number | null;
  score_band: string | null;
  customer_id: string | null;
  lost_reason: string | null;
  tags: { id: string; name: string; color: string | null }[];
  notes: { id: string; author_name: string | null; body: string; created_at: string }[];
  created_at: string;
}

interface Activity {
  id: string;
  type: string;
  title: string;
  actor_name: string | null;
  created_at: string;
}

interface TeamUser { id: string; full_name: string; role: string }

/** Result of POST /ai/components/lead-qualification. The score is computed by a
 *  deterministic engine (backend/app/modules/ai/grading.py) using the weights
 *  the admin set during onboarding, so it is safe to show as fact. */
interface Qualification {
  ai_score: number;
  score_band: string;
  grade: string;
  recommended_action: string;
  needs_human_review: boolean;
  weights: Record<string, number>;
  breakdown: Record<string, { score: number; contributing_factors: string[] }>;
}

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [timeline, setTimeline] = useState<Activity[]>([]);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [tagName, setTagName] = useState("");
  const [aiSummary, setAiSummary] = useState<string>("");
  const [nextAction, setNextAction] = useState<{ action: string; reason: string } | null>(null);
  const [qualification, setQualification] = useState<Qualification | null>(null);

  /* Which AI actions this workspace allows, from its onboarding consent and
     feature answers. Fetched through SWR rather than a mount-time effect on
     purpose: an admin can change the policy on another page, and Next's client
     router can restore this page without remounting it — a one-shot fetch would
     leave the panel offering actions the server now refuses. SWR revalidates on
     focus and on an interval, so the panel converges. */
  const { data: aiCatalogResponse } = useApiSWR<{
    data: { widgets: string[]; components: string[]; ai_consent: boolean };
  }>("/ai/catalog");
  const aiCatalog = aiCatalogResponse?.data ?? null;
  const [drafts, setDrafts] = useState<Record<string, string> | null>(null);
  const [aiBusy, setAiBusy] = useState("");
  const [team, setTeam] = useState<TeamUser[]>([]);
  const [showAssign, setShowAssign] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [visitForm, setVisitForm] = useState({ start_at: "", end_at: "", location: "" });
  const [visitAttendees, setVisitAttendees] = useState<string[]>([]);
  const [visitBusy, setVisitBusy] = useState(false);
  const canManage = user && MANAGER_ROLES.has(user.role);

  const load = useCallback(async () => {
    try {
      const res = await api<{ data: LeadDetail }>(`/leads/${id}`);
      setLead(res.data);
      const tl = await api<{ data: Activity[] }>(`/leads/${id}/timeline`);
      setTimeline(tl.data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load lead.");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (canManage) {
      api<{ data: TeamUser[] }>("/users").then((r) => setTeam(r.data)).catch(() => {});
    }
  }, [canManage]);


  /** Until the catalog loads, show everything — a slow request shouldn't make
   *  the panel look empty. Once it arrives it is authoritative. */
  function aiAllowed(kind: "widget" | "component", name: string): boolean {
    if (!aiCatalog) return true;
    return (kind === "widget" ? aiCatalog.widgets : aiCatalog.components).includes(name);
  }

  async function changeStage(stage: string) {
    if (!lead || stage === lead.stage) return;
    let lost_reason: string | null = null;
    if (stage === "lost") {
      lost_reason = prompt("Reason for losing this lead?") ?? "Not specified";
    }
    const reopen = lead.stage === "lost" || lead.stage === "completed";
    if (reopen && !confirm(`This lead is ${lead.stage}. Reopen it and move to ${STAGE_LABELS[stage]}?`)) {
      return;
    }
    try {
      await api(`/pipeline/leads/${id}/stage`, {
        method: "PATCH",
        body: { stage, lost_reason, reopen },
      });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to change stage.");
    }
  }

  async function scheduleSiteVisit(e: React.FormEvent) {
    e.preventDefault();
    if (!visitForm.start_at) return;
    setVisitBusy(true);
    try {
      await api(`/leads/${id}/schedule-site-visit`, {
        method: "POST",
        body: {
          start_at: new Date(visitForm.start_at).toISOString(),
          end_at: visitForm.end_at ? new Date(visitForm.end_at).toISOString() : null,
          location: visitForm.location || null,
          attendee_ids: visitAttendees,
        },
      });
      setShowSchedule(false);
      setVisitForm({ start_at: "", end_at: "", location: "" });
      setVisitAttendees([]);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to schedule site visit.");
    } finally {
      setVisitBusy(false);
    }
  }

  async function addNote(e: React.FormEvent) {
    e.preventDefault();
    if (!note.trim()) return;
    await api(`/leads/${id}/notes`, { method: "POST", body: { body: note.trim() } });
    setNote("");
    load();
  }

  async function addTag(e: React.FormEvent) {
    e.preventDefault();
    if (!tagName.trim()) return;
    await api(`/leads/${id}/tags`, { method: "POST", body: { name: tagName.trim() } });
    setTagName("");
    load();
  }

  async function convert() {
    try {
      const res = await api<{ data: { id: string } }>(`/leads/${id}/convert`, {
        method: "POST",
        body: {},
      });
      router.push(`/customers/${res.data.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Conversion failed.");
    }
  }

  async function runAI(kind: "summary" | "next" | "qualify" | "drafts") {
    setAiBusy(kind);
    try {
      if (kind === "summary") {
        const res = await api<{ data: { result: { summary: string } } }>(
          "/ai/widgets/lead-summary",
          { method: "POST", body: { lead_id: id } }
        );
        setAiSummary(res.data.result.summary);
      } else if (kind === "next") {
        const res = await api<{ data: { result: { action: string; reason: string } } }>(
          "/ai/widgets/next-best-action",
          { method: "POST", body: { lead_id: id } }
        );
        setNextAction(res.data.result);
      } else if (kind === "qualify") {
        const res = await api<{ data: { result: Qualification } }>(
          "/ai/components/lead-qualification",
          { method: "POST", body: { lead_id: id } }
        );
        // The scoring engine returns a per-dimension breakdown; showing it is
        // what makes the number arguable rather than a black box.
        setQualification(res.data.result);
        load();
      } else {
        const res = await api<{ data: { result: { drafts: Record<string, string> } } }>(
          "/ai/components/follow-up",
          { method: "POST", body: { lead_id: id } }
        );
        setDrafts(res.data.result.drafts);
      }
    } finally {
      setAiBusy("");
    }
  }

  if (error && !lead) return <ErrorNote message={error} />;
  if (!lead) return <SkeletonRows rows={6} height={60} />;

  const BAND_COLORS: Record<string, string> = { hot: "#ef4444", warm: "#f59e0b", cold: "#8b98ac" };

  return (
    <div className="fade-up">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link href="/leads" className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-ink">
            <ArrowLeft size={16} />
          </Link>
          <div>
            <h1 className="text-lg font-semibold">{lead.full_name}</h1>
            <p className="text-xs text-muted">
              {lead.phone} {lead.email ? `· ${lead.email}` : ""} · via {lead.source.replace(/_/g, " ")}
            </p>
          </div>
          <Badge color={STAGE_COLORS[lead.stage]}>{STAGE_LABELS[lead.stage]}</Badge>
          {lead.score_band && (
            <Badge color={BAND_COLORS[lead.score_band]}>
              {lead.score_band} {lead.ai_score != null ? `· ${lead.ai_score}` : ""}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={lead.stage}
            onChange={(e) => changeStage(e.target.value)}
            className="w-48"
            aria-label="Change stage"
          >
            {STAGE_ORDER.map((s) => <option key={s} value={s}>{STAGE_LABELS[s]}</option>)}
          </Select>
          <Button variant="secondary" onClick={() => setShowSchedule(true)}>
            <CalendarPlus size={14} /> Schedule visit
          </Button>
          {canManage && (
            <Button variant="secondary" onClick={() => setShowAssign(true)}>Reassign</Button>
          )}
          {lead.customer_id ? (
            <Link href={`/customers/${lead.customer_id}`}>
              <Button variant="secondary"><UserCheck size={14} /> View customer</Button>
            </Link>
          ) : (
            <Button onClick={convert}><UserCheck size={14} /> Convert to customer</Button>
          )}
        </div>
      </div>

      {error && <div className="mb-3"><ErrorNote message={error} /></div>}

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Left: profile + timeline */}
        <div className="space-y-4 lg:col-span-2">
          <Card className="grid grid-cols-2 gap-x-6 gap-y-3 p-4 sm:grid-cols-3">
            {[
              ["Budget", `${formatINR(lead.budget_min)} – ${formatINR(lead.budget_max)}`],
              ["Property type", lead.property_type ?? "—"],
              ["Location", lead.location_preference ?? "—"],
              ["Owner", lead.assignee?.full_name ?? "Unassigned"],
              ["Campaign", lead.campaign ?? "—"],
              ["Created", formatDateTime(lead.created_at)],
            ].map(([label, value]) => (
              <div key={label as string}>
                <p className="text-[10px] uppercase tracking-wide text-faint">{label}</p>
                <p className="mt-0.5 text-xs">{value}</p>
              </div>
            ))}
            {lead.requirements && (
              <div className="col-span-full">
                <p className="text-[10px] uppercase tracking-wide text-faint">Requirements</p>
                <p className="mt-0.5 text-xs text-muted">{lead.requirements}</p>
              </div>
            )}
            {lead.lost_reason && (
              <div className="col-span-full">
                <p className="text-[10px] uppercase tracking-wide text-danger">Lost reason</p>
                <p className="mt-0.5 text-xs text-muted">{lead.lost_reason}</p>
              </div>
            )}
            <div className="col-span-full flex flex-wrap items-center gap-2">
              <TagIcon size={13} className="text-faint" />
              {lead.tags.map((t) => (
                <Badge key={t.id} color={t.color ?? "#3b82f6"}>{t.name}</Badge>
              ))}
              <form onSubmit={addTag}>
                <input
                  value={tagName}
                  onChange={(e) => setTagName(e.target.value)}
                  placeholder="+ tag"
                  className="w-20 rounded border border-edge bg-transparent px-2 py-0.5 text-[11px] outline-none focus:border-primary"
                />
              </form>
            </div>
          </Card>

          {/* Notes */}
          <Card className="p-4">
            <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold">
              <MessageSquare size={13} /> Notes
            </p>
            <form onSubmit={addNote} className="mb-3 flex gap-2">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Log a call, meeting or observation…"
                className="flex-1 rounded-lg border border-edge-strong bg-bg px-3 py-2 text-xs outline-none focus:border-primary"
              />
              <Button size="sm" type="submit">Add</Button>
            </form>
            {lead.notes.length === 0 ? (
              <p className="py-2 text-xs text-faint">No notes yet.</p>
            ) : (
              <ul className="space-y-2">
                {lead.notes.map((n) => (
                  <li key={n.id} className="rounded-lg border border-edge px-3 py-2">
                    <p className="text-xs">{n.body}</p>
                    <p className="mt-1 text-[10px] text-faint">
                      {n.author_name ?? "Unknown"} · {timeAgo(n.created_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Timeline */}
          <Card className="p-4">
            <p className="mb-3 text-xs font-semibold">Timeline</p>
            <ol className="relative ml-2 space-y-3 border-l border-edge pl-4">
              {timeline.map((a) => (
                <li key={a.id} className="relative">
                  <span
                    className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-surface"
                    style={{ backgroundColor: a.type === "ai_recommendation" ? "#8b5cf6" : "#3b82f6" }}
                  />
                  <p className="text-xs">{a.title}</p>
                  <p className="text-[10px] text-faint">
                    {a.actor_name ? `${a.actor_name} · ` : ""}{formatDateTime(a.created_at)}
                  </p>
                </li>
              ))}
            </ol>
          </Card>
        </div>

        {/* Right: Ask Pappu AI dock (PRD §7.2) */}
        <div className="space-y-3">
          <AIPanel title="Ask Pappu">
            {aiCatalog && !aiCatalog.ai_consent && (
              <p className="mb-3 rounded-lg bg-warning/10 px-3 py-2 text-[11px] text-warning">
                AI is switched off for this workspace — AI usage consent was
                declined during setup. An admin can change it under
                Settings → Company profile.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {aiAllowed("widget", "lead-summary") && (
                <Button size="sm" variant="ai" disabled={!!aiBusy} onClick={() => runAI("summary")}>
                  {aiBusy === "summary" ? <Spinner size={12} /> : <Sparkles size={12} />} Summarize
                </Button>
              )}
              {aiAllowed("component", "lead-qualification") && (
                <Button size="sm" variant="ai" disabled={!!aiBusy} onClick={() => runAI("qualify")}>
                  {aiBusy === "qualify" ? <Spinner size={12} /> : <Wand2 size={12} />} Score lead
                </Button>
              )}
              {aiAllowed("widget", "next-best-action") && (
                <Button size="sm" variant="ai" disabled={!!aiBusy} onClick={() => runAI("next")}>
                  {aiBusy === "next" ? <Spinner size={12} /> : <Sparkles size={12} />} Next action
                </Button>
              )}
              {aiAllowed("component", "follow-up") && (
                <Button size="sm" variant="ai" disabled={!!aiBusy} onClick={() => runAI("drafts")}>
                  {aiBusy === "drafts" ? <Spinner size={12} /> : <Wand2 size={12} />} Draft follow-up
                </Button>
              )}
            </div>
            {aiSummary && (
              <p className="mt-3 rounded-lg bg-bg/60 p-3 text-xs leading-relaxed text-muted">
                {aiSummary}
              </p>
            )}
            {nextAction && (
              <div className="mt-3 rounded-lg bg-bg/60 p-3">
                <p className="text-xs font-medium text-ink">{nextAction.action}</p>
                <p className="mt-1 text-[11px] text-muted">{nextAction.reason}</p>
              </div>
            )}
            {qualification && (
              <div className="mt-3 rounded-lg bg-bg/60 p-3">
                <div className="flex items-baseline justify-between">
                  <p className="text-xs font-medium text-ink">
                    Grade {qualification.grade} · {qualification.ai_score}/100
                  </p>
                  <Badge color={BAND_COLORS[qualification.score_band]}>
                    {qualification.score_band}
                  </Badge>
                </div>
                <ul className="mt-2 space-y-1">
                  {Object.entries(qualification.breakdown).map(([dimension, detail]) => (
                    <li key={dimension} className="text-[11px]">
                      <div className="flex items-center justify-between gap-2 text-muted">
                        <span className="capitalize">{dimension.replace(/_/g, " ")}</span>
                        <span className="tabular-nums">
                          {detail.score}/100
                          <span className="ml-1 text-faint">
                            ×{Math.round((qualification.weights[dimension] ?? 0) * 100)}%
                          </span>
                        </span>
                      </div>
                      <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-raised">
                        <div className="h-full bg-primary" style={{ width: `${detail.score}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[11px] text-muted">
                  {qualification.recommended_action}
                </p>
                {qualification.needs_human_review && (
                  <p className="mt-1.5 text-[10px] text-warning">
                    This record is sparse — check the score against what you know before
                    acting on it.
                  </p>
                )}
              </div>
            )}
            {drafts && (
              <div className="mt-3 space-y-2">
                <p className="text-[10px] uppercase tracking-wide text-faint">
                  Drafts — review before sending
                </p>
                <div className="rounded-lg bg-bg/60 p-3">
                  <p className="text-[10px] font-semibold text-faint">WhatsApp</p>
                  <p className="mt-1 text-xs text-muted">{drafts.whatsapp}</p>
                </div>
                <div className="rounded-lg bg-bg/60 p-3">
                  <p className="text-[10px] font-semibold text-faint">Email — {drafts.email_subject}</p>
                  <p className="mt-1 whitespace-pre-line text-xs text-muted">{drafts.email_body}</p>
                </div>
              </div>
            )}
          </AIPanel>
        </div>
      </div>

      {/* Reassign modal */}
      <Modal open={showAssign} onClose={() => setShowAssign(false)} title="Reassign lead">
        <div className="space-y-2">
          {team.filter((t) => t.id !== lead.assigned_to).map((t) => (
            <button
              key={t.id}
              onClick={async () => {
                await api(`/leads/${id}/assign`, { method: "POST", body: { user_id: t.id } });
                setShowAssign(false);
                load();
              }}
              className="flex w-full items-center justify-between rounded-lg border border-edge px-3 py-2 text-left text-xs hover:border-primary hover:bg-raised"
            >
              <span>{t.full_name}</span>
              <span className="text-faint">{t.role.replace(/_/g, " ")}</span>
            </button>
          ))}
        </div>
      </Modal>

      {/* Schedule site visit modal */}
      <Modal open={showSchedule} onClose={() => setShowSchedule(false)} title="Schedule site visit">
        <form onSubmit={scheduleSiteVisit} className="space-y-3">
          <Input
            label="Start"
            type="datetime-local"
            value={visitForm.start_at}
            onChange={(e) => setVisitForm((f) => ({ ...f, start_at: e.target.value }))}
            required
          />
          <Input
            label="End (optional)"
            type="datetime-local"
            value={visitForm.end_at}
            onChange={(e) => setVisitForm((f) => ({ ...f, end_at: e.target.value }))}
          />
          <Input
            label="Location"
            placeholder="Model flat, Tower B"
            value={visitForm.location}
            onChange={(e) => setVisitForm((f) => ({ ...f, location: e.target.value }))}
          />
          {canManage && team.length > 0 && (
            <div>
              <span className="mb-1.5 block text-xs font-medium text-muted">Invite team members</span>
              <div className="max-h-32 space-y-1 overflow-y-auto rounded-lg border border-edge p-2">
                {team.map((t) => (
                  <label key={t.id} className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={visitAttendees.includes(t.id)}
                      onChange={(e) =>
                        setVisitAttendees((prev) =>
                          e.target.checked ? [...prev, t.id] : prev.filter((x) => x !== t.id)
                        )
                      }
                    />
                    {t.full_name}
                  </label>
                ))}
              </div>
            </div>
          )}
          <p className="text-[11px] text-faint">
            The lead&apos;s owner is invited automatically and everyone gets an email with a
            calendar (.ics) invite.
          </p>
          <Button type="submit" disabled={visitBusy} className="w-full justify-center">
            {visitBusy ? <Spinner size={12} /> : <CalendarPlus size={12} />} Schedule &amp; send invites
          </Button>
        </form>
      </Modal>
    </div>
  );
}
