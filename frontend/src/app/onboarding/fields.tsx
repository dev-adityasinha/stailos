"use client";

/* Form primitives used only by the onboarding wizard. Anything reusable beyond
   this flow belongs in components/ui.tsx instead. */

import { Check, Trash2, Upload } from "lucide-react";
import { Spinner, cx } from "@/components/ui";

/** Multi-select chip group. */
export function Chips({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const toggle = (option: string) =>
    onChange(
      value.includes(option) ? value.filter((v) => v !== option) : [...value, option]
    );
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={value.includes(option)}
          onClick={() => toggle(option)}
          className={cx(
            "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
            value.includes(option)
              ? "border-primary bg-primary/15 text-primary"
              : "border-edge-strong text-muted hover:border-primary/50 hover:text-ink"
          )}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

/** Labelled wrapper for a control that isn't a plain input. */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <span className="mb-1.5 block text-xs font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-[11px] text-faint">{hint}</span>}
    </div>
  );
}

/** Yes/no pair. Explicitly three-state (null = unanswered) so a required
 *  consent can't be satisfied by simply never touching the control. */
export function YesNo({
  value,
  onChange,
}: {
  value: boolean | null;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex gap-2">
      {[
        { label: "Yes", answer: true },
        { label: "No", answer: false },
      ].map(({ label, answer }) => (
        <button
          key={label}
          type="button"
          aria-pressed={value === answer}
          onClick={() => onChange(answer)}
          className={cx(
            "rounded-lg border px-4 py-1.5 text-xs font-medium transition-colors",
            value === answer
              ? answer
                ? "border-success bg-success/15 text-success"
                : "border-edge-strong bg-raised text-ink"
              : "border-edge-strong text-muted hover:border-primary/50 hover:text-ink"
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** 0–100 relative-importance slider used by the lead-scoring step. */
export function WeightSlider({
  label,
  hint,
  value,
  share,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  /** Normalised share of the total, so the effect of the number is visible. */
  share: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium text-ink">{label}</span>
        <span className="text-[11px] tabular-nums text-muted">
          {(share * 100).toFixed(0)}% of the score
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        step={5}
        value={value}
        aria-label={label}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1.5 w-full accent-[var(--primary)]"
      />
      <span className="mt-0.5 block text-[11px] text-faint">{hint}</span>
    </div>
  );
}

export interface UploadedAsset {
  document_id: string;
  title: string;
  category: string;
  filename: string | null;
  size: number;
  download_path: string;
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

/** A single upload slot: pick a file, it uploads immediately, and every file
 *  already stored under this category is listed with a working download link. */
export function FileSlot({
  label,
  accept,
  category,
  assets,
  busy,
  onPick,
  onRemove,
}: {
  label: string;
  accept: string;
  category: string;
  assets: UploadedAsset[];
  busy: boolean;
  onPick: (file: File) => void;
  onRemove: (documentId: string) => void;
}) {
  const mine = assets.filter((a) => a.category === category);
  return (
    <div className="rounded-lg border border-edge bg-raised/40 p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-ink">{label}</span>
        <label className="shrink-0 cursor-pointer">
          <input
            type="file"
            accept={accept}
            aria-label={`Upload ${label}`}
            className="hidden"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onPick(file);
              // Reset so re-picking the same filename fires onChange again.
              e.target.value = "";
            }}
          />
          <span
            className={cx(
              "flex items-center gap-1.5 rounded-lg border border-dashed px-2.5 py-1.5",
              "text-[11px] transition-colors",
              busy
                ? "border-edge text-faint"
                : "border-edge-strong text-muted hover:border-primary hover:text-ink"
            )}
          >
            {busy ? <Spinner size={12} /> : <Upload size={12} />}
            {busy ? "Uploading…" : "Choose file"}
          </span>
        </label>
      </div>
      {mine.length > 0 && (
        <ul className="mt-2 space-y-1">
          {mine.map((asset) => (
            <li
              key={asset.document_id}
              className="flex items-center justify-between gap-2 text-[11px]"
            >
              <span className="flex min-w-0 items-center gap-1.5 text-muted">
                <Check size={11} className="shrink-0 text-success" />
                <span className="truncate">{asset.filename ?? asset.title}</span>
                <span className="shrink-0 text-faint">{formatSize(asset.size)}</span>
              </span>
              <button
                type="button"
                onClick={() => onRemove(asset.document_id)}
                aria-label={`Remove ${asset.filename ?? asset.title}`}
                className="shrink-0 text-faint transition-colors hover:text-danger"
              >
                <Trash2 size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <span className="mt-1.5 block text-[11px] text-faint">
        Accepts {accept.replaceAll(".", "").replaceAll(",", ", ")}
      </span>
    </div>
  );
}
