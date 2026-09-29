"use client";

import { useState } from "react";
import { FileDown, FileSpreadsheet, FileText } from "lucide-react";
import { downloadFile } from "@/lib/api";
import { Button, Card, PageHeader, Spinner } from "@/components/ui";

const REPORTS = [
  { type: "lead", title: "Lead Report", desc: "All leads with stage, score, owner and source." },
  { type: "sales", title: "Sales Report", desc: "Bookings with value, collections and outstanding." },
  { type: "agent", title: "Agent Report", desc: "Per-agent leads, conversions, bookings and revenue." },
  { type: "booking", title: "Booking Report", desc: "Booking pipeline with token and total value." },
  { type: "property", title: "Property Report", desc: "Full inventory with pricing and unit status." },
  { type: "revenue", title: "Revenue Report", desc: "Every payment receipt with method and milestone." },
  { type: "campaign", title: "Campaign Report", desc: "ROI and conversion rate by lead source and campaign." },
];

const FORMATS = [
  { format: "csv", label: "CSV", icon: FileText },
  { format: "xlsx", label: "Excel", icon: FileSpreadsheet },
  { format: "pdf", label: "PDF", icon: FileDown },
] as const;

export default function ReportsPage() {
  const [busy, setBusy] = useState("");

  async function generate(type: string, format: string) {
    const key = `${type}:${format}`;
    setBusy(key);
    try {
      await downloadFile(
        "/reports/generate",
        { method: "POST", body: { type, format } },
        `${type}_report.${format}`
      );
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="fade-up">
      <PageHeader
        title="Reports"
        subtitle="Generate and export operational reports — data respects your role scope"
      />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {REPORTS.map((r) => (
          <Card key={r.type} className="flex flex-col p-4">
            <p className="text-sm font-semibold">{r.title}</p>
            <p className="mt-1 flex-1 text-xs text-muted">{r.desc}</p>
            <div className="mt-4 flex gap-2">
              {FORMATS.map(({ format, label, icon: Icon }) => (
                <Button
                  key={format}
                  size="sm"
                  variant="secondary"
                  disabled={!!busy}
                  onClick={() => generate(r.type, format)}
                >
                  {busy === `${r.type}:${format}` ? <Spinner size={12} /> : <Icon size={12} />}
                  {label}
                </Button>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
