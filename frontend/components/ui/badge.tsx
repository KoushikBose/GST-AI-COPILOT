import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Status variants use the reserved status palette and are always paired with
 * a text label (and, where they carry meaning, an icon at the call site) —
 * colour never carries the state on its own.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors duration-200",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary-wash text-primary",
        good: "border-transparent bg-good/15 text-good",
        warning: "border-transparent bg-warning/15 text-warning",
        serious: "border-transparent bg-serious/15 text-serious",
        critical: "border-transparent bg-critical/15 text-critical",
        outline: "border-border text-muted-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

/** Small status dot for use beside a text label (never colour-alone). */
export function StatusDot({ className }: { className?: string }) {
  return <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full bg-current", className)} />;
}
