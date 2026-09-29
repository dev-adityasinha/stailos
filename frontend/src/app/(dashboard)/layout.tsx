"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  BarChart3, Bell, Building2, Calendar, CheckSquare, ChevronsLeft, ChevronsRight,
  FileText, FolderOpen, LayoutDashboard, LogOut, Menu, Plus, Search, Settings,
  Sparkles, Ticket, Users, UserSquare2, Wallet, X,
} from "lucide-react";
import { ADMIN_ROLES, ROLE_LABELS, can, useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { Avatar, Badge, Button, EmptyState, Spinner, cx } from "@/components/ui";
import { ThemeToggle } from "@/components/theme-toggle";
import { timeAgo } from "@/lib/format";

// `resource` is what the page reads from the API; roles without read access to
// it neither see the link nor get the page (the API would only answer 403).
const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/leads", label: "Leads", icon: Users, resource: "leads" },
  { href: "/pipeline", label: "Pipeline", icon: BarChart3, resource: "leads" },
  { href: "/customers", label: "Customers", icon: UserSquare2, resource: "customers" },
  { href: "/properties", label: "Properties", icon: Building2, resource: "properties" },
  { href: "/bookings", label: "Bookings", icon: Wallet, resource: "bookings" },
  { href: "/events", label: "Events", icon: Ticket, resource: "events" },
  { href: "/tasks", label: "Tasks", icon: CheckSquare, resource: "tasks" },
  { href: "/calendar", label: "Calendar", icon: Calendar, resource: "calendar" },
  { href: "/analytics", label: "Analytics", icon: BarChart3, resource: "analytics" },
  { href: "/reports", label: "Reports", icon: FileText, resource: "reports" },
  { href: "/documents", label: "Documents", icon: FolderOpen, resource: "documents" },
  { href: "/notifications", label: "Notifications", icon: Bell, resource: "notifications" },
];

/** Resource a path needs, for pages reached by URL rather than the sidebar. */
function resourceFor(pathname: string): string | undefined {
  if (pathname === "/settings/team" || pathname.startsWith("/settings/team/")) return "users";
  return NAV.find((n) => pathname === n.href || pathname.startsWith(n.href + "/"))?.resource;
}

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  read: boolean;
  created_at: string;
}

function NotificationTray() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const seenIds = useRef<Set<string> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api<{ data: Notification[]; meta: { unread: number } }>(
        "/notifications",
        { params: { limit: 15 } }
      );
      setItems(res.data);
      setUnread(res.meta.unread);
      if (res.meta.unread > 0 && "Notification" in window &&
          window.Notification.permission === "default") {
        window.Notification.requestPermission();
      }
      // Fire a native browser notification for items that appeared since the
      // last poll (Task 12: browser notifications). First poll only primes.
      if ("Notification" in window && window.Notification.permission === "granted") {
        if (seenIds.current !== null) {
          for (const n of res.data) {
            if (!n.read && !seenIds.current.has(n.id)) {
              new window.Notification("Pappu AI CRM", { body: n.title, tag: n.id });
            }
          }
        }
        seenIds.current = new Set(res.data.map((n) => n.id));
      }
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function markAll() {
    await api("/notifications/read-all", { method: "POST" });
    load();
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Notifications"
        className="relative rounded-lg p-2 text-muted hover:bg-raised hover:text-ink"
      >
        <Bell size={17} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="fade-up absolute right-0 top-11 z-40 w-80 rounded-xl border border-edge-strong bg-surface shadow-2xl">
          <div className="flex items-center justify-between border-b border-edge px-4 py-2.5">
            <p className="text-xs font-semibold">Notifications</p>
            {unread > 0 && (
              <button onClick={markAll} className="text-[11px] text-primary hover:underline">
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-4 py-8 text-center text-xs text-faint">
                Nothing yet — assignment alerts, follow-up reminders and booking
                updates land here.
              </p>
            ) : (
              items.map((n) => (
                <div
                  key={n.id}
                  className={cx(
                    "border-b border-edge px-4 py-2.5 last:border-0",
                    !n.read && "bg-primary/[0.06]"
                  )}
                >
                  <p className="text-xs">{n.title}</p>
                  {n.body && <p className="mt-0.5 text-[11px] text-muted">{n.body}</p>}
                  <p className="mt-1 text-[10px] text-faint">{timeAgo(n.created_at)}</p>
                </div>
              ))
            )}
          </div>
          <Link
            href="/notifications"
            onClick={() => setOpen(false)}
            className="block border-t border-edge px-4 py-2 text-center text-[11px] text-primary hover:underline"
          >
            View all notifications
          </Link>
        </div>
      )}
    </div>
  );
}

function GlobalSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (q.trim()) router.push(`/leads?q=${encodeURIComponent(q.trim())}`);
  }

  return (
    <form onSubmit={onSubmit} className="relative hidden md:block">
      <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search leads, customers…"
        className="w-64 rounded-lg border border-edge bg-bg py-1.5 pl-8 pr-3 text-xs text-ink placeholder:text-faint outline-none focus:border-primary"
      />
    </form>
  );
}

