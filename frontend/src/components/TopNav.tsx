import type { Page } from "../lib/api";

interface TopNavProps {
  active: Page;
  onNavigate: (page: Page) => void;
}

const tabs: { id: Page; label: string }[] = [
  { id: "prizepicks", label: "The Board" },
  { id: "slip", label: "Build a Slip" },
  { id: "bets", label: "My Bets" },
  { id: "execution", label: "Update Data" },
  { id: "clv", label: "Results" },
  { id: "help", label: "Help" },
];

export function TopNav({ active, onNavigate }: TopNavProps) {
  return (
    <header className="border-b-2 border-ink bg-card/85 backdrop-blur-sm">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6">
        <div className="flex items-baseline gap-2 py-4">
          <span
            className="text-xl font-extrabold tracking-tight text-ink"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Edge Desk
          </span>
          <span className="hidden text-xs text-ink-faint sm:inline">
            PrizePicks vs. the bookmakers
          </span>
        </div>

        <nav className="flex h-full items-stretch gap-1">
          {tabs.map(({ id, label }) => {
            const isActive = active === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => onNavigate(id)}
                className={`relative px-4 py-5 text-sm font-semibold transition-colors ${
                  isActive ? "text-ink" : "text-ink-faint hover:text-ink-soft"
                }`}
              >
                {label}
                {isActive && (
                  <span className="absolute inset-x-3 -bottom-0.5 h-[3px] bg-bet" />
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
