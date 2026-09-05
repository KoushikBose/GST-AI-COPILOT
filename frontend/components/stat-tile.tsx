"use client";

import { useEffect, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** Counts from 0 to `target` once, respecting reduced-motion. */
function useCountUp(target: number, durationMs = 700) {
  const [display, setDisplay] = useState(0);
  const frameRef = useRef<number>();

  useEffect(() => {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced || target === 0) {
      setDisplay(target);
      return;
    }

    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min((now - start) / durationMs, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setDisplay(target * eased);
      if (progress < 1) frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [target, durationMs]);

  return display;
}

/** 12-point sparkline: context in the de-emphasis hue, latest point in the accent. */
function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null;

  const width = 72;
  const height = 22;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min || 1;

  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * width;
    const y = height - ((p - min) / range) * height;
    return [x, y] as const;
  });

  const path = coords
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
  const last = coords[coords.length - 1]!;

  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden>
      <path
        d={path}
        fill="none"
        stroke="var(--baseline)"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={last[0]}
        cy={last[1]}
        r={3}
        fill="var(--series-1)"
        stroke="var(--surface-1)"
        strokeWidth={2}
      />
    </svg>
  );
}

export function StatTile({
  label,
  value,
  rawValue,
  icon: Icon,
  loading,
  sparkline,
  tone = "neutral",
  delay = 0,
}: {
  label: string;
  value: string;
  rawValue?: number;
  icon: LucideIcon;
  loading?: boolean;
  sparkline?: number[];
  tone?: "neutral" | "critical" | "warning";
  delay?: number;
}) {
  const counted = useCountUp(rawValue ?? 0);
  const showCounted = rawValue !== undefined && counted < (rawValue ?? 0) - 0.5;

  return (
    <Card
      tilt
      tiltMax={7}
      className="animate-rise-in p-5"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-muted-foreground">{label}</p>
        <span
          className={cn(
            "tilt-layer flex h-7 w-7 items-center justify-center rounded-md",
            tone === "critical"
              ? "bg-critical/15 text-critical"
              : tone === "warning"
                ? "bg-warning/15 text-warning"
                : "bg-primary-wash text-primary"
          )}
        >
          <Icon className="h-3.5 w-3.5" />
        </span>
      </div>

      <div className="mt-3 flex items-end justify-between gap-3">
        {loading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <span
            className={cn(
              "tilt-layer text-2xl font-semibold leading-none",
              tone === "critical" && "text-critical",
              tone === "warning" && "text-warning"
            )}
          >
            {showCounted ? Math.round(counted).toLocaleString("en-IN") : value}
          </span>
        )}
        {!loading && sparkline && sparkline.length > 1 && (
          <span className="tilt-layer-sm">
            <Sparkline points={sparkline} />
          </span>
        )}
      </div>
    </Card>
  );
}
