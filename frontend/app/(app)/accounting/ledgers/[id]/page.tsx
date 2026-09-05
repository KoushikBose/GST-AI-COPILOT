"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, AlertCircle } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency, titleCase } from "@/lib/utils";

interface Txn {
  date: string;
  voucher_type: string;
  voucher_number: string;
  narration: string | null;
  debit: string;
  credit: string;
  balance: string;
  balance_side: string;
}
interface Statement {
  ledger_name: string;
  opening_balance: string;
  opening_side: string;
  closing_balance: string;
  closing_side: string;
  transactions: Txn[];
}

export default function LedgerStatementPage() {
  const params = useParams<{ id: string }>();

  const q = useQuery({
    queryKey: ["acc", "ledger-statement", params.id],
    queryFn: async () =>
      (await apiClient.get<Statement>(`/accounting/ledgers/${params.id}/statement`)).data,
    retry: false,
  });

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-border px-6">
        <Link
          href="/accounting/ledgers"
          className="text-muted-foreground hover:text-foreground"
          aria-label="Back to ledgers"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold">
            {q.data?.ledger_name ?? "Ledger"}
          </h1>
          <p className="text-xs text-muted-foreground">Ledger account · running balance</p>
        </div>
      </header>

      <main className="flex-1 space-y-5 p-6">
        {q.isLoading && <Skeleton className="h-96 w-full" />}
        {q.isError && (
          <Card className="flex items-center gap-3 border-critical/40 p-4 text-sm">
            <AlertCircle className="h-4 w-4 text-critical" />
            {getApiErrorMessage(q.error)}
            <Link href="/accounting/ledgers" className="ml-auto">
              <Button variant="outline" size="sm">
                Back
              </Button>
            </Link>
          </Card>
        )}
        {q.data && (
          <>
            <div className="flex flex-wrap gap-3">
              <Card className="flex-1 p-4">
                <p className="text-xs text-muted-foreground">Opening balance</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {formatCurrency(q.data.opening_balance)}{" "}
                  <span className="text-xs text-muted-foreground">
                    {q.data.opening_side.toUpperCase()}
                  </span>
                </p>
              </Card>
              <Card className="flex-1 p-4">
                <p className="text-xs text-muted-foreground">Closing balance</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {formatCurrency(q.data.closing_balance)}{" "}
                  <span className="text-xs text-muted-foreground">
                    {q.data.closing_side.toUpperCase()}
                  </span>
                </p>
              </Card>
            </div>

            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-border bg-elevated text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 font-medium">Date</th>
                      <th className="px-4 py-3 font-medium">Voucher</th>
                      <th className="px-4 py-3 font-medium">Particulars</th>
                      <th className="px-4 py-3 text-right font-medium">Debit</th>
                      <th className="px-4 py-3 text-right font-medium">Credit</th>
                      <th className="px-4 py-3 text-right font-medium">Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.data.transactions.map((t, i) => (
                      <tr key={i} className="border-b border-border last:border-0">
                        <td className="px-4 py-2.5 tabular-nums text-muted-foreground">{t.date}</td>
                        <td className="px-4 py-2.5">
                          <Badge variant="outline">{titleCase(t.voucher_type)}</Badge>{" "}
                          <span className="ml-1 font-mono text-xs text-muted-foreground">
                            {t.voucher_number}
                          </span>
                        </td>
                        <td className="max-w-[280px] truncate px-4 py-2.5 text-secondary">
                          {t.narration ?? "—"}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums">
                          {t.debit ? formatCurrency(t.debit) : ""}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums">
                          {t.credit ? formatCurrency(t.credit) : ""}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums">
                          {formatCurrency(t.balance)} {t.balance_side.toUpperCase()}
                        </td>
                      </tr>
                    ))}
                    {q.data.transactions.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-10 text-center text-muted-foreground">
                          No transactions in this period.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}
