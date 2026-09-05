"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { ChartTooltip } from "@/components/charts/chart-card";

export interface DonutDatum {
  label: string;
  value: number;
  color?: string;
}

const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

/**
 * Part-to-whole for a small number of categories (<= 5). Flat fills — an
 * exploded/3D pie distorts area perception. A labelled legend sits beside it.
 */
export function DonutChart({
  data,
  formatter = (v: number) => v.toLocaleString("en-IN"),
  height = 220,
}: {
  data: DonutDatum[];
  formatter?: (value: number) => string;
  height?: number;
}) {
  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row">
      <ResponsiveContainer width="55%" height={height} minWidth={160}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="label"
            innerRadius="58%"
            outerRadius="90%"
            paddingAngle={2}
            stroke="var(--surface-1)"
            strokeWidth={2}
          >
            {data.map((d, i) => (
              <Cell key={d.label} fill={d.color ?? SERIES[i % SERIES.length]} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip formatter={formatter} />} />
        </PieChart>
      </ResponsiveContainer>
      <ul className="flex flex-1 flex-col gap-1.5 text-xs">
        {data.map((d, i) => (
          <li key={d.label} className="flex items-center gap-2">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: d.color ?? SERIES[i % SERIES.length] }}
              aria-hidden
            />
            <span className="text-muted-foreground">{d.label}</span>
            <span className="ml-auto tabular-nums font-medium text-foreground">
              {formatter(d.value)}
            </span>
            <span className="w-10 text-right tabular-nums text-muted-foreground">
              {total ? Math.round((d.value / total) * 100) : 0}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
