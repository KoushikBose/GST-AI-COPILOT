"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  GitCompare,
  Upload,
  RefreshCw,
  Download,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
} from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { cn, formatCurrency, titleCase } from "@/lib/utils";

type Source = "gstr2a" | "gstr2b";
type MatchStatus = "matched" | "mismatch" | "missing_in_return" | "missing_in_books";

interface ReconciliationRun {
  id: string;
  period: string;
  source: Source;
  book_invoice_count: number;
  return_record_count: number;
  matched_count: number;
  mismatch_count: number;
  missing_in_return_count: number;
  missing_in_books_count: number;
  itc_at_risk: string;
  potential_unclaimed_itc: string;
}

interface ReconciliationMatch {
  id: string;
  status: MatchStatus;
  supplier_gstin: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  book_taxable_value: string | null;
  book_tax: string | null;
  return_taxable_value: string | null;
  return_tax: string | null;
  itc_at_risk: string;
  reasons: string[];
}

const STATUS_VARIANT: Record<MatchStatus, "good" | "warning" | "critical" | "outline"> = {
  matched: "good",
  mismatch: "warning",
  missing_in_return: "critical",
  missing_in_books: "outline",
};

const STATUS_ICON: Record<MatchStatus, typeof CheckCircle2> = {
  matched: CheckCircle2,
  mismatch: AlertTriangle,
  missing_in_return: AlertCircle,
  missing_in_books: HelpCircle,
};

