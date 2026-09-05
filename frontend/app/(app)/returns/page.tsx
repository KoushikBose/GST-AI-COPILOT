"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Download, Send, RefreshCw, AlertCircle } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { cn, formatCurrency, titleCase } from "@/lib/utils";

interface ReturnSummary {
  id: string;
  return_type: "gstr1" | "gstr3b";
  period: string;
  status: string;
  invoice_count: number;
  total_taxable_value: string;
  total_tax: string;
}

interface ReturnDetail extends ReturnSummary {
  summary: Record<string, any>;
  rules_version: string;
  review_notes: string | null;
}

const STATUS_VARIANT: Record<string, "good" | "warning" | "critical" | "outline"> = {
  generated: "outline",
  under_review: "warning",
  approved: "good",
  exported: "good",
  filed_externally: "good",
  draft: "outline",
};

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function TaxRow({ label, block }: { label: string; block: Record<string, string> }) {
  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-2 pr-4 text-secondary">{label}</td>
      <td className="py-2 pr-4 text-right tabular-nums">{formatCurrency(block.taxable_value)}</td>
      <td className="py-2 pr-4 text-right tabular-nums">{formatCurrency(block.igst)}</td>
      <td className="py-2 pr-4 text-right tabular-nums">{formatCurrency(block.cgst)}</td>
      <td className="py-2 pr-4 text-right tabular-nums">{formatCurrency(block.sgst)}</td>
      <td className="py-2 text-right tabular-nums font-medium">{formatCurrency(block.total_tax)}</td>
    </tr>
  );
}

