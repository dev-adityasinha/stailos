"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import { Card, EmptyState, PageHeader, SkeletonRows } from "@/components/ui";
import { Avatar } from "@/components/ui";
import { formatINR, timeAgo } from "@/lib/format";

interface Customer {
  id: string;
  full_name: string;
  phone: string;
  email: string | null;
  city: string | null;
  occupation: string | null;
  budget_min: string | null;
  budget_max: string | null;
  assignee: { full_name: string; avatar_color: string | null } | null;
  updated_at: string;
}

export default function CustomersPage() {
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    const res = await api<{ data: Customer[]; meta: { total: number } }>("/customers", {
      params: { q, limit: 50 },
    });
    setCustomers(res.data);
    setTotal(res.meta.total);
  }, [q]);

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  return (
    <div className="fade-up">
      <PageHeader
        title="Customers"
        subtitle={`${total} customer profile${total === 1 ? "" : "s"} — created by converting qualified leads`}
      />
      <div className="relative mb-4 w-64">
        <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search customers…"
          className="w-full rounded-lg border border-edge-strong bg-surface py-2 pl-8 pr-3 text-sm outline-none focus:border-primary"
        />
      </div>
      <Card>
        {customers === null ? (
          <SkeletonRows />
        ) : customers.length === 0 ? (
          <EmptyState
            title="No customers yet"
            hint="Convert a lead to create the first customer profile — open a lead and press “Convert to customer”."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge text-[11px] uppercase tracking-wide text-faint">
                  <th className="px-4 py-2.5 font-medium">Customer</th>
                  <th className="px-4 py-2.5 font-medium">City</th>
                  <th className="px-4 py-2.5 font-medium">Occupation</th>
                  <th className="px-4 py-2.5 font-medium">Budget</th>
                  <th className="px-4 py-2.5 font-medium">Owner</th>
                  <th className="px-4 py-2.5 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {customers.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => router.push(`/customers/${c.id}`)}
                    className="cursor-pointer border-b border-edge/60 last:border-0 hover:bg-raised/60"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <Avatar name={c.full_name} size={28} />
                        <div>
                          <p className="font-medium">{c.full_name}</p>
                          <p className="text-[11px] text-faint">{c.phone}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted">{c.city ?? "—"}</td>
                    <td className="px-4 py-3 text-muted">{c.occupation ?? "—"}</td>
                    <td className="px-4 py-3 text-muted">
                      {formatINR(c.budget_min)} – {formatINR(c.budget_max)}
                    </td>
                    <td className="px-4 py-3 text-muted">{c.assignee?.full_name ?? "—"}</td>
                    <td className="px-4 py-3 text-faint">{timeAgo(c.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
