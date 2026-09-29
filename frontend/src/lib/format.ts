/** Indian-market formatting helpers. */

export function formatINR(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(1)} L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString("en-IN", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  const seconds = (Date.now() - d.getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)}d ago`;
  return formatDate(iso);
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

export const STAGE_LABELS: Record<string, string> = {
  new: "New Lead",
  contacted: "Contacted",
  qualified: "Qualified",
  interested: "Interested",
  site_visit_scheduled: "Site Visit Scheduled",
  negotiation: "Negotiation",
  booked: "Booked",
  completed: "Completed",
  lost: "Lost",
};

export const STAGE_ORDER = Object.keys(STAGE_LABELS);

export const STAGE_COLORS: Record<string, string> = {
  new: "#8b98ac",
  contacted: "#3b82f6",
  qualified: "#06b6d4",
  interested: "#8b5cf6",
  site_visit_scheduled: "#f59e0b",
  negotiation: "#f97316",
  booked: "#10b981",
  completed: "#059669",
  lost: "#ef4444",
};

export const BOOKING_STAGES = [
  "site_visit", "booking", "documentation", "payment", "possession", "completed",
];

export const BOOKING_STAGE_LABELS: Record<string, string> = {
  site_visit: "Site Visit",
  booking: "Booking",
  documentation: "Documentation",
  payment: "Payment",
  possession: "Possession",
  completed: "Completed",
};
