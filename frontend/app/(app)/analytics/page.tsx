"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ReceiptText, ShieldCheck, Bot, CheckSquare, WifiOff } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { StatTile } from "@/components/stat-tile";
import { ChartCard } from "@/components/charts/chart-card";
import { MultiTrendChart } from "@/components/charts/multi-trend-chart";
import { BreakdownBarChart } from "@/components/charts/breakdown-bar-chart";
import { DonutChart } from "@/components/charts/donut-chart";
import { Card } from "@/components/ui/card";
import {
  formatCompactCurrency,
  formatCurrency,
  formatPeriod,
  titleCase,
} from "@/lib/utils";

interface Overview {
  total_invoices: number;
  total_tax: number;
  invoices_by_direction: Record<string, { count: number; taxable_value: number; total_tax: number }>;
  invoices_needing_review: number;
  avg_compliance_score: number;
  pending_approvals: number;
  agent_runs_by_status: Record<string, number>;
  itc_records_needing_review: number;
}

interface GstTrendPoint {
  period: string;
  outward_tax: number;
  inward_tax: number;
  net_tax: number;
  invoice_count: number;
}

interface ComplianceAnalytics {
  avg_score: number;
  total_checks: number;
  issues_by_severity: { severity: string; count: number }[];
  score_trend: { period: string; avg_score: number; checks: number }[];
}

interface AgentMetrics {
  total_runs: number;
  escalation_rate: number;
  by_status: Record<string, number>;
  by_intent: { intent: string; count: number; avg_latency_ms: number; avg_confidence: number }[];
  runs_trend: { period: string; runs: number; avg_latency_ms: number }[];
}

interface ITCSummary {
  by_status: { status: string; count: number; eligible_amount: number }[];
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: "var(--status-critical)",
  high: "var(--status-serious)",
  medium: "var(--status-warning)",
  low: "var(--status-good)",
  info: "var(--series-1)",
};

