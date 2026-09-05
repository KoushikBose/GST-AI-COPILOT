"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, ArrowLeft, AlertCircle, CheckCircle2, BookText } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { cn, formatCurrency, titleCase } from "@/lib/utils";

interface InvoiceItem {
  line_number: number;
  description: string | null;
  hsn_sac: string | null;
  taxable_value: string;
  gst_rate: string;
  cgst: string;
  sgst: string;
  igst: string;
  cess: string;
}

interface InvoiceDetail {
  id: string;
  status: string;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  supplier_gstin: string | null;
  buyer_name: string | null;
  buyer_gstin: string | null;
  place_of_supply: string | null;
  transaction_scope: string | null;
  taxable_value: string | null;
  total_tax: string | null;
  grand_total: string | null;
  ocr_confidence: string | null;
  items: InvoiceItem[];
}

interface ComplianceIssue {
  severity: string;
  rule_code: string;
  message: string;
  recommendation: string | null;
}

interface AnalysisResult {
  compliance: { score: number; passed_checks: number; total_checks: number; issues: ComplianceIssue[] };
  itc: {
    status: string;
    reasons: string[];
    missing_evidence: string[];
    confidence: string;
    eligible_amount: string | null;
  };
}

const SEVERITY_VARIANT: Record<string, "critical" | "serious" | "warning" | "good" | "outline"> = {
  critical: "critical",
  high: "serious",
  medium: "warning",
  low: "good",
  info: "outline",
};

/** Meter: fill carries severity, track is a recessive step of the same surface ramp. */
function ScoreMeter({ score }: { score: number }) {
  const tone =
    score >= 85 ? "var(--status-good)" : score >= 60 ? "var(--status-warning)" : "var(--status-critical)";

  return (
    <div className="flex items-center gap-3">
      <span className="text-2xl font-semibold leading-none" style={{ color: tone }}>
        {score}
        <span className="text-sm text-muted-foreground">/100</span>
      </span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-elevated">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ width: `${score}%`, background: tone }}
        />
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string | null | undefined;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border py-2 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("text-right", mono && "font-mono text-xs")}>{value || "—"}</span>
    </div>
  );
}

