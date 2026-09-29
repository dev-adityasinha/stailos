"use client";

import { Eye, EyeOff, X } from "lucide-react";
import { useEffect, useState } from "react";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/* ----------------------------------------------------------------- Button */

const buttonVariants = {
  primary:
    "bg-primary hover:bg-primary-hover text-white shadow-sm disabled:opacity-50",
  secondary:
    "bg-raised hover:bg-edge text-ink border border-edge-strong disabled:opacity-50",
  ghost: "hover:bg-raised text-muted hover:text-ink disabled:opacity-50",
  danger: "bg-danger/15 hover:bg-danger/25 text-danger border border-danger/30",
  ai: "bg-ai/15 hover:bg-ai/25 text-[#b79bfa] border border-ai/40",
} as const;

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof buttonVariants;
  size?: "sm" | "md";
}) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium",
        "transition-colors duration-150 cursor-pointer disabled:cursor-not-allowed",
        size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3.5 py-2 text-sm",
        buttonVariants[variant],
        className
      )}
      {...props}
    />
  );
}

/* ------------------------------------------------------------------ Input */

export function Input({
  label,
  error,
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label?: string; error?: string }) {
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-xs font-medium text-muted">{label}</span>}
      <input
        className={cx(
          "w-full rounded-lg border bg-surface px-3 py-2 text-sm text-ink",
          "placeholder:text-faint outline-none transition-colors",
          "focus:border-primary focus:ring-2 focus:ring-primary/25",
          error ? "border-danger" : "border-edge-strong",
          className
        )}
        {...props}
      />
      {error && <span className="mt-1 block text-xs text-danger">{error}</span>}
    </label>
  );
}

export function PasswordInput({
  label,
  error,
  className,
  ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label?: string;
  error?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-xs font-medium text-muted">{label}</span>}
      <div className="relative">
        <input
          type={visible ? "text" : "password"}
          className={cx(
            "w-full rounded-lg border bg-surface px-3 py-2 pr-9 text-sm text-ink",
            "placeholder:text-faint outline-none transition-colors",
            "focus:border-primary focus:ring-2 focus:ring-primary/25",
            error ? "border-danger" : "border-edge-strong",
            className
          )}
          {...props}
        />
        <button
          type="button"
          tabIndex={-1}
          onClick={() => setVisible((v) => !v)}
          className="absolute inset-y-0 right-0 flex items-center px-2.5 text-faint hover:text-muted"
          aria-label={visible ? "Hide password" : "Show password"}
        >
          {visible ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
      </div>
      {error && <span className="mt-1 block text-xs text-danger">{error}</span>}
    </label>
  );
}

export function Textarea({
  label,
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }) {
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-xs font-medium text-muted">{label}</span>}
      <textarea
        className={cx(
          "w-full rounded-lg border border-edge-strong bg-surface px-3 py-2 text-sm",
          "text-ink placeholder:text-faint outline-none transition-colors",
          "focus:border-primary focus:ring-2 focus:ring-primary/25",
          className
        )}
        rows={3}
        {...props}
      />
    </label>
  );
}

export function Select({
  label,
  children,
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-xs font-medium text-muted">{label}</span>}
      <select
        className={cx(
          "w-full rounded-lg border border-edge-strong bg-surface px-3 py-2 text-sm",
          "text-ink outline-none focus:border-primary focus:ring-2 focus:ring-primary/25",
          className
        )}
        {...props}
      >
        {children}
      </select>
    </label>
  );
}

/* ------------------------------------------------------------- Card/Badge */

export function Card({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx("rounded-xl border border-edge bg-surface", className)}
      {...props}
    />
  );
}

export function Badge({
  color = "var(--muted)",
  children,
  className,
}: {
  color?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
        className
      )}
      style={{ backgroundColor: `${color}22`, color }}
    >
      {children}
    </span>
  );
}

export function Avatar({ name, color, size = 32 }: { name: string; color?: string | null; size?: number }) {
  const init = name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.38,
        backgroundColor: color ?? "#3b82f6",
      }}
    >
      {init}
    </span>
  );
}

/* ------------------------------------------------------------------ Modal */

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 pt-[8vh]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className={cx(
          "fade-up w-full rounded-xl border border-edge-strong bg-surface shadow-2xl",
          wide ? "max-w-3xl" : "max-w-lg"
        )}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="flex items-center justify-between border-b border-edge px-5 py-3.5">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-muted hover:bg-raised hover:text-ink"
          >
            <X size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ States/misc */

export function Spinner({ size = 20 }: { size?: number }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-edge-strong border-t-primary"
      style={{ width: size, height: size }}
      role="status"
      aria-label="Loading"
    />
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 py-14 text-center">
      <p className="text-sm font-medium text-muted">{title}</p>
      {hint && <p className="max-w-sm text-xs text-faint">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function SkeletonRows({ rows = 5, height = 44 }: { rows?: number; height?: number }) {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton w-full" style={{ height }} />
      ))}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
      {message}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-lg font-semibold">{title}</h1>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/* AI accent block per PRD: purple = AI-generated content */
export function AIPanel({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("rounded-xl border border-ai/30 bg-ai/[0.06] p-4", className)}>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-[#b79bfa]">
        <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-ai" />
        {title}
      </p>
      {children}
    </div>
  );
}
