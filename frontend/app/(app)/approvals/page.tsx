"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, Check, X, Pencil, AlertCircle } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { cn, titleCase } from "@/lib/utils";

interface Approval {
  id: string;
  approval_type: string;
  risk: string;
  status: string;
  entity_type: string;
  entity_id: string;
  ai_recommendation: Record<string, unknown>;
  confidence: string | null;
  decision_notes: string | null;
  created_at: string;
}

const RISK_VARIANT: Record<string, "critical" | "warning" | "good"> = {
  high: "critical",
  medium: "warning",
  low: "good",
};

const STATUS_VARIANT: Record<string, "good" | "warning" | "critical" | "outline"> = {
  pending: "warning",
  approved: "good",
  rejected: "critical",
  modified: "outline",
};

function DecisionButtons({ approval }: { approval: Approval }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);

  async function decide(decision: "approve" | "reject" | "modify") {
    let notes: string | null = null;
    if (decision !== "approve") {
      notes = window.prompt(
        decision === "reject" ? "Reason for rejecting?" : "Note on the modification?"
      );
      if (notes === null) return;
    }
    setBusy(decision);
    try {
      await apiClient.post(`/approvals/${approval.id}/decision`, {
        decision,
        notes,
        ...(decision === "modify" ? { final_payload: approval.ai_recommendation } : {}),
      });
      await queryClient.invalidateQueries({ queryKey: ["approvals"] });
      await queryClient.invalidateQueries({ queryKey: ["approval-counts"] });
      toast.success("Decision recorded", `Review task ${decision}d.`);
    } catch (err) {
      toast.error("Couldn't record decision", getApiErrorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  if (approval.status !== "pending") {
    return (
      <Badge variant={STATUS_VARIANT[approval.status] ?? "outline"}>
        {titleCase(approval.status)}
      </Badge>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" onClick={() => decide("approve")} loading={busy === "approve"}>
        {busy !== "approve" && <Check className="h-3.5 w-3.5" />}
        Approve
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={() => decide("modify")}
        loading={busy === "modify"}
      >
        {busy !== "modify" && <Pencil className="h-3.5 w-3.5" />}
        Modify
      </Button>
      <Button
        size="sm"
        variant="destructive"
        onClick={() => decide("reject")}
        loading={busy === "reject"}
      >
        {busy !== "reject" && <X className="h-3.5 w-3.5" />}
        Reject
      </Button>
    </div>
  );
}

export default function ApprovalsPage() {
  const [filter, setFilter] = useState<"pending" | "all">("pending");

  const approvals = useQuery({
    queryKey: ["approvals", filter],
    queryFn: async () =>
      (
        await apiClient.get<Approval[]>("/approvals", {
          params: filter === "pending" ? { status: "pending" } : {},
        })
      ).data,
    retry: false,
  });

  const rows = useMemo(() => approvals.data ?? [], [approvals.data]);

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Review queue</h1>
          <p className="text-xs text-muted-foreground">
            Human sign-off on high-impact or low-confidence AI outputs
          </p>
        </div>
        <div className="flex rounded-md border border-border p-0.5 text-xs">
          {(["pending", "all"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "rounded px-2.5 py-1 transition-colors",
                filter === f
                  ? "bg-primary-wash text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {titleCase(f)}
            </button>
          ))}
        </div>
      </header>

      <main className="flex-1 space-y-4 p-6">
        {approvals.isLoading &&
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32 w-full" />)}

        {approvals.isError && (
          <Card className="flex items-start gap-3 border-critical/40 p-4">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-critical" />
            <p className="text-sm text-muted-foreground">
              Couldn&apos;t load the review queue. {getApiErrorMessage(approvals.error)}
            </p>
          </Card>
        )}

        {!approvals.isLoading && rows.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-20">
            <CheckSquare className="h-7 w-7 text-muted-foreground" />
            <p className="text-sm font-medium">Nothing waiting for review</p>
            <p className="text-xs text-muted-foreground">
              Compliance exceptions, ITC assessments and return drafts land here.
            </p>
          </div>
        )}

        {rows.map((approval) => (
          <Card key={approval.id} interactive className="p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">
                    {titleCase(approval.approval_type)}
                  </span>
                  <Badge variant={RISK_VARIANT[approval.risk] ?? "outline"}>
                    {titleCase(approval.risk)} risk
                  </Badge>
                  {approval.confidence && (
                    <span className="text-xs text-muted-foreground">
                      Confidence {Math.round(parseFloat(approval.confidence) * 100)}%
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {titleCase(approval.entity_type)} · {approval.entity_id.slice(0, 8)}… ·{" "}
                  {new Date(approval.created_at).toLocaleString("en-IN")}
                </p>
              </div>
              <DecisionButtons approval={approval} />
            </div>

            <pre className="mt-3 max-h-48 overflow-auto rounded-md border border-border bg-elevated p-3 text-xs text-secondary">
              {JSON.stringify(approval.ai_recommendation, null, 2)}
            </pre>
            {approval.decision_notes && (
              <p className="mt-2 text-xs text-muted-foreground">
                Note: {approval.decision_notes}
              </p>
            )}
          </Card>
        ))}
      </main>
    </div>
  );
}
