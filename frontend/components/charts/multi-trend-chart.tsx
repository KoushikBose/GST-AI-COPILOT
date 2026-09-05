"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartTooltip } from "@/components/charts/chart-card";

export interface MultiTrendSeries {
  key: string;
  name: string;
  color: string;
}

/**
 * Multi-series line chart over time. Series wear the validated categorical
 * palette slots; the legend names each line (colour never carries meaning
 * alone). Every value is also reachable via the ChartCard table twin.
 */
export function MultiTrendChart({
  data,
  series,
  formatter = (v: number) => v.toLocaleString("en-IN"),
  height = 240,
}: {
  data: Record<string, string | number>[];
  series: MultiTrendSeries[];
  formatter?: (value: number) => string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
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
          tickFormatter={(v: number) => formatter(v)}
        />
        <Tooltip
          cursor={{ stroke: "var(--baseline)", strokeWidth: 1 }}
          content={<ChartTooltip formatter={formatter} />}
        />
        <Legend
          iconType="plainline"
          wrapperStyle={{ fontSize: 11, color: "var(--text-muted)" }}
        />
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stroke={s.color}
            strokeWidth={2}
            strokeLinecap="round"
            dot={false}
            activeDot={{ r: 4, fill: s.color, stroke: "var(--surface-1)", strokeWidth: 2 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
