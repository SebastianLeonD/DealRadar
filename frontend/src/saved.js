// Saved-items watchlist, persisted in the browser (no login/backend needed).
// We keep a full snapshot of each deal so it can still be shown after it drops
// off the live board; the server tells us which are still on sale.
import { useCallback, useEffect, useState } from "react";

const KEY = "dealradar:saved";

const read = () => {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || [];
  } catch {
    return [];
  }
};

export function useSaved() {
  const [saved, setSaved] = useState(read);

  // keep other tabs in sync
  useEffect(() => {
    const onStorage = (e) => e.key === KEY && setSaved(read());
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const persist = useCallback((next) => {
    setSaved(next);
    localStorage.setItem(KEY, JSON.stringify(next));
  }, []);

  const toggle = useCallback(
    (deal) => {
      const next = saved.some((d) => d.url === deal.url)
        ? saved.filter((d) => d.url !== deal.url)
        : [{ ...deal, saved_at: Date.now() }, ...saved];
      persist(next);
    },
    [saved, persist]
  );

  const remove = useCallback((url) => persist(saved.filter((d) => d.url !== url)), [saved, persist]);

  return { saved, toggle, remove };
}
