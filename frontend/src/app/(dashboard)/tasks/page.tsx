"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { CheckCircle2, Circle, Clock, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { MANAGER_ROLES, useAuth } from "@/lib/auth";
import {
  Badge, Button, Card, EmptyState, Input, Modal, PageHeader, Select,
  SkeletonRows, Textarea, cx,
} from "@/components/ui";
import { formatDateTime, timeAgo } from "@/lib/format";

interface Task {
  id: string;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  due_date: string | null;
  assignee: { id: string; full_name: string } | null;
  comments: { id: string; author_name: string | null; body: string; created_at: string }[];
  created_at: string;
}

interface TeamUser { id: string; full_name: string }

const PRIORITY_COLORS: Record<string, string> = {
  urgent: "#ef4444", high: "#f59e0b", medium: "#3b82f6", low: "#8b98ac",
};

function TasksInner() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [overdue, setOverdue] = useState(false);
  const [showNew, setShowNew] = useState(searchParams.get("new") === "1");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [team, setTeam] = useState<TeamUser[]>([]);
  // Computed in an effect (not during render) so overdue-ness stays a pure
  // function of state; refreshed every minute since it's a slow-changing value.
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);
  const [form, setForm] = useState({
    title: "", description: "", priority: "medium", due_date: "", assigned_to: "",
  });
  const canAssign = user && MANAGER_ROLES.has(user.role);

  useEffect(() => {
    if (searchParams.get("new") === "1") setShowNew(true);
  }, [searchParams]);

  const load = useCallback(async () => {
    const res = await api<{ data: Task[] }>("/tasks", {
      params: { status: statusFilter, overdue, limit: 100 },
    });
    setTasks(res.data);
  }, [statusFilter, overdue]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (canAssign) {
      api<{ data: TeamUser[] }>("/users").then((r) => setTeam(r.data)).catch(() => {});
    }
  }, [canAssign]);

  async function createTask(e: React.FormEvent) {
    e.preventDefault();
    await api("/tasks", {
      method: "POST",
      body: {
        title: form.title,
        description: form.description || null,
        priority: form.priority,
        due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
        assigned_to: form.assigned_to || null,
      },
    });
    setForm({ title: "", description: "", priority: "medium", due_date: "", assigned_to: "" });
    setShowNew(false);
    load();
  }

  async function toggleStatus(task: Task) {
    const next = task.status === "done" ? "todo" : "done";
    await api(`/tasks/${task.id}`, { method: "PATCH", body: { status: next } });
    load();
  }

  async function addComment(taskId: string) {
    if (!comment.trim()) return;
    await api(`/tasks/${taskId}/comments`, { method: "POST", body: { body: comment.trim() } });
    setComment("");
    load();
  }

  return (
    <div className="fade-up">
      <PageHeader
        title="Tasks"
        actions={<Button onClick={() => setShowNew(true)}><Plus size={14} /> New task</Button>}
      />
      <div className="mb-4 flex gap-2">
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-36">
          <option value="">All statuses</option>
          <option value="todo">To do</option>
          <option value="in_progress">In progress</option>
          <option value="done">Done</option>
          <option value="cancelled">Cancelled</option>
        </Select>
        <Button variant={overdue ? "primary" : "secondary"} size="sm"
                onClick={() => setOverdue((o) => !o)}>
          <Clock size={13} /> Overdue only
        </Button>
      </div>
      <Card>
        {tasks === null ? (
          <SkeletonRows />
        ) : tasks.length === 0 ? (
          <EmptyState title="No tasks" hint="Create a task to track follow-ups and to-dos."
                      action={<Button size="sm" onClick={() => setShowNew(true)}><Plus size={13} /> New task</Button>} />
        ) : (
          <ul className="divide-y divide-edge/60">
            {tasks.map((t) => {
              const isOverdue = now !== null && t.due_date && t.status !== "done" &&
                new Date(t.due_date + "Z").getTime() < now;
              return (
                <li key={t.id} className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <button onClick={() => toggleStatus(t)} aria-label="Toggle done"
                            className="text-muted hover:text-success">
                      {t.status === "done"
                        ? <CheckCircle2 size={17} className="text-success" />
                        : <Circle size={17} />}
                    </button>
                    <button
                      className="flex-1 text-left"
                      onClick={() => setExpanded((x) => (x === t.id ? null : t.id))}
                    >
                      <span className={cx("text-xs font-medium",
                                          t.status === "done" && "text-faint line-through")}>
                        {t.title}
                      </span>
                      <span className="ml-2 text-[10px] text-faint">
                        {t.assignee?.full_name}
                      </span>
                    </button>
                    <Badge color={PRIORITY_COLORS[t.priority]}>{t.priority}</Badge>
                    {t.due_date && (
                      <span className={cx("text-[10px]", isOverdue ? "font-semibold text-danger" : "text-faint")}>
                        {isOverdue ? "overdue · " : ""}{formatDateTime(t.due_date)}
                      </span>
                    )}
                  </div>
                  {expanded === t.id && (
                    <div className="ml-8 mt-2 space-y-2">
                      {t.description && <p className="text-xs text-muted">{t.description}</p>}
                      {t.comments.map((c) => (
                        <p key={c.id} className="rounded-lg bg-raised px-3 py-1.5 text-[11px] text-muted">
                          {c.body}
                          <span className="ml-2 text-faint">
                            — {c.author_name ?? "Unknown"}, {timeAgo(c.created_at)}
                          </span>
                        </p>
                      ))}
                      <div className="flex gap-2">
                        <input
                          value={comment}
                          onChange={(e) => setComment(e.target.value)}
                          placeholder="Add a comment…"
                          className="flex-1 rounded-lg border border-edge bg-bg px-3 py-1.5 text-[11px] outline-none focus:border-primary"
                        />
                        <Button size="sm" variant="secondary" onClick={() => addComment(t.id)}>
                          Comment
                        </Button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Modal open={showNew} onClose={() => setShowNew(false)} title="New task">
        <form onSubmit={createTask} className="space-y-4">
          <Input label="Title *" required minLength={2} value={form.title}
                 onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
          <Textarea label="Description" value={form.description}
                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          <div className="grid grid-cols-2 gap-4">
            <Select label="Priority" value={form.priority}
                    onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}>
              {["low", "medium", "high", "urgent"].map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </Select>
            <Input label="Due" type="datetime-local" value={form.due_date}
                   onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))} />
          </div>
          {canAssign && team.length > 0 && (
            <Select label="Assign to" value={form.assigned_to}
                    onChange={(e) => setForm((f) => ({ ...f, assigned_to: e.target.value }))}>
              <option value="">Myself</option>
              {team.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </Select>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setShowNew(false)}>Cancel</Button>
            <Button type="submit">Create task</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default function TasksPage() {
  return (
    <Suspense fallback={<SkeletonRows />}>
      <TasksInner />
    </Suspense>
  );
}
