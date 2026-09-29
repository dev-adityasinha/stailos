"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, UserX } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { ADMIN_ROLES, ROLE_LABELS, useAuth } from "@/lib/auth";
import {
  Avatar, Badge, Button, Card, ErrorNote, Input, Modal, PageHeader,
  PasswordInput, Select, SkeletonRows,
} from "@/components/ui";
import { timeAgo } from "@/lib/format";

interface Member {
  id: string; full_name: string; email: string; role: string;
  is_active: boolean; avatar_color: string | null; manager_id: string | null;
  last_login_at: string | null;
}

export default function TeamPage() {
  const { user } = useAuth();
  const [members, setMembers] = useState<Member[] | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    full_name: "", email: "", password: "", role: "sales_executive",
  });
  const isAdmin = user && ADMIN_ROLES.has(user.role);

  const load = useCallback(async () => {
    const res = await api<{ data: Member[] }>("/users");
    setMembers(res.data);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/users", { method: "POST", body: form });
      setShowNew(false);
      setForm({ full_name: "", email: "", password: "", role: "sales_executive" });
      load();
    } catch (err) {
      setError(errorMessage(err, "Failed to create user."));
    }
  }

  async function changeRole(memberId: string, role: string) {
    setError("");
    try {
      await api(`/users/${memberId}/role`, { method: "PATCH", body: { role } });
      load();
    } catch (err) {
      setError(errorMessage(err, "Role change failed."));
    }
  }

  async function deactivate(memberId: string) {
    if (!confirm("Deactivate this user? They will be signed out and unable to log in.")) return;
    setError("");
    try {
      await api(`/users/${memberId}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(errorMessage(err, "Deactivation failed."));
    }
  }

  return (
    <div className="fade-up">
      <PageHeader
        title="Team & roles"
        subtitle="Manage users and their access level"
        actions={isAdmin ? (
          <Button onClick={() => setShowNew(true)}><Plus size={14} /> Add member</Button>
        ) : undefined}
      />
      {error && <div className="mb-3"><ErrorNote message={error} /></div>}
      <Card>
        {members === null ? (
          <SkeletonRows />
        ) : (
          <ul className="divide-y divide-edge/60">
            {members.map((m) => (
              <li key={m.id} className="flex items-center gap-3 px-4 py-3">
                <Avatar name={m.full_name} color={m.avatar_color} size={32} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">
                    {m.full_name}
                    {m.id === user?.id && <span className="ml-1.5 text-[10px] text-faint">(you)</span>}
                  </p>
                  <p className="truncate text-[10px] text-faint">
                    {m.email} · last login {m.last_login_at ? timeAgo(m.last_login_at) : "never"}
                  </p>
                </div>
                {!m.is_active && <Badge color="#ef4444">deactivated</Badge>}
                {isAdmin && m.id !== user?.id ? (
                  <>
                    <select
                      value={m.role}
                      onChange={(e) => changeRole(m.id, e.target.value)}
                      className="rounded-lg border border-edge bg-surface px-2 py-1.5 text-[11px] outline-none focus:border-primary"
                    >
                      {Object.entries(ROLE_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                    {m.is_active && (
                      <Button size="sm" variant="danger" title="Deactivate"
                              onClick={() => deactivate(m.id)}>
                        <UserX size={12} />
                      </Button>
                    )}
                  </>
                ) : (
                  <Badge color="#3b82f6">{ROLE_LABELS[m.role] ?? m.role}</Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal open={showNew} onClose={() => setShowNew(false)} title="Add team member">
        <form onSubmit={createUser} className="space-y-4">
          <Input label="Full name *" required minLength={2} value={form.full_name}
                 onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} />
          <Input label="Email *" type="email" required value={form.email}
                 onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
          <PasswordInput label="Temporary password *" required value={form.password}
                 onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                 placeholder="Min 10 chars, 1 uppercase, 1 number, 1 symbol" />
          <Select label="Role" value={form.role}
                  onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
            {Object.entries(ROLE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </Select>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setShowNew(false)}>Cancel</Button>
            <Button type="submit">Create member</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
