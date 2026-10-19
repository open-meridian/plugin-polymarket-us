"""Polymarket US's answers, read into the venue's values (the SDK's
`meridian.roles.data.event_contracts`): the one place Polymarket US's
vocabulary is read.

Polymarket US is QCX LLC, a CFTC-designated contract market, not the
international on-chain market: its own markets, identifiers and dollars
(docs.polymarket.us). Nothing of the international venue -- its outcome
tokens, their IDs, its USDC -- is read or named here.

- **The cash** is the US dollar, by its ISO 4217 code: every amount
  Polymarket US states is `{"value": "0.55", "currency": "USD"}`, and a
  winning contract settles at $1.00 ("Market Resolution"). An amount in any
  other currency is kept as sent and never read as a price.
- **A contract** is one Polymarket US market, by its slug
  (`aec-nfl-kc-phi-2026-02-09`), which names its one instrument: a market
  "has one instrument" and its NO side is that instrument sold, a short
  position, with no NO shares of its own ("Market Structure"). So the
  plugin records the instrument -- the YES side, the market's long side --
  as one binary event contract, as plugin-kalshi records a Kalshi market's
  YES; its NO side is the same contract, held short. A market is taken as
  binary where its `marketSides` are one long side and one short side;
  any other market is not served. What one contract pays if the event
  happens is $1.00. Its words are the market's `question` and its long
  side's own words (its `description`, else the market's `title`); trading
  closes at its `endDate`; it trades while its `status` is
  `MARKET_STATUS_OPEN`.
- **Its book** is `/book`'s: its best bid the highest of `bids`, its best
  offer the lowest of `offers`, each `px` with its `qty` in contracts (a
  fractional contract possible), every price per contract in dollars as
  text; stated at its `transactTime`. The lighter `/bbo` is not read: its
  `bidShares` and `askShares` are each side's every level summed and
  rounded to two significant figures, never the best level's size.
- **The last trade** is the same answer's `stats.lastTradePx`, traded at
  its `stats.lastTradeSetTime`; Polymarket US gives a trade no identity
  there, so a row is keyed by the raw record's line. The book is read once
  for both, the last trade and then the quote, in the same pass.
- **What is not read as anything.** `stats.settlementPx` (and the BBO's
  `settlementPx`) is stated on an open market too, with a calculation
  method and a time of its own: a daily settlement price, never the
  market's outcome. `/v1/price-history` is book-derived display prices --
  the YES side's from the best ask, the NO side's from one less the best
  bid -- as floats, "not individual trades": neither a close nor a bar.
- **Its outcome** (contract v23; the lake plan's "vL1c") is read only once
  the market's `status` is `MARKET_STATUS_RESOLVED` -- "final settlement
  published; the outcome will not change" -- from `/settlement`'s
  `settlement`, the settlement price of the market's one instrument, the
  contract the plugin records: what one contract settles at, in dollars.
  So its stage is final. `MARKET_STATUS_RESOLVING` ("past expiry, final
  settlement not yet published -- payouts are pending") states no outcome,
  and Polymarket US publishes no proposed, determined or disputed outcome
  before the final one ("All resolutions are final", per its rulebook), so
  nothing is recorded before it. Polymarket US's word is the settlement
  price as it states it (`polymarket-us:settlement`): 1 pays, 0 pays nothing,
  and a price between -- an instrument that "may settle at last fair market
  prices" under its market's rules -- pays part. It states no time of
  determination or payout, so the outcome is valid from when the answer
  first stating it arrived, and its payout time stays unset; the outcome's
  raw record is the settlement answer.
- **A range market's bounds** (contract v26; the gaps spec's A4) are its
  `assetPriceTerms` (docs.polymarket.us, "Markets API Overview: Crypto Price
  Market Fields", and "Crypto Schema"): a `ASSET_PRICE_MARKET_TYPE_RANGE`
  bucket's `rangeLower` and `rangeUpper`, each inclusive, the open side of a
  tail (`rangeKind` `_BELOW` or `_ABOVE`) null; an
  `ASSET_PRICE_MARKET_TYPE_ABOVE_BELOW` market's `strike`, a floor inclusive
  -- its long side "pays when the settlement value is greater than or equal
  to the strike". Up/Down (its reference stamped only once its window opens)
  and One-Touch (touched at any moment of its window) state no bound, nor
  does any market without `assetPriceTerms`. Each amount is in dollars, as
  any other. Both are the contract's own (`Contract.floor`, `.cap`, from
  0.3.1 on open-meridian 0.31.1, whose contract map keeps them);
  `bound_unit` is left empty: a bound here is a price, whose unit is an
  instrument's ID the conversion does not hold. A bound reaches no row in
  contract v26; its data path is contract v27's (ruling 464).
- **Events are not reported** (contract v26, W3.29). Polymarket US groups
  its markets into events -- `/v1/events/slug/{slug}`, its `markets` nested,
  its `seriesSlug` its series ("Events API Overview"; "Events & Markets") --
  but states neither flag on an event, and a market's own answer names no
  event: no public read answers the event of a market. Finding it would mean
  reading the venue's whole event list, which the plugin never reads, or
  parsing the market's slug, which Polymarket US says not to do ("Do not
  parse the instrument symbol or slug", "Crypto Schema"). So no event is
  read and no group reported; the data suite's two cases are not presented.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from meridian.roles.data import NANOS_PER_SECOND, Endpoint, Limits, Session, Unread, number
from meridian.roles.data.event_contracts import (
    FINAL,
    Bound,
    Cash,
    Contract,
    Resolution,
    Tick,
    Top,
)

from .venue import BURST, GATEWAY, NOT_FOUND, RATE_PER_SECOND, Fetched, Polymarket, VenueError

VENUE = "polymarket-us"
NAME = "Polymarket US"
#: What the venue entitles this plugin to: its public market data, no key.
ENTITLED = "Public market data: a contract is read only for a subject the lake asked for"
#: How a Polymarket US market makes a contract, said on the Datasets page.
VENDOR_NOTE = (
    "Each market is one instrument, its YES side, paying one dollar if the event happens; "
    "its NO side is the same instrument held short."
)
#: Polymarket US in the venue master: QCX LLC's ISO 10383 MIC.
VENUE_IDENTIFIERS: tuple[tuple[str, str, str], ...] = (("iso10383", "QCEX", ""),)
CASH = Cash("USD", "currency", "iso4217", "USD", "US dollar")
#: The currency every amount Polymarket US states is in.
CURRENCY = "USD"
#: What one contract pays if the event happens: $1.00.
PAYOUT = Decimal("1.00")
#: The status in which Polymarket US trades a market.
TRADING = "MARKET_STATUS_OPEN"
#: The status that states a market's final settlement published.
RESOLVED = "MARKET_STATUS_RESOLVED"
#: Where Polymarket US's word for an outcome is, as reported.
SETTLEMENT = "polymarket-us:settlement"
#: How long a book read for the last trade serves the quote that follows.
BOOK_HELD_NS = NANOS_PER_SECOND

LIMITS = Limits(
    allowed="Polymarket US limits its public reads per IP; its market data needs no key",
    spent=f"At most {RATE_PER_SECOND:g} a second, bursts of {BURST}; a 429 waited out",
)

_RFC3339 = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})"
)


def rfc3339_ns(text: str) -> int:
    """An RFC 3339 time, to the nanosecond (datetime holds only six digits)."""
    match = _RFC3339.fullmatch(text)
    if match is None:
        raise ValueError(f"{text!r} is not an RFC 3339 time")
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    offset = _dt.timedelta()
    if zone != "Z":
        sign = 1 if zone[0] == "+" else -1
        offset = sign * _dt.timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
    moment = _dt.datetime(
        int(year), int(month), int(day), int(hour), int(minute), int(second),
        tzinfo=_dt.timezone(offset),
    )  # fmt: skip
    return int(moment.timestamp()) * NANOS_PER_SECOND + int((fraction or "0").ljust(9, "0"))


def _when(text: object) -> int:
    try:
        return rfc3339_ns(str(text)) if text else 0
    except ValueError:
        return 0


def _text(value: object) -> str:
    return "" if value is None else str(value)


def dollars(amount: object, field: str, unread: list[Unread]) -> Decimal | None:
    """An amount Polymarket US states, `{"value": ..., "currency": "USD"}`, in
    dollars from its own text; an amount in another currency, or whose value
    does not read, kept as sent. None where there is none."""
    if amount is None:
        return None
    if not isinstance(amount, Mapping):
        unread.append(Unread(field, _text(amount)))
        return None
    currency = _text(amount.get("currency"))
    if currency != CURRENCY:
        unread.append(Unread(f"{field}.currency", currency or "?"))
        return None
    value = number(amount.get("value"))
    if value is None:
        unread.append(Unread(f"{field}.value", _text(amount.get("value"))))
    return value


def _words(body: Mapping[str, Any], long: Mapping[str, Any] | None) -> str:
    """What the contract pays on, in Polymarket US's words: the market's
    question and its long side's own words."""
    question = _text(body.get("question")).strip()
    title = _text(body.get("title")).strip()
    side = _text(long.get("description") if long else "").strip()
    said = side if side and side.lower() != "yes" else title
    if not question:
        return said
    return f"{question}: {said}" if said and said != question else question


