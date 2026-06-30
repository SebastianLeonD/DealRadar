"""Shared robust HTTP client + credit budgeting for Odds-API scrapers.

Council resolutions (engineering, firewall-load-bearing):

  * http-robustness — every request gets a timeout, bounded exponential
    backoff with jitter honoring Retry-After on 429/5xx, and a max-retry
    budget. A persistent per-(event, book) failure becomes a TYPED failure
    (fetch_status in {ok, http_error, timeout, empty}), never a silent
    `continue` that drops a game and biases consensus.

  * credit-cost — the real Odds-API cost of an /events/{id}/odds call is
    (#markets) x (#regions); books within a region do NOT multiply. A
    MAX_CREDITS_PER_SLATE budget with a deterministic book-priority DROP
    ORDER governs truncation. A budget- or failure-truncated line withholds
    the identified-consensus tag rather than computing it on a partial set.

The network call is injected (`get_fn`) so the retry/credit logic is unit
testable without real HTTP.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from engine.config import (
    BOOK_PRIORITY,
    HTTP_BACKOFF_BASE_SECONDS,
    HTTP_MAX_RETRIES,
    HTTP_TIMEOUT_SECONDS,
    MAX_CREDITS_PER_SLATE,
)

# Typed fetch outcomes persisted per (event, book) so a recompute can tell
# "book did not quote this line" (empty) from "fetch failed" (http_error/timeout).
FETCH_OK = "ok"
FETCH_HTTP_ERROR = "http_error"
FETCH_TIMEOUT = "timeout"
FETCH_EMPTY = "empty"


def estimate_event_cost(n_markets: int, n_regions: int = 1) -> int:
    """Odds-API credit cost of one event-odds call: markets x regions."""
    return max(1, n_markets * n_regions)


@dataclass
class CreditBudget:
    """Tracks Odds-API spend against a per-slate cap with a hard stop."""

    max_credits: int = MAX_CREDITS_PER_SLATE
    spent: int = 0
    used_header: int | None = None
    remaining_header: int | None = None

    def can_afford(self, cost: int) -> bool:
        return self.spent + cost <= self.max_credits

    def charge(self, cost: int) -> None:
        self.spent += cost

    def reconcile(self, used: str | None, remaining: str | None) -> None:
        """Reconcile against the API's own x-requests headers (source of truth)."""
        if used is not None:
            try:
                self.used_header = int(used)
            except (TypeError, ValueError):
                pass
        if remaining is not None:
            try:
                self.remaining_header = int(remaining)
            except (TypeError, ValueError):
                pass

    def exhausted(self) -> bool:
        if self.remaining_header is not None and self.remaining_header <= 0:
            return True
        return self.spent >= self.max_credits


def truncate_books(books: list[str]) -> list[str]:
    """Deterministic drop order: keep sharpest books first (council BOOK_PRIORITY).

    Books not in the priority list sort last (least preferred), preserving
    their input order, so truncation is reproducible rather than wherever
    quota happens to run out.
    """
    def rank(book: str) -> tuple[int, int]:
        try:
            return (0, BOOK_PRIORITY.index(book))
        except ValueError:
            return (1, books.index(book))

    return sorted(books, key=rank)


@dataclass
class FetchResult:
    data: object | None
    status: str
    used: str | None = None
    remaining: str | None = None
    attempts: int = 0


def _is_retryable(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def fetch_json(
    url: str,
    params: dict,
    *,
    get_fn,
    timeout: float = HTTP_TIMEOUT_SECONDS,
    max_retries: int = HTTP_MAX_RETRIES,
    backoff_base: float = HTTP_BACKOFF_BASE_SECONDS,
    sleep_fn=time.sleep,
    jitter: float = 0.0,
) -> FetchResult:
    """GET JSON with bounded retry/backoff and a typed result.

    `get_fn(url, params=..., timeout=...)` must return an object exposing
    `.status_code`, `.headers`, and `.json()` (the `requests` contract). A
    timeout is signaled by raising; the typed status absorbs it.
    """
    attempts = 0
    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        try:
            response = get_fn(url, params=params, timeout=timeout)
        except Exception:  # connection error / timeout raised by the transport
            if attempt < max_retries:
                sleep_fn(backoff_base * (2 ** attempt) + jitter)
                continue
            return FetchResult(None, FETCH_TIMEOUT, attempts=attempts)

        used = response.headers.get("x-requests-used")
        remaining = response.headers.get("x-requests-remaining")

        if response.status_code == 200:
            data = response.json()
            status = FETCH_OK if data else FETCH_EMPTY
            return FetchResult(data, status, used, remaining, attempts)

        if _is_retryable(response.status_code) and attempt < max_retries:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after is not None else backoff_base * (2 ** attempt)
            except (TypeError, ValueError):
                delay = backoff_base * (2 ** attempt)
            sleep_fn(delay + jitter)
            continue

        return FetchResult(None, FETCH_HTTP_ERROR, used, remaining, attempts)

    return FetchResult(None, FETCH_HTTP_ERROR, attempts=attempts)
