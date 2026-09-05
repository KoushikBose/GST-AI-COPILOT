"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartTooltip } from "@/components/charts/chart-card";
import { formatCompactCurrency } from "@/lib/utils";

export interface TrendPoint {
  period: string;
  value: number;
}

/**
 * Single-series trend over time — one hue, no legend (the card title names
 * what's plotted). 2px line, 10% wash fill, hairline solid grid.
 */
export function GstTrendChart({ data }: { data: TrendPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis
          dataKey="period"
          tickLine={false}
          axisLine={{ stroke: "var(--baseline)" }}
          tickMargin={8}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={(v: number) => formatCompactCurrency(v)}
        />
        <Tooltip
          cursor={{ stroke: "var(--baseline)", strokeWidth: 1 }}
          content={<ChartTooltip formatter={(v) => formatCompactCurrency(v)} />}
        />
        <Area
          type="monotone"
          dataKey="value"
          name="GST"
          stroke="var(--series-1)"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="var(--series-1)"
          fillOpacity={0.1}
          activeDot={{
            r: 4,
            fill: "var(--series-1)",
            stroke: "var(--surface-1)",
            strokeWidth: 2,
          }}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
