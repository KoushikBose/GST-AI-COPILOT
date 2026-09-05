"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  ReceiptText,
  ShieldAlert,
  Clock,
  ArrowRight,
  WifiOff,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { StatTile } from "@/components/stat-tile";
import { ChartCard } from "@/components/charts/chart-card";
import { GstTrendChart, type TrendPoint } from "@/components/charts/gst-trend-chart";
import { BreakdownBarChart } from "@/components/charts/breakdown-bar-chart";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  formatCompactCurrency,
  formatCurrency,
  formatPeriod,
  titleCase,
  toNumber,
} from "@/lib/utils";

interface InvoiceItem {
  cgst: string;
  sgst: string;
  igst: string;
  cess: string;
}

interface Invoice {
  id: string;
  status: string;
  direction: string;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  buyer_name: string | null;
  total_tax: string | null;
  grand_total: string | null;
  items: InvoiceItem[];
}

interface ComplianceIssue {
  severity: string;
  rule_code: string;
  message: string;
}

const STATUS_VARIANT: Record<string, "good" | "warning" | "critical" | "outline"> = {
  extracted: "good",
  validated: "good",
  approved: "good",
  needs_review: "warning",
  failed: "critical",
  rejected: "critical",
};

const SEVERITY_COLOR: Record<string, string> = {
  critical: "var(--status-critical)",
  high: "var(--status-serious)",
  medium: "var(--status-warning)",
  low: "var(--status-good)",
  info: "var(--series-1)",
};

