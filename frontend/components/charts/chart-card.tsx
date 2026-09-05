"use client";

import { useState } from "react";
import { BarChart3, Table2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export interface TableColumn {
  key: string;
  label: string;
  align?: "left" | "right";
}

/**
 * Chart container with a built-in table-view twin.
 *
 * Every chart ships an equivalent table so no value is reachable only by
 * hovering — tooltips enhance, they never gate the data.
 */
export function ChartCard({
  title,
  subtitle,
  loading,
  isEmpty,
  emptyMessage = "No data yet.",
  columns,
  rows,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  loading?: boolean;
  isEmpty?: boolean;
  emptyMessage?: string;
  columns: TableColumn[];
  rows: Record<string, string | number>[];
  children: React.ReactNode;
  className?: string;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");

  return (
    <Card className={cn("flex flex-col", className)} interactive>
      <div className="flex items-start justify-between gap-4 p-5 pb-3">
        <div className="min-w-0">
          <h3 className="text-sm font-medium text-foreground">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <div className="flex shrink-0 rounded-md border border-border p-0.5">
          {(
            [
              { id: "chart" as const, icon: BarChart3, label: "Chart view" },
              { id: "table" as const, icon: Table2, label: "Table view" },
            ]
          ).map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setView(id)}
              aria-label={label}
              title={label}
              aria-pressed={view === id}
              className={cn(
                "rounded p-1.5 transition-colors duration-200",
                view === id
                  ? "bg-primary-wash text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
            </button>
          ))}
        </div>
      </div>

      <div className="px-5 pb-5">
        {loading ? (
          <Skeleton className="h-[220px] w-full" />
        ) : isEmpty ? (
          <div className="flex h-[220px] items-center justify-center rounded-md border border-dashed border-border">
            <p className="text-sm text-muted-foreground">{emptyMessage}</p>
          </div>
        ) : view === "chart" ? (
          <div className="animate-fade-in">{children}</div>
        ) : (
          <div className="animate-fade-in max-h-[220px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-card">
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                  {columns.map((c) => (
                    <th
                      key={c.key}
                      className={cn("py-2 font-medium", c.align === "right" && "text-right")}
                    >
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    {columns.map((c) => (
                      <td
                        key={c.key}
                        className={cn(
                          "py-2 text-secondary",
                          c.align === "right" && "text-right tabular-nums"
                        )}
                      >
                        {row[c.key]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}

/** Themed tooltip shared by every chart. */
export function ChartTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
  formatter?: (value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border-strong bg-card px-3 py-2 shadow-xl shadow-black/30">
      {label && <p className="mb-1 text-xs font-medium text-foreground">{label}</p>}
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2 text-xs">
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ background: entry.color }}
            aria-hidden
          />
          <span className="text-muted-foreground">{entry.name}</span>
          <span className="ml-auto pl-3 font-medium tabular-nums text-foreground">
            {formatter ? formatter(entry.value) : entry.value.toLocaleString("en-IN")}
          </span>
        </div>
      ))}
    </div>
  );
}
