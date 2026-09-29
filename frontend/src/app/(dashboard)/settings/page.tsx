"use client";

import { useCallback, useEffect, useState } from "react";
import { MonitorSmartphone, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { Avatar, Badge, Button, Card, PageHeader, SkeletonRows } from "@/components/ui";
import { formatDateTime, timeAgo } from "@/lib/format";

interface Session {
  id: string; user_agent: string | null; ip_address: string | null;
  created_at: string; expires_at: string;
}

export default function SettingsPage() {
  const { user } = useAuth();
  const [sessions, setSessions] = useState<Session[] | null>(null);

  const load = useCallback(async () => {
    const res = await api<{ data: Session[] }>("/auth/sessions");
    setSessions(res.data);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function revoke(id: string) {
    await api(`/auth/sessions/${id}`, { method: "DELETE" });
    load();
  }

  if (!user) return null;

  return (
    <div className="fade-up max-w-2xl">
      <PageHeader title="Settings" />

      <Card className="mb-4 flex items-center gap-4 p-5">
        <Avatar name={user.full_name} color={user.avatar_color} size={52} />
        <div className="flex-1">
          <p className="text-sm font-semibold">{user.full_name}</p>
          <p className="text-xs text-muted">{user.email}{user.phone ? ` · ${user.phone}` : ""}</p>
          <div className="mt-1.5 flex gap-2">
            <Badge color="#3b82f6">{ROLE_LABELS[user.role] ?? user.role}</Badge>
            <Badge color={user.email_verified ? "#10b981" : "#f59e0b"}>
              <ShieldCheck size={10} />
              {user.email_verified ? "Email verified" : "Email not verified"}
            </Badge>
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold">
          <MonitorSmartphone size={13} /> Active sessions
        </p>
        <p className="mb-3 text-[11px] text-muted">
          Each sign-in creates a session. Revoke any you don&apos;t recognize —
          this signs that device out immediately.
        </p>
        {sessions === null ? (
          <SkeletonRows rows={2} />
        ) : sessions.length === 0 ? (
          <p className="text-xs text-faint">No active sessions.</p>
        ) : (
          <ul className="space-y-2">
            {sessions.map((s) => (
              <li key={s.id} className="flex items-center justify-between rounded-lg border border-edge px-3 py-2.5">
                <div>
                  <p className="max-w-md truncate text-xs">
                    {s.user_agent ?? "Unknown device"}
                  </p>
                  <p className="mt-0.5 text-[10px] text-faint">
                    {s.ip_address ?? "unknown IP"} · started {timeAgo(s.created_at)} ·
                    expires {formatDateTime(s.expires_at)}
                  </p>
                </div>
                <Button size="sm" variant="danger" onClick={() => revoke(s.id)}>
                  <Trash2 size={12} /> Revoke
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
