"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, ScrollText, Check } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { cn, formatCurrency, titleCase } from "@/lib/utils";

interface Ledger {
  id: string;
  name: string;
  group_name: string;
}
interface Voucher {
  id: string;
  voucher_type: string;
  voucher_number: string;
  date: string;
  narration: string | null;
  total_amount: string;
  is_auto_generated: boolean;
}

interface EntryRow {
  ledger_id: string;
  side: "dr" | "cr";
  amount: string;
}

const VOUCHER_TYPES = [
  "journal",
  "payment",
  "receipt",
  "contra",
  "sales",
  "purchase",
  "debit_note",
  "credit_note",
];

const TYPE_VARIANT: Record<string, "good" | "warning" | "serious" | "outline"> = {
  sales: "good",
  receipt: "good",
  purchase: "warning",
  payment: "warning",
  journal: "outline",
  contra: "outline",
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function VouchersPage() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [vType, setVType] = useState("journal");
  const [date, setDate] = useState(today());
  const [narration, setNarration] = useState("");
  const [rows, setRows] = useState<EntryRow[]>([
    { ledger_id: "", side: "dr", amount: "" },
    { ledger_id: "", side: "cr", amount: "" },
  ]);
  const [saving, setSaving] = useState(false);
  const [typeFilter, setTypeFilter] = useState("all");

  const ledgers = useQuery({
    queryKey: ["acc", "ledgers"],
    queryFn: async () => (await apiClient.get<Ledger[]>("/accounting/ledgers")).data,
    retry: false,
  });
  const vouchers = useQuery({
    queryKey: ["acc", "vouchers", typeFilter],
    queryFn: async () =>
      (
        await apiClient.get<Voucher[]>("/accounting/vouchers", {
          params: typeFilter === "all" ? {} : { voucher_type: typeFilter },
        })
      ).data,
    retry: false,
  });

  const totals = useMemo(() => {
    let dr = 0;
    let cr = 0;
    for (const r of rows) {
      const amt = Number(r.amount) || 0;
      if (r.side === "dr") dr += amt;
      else cr += amt;
    }
    return { dr, cr, balanced: dr > 0 && Math.abs(dr - cr) < 0.01 };
  }, [rows]);

  function setRow(i: number, patch: Partial<EntryRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  async function submit() {
    if (!totals.balanced) {
      toast.warning("Voucher not balanced", "Total debit must equal total credit.");
      return;
    }
    if (rows.some((r) => !r.ledger_id || !Number(r.amount))) {
      toast.warning("Incomplete entry", "Every line needs a ledger and an amount.");
      return;
    }
    setSaving(true);
    try {
      await apiClient.post("/accounting/vouchers", {
        voucher_type: vType,
        date,
        narration: narration || null,
        entries: rows.map((r) => ({
          ledger_id: r.ledger_id,
          side: r.side,
          amount: r.amount,
        })),
      });
      await queryClient.invalidateQueries({ queryKey: ["acc"] });
      toast.success("Voucher posted");
      setRows([
        { ledger_id: "", side: "dr", amount: "" },
        { ledger_id: "", side: "cr", amount: "" },
      ]);
      setNarration("");
      setOpen(false);
    } catch (err) {
      toast.error("Couldn't post voucher", getApiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Day Book</h1>
          <p className="text-xs text-muted-foreground">Every voucher, newest first</p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="h-9 text-xs"
          >
            <option value="all">All types</option>
            {VOUCHER_TYPES.map((t) => (
              <option key={t} value={t}>
                {titleCase(t)}
              </option>
            ))}
          </Select>
          <Button size="sm" onClick={() => setOpen((v) => !v)}>
            <Plus className="h-3.5 w-3.5" />
            New voucher
          </Button>
        </div>
      </header>

      <main className="flex-1 space-y-5 p-6">
        {open && (
          <Card className="space-y-4 p-5">
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                Type
                <Select value={vType} onChange={(e) => setVType(e.target.value)} className="h-9">
                  {VOUCHER_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {titleCase(t)}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                Date
                <Input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="h-9 w-40"
                />
              </label>
              <label className="flex flex-1 flex-col gap-1 text-xs text-muted-foreground">
                Narration
                <Input
                  value={narration}
                  onChange={(e) => setNarration(e.target.value)}
                  placeholder="Being…"
                  className="h-9"
                />
              </label>
            </div>

            <div className="space-y-2">
              {rows.map((r, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <Select
                    value={r.ledger_id}
                    onChange={(e) => setRow(i, { ledger_id: e.target.value })}
                    className="h-9 min-w-[200px] flex-1"
                  >
                    <option value="">Select ledger…</option>
                    {(ledgers.data ?? []).map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </Select>
                  <Select
                    value={r.side}
                    onChange={(e) => setRow(i, { side: e.target.value as "dr" | "cr" })}
                    className="h-9 w-24"
                  >
                    <option value="dr">Debit</option>
                    <option value="cr">Credit</option>
                  </Select>
                  <Input
                    value={r.amount}
                    onChange={(e) => setRow(i, { amount: e.target.value })}
                    placeholder="0.00"
                    inputMode="decimal"
                    className="h-9 w-32 text-right tabular-nums"
                  />
                  <button
                    onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))}
                    disabled={rows.length <= 2}
                    className="text-muted-foreground transition-colors hover:text-critical disabled:opacity-30"
                    aria-label="Remove line"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  setRows((prev) => [...prev, { ledger_id: "", side: "dr", amount: "" }])
                }
              >
                <Plus className="h-3.5 w-3.5" />
                Add line
              </Button>
            </div>

            <div className="flex items-center justify-between border-t border-border pt-3 text-sm">
              <span
                className={cn(
                  "flex items-center gap-1.5 text-xs font-medium",
                  totals.balanced ? "text-good" : "text-warning"
                )}
              >
                {totals.balanced && <Check className="h-3.5 w-3.5" />}
                Dr {formatCurrency(totals.dr)} · Cr {formatCurrency(totals.cr)}
              </span>
              <Button onClick={submit} loading={saving} disabled={!totals.balanced}>
                Post voucher
              </Button>
            </div>
          </Card>
        )}

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-elevated text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Number</th>
                  <th className="px-4 py-3 font-medium">Narration</th>
                  <th className="px-4 py-3 text-right font-medium">Amount</th>
                </tr>
              </thead>
              <tbody>
                {vouchers.isLoading &&
                  Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={5} className="px-4 py-3">
                        <Skeleton className="h-4 w-full" />
                      </td>
                    </tr>
                  ))}
                {(vouchers.data ?? []).map((v) => (
                  <tr key={v.id} className="border-b border-border last:border-0 hover:bg-elevated">
                    <td className="px-4 py-2.5 tabular-nums text-muted-foreground">{v.date}</td>
                    <td className="px-4 py-2.5">
                      <Badge variant={TYPE_VARIANT[v.voucher_type] ?? "outline"}>
                        {titleCase(v.voucher_type)}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs">{v.voucher_number}</td>
                    <td className="max-w-[320px] truncate px-4 py-2.5 text-secondary">
                      {v.narration ?? "—"}
                      {v.is_auto_generated && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                          auto
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {formatCurrency(v.total_amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!vouchers.isLoading && (vouchers.data?.length ?? 0) === 0 && (
            <div className="flex flex-col items-center gap-2 py-14">
              <ScrollText className="h-6 w-6 text-muted-foreground" />
              <p className="text-sm font-medium">No vouchers yet</p>
              <p className="text-xs text-muted-foreground">
                Post an invoice to the books, or create a journal voucher above.
              </p>
            </div>
          )}
        </Card>
      </main>
    </div>
  );
}