export default function DashboardPage() {
  const invoicesQuery = useQuery({
    queryKey: ["invoices"],
    queryFn: async () => (await apiClient.get<Invoice[]>("/invoices")).data,
    retry: false,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((i) => ["processing", "uploaded"].includes(i.status))
        ? 4000
        : false,
  });
  const issuesQuery = useQuery({
    queryKey: ["compliance-issues"],
    queryFn: async () => (await apiClient.get<ComplianceIssue[]>("/compliance/issues")).data,
    retry: false,
  });
  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: async () => (await apiClient.get<unknown[]>("/documents")).data,
    retry: false,
  });

  // Memoised so the `?? []` fallback doesn't hand every downstream useMemo a
  // fresh array identity on each render.
  const invoices = useMemo(() => invoicesQuery.data ?? [], [invoicesQuery.data]);
  const issues = useMemo(() => issuesQuery.data ?? [], [issuesQuery.data]);
  const offline = invoicesQuery.isError && issuesQuery.isError && documentsQuery.isError;

  const stats = useMemo(() => {
    const totalTax = invoices.reduce((sum, i) => sum + toNumber(i.total_tax), 0);
    return {
      totalInvoices: invoices.length,
      totalTax,
      pendingReview: invoices.filter((i) => i.status === "needs_review").length,
      criticalIssues: issues.filter((i) => i.severity === "critical").length,
    };
  }, [invoices, issues]);

  /** Monthly GST totals, oldest → newest, from each invoice's date. */
  const trend: TrendPoint[] = useMemo(() => {
    const byPeriod = new Map<string, number>();
    for (const inv of invoices) {
      if (!inv.invoice_date) continue;
      const period = inv.invoice_date.slice(0, 7); // YYYY-MM
      byPeriod.set(period, (byPeriod.get(period) ?? 0) + toNumber(inv.total_tax));
    }
    return [...byPeriod.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-12)
      .map(([period, value]) => ({ period: formatPeriod(period), value }));
  }, [invoices]);

  const taxSplit = useMemo(() => {
    const totals = { CGST: 0, SGST: 0, IGST: 0, CESS: 0 };
    for (const inv of invoices) {
      for (const item of inv.items ?? []) {
        totals.CGST += toNumber(item.cgst);
        totals.SGST += toNumber(item.sgst);
        totals.IGST += toNumber(item.igst);
        totals.CESS += toNumber(item.cess);
      }
    }
    return Object.entries(totals)
      .filter(([, v]) => v > 0)
      .map(([label, value]) => ({ label, value }));
  }, [invoices]);

  const issuesBySeverity = useMemo(() => {
    const order = ["critical", "high", "medium", "low", "info"];
    const counts = new Map<string, number>();
    for (const issue of issues) {
      counts.set(issue.severity, (counts.get(issue.severity) ?? 0) + 1);
    }
    return order
      .filter((sev) => counts.has(sev))
      .map((sev) => ({
        label: titleCase(sev),
        value: counts.get(sev) ?? 0,
        color: SEVERITY_COLOR[sev],
      }));
  }, [issues]);

  const trendSparkline = trend.map((t) => t.value);

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Dashboard</h1>
          <p className="text-xs text-muted-foreground">
            GST position, compliance exposure and processing status
          </p>
        </div>
      </header>

      <main className="flex-1 space-y-5 p-6">
        {offline && (
          <Card className="animate-fade-in flex items-start gap-3 border-critical/40 p-4">
            <WifiOff className="mt-0.5 h-4 w-4 shrink-0 text-critical" />
            <div className="text-sm">
              <p className="font-medium text-critical">Backend API is unreachable</p>
              <p className="mt-0.5 text-muted-foreground">
                The dashboard can&apos;t load data until the API is running at{" "}
                <code className="rounded bg-elevated px-1 py-0.5 text-xs">
                  {process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}
                </code>
                . Start it with <code className="rounded bg-elevated px-1 py-0.5 text-xs">make dev-backend</code>.
              </p>
            </div>
          </Card>
        )}

        {/* KPI row */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Total invoices"
            value={stats.totalInvoices.toLocaleString("en-IN")}
            rawValue={stats.totalInvoices}
            icon={FileText}
            loading={invoicesQuery.isLoading}
            delay={0}
          />
          <StatTile
            label="GST tracked"
            value={formatCompactCurrency(stats.totalTax)}
            icon={ReceiptText}
            loading={invoicesQuery.isLoading}
            sparkline={trendSparkline}
            delay={60}
          />
          <StatTile
            label="Pending review"
            value={stats.pendingReview.toLocaleString("en-IN")}
            rawValue={stats.pendingReview}
            icon={Clock}
            loading={invoicesQuery.isLoading}
            tone={stats.pendingReview > 0 ? "warning" : "neutral"}
            delay={120}
          />
          <StatTile
            label="Critical issues"
            value={stats.criticalIssues.toLocaleString("en-IN")}
            rawValue={stats.criticalIssues}
            icon={ShieldAlert}
            loading={issuesQuery.isLoading}
            tone={stats.criticalIssues > 0 ? "critical" : "neutral"}
            delay={180}
          />
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <ChartCard
            className="lg:col-span-2"
            title="GST by month"
            subtitle="Total tax across all recorded invoices"
            loading={invoicesQuery.isLoading}
            isEmpty={trend.length === 0}
            emptyMessage="No dated invoices yet."
            columns={[
              { key: "period", label: "Period" },
              { key: "amount", label: "GST", align: "right" },
            ]}
            rows={trend.map((t) => ({ period: t.period, amount: formatCurrency(t.value) }))}
          >
            <GstTrendChart data={trend} />
          </ChartCard>

          <ChartCard
            title="Tax component split"
            subtitle="CGST / SGST / IGST / CESS"
            loading={invoicesQuery.isLoading}
            isEmpty={taxSplit.length === 0}
            emptyMessage="No tax components recorded."
            columns={[
              { key: "label", label: "Component" },
              { key: "amount", label: "Amount", align: "right" },
            ]}
            rows={taxSplit.map((t) => ({ label: t.label, amount: formatCurrency(t.value) }))}
          >
            <BreakdownBarChart data={taxSplit} formatter={formatCompactCurrency} />
          </ChartCard>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartCard
            title="Compliance issues by severity"
            subtitle="Open issues across all invoices"
            loading={issuesQuery.isLoading}
            isEmpty={issuesBySeverity.length === 0}
            emptyMessage="No compliance issues found."
            columns={[
              { key: "label", label: "Severity" },
              { key: "count", label: "Issues", align: "right" },
            ]}
            rows={issuesBySeverity.map((s) => ({ label: s.label, count: s.value }))}
          >
            <BreakdownBarChart data={issuesBySeverity} />
          </ChartCard>

          {/* Recent invoices */}
          <Card interactive className="flex flex-col">
            <div className="flex items-center justify-between p-5 pb-3">
              <div>
                <h3 className="text-sm font-medium text-foreground">Recent invoices</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">Latest uploads</p>
              </div>
              <Link
                href="/invoices"
                className="flex items-center gap-1 text-xs font-medium text-primary transition-opacity hover:opacity-80"
              >
                View all <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            <div className="flex flex-col gap-1.5 px-5 pb-5">
              {invoicesQuery.isLoading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-11 w-full" />
                ))}

              {!invoicesQuery.isLoading && invoices.length === 0 && (
                <div className="flex h-[180px] items-center justify-center rounded-md border border-dashed border-border">
                  <p className="text-sm text-muted-foreground">No invoices uploaded yet.</p>
                </div>
              )}

              {invoices.slice(0, 5).map((inv) => (
                <Link
                  key={inv.id}
                  href={`/invoices/${inv.id}`}
                  className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2.5 text-sm transition-all duration-200 hover:border-border-strong hover:bg-elevated"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">
                      {inv.invoice_number ?? `${inv.id.slice(0, 8)}…`}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {inv.supplier_name ?? inv.buyer_name ?? "Unknown party"}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="tabular-nums text-muted-foreground">
                      {formatCompactCurrency(inv.grand_total)}
                    </span>
                    <Badge variant={STATUS_VARIANT[inv.status] ?? "outline"}>
                      {titleCase(inv.status)}
                    </Badge>
                  </div>
                </Link>
              ))}
            </div>
          </Card>
        </div>
      </main>
    </div>
  );
}
