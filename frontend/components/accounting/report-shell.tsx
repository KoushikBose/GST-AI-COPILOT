"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";

/**
 * Shared chrome for the Trial Balance / P&L / Balance Sheet pages: a title,
 * an as-on (or date-range) picker, and a CSV export button that hits
 * `/accounting/reports/{type}/export`.
 */
export function ReportShell({
  title,
  subtitle,
  reportType,
  mode,
  value,
  onChange,
  children,
}: {
  title: string;
  subtitle: string;
  reportType: "trial-balance" | "profit-loss" | "balance-sheet";
  mode: "as-on" | "range";
  value: { asOn?: string; from?: string; to?: string };
  onChange: (v: { asOn?: string; from?: string; to?: string }) => void;
  children: React.ReactNode;
}) {
  const [exporting, setExporting] = useState(false);

  async function exportCsv() {
    setExporting(true);
    try {
      const params =
        mode === "as-on"
          ? { as_on: value.asOn }
          : { date_from: value.from, date_to: value.to };
      const res = await apiClient.get(`/accounting/reports/${reportType}/export`, {
        params,
        responseType: "blob",
      });
      const url = URL.createObjectURL(res.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${reportType}.csv`;
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
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">{title}</h1>
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        </div>
        <div className="flex items-end gap-2">
          {mode === "as-on" ? (
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              As on
              <Input
                type="date"
                value={value.asOn ?? ""}
                onChange={(e) => onChange({ asOn: e.target.value })}
                className="h-9 w-40"
              />
            </label>
          ) : (
            <>
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                From
                <Input
                  type="date"
                  value={value.from ?? ""}
                  onChange={(e) => onChange({ ...value, from: e.target.value })}
                  className="h-9 w-40"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                To
                <Input
                  type="date"
                  value={value.to ?? ""}
                  onChange={(e) => onChange({ ...value, to: e.target.value })}
                  className="h-9 w-40"
                />
              </label>
            </>
          )}
          <Button variant="outline" size="sm" onClick={exportCsv} loading={exporting}>
            {!exporting && <Download className="h-3.5 w-3.5" />}
            Export CSV
          </Button>
        </div>
      </header>
      <main className="flex-1 space-y-5 p-6">{children}</main>
    </div>
  );
}
