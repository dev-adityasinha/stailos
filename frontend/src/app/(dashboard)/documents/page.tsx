"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Download, FileUp, History, Plus } from "lucide-react";
import { api, ApiError, downloadFile } from "@/lib/api";
import {
  Badge, Button, Card, EmptyState, ErrorNote, Input, Modal, PageHeader,
  Select, SkeletonRows,
} from "@/components/ui";
import { formatDateTime, timeAgo } from "@/lib/format";
import {
  DOCUMENT_CATEGORIES as CATEGORIES,
  DOCUMENT_CATEGORY_COLORS as CATEGORY_COLORS,
  DOCUMENT_UPLOAD_ACCEPT,
} from "@/lib/documents";

interface Version {
  id: string; version_number: number; filename: string; size: number;
  note: string | null; created_at: string;
}
interface Doc {
  id: string; title: string; category: string; entity_type: string | null;
  current_version: number; versions: Version[]; updated_at: string;
}

function formatBytes(n: number): string {
  if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

function DocumentsInner() {
  const searchParams = useSearchParams();
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [category, setCategory] = useState("");
  const [showUpload, setShowUpload] = useState(searchParams.get("new") === "1");
  const [historyDoc, setHistoryDoc] = useState<Doc | null>(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ title: "", category: "other" });
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (searchParams.get("new") === "1") setShowUpload(true);
  }, [searchParams]);

  const load = useCallback(async () => {
    const res = await api<{ data: Doc[] }>("/documents", { params: { category, limit: 100 } });
    setDocs(res.data);
  }, [category]);

  useEffect(() => { load(); }, [load]);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", form.title);
      fd.append("category", form.category);
      await api("/documents/upload", { method: "POST", formData: fd });
      setShowUpload(false);
      setForm({ title: "", category: "other" });
      setFile(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function addVersion(docId: string, f: File) {
    const fd = new FormData();
    fd.append("file", f);
    try {
      await api(`/documents/${docId}/version`, { method: "POST", formData: fd });
      setHistoryDoc(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Version upload failed.");
    }
  }

  return (
    <div className="fade-up">
      <PageHeader
        title="Documents"
        subtitle="KYC, agreements, receipts and brochures with version tracking"
        actions={<Button onClick={() => setShowUpload(true)}><Plus size={14} /> Upload</Button>}
      />
      {error && <div className="mb-3"><ErrorNote message={error} /></div>}
      <div className="mb-4">
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-44">
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
        </Select>
      </div>
      <Card>
        {docs === null ? (
          <SkeletonRows />
        ) : docs.length === 0 ? (
          <EmptyState title="No documents" hint="Upload agreements, KYC or receipts to keep them versioned in one place."
                      action={<Button size="sm" onClick={() => setShowUpload(true)}><Plus size={13} /> Upload</Button>} />
        ) : (
          <ul className="divide-y divide-edge/60">
            {docs.map((d) => (
              <li key={d.id} className="flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{d.title}</p>
                  <p className="mt-0.5 text-[10px] text-faint">
                    v{d.current_version} · {d.versions.at(-1)?.filename} · updated {timeAgo(d.updated_at)}
                  </p>
                </div>
                <Badge color={CATEGORY_COLORS[d.category]}>{d.category.replace(/_/g, " ")}</Badge>
                <Button size="sm" variant="ghost" title="Version history"
                        onClick={() => setHistoryDoc(d)}>
                  <History size={13} /> v{d.current_version}
                </Button>
                <Button size="sm" variant="secondary"
                        onClick={() => downloadFile(`/documents/${d.id}/download`, {}, d.title)}>
                  <Download size={13} />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Upload modal */}
      <Modal open={showUpload} onClose={() => setShowUpload(false)} title="Upload document">
        <form onSubmit={upload} className="space-y-4">
          <Input label="Title *" required minLength={2} value={form.title}
                 onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
          <Select label="Category" value={form.category}
                  onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
          </Select>
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-muted">File *</span>
            <input
              type="file"
              required
              accept={DOCUMENT_UPLOAD_ACCEPT}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-xs text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-raised file:px-3 file:py-2 file:text-xs file:text-ink"
            />
          </label>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setShowUpload(false)}>Cancel</Button>
            <Button type="submit" disabled={busy || !file}>
              {busy ? "Uploading…" : <><FileUp size={14} /> Upload</>}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Version history */}
      <Modal open={!!historyDoc} onClose={() => setHistoryDoc(null)}
             title={historyDoc ? `Versions — ${historyDoc.title}` : ""}>
        {historyDoc && (
          <div className="space-y-3">
            <ul className="space-y-2">
              {[...historyDoc.versions].reverse().map((v) => (
                <li key={v.id} className="flex items-center justify-between rounded-lg border border-edge px-3 py-2 text-xs">
                  <span>
                    <b>v{v.version_number}</b> · {v.filename} · {formatBytes(v.size)}
                    {v.note && <span className="ml-1 text-muted">— {v.note}</span>}
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="text-faint">{formatDateTime(v.created_at)}</span>
                    <Button size="sm" variant="ghost"
                            onClick={() => downloadFile(
                              `/documents/${historyDoc.id}/download`,
                              { params: { version: v.version_number } },
                              v.filename
                            )}>
                      <Download size={12} />
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted">Upload new version</span>
              <input
                type="file"
                accept={DOCUMENT_UPLOAD_ACCEPT}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f && historyDoc) addVersion(historyDoc.id, f);
                }}
                className="block w-full text-xs text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-raised file:px-3 file:py-2 file:text-xs file:text-ink"
              />
            </label>
          </div>
        )}
      </Modal>
    </div>
  );
}

export default function DocumentsPage() {
  return (
    <Suspense fallback={<SkeletonRows />}>
      <DocumentsInner />
    </Suspense>
  );
}
