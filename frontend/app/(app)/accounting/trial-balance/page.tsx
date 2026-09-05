"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { ReportShell } from "@/components/accounting/report-shell";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/utils";

interface Row {
  ledger_id: string;
  name: string;
  group_name: string;
  debit: string;
  credit: string;
}
interface TrialBalance {
  as_on: string;
  rows: Row[];
  total_debit: string;
  total_credit: string;
  difference: string;
  is_balanced: boolean;
}

export default function TrialBalancePage() {
  const [asOn, setAsOn] = useState<string | undefined>(undefined);

  const q = useQuery({
    queryKey: ["acc", "trial-balance", asOn],
    queryFn: async () =>
      (
        await apiClient.get<TrialBalance>("/accounting/reports/trial-balance", {
          params: asOn ? { as_on: asOn } : {},
        })
      ).data,
    retry: false,
  });

  const data = q.data;

  return (
    <ReportShell
      title="Trial Balance"
      subtitle="Closing balance of every ledger — total debit must equal total credit"
      reportType="trial-balance"
      mode="as-on"
      value={{ asOn }}
      onChange={(v) => setAsOn(v.asOn || undefined)}
    >
      {q.isLoading && <Skeleton className="h-96 w-full" />}
      {data && (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <span className="text-xs text-muted-foreground">As on {data.as_on}</span>
            <Badge variant={data.is_balanced ? "good" : "critical"}>
              {data.is_balanced
                ? "Balanced"
                : `Difference ${formatCurrency(data.difference)}`}
            </Badge>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-elevated text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Ledger</th>
                  <th className="px-4 py-3 font-medium">Group</th>
                  <th className="px-4 py-3 text-right font-medium">Debit</th>
                  <th className="px-4 py-3 text-right font-medium">Credit</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.ledger_id} className="border-b border-border last:border-0">
                    <td className="px-4 py-2.5 font-medium">{r.name}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{r.group_name}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {Number(r.debit) ? formatCurrency(r.debit) : ""}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {Number(r.credit) ? formatCurrency(r.credit) : ""}
                    </td>
                  </tr>
                ))}
                {data.rows.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-10 text-center text-muted-foreground">
                      No ledger balances yet. Post an invoice or create a voucher.
                    </td>
                  </tr>
                )}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-border-strong font-semibold">
                  <td className="px-4 py-3" colSpan={2}>
                    Total
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {formatCurrency(data.total_debit)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {formatCurrency(data.total_credit)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </Card>
      )}
    </ReportShell>
  );
}