export default function InvoiceDetailPage() {
  const params = useParams<{ id: string }>();
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [posting, setPosting] = useState(false);

  const invoice = useQuery({
    queryKey: ["invoice", params.id],
    queryFn: async () => (await apiClient.get<InvoiceDetail>(`/invoices/${params.id}`)).data,
    retry: false,
    refetchInterval: (query) =>
      ["processing", "uploaded"].includes(query.state.data?.status ?? "") ? 3000 : false,
  });

  async function runAnalysis() {
    setAnalyzing(true);
    try {
      const { data } = await apiClient.post<AnalysisResult>(`/invoices/${params.id}/analyze`);
      setAnalysis(data);
      toast.success(
        "Analysis complete",
        `Compliance score ${data.compliance.score}/100 · ITC ${titleCase(data.itc.status)}`
      );
    } catch (err) {
      toast.error("Analysis failed", getApiErrorMessage(err));
    } finally {
      setAnalyzing(false);
    }
  }

  async function postToBooks() {
    setPosting(true);
    try {
      const { data } = await apiClient.post<{ voucher_number: string; voucher_type: string }>(
        `/accounting/invoices/${params.id}/post`
      );
      toast.success(
        "Posted to books",
        `${titleCase(data.voucher_type)} voucher ${data.voucher_number} created.`
      );
    } catch (err) {
      toast.error("Couldn't post to books", getApiErrorMessage(err));
    } finally {
      setPosting(false);
    }
  }

  if (invoice.isLoading) {
    return (
      <div className="flex-1 space-y-4 p-6">
        <Skeleton className="h-8 w-56" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card className="p-5">
            <SkeletonText lines={6} />
          </Card>
          <Card className="p-5">
            <SkeletonText lines={6} />
          </Card>
        </div>
      </div>
    );
  }

  if (invoice.isError || !invoice.data) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6">
        <AlertCircle className="h-6 w-6 text-critical" />
        <p className="text-sm font-medium">Invoice not found</p>
        <Link href="/invoices">
          <Button variant="outline" size="sm">
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to invoices
          </Button>
        </Link>
      </div>
    );
  }

  const inv = invoice.data;

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border px-6">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/invoices"
            className="text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Back to invoices"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold">
              {inv.invoice_number ?? "Invoice"}
            </h1>
            <p className="text-xs text-muted-foreground">{inv.invoice_date ?? "No date extracted"}</p>
          </div>
          <Badge variant="outline">{titleCase(inv.status)}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={postToBooks} loading={posting}>
            {!posting && <BookText className="h-4 w-4" />}
            {posting ? "Posting…" : "Post to books"}
          </Button>
          <Button onClick={runAnalysis} loading={analyzing}>
            {!analyzing && <ShieldCheck className="h-4 w-4" />}
            {analyzing ? "Analyzing…" : "Run compliance + ITC"}
          </Button>
        </div>
      </header>

      <main className="flex-1 space-y-5 p-6">
        {(inv.status === "processing" || inv.status === "uploaded") && (
          <Card className="flex items-center gap-3 border-warning/40 p-4 text-sm">
            <span className="flex gap-1">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-warning" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-warning" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-warning" />
            </span>
            <span className="text-muted-foreground">
              OCR and AI extraction are still running. This page refreshes automatically.
            </span>
          </Card>
        )}
        {inv.status === "failed" && (
          <Card className="flex items-center gap-3 border-critical/40 p-4 text-sm">
            <AlertCircle className="h-4 w-4 shrink-0 text-critical" />
            <span className="text-muted-foreground">
              Extraction failed for this invoice.
              {typeof (inv as { extracted_fields?: { error?: string } }).extracted_fields?.error ===
              "string"
                ? ` ${(inv as { extracted_fields?: { error?: string } }).extracted_fields!.error}`
                : " Check that the OCR engine and the LLM service are running, then re-upload."}
            </span>
          </Card>
        )}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card interactive className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Extracted details</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-x-8 text-sm sm:grid-cols-2">
              <div>
                <Row label="Supplier" value={inv.supplier_name} />
                <Row label="Supplier GSTIN" value={inv.supplier_gstin} mono />
                <Row label="Buyer" value={inv.buyer_name} />
                <Row label="Buyer GSTIN" value={inv.buyer_gstin} mono />
              </div>
              <div>
                <Row label="Place of supply" value={inv.place_of_supply} />
                <Row
                  label="Transaction scope"
                  value={inv.transaction_scope ? titleCase(inv.transaction_scope) : null}
                />
                <Row
                  label="OCR confidence"
                  value={
                    inv.ocr_confidence
                      ? `${Math.round(parseFloat(inv.ocr_confidence) * 100)}%`
                      : "Native text (no OCR)"
                  }
                />
                <Row label="Line items" value={String(inv.items.length)} />
              </div>
            </CardContent>
          </Card>

          <Card interactive>
            <CardHeader>
              <CardTitle>Tax summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-baseline justify-between">
                <span className="text-muted-foreground">Taxable value</span>
                <span className="tabular-nums">{formatCurrency(inv.taxable_value)}</span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-muted-foreground">Total tax</span>
                <span className="tabular-nums">{formatCurrency(inv.total_tax)}</span>
              </div>
              <div className="flex items-baseline justify-between border-t border-border pt-3">
                <span className="font-medium">Grand total</span>
                <span className="text-lg font-semibold">{formatCurrency(inv.grand_total)}</span>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card interactive>
          <CardHeader>
            <CardTitle>Line items</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Description</th>
                    <th className="py-2 pr-4 font-medium">HSN/SAC</th>
                    <th className="py-2 pr-4 text-right font-medium">Taxable</th>
                    <th className="py-2 pr-4 text-right font-medium">Rate</th>
                    <th className="py-2 pr-4 text-right font-medium">CGST</th>
                    <th className="py-2 pr-4 text-right font-medium">SGST</th>
                    <th className="py-2 text-right font-medium">IGST</th>
                  </tr>
                </thead>
                <tbody>
                  {inv.items.map((item) => (
                    <tr
                      key={item.line_number}
                      className="border-b border-border transition-colors last:border-0 hover:bg-elevated"
                    >
                      <td className="max-w-[240px] truncate py-2.5 pr-4">
                        {item.description ?? "—"}
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-xs text-muted-foreground">
                        {item.hsn_sac ?? "—"}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">
                        {formatCurrency(item.taxable_value)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-muted-foreground">
                        {item.gst_rate}%
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">
                        {formatCurrency(item.cgst)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">
                        {formatCurrency(item.sgst)}
                      </td>
                      <td className="py-2.5 text-right tabular-nums">
                        {formatCurrency(item.igst)}
                      </td>
                    </tr>
                  ))}
                  {inv.items.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-muted-foreground">
                        No line items were extracted from this invoice.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {analysis && (
          <div className="animate-fade-in-up grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card interactive>
              <CardHeader>
                <CardTitle>Compliance</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <ScoreMeter score={analysis.compliance.score} />
                <p className="text-xs text-muted-foreground">
                  {analysis.compliance.passed_checks} of {analysis.compliance.total_checks} checks
                  passed
                </p>

                {analysis.compliance.issues.length === 0 ? (
                  <div className="flex items-center gap-2 rounded-md border border-border p-3 text-sm">
                    <CheckCircle2 className="h-4 w-4 text-good" />
                    No compliance issues found.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {analysis.compliance.issues.map((issue, i) => (
                      <div
                        key={i}
                        className="rounded-md border border-border p-3 text-sm transition-colors hover:border-border-strong"
                      >
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <Badge variant={SEVERITY_VARIANT[issue.severity] ?? "outline"}>
                            {titleCase(issue.severity)}
                          </Badge>
                          <span className="font-mono text-[11px] text-muted-foreground">
                            {issue.rule_code}
                          </span>
                        </div>
                        <p className="text-secondary">{issue.message}</p>
                        {issue.recommendation && (
                          <p className="mt-1.5 text-xs text-muted-foreground">
                            {issue.recommendation}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card interactive>
              <CardHeader>
                <CardTitle>ITC assessment</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant={
                      analysis.itc.status === "eligible"
                        ? "good"
                        : analysis.itc.status === "ineligible"
                          ? "critical"
                          : "warning"
                    }
                  >
                    {titleCase(analysis.itc.status)}
                  </Badge>
                  {analysis.itc.eligible_amount && (
                    <span className="text-muted-foreground">
                      Potential credit:{" "}
                      <span className="tabular-nums text-foreground">
                        {formatCurrency(analysis.itc.eligible_amount)}
                      </span>
                    </span>
                  )}
                </div>

                <div>
                  <p className="mb-1.5 font-medium">Reasons</p>
                  <ul className="space-y-1 text-muted-foreground">
                    {analysis.itc.reasons.map((r, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-current" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>

                {analysis.itc.missing_evidence.length > 0 && (
                  <div>
                    <p className="mb-1.5 font-medium">Missing evidence</p>
                    <ul className="space-y-1 text-muted-foreground">
                      {analysis.itc.missing_evidence.map((r, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-current" />
                          {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}