def resolution(body: Mapping[str, Any]) -> Resolution:
    """A market's outcome from `/settlement`'s answer: final, at the
    settlement price of its one instrument, as stated."""
    stated = body.get("settlement")
    value = number(stated)
    word = _text(stated)
    return Resolution(
        stage=FINAL,
        value=value,
        scheme=SETTLEMENT if word else "",
        word=word,
        text=word,
        unread=() if value is not None else (Unread("settlement", word or "?"),),
    )


#: The market families whose terms state a bound, as `assetPriceTerms`
#: names them.
RANGE = "ASSET_PRICE_MARKET_TYPE_RANGE"
ABOVE_BELOW = "ASSET_PRICE_MARKET_TYPE_ABOVE_BELOW"


def bounds(body: Mapping[str, Any], unread: list[Unread]) -> tuple[Bound | None, Bound | None]:
    """A range market's floor and cap as its `assetPriceTerms` state them,
    each inclusive; neither for a market whose terms state no bound."""
    terms = body.get("assetPriceTerms")
    if not isinstance(terms, Mapping):
        return None, None
    kind = _text(terms.get("marketType"))
    field = "assetPriceTerms"
    if kind == RANGE:
        floor = dollars(terms.get("rangeLower"), f"{field}.rangeLower", unread)
        cap = dollars(terms.get("rangeUpper"), f"{field}.rangeUpper", unread)
        return (
            Bound(floor, True) if floor is not None else None,
            Bound(cap, True) if cap is not None else None,
        )
    if kind == ABOVE_BELOW:
        strike = dollars(terms.get("strike"), f"{field}.strike", unread)
        return (Bound(strike, True) if strike is not None else None), None
    return None, None


