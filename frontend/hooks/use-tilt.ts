"use client";

import { useCallback, useRef } from "react";

interface TiltOptions {
  /** Max rotation in degrees at the pointer's furthest extent. */
  max?: number;
  /** Disable entirely (e.g. on touch devices where hover doesn't apply). */
  disabled?: boolean;
}

/**
 * Cursor-tracked 3D tilt, driven entirely through CSS custom properties
 * (--rx, --ry, --mx, --my) written directly to the DOM node — no React
 * state, so pointer-move never triggers a re-render.
 *
 * Pair the returned handlers with the `.tilt` / `.spotlight` CSS classes
 * (see globals.css). Respects prefers-reduced-motion by no-opping.
 */
export function useTilt({ max = 8, disabled = false }: TiltOptions = {}) {
  const ref = useRef<HTMLDivElement>(null);
  const reducedMotion = useRef(false);

  if (typeof window !== "undefined" && reducedMotion.current === false) {
    reducedMotion.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (disabled || reducedMotion.current || e.pointerType === "touch") return;
      const el = ref.current;
      if (!el) return;

      const rect = el.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width; // 0..1
      const py = (e.clientY - rect.top) / rect.height;

      const ry = (px - 0.5) * max * 2; // rotateY follows horizontal offset
      const rx = -(py - 0.5) * max * 2; // rotateX follows vertical offset (inverted)

      el.style.setProperty("--rx", `${rx.toFixed(2)}deg`);
      el.style.setProperty("--ry", `${ry.toFixed(2)}deg`);
      el.style.setProperty("--mx", `${(px * 100).toFixed(1)}%`);
      el.style.setProperty("--my", `${(py * 100).toFixed(1)}%`);
      el.dataset.tracking = "true";
    },
    [disabled, max]
  );

  const onPointerLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--rx", "0deg");
    el.style.setProperty("--ry", "0deg");
    el.dataset.tracking = "false";
  }, []);

  return { ref, onPointerMove, onPointerLeave };
}
