"use client";

import Link from "next/link";
import { useCallback, useRef } from "react";
import {
  ArrowRight,
  Sparkles,
  Calculator,
  ShieldCheck,
  FileSearch,
  Zap,
  Github,
} from "lucide-react";

const FEATURES = [
  {
    icon: FileSearch,
    title: "Grounded GST research",
    body: "Hybrid retrieval over GST Acts, Rules, Notifications and Circulars — every answer cites its sources.",
  },
  {
    icon: Calculator,
    title: "Deterministic tax engine",
    body: "CGST / SGST / IGST / CESS computed by a unit-tested rule engine. The model never does the arithmetic.",
  },
  {
    icon: ShieldCheck,
    title: "Compliance & ITC checks",
    body: "GSTIN validation, duplicate detection and arithmetic consistency, with human review on anything uncertain.",
  },
];

const STATS = [
  { value: "7", label: "Qdrant knowledge collections" },
  { value: "0", label: "LLM-generated tax figures" },
  { value: "82", label: "Deterministic-core unit tests" },
  { value: "100%", label: "Open-source runtime" },
];

/** Cursor-tracked tilt, scoped to this page — writes CSS vars, no re-render. */
function useLandingTilt(max = 9) {
  const ref = useRef<HTMLDivElement>(null);

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (e.pointerType === "touch") return;
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width;
      const py = (e.clientY - rect.top) / rect.height;
      el.style.setProperty("--rx", `${(-(py - 0.5) * max * 2).toFixed(2)}deg`);
      el.style.setProperty("--ry", `${((px - 0.5) * max * 2).toFixed(2)}deg`);
      el.style.setProperty("--mx", `${(px * 100).toFixed(1)}%`);
      el.style.setProperty("--my", `${(py * 100).toFixed(1)}%`);
      el.dataset.tracking = "true";
    },
    [max]
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

function FeatureCard({
  icon: Icon,
  title,
  body,
  delay,
}: {
  icon: typeof FileSearch;
  title: string;
  body: string;
  delay: number;
}) {
  const { ref, onPointerMove, onPointerLeave } = useLandingTilt(9);
  return (
    <div
      ref={ref}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
      data-tracking="false"
      className="animate-rise-in scene landing-card spotlight tilt rounded-xl p-6"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="tilt-layer">
        <span className="landing-icon-chip inline-flex h-10 w-10 items-center justify-center rounded-lg">
          <Icon className="h-[18px] w-[18px] text-white" strokeWidth={2} />
        </span>
        <h3 className="mt-4 text-sm font-semibold text-white">{title}</h3>
        <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--lv-ink-dim)" }}>
          {body}
        </p>
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <main className="landing-scene relative min-h-screen overflow-hidden">
      <div className="landing-mesh" aria-hidden />
      <div
        className="landing-orb"
        style={{
          width: 10,
          height: 10,
          top: "18%",
          left: "22%",
          background: "var(--lv-pink-glow)",
          boxShadow: "0 0 24px 6px var(--lv-pink-glow)",
        }}
        aria-hidden
      />
      <div
        className="landing-orb"
        style={{
          width: 6,
          height: 6,
          top: "62%",
          left: "78%",
          background: "var(--lv-violet-bright)",
          boxShadow: "0 0 20px 5px var(--lv-violet-bright)",
          animationDelay: "1.2s",
        }}
        aria-hidden
      />
      <div
        className="landing-orb"
        style={{
          width: 8,
          height: 8,
          top: "78%",
          left: "14%",
          background: "var(--lv-fuchsia)",
          boxShadow: "0 0 22px 5px var(--lv-fuchsia)",
          animationDelay: "2.1s",
        }}
        aria-hidden
      />

      {/* Nav */}
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2">
          <span
            className="flex h-8 w-8 items-center justify-center rounded-lg"
            style={{
              background: "linear-gradient(135deg, var(--lv-violet), var(--lv-fuchsia))",
            }}
          >
            <Sparkles className="h-4 w-4 text-white" />
          </span>
          <span className="text-sm font-semibold text-white">GST AI Copilot</span>
        </div>
        <a
          href="https://github.com"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors duration-200"
          style={{ borderColor: "var(--lv-card-border)", color: "var(--lv-ink-dim)" }}
        >
          <Github className="h-3.5 w-3.5" />
          Open source
        </a>
      </header>

      {/* Hero */}
      <section className="relative z-10 mx-auto flex max-w-3xl flex-col items-center px-6 pb-20 pt-16 text-center sm:pt-24">
        <span className="landing-badge animate-rise-in inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs" style={{ color: "var(--lv-ink-dim)" }}>
          <Zap className="h-3 w-3" style={{ color: "var(--lv-pink-glow)" }} />
          Synthetic demo data · not a filing system
        </span>

        <h1
          className="animate-rise-in landing-gradient-text mt-6 text-5xl font-bold leading-[1.1] tracking-tight sm:text-6xl"
          style={{ animationDelay: "70ms" }}
        >
          GST AI Copilot
        </h1>

        <p
          className="animate-rise-in mt-5 max-w-xl text-balance text-base leading-relaxed sm:text-lg"
          style={{ animationDelay: "140ms", color: "var(--lv-ink-dim)" }}
        >
          Agentic AI, grounded GST research, invoice intelligence and deterministic tax
          calculation for Indian SMEs, accountants and CA firms.
        </p>

        <div
          className="animate-rise-in mt-8 flex flex-wrap items-center justify-center gap-3"
          style={{ animationDelay: "210ms" }}
        >
          <Link
            href="/dashboard"
            className="landing-cta group inline-flex items-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold text-white"
          >
            Open dashboard
            <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
          </Link>
          <Link
            href="/chat"
            className="inline-flex items-center gap-2 rounded-lg border px-6 py-3 text-sm font-medium text-white transition-colors duration-200 hover:bg-white/5"
            style={{ borderColor: "var(--lv-card-border)" }}
          >
            Try GST chat
          </Link>
        </div>

        {/* Stats strip */}
        <div
          className="animate-rise-in mt-16 grid w-full grid-cols-2 gap-6 border-t pt-10 sm:grid-cols-4"
          style={{ animationDelay: "280ms", borderColor: "var(--lv-card-border)" }}
        >
          {STATS.map((s) => (
            <div key={s.label}>
              <div className="landing-stat-value text-2xl font-bold sm:text-3xl">{s.value}</div>
              <div className="mt-1 text-xs" style={{ color: "var(--lv-ink-faint)" }}>
                {s.label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Feature grid */}
      <section className="relative z-10 mx-auto max-w-5xl px-6 pb-24">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {FEATURES.map((f, i) => (
            <FeatureCard key={f.title} {...f} delay={340 + i * 90} />
          ))}
        </div>
      </section>
    </main>
  );
}
