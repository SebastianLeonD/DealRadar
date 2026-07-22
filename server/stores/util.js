// Shared helpers for direct store fetchers.

export const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  Accept: "application/json",
};

export async function getJSON(url) {
  const resp = await fetch(url, { headers: HEADERS, signal: AbortSignal.timeout(20000) });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export const usd = (n) => (Number.isInteger(n) ? `$${n}` : `$${n.toFixed(2)}`);
