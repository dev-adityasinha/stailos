"use client";

import { useCallback, useEffect, useState } from "react";
import { Building2, Heart, Link2, Scale, Star, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import {
  Badge, Button, Card, EmptyState, Input, Modal, PageHeader, Select,
  SkeletonRows, cx,
} from "@/components/ui";
import { formatINR } from "@/lib/format";

interface Unit {
  id: string;
  unit_number: string;
  floor: number | null;
  unit_type: string;
  carpet_area_sqft: string | null;
  price: string;
  status: string;
  facing: string | null;
  project: {
    id: string; name: string; builder_name: string; location: string; city: string;
    amenities: string[] | null; status: string; rera_id: string | null;
  };
}

interface CustomerBrief { id: string; full_name: string; phone: string }

const STATUS_COLORS: Record<string, string> = {
  available: "#10b981", held: "#f59e0b", booked: "#3b82f6", sold: "#8b98ac",
};

export default function PropertiesPage() {
  const [units, setUnits] = useState<Unit[] | null>(null);
  const [q, setQ] = useState("");
  const [unitType, setUnitType] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [compare, setCompare] = useState<Unit[]>([]);
  const [showCompare, setShowCompare] = useState(false);
  const [linkTarget, setLinkTarget] = useState<{ unit: Unit; relation: string } | null>(null);
  const [customers, setCustomers] = useState<CustomerBrief[]>([]);
  const [feedback, setFeedback] = useState("");

  const load = useCallback(async () => {
    const res = await api<{ data: Unit[] }>("/properties", {
      params: { q, unit_type: unitType, max_price: maxPrice },
    });
    setUnits(res.data);
  }, [q, unitType, maxPrice]);

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  async function openLink(unit: Unit, relation: string) {
    const res = await api<{ data: CustomerBrief[] }>("/customers", { params: { limit: 50 } });
    setCustomers(res.data);
    setLinkTarget({ unit, relation });
  }

  async function linkCustomer(customerId: string) {
    if (!linkTarget) return;
    const action = { shortlisted: "shortlist", favourite: "favourite", attached: "attach" }[
      linkTarget.relation
    ];
    try {
      await api(`/properties/${linkTarget.unit.id}/${action}`, {
        method: "POST",
        body: { customer_id: customerId },
      });
      setFeedback(`Unit ${linkTarget.unit.unit_number} ${linkTarget.relation} for customer.`);
    } catch (err) {
      setFeedback(err instanceof ApiError ? err.message : "Failed to link.");
    }
    setLinkTarget(null);
    setTimeout(() => setFeedback(""), 4000);
  }

  function toggleCompare(unit: Unit) {
    setCompare((c) =>
      c.some((u) => u.id === unit.id)
        ? c.filter((u) => u.id !== unit.id)
        : c.length >= 4 ? c : [...c, unit]
    );
  }

  const unitTypes = [...new Set((units ?? []).map((u) => u.unit_type))];

  return (
    <div className="fade-up">
      <PageHeader
        title="Properties"
        subtitle="Browse inventory, shortlist for customers, compare units"
        actions={
          compare.length >= 2 ? (
            <Button onClick={() => setShowCompare(true)}>
              <Scale size={14} /> Compare ({compare.length})
            </Button>
          ) : undefined
        }
      />
      {feedback && (
        <p className="mb-3 rounded-lg border border-edge bg-raised px-3 py-2 text-xs text-muted">
          {feedback}
        </p>
      )}
      <div className="mb-4 flex flex-wrap gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search project, builder, location…"
          className="w-64 rounded-lg border border-edge-strong bg-surface px-3 py-2 text-sm outline-none focus:border-primary"
        />
        <Select value={unitType} onChange={(e) => setUnitType(e.target.value)} className="w-32">
          <option value="">All types</option>
          {unitTypes.map((t) => <option key={t} value={t}>{t}</option>)}
        </Select>
        <Input type="number" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)}
               placeholder="Max price ₹" className="w-36" />
      </div>

      {units === null ? (
        <SkeletonRows rows={4} height={90} />
      ) : units.length === 0 ? (
        <EmptyState title="No inventory matches" hint="Adjust the filters, or ask an admin to add projects." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {units.map((unit) => {
            const inCompare = compare.some((u) => u.id === unit.id);
            return (
              <Card key={unit.id} className={cx("p-4 transition-colors", inCompare && "border-primary")}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">{unit.project.name}</p>
                    <p className="mt-0.5 flex items-center gap-1 text-[11px] text-muted">
                      <Building2 size={11} /> {unit.project.location}
                    </p>
                  </div>
                  <Badge color={STATUS_COLORS[unit.status]}>{unit.status}</Badge>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  {[
                    ["Unit", `#${unit.unit_number}`],
                    ["Type", unit.unit_type],
                    ["Area", unit.carpet_area_sqft ? `${Number(unit.carpet_area_sqft).toFixed(0)} sqft` : "—"],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg bg-raised px-1 py-1.5">
                      <p className="text-[9px] uppercase text-faint">{label}</p>
                      <p className="text-[11px] font-medium">{value}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-base font-semibold text-success">{formatINR(unit.price)}</p>
                <p className="text-[10px] text-faint">
                  {unit.project.builder_name}
                  {unit.project.rera_id ? ` · RERA ${unit.project.rera_id}` : ""}
                </p>
                <div className="mt-3 flex gap-1.5">
                  <Button size="sm" variant="secondary" title="Shortlist for a customer"
                          onClick={() => openLink(unit, "shortlisted")}>
                    <Star size={12} /> Shortlist
                  </Button>
                  <Button size="sm" variant="secondary" title="Mark favourite"
                          onClick={() => openLink(unit, "favourite")}>
                    <Heart size={12} />
                  </Button>
                  <Button size="sm" variant="secondary" title="Attach to customer"
                          onClick={() => openLink(unit, "attached")}>
                    <Link2 size={12} />
                  </Button>
                  <Button size="sm" variant={inCompare ? "primary" : "ghost"}
                          title="Add to comparison" onClick={() => toggleCompare(unit)}>
                    <Scale size={12} />
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Customer picker for shortlist/favourite/attach */}
      <Modal
        open={!!linkTarget}
        onClose={() => setLinkTarget(null)}
        title={linkTarget ? `${linkTarget.relation === "shortlisted" ? "Shortlist" : linkTarget.relation === "favourite" ? "Favourite" : "Attach"} unit #${linkTarget.unit.unit_number} for…` : ""}
      >
        {customers.length === 0 ? (
          <p className="text-xs text-faint">No customers in your scope — convert a lead first.</p>
        ) : (
          <div className="max-h-80 space-y-2 overflow-y-auto">
            {customers.map((c) => (
              <button
                key={c.id}
                onClick={() => linkCustomer(c.id)}
                className="flex w-full items-center justify-between rounded-lg border border-edge px-3 py-2 text-left text-xs hover:border-primary hover:bg-raised"
              >
                <span>{c.full_name}</span>
                <span className="text-faint">{c.phone}</span>
              </button>
            ))}
          </div>
        )}
      </Modal>

      {/* Comparison modal */}
      <Modal open={showCompare} onClose={() => setShowCompare(false)} title="Compare units" wide>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-edge text-[10px] uppercase text-faint">
                <th className="py-2 pr-3">Attribute</th>
                {compare.map((u) => (
                  <th key={u.id} className="py-2 pr-3">
                    <span className="flex items-center gap-1">
                      {u.project.name} #{u.unit_number}
                      <button onClick={() => toggleCompare(u)} className="text-faint hover:text-danger">
                        <X size={11} />
                      </button>
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {([
                ["Price", (u: Unit) => formatINR(u.price)],
                ["Type", (u: Unit) => u.unit_type],
                ["Carpet area", (u: Unit) => u.carpet_area_sqft ? `${Number(u.carpet_area_sqft).toFixed(0)} sqft` : "—"],
                ["Floor", (u: Unit) => u.floor?.toString() ?? "—"],
                ["Facing", (u: Unit) => u.facing ?? "—"],
                ["Location", (u: Unit) => u.project.location],
                ["Builder", (u: Unit) => u.project.builder_name],
                ["Status", (u: Unit) => u.status],
                ["Amenities", (u: Unit) => u.project.amenities?.join(", ") ?? "—"],
              ] as [string, (u: Unit) => string][]).map(([label, get]) => (
                <tr key={label} className="border-b border-edge/60 last:border-0">
                  <td className="py-2 pr-3 font-medium text-muted">{label}</td>
                  {compare.map((u) => (
                    <td key={u.id} className="py-2 pr-3">{get(u)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Modal>
    </div>
  );
}