function ReturnDetailView({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);

  const detail = useQuery({
    queryKey: ["return", id],
    queryFn: async () => (await apiClient.get<ReturnDetail>(`/returns/${id}`)).data,
    retry: false,
  });

  async function submit() {
    setBusy("submit");
    try {
      await apiClient.post(`/returns/${id}/submit`);
      await queryClient.invalidateQueries({ queryKey: ["returns"] });
      await queryClient.invalidateQueries({ queryKey: ["return", id] });
      toast.success("Submitted for review", "A reviewer must approve it in the review queue.");
    } catch (err) {
      toast.error("Submit failed", getApiErrorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function exportCsv() {
    setBusy("export");
    try {
      const res = await apiClient.get(`/returns/${id}/export`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${detail.data?.return_type}_${detail.data?.period}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      await queryClient.invalidateQueries({ queryKey: ["returns"] });
      toast.success("Exported", "The CSV download has started.");
    } catch (err) {
      toast.error("Export failed", getApiErrorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  if (detail.isLoading) return <Skeleton className="h-64 w-full" />;
  if (detail.isError || !detail.data)
    return <p className="text-sm text-muted-foreground">Couldn&apos;t load this return.</p>;

  const r = detail.data;
  const s = r.summary ?? {};

  return (
    <Card interactive>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>
          {r.return_type.toUpperCase()} · {r.period}
        </CardTitle>
        <div className="flex items-center gap-2">
          <Badge variant={STATUS_VARIANT[r.status] ?? "outline"}>{titleCase(r.status)}</Badge>
          {(r.status === "generated" || r.status === "draft") && (
            <Button size="sm" variant="outline" onClick={submit} loading={busy === "submit"}>
              {busy !== "submit" && <Send className="h-3.5 w-3.5" />}
              Submit for review
            </Button>
          )}
          <Button size="sm" onClick={exportCsv} loading={busy === "export"}>
            {busy !== "export" && <Download className="h-3.5 w-3.5" />}
            Export CSV
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {r.review_notes && (
          <p className="rounded-md border border-border bg-elevated p-2.5 text-xs text-muted-foreground">
            Reviewer note: {r.review_notes}
          </p>
        )}

        {r.return_type === "gstr3b" ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="py-2 pr-4 font-medium">Section</th>
                  <th className="py-2 pr-4 text-right font-medium">Taxable</th>
                  <th className="py-2 pr-4 text-right font-medium">IGST</th>
                  <th className="py-2 pr-4 text-right font-medium">CGST</th>
                  <th className="py-2 pr-4 text-right font-medium">SGST</th>
                  <th className="py-2 text-right font-medium">Total tax</th>
                </tr>
              </thead>
              <tbody>
                <TaxRow label="Outward taxable supplies" block={s.outward_taxable_supplies ?? {}} />
                <TaxRow label="Eligible ITC" block={s.eligible_itc ?? {}} />
                <TaxRow label="Net tax payable" block={s.net_tax_payable ?? {}} />
              </tbody>
            </table>
          </div>
        ) : (
          <>
            <div>
              <p className="mb-2 font-medium">Rate-wise outward supplies</p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="py-2 pr-4 font-medium">Rate</th>
                      <th className="py-2 pr-4 text-right font-medium">Taxable</th>
                      <th className="py-2 pr-4 text-right font-medium">IGST</th>
                      <th className="py-2 pr-4 text-right font-medium">CGST</th>
                      <th className="py-2 pr-4 text-right font-medium">SGST</th>
                      <th className="py-2 text-right font-medium">Total tax</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(s.rate_wise ?? []).map((b: Record<string, string>) => (
                      <TaxRow key={b.gst_rate} label={`${b.gst_rate}%`} block={b} />
                    ))}
                    {(s.rate_wise ?? []).length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-muted-foreground">
                          No outward supplies recorded for this period.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              {(s.b2b ?? []).length} B2B counterpart{(s.b2b ?? []).length === 1 ? "y" : "ies"} ·{" "}
              {(s.b2c ?? []).length} B2C group(s)
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function ReturnsPage() {
  const queryClient = useQueryClient();
  const [returnType, setReturnType] = useState<"gstr1" | "gstr3b">("gstr1");
  const [period, setPeriod] = useState(currentPeriod());
  const [generating, setGenerating] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const returns = useQuery({
    queryKey: ["returns"],
    queryFn: async () => (await apiClient.get<ReturnSummary[]>("/returns")).data,
    retry: false,
  });

  const rows = useMemo(() => returns.data ?? [], [returns.data]);

  async function generate() {
    if (!/^\d{4}-\d{2}$/.test(period)) {
      toast.warning("Invalid period", "Use YYYY-MM, e.g. 2026-01.");
      return;
    }
    setGenerating(true);
    try {
      const { data } = await apiClient.post<ReturnDetail>("/returns/generate", {
        return_type: returnType,
        period,
      });
      await queryClient.invalidateQueries({ queryKey: ["returns"] });
      setSelected(data.id);
      toast.success("Return generated", `${returnType.toUpperCase()} for ${period} is ready.`);
    } catch (err) {
      toast.error("Generation failed", getApiErrorMessage(err));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Return preparation</h1>
          <p className="text-xs text-muted-foreground">
            Deterministic GSTR-1 / GSTR-3B drafts from your invoices · not a filing integration
          </p>
        </div>
      </header>

      <main className="flex-1 space-y-5 p-6">
        <Card className="flex flex-wrap items-end gap-3 p-5">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">Return</label>
            <Select
              value={returnType}
              onChange={(e) => setReturnType(e.target.value as "gstr1" | "gstr3b")}
            >
              <option value="gstr1">GSTR-1 (outward supplies)</option>
              <option value="gstr3b">GSTR-3B (monthly summary)</option>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">Period</label>
            <Input
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              placeholder="YYYY-MM"
              className="w-36"
            />
          </div>
          <Button onClick={generate} loading={generating}>
            {!generating && <RefreshCw className="h-4 w-4" />}
            Generate
          </Button>
        </Card>

        {returns.isError && (
          <Card className="flex items-start gap-3 border-critical/40 p-4">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-critical" />
            <p className="text-sm text-muted-foreground">{getApiErrorMessage(returns.error)}</p>
          </Card>
        )}

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-elevated text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Return</th>
                  <th className="px-4 py-3 font-medium">Period</th>
                  <th className="px-4 py-3 text-right font-medium">Invoices</th>
                  <th className="px-4 py-3 text-right font-medium">Taxable</th>
                  <th className="px-4 py-3 text-right font-medium">Tax</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {returns.isLoading &&
                  Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={6} className="px-4 py-3">
                        <Skeleton className="h-4 w-full" />
                      </td>
                    </tr>
                  ))}
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => setSelected(r.id)}
                    className={cn(
                      "cursor-pointer border-b border-border transition-colors last:border-0 hover:bg-elevated",
                      selected === r.id && "bg-primary-wash"
                    )}
                  >
                    <td className="px-4 py-3 font-medium">{r.return_type.toUpperCase()}</td>
                    <td className="px-4 py-3 tabular-nums text-muted-foreground">{r.period}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{r.invoice_count}</td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatCurrency(r.total_taxable_value)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatCurrency(r.total_tax)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={STATUS_VARIANT[r.status] ?? "outline"}>
                        {titleCase(r.status)}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!returns.isLoading && rows.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-14">
              <FileSpreadsheet className="h-6 w-6 text-muted-foreground" />
              <p className="text-sm font-medium">No returns prepared yet</p>
              <p className="text-xs text-muted-foreground">
                Generate one for a period above — it aggregates that month&apos;s invoices.
              </p>
            </div>
          )}
        </Card>

        {selected && <ReturnDetailView id={selected} />}
      </main>
    </div>
  );
}
