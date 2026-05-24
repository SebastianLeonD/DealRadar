import {
  BarChart3,
  Play,
  TrendingUp,
} from "lucide-react";
import type { Page } from "../lib/api";

interface SidebarProps {
  active: Page;
  onNavigate: (page: Page) => void;
}

const navItems: { id: Page; label: string; icon: typeof Play }[] = [
  { id: "execution", label: "Execution", icon: Play },
  { id: "opportunities", label: "Active Opportunities", icon: TrendingUp },
  { id: "clv", label: "CLV Performance", icon: BarChart3 },
];

export function Sidebar({ active, onNavigate }: SidebarProps) {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface-raised">
      <div className="border-b border-border px-5 py-6">
        <h1 className="text-lg font-bold tracking-tight text-text">
          Arbitrage_CC
        </h1>
        <p className="mt-0.5 text-xs text-text-muted">Control Center</p>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map(({ id, label, icon: Icon }) => {
          const isActive = active === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onNavigate(id)}
              className={`relative flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-accent/8 text-accent"
                  : "text-text-muted hover:bg-white/5 hover:text-text"
              }`}
            >
              {isActive && (
                <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-accent" />
              )}
              <Icon
                size={18}
                className={isActive ? "text-accent" : "text-text-dim"}
              />
              {label}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-border px-5 py-4">
        <p className="text-xs text-text-dim">v1.0.0 (Local Engine)</p>
      </div>
    </aside>
  );
}
