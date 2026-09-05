import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Buttons carry real depth: a raised resting state (elevation + top inner
 * highlight), a lift on hover, and a press-in on active — so the control
 * reads as a physical surface rather than a painted rectangle.
 */
const buttonVariants = cva(
  [
    "relative inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium",
    "transition-all duration-200 ease-out",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
    "disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none",
    "hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98]",
  ].join(" "),
  {
    variants: {
      variant: {
        default:
          "bg-gradient-to-br from-primary to-accent2 text-primary-foreground shadow-[var(--elev-2),var(--edge-top-strong)] hover:shadow-[var(--elev-3),var(--edge-top-strong)] hover:brightness-110 active:shadow-[var(--elev-1)]",
        outline:
          "border border-border bg-card text-foreground shadow-[var(--elev-1),var(--edge-top)] hover:border-border-strong hover:shadow-[var(--elev-2),var(--edge-top)]",
        ghost:
          "text-muted-foreground hover:bg-elevated hover:text-foreground hover:translate-y-0",
        destructive:
          "bg-critical text-white shadow-[var(--elev-2),var(--edge-top-strong)] hover:shadow-[var(--elev-3),var(--edge-top-strong)] hover:brightness-110",
        subtle:
          "bg-elevated text-foreground shadow-[var(--elev-1),var(--edge-top)] hover:bg-gridline hover:shadow-[var(--elev-2),var(--edge-top)]",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-6",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
);
Button.displayName = "Button";
