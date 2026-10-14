"""Polymarket US's public market data: the one module that speaks to it.

Polymarket US is QCX LLC, a CFTC-designated contract market (ISO 10383
`QCEX`); its public API is at gateway.polymarket.us and needs no key
(docs.polymarket.us, "API Reference: Introduction"). Three reads, each of
one market by its slug: `/v1/market/slug/{slug}` (the market, asked only
for a subject the lake wants, and asked again for its outcome once it is
past its end), `/v1/markets/{slug}/book` (its resting bids and offers and
its statistics, the last trade among them) and
`/v1/markets/{slug}/settlement` (its settlement price, asked only once the
market states its final settlement published). Nothing here holds a
credential, and nothing is sent but the request: the authenticated API at
api.polymarket.us, its WebSockets among them, is never called. The
standard library's HTTP client; the plugin depends on nothing but the SDK.
The market list is never read: a market is asked for by its slug, one at a
time.

**Rate limits, honoured.** Polymarket US limits its public reads per IP
(docs.polymarket.us, "Rate Limits"); this client spends at most five a
second from a token bucket, and a 429 is waited out (its Retry-After, else
1, 2, 4 seconds) and asked again at most three times, each one counted.

**Every response is a raw record first** (raw.py), kept exactly as its bytes
arrived, with its status and the headers that say when it was sent, before
anything is read from it. A body is parsed with `json_decimal`, so a JSON
number becomes a Decimal from its own text and never a float.

**Where it answers from.** Polymarket US itself; or, in synthetic mode, the
synthetic exchanges this package carries, or a developer's recorded ones,
through the same requests (synthetic.py).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .market import Health, json_decimal
from .raw import RawStore

GATEWAY = "https://gateway.polymarket.us"
USER_AGENT = "plugin-polymarket-us (+https://open-meridian.dev)"

#: What the plugin spends: five a second, in bursts of five.
RATE_PER_SECOND = 5.0
BURST = 5
#: The status of an answer saying the venue knows nothing by the name asked.
NOT_FOUND = 404
#: The headers kept with a record: when it was sent, and rate limits.
KEPT_HEADERS = ("date", "cache-control", "age", "etag", "retry-after")


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, Mapping[str, str]], Response]


def urllib_transport(url: str, headers: Mapping[str, str]) -> Response:
    """One GET over HTTPS, with the standard library."""
    request = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=15) as answer:
            return Response(
                answer.status, {k.lower(): v for k, v in answer.headers.items()}, answer.read()
            )
    except urllib.error.HTTPError as answer:
        return Response(
            answer.code, {k.lower(): v for k, v in answer.headers.items()}, answer.read()
        )


class RateLimiter:
    """A token bucket: `rate` calls a second, `burst` at once."""

    def __init__(
        self,
        rate: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.rate, self.burst = rate, burst
        self._clock, self._sleep = clock, sleep
        self._tokens = float(burst)
        self._at = clock()
        self.waited = 0.0

    def acquire(self) -> None:
        now = self._clock()
        self._tokens = min(self.burst, self._tokens + (now - self._at) * self.rate)
        self._at = now
        if self._tokens < 1:
            wait = (1 - self._tokens) / self.rate
            self._sleep(wait)
            self.waited += wait
            self._at = self._clock()
            self._tokens = 1.0
        self._tokens -= 1


class VenueError(Exception):
    """Polymarket US answered with something other than what was asked for,
    or did not answer."""

    def __init__(self, call: str, status: int, detail: str, raw_key: str = "") -> None:
        kept = f" (raw record {raw_key})" if raw_key else ""
        super().__init__(f"Polymarket US's {call}: {status or 'no answer'} {detail}{kept}")
        self.call, self.status, self.detail, self.raw_key = call, status, detail, raw_key


@dataclass(frozen=True)
class Fetched:
    """A parsed body, the key of the raw record it was kept as, and when it
    arrived."""

    value: Any
    raw_key: str
    received_at_ns: int


class Polymarket:
    """Polymarket US's public reads, every response kept."""

    def __init__(
        self,
        store: RawStore,
        transport: Transport = urllib_transport,
        limiter: RateLimiter | None = None,
        clock_ns: Callable[[], int] = time.time_ns,
        sleep: Callable[[float], None] = time.sleep,
        retries: int = 3,
    ) -> None:
        self.store, self.transport = store, transport
        self.limiter = limiter or RateLimiter(RATE_PER_SECOND, BURST)
        self.clock_ns, self.sleep, self.retries = clock_ns, sleep, retries
        self.health = Health()

    def _get(
        self,
        call: str,
        name: str,
        path: str,
        live: bool = False,
    ) -> Fetched:
        url = GATEWAY + path
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        for attempt in range(self.retries + 1):
            self.limiter.acquire()
            self.health.waited_seconds = self.limiter.waited
            self.health.calls += 1
            try:
                answer = self.transport(url, headers)
            except OSError as failed:
                self._failed(f"{call}: {failed}")
                raise VenueError(call, 0, str(failed)) from None
            received = self.clock_ns()
            text = answer.body.decode("utf-8", errors="replace")
            record = {
                "venue": "polymarket-us",
                "call": call,
                "request": {"method": "GET", "url": url},
                "received_at_ns": received,
                "status": answer.status,
                "headers": {h: answer.headers[h] for h in KEPT_HEADERS if h in answer.headers},
                "body": text,
            }
            ok = answer.status == 200
            if live and ok:
                raw_key = self.store.keep_line(call, name, record)
            else:
                raw_key = self.store.keep(call, name, record)
            if answer.status == 429 and attempt < self.retries:
                self.health.rate_limited += 1
                retry_after = answer.headers.get("retry-after", "")
                self.sleep(float(retry_after) if retry_after.isdigit() else 2.0**attempt)
                continue
            if answer.status == NOT_FOUND:
                # An answer: the venue knows nothing by that name.
                self.health.last_ok_ns = received
                raise VenueError(call, answer.status, _message(text), raw_key)
            if not ok:
                self._failed(f"{call}: {answer.status} {_message(text)}")
                raise VenueError(call, answer.status, _message(text), raw_key)
            try:
                value = json_decimal(text)
            except json.JSONDecodeError as broken:
                self._failed(f"{call}: not JSON")
                raise VenueError(call, answer.status, f"not JSON: {broken}", raw_key) from None
            self.health.last_ok_ns = received
            # A live answer unchanged since it was first kept is that answer:
            # its line, and the time it first arrived.
            return Fetched(value, raw_key, self.store.received(raw_key, received))
        raise AssertionError("unreachable")

    def _failed(self, why: str) -> None:
        self.health.failures += 1
        self.health.last_failed_ns = self.clock_ns()
        self.health.last_error = why

    def market(self, slug: str, live: bool = False) -> Fetched:
        """One market, by its slug; `live`, read again for its outcome, kept
        as a line of the day's live responses, added only when it changed."""
        return self._get("market", slug, f"/v1/market/slug/{_quoted(slug)}", live=live)

    def book(self, slug: str) -> Fetched:
        """A market's resting bids and offers, and its statistics."""
        return self._get("book", slug, f"/v1/markets/{_quoted(slug)}/book", live=True)

    def settlement(self, slug: str, live: bool = False) -> Fetched:
        """A market's settlement price; a 404 where it states none."""
        return self._get("settlement", slug, f"/v1/markets/{_quoted(slug)}/settlement", live=live)


def _quoted(slug: str) -> str:
    return urllib.parse.quote(slug, safe="")


def _message(text: str) -> str:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text[:200]
    if isinstance(parsed, dict):
        said = parsed.get("error", parsed)
        if isinstance(said, str):
            return said[:200]
        if isinstance(said, dict) and "message" in said:
            return str(said["message"])[:200]
    return text[:200]