function QuickActions() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const { user } = useAuth();
  const actions = [
    { label: "New lead", href: "/leads?new=1", resource: "leads" },
    { label: "New task", href: "/tasks?new=1", resource: "tasks" },
    { label: "New event", href: "/calendar?new=1", resource: "calendar" },
    { label: "Upload document", href: "/documents?new=1", resource: "documents" },
  ].filter((a) => can(user, a.resource, "create"));

  if (actions.length === 0) return null;

  return (
    <div className="relative" ref={ref}>
      <Button size="sm" onClick={() => setOpen((o) => !o)}>
        <Plus size={14} /> New
      </Button>
      {open && (
        <div className="fade-up absolute right-0 top-9 z-40 w-44 rounded-xl border border-edge-strong bg-surface py-1 shadow-2xl">
          {actions.map((a) => (
            <button
              key={a.href}
              onClick={() => {
                setOpen(false);
                router.push(a.href);
              }}
              className="block w-full px-3 py-2 text-left text-xs text-muted hover:bg-raised hover:text-ink"
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const pageResource = resourceFor(pathname);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  // Onboarding gate: workspace admins with an un-onboarded tenant go to the
  // setup wizard first. Non-admins are never redirected, and "Skip for now"
  // (sessionStorage flag) keeps the gate from becoming a trap.
  useEffect(() => {
    if (loading || !user) return;
    if (
      ADMIN_ROLES.has(user.role) &&
      user.onboarding_completed === false &&
      sessionStorage.getItem("onboarding_skipped") !== "1"
    ) {
      router.replace("/onboarding");
    }
  }, [loading, user, router]);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner size={28} />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      {/* Drawer backdrop (phones + tablets) */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      )}
      {/* Sidebar — persistent on desktop, off-canvas overlay drawer below lg */}
      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-50 flex h-screen w-64 flex-col border-r border-edge bg-surface transition-transform duration-200 lg:w-56",
          "lg:sticky lg:top-0 lg:z-auto lg:transition-[width]",
          collapsed ? "lg:w-[60px]" : "lg:w-56",
          mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        <div className="flex items-center gap-2 px-4 py-4">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/20 text-primary">
            <Sparkles size={16} />
          </span>
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold leading-tight">Pappu AI</p>
              <p className="text-[10px] text-faint">STAIL Realty OS</p>
            </div>
          )}
          <button
            onClick={() => setMobileOpen(false)}
            className="ml-auto rounded-lg p-1 text-muted hover:bg-raised hover:text-ink lg:hidden"
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
          {NAV.filter((n) => !n.resource || can(user, n.resource)).map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                title={label}
                onClick={() => setMobileOpen(false)}
                className={cx(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition-colors",
                  active
                    ? "bg-primary/15 font-medium text-primary"
                    : "text-muted hover:bg-raised hover:text-ink"
                )}
              >
                <Icon size={16} className="shrink-0" />
                {!collapsed && label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-edge p-2">
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="hidden w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-muted hover:bg-raised hover:text-ink lg:flex"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
            {!collapsed && "Collapse"}
          </button>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-edge bg-bg/90 px-5 py-2.5 backdrop-blur">
          <button
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            className="rounded-lg p-2 text-muted hover:bg-raised hover:text-ink lg:hidden"
          >
            <Menu size={18} />
          </button>
          <GlobalSearch />
          <div className="flex items-center gap-2">
            <QuickActions />
            <ThemeToggle />
            <NotificationTray />
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setMenuOpen((o) => !o)}
                className="flex items-center gap-2 rounded-lg p-1 pr-2 hover:bg-raised"
                aria-label="User menu"
              >
                <Avatar name={user.full_name} color={user.avatar_color} size={28} />
                <span className="hidden text-left sm:block">
                  <span className="block max-w-[140px] truncate text-xs font-medium">
                    {user.full_name}
                  </span>
                  <span className="block text-[10px] text-faint">
                    {ROLE_LABELS[user.role] ?? user.role}
                  </span>
                </span>
              </button>
              {menuOpen && (
                <div className="fade-up absolute right-0 top-11 z-40 w-52 rounded-xl border border-edge-strong bg-surface py-1 shadow-2xl">
                  <div className="border-b border-edge px-3 py-2">
                    <p className="truncate text-xs font-medium">{user.email}</p>
                    <Badge color="#3b82f6" className="mt-1">
                      {ROLE_LABELS[user.role] ?? user.role}
                    </Badge>
                  </div>
                  <Link
                    href="/settings"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-xs text-muted hover:bg-raised hover:text-ink"
                  >
                    <Settings size={14} /> Settings & sessions
                  </Link>
                  {ADMIN_ROLES.has(user.role) && (
                    <>
                      <Link
                        href="/settings/company"
                        onClick={() => setMenuOpen(false)}
                        className="flex items-center gap-2 px-3 py-2 text-xs text-muted hover:bg-raised hover:text-ink"
                      >
                        <Building2 size={14} /> Company profile
                      </Link>
                      <Link
                        href="/settings/team"
                        onClick={() => setMenuOpen(false)}
                        className="flex items-center gap-2 px-3 py-2 text-xs text-muted hover:bg-raised hover:text-ink"
                      >
                        <Users size={14} /> Team & roles
                      </Link>
                    </>
                  )}
                  <button
                    onClick={logout}
                    className="flex w-full items-center gap-2 px-3 py-2 text-xs text-danger hover:bg-raised"
                  >
                    <LogOut size={14} /> Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-5">
          {pageResource && !can(user, pageResource) ? (
            <EmptyState
              title="You don't have access to this page"
              hint={`Your role (${ROLE_LABELS[user.role] ?? user.role}) can't view this module. Ask a workspace admin if you need it.`}
              action={<Link href="/dashboard"><Button variant="secondary">Back to dashboard</Button></Link>}
            />
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}
