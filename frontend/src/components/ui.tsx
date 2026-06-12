import type { ReactNode } from "react";

/* ---------- plain-english translators ---------- */

export function verdictWord(verdict: string | null): "YES" | "MAYBE" | "SKIP" | "—" {
  if (verdict === "YES") return "YES";
  if (verdict === "LEAN") return "MAYBE";
  if (verdict === "NO") return "SKIP";
  return "—";
}

export function statLabel(stat: string | null): string {
  if (!stat) return "";
  const firstHalf = stat.endsWith("_1h");
  const base = stat
    .replace(/_1h$/, "")
    .replace(/^player_/, "")
    .replaceAll("_", " ");
  return firstHalf ? `${base} · 1st half` : base;
}

/* ---------- primitives ---------- */

interface BadgeProps {
  children: ReactNode;
  variant?: "bet" | "maybe" | "skip" | "info" | "neutral" | "ink";
}

const badgeStyles: Record<NonNullable<BadgeProps["variant"]>, string> = {
  bet: "bg-bet-soft text-bet border-bet/25",
  maybe: "bg-maybe-soft text-maybe border-maybe/25",
  skip: "bg-skip-soft text-skip border-skip/25",
  info: "bg-info-soft text-info border-info/20",
  neutral: "bg-paper text-ink-soft border-line",
  ink: "bg-ink text-card border-ink",
};

export function Badge({ children, variant = "neutral" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide ${badgeStyles[variant]}`}
    >
      {children}
    </span>
  );
}

interface MetricCardProps {
  label: string;
  value: string | number;
  hint?: string;
}

export function MetricCard({ label, value, hint }: MetricCardProps) {
  return (
    <div className="rounded-lg border border-line bg-card px-5 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
        {label}
      </p>
      <p className="tnum mt-1.5 text-3xl font-semibold text-ink">{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}

interface PageHeaderProps {
  title: string;
  subtitle: string;
  action?: ReactNode;
}

export function PageHeader({ title, subtitle, action }: PageHeaderProps) {
  return (
    <div className="rise mb-8 flex items-end justify-between gap-4 border-b-2 border-ink pb-5">
      <div>
        <h1
          className="text-[34px] font-bold leading-none tracking-tight text-ink"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {title}
        </h1>
        <p className="mt-2 text-sm text-ink-soft">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line-strong bg-paper px-6 py-12 text-center text-sm text-ink-soft">
      {message}
    </div>
  );
}

/* small win-chance bar with a tick at the 54.25% break-even */
export function WinBar({ prob }: { prob: number }) {
  const pct = Math.min(prob * 100, 100);
  return (
    <div className="relative h-1.5 w-full max-w-[88px] overflow-visible rounded-full bg-line">
      <div
        className={`h-full rounded-full ${prob >= 0.5425 ? "bg-bet" : "bg-skip"}`}
        style={{ width: `${pct}%` }}
      />
      <span className="absolute -top-[3px] left-[54.25%] h-3 w-px bg-ink-faint" />
    </div>
  );
}

export function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return iso;
  }
}

export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}