export default function AnalyticsPage() {
  const overview = useQuery({
    queryKey: ["analytics", "overview"],
    queryFn: async () => (await apiClient.get<Overview>("/analytics/overview")).data,
    retry: false,
  });
  const gstTrend = useQuery({
    queryKey: ["analytics", "gst-trend"],
    queryFn: async () =>
      (await apiClient.get<GstTrendPoint[]>("/analytics/gst-trend", { params: { months: 12 } })).data,
    retry: false,
  });
  const compliance = useQuery({
    queryKey: ["analytics", "compliance"],
    queryFn: async () => (await apiClient.get<ComplianceAnalytics>("/analytics/compliance")).data,
    retry: false,
  });
  const agents = useQuery({
    queryKey: ["analytics", "agents"],
    queryFn: async () => (await apiClient.get<AgentMetrics>("/analytics/agents")).data,
    retry: false,
  });
  const itc = useQuery({
    queryKey: ["analytics", "itc"],
    queryFn: async () => (await apiClient.get<ITCSummary>("/analytics/itc")).data,
    retry: false,
  });

  const offline = overview.isError && gstTrend.isError && agents.isError;

  const trendRows = useMemo(
    () =>
      (gstTrend.data ?? []).map((p) => ({
        period: formatPeriod(p.period),
        outward_tax: p.outward_tax,
        inward_tax: p.inward_tax,
        net_tax: p.net_tax,
      })),
    [gstTrend.data]
  );

  const severityRows = useMemo(
    () =>
      (compliance.data?.issues_by_severity ?? [])
        .slice()
        .sort(
          (a, b) =>
            ["critical", "high", "medium", "low", "info"].indexOf(a.severity) -
            ["critical", "high", "medium", "low", "info"].indexOf(b.severity)
        )
        .map((s) => ({
          label: titleCase(s.severity),
          value: s.count,
          color: SEVERITY_COLOR[s.severity],
        })),
    [compliance.data]
  );

  const complianceTrend = useMemo(
    () =>
      (compliance.data?.score_trend ?? []).map((p) => ({
        period: formatPeriod(p.period),
        avg_score: p.avg_score,
      })),
    [compliance.data]
  );

  const intentRows = useMemo(
    () =>
      (agents.data?.by_intent ?? []).map((r) => ({
        label: r.intent,
        value: r.count,
      })),
    [agents.data]
  );

  const latencyTrend = useMemo(
    () =>
      (agents.data?.runs_trend ?? []).map((p) => ({
        period: formatPeriod(p.period),
        avg_latency_ms: p.avg_latency_ms,
        runs: p.runs,
      })),
    [agents.data]
  );

  const itcRows = useMemo(
    () =>
      (itc.data?.by_status ?? []).map((s) => ({
        label: titleCase(s.status),
        value: s.eligible_amount || s.count,
      })),
    [itc.data]
  );

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Analytics</h1>
          <p className="text-xs text-muted-foreground">
            GST position, compliance exposure, ITC and agent performance over time
          </p>
        </div>
      </header>

      <main className="flex-1 space-y-5 p-6">
        {offline && (
          <Card className="flex items-start gap-3 border-critical/40 p-4">
            <WifiOff className="mt-0.5 h-4 w-4 shrink-0 text-critical" />
            <p className="text-sm text-muted-foreground">
              Analytics can&apos;t load until the API is reachable.
            </p>
          </Card>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="GST tracked"
            value={formatCompactCurrency(overview.data?.total_tax ?? 0)}
            icon={ReceiptText}
            loading={overview.isLoading}
            delay={0}
          />
          <StatTile
            label="Avg compliance score"
            value={`${overview.data?.avg_compliance_score ?? 0}/100`}
            rawValue={overview.data?.avg_compliance_score}
            icon={ShieldCheck}
            loading={compliance.isLoading}
            tone={(overview.data?.avg_compliance_score ?? 100) < 70 ? "warning" : "neutral"}
            delay={60}
          />
          <StatTile
            label="Agent runs"
            value={(agents.data?.total_runs ?? 0).toLocaleString("en-IN")}
            rawValue={agents.data?.total_runs}
            icon={Bot}
            loading={agents.isLoading}
            delay={120}
          />
          <StatTile
            label="Pending review"
            value={(overview.data?.pending_approvals ?? 0).toLocaleString("en-IN")}
            rawValue={overview.data?.pending_approvals}
            icon={CheckSquare}
            loading={overview.isLoading}
            tone={(overview.data?.pending_approvals ?? 0) > 0 ? "warning" : "neutral"}
            delay={180}
          />
        </div>

        <ChartCard
          title="Output tax vs. input tax credit"
          subtitle="Monthly outward tax, inward ITC and net position"
          loading={gstTrend.isLoading}
          isEmpty={trendRows.length === 0}
          emptyMessage="No dated invoices yet."
          columns={[
            { key: "period", label: "Period" },
            { key: "outward", label: "Outward", align: "right" },
            { key: "inward", label: "ITC", align: "right" },
            { key: "net", label: "Net", align: "right" },
          ]}
          rows={trendRows.map((t) => ({
            period: t.period,
            outward: formatCurrency(t.outward_tax),
            inward: formatCurrency(t.inward_tax),
            net: formatCurrency(t.net_tax),
          }))}
        >
          <MultiTrendChart
            data={trendRows}
            formatter={formatCompactCurrency}
            series={[
              { key: "outward_tax", name: "Outward tax", color: "var(--series-1)" },
              { key: "inward_tax", name: "Input tax credit", color: "var(--series-2)" },
              { key: "net_tax", name: "Net payable", color: "var(--series-3)" },
            ]}
          />
        </ChartCard>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartCard
            title="Compliance issues by severity"
            subtitle={`${compliance.data?.total_checks ?? 0} checks run`}
            loading={compliance.isLoading}
            isEmpty={severityRows.length === 0}
            emptyMessage="No compliance issues found."
            columns={[
              { key: "label", label: "Severity" },
              { key: "count", label: "Issues", align: "right" },
            ]}
            rows={severityRows.map((s) => ({ label: s.label, count: s.value }))}
          >
            <BreakdownBarChart data={severityRows} />
          </ChartCard>

          <ChartCard
            title="Compliance score trend"
            subtitle="Average score per month"
            loading={compliance.isLoading}
            isEmpty={complianceTrend.length === 0}
            emptyMessage="Not enough history yet."
            columns={[
              { key: "period", label: "Period" },
              { key: "score", label: "Avg score", align: "right" },
            ]}
            rows={complianceTrend.map((t) => ({ period: t.period, score: t.avg_score }))}
          >
            <MultiTrendChart
              data={complianceTrend}
              formatter={(v) => `${Math.round(v)}`}
              series={[{ key: "avg_score", name: "Avg score", color: "var(--series-1)" }]}
            />
          </ChartCard>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartCard
            title="Agent runs by intent"
            subtitle={`${Math.round((agents.data?.escalation_rate ?? 0) * 100)}% escalation rate`}
            loading={agents.isLoading}
            isEmpty={intentRows.length === 0}
            emptyMessage="No agent runs yet."
            columns={[
              { key: "label", label: "Intent" },
              { key: "count", label: "Runs", align: "right" },
            ]}
            rows={intentRows.map((r) => ({ label: r.label, count: r.value }))}
          >
            <BreakdownBarChart data={intentRows} />
          </ChartCard>

          <ChartCard
            title="Agent latency trend"
            subtitle="Average response time per month"
            loading={agents.isLoading}
            isEmpty={latencyTrend.length === 0}
            emptyMessage="No agent runs yet."
            columns={[
              { key: "period", label: "Period" },
              { key: "latency", label: "Avg latency", align: "right" },
              { key: "runs", label: "Runs", align: "right" },
            ]}
            rows={latencyTrend.map((t) => ({
              period: t.period,
              latency: `${(t.avg_latency_ms / 1000).toFixed(1)}s`,
              runs: t.runs,
            }))}
          >
            <MultiTrendChart
              data={latencyTrend}
              formatter={(v) => `${(v / 1000).toFixed(1)}s`}
              series={[{ key: "avg_latency_ms", name: "Avg latency", color: "var(--series-4)" }]}
            />
          </ChartCard>
        </div>

        <ChartCard
          title="Input tax credit by status"
          subtitle="Eligible amount pending human verification"
          loading={itc.isLoading}
          isEmpty={itcRows.length === 0}
          emptyMessage="No ITC assessments run yet."
          columns={[
            { key: "label", label: "Status" },
            { key: "amount", label: "Amount", align: "right" },
          ]}
          rows={itcRows.map((r) => ({ label: r.label, amount: formatCurrency(r.value) }))}
        >
          <DonutChart data={itcRows} formatter={formatCompactCurrency} />
        </ChartCard>
      </main>
    </div>
  );
}
