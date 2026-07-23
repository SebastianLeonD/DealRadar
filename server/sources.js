// Deal feed fetchers. All sources are direct retailer scrapers — no API keys
// beyond the optional Best Buy one.
import { SCRAPERS } from "./stores/index.js";

/** Every source — the direct retailer scrapers — as {name, fetch}. */
export const ALL_SOURCES = [...SCRAPERS];

// After a rate-limit (429), skip the source for a while instead of hammering
// it every refresh. In-memory: source name -> epoch ms until which to skip.
const COOLDOWN_MS = 30 * 60 * 1000;
const coolingUntil = new Map();

/** Fetch every source (scrapers). Returns {deals, errors, health} —
    one source failing never blocks the rest; health has a row per source. */
export async function fetchAll() {
  const deals = [];
  const errors = [];
  const health = [];
  await Promise.all(
    ALL_SOURCES.map(async (s) => {
      const until = coolingUntil.get(s.name);
      if (until && Date.now() < until) {
        health.push({
          source: s.name, ok: false, count: 0, ms: 0, skipped: true,
          error: `rate-limited — cooling down until ${new Date(until).toLocaleTimeString()}`,
        });
        return;
      }
      const started = Date.now();
      try {
        const d = await s.fetch();
        coolingUntil.delete(s.name);
        deals.push(...d);
        health.push({ source: s.name, ok: true, count: d.length, ms: Date.now() - started });
      } catch (e) {
        const error = String(e?.message ?? e);
        if (error.includes("429")) coolingUntil.set(s.name, Date.now() + COOLDOWN_MS);
        errors.push(`${s.name}: ${error}`);
        health.push({ source: s.name, ok: false, count: 0, error, ms: Date.now() - started });
      }
    })
  );
  health.sort((a, b) => a.source.localeCompare(b.source));
  return { deals, errors, health };
}
