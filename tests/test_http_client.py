"""Robust HTTP client + credit budget (council http-robustness / credit-cost)."""

from scrapers.http_client import (
    FETCH_EMPTY,
    FETCH_HTTP_ERROR,
    FETCH_OK,
    FETCH_TIMEOUT,
    CreditBudget,
    estimate_event_cost,
    fetch_json,
    truncate_books,
)


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


def _getter(responses):
    """Return a get_fn that yields queued responses (or raises for timeouts)."""
    calls = {'n': 0}

    def get_fn(url, params=None, timeout=None):
        item = responses[calls['n']]
        calls['n'] += 1
        if isinstance(item, Exception):
            raise item
        return item

    return get_fn, calls


def test_success_returns_ok_and_data():
    get_fn, _ = _getter([FakeResponse(200, {'a': 1}, {'x-requests-remaining': '99'})])
    r = fetch_json('u', {}, get_fn=get_fn, sleep_fn=lambda s: None)
    assert r.status == FETCH_OK
    assert r.data == {'a': 1}
    assert r.remaining == '99'


def test_empty_payload_is_typed_empty():
    get_fn, _ = _getter([FakeResponse(200, [])])
    r = fetch_json('u', {}, get_fn=get_fn, sleep_fn=lambda s: None)
    assert r.status == FETCH_EMPTY


def test_retries_then_succeeds_on_429():
    get_fn, calls = _getter([
        FakeResponse(429, headers={'Retry-After': '0'}),
        FakeResponse(200, {'ok': True}),
    ])
    r = fetch_json('u', {}, get_fn=get_fn, max_retries=3, sleep_fn=lambda s: None)
    assert r.status == FETCH_OK
    assert calls['n'] == 2


def test_persistent_5xx_is_typed_http_error():
    get_fn, _ = _getter([FakeResponse(503)] * 5)
    r = fetch_json('u', {}, get_fn=get_fn, max_retries=2, sleep_fn=lambda s: None)
    assert r.status == FETCH_HTTP_ERROR


def test_timeout_exception_is_typed_timeout():
    get_fn, _ = _getter([TimeoutError(), TimeoutError(), TimeoutError()])
    r = fetch_json('u', {}, get_fn=get_fn, max_retries=2, sleep_fn=lambda s: None)
    assert r.status == FETCH_TIMEOUT


def test_credit_cost_is_markets_times_regions():
    assert estimate_event_cost(5, 1) == 5
    assert estimate_event_cost(5, 2) == 10
    assert estimate_event_cost(0, 1) == 1  # never zero


def test_budget_hard_stop():
    b = CreditBudget(max_credits=10)
    assert b.can_afford(5)
    b.charge(5)
    b.charge(5)
    assert not b.can_afford(1)
    assert b.exhausted()


def test_budget_reconciles_with_headers():
    b = CreditBudget(max_credits=100)
    b.reconcile('20', '0')
    assert b.remaining_header == 0
    assert b.exhausted()  # API says no credits left


def test_truncate_books_keeps_sharpest_first():
    ordered = truncate_books(['betmgm', 'pinnacle', 'fanduel', 'draftkings'])
    assert ordered[0] == 'pinnacle'
    assert ordered[1] == 'draftkings'
    assert ordered.index('fanduel') < ordered.index('betmgm')
