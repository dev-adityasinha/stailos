"use client";

import { useRouter } from "next/navigation";
import { useSWRConfig } from "swr";
import { useEffect, useState } from "react";
import { Building2, Check } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { ADMIN_ROLES, useAuth } from "@/lib/auth";
import { Badge, Button, Card, Input, PageHeader, SkeletonRows } from "@/components/ui";

/* Displays and edits the tenant's onboarding data — every step stored on the
   backend, whether it was filled in the in-app wizard or via StailOS. The three
   sections below are editable in place ("1" company, "2" projects, "4" target
   customer); every other step is rendered read-only so nothing the user filled
   ever disappears. Section titles come from the wizard's own step registry, so
   adding a page there labels it correctly here without a second edit. */

import { AI_FEATURE_GROUPS, STEPS } from "@/app/onboarding/steps";
import { Chips, YesNo } from "@/app/onboarding/fields";

type StepData = Record<string, unknown>;
interface Project {
  name?: string; location?: string; city?: string; possession?: string;
  priceRange?: string; amenities?: string[];
}

const COMPANY_FIELDS: [key: string, label: string][] = [
  ["companyName", "Company name"], ["legalName", "Legal entity name"],
  ["brandName", "Brand name"], ["cin", "CIN"], ["gst", "GST number"],
  ["pan", "PAN"], ["rera", "RERA number"], ["yearEstablished", "Year established"],
  ["website", "Website"], ["linkedin", "LinkedIn page"],
  ["headOffice", "Head office city"], ["state", "State"], ["country", "Country"],
];

const STEP_LABELS: Record<string, string> = Object.fromEntries(
  STEPS.map((step) => [step.key, step.title])
);

function SectionSaved({ show }: { show: boolean }) {
  return show ? (
    <span className="flex items-center gap-1 text-xs text-success">
      <Check size={12} /> Saved
    </span>
  ) : null;
}

