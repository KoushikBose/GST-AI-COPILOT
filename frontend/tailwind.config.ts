import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // page / surfaces
        background: "var(--page)",
        card: "var(--surface-1)",
        elevated: "var(--surface-2)",
        muted: {
          DEFAULT: "var(--surface-2)",
          foreground: "var(--text-muted)",
        },
        // ink
        foreground: "var(--text-primary)",
        secondary: "var(--text-secondary)",
        // lines
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        gridline: "var(--gridline)",
        baseline: "var(--baseline)",
        // accent
        primary: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-ink)",
          wash: "var(--accent-wash)",
        },
        accent2: "var(--accent-2)",
        // categorical series
        series: {
          1: "var(--series-1)",
          2: "var(--series-2)",
          3: "var(--series-3)",
          4: "var(--series-4)",
        },
        // status (fixed)
        good: "var(--status-good)",
        warning: "var(--status-warning)",
        serious: "var(--status-serious)",
        critical: "var(--status-critical)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
