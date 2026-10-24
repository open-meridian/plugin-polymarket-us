"""Polymarket US's side of the data role's checks: this plugin's synthetic
exchanges, named for what each of the checks asks a source to present.

tests/test_data_role.py runs the SDK's checks for an event-contract venue
(`meridian.roles.data.testing.EventContractsChecks`) -- the data suite
unchanged, the venue's work past the suite's cases, its outcomes, and the
pages -- against this plugin's own conversion; this module is the one place
they learn which venue they are holding. Each answer comes through the
plugin's real client, raw records and reading (synthetic.py's transport over
the exchanges this package carries, `src/polymarket_us/synthetic/`), with
invented markets, slugs and values; real recordings are never committed (the
plan's Q11).
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from meridian.edge import RawStore
from meridian.roles.data.event_contracts import Market
from meridian.roles.data.testing import EVENT_CONTRACTS_NOT_PRESENTED

from polymarket_us import page
from polymarket_us.convert import PolymarketUsMarket
from polymarket_us.synthetic import Synthetic
from polymarket_us.venue import Polymarket, RateLimiter

__all__ = ["page"]

SYNTHETIC = Path(__file__).parent.parent / "src" / "polymarket_us" / "synthetic"

#: The venue's name as a symbol's source, and the plugin's.
VENUE = "polymarket-us"
#: The suite's clock: 2026-10-10 12:00 UTC.
NOW_NS = 1_791_633_600 * 1_000_000_000
TODAY = date(2026, 10, 10)

#: A market with both sides of its book and a last trade: one instrument, its
#: YES side the contract.
BASE = "syn-nfl-aar-bob-2026-12-06"
#: Its last trade's price, its best bid and offer and their sizes, in dollars.
LAST = "0.4400"
BID, BID_SIZE = "0.4300", "550.5000"
ASK, ASK_SIZE = "0.4500", "125.2500"
#: What one contract pays if the event happens, in the venue's cash.
PAYOUT, CASH = "1.00", "USD"
#: A market whose prices have more places than a float holds.
EXACT = "syn-crypto-btc-above-2026-12-31-150000"
EXACT_LAST = "0.123456789012345678"
#: A market with bids and no offer.
ONE_SIDED = "syn-weather-nyc-snow-2026-12-25"
#: A market of three sides, not one instrument's long and short side.
NOT_BINARY = "syn-mlb-ws-2026-three-sides"
#: Polymarket US prices in US dollars: no stablecoin, so its cash is a
#: currency code.
STABLE = False

# ── Outcomes (contract v23) ─────────────────────────────────────────────────

#: A market Polymarket US has resolved, its long side the winner: its
#: outcome from the contract's own side, final, at the settlement price it
#: states, its word that price as stated.
RESOLVED = "syn-nfl-cra-dev-2026-10-04"
RESOLVED_STAGE = "OUTCOME_STAGE_FINAL"
WORD = ("polymarket-us:settlement", "1")
#: A market resolved with its long side the loser: it settles at nothing.
RESOLVED_LOSER = "syn-nfl-elk-fox-2026-10-04"
#: A market settled at a last fair market price: part of its payout.
PARTIAL, PARTIAL_VALUE = "syn-nfl-gnu-hog-2026-10-04", "0.45"
#: A market resolved whose settlement Polymarket US does not answer yet.
UNSETTLED = "syn-nfl-ibx-jag-2026-10-04"
#: A market past its end whose final settlement is not yet published.
PENDING = "syn-nfl-kit-lyn-2026-10-09"
#: No later stage: Polymarket US publishes an outcome only once it is final.
LATER: tuple[tuple[Path, str, int], ...] = ()
#: The suite's outcome cases as Polymarket US presents them: an outcome
#: recorded at the stage it states, final (the case takes determined or
#: final, ruled 2026-10-13), and a partial payout. A dispute it never states:
#: see NOT_PRESENTED.
DETERMINED: str | None = RESOLVED
DISPUTED: tuple[str, tuple[Path, ...]] | None = None

#: The suite's cases Polymarket US never presents here, each with why: the
#: live dataset publishes prices and quotes now, per contract, in dollars,
#: and the outcomes dataset each final settlement. From contract v27 the SDK
#: names an event-contract venue's own (`EVENT_CONTRACTS_NOT_PRESENTED`): the
#: rates cases; the dataset's liveness, since Polymarket US is polled over
#: REST and no stream gives a heartbeat; `queries-the-lake-within-bounds`,
#: about trades, which it records none of; and the feed delay, about
#: `latency`, which core receives from contract v28 (ruling 518).
NOT_PRESENTED = {
    **EVENT_CONTRACTS_NOT_PRESENTED,
    "a-daily-close": "its live dataset publishes prices and quotes now, and no daily closes",
    "the-forming-day-restated": "its live dataset publishes no daily closes to restate",
    "a-daily-bar": "it publishes no bars: Polymarket US's price history is book-derived display "
    "prices, not trades, and states no open, high, low or close per day",
    "an-fx-rate": "it prices event contracts, and no currency's rate against another",
    "a-stablecoin-quote": "its prices are in US dollars, and it quotes nothing in a stablecoin",
    "a-subject-another-source-resolved": "its subjects are event contracts, and no security",
    "a-trade-recorded": "its live dataset publishes prices and quotes, and no trades",
    "the-makers-side-inverted": "its live dataset publishes no trades",
    "a-condition-converted": "its live dataset publishes no trades",
    "a-condition-not-converted": "its live dataset publishes no trades",
    "a-trade-withdrawn": "its live dataset publishes no trades",
    "a-standing-want-streamed": "its live dataset publishes no trades to stream",
    "the-takers-side-stated": "its live dataset publishes no trades",
    "a-restarts-gap-backfilled": "its live dataset publishes no trades, so a restart leaves no "
    "gap of trades to read back",
    "reads-a-calendar": "it records event contracts' prices and quotes as they are polled: it "
    "reads no settlement calendar",
    "asks-for-a-settlement-date": "it records prices and quotes as published; an event contract "
    "settles on its outcome, and it never computes a settlement date",
    "restates-a-disputed-outcome": "Polymarket US publishes an outcome only once its final "
    "settlement is published, and states no dispute: no outcome is recorded before the final one "
    "to be restated as disputed",
    # Contract v26 (W3.29): the venue's events, as convert.py says.
    "reports-an-event-group": "Polymarket US groups markets into events, but a market's answer "
    "names no event and no public read answers a market's event: finding it would mean reading "
    "the venue's whole event list, which the plugin never reads, or parsing the market's slug, "
    "which Polymarket US says not to do",
    "reports-a-flag-the-venue-does-not-state": "it reports no event group (see "
    "reports-an-event-group), so no flag to report as not stated",
}


def _instant(_: float) -> None:
    return None


def market(now_ns: int = NOW_NS, directory: Path | None = None) -> Market:
    """Polymarket US's synthetic exchange through the plugin's own client, its
    answers kept in a fresh store."""
    store = RawStore(Path(tempfile.mkdtemp(prefix="polymarket-us-raw-")))
    client = Polymarket(
        store,
        transport=Synthetic(directory or SYNTHETIC),
        limiter=RateLimiter(1000.0, 1000, sleep=_instant),
        clock_ns=lambda: now_ns,
        sleep=_instant,
    )
    return PolymarketUsMarket(client, "synthetic")


def calls(market: Any) -> list[str]:
    """The URLs the plugin asked of the venue, in order, from its raw records."""
    return [r["request"]["url"] for r in market.client.store.records()]