export default function CompanyProfilePage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const { mutate } = useSWRConfig();
  const [data, setData] = useState<Record<string, StepData> | null>(null);
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState("");
  const [savedSection, setSavedSection] = useState("");

  const [company, setCompany] = useState<Record<string, string>>({});
  const [projects, setProjects] = useState<Project[]>([]);
  const [target, setTarget] = useState({ buyerSegments: "", budgetRange: "", preferredCities: "" });
  // AI features and consent are enforced by the backend, so they have to be
  // changeable somewhere — the refusal message points admins here.
  const [features, setFeatures] = useState<Record<string, string[]>>({});
  const [aiConsent, setAiConsent] = useState<boolean | null>(null);
  const [marketingConsent, setMarketingConsent] = useState<boolean | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user || !ADMIN_ROLES.has(user.role)) {
      router.replace("/dashboard");
      return;
    }
    api<{ data: { onboarding_data: Record<string, StepData> | null; onboarding_completed: boolean } }>(
      "/onboarding/state"
    )
      .then((res) => {
        const d = res.data.onboarding_data ?? {};
        setData(d);
        setCompleted(res.data.onboarding_completed);
        const s1 = (d["1"] ?? {}) as Record<string, unknown>;
        setCompany(
          Object.fromEntries(COMPANY_FIELDS.map(([k]) => [k, s1[k] != null ? String(s1[k]) : ""]))
        );
        const s2 = (d["2"] ?? {}) as { projects?: Project[] };
        setProjects(s2.projects ?? []);
        const s4 = (d["4"] ?? {}) as {
          buyerSegments?: string[]; budgetRange?: string; preferredCities?: string[];
        };
        setTarget({
          buyerSegments: (s4.buyerSegments ?? []).join(", "),
          budgetRange: s4.budgetRange ?? "",
          preferredCities: (s4.preferredCities ?? []).join(", "),
        });
        const s6 = (d["6"] ?? {}) as Record<string, string[]>;
        setFeatures(
          Object.fromEntries(AI_FEATURE_GROUPS.map((g) => [g.key, s6[g.key] ?? []]))
        );
        const s12 = (d["12"] ?? {}) as Record<string, boolean>;
        setAiConsent(s12.aiUsageConsent ?? null);
        setMarketingConsent(s12.marketingConsent ?? null);
      })
      .catch((err) => setError(errorMessage(err, "Failed to load company profile.")));
  }, [loading, user, router]);

  async function save(section: string, key: string, payload: StepData) {
    setError("");
    try {
      await api("/onboarding/step", { method: "PATCH", body: { step_id: key, data: payload } });
      // Steps 6 and 12 decide which AI actions the rest of the app may offer.
      // Without dropping the cached policy, other pages keep rendering buttons
      // the server has just started refusing until SWR next revalidates.
      if (key === "6" || key === "12") await mutate("/ai/catalog");
      setSavedSection(section);
      setTimeout(() => setSavedSection(""), 2500);
    } catch (err) {
      setError(errorMessage(err, "Failed to save."));
    }
  }

  if (loading || !user || data === null) {
    return error
      ? <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>
      : <SkeletonRows rows={4} height={90} />;
  }

  const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
  // Steps with a dedicated editable section above are excluded so they aren't
  // also dumped into the read-only "other setup data" block.
  const EDITED_STEPS = ["1", "2", "4", "6", "12"];
  const extraSteps = Object.entries(data).filter(
    ([k, v]) => !EDITED_STEPS.includes(k) && v && Object.keys(v).length > 0
  );

  return (
    <div className="fade-up mx-auto max-w-3xl">
      <PageHeader
        title="Company profile"
        subtitle="Everything captured during workspace setup — editable any time"
        actions={
          <Badge color={completed ? "#10b981" : "#f59e0b"}>
            {completed ? "Setup complete" : "Setup incomplete"}
          </Badge>
        }
      />
      {error && <p className="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>}

      <div className="space-y-4">
        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-xs font-semibold">
              <Building2 size={13} /> Company
            </p>
            <SectionSaved show={savedSection === "company"} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {COMPANY_FIELDS.map(([key, label]) => (
              <Input key={key} label={label} value={company[key] ?? ""}
                     onChange={(e) => setCompany((c) => ({ ...c, [key]: e.target.value }))} />
            ))}
          </div>
          <Button size="sm" className="mt-4"
                  onClick={() => save("company", "1", { ...(data["1"] ?? {}), ...company })}>
            Save company
          </Button>
        </Card>

        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-xs font-semibold">Projects</p>
            <SectionSaved show={savedSection === "projects"} />
          </div>
          {projects.length === 0 && (
            <p className="mb-3 text-xs text-faint">No projects recorded during setup.</p>
          )}
          <div className="space-y-3">
            {projects.map((p, idx) => (
              <div key={idx} className="grid gap-3 rounded-lg border border-edge p-3 sm:grid-cols-2">
                <Input label="Name" value={p.name ?? ""}
                       onChange={(e) => setProjects((ps) => ps.map((x, i) => i === idx ? { ...x, name: e.target.value } : x))} />
                <Input label="Locality" value={p.location ?? ""}
                       onChange={(e) => setProjects((ps) => ps.map((x, i) => i === idx ? { ...x, location: e.target.value } : x))} />
                <Input label="City" value={p.city ?? ""}
                       onChange={(e) => setProjects((ps) => ps.map((x, i) => i === idx ? { ...x, city: e.target.value } : x))} />
                <Input label="Possession" value={p.possession ?? ""}
                       onChange={(e) => setProjects((ps) => ps.map((x, i) => i === idx ? { ...x, possession: e.target.value } : x))} />
                <Input label="Price range" value={p.priceRange ?? ""}
                       onChange={(e) => setProjects((ps) => ps.map((x, i) => i === idx ? { ...x, priceRange: e.target.value } : x))} />
              </div>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <Button size="sm" variant="secondary"
                    onClick={() => setProjects((ps) => [...ps, {}])}>
              + Add project
            </Button>
            <Button size="sm"
                    onClick={() => save("projects", "2", { ...(data["2"] ?? {}), projects: projects.filter((p) => (p.name ?? "").trim()) })}>
              Save projects
            </Button>
          </div>
          <p className="mt-3 text-[11px] text-faint">
            Note: live inventory records created at launch are managed under Properties —
            this section is your setup record.
          </p>
        </Card>

        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-xs font-semibold">Target customer</p>
            <SectionSaved show={savedSection === "target"} />
          </div>
          <div className="space-y-4">
            <Input label="Buyer segments (comma-separated)" value={target.buyerSegments}
                   onChange={(e) => setTarget((t) => ({ ...t, buyerSegments: e.target.value }))} />
            <Input label="Budget range" value={target.budgetRange}
                   onChange={(e) => setTarget((t) => ({ ...t, budgetRange: e.target.value }))} />
            <Input label="Preferred cities (comma-separated)" value={target.preferredCities}
                   onChange={(e) => setTarget((t) => ({ ...t, preferredCities: e.target.value }))} />
          </div>
          <Button size="sm" className="mt-4"
                  onClick={() => save("target", "4", {
                    ...(data["4"] ?? {}),
                    buyerSegments: csv(target.buyerSegments),
                    budgetRange: target.budgetRange,
                    preferredCities: csv(target.preferredCities),
                  })}>
            Save target customer
          </Button>
        </Card>

        <Card className="p-5">
          <div className="mb-1 flex items-center justify-between">
            <p className="text-xs font-semibold">AI features</p>
            <SectionSaved show={savedSection === "features"} />
          </div>
          <p className="mb-4 text-[11px] text-faint">
            Unticking a feature switches it off for everyone in this workspace —
            the matching AI action stops appearing and the API refuses it. Leave
            every group empty to keep all features available.
          </p>
          <div className="space-y-4">
            {AI_FEATURE_GROUPS.map((group) => (
              <div key={group.key}>
                <span className="mb-1.5 block text-xs font-medium text-muted">
                  {group.label}
                </span>
                <Chips
                  options={group.options}
                  value={features[group.key] ?? []}
                  onChange={(v) => setFeatures((f) => ({ ...f, [group.key]: v }))}
                />
              </div>
            ))}
          </div>
          <Button size="sm" className="mt-4"
                  onClick={() => save("features", "6", { ...(data["6"] ?? {}), ...features })}>
            Save AI features
          </Button>
        </Card>

        <Card className="p-5">
          <div className="mb-1 flex items-center justify-between">
            <p className="text-xs font-semibold">Compliance &amp; consent</p>
            <SectionSaved show={savedSection === "consent"} />
          </div>
          <p className="mb-4 text-[11px] text-faint">
            Declining AI usage consent stops every AI agent in this workspace
            immediately.
          </p>
          <div className="space-y-4">
            <div>
              <span className="mb-1.5 block text-xs font-medium text-muted">
                Marketing consent
              </span>
              <YesNo value={marketingConsent} onChange={setMarketingConsent} />
            </div>
            <div>
              <span className="mb-1.5 block text-xs font-medium text-muted">
                AI usage consent
              </span>
              <YesNo value={aiConsent} onChange={setAiConsent} />
              {aiConsent === false && (
                <p className="mt-2 rounded-lg bg-warning/10 px-3 py-2 text-[11px] text-warning">
                  AI features are currently switched off for this workspace.
                </p>
              )}
            </div>
          </div>
          <Button size="sm" className="mt-4"
                  onClick={() => save("consent", "12", {
                    ...(data["12"] ?? {}),
                    marketingConsent: marketingConsent === true,
                    aiUsageConsent: aiConsent === true,
                  })}>
            Save consent
          </Button>
        </Card>

        {extraSteps.length > 0 && (
          <Card className="p-5">
            <p className="mb-4 text-xs font-semibold">Other setup data</p>
            <div className="space-y-4">
              {extraSteps.map(([stepKey, stepData]) => (
                <div key={stepKey}>
                  <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-faint">
                    {STEP_LABELS[stepKey] ?? `Step ${stepKey}`}
                  </p>
                  <div className="space-y-1 rounded-lg border border-edge p-3">
                    {Object.entries(stepData).map(([k, v]) => (
                      <div key={k} className="flex items-start justify-between gap-4 text-xs">
                        <span className="shrink-0 text-muted">{k}</span>
                        <span className="text-right font-medium break-all">
                          {Array.isArray(v)
                            ? (v.length && typeof v[0] === "object" ? `${v.length} entries` : v.join(", ")) || "—"
                            : typeof v === "object" && v !== null
                              ? JSON.stringify(v)
                              : String(v ?? "—")}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
