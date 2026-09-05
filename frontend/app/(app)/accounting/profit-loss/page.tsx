"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { ReportShell } from "@/components/accounting/report-shell";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatCurrency } from "@/lib/utils";

interface Line {
  name: string;
  group_name: string;
  amount: string;
}
interface PnL {
  date_from: string;
  date_to: string;
  direct_income: Line[];
  direct_expense: Line[];
  indirect_income: Line[];
  indirect_expense: Line[];
  gross_profit: string;
  net_profit: string;
}

function Section({ heading, lines }: { heading: string; lines: Line[] }) {
  if (lines.length === 0) return null;
  return (
    <>
      <tr className="bg-elevated/60">
        <td className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground" colSpan={2}>
          {heading}
        </td>
      </tr>
      {lines.map((l) => (
        <tr key={l.name} className="border-b border-border last:border-0">
          <td className="px-4 py-2 pl-6 text-secondary">{l.name}</td>
          <td className="px-4 py-2 text-right tabular-nums">{formatCurrency(l.amount)}</td>
        </tr>
      ))}
    </>
  );
}

export default function ProfitLossPage() {
  const [range, setRange] = useState<{ from?: string; to?: string }>({});

  const q = useQuery({
    queryKey: ["acc", "pnl", range.from, range.to],
    queryFn: async () =>
      (
        await apiClient.get<PnL>("/accounting/reports/profit-loss", {
          params: { date_from: range.from, date_to: range.to },
        })
      ).data,
    retry: false,
  });

  const d = q.data;
  const net = Number(d?.net_profit ?? 0);

  return (
    <ReportShell
      title="Profit & Loss A/c"
      subtitle="Trading and profit & loss account for the period"
      reportType="profit-loss"
      mode="range"
      value={range}
      onChange={(v) => setRange({ from: v.from, to: v.to })}
    >
      {q.isLoading && <Skeleton className="h-96 w-full" />}
      {d && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card className="overflow-hidden">
            <div className="border-b border-border bg-elevated px-4 py-3 text-sm font-medium">
              Income
            </div>
            <table className="w-full text-sm">
              <tbody>
                <Section heading="Direct income (Sales)" lines={d.direct_income} />
                <Section heading="Indirect income" lines={d.indirect_income} />
              </tbody>
            </table>
          </Card>

          <Card className="overflow-hidden">
            <div className="border-b border-border bg-elevated px-4 py-3 text-sm font-medium">
              Expenditure
            </div>
            <table className="w-full text-sm">
              <tbody>
                <Section heading="Direct expenses (Purchases)" lines={d.direct_expense} />
                <Section heading="Indirect expenses" lines={d.indirect_expense} />
              </tbody>
            </table>
          </Card>

          <Card className="p-5 lg:col-span-2">
            <div className="flex flex-wrap items-center justify-between gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Gross profit</p>
                <p className="text-lg font-semibold tabular-nums">
                  {formatCurrency(d.gross_profit)}
                </p>
              </div>
              <div className="text-right">
                <p className="text-muted-foreground">Net profit ({d.date_from} → {d.date_to})</p>
                <p
                  className={cn(
                    "text-2xl font-semibold tabular-nums",
                    net < 0 ? "text-critical" : "text-good"
                  )}
                >
                  {formatCurrency(d.net_profit)}
                </p>
              </div>
            </div>
          </Card>
        </div>
      )}
    </ReportShell>
  );
}
