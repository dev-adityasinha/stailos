"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, KeyRound, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Button, Card, ErrorNote, Input, SkeletonRows } from "@/components/ui";
import { formatDateTime, timeAgo } from "@/lib/format";

interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

interface CreatedKey extends ApiKey {
  key: string;
}

const ADMIN_ROLES = new Set(["super_admin", "company_admin"]);

/**
 * API keys: the credential another system uses to call this CRM.
 *
 * The one piece of UX that matters here is that the key is shown exactly once.
 * The server stores only its hash, so there is no "show it again" to build, and
 * a panel that failed to say so would send people back looking for a key that
 * no longer exists anywhere. It stays on screen with a copy button until it is
 * dismissed, and the dismissal is what says the moment has passed.
 *
 * Admin-only, matching the endpoint. A key acts as the user who made it, so
 * issuing one hands out that user's access.
 */
export function ApiKeysCard() {
  const { user } = useAuth();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<CreatedKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  const isAdmin = user ? ADMIN_ROLES.has(user.role) : false;

  const load = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const res = await api<{ data: ApiKey[] }>("/api-keys");
      setKeys(res.data);
    } catch (e) {
      setError((e as Error).message);
      setKeys([]);
    }
  }, [isAdmin]);

  useEffect(() => {
    load();
  }, [load]);

  if (!isAdmin) return null;

  async function create() {
    if (!name.trim()) return;
    setCreating(true);
    setError("");
    try {
      const res = await api<{ data: CreatedKey }>("/api-keys", {
        method: "POST",
        body: { name: name.trim() },
      });
      setCreated(res.data);
      setCopied(false);
      setName("");
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreating(false);
    }
  }

  async function revoke(id: string) {
    setError("");
    try {
      await api(`/api-keys/${id}`, { method: "DELETE" });
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      // Clipboard blocked (insecure origin, denied permission). The key is on
      // screen and selectable, so there is still a way to take it.
      setError("Could not copy automatically. Select the key and copy it.");
    }
  }

  const live = (keys ?? []).filter((k) => k.revoked_at === null);

  return (
    <Card className="mt-4 p-5">
      <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold">
        <KeyRound size={13} /> API keys
      </p>
      <p className="mb-3 text-[11px] text-muted">
        For connecting another system to this workspace. A key acts as you, with your
        role and your data, and keeps working until you revoke it.
      </p>

      {error ? <ErrorNote message={error} /> : null}

      {created ? (
        <div className="mb-3 rounded-lg border border-edge bg-raised p-3">
          <p className="text-[11px] font-semibold">
            Copy {created.name} now. This is the only time it is shown.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 overflow-x-auto whitespace-nowrap rounded border border-edge bg-bg px-2 py-1.5 font-mono text-[11px]">
              {created.key}
            </code>
            <Button size="sm" onClick={() => copy(created.key)}>
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <button
            type="button"
            onClick={() => setCreated(null)}
            className="mt-2 text-[10px] text-muted underline underline-offset-2">
            I have saved it
          </button>
        </div>
      ) : null}

      <div className="mb-3 flex items-end gap-2">
        <div className="flex-1">
          <Input
            label="New key name"
            placeholder="Viralitea"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <Button size="sm" onClick={create} disabled={creating || !name.trim()}>
          <Plus size={12} /> {creating ? "Creating…" : "Create key"}
        </Button>
      </div>

      {keys === null ? (
        <SkeletonRows rows={2} />
      ) : live.length === 0 ? (
        <p className="text-xs text-faint">No API keys yet.</p>
      ) : (
        <ul className="space-y-2">
          {live.map((k) => (
            <li
              key={k.id}
              className="flex items-center justify-between rounded-lg border border-edge px-3 py-2.5">
              <div>
                <p className="flex items-center gap-2 text-xs">
                  {k.name}
                  <Badge color="#64748b">{k.prefix}…</Badge>
                </p>
                <p className="mt-0.5 text-[10px] text-faint">
                  created {formatDateTime(k.created_at)} ·{" "}
                  {k.last_used_at ? `last used ${timeAgo(k.last_used_at)}` : "never used"}
                </p>
              </div>
              <Button size="sm" variant="danger" onClick={() => revoke(k.id)}>
                <Trash2 size={12} /> Revoke
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
