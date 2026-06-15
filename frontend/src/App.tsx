import { useState } from "react";
import { TopNav } from "./components/TopNav";
import { ClvPage } from "./pages/ClvPage";
import { ExecutionPage } from "./pages/ExecutionPage";
import { HelpPage } from "./pages/HelpPage";
import { PrizePicksBoardPage } from "./pages/PrizePicksBoardPage";
import { MyBetsPage } from "./pages/MyBetsPage";
import type { Page } from "./lib/api";

export default function App() {
  const [page, setPage] = useState<Page>("prizepicks");

  return (
    <div className="min-h-screen">
      <TopNav active={page} onNavigate={setPage} />
      <main className="mx-auto max-w-5xl px-6 py-10">
        {page === "prizepicks" && <PrizePicksBoardPage />}
        {page === "bets" && <MyBetsPage />}
        {page === "execution" && <ExecutionPage />}
        {page === "clv" && <ClvPage />}
        {page === "help" && <HelpPage />}
      </main>
    </div>
  );
}
