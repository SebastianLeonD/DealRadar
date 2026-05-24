import type { ReactNode } from "react";

interface BadgeProps {
  children: ReactNode;
  variant?: "fresh" | "aging" | "stale" | "online" | "cyan" | "purple" | "orange" | "over" | "under" | "neutral";
}

const variantStyles: Record<NonNullable<BadgeProps["variant"]>, string> = {
  fresh: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  aging: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  stale: "bg-rose-500/15 text-rose-400 border-rose-500/30",
  online: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  cyan: "bg-cyan-500/12 text-cyan-400 border-cyan-500/25",
  purple: "bg-purple-500/12 text-purple-400 border-purple-500/25",
  orange: "bg-amber-500/12 text-amber-400 border-amber-500/25",
  over: "bg-emerald-500/12 text-emerald-400 border-emerald-500/25",
  under: "bg-rose-500/12 text-rose-400 border-rose-500/25",
  neutral: "bg-white/5 text-text-muted border-border",
};

export function Badge({ children, variant = "neutral" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide ${variantStyles[variant]}`}
    >
      {children}
    </span>
  );
}

interface MetricCardProps {
  label: string;
  value: string | number;
}

export function MetricCard({ label, value }: MetricCardProps) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-surface-card px-5 py-4">
      <div className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-accent/80 to-cyan-500/40" />
      <p className="text-xs font-medium uppercase tracking-widest text-text-dim">
        {label}
      </p>
      <p className="mt-1 text-3xl font-bold tracking-tight text-text">{value}</p>
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
    <div className="mb-8 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-text">{title}</h1>
        <p className="mt-1 text-sm text-text-muted">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

interface EmptyStateProps {
  message: string;
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="rounded-xl border border-dashed border-white/10 bg-surface-raised/50 px-6 py-12 text-center text-sm text-text-muted">
      {message}
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
