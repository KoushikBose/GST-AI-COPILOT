"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { useTilt } from "@/hooks/use-tilt";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Flat hover (border + lift), the old default. */
  interactive?: boolean;
  /** Cursor-tracked 3D tilt + spotlight wash. Implies interactive elevation. */
  tilt?: boolean;
  /** Max tilt angle in degrees — smaller for dense grids, larger for hero cards. */
  tiltMax?: number;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, interactive, tilt, tiltMax = 6, style, children, ...props }, forwardedRef) => {
    const { ref, onPointerMove, onPointerLeave } = useTilt({ max: tiltMax, disabled: !tilt });

    // merge forwarded ref with the internal tilt ref
    const setRefs = React.useCallback(
      (node: HTMLDivElement | null) => {
        (ref as React.MutableRefObject<HTMLDivElement | null>).current = node;
        if (typeof forwardedRef === "function") forwardedRef(node);
        else if (forwardedRef) (forwardedRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
      },
      [ref, forwardedRef]
    );

    if (!tilt) {
      return (
        <div
          ref={setRefs}
          className={cn(
            "rounded-lg border border-border bg-card text-foreground elev-1 transition-all duration-200 ease-out",
            interactive && "press hover:border-border-strong",
            className
          )}
          style={style}
          {...props}
        >
          {children}
        </div>
      );
    }

    return (
      <div
        ref={setRefs}
        onPointerMove={onPointerMove}
        onPointerLeave={onPointerLeave}
        data-tracking="false"
        className={cn(
          "scene rounded-lg border border-border bg-card text-foreground",
          "tilt tilt-lift spotlight elev-2 hover:border-border-strong",
          className
        )}
        style={style}
        {...props}
      >
        <div className="tilt-layer-sm h-full">{children}</div>
      </div>
    );
  }
);
Card.displayName = "Card";

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1 p-5", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn("text-sm font-medium text-muted-foreground", className)} {...props} />
  );
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5 pt-0", className)} {...props} />;
}
