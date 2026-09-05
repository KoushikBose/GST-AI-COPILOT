"use client";

import { useEffect } from "react";
import { create } from "zustand";
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastKind = "success" | "error" | "warning" | "info";

interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  description?: string;
}

interface ToastState {
  toasts: Toast[];
  push: (t: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => set((s) => ({ toasts: [...s.toasts, { ...t, id: nextId++ }] })),
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));

export const toast = {
  success: (title: string, description?: string) =>
    useToastStore.getState().push({ kind: "success", title, description }),
  error: (title: string, description?: string) =>
    useToastStore.getState().push({ kind: "error", title, description }),
  warning: (title: string, description?: string) =>
    useToastStore.getState().push({ kind: "warning", title, description }),
  info: (title: string, description?: string) =>
    useToastStore.getState().push({ kind: "info", title, description }),
};

const KIND_CONFIG: Record<ToastKind, { icon: typeof Info; className: string }> = {
  success: { icon: CheckCircle2, className: "text-good" },
  error: { icon: XCircle, className: "text-critical" },
  warning: { icon: AlertTriangle, className: "text-warning" },
  info: { icon: Info, className: "text-primary" },
};

function ToastItem({ toast: t }: { toast: Toast }) {
  const dismiss = useToastStore((s) => s.dismiss);
  const { icon: Icon, className } = KIND_CONFIG[t.kind];

  useEffect(() => {
    const timer = setTimeout(() => dismiss(t.id), 5000);
    return () => clearTimeout(timer);
  }, [t.id, dismiss]);

  return (
    <div
      role="status"
      className="animate-rise-in glass pointer-events-auto flex w-80 items-start gap-3 rounded-lg border border-border-strong p-3.5 shadow-[var(--elev-4),var(--edge-top-strong)]"
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", className)} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{t.title}</p>
        {t.description && (
          <p className="mt-0.5 break-words text-xs text-muted-foreground">{t.description}</p>
        )}
      </div>
      <button
        onClick={() => dismiss(t.id)}
        aria-label="Dismiss"
        className="text-muted-foreground transition-colors hover:text-foreground"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  );
}
