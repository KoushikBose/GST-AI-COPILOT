"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { ReportShell } from "@/components/accounting/report-shell";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/utils";

interface Line {
  name: string;
  group_name: string;
  amount: string;
}
interface BalanceSheet {
  as_on: string;
  assets: Line[];
  liabilities: Line[];
  net_profit: string;
  total_assets: string;
  total_liabilities: string;
  difference: string;
  is_balanced: boolean;
}

function SideTable({
  heading,
  lines,
  extra,
  total,
}: {
  heading: string;
  lines: Line[];
  extra?: { name: string; amount: string } | null;
  total: string;
}) {
  return (
    <Card className="flex flex-col overflow-hidden">
      <div className="border-b border-border bg-elevated px-4 py-3 text-sm font-medium">
        {heading}
      </div>
      <table className="w-full flex-1 text-sm">
        <tbody>
          {lines.map((l) => (
            <tr key={l.name} className="border-b border-border last:border-0">
              <td className="px-4 py-2.5">
                <div className="text-secondary">{l.name}</div>
                <div className="text-xs text-muted-foreground">{l.group_name}</div>
              </td>
              <td className="px-4 py-2.5 text-right align-top tabular-nums">
                {formatCurrency(l.amount)}
              </td>
            </tr>
          ))}
          {extra && (
            <tr className="border-b border-border last:border-0">
              <td className="px-4 py-2.5 italic text-secondary">{extra.name}</td>
              <td className="px-4 py-2.5 text-right tabular-nums">
                {formatCurrency(extra.amount)}
              </td>
            </tr>
          )}
          {lines.length === 0 && !extra && (
            <tr>
              <td colSpan={2} className="py-8 text-center text-muted-foreground">
                Nothing here yet.
              </td>
            </tr>
          )}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-border-strong font-semibold">
            <td className="px-4 py-3">Total</td>
            <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(total)}</td>
          </tr>
        </tfoot>
      </table>
    </Card>
  );
}

export default function BalanceSheetPage() {
  const [asOn, setAsOn] = useState<string | undefined>(undefined);

  const q = useQuery({
    queryKey: ["acc", "balance-sheet", asOn],
    queryFn: async () =>
      (
        await apiClient.get<BalanceSheet>("/accounting/reports/balance-sheet", {
          params: asOn ? { as_on: asOn } : {},
        })
      ).data,
    retry: false,
  });

  const d = q.data;

  return (
    <ReportShell
      title="Balance Sheet"
      subtitle="Liabilities & capital against assets, as on a date"
      reportType="balance-sheet"
      mode="as-on"
      value={{ asOn }}
      onChange={(v) => setAsOn(v.asOn || undefined)}
    >
      {q.isLoading && <Skeleton className="h-96 w-full" />}
      {d && (
        <>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">As on {d.as_on}</span>
            <Badge variant={d.is_balanced ? "good" : "critical"}>
              {d.is_balanced ? "Balanced" : `Difference ${formatCurrency(d.difference)}`}
            </Badge>
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <SideTable
              heading="Liabilities"
              lines={d.liabilities}
              extra={{ name: "Profit & Loss A/c (current period)", amount: d.net_profit }}
              total={d.total_liabilities}
            />
            <SideTable heading="Assets" lines={d.assets} total={d.total_assets} />
          </div>
        </>
      )}
    </ReportShell>
  );
}
