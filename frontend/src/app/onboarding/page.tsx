"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, ArrowRight, Building2, Check, FileText, Rocket, Upload, Users,
} from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { ADMIN_ROLES, useAuth } from "@/lib/auth";
import { Button, Card, Input, Select, Spinner, Textarea, cx } from "@/components/ui";
import { Chips, Field, FileSlot, WeightSlider, YesNo, type UploadedAsset } from "./fields";
import {
  AI_FEATURE_GROUPS, AMENITIES, BUSINESS_TYPES, BUYER_SEGMENTS, BUYING_PURPOSES,
  CONFIGURATIONS, CONTACT_CHANNELS, DEFAULT_WEIGHTS, DESIGNATIONS, DOCUMENT_SLOTS,
  INDUSTRIES, INTEGRATIONS, INVITE_ROLES, KNOWLEDGE_BASE_HINT, LEAD_SOURCES,
  OBJECTIONS, OCCUPATIONS, PAIN_POINTS, PROJECT_STATUSES, PROPERTY_TYPES,
  PURCHASE_TIMELINES, PURCHASE_TRIGGERS, SCORING_DIMENSIONS, STEPS,
} from "./steps";

interface Project {
  name: string;
  location: string;
  city: string;
  status: string;
  priceRange: string;
  configurations: string[];
  amenities: string[];
  possession: string;
  rera: string;
  usp: string;
}

const BLANK_PROJECT: Project = {
  name: "", location: "", city: "", status: "under_construction", priceRange: "",
  configurations: [], amenities: [], possession: "", rera: "", usp: "",
};

type Row = Record<string, string>;

/** Minimal CSV reader for the import step. Quoted fields containing commas are
 *  handled because exported CRM data routinely has them in address columns. */
function parseCsv(text: string): Row[] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
  if (lines.length < 2) return [];
  const split = (line: string): string[] => {
    const out: string[] = [];
    let field = "";
    let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      if (quoted) {
        if (ch === '"' && line[i + 1] === '"') { field += '"'; i += 1; }
        else if (ch === '"') quoted = false;
        else field += ch;
      } else if (ch === '"') quoted = true;
      else if (ch === ",") { out.push(field); field = ""; }
      else field += ch;
    }
    out.push(field);
    return out.map((f) => f.trim());
  };
  const headers = split(lines[0]);
  return lines.slice(1).map((line) => {
    const values = split(line);
    const row: Row = {};
    headers.forEach((h, i) => { row[h] = values[i] ?? ""; });
    return row;
  });
}

function splitList(text: string): string[] {
  return text.split(",").map((s) => s.trim()).filter(Boolean);
}

function toNumber(text: string): number | undefined {
  const n = Number(text);
  return text.trim() !== "" && Number.isFinite(n) ? n : undefined;
}