const STATUS_FILTERS: Array<{ label: string; value: MatchStatus | "all" }> = [
  { label: "All", value: "all" },
  { label: "Matched", value: "matched" },
  { label: "Mismatch", value: "mismatch" },
  { label: "Missing in 2A/2B", value: "missing_in_return" },
  { label: "Missing in books", value: "missing_in_books" },
];

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function RunDetail({ run }: { run: ReconciliationRun }) {
  const [statusFilter, setStatusFilter] = useState<MatchStatus | "all">("all");
  const [exporting, setExporting] = useState(false);

  const matches = useQuery({
    queryKey: ["reconciliation-matches", run.id, statusFilter],
    queryFn: async () =>
      (
        await apiClient.get<ReconciliationMatch[]>(`/reconciliation/${run.id}/matches`, {
          params: statusFilter === "all" ? undefined : { status: statusFilter },
        })
      ).data,
    retry: false,
  });

  async function exportCsv() {
    setExporting(true);
    try {
      const res = await apiClient.get(`/reconciliation/${run.id}/export`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(res.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `reconciliation_${run.period}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Exported", "The CSV download has started.");
    } catch (err) {
      toast.error("Export failed", getApiErrorMessage(err));
    } finally {
      setExporting(false);
    }
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <CardTitle>
          {run.period} · {run.source.toUpperCase()}
        </CardTitle>
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-xs text-muted-foreground">
            ITC at risk <span className="font-semibold text-critical">{formatCurrency(run.itc_at_risk)}</span>
            {" · "}
            Potential unclaimed{" "}
            <span className="font-semibold text-foreground">
              {formatCurrency(run.potential_unclaimed_itc)}
            </span>
          </p>
          <Button size="sm" onClick={exportCsv} loading={exporting}>
            {!exporting && <Download className="h-3.5 w-3.5" />}
            Export CSV
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                statusFilter === f.value
                  ? "border-primary bg-primary-wash text-primary"
                  : "border-border text-muted-foreground hover:border-border-strong"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="py-2 pr-4 font-medium">Status</th>
                <th className="py-2 pr-4 font-medium">Supplier GSTIN</th>
                <th className="py-2 pr-4 font-medium">Invoice #</th>
                <th className="py-2 pr-4 text-right font-medium">Books tax</th>
                <th className="py-2 pr-4 text-right font-medium">2A/2B tax</th>
                <th className="py-2 pr-4 text-right font-medium">ITC at risk</th>
                <th className="py-2 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody>
              {matches.isLoading &&
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={7} className="py-3">
                      <Skeleton className="h-4 w-full" />
                    </td>
                  </tr>
                ))}
              {(matches.data ?? []).map((m) => {
                const Icon = STATUS_ICON[m.status];
                return (
                  <tr key={m.id} className="border-b border-border last:border-0 align-top">
                    <td className="py-2.5 pr-4">
                      <Badge variant={STATUS_VARIANT[m.status]}>
                        <Icon className="h-3 w-3" />
                        {titleCase(m.status)}
                      </Badge>
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-xs">{m.supplier_gstin ?? "—"}</td>
                    <td className="py-2.5 pr-4">{m.invoice_number ?? "—"}</td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">
                      {m.book_tax !== null ? formatCurrency(m.book_tax) : "—"}
                    </td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">
                      {m.return_tax !== null ? formatCurrency(m.return_tax) : "—"}
                    </td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">
                      {Number(m.itc_at_risk) > 0 ? (
                        <span className="font-medium text-critical">
                          {formatCurrency(m.itc_at_risk)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2.5 max-w-xs text-xs text-muted-foreground">
                      {m.reasons.join(" ") || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!matches.isLoading && (matches.data ?? []).length === 0 && (
            <div className="flex flex-col items-center gap-2 py-14">
              <GitCompare className="h-6 w-6 text-muted-foreground" />
              <p className="text-sm font-medium">No rows for this filter</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function ReconciliationPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [uploadPeriod, setUploadPeriod] = useState(currentPeriod());
  const [uploadSource, setUploadSource] = useState<Source>("gstr2b");
  const [uploading, setUploading] = useState(false);

  const [runPeriod, setRunPeriod] = useState(currentPeriod());
  const [runSource, setRunSource] = useState<Source>("gstr2b");
  const [running, setRunning] = useState(false);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const runs = useQuery({
    queryKey: ["reconciliation-runs"],
    queryFn: async () => (await apiClient.get<ReconciliationRun[]>("/reconciliation")).data,
    retry: false,
  });

  const selectedRun = (runs.data ?? []).find((r) => r.id === selectedRunId) ?? null;

  function validPeriod(period: string): boolean {
    return /^\d{4}-\d{2}$/.test(period);
  }

  async function handleUpload() {
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      toast.warning("No file selected", "Choose the GSTR-2A/2B CSV export to upload.");
      return;
    }
    if (!validPeriod(uploadPeriod)) {
      toast.warning("Invalid period", "Use YYYY-MM, e.g. 2026-01.");
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("period", uploadPeriod);
      formData.append("source", uploadSource);
      const { data } = await apiClient.post<{ records_imported: number }>(
        "/reconciliation/upload",
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      toast.success(
        "Data imported",
        `${data.records_imported} row(s) imported for ${uploadPeriod}. Run reconciliation next.`
      );
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      toast.error("Upload failed", getApiErrorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleRun() {
    if (!validPeriod(runPeriod)) {
      toast.warning("Invalid period", "Use YYYY-MM, e.g. 2026-01.");
      return;
    }
    setRunning(true);
    try {
      const { data } = await apiClient.post<ReconciliationRun>("/reconciliation/run", {
        period: runPeriod,
        source: runSource,
      });
      await queryClient.invalidateQueries({ queryKey: ["reconciliation-runs"] });
      setSelectedRunId(data.id);
      toast.success("Reconciliation complete", `${runPeriod} · ${data.matched_count} matched.`);
    } catch (err) {
      toast.error("Reconciliation failed", getApiErrorMessage(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">GSTR-2A/2B reconciliation</h1>
          <p className="text-xs text-muted-foreground">
            Match purchase invoices against supplier-reported filings · CSV upload, no live GSTN connection
          </p>
        </div>
      </header>

      <main className="flex-1 space-y-5 p-6">
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="space-y-3 p-5">
            <p className="text-sm font-medium">1. Upload GSTR-2A/2B export</p>
            <p className="text-xs text-muted-foreground">
              Download the CSV from the GST portal, then upload it here. Columns needed:
              supplier GSTIN, invoice number, taxable value (igst/cgst/sgst/cess optional).
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-muted-foreground">Period</label>
                <Input
                  value={uploadPeriod}
                  onChange={(e) => setUploadPeriod(e.target.value)}
                  placeholder="YYYY-MM"
                  className="w-32"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-muted-foreground">Source</label>
                <Select
                  value={uploadSource}
                  onChange={(e) => setUploadSource(e.target.value as Source)}
                >
                  <option value="gstr2b">GSTR-2B</option>
                  <option value="gstr2a">GSTR-2A</option>
                </Select>
              </div>
              <input ref={fileInputRef} type="file" accept=".csv" className="text-xs" />
              <Button onClick={handleUpload} loading={uploading}>
                {!uploading && <Upload className="h-4 w-4" />}
                Upload
              </Button>
            </div>
          </Card>

          <Card className="space-y-3 p-5">
            <p className="text-sm font-medium">2. Run reconciliation</p>
            <p className="text-xs text-muted-foreground">
              Deterministically matches that period&apos;s purchase invoices against the
              uploaded data — re-running replaces the previous result for the period.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-muted-foreground">Period</label>
                <Input
                  value={runPeriod}
                  onChange={(e) => setRunPeriod(e.target.value)}
                  placeholder="YYYY-MM"
                  className="w-32"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-muted-foreground">Source</label>
                <Select value={runSource} onChange={(e) => setRunSource(e.target.value as Source)}>
                  <option value="gstr2b">GSTR-2B</option>
                  <option value="gstr2a">GSTR-2A</option>
                </Select>
              </div>
              <Button onClick={handleRun} loading={running}>
                {!running && <RefreshCw className="h-4 w-4" />}
                Run reconciliation
              </Button>
            </div>
          </Card>
        </div>

        {runs.isError && (
          <Card className="flex items-start gap-3 border-critical/40 p-4">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-critical" />
            <p className="text-sm text-muted-foreground">{getApiErrorMessage(runs.error)}</p>
          </Card>
        )}

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-elevated text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Period</th>
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 text-right font-medium">Matched</th>
                  <th className="px-4 py-3 text-right font-medium">Mismatch</th>
                  <th className="px-4 py-3 text-right font-medium">Missing in 2A/2B</th>
                  <th className="px-4 py-3 text-right font-medium">Missing in books</th>
                  <th className="px-4 py-3 text-right font-medium">ITC at risk</th>
                </tr>
              </thead>
              <tbody>
                {runs.isLoading &&
                  Array.from({ length: 2 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={7} className="px-4 py-3">
                        <Skeleton className="h-4 w-full" />
                      </td>
                    </tr>
                  ))}
                {(runs.data ?? []).map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => setSelectedRunId(r.id)}
                    className={cn(
                      "cursor-pointer border-b border-border transition-colors last:border-0 hover:bg-elevated",
                      selectedRunId === r.id && "bg-primary-wash"
                    )}
                  >
                    <td className="px-4 py-3 tabular-nums">{r.period}</td>
                    <td className="px-4 py-3 uppercase text-muted-foreground">{r.source}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-good">
                      {r.matched_count}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-warning">
                      {r.mismatch_count}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-critical">
                      {r.missing_in_return_count}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                      {r.missing_in_books_count}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-medium">
                      {formatCurrency(r.itc_at_risk)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!runs.isLoading && (runs.data ?? []).length === 0 && (
            <div className="flex flex-col items-center gap-2 py-14">
              <GitCompare className="h-6 w-6 text-muted-foreground" />
              <p className="text-sm font-medium">No reconciliations run yet</p>
              <p className="text-xs text-muted-foreground">
                Upload a GSTR-2A/2B export above, then run reconciliation for that period.
              </p>
            </div>
          )}
        </Card>

        {selectedRun && <RunDetail run={selectedRun} />}
      </main>
    </div>
  );
}
