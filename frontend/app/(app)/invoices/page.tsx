"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, Search, FileText, ArrowRight } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SkeletonTableRows } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { cn, formatCurrency, titleCase } from "@/lib/utils";

interface Invoice {
  id: string;
  direction: string;
  status: string;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  buyer_name: string | null;
  grand_total: string | null;
}

const STATUS_VARIANT: Record<string, "good" | "warning" | "critical" | "outline"> = {
  extracted: "good",
  validated: "good",
  approved: "good",
  processing: "warning",
  uploaded: "warning",
  needs_review: "warning",
  failed: "critical",
  rejected: "critical",
};

const PENDING_STATUSES = new Set(["processing", "uploaded"]);

export default function InvoicesPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [direction, setDirection] = useState("purchase");

  const invoices = useQuery({
    queryKey: ["invoices"],
    queryFn: async () => (await apiClient.get<Invoice[]>("/invoices")).data,
    retry: false,
    // Extraction runs in the background after upload — keep refetching while
    // anything is still processing so the row flips to "Extracted" on its own.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((i) => PENDING_STATUSES.has(i.status)) ? 3000 : false,
  });

  const filtered = useMemo(() => {
    const rows = invoices.data ?? [];
    const term = search.trim().toLowerCase();
    return rows.filter((inv) => {
      const matchesStatus = statusFilter === "all" || inv.status === statusFilter;
      const matchesTerm =
        !term ||
        [inv.invoice_number, inv.supplier_name, inv.buyer_name]
          .filter(Boolean)
          .some((v) => v!.toLowerCase().includes(term));
      return matchesStatus && matchesTerm;
    });
  }, [invoices.data, search, statusFilter]);

  const statuses = useMemo(
    () => [...new Set((invoices.data ?? []).map((i) => i.status))].sort(),
    [invoices.data]
  );

  async function uploadFile(file: File) {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("direction", direction);
      await apiClient.post("/invoices/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(
        "Invoice uploaded",
        `${file.name} is being read now — the row updates automatically when extraction finishes.`
      );
    } catch (err) {
      toast.error("Upload failed", getApiErrorMessage(err, "The invoice could not be processed."));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await queryClient.invalidateQueries({ queryKey: ["invoices"] });
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["invoices"] }), 2500);
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Invoices</h1>
          <p className="text-xs text-muted-foreground">
            OCR extraction, deterministic GST validation and compliance checks
          </p>
        </div>
        <Select
          value={direction}
          onChange={(e) => setDirection(e.target.value)}
          className="h-9 text-xs"
          aria-label="Invoice direction for new uploads"
        >
          <option value="purchase">Upload as purchase</option>
          <option value="sales">Upload as sales</option>
        </Select>
      </header>

      <main className="flex-1 space-y-5 p-6">
        {/* Drop zone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) uploadFile(file);
          }}
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-8 text-center",
            "transition-all duration-300 ease-out",
            // recessed well at rest, lifts toward the viewer while dragging
            dragging
              ? "-translate-y-1 scale-[1.01] border-primary bg-primary-wash shadow-[var(--elev-3),var(--edge-top-strong)]"
              : "border-border bg-elevated/40 shadow-[inset_0_2px_8px_rgba(0,0,0,0.28)] hover:border-border-strong hover:bg-elevated"
          )}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.tiff"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) uploadFile(file);
            }}
          />
          <Upload
            className={cn(
              "h-5 w-5 transition-transform duration-200",
              dragging ? "scale-110 text-primary" : "text-muted-foreground"
            )}
          />
          <p className="text-sm font-medium">
            {uploading ? "Uploading…" : "Drop an invoice here, or click to browse"}
          </p>
          <p className="text-xs text-muted-foreground">
            PDF, PNG, JPG or TIFF · up to 25MB · OCR + AI extraction runs in the background
          </p>
        </div>

        {/* Filter row — one row above everything it scopes */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search invoice number or party…"
              className="pl-9"
            />
          </div>
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All statuses</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </Select>
          <span className="text-xs text-muted-foreground">
            {filtered.length} of {invoices.data?.length ?? 0}
          </span>
        </div>

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-elevated text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Invoice #</th>
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Direction</th>
                  <th className="px-4 py-3 font-medium">Party</th>
                  <th className="px-4 py-3 text-right font-medium">Total</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {invoices.isLoading && <SkeletonTableRows rows={6} cols={7} />}

                {!invoices.isLoading &&
                  filtered.map((inv) => (
                    <tr
                      key={inv.id}
                      className="group border-b border-border transition-colors last:border-0 hover:bg-elevated"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/invoices/${inv.id}`}
                          className="font-medium text-primary transition-opacity hover:opacity-80"
                        >
                          {inv.invoice_number ?? `${inv.id.slice(0, 8)}…`}
                        </Link>
                      </td>
                      <td className="px-4 py-3 tabular-nums text-muted-foreground">
                        {inv.invoice_date ?? "—"}
                      </td>
                      <td className="px-4 py-3 capitalize text-secondary">{inv.direction}</td>
                      <td className="max-w-[220px] truncate px-4 py-3 text-secondary">
                        {inv.supplier_name ?? inv.buyer_name ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {formatCurrency(inv.grand_total)}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={STATUS_VARIANT[inv.status] ?? "outline"}>
                          {titleCase(inv.status)}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Link href={`/invoices/${inv.id}`} aria-label="Open invoice">
                          <ArrowRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                        </Link>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          {!invoices.isLoading && filtered.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-14">
              <FileText className="h-6 w-6 text-muted-foreground" />
              <p className="text-sm font-medium">
                {invoices.data?.length ? "No invoices match your filters" : "No invoices yet"}
              </p>
              <p className="text-xs text-muted-foreground">
                {invoices.data?.length
                  ? "Try clearing the search or status filter."
                  : "Drop a PDF or scanned invoice above to get started."}
              </p>
              {!!invoices.data?.length && (
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-2"
                  onClick={() => {
                    setSearch("");
                    setStatusFilter("all");
                  }}
                >
                  Clear filters
                </Button>
              )}
            </div>
          )}
        </Card>
      </main>
    </div>
  );
}
