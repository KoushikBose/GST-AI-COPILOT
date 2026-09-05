"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartTooltip } from "@/components/charts/chart-card";

export interface BreakdownDatum {
  label: string;
  value: number;
  /** Optional explicit colour — used for status distributions only. */
  color?: string;
}

/**
 * Horizontal magnitude comparison. Nominal categories all wear the same hue
 * (slot 1) unless the caller supplies status colours — bar length already
 * encodes magnitude, so a value-ramp would double-encode it.
 *
 * Values are direct-labelled at the bar tips, so nothing is tooltip-gated.
 */
export function BreakdownBarChart({
  data,
  formatter = (v: number) => v.toLocaleString("en-IN"),
  height = 220,
}: {
  data: BreakdownDatum[];
  formatter?: (value: number) => string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 56, bottom: 0, left: 0 }}
        barCategoryGap={10}
      >
        <CartesianGrid stroke="var(--gridline)" horizontal={false} />
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="label"
          tickLine={false}
          axisLine={{ stroke: "var(--baseline)" }}
          width={92}
          tickMargin={8}
        />
        <Tooltip
          cursor={{ fill: "var(--surface-2)" }}
          content={<ChartTooltip formatter={formatter} />}
        />
        <Bar dataKey="value" name="Amount" barSize={16} radius={[0, 4, 4, 0]} isAnimationActive>
          {data.map((d, i) => (
            <Cell key={i} fill={d.color ?? "var(--series-1)"} />
          ))}
          <LabelList
            dataKey="value"
            position="right"
            offset={8}
            formatter={formatter}
            style={{
              fill: "var(--text-secondary)",
              fontSize: 11,
              fontVariantNumeric: "tabular-nums",
            }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
