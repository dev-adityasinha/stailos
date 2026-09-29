"use client";

import { useCallback, useEffect, useState } from "react";
import { Bell, CheckCheck } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, EmptyState, PageHeader, SkeletonRows, cx } from "@/components/ui";
import { timeAgo } from "@/lib/format";

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  entity_type: string | null;
  entity_id: string | null;
  read: boolean;
  created_at: string;
}

const TYPE_META: Record<string, { label: string; color: string }> = {
  assignment: { label: "Assignment", color: "#3b82f6" },
  follow_up: { label: "Follow-up", color: "#06b6d4" },
  booking_update: { label: "Booking", color: "#10b981" },
  task: { label: "Task", color: "#f59e0b" },
  ai_suggestion: { label: "AI suggestion", color: "#8b5cf6" },
  system: { label: "System", color: "#8b98ac" },
};

export default function NotificationsPage() {
  const [items, setItems] = useState<Notification[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [onlyUnread, setOnlyUnread] = useState(false);

  const load = useCallback(async () => {
    const res = await api<{ data: Notification[]; meta: { unread: number } }>(
      "/notifications",
      { params: { unread: onlyUnread, limit: 100 } }
    );
    setItems(res.data);
    setUnread(res.meta.unread);
  }, [onlyUnread]);

  useEffect(() => { load(); }, [load]);

  async function markRead(id: string) {
    await api(`/notifications/${id}/read`, { method: "PATCH" });
    load();
  }

  async function markAll() {
    await api("/notifications/read-all", { method: "POST" });
    load();
  }

  return (
    <div className="fade-up max-w-3xl">
      <PageHeader
        title="Notification center"
        subtitle={`${unread} unread`}
        actions={
          <>
            <Button variant={onlyUnread ? "primary" : "secondary"} size="sm"
                    onClick={() => setOnlyUnread((o) => !o)}>
              <Bell size={13} /> Unread only
            </Button>
            {unread > 0 && (
              <Button variant="secondary" size="sm" onClick={markAll}>
                <CheckCheck size={13} /> Mark all read
              </Button>
            )}
          </>
        }
      />
      <Card>
        {items === null ? (
          <SkeletonRows />
        ) : items.length === 0 ? (
          <EmptyState
            title={onlyUnread ? "Nothing unread" : "No notifications yet"}
            hint="Assignment alerts, follow-up reminders, booking updates and AI suggestions appear here."
          />
        ) : (
          <ul className="divide-y divide-edge/60">
            {items.map((n) => {
              const meta = TYPE_META[n.type] ?? TYPE_META.system;
              return (
                <li
                  key={n.id}
                  className={cx("flex items-start gap-3 px-4 py-3", !n.read && "bg-primary/[0.05]")}
                >
                  <span className="mt-1 h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: n.read ? "transparent" : meta.color }} />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs">{n.title}</p>
                    {n.body && <p className="mt-0.5 text-[11px] text-muted">{n.body}</p>}
                    <p className="mt-1 text-[10px] text-faint">{timeAgo(n.created_at)}</p>
                  </div>
                  <Badge color={meta.color}>{meta.label}</Badge>
                  {!n.read && (
                    <Button size="sm" variant="ghost" onClick={() => markRead(n.id)}>
                      Mark read
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
