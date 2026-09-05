"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, ArrowRight, BookText } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { titleCase } from "@/lib/utils";

interface Group {
  id: string;
  name: string;
  nature: string;
  classification: string;
}
interface Ledger {
  id: string;
  name: string;
  group_id: string;
  group_name: string;
  nature: string;
  opening_balance: string;
  opening_side: string;
  is_system: boolean;
}

const NATURE_VARIANT: Record<string, "good" | "warning" | "serious" | "outline"> = {
  asset: "good",
  liability: "warning",
  income: "serious",
  expense: "outline",
};

export default function LedgersPage() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [groupId, setGroupId] = useState("");
  const [opening, setOpening] = useState("0");
  const [side, setSide] = useState("dr");
  const [saving, setSaving] = useState(false);

  const groups = useQuery({
    queryKey: ["acc", "groups"],
    queryFn: async () => (await apiClient.get<Group[]>("/accounting/groups")).data,
    retry: false,
  });
  const ledgers = useQuery({
    queryKey: ["acc", "ledgers"],
    queryFn: async () => (await apiClient.get<Ledger[]>("/accounting/ledgers")).data,
    retry: false,
  });

  const grouped = useMemo(() => {
    const map = new Map<string, Ledger[]>();
    for (const l of ledgers.data ?? []) {
      const arr = map.get(l.group_name) ?? [];
      arr.push(l);
      map.set(l.group_name, arr);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [ledgers.data]);

  async function create() {
    if (!name.trim() || !groupId) {
      toast.warning("Name and group are required");
      return;
    }
    setSaving(true);
    try {
      await apiClient.post("/accounting/ledgers", {
        name,
        group_id: groupId,
        opening_balance: opening || "0",
        opening_side: side,
      });
      await queryClient.invalidateQueries({ queryKey: ["acc", "ledgers"] });
      toast.success("Ledger created", name);
      setName("");
      setOpening("0");
      setOpen(false);
    } catch (err) {
      toast.error("Couldn't create ledger", getApiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Ledgers</h1>
          <p className="text-xs text-muted-foreground">Chart of accounts · grouped by nature</p>
        </div>
        <Button size="sm" onClick={() => setOpen((v) => !v)}>
          <Plus className="h-3.5 w-3.5" />
          New ledger
        </Button>
      </header>

      <main className="flex-1 space-y-5 p-6">
        {open && (
          <Card className="grid grid-cols-1 gap-3 p-5 sm:grid-cols-2 lg:grid-cols-5">
            <Input placeholder="Ledger name" value={name} onChange={(e) => setName(e.target.value)} />
            <Select value={groupId} onChange={(e) => setGroupId(e.target.value)}>
              <option value="">Select group…</option>
              {(groups.data ?? []).map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </Select>
            <Input
              placeholder="Opening balance"
              value={opening}
              onChange={(e) => setOpening(e.target.value)}
            />
            <Select value={side} onChange={(e) => setSide(e.target.value)}>
              <option value="dr">Debit</option>
              <option value="cr">Credit</option>
            </Select>
            <Button onClick={create} loading={saving}>
              Create
            </Button>
          </Card>
        )}

        {ledgers.isLoading &&
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32 w-full" />)}

        {grouped.map(([group, items]) => (
          <Card key={group} className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-border bg-elevated px-4 py-2.5">
              <span className="text-sm font-medium">{group}</span>
              <Badge variant={NATURE_VARIANT[items[0]?.nature ?? ""] ?? "outline"}>
                {titleCase(items[0]?.nature ?? "")}
              </Badge>
            </div>
            <ul className="divide-y divide-border">
              {items.map((l) => (
                <li key={l.id}>
                  <Link
                    href={`/accounting/ledgers/${l.id}`}
                    className="group flex items-center justify-between px-4 py-2.5 text-sm transition-colors hover:bg-elevated"
                  >
                    <span className="flex items-center gap-2">
                      <BookText className="h-3.5 w-3.5 text-muted-foreground" />
                      {l.name}
                      {l.is_system && (
                        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                          system
                        </span>
                      )}
                    </span>
                    <span className="flex items-center gap-3 text-muted-foreground">
                      {Number(l.opening_balance) > 0 && (
                        <span className="tabular-nums">
                          {l.opening_balance} {l.opening_side.toUpperCase()}
                        </span>
                      )}
                      <ArrowRight className="h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </main>
    </div>
  );
}