def contract(
    body: Mapping[str, Any],
    raw_key: str,
    received_ns: int = 0,
    settled: Fetched | None = None,
) -> Contract:
    """One market, from `/v1/market/slug/{slug}`'s `market`; with its outcome
    where the market is resolved and `/settlement` answered (`settled`), the
    outcome's raw record and time that answer's."""
    unread: list[Unread] = []
    sides = body.get("marketSides")
    sides = [s for s in sides if isinstance(s, Mapping)] if isinstance(sides, Sequence) else []
    long = [s for s in sides if s.get("long") is True]
    short = [s for s in sides if s.get("long") is False]
    binary = len(sides) == 2 and len(long) == 1 and len(short) == 1
    for side in sides:
        dollars(side.get("quote"), "marketSides.quote", unread)
    floor, cap = bounds(body, unread)
    status = _text(body.get("status"))
    if status in ("", "MARKET_STATUS_UNSPECIFIED"):
        tradable = body.get("active") is True and body.get("closed") is not True
    else:
        tradable = status == TRADING
    outcome = None
    if settled is not None and isinstance(settled.value, Mapping):
        outcome = resolution(settled.value)
        raw_key, received_ns = settled.raw_key, settled.received_at_ns
    return Contract(
        code=str(body["slug"]),
        title=_words(body, long[0] if long else None),
        binary=binary,
        payout=PAYOUT,
        closes_at_ns=_when(body.get("endDate")),
        tradable=tradable,
        status=status,
        market=_text(body.get("id")),
        raw_key=raw_key,
        unread=tuple(unread),
        resolution=outcome,
        read_at_ns=received_ns,
        floor=floor,
        cap=cap,
    )


