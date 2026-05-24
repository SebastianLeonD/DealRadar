import { useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ClvPage } from "./pages/ClvPage";
import { ExecutionPage } from "./pages/ExecutionPage";
import { OpportunitiesPage } from "./pages/OpportunitiesPage";
import type { Page } from "./lib/api";

export default function App() {
  const [page, setPage] = useState<Page>("execution");

  return (
    <div className="flex h-full min-h-screen bg-surface">
      <Sidebar active={page} onNavigate={setPage} />
      <main className="flex-1 overflow-y-auto p-8">
        {page === "execution" && <ExecutionPage />}
        {page === "opportunities" && <OpportunitiesPage />}
        {page === "clv" && <ClvPage />}
      </main>
    </div>
  );
}
