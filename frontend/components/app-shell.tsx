"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  BookOpen,
  BarChart3,
  FileSpreadsheet,
  CheckSquare,
  BookText,
  Settings,
  ShieldCheck,
  Menu,
  X,
  Sparkles,
  GitCompare,
} from "lucide-react";
import axios from "axios";
import { useAuthStore } from "@/lib/auth-store";
import { ThemeToggle } from "@/components/theme-toggle";
import { Toaster } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "GST Chat", icon: MessageSquare },
  { href: "/invoices", label: "Invoices", icon: FileText },
  { href: "/accounting", label: "Accounting", icon: BookText },
  { href: "/documents", label: "Documents", icon: BookOpen },
  { href: "/returns", label: "Returns", icon: FileSpreadsheet },
  { href: "/reconciliation", label: "Reconciliation", icon: GitCompare },
  { href: "/approvals", label: "Review queue", icon: CheckSquare },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
];

const ADMIN_NAV_ITEMS = [
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/admin", label: "Admin", icon: ShieldCheck },
];

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/**
 * Live backend reachability pill. Without this, a stopped API surfaces only as
 * a generic "something went wrong" on whichever page you happened to open.
 */
function ApiStatus() {
  const { data, isLoading } = useQuery({
    queryKey: ["api-health"],
    queryFn: async () => {
      const res = await axios.get(`${API_BASE_URL}/api/v1/health`, { timeout: 4000 });
      return res.data as { status: string };
    },
    refetchInterval: 15_000,
    retry: false,
  });

  const online = data?.status === "ok";
  const label = isLoading ? "Checking API…" : online ? "API connected" : "API offline";

  return (
    <div
      className="flex items-center gap-2 rounded-md border border-border bg-elevated px-2 py-1.5 text-xs elev-1"
      title={online ? API_BASE_URL : `Cannot reach ${API_BASE_URL}`}
    >
      <span className="relative flex h-1.5 w-1.5 shrink-0">
        {online && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-good opacity-60" />
        )}
        <span
          className={cn(
            "relative inline-flex h-1.5 w-1.5 rounded-full transition-colors duration-300",
            isLoading ? "bg-muted-foreground" : online ? "bg-good" : "bg-critical"
          )}
          aria-hidden
        />
      </span>
      <span className={cn("truncate", online ? "text-muted-foreground" : "text-critical")}>
        {label}
      </span>
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);
  const activeOrg = user?.memberships[0];
  const isAdmin = ["org_admin", "super_admin"].includes(activeOrg?.role ?? "");
  const navItems = isAdmin ? [...NAV_ITEMS, ...ADMIN_NAV_ITEMS] : NAV_ITEMS;

  return (
    <>
      <div className="flex h-16 items-center gap-2 border-b border-border px-5">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-primary to-accent2 shadow-[var(--elev-2),var(--edge-top-strong)]">
          <Sparkles className="h-3.5 w-3.5 text-white" />
        </span>
        <span className="text-[15px] font-semibold tracking-tight">GST AI Copilot</span>
      </div>

      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname?.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
                "transition-all duration-200 ease-out",
                active
                  ? "bg-elevated text-primary elev-2"
                  : "text-muted-foreground hover:-translate-y-0.5 hover:bg-elevated hover:text-foreground hover:shadow-[var(--elev-1),var(--edge-top)]"
              )}
            >
              {active && (
                <span
                  className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r bg-primary"
                  aria-hidden
                />
              )}
              <Icon className="h-4 w-4 shrink-0 transition-transform duration-200 group-hover:scale-110" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex flex-col gap-2 border-t border-border p-3">
        {user && (
          <div className="px-2 text-xs">
            <div className="truncate font-medium text-foreground">{user.full_name}</div>
            <div className="truncate text-muted-foreground">{activeOrg?.organization_name}</div>
          </div>
        )}
        <ApiStatus />
        <div className="flex items-center justify-between px-2 pt-1">
          <span className="text-xs text-muted-foreground">Theme</span>
          <ThemeToggle />
        </div>
      </div>
    </>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="relative flex min-h-screen bg-background">
      {/* Ambient depth field — sits behind everything, never intercepts input */}
      <div className="ambient" aria-hidden />

      {/* Desktop sidebar */}
      <aside className="glass relative z-10 hidden w-64 shrink-0 flex-col border-r border-border sm:flex">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 sm:hidden">
          <div
            className="animate-fade-in absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <aside className="glass animate-fade-in absolute left-0 top-0 flex h-full w-64 flex-col border-r border-border elev-3">
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <div className="glass flex h-14 items-center gap-3 border-b border-border px-4 sm:hidden">
          <button
            onClick={() => setMobileOpen((v) => !v)}
            aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-elevated hover:text-foreground"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <span className="text-sm font-semibold">GST AI Copilot</span>
        </div>

        {children}
      </div>

      <Toaster />
    </div>
  );
}