def _levels(
    levels: object, side: str, unread: list[Unread]
) -> list[tuple[Decimal, Decimal | None]]:
    """A side's levels, each `{"px": amount, "qty": "..."}`, read; a level
    whose price does not read kept as sent."""
    read: list[tuple[Decimal, Decimal | None]] = []
    held = levels if isinstance(levels, Sequence) and not isinstance(levels, str) else []
    for level in held:
        if not isinstance(level, Mapping):
            unread.append(Unread(f"marketData.{side}", _text(level)))
            continue
        price = dollars(level.get("px"), f"marketData.{side}.px", unread)
        if price is None:
            continue
        size = number(level.get("qty"))
        if size is None:
            unread.append(Unread(f"marketData.{side}.qty", _text(level.get("qty"))))
        read.append((price, size))
    return read


def _data(body: object) -> Mapping[str, Any]:
    data = body.get("marketData") if isinstance(body, Mapping) else None
    return data if isinstance(data, Mapping) else {}


def top(of: Contract, body: Mapping[str, Any], raw_key: str, received_ns: int) -> Top:
    """The contract's best bid and offer, each with its size."""
    unread: list[Unread] = []
    data = _data(body)
    bids = _levels(data.get("bids"), "bids", unread)
    offers = _levels(data.get("offers"), "offers", unread)
    bid = max(bids, key=lambda level: level[0]) if bids else None
    ask = min(offers, key=lambda level: level[0]) if offers else None
    at = _when(data.get("transactTime"))
    return Top(
        code=of.code,
        bid=bid[0] if bid else None,
        ask=ask[0] if ask else None,
        bid_size=bid[1] if bid else None,
        ask_size=ask[1] if ask else None,
        at_ns=at or received_ns,
        stated=bool(at),
        raw_key=raw_key,
        unread=tuple(unread),
    )


def tick(of: Contract, body: Mapping[str, Any], raw_key: str, received_ns: int) -> Tick:
    """The contract's last trade, from the book's statistics; no trade, no
    price."""
    stats = _data(body).get("stats")
    stats = stats if isinstance(stats, Mapping) else {}
    unread: list[Unread] = []
    price = dollars(stats.get("lastTradePx"), "stats.lastTradePx", unread)
    at = _when(stats.get("lastTradeSetTime"))
    return Tick(
        code=of.code,
        price=price,
        at_ns=at or received_ns,
        stated=bool(at),
        raw_key=raw_key,
        unread=tuple(unread),
    )


@dataclass(frozen=True)
class _Book:
    code: str
    fetched: Fetched
    at_ns: int


class PolymarketUsMarket:
    """Polymarket US's market data, as the shared data plugin's work asks for
    it."""

    venue = VENUE
    name = NAME
    venue_identifiers = VENUE_IDENTIFIERS
    cash = CASH

    def __init__(self, client: Polymarket, mode: str = "live") -> None:
        self.client = client
        address = GATEWAY if mode == "live" else f"{mode}: no call leaves the deployment"
        self.session = Session(
            mode=mode,
            endpoints=(
                Endpoint(
                    "REST", address, "a market and its settlement, its book and its last trade"
                ),
            ),
            limits=LIMITS,
            health=client.health,
        )
        #: The book read for a last trade, held for the quote that follows.
        self._book: _Book | None = None

    def contract(self, code: str, watching: bool = False) -> Contract | None:
        try:
            fetched = self.client.market(code, live=watching)
        except VenueError as refused:
            if refused.status == NOT_FOUND:
                return None
            raise
        body = fetched.value.get("market") if isinstance(fetched.value, Mapping) else None
        if not isinstance(body, Mapping) or "slug" not in body:
            return None
        settled = None
        if _text(body.get("status")) == RESOLVED:
            try:
                settled = self.client.settlement(code, live=watching)
            except VenueError as refused:
                if refused.status != NOT_FOUND:
                    raise
        return contract(body, fetched.raw_key, fetched.received_at_ns, settled)

    def _read_book(self, of: Contract, held: bool) -> Fetched:
        """The contract's book: the one just read for its last trade, where
        `held` and it is that contract's and within the second, else read."""
        book, self._book = self._book, None
        now = self.client.clock_ns()
        if held and book is not None and book.code == of.code and now - book.at_ns < BOOK_HELD_NS:
            return book.fetched
        return self.client.book(of.code)

    def last(self, of: Contract) -> Tick:
        fetched = self._read_book(of, held=False)
        self._book = _Book(of.code, fetched, self.client.clock_ns())
        return tick(of, fetched.value, fetched.raw_key, fetched.received_at_ns)

    def top(self, of: Contract) -> Top:
        fetched = self._read_book(of, held=True)
        return top(of, fetched.value, fetched.raw_key, fetched.received_at_ns)
