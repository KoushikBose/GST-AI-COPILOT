"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  BookText,
  ScrollText,
  Scale,
  TrendingUp,
  Wallet,
  ArrowRight,
  ArrowDownCircle,
  ArrowUpCircle,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { StatTile } from "@/components/stat-tile";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatCompactCurrency, formatCurrency } from "@/lib/utils";

interface TrialBalance {
  total_debit: string;
  total_credit: string;
  is_balanced: boolean;
  rows: unknown[];
}
interface ProfitLoss {
  gross_profit: string;
  net_profit: string;
}
interface Outstanding {
  total: string;
  rows: { name: string; balance: string }[];
}

const TILES = [
  {
    href: "/accounting/vouchers",
    label: "Day Book & Vouchers",
    body: "Every journal entry, chronologically. Create manual vouchers.",
    icon: ScrollText,
  },
  {
    href: "/accounting/ledgers",
    label: "Ledgers",
    body: "Chart of accounts. Drill into any ledger's running balance.",
    icon: BookText,
  },
  {
    href: "/accounting/trial-balance",
    label: "Trial Balance",
    body: "Closing debit / credit balance of every ledger — must tie.",
    icon: Scale,
  },
  {
    href: "/accounting/profit-loss",
    label: "Profit & Loss A/c",
    body: "Trading and P&L account for the financial year.",
    icon: TrendingUp,
  },
  {
    href: "/accounting/balance-sheet",
    label: "Balance Sheet",
    body: "Assets against liabilities and capital, as on a date.",
    icon: Wallet,
  },
];

export default function AccountingGatewayPage() {
  const tb = useQuery({
    queryKey: ["acc", "trial-balance"],
    queryFn: async () =>
      (await apiClient.get<TrialBalance>("/accounting/reports/trial-balance")).data,
    retry: false,
  });
  const pnl = useQuery({
    queryKey: ["acc", "pnl"],
    queryFn: async () => (await apiClient.get<ProfitLoss>("/accounting/reports/profit-loss")).data,
    retry: false,
  });
  const receivable = useQuery({
    queryKey: ["acc", "outstanding", "receivable"],
    queryFn: async () =>
      (
        await apiClient.get<Outstanding>("/accounting/reports/outstanding", {
          params: { kind: "receivable" },
        })
      ).data,
    retry: false,
  });
  const payable = useQuery({
    queryKey: ["acc", "outstanding", "payable"],
    queryFn: async () =>
      (
        await apiClient.get<Outstanding>("/accounting/reports/outstanding", {
          params: { kind: "payable" },
        })
      ).data,
    retry: false,
  });

  const netProfit = Number(pnl.data?.net_profit ?? 0);

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Gateway of Accounts</h1>
          <p className="text-xs text-muted-foreground">
            Double-entry books · deterministic financial statements
          </p>
        </div>
        {tb.data && (
          <Badge variant={tb.data.is_balanced ? "good" : "critical"}>
            {tb.data.is_balanced ? "Books balanced" : "Trial balance mismatch"}
          </Badge>
        )}
      </header>

      <main className="flex-1 space-y-5 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Net profit (FY)"
            value={formatCompactCurrency(netProfit)}
            icon={TrendingUp}
            loading={pnl.isLoading}
            tone={netProfit < 0 ? "critical" : "neutral"}
          />
          <StatTile
            label="Trial balance total"
            value={formatCompactCurrency(tb.data?.total_debit ?? 0)}
            icon={Scale}
            loading={tb.isLoading}
          />
          <StatTile
            label="Receivables"
            value={formatCompactCurrency(receivable.data?.total ?? 0)}
            icon={ArrowDownCircle}
            loading={receivable.isLoading}
          />
          <StatTile
            label="Payables"
            value={formatCompactCurrency(payable.data?.total ?? 0)}
            icon={ArrowUpCircle}
            loading={payable.isLoading}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {TILES.map((t) => {
            const Icon = t.icon;
            return (
              <Link key={t.href} href={t.href}>
                <Card interactive className="flex h-full flex-col p-5">
                  <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary-wash text-primary">
                    <Icon className="h-4 w-4" />
                  </span>
                  <h3 className="mt-3 flex items-center gap-1.5 text-sm font-medium">
                    {t.label}
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                  </h3>
                  <p className="mt-1 text-xs text-muted-foreground">{t.body}</p>
                </Card>
              </Link>
            );
          })}
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {(
            [
              ["Top receivables", receivable.data, "/accounting/ledgers"],
              ["Top payables", payable.data, "/accounting/ledgers"],
            ] as const
          ).map(([title, data, href]) => (
            <Card key={title} interactive className="flex flex-col p-5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">{title}</h3>
                <Link href={href} className="text-xs font-medium text-primary hover:opacity-80">
                  Ledgers
                </Link>
              </div>
              <ul className="mt-3 divide-y divide-border text-sm">
                {(data?.rows ?? []).slice(0, 5).map((r) => (
                  <li key={r.name} className="flex items-center justify-between py-2">
                    <span className="truncate text-secondary">{r.name}</span>
                    <span className="tabular-nums">{formatCurrency(r.balance)}</span>
                  </li>
                ))}
                {(data?.rows ?? []).length === 0 && (
                  <li className="py-6 text-center text-xs text-muted-foreground">
                    Nothing outstanding.
                  </li>
                )}
              </ul>
            </Card>
          ))}
        </div>
      </main>
    </div>
  );
}