export default function OnboardingPage() {
  const router = useRouter();
  const { user, loading, refreshUser } = useAuth();

  const [index, setIndex] = useState(0); // 0..STEPS.length (last = review)
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [inviteResults, setInviteResults] = useState<
    { sent: string[]; already_exists: string[]; failed: string[] } | null
  >(null);

  /* ── per-step state ─────────────────────────────────────────────────────── */
  const [company, setCompany] = useState({
    companyName: "", legalName: "", brandName: "", cin: "", gst: "", pan: "",
    rera: "", yearEstablished: "", website: "", linkedin: "", address: "",
    headOffice: "", state: "", country: "India",
  });
  const [contact, setContact] = useState({
    fullName: "", designation: "", mobile: "", whatsapp: "", email: "",
    preferredChannel: "WhatsApp",
  });
  const [profile, setProfile] = useState({
    employees: "", salesTeamSize: "", marketingTeamSize: "", activeProjects: "",
    completedProjects: "", yearsInRealEstate: "", cities: "",
    businessTypes: [] as string[], propertyTypes: [] as string[],
    leadSources: [] as string[],
  });
  const [projects, setProjects] = useState<Project[]>([{ ...BLANK_PROJECT }]);
  const [icp, setIcp] = useState({
    buyerSegments: [] as string[], occupations: [] as string[],
    industries: [] as string[], purchaseTimeline: "", purposes: [] as string[],
    triggers: [] as string[], painPoints: [] as string[],
    objections: [] as string[], budgetRange: "", preferredCities: "",
    incomeMin: "", incomeMax: "",
  });
  const [scoring, setScoring] = useState({
    weights: { ...DEFAULT_WEIGHTS },
    hot: 70,
    warm: 40,
  });
  const [features, setFeatures] = useState<Record<string, string[]>>({});
  const [integrations, setIntegrations] = useState<string[]>([]);
  const [imports, setImports] = useState({
    importLeads: [] as Row[], importCustomers: [] as Row[],
    leadsFileName: "", customersFileName: "", csvError: "",
  });
  const [assets, setAssets] = useState<UploadedAsset[]>([]);
  const [uploading, setUploading] = useState<string | null>(null);
  const [process, setProcess] = useState({
    responseTimeMinutes: "", averageSiteVisits: "", bookingAmount: "",
    monthlyLeadTarget: "", monthlySiteVisitTarget: "", monthlyBookingTarget: "",
    monthlyRevenueTarget: "", maxCpl: "", targetRoas: "",
  });
  const [team, setTeam] = useState({ invites: "", permissionLevel: "Sales" });
  const [consent, setConsent] = useState<{
    marketingConsent: boolean | null; aiUsageConsent: boolean | null;
  }>({ marketingConsent: null, aiUsageConsent: null });

  /* Steps already saved this session — drives the left-nav ticks. */
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const bailedRef = useRef(false);

  /* ── load ───────────────────────────────────────────────────────────────── */
  useEffect(() => {
    if (loading) return;
    if (!user) { router.replace("/login"); return; }
    if (!ADMIN_ROLES.has(user.role) || user.onboarding_completed === true) {
      router.replace("/dashboard");
      return;
    }

    Promise.all([
      api<{ data: { onboarding_data: Record<string, Record<string, unknown>> | null } }>(
        "/onboarding/state"
      ),
      // Uploads are stored the moment they're picked, so what's already there
      // must show on revisit — otherwise the admin re-uploads everything.
      api<{ data: UploadedAsset[] }>("/onboarding/documents").catch(() => ({ data: [] })),
    ])
      .then(([state, documents]) => {
        const d = state.data.onboarding_data ?? {};
        const pick = <T,>(key: string) => (d[key] ?? {}) as T;
        setSaved(new Set(Object.keys(d)));

        const s1 = pick<Record<string, string>>("1");
        setCompany((c) => ({
          ...c,
          ...Object.fromEntries(
            Object.entries(s1).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)])
          ),
          companyName: s1.companyName ?? user.tenant_name ?? "",
        }));

        const s1b = pick<Record<string, string>>("1b");
        setContact((c) => ({
          ...c,
          fullName: s1b.fullName ?? user.full_name ?? "",
          designation: s1b.designation ?? "",
          mobile: s1b.mobile ?? "",
          whatsapp: s1b.whatsapp ?? "",
          email: s1b.email ?? user.email ?? "",
          preferredChannel: s1b.preferredChannel ?? "WhatsApp",
        }));

        const s1c = pick<Record<string, unknown>>("1c");
        setProfile((p) => ({
          ...p,
          employees: s1c.employees ? String(s1c.employees) : "",
          salesTeamSize: s1c.salesTeamSize ? String(s1c.salesTeamSize) : "",
          marketingTeamSize: s1c.marketingTeamSize ? String(s1c.marketingTeamSize) : "",
          activeProjects: s1c.activeProjects ? String(s1c.activeProjects) : "",
          completedProjects: s1c.completedProjects ? String(s1c.completedProjects) : "",
          yearsInRealEstate: s1c.yearsInRealEstate ? String(s1c.yearsInRealEstate) : "",
          cities: ((s1c.cities as string[]) ?? []).join(", "),
          businessTypes: (s1c.businessTypes as string[]) ?? [],
          propertyTypes: (s1c.propertyTypes as string[]) ?? [],
          leadSources: (s1c.leadSources as string[]) ?? [],
        }));

        const s2 = pick<{ projects?: Partial<Project>[] }>("2");
        if (s2.projects?.length) {
          setProjects(s2.projects.map((p) => ({ ...BLANK_PROJECT, ...p })));
        }

        const s4 = pick<Record<string, unknown>>("4");
        setIcp((i) => ({
          ...i,
          buyerSegments: (s4.buyerSegments as string[]) ?? [],
          occupations: (s4.occupations as string[]) ?? [],
          industries: (s4.industries as string[]) ?? [],
          purchaseTimeline: (s4.purchaseTimeline as string) ?? "",
          purposes: (s4.purposes as string[]) ?? [],
          triggers: (s4.triggers as string[]) ?? [],
          painPoints: (s4.painPoints as string[]) ?? [],
          objections: (s4.objections as string[]) ?? [],
          budgetRange: (s4.budgetRange as string) ?? "",
          preferredCities: ((s4.preferredCities as string[]) ?? []).join(", "),
          incomeMin: s4.incomeMin ? String(s4.incomeMin) : "",
          incomeMax: s4.incomeMax ? String(s4.incomeMax) : "",
        }));

        const s5 = pick<{
          scoringWeights?: Record<string, number>;
          leadBands?: { hot?: number; warm?: number };
        }>("5");
        setScoring({
          weights: { ...DEFAULT_WEIGHTS, ...(s5.scoringWeights ?? {}) },
          hot: s5.leadBands?.hot ?? 70,
          warm: s5.leadBands?.warm ?? 40,
        });

        const s6 = pick<Record<string, string[]>>("6");
        setFeatures(
          Object.fromEntries(
            AI_FEATURE_GROUPS.map((g) => [g.key, s6[g.key] ?? []])
          )
        );
        setIntegrations(s6.integrations ?? []);

        const s9 = pick<Record<string, unknown>>("9");
        setProcess((p) =>
          Object.fromEntries(
            Object.keys(p).map((k) => [k, s9[k] != null ? String(s9[k]) : ""])
          ) as typeof p
        );

        const s11 = pick<{ teamInvites?: string[]; permissionLevel?: string }>("11");
        setTeam({
          invites: (s11.teamInvites ?? []).join(", "),
          permissionLevel: s11.permissionLevel ?? "Sales",
        });

        const s12 = pick<Record<string, boolean>>("12");
        setConsent({
          marketingConsent: s12.marketingConsent ?? null,
          aiUsageConsent: s12.aiUsageConsent ?? null,
        });

        setAssets(documents.data ?? []);
        setReady(true);
      })
      .catch(() => {
        // API error / non-admin race: bail to the dashboard — and set the skip
        // flag first, otherwise the dashboard gate immediately bounces an
        // un-onboarded admin back here, producing an infinite redirect loop
        // against a failing endpoint.
        if (bailedRef.current) return;
        bailedRef.current = true;
        sessionStorage.setItem("onboarding_skipped", "1");
        router.replace("/dashboard");
      });
  }, [loading, user, router]);

  /* ── save ───────────────────────────────────────────────────────────────── */
  const stepPayload = useCallback((key: string): Record<string, unknown> => {
    switch (key) {
      case "1":
        return { ...company, yearEstablished: toNumber(company.yearEstablished) };
      case "1b":
        return contact;
      case "1c":
        return {
          businessTypes: profile.businessTypes,
          propertyTypes: profile.propertyTypes,
          leadSources: profile.leadSources,
          cities: splitList(profile.cities),
          employees: toNumber(profile.employees),
          salesTeamSize: toNumber(profile.salesTeamSize),
          marketingTeamSize: toNumber(profile.marketingTeamSize),
          activeProjects: toNumber(profile.activeProjects),
          completedProjects: toNumber(profile.completedProjects),
          yearsInRealEstate: toNumber(profile.yearsInRealEstate),
        };
      case "2":
        return { projects: projects.filter((p) => p.name.trim()) };
      case "4":
        return {
          ...icp,
          preferredCities: splitList(icp.preferredCities),
          incomeMin: toNumber(icp.incomeMin),
          incomeMax: toNumber(icp.incomeMax),
        };
      case "5":
        return {
          scoringWeights: scoring.weights,
          leadBands: { hot: scoring.hot, warm: scoring.warm },
        };
      case "6":
        return { ...features, integrations };
      case "7":
        return {
          importLeads: imports.importLeads,
          importCustomers: imports.importCustomers,
        };
      case "8":
        // Files are already stored server-side; record the manifest so the
        // review page and any later audit can see what was attached.
        return {
          documents: assets.map((a) => ({
            document_id: a.document_id, category: a.category, filename: a.filename,
          })),
        };
      case "9":
        return Object.fromEntries(
          Object.entries(process).map(([k, v]) => [k, toNumber(v)])
        );
      case "11":
        return {
          teamInvites: splitList(team.invites),
          permissionLevel: team.permissionLevel,
        };
      case "12":
        return {
          marketingConsent: consent.marketingConsent === true,
          aiUsageConsent: consent.aiUsageConsent === true,
        };
      default:
        return {};
    }
  }, [company, contact, profile, projects, icp, scoring, features, integrations,
      imports, assets, process, team, consent]);

  const saveStep = useCallback(async (key: string) => {
    await api("/onboarding/step", {
      method: "PATCH",
      body: { step_id: key, data: stepPayload(key) },
    });
    setSaved((s) => new Set(s).add(key));
  }, [stepPayload]);

  /** Blocking requirement for the current step, or null when it may be left. */
  const blocker = useMemo((): string | null => {
    const key = STEPS[index]?.key;
    if (key === "1" && !company.companyName.trim()) return "Company name is required.";
    if (key === "1b" && !contact.fullName.trim()) return "Your full name is required.";
    if (key === "12") {
      if (consent.marketingConsent === null || consent.aiUsageConsent === null) {
        return "Please answer both consent questions.";
      }
      if (!consent.aiUsageConsent) {
        return "AI features cannot be enabled without AI usage consent.";
      }
    }
    return null;
  }, [index, company.companyName, contact.fullName, consent]);

  async function goTo(target: number) {
    setError("");
    if (target === index) return;
    // Moving forward saves; moving backward does not, so a half-typed page is
    // never persisted just because someone clicked "Back".
    if (target > index) {
      if (blocker) { setError(blocker); return; }
      setBusy(true);
      try {
        const key = STEPS[index]?.key;
        if (key) await saveStep(key);
      } catch (err) {
        setError(errorMessage(err, "Failed to save this step."));
        setBusy(false);
        return;
      }
      setBusy(false);
    }
    setIndex(target);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function launch() {
    setError("");
    setBusy(true);
    try {
      if (blocker) { setError(blocker); setBusy(false); return; }
      const res = await api<{
        data: { invites: { sent: string[]; already_exists: string[]; failed: string[] } };
      }>("/onboarding/complete", { method: "POST", body: {} });
      await refreshUser(); // picks up onboarding_completed=true so the gate stands down
      const invites = res.data.invites;
      if (invites && (invites.already_exists.length > 0 || invites.failed.length > 0)) {
        // Don't vanish to the dashboard while some invites were skipped — the
        // admin needs to see which, and why.
        setInviteResults(invites);
        setBusy(false);
        return;
      }
      router.replace("/dashboard");
    } catch (err) {
      setError(errorMessage(err, "Failed to complete setup."));
      setBusy(false);
    }
  }

  function skip() {
    sessionStorage.setItem("onboarding_skipped", "1");
    router.push("/dashboard");
  }

  /* ── uploads ────────────────────────────────────────────────────────────── */
  async function upload(category: string, file: File) {
    setError("");
    setUploading(category);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("category", category);
      const res = await api<{ data: UploadedAsset }>("/onboarding/upload", {
        method: "POST",
        formData,
      });
      setAssets((current) => [res.data, ...current]);
    } catch (err) {
      setError(errorMessage(err, `Could not upload ${file.name}.`));
    } finally {
      setUploading(null);
    }
  }

  async function removeAsset(documentId: string) {
    setError("");
    try {
      await api(`/onboarding/documents/${documentId}`, { method: "DELETE" });
      setAssets((current) => current.filter((a) => a.document_id !== documentId));
    } catch (err) {
      setError(errorMessage(err, "Could not remove that file."));
    }
  }

  function onCsv(kind: "importLeads" | "importCustomers", file: File) {
    file.text().then((text) => {
      const rows = parseCsv(text);
      const nameKey = kind === "importLeads" ? "leadsFileName" : "customersFileName";
      setImports((i) => ({
        ...i,
        [kind]: rows,
        [nameKey]: file.name,
        csvError: rows.length
          ? rows.some((r) => (r.phone ?? "").trim())
            ? ""
            : `${file.name} has no "phone" column — rows without a phone number are skipped.`
          : `${file.name} had no data rows. Expected a header row plus at least one record.`,
      }));
    });
  }

  /* ── render ─────────────────────────────────────────────────────────────── */
  if (loading || !user || !ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <Spinner />
      </div>
    );
  }

  if (inviteResults) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg px-6 text-ink">
        <Card className="w-full max-w-md space-y-4 p-6">
          <h1 className="flex items-center gap-2 text-lg font-semibold">
            <Rocket size={17} className="text-primary" /> Workspace launched
          </h1>
          {inviteResults.sent.length > 0 && (
            <p className="text-sm text-muted">
              <Check size={13} className="mr-1 inline text-success" />
              Invites sent to {inviteResults.sent.join(", ")}.
            </p>
          )}
          {inviteResults.already_exists.length > 0 && (
            <div className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2.5 text-xs">
              <p className="font-medium">Couldn&apos;t invite (account already exists):</p>
              <p className="mt-1 text-muted">{inviteResults.already_exists.join(", ")}</p>
              <p className="mt-2 text-[11px] text-faint">
                Each email can belong to only one workspace right now. These people
                already have an account — in this workspace or another one.
              </p>
            </div>
          )}
          {inviteResults.failed.length > 0 && (
            <div className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2.5 text-xs">
              <p className="font-medium">Failed to invite:</p>
              <p className="mt-1 text-muted">{inviteResults.failed.join(", ")}</p>
            </div>
          )}
          <Button className="w-full justify-center" onClick={() => router.replace("/dashboard")}>
            Continue to dashboard <ArrowRight size={14} />
          </Button>
        </Card>
      </div>
    );
  }

  const isReview = index === STEPS.length;
  const meta = STEPS[index];
  const totalPages = STEPS.length + 1;
  const weightTotal =
    Object.values(scoring.weights).reduce((a, b) => a + b, 0) || 1;
  const namedProjects = projects.filter((p) => p.name.trim());
  const inviteCount = splitList(team.invites).length;

  const groups = [...new Set(STEPS.map((s) => s.group))];

  return (
    <div className="min-h-screen bg-bg text-ink">
      <div className="fixed inset-x-0 top-0 z-40 h-1 bg-raised">
        <div
          className="h-full bg-primary transition-all duration-500"
          style={{ width: `${((index + 1) / totalPages) * 100}%` }}
        />
      </div>

      <header className="flex items-center justify-between border-b border-edge px-6 py-4">
        <p className="text-sm font-semibold">
          {company.companyName || user.tenant_name || "Your workspace"}
          <span className="ml-2 text-xs font-normal text-muted">Workspace setup</span>
        </p>
        <button onClick={skip} className="text-xs text-muted hover:text-ink hover:underline">
          Skip for now
        </button>
      </header>

      <div className="mx-auto flex max-w-6xl gap-8 px-6 py-8">
        {/* left nav */}
        <nav className="hidden w-56 shrink-0 lg:block">
          <ol className="sticky top-8 space-y-4">
            {groups.map((group) => (
              <li key={group}>
                <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint">
                  {group}
                </p>
                <ul className="space-y-0.5">
                  {STEPS.map((step, i) =>
                    step.group !== group ? null : (
                      <li key={step.key}>
                        <button
                          onClick={() => goTo(i)}
                          aria-current={i === index ? "step" : undefined}
                          className={cx(
                            "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left",
                            "text-xs transition-colors",
                            i === index
                              ? "bg-primary/10 font-medium text-primary"
                              : "text-muted hover:bg-raised hover:text-ink"
                          )}
                        >
                          <span
                            className={cx(
                              "flex h-4 w-4 shrink-0 items-center justify-center rounded-full",
                              "border text-[9px]",
                              saved.has(step.key)
                                ? "border-success bg-success/15 text-success"
                                : i === index
                                  ? "border-primary text-primary"
                                  : "border-edge-strong text-faint"
                            )}
                          >
                            {saved.has(step.key) ? <Check size={9} /> : i + 1}
                          </span>
                          <span className="truncate">{step.title}</span>
                        </button>
                      </li>
                    )
                  )}
                </ul>
              </li>
            ))}
            <li className="border-t border-edge pt-3">
              <button
                onClick={() => goTo(STEPS.length)}
                aria-current={isReview ? "step" : undefined}
                className={cx(
                  "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs transition-colors",
                  isReview
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-muted hover:bg-raised hover:text-ink"
                )}
              >
                <Rocket size={12} /> Review &amp; launch
              </button>
            </li>
          </ol>
        </nav>

        {/* form */}
        <main className="min-w-0 flex-1">
          <p className="text-[11px] font-medium uppercase tracking-wide text-primary">
            Step {index + 1} of {totalPages}
            {meta?.optional && <span className="ml-2 text-faint">Optional</span>}
          </p>
          <h1 className="mt-1 text-xl font-semibold">
            {isReview ? "Review & launch" : meta.title}
          </h1>
          <p className="mt-1 text-xs text-muted">
            {isReview
              ? "One last look. Launching creates your inventory, imports your pipeline, and sends invites."
              : meta.sub}
          </p>

          {error && (
            <p className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>
          )}

          <div className="mt-6 space-y-4">
            {/* ── 1. Company information ─────────────────────────────────── */}
            {meta?.key === "1" && (
              <Card className="grid gap-4 p-5 sm:grid-cols-2">
                <Input label="Company name *" required value={company.companyName}
                       onChange={(e) => setCompany((c) => ({ ...c, companyName: e.target.value }))} />
                <Input label="Legal entity name" value={company.legalName}
                       onChange={(e) => setCompany((c) => ({ ...c, legalName: e.target.value }))} />
                <Input label="Brand name" value={company.brandName}
                       onChange={(e) => setCompany((c) => ({ ...c, brandName: e.target.value }))} />
                <Input label="CIN" value={company.cin}
                       onChange={(e) => setCompany((c) => ({ ...c, cin: e.target.value }))} />
                <Input label="GST number" value={company.gst}
                       onChange={(e) => setCompany((c) => ({ ...c, gst: e.target.value }))} />
                <Input label="PAN" value={company.pan}
                       onChange={(e) => setCompany((c) => ({ ...c, pan: e.target.value }))} />
                <Input label="RERA registration number" value={company.rera}
                       onChange={(e) => setCompany((c) => ({ ...c, rera: e.target.value }))} />
                <Input label="Year established" type="number" min={1800}
                       max={new Date().getFullYear()} value={company.yearEstablished}
                       onChange={(e) => setCompany((c) => ({ ...c, yearEstablished: e.target.value }))} />
                <Input label="Website" value={company.website} placeholder="https://"
                       onChange={(e) => setCompany((c) => ({ ...c, website: e.target.value }))} />
                <Input label="LinkedIn page" value={company.linkedin} placeholder="https://"
                       onChange={(e) => setCompany((c) => ({ ...c, linkedin: e.target.value }))} />
                <Input label="Head office city" value={company.headOffice}
                       onChange={(e) => setCompany((c) => ({ ...c, headOffice: e.target.value }))} />
                <Input label="State" value={company.state}
                       onChange={(e) => setCompany((c) => ({ ...c, state: e.target.value }))} />
                <Input label="Country" value={company.country}
                       onChange={(e) => setCompany((c) => ({ ...c, country: e.target.value }))} />
                <div className="sm:col-span-2">
                  <Textarea label="Corporate office address" value={company.address}
                            onChange={(e) => setCompany((c) => ({ ...c, address: e.target.value }))} />
                </div>
              </Card>
            )}

            {/* ── 1b. Primary contact ────────────────────────────────────── */}
            {meta?.key === "1b" && (
              <Card className="grid gap-4 p-5 sm:grid-cols-2">
                <Input label="Full name *" required value={contact.fullName}
                       onChange={(e) => setContact((c) => ({ ...c, fullName: e.target.value }))} />
                <Select label="Designation" value={contact.designation}
                        onChange={(e) => setContact((c) => ({ ...c, designation: e.target.value }))}>
                  <option value="">Select…</option>
                  {DESIGNATIONS.map((d) => <option key={d} value={d}>{d}</option>)}
                </Select>
                <Input label="Mobile number" type="tel" value={contact.mobile}
                       onChange={(e) => setContact((c) => ({ ...c, mobile: e.target.value }))} />
                <Input label="WhatsApp number" type="tel" value={contact.whatsapp}
                       onChange={(e) => setContact((c) => ({ ...c, whatsapp: e.target.value }))} />
                <Input label="Email address" type="email" value={contact.email}
                       onChange={(e) => setContact((c) => ({ ...c, email: e.target.value }))} />
                <Select label="Preferred communication" value={contact.preferredChannel}
                        onChange={(e) => setContact((c) => ({ ...c, preferredChannel: e.target.value }))}>
                  {CONTACT_CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
                <p className="text-[11px] text-faint sm:col-span-2">
                  Saving this page renames your own account to the name above.
                </p>
              </Card>
            )}

            {/* ── 1c. Profile & footprint ────────────────────────────────── */}
            {meta?.key === "1c" && (
              <>
                <Card className="grid gap-4 p-5 sm:grid-cols-3">
                  <Input label="Total employees" type="number" min={0} value={profile.employees}
                         onChange={(e) => setProfile((p) => ({ ...p, employees: e.target.value }))} />
                  <Input label="Sales team size" type="number" min={0} value={profile.salesTeamSize}
                         onChange={(e) => setProfile((p) => ({ ...p, salesTeamSize: e.target.value }))} />
                  <Input label="Marketing team size" type="number" min={0}
                         value={profile.marketingTeamSize}
                         onChange={(e) => setProfile((p) => ({ ...p, marketingTeamSize: e.target.value }))} />
                  <Input label="Active projects" type="number" min={0} value={profile.activeProjects}
                         onChange={(e) => setProfile((p) => ({ ...p, activeProjects: e.target.value }))} />
                  <Input label="Completed projects" type="number" min={0}
                         value={profile.completedProjects}
                         onChange={(e) => setProfile((p) => ({ ...p, completedProjects: e.target.value }))} />
                  <Input label="Years in real estate" type="number" min={0}
                         value={profile.yearsInRealEstate}
                         onChange={(e) => setProfile((p) => ({ ...p, yearsInRealEstate: e.target.value }))} />
                </Card>
                <Card className="space-y-4 p-5">
                  <Input
                    label="Cities you operate in (comma-separated)"
                    value={profile.cities}
                    placeholder="Bengaluru, Mysuru, Pune"
                    onChange={(e) => setProfile((p) => ({ ...p, cities: e.target.value }))}
                  />
                  <p className="-mt-2 text-[11px] text-faint">
                    Leads whose preferred area falls inside this list score higher on the
                    geography dimension.
                  </p>
                  <Field label="Business type">
                    <Chips options={BUSINESS_TYPES} value={profile.businessTypes}
                           onChange={(v) => setProfile((p) => ({ ...p, businessTypes: v }))} />
                  </Field>
                  <Field label="Property types you sell">
                    <Chips options={PROPERTY_TYPES} value={profile.propertyTypes}
                           onChange={(v) => setProfile((p) => ({ ...p, propertyTypes: v }))} />
                  </Field>
                  <Field label="Current lead sources">
                    <Chips options={LEAD_SOURCES} value={profile.leadSources}
                           onChange={(v) => setProfile((p) => ({ ...p, leadSources: v }))} />
                  </Field>
                </Card>
              </>
            )}

            {/* ── 2. Project portfolio ───────────────────────────────────── */}
            {meta?.key === "2" && (
              <>
                {projects.map((project, idx) => {
                  const patch = (changes: Partial<Project>) =>
                    setProjects((ps) => ps.map((p, i) => (i === idx ? { ...p, ...changes } : p)));
                  return (
                    <Card key={idx} className="space-y-4 p-5">
                      <div className="flex items-center justify-between">
                        <p className="flex items-center gap-1.5 text-xs font-semibold">
                          <Building2 size={13} /> Project {idx + 1}
                        </p>
                        {projects.length > 1 && (
                          <button
                            onClick={() => setProjects((ps) => ps.filter((_, i) => i !== idx))}
                            className="text-xs text-faint hover:text-danger"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                      <div className="grid gap-4 sm:grid-cols-2">
                        <Input label="Project name" value={project.name}
                               onChange={(e) => patch({ name: e.target.value })} />
                        <Input label="Locality" value={project.location} placeholder="Whitefield"
                               onChange={(e) => patch({ location: e.target.value })} />
                        <Input label="City" value={project.city} placeholder="Bengaluru"
                               onChange={(e) => patch({ city: e.target.value })} />
                        <Select label="Status" value={project.status}
                                onChange={(e) => patch({ status: e.target.value })}>
                          {PROJECT_STATUSES.map((s) => (
                            <option key={s.value} value={s.value}>{s.label}</option>
                          ))}
                        </Select>
                        <Input label="Price range" value={project.priceRange}
                               placeholder="₹1.2Cr – ₹3.4Cr"
                               onChange={(e) => patch({ priceRange: e.target.value })} />
                        <Input label="Possession" value={project.possession}
                               placeholder="Dec 2027"
                               onChange={(e) => patch({ possession: e.target.value })} />
                        <Input label="Project RERA number" value={project.rera}
                               onChange={(e) => patch({ rera: e.target.value })} />
                        <Input label="Unique selling point" value={project.usp}
                               placeholder="Lake-facing towers"
                               onChange={(e) => patch({ usp: e.target.value })} />
                      </div>
                      <Field
                        label="Configurations on offer"
                        hint="Each configuration becomes one available unit, priced across the range above."
                      >
                        <Chips options={CONFIGURATIONS} value={project.configurations}
                               onChange={(v) => patch({ configurations: v })} />
                      </Field>
                      <Field label="Amenities">
                        <Chips options={AMENITIES} value={project.amenities}
                               onChange={(v) => patch({ amenities: v })} />
                      </Field>
                    </Card>
                  );
                })}
                <Button
                  variant="secondary" className="w-full justify-center"
                  onClick={() => setProjects((ps) => [...ps, { ...BLANK_PROJECT }])}
                >
                  + Add another project
                </Button>
              </>
            )}

            {/* ── 4. Ideal customer profile ──────────────────────────────── */}
            {meta?.key === "4" && (
              <>
                <Card className="space-y-4 p-5">
                  <Field label="Who buys from you">
                    <Chips options={BUYER_SEGMENTS} value={icp.buyerSegments}
                           onChange={(v) => setIcp((i) => ({ ...i, buyerSegments: v }))} />
                  </Field>
                  <Field label="Typical occupations">
                    <Chips options={OCCUPATIONS} value={icp.occupations}
                           onChange={(v) => setIcp((i) => ({ ...i, occupations: v }))} />
                  </Field>
                  <Field label="Industries">
                    <Chips options={INDUSTRIES} value={icp.industries}
                           onChange={(v) => setIcp((i) => ({ ...i, industries: v }))} />
                  </Field>
                </Card>
                <Card className="grid gap-4 p-5 sm:grid-cols-2">
                  <Input label="Typical budget range" value={icp.budgetRange}
                         placeholder="₹80L – ₹4Cr"
                         onChange={(e) => setIcp((i) => ({ ...i, budgetRange: e.target.value }))} />
                  <Select label="Usual purchase timeline" value={icp.purchaseTimeline}
                          onChange={(e) => setIcp((i) => ({ ...i, purchaseTimeline: e.target.value }))}>
                    <option value="">Select…</option>
                    {PURCHASE_TIMELINES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </Select>
                  <Input label="Annual income floor (₹)" type="number" min={0} value={icp.incomeMin}
                         onChange={(e) => setIcp((i) => ({ ...i, incomeMin: e.target.value }))} />
                  <Input label="Annual income ceiling (₹)" type="number" min={0}
                         value={icp.incomeMax}
                         onChange={(e) => setIcp((i) => ({ ...i, incomeMax: e.target.value }))} />
                  <div className="sm:col-span-2">
                    <Input label="Preferred cities (comma-separated)" value={icp.preferredCities}
                           placeholder="Bengaluru, Mumbai"
                           onChange={(e) => setIcp((i) => ({ ...i, preferredCities: e.target.value }))} />
                  </div>
                </Card>
                <Card className="space-y-4 p-5">
                  <Field label="Why they buy">
                    <Chips options={BUYING_PURPOSES} value={icp.purposes}
                           onChange={(v) => setIcp((i) => ({ ...i, purposes: v }))} />
                  </Field>
                  <Field label="What triggers the decision">
                    <Chips options={PURCHASE_TRIGGERS} value={icp.triggers}
                           onChange={(v) => setIcp((i) => ({ ...i, triggers: v }))} />
                  </Field>
                  <Field label="Their pain points">
                    <Chips options={PAIN_POINTS} value={icp.painPoints}
                           onChange={(v) => setIcp((i) => ({ ...i, painPoints: v }))} />
                  </Field>
                  <Field
                    label="Objections you hear most"
                    hint="Used to draft follow-ups that pre-empt the objection instead of walking into it."
                  >
                    <Chips options={OBJECTIONS} value={icp.objections}
                           onChange={(v) => setIcp((i) => ({ ...i, objections: v }))} />
                  </Field>
                </Card>
              </>
            )}

            {/* ── 5. AI lead scoring ─────────────────────────────────────── */}
            {meta?.key === "5" && (
              <>
                <Card className="space-y-5 p-5">
                  <p className="text-xs text-muted">
                    Drag to set how much each dimension matters. These are relative
                    weights, not percentages — the share shown on the right is what
                    the scoring engine actually applies.
                  </p>
                  {SCORING_DIMENSIONS.map((dimension) => (
                    <WeightSlider
                      key={dimension.key}
                      label={dimension.label}
                      hint={dimension.hint}
                      value={scoring.weights[dimension.key] ?? 0}
                      share={(scoring.weights[dimension.key] ?? 0) / weightTotal}
                      onChange={(v) =>
                        setScoring((s) => ({
                          ...s, weights: { ...s.weights, [dimension.key]: v },
                        }))
                      }
                    />
                  ))}
                  <button
                    type="button"
                    onClick={() => setScoring((s) => ({ ...s, weights: { ...DEFAULT_WEIGHTS } }))}
                    className="text-xs text-primary hover:underline"
                  >
                    Reset to recommended weights
                  </button>
                </Card>
                <Card className="space-y-4 p-5">
                  <p className="text-xs font-semibold">Lead bands</p>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Input
                      label="Hot at or above" type="number" min={1} max={100}
                      value={String(scoring.hot)}
                      onChange={(e) => setScoring((s) => ({ ...s, hot: Number(e.target.value) }))}
                    />
                    <Input
                      label="Warm at or above" type="number" min={0} max={99}
                      value={String(scoring.warm)}
                      onChange={(e) => setScoring((s) => ({ ...s, warm: Number(e.target.value) }))}
                    />
                  </div>
                  {scoring.hot <= scoring.warm && (
                    <p className="rounded-lg bg-warning/10 px-3 py-2 text-[11px] text-warning">
                      The hot threshold must be above the warm one, otherwise no lead can
                      ever be warm. Saved as-is, these values fall back to 70 / 40.
                    </p>
                  )}
                  <p className="text-[11px] text-faint">
                    Anything below the warm threshold is cold. A lead crossing into hot
                    notifies its owner.
                  </p>
                </Card>
              </>
            )}

            {/* ── 6. AI features & integrations ──────────────────────────── */}
            {meta?.key === "6" && (
              <>
                {AI_FEATURE_GROUPS.map((group) => (
                  <Card key={group.key} className="space-y-3 p-5">
                    <p className="text-xs font-semibold">{group.label}</p>
                    <Chips
                      options={group.options}
                      value={features[group.key] ?? []}
                      onChange={(v) => setFeatures((f) => ({ ...f, [group.key]: v }))}
                    />
                  </Card>
                ))}
                <Card className="space-y-3 p-5">
                  <p className="text-xs font-semibold">Integrations to connect</p>
                  <Chips options={INTEGRATIONS} value={integrations} onChange={setIntegrations} />
                  <p className="text-[11px] text-faint">
                    Selecting these records your intent. Each one still needs its own
                    credentials in Settings before it goes live.
                  </p>
                </Card>
              </>
            )}

            {/* ── 7. Import pipeline ─────────────────────────────────────── */}
            {meta?.key === "7" && (
              <Card className="space-y-4 p-5">
                <p className="flex items-center gap-1.5 text-xs font-semibold">
                  <Upload size={13} /> Import your existing pipeline
                </p>
                <p className="text-[11px] text-faint">
                  CSV with columns: first_name, last_name, email, phone. A phone number
                  is required — rows without one are skipped.
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
                  {(["importLeads", "importCustomers"] as const).map((kind) => {
                    const fileName =
                      kind === "importLeads" ? imports.leadsFileName : imports.customersFileName;
                    const rows = imports[kind];
                    return (
                      <label key={kind} className="block cursor-pointer">
                        <span className="mb-1.5 block text-xs font-medium text-muted">
                          {kind === "importLeads" ? "Leads CSV" : "Customers CSV"}
                        </span>
                        <input
                          type="file" accept=".csv" className="hidden"
                          onChange={(e) => e.target.files?.[0] && onCsv(kind, e.target.files[0])}
                        />
                        <span className="flex items-center gap-2 rounded-lg border border-dashed border-edge-strong px-3 py-2.5 text-xs text-muted hover:border-primary">
                          <Upload size={13} />
                          {fileName || "Choose file"}
                        </span>
                        {rows.length > 0 && (
                          <span className="mt-1 block text-[11px] text-success">
                            {rows.length} rows parsed
                          </span>
                        )}
                      </label>
                    );
                  })}
                </div>
                {imports.csvError && (
                  <p className="rounded-lg bg-warning/10 px-3 py-2 text-[11px] text-warning">
                    {imports.csvError}
                  </p>
                )}
              </Card>
            )}

            {/* ── 8. Documents & knowledge base ──────────────────────────── */}
            {meta?.key === "8" && (
              <>
                <Card className="space-y-3 p-5">
                  <p className="flex items-center gap-1.5 text-xs font-semibold">
                    <FileText size={13} /> Brand & project assets
                  </p>
                  <p className="text-[11px] text-faint">
                    Files upload as soon as you pick them and are stored in your
                    workspace documents — you can leave this page and come back.
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {DOCUMENT_SLOTS.map((slot) => (
                      <FileSlot
                        key={slot.category}
                        label={slot.label}
                        accept={slot.accept}
                        category={slot.category}
                        assets={assets}
                        busy={uploading === slot.category}
                        onPick={(file) => upload(slot.category, file)}
                        onRemove={removeAsset}
                      />
                    ))}
                  </div>
                </Card>
                <Card className="space-y-3 p-5">
                  <p className="text-xs font-semibold">AI knowledge base</p>
                  <p className="text-[11px] text-faint">
                    Documents the AI is allowed to draw on: {KNOWLEDGE_BASE_HINT.join(", ")}.
                  </p>
                  <FileSlot
                    label="Knowledge base documents"
                    accept=".pdf,.doc,.docx,.txt,.csv,.xls,.xlsx"
                    category="knowledge_base"
                    assets={assets}
                    busy={uploading === "knowledge_base"}
                    onPick={(file) => upload("knowledge_base", file)}
                    onRemove={removeAsset}
                  />
                </Card>
              </>
            )}

            {/* ── 9. Sales process & targets ─────────────────────────────── */}
            {meta?.key === "9" && (
              <>
                <Card className="grid gap-4 p-5 sm:grid-cols-3">
                  <Input label="Response time SLA (minutes)" type="number" min={0}
                         value={process.responseTimeMinutes}
                         onChange={(e) => setProcess((p) => ({ ...p, responseTimeMinutes: e.target.value }))} />
                  <Input label="Site visits per booking" type="number" min={0}
                         value={process.averageSiteVisits}
                         onChange={(e) => setProcess((p) => ({ ...p, averageSiteVisits: e.target.value }))} />
                  <Input label="Booking amount (₹)" type="number" min={0}
                         value={process.bookingAmount}
                         onChange={(e) => setProcess((p) => ({ ...p, bookingAmount: e.target.value }))} />
                </Card>
                <Card className="grid gap-4 p-5 sm:grid-cols-3">
                  <Input label="Monthly lead target" type="number" min={0}
                         value={process.monthlyLeadTarget}
                         onChange={(e) => setProcess((p) => ({ ...p, monthlyLeadTarget: e.target.value }))} />
                  <Input label="Monthly site-visit target" type="number" min={0}
                         value={process.monthlySiteVisitTarget}
                         onChange={(e) => setProcess((p) => ({ ...p, monthlySiteVisitTarget: e.target.value }))} />
                  <Input label="Monthly booking target" type="number" min={0}
                         value={process.monthlyBookingTarget}
                         onChange={(e) => setProcess((p) => ({ ...p, monthlyBookingTarget: e.target.value }))} />
                  <Input label="Monthly revenue target (₹)" type="number" min={0}
                         value={process.monthlyRevenueTarget}
                         onChange={(e) => setProcess((p) => ({ ...p, monthlyRevenueTarget: e.target.value }))} />
                  <Input label="Maximum cost per lead (₹)" type="number" min={0}
                         value={process.maxCpl}
                         onChange={(e) => setProcess((p) => ({ ...p, maxCpl: e.target.value }))} />
                  <Input label="Target ROAS" type="number" min={0} step="0.1"
                         value={process.targetRoas}
                         onChange={(e) => setProcess((p) => ({ ...p, targetRoas: e.target.value }))} />
                </Card>
              </>
            )}

            {/* ── 11. Team invites ───────────────────────────────────────── */}
            {meta?.key === "11" && (
              <Card className="space-y-4 p-5">
                <p className="flex items-center gap-1.5 text-xs font-semibold">
                  <Users size={13} /> Invite your team
                </p>
                <Input
                  label="Email addresses (comma-separated)" value={team.invites}
                  placeholder="priya@company.com, rahul@company.com"
                  onChange={(e) => setTeam((t) => ({ ...t, invites: e.target.value }))}
                />
                <Select label="Their role" value={team.permissionLevel}
                        onChange={(e) => setTeam((t) => ({ ...t, permissionLevel: e.target.value }))}>
                  {INVITE_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </Select>
                <p className="text-[11px] text-faint">
                  Invites are sent when you launch. Everyone listed here gets the same
                  role — you can change individual roles later under Settings → Team.
                </p>
              </Card>
            )}

            {/* ── 12. Compliance & consent ───────────────────────────────── */}
            {meta?.key === "12" && (
              <Card className="space-y-5 p-5">
                <Field
                  label="Marketing consent"
                  hint="Applies to every lead and customer you import or capture."
                >
                  <p className="mb-2 text-xs text-muted">
                    Do you confirm that all customer data uploaded here was collected
                    with appropriate consent, and may be used for marketing in
                    compliance with applicable privacy laws?
                  </p>
                  <YesNo
                    value={consent.marketingConsent}
                    onChange={(v) => setConsent((c) => ({ ...c, marketingConsent: v }))}
                  />
                </Field>
                <Field
                  label="AI usage consent"
                  hint="Required — the AI features cannot be enabled without it."
                >
                  <p className="mb-2 text-xs text-muted">
                    Do you authorise the platform to analyse your project data, customer
                    interactions, and campaign performance to improve AI recommendations
                    and automations?
                  </p>
                  <YesNo
                    value={consent.aiUsageConsent}
                    onChange={(v) => setConsent((c) => ({ ...c, aiUsageConsent: v }))}
                  />
                </Field>
              </Card>
            )}

            {/* ── review ─────────────────────────────────────────────────── */}
            {isReview && (
              <>
                <Card className="space-y-3 p-5">
                  {[
                    ["Company", company.companyName || "—"],
                    ["Primary contact", contact.fullName || "—"],
                    ["Operating cities", splitList(profile.cities).join(", ") || "—"],
                    ["Projects to create", String(namedProjects.length)],
                    ["Units to create",
                      String(namedProjects.reduce(
                        (n, p) => n + Math.max(p.configurations.length, 1), 0
                      ))],
                    ["Buyer segments", icp.buyerSegments.join(", ") || "—"],
                    ["Leads to import", String(imports.importLeads.length)],
                    ["Customers to import", String(imports.importCustomers.length)],
                    ["Documents uploaded", String(assets.length)],
                    ["Team invites", String(inviteCount)],
                    ["AI usage consent", consent.aiUsageConsent ? "Given" : "Not given"],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="flex items-center justify-between gap-4 border-b border-edge/50 pb-2 text-sm last:border-0 last:pb-0"
                    >
                      <span className="shrink-0 text-muted">{label}</span>
                      <span className="flex min-w-0 items-center gap-1.5 text-right font-medium">
                        <Check size={13} className="shrink-0 text-success" />
                        <span className="truncate">{value}</span>
                      </span>
                    </div>
                  ))}
                </Card>
                <p className="text-[11px] text-faint">
                  Launching creates your property records, imports your pipeline, and
                  sends team invites. Everything here stays editable under
                  Settings → Company profile.
                </p>
              </>
            )}
          </div>

          <div className="mt-8 flex items-center justify-between">
            <Button
              variant="ghost" disabled={index === 0 || busy}
              onClick={() => goTo(index - 1)}
            >
              <ArrowLeft size={14} /> Back
            </Button>
            {!isReview ? (
              <Button onClick={() => goTo(index + 1)} disabled={busy}>
                {busy ? <Spinner size={14} /> : <>Next <ArrowRight size={14} /></>}
              </Button>
            ) : (
              <Button onClick={launch} disabled={busy}>
                {busy ? <Spinner size={14} /> : <><Rocket size={14} /> Launch workspace</>}
              </Button>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
