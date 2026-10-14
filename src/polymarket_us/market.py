"""What a venue's event contracts come to before they become the lake's rows:
the venue's own words read, nothing of the contract's yet.

`convert.py` reads Polymarket US's responses into these values -- every
number a `Decimal` from the venue's own text, never a float; a value that
would not read kept as the venue sent it -- and `dgm.py` turns them into the
lake's prices, quotes and outcomes. So Polymarket US's vocabulary stops at
`convert.py`.

- `Cash`: the asset the venue's prices and payouts are in: a currency by its
  ISO 4217 code (Polymarket US's dollar), or a venue's own
  token instrument, known by its code with the venue as source (a token,
  never its currency: the product owner's ruling of 2026-10-03).
- `Contract`: one binary event contract, by the venue's own code for it --
  Polymarket US's market slug -- with the venue's
  words for what it pays on, what one contract pays if the event happens
  (`payout`, in the venue's cash) and when trading in it closes.
- `Tick`: the last trade's price, per contract; `Top`: the best bid and
  offer, each with its size in contracts, a side with no order None.
- `Resolution` (contract v23): the venue's determination of a contract,
  from the contract's own side, at the stage the venue states -- what one
  contract settles at, the venue's word for it as reported, and when it paid
  out -- read from the same answer as the contract.
- `Unread`: a value that did not read as a number, kept as sent.

A price is money per contract, never a probability (plans/the-lake-prices-
the-book, "The event contract"): the implied probability is a price over
the payout, a reader's computation, and nothing here stores it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

NANOS_PER_SECOND = 1_000_000_000
SECONDS_PER_DAY = 86_400

#: The contract's Decimal: at most 18 places and 38 digits (meridian.Money).
MOST_PLACES = 18
MOST_DIGITS = 38


@dataclass(frozen=True)
class Unread:
    """A venue's value that did not read as the contract's number: its field
    in the venue's response, and its text as sent."""

    field: str
    text: str


def json_decimal(body: str | bytes) -> Any:
    """A JSON body with every number that is not a whole one a `Decimal` from
    its own text: no float ever exists."""
    return json.loads(body, parse_float=Decimal)


def number(value: object) -> Decimal | None:
    """A venue's figure as the contract's number, from its text: a string or a
    JSON number read by `json_decimal`. None where it is not a finite number,
    or holds more places or digits than the contract's Decimal does; never
    rounded."""
    if isinstance(value, bool) or value is None or isinstance(value, float):
        return None
    try:
        amount = Decimal(value) if isinstance(value, int | Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    sign, digits, exponent = amount.as_tuple()
    places = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    if places > MOST_PLACES or len(digits) > MOST_DIGITS:
        return None
    return amount


def utc_day(at_s: int) -> date:
    """The UTC date the second `at_s` falls on."""
    return date.fromordinal(date(1970, 1, 1).toordinal() + at_s // SECONDS_PER_DAY)


@dataclass(frozen=True)
class Cash:
    """The asset a venue's prices and payouts are in."""

    #: The venue's own code for it (`USD`, `USDC`).
    code: str
    #: "currency" or "token".
    kind: str
    #: Its global identifier's scheme and value -- ("iso4217", "USD") -- or
    #: empty for the venue's own token instrument, known by its code alone.
    scheme: str = ""
    value: str = ""
    #: The venue's own name for it, offered as stated.
    name: str = ""

    @property
    def currency_code(self) -> str:
        """Its ISO 4217 code, for a currency; empty for a token."""
        return self.value if self.scheme == "iso4217" else ""


#: The stages of a determination, in the contract's words (the lake plan's
#: "vL1c", item 2): each venue's own states are read into these in its
#: `convert.py`.
PROPOSED, DETERMINED, DISPUTED, FINAL = "proposed", "determined", "disputed", "final"


@dataclass(frozen=True)
class Resolution:
    """The venue's determination of one contract, at one stage, as the venue
    states it: nothing of the contract's yet."""

    #: The stage, one of PROPOSED, DETERMINED, DISPUTED and FINAL.
    stage: str
    #: What one contract settles at, in the venue's cash; None where the
    #: venue states no value at this stage, or its value did not read.
    value: Decimal | None
    #: The venue's own word for the determination, as reported: where it is
    #: in the venue's answer (`polymarket-us:settlement`), its code and its
    #: text. Empty
    #: where the venue states none at this stage.
    scheme: str = ""
    word: str = ""
    text: str = ""
    #: When the venue determined it, where the venue says; 0 where it does
    #: not, and the determination is valid from when its answer arrived.
    determined_at_ns: int = 0
    #: When the venue paid out, as it states it; 0 until then, or where it
    #: states no payout.
    settled_at_ns: int = 0
    unread: tuple[Unread, ...] = ()


@dataclass(frozen=True)
class Contract:
    """One binary event contract, as the venue states it."""

    #: The venue's own code for it: a market ticker, a market slug.
    code: str
    #: What it pays on, in the venue's words: offered as the record's
    #: description, marked as another's wherever it reaches an agent.
    title: str
    #: Whether the venue states it as binary: it pays `payout` if the event
    #: happens and nothing if it does not.
    binary: bool
    #: What one contract pays if the event happens, in the venue's cash;
    #: None where the venue's statement did not read.
    payout: Decimal | None
    #: When trading in it closes, in UTC nanoseconds; 0 where the venue
    #: states none.
    closes_at_ns: int = 0
    #: Whether the venue trades it now, and its status in the venue's word.
    tradable: bool = True
    status: str = ""
    #: The venue's other code for the market it belongs to, where it gives
    #: one (Polymarket US's market ID).
    market: str = ""
    raw_key: str = ""
    unread: tuple[Unread, ...] = ()
    #: Its determination as the venue states it in the same answer (contract
    #: v23); None while the venue states none.
    resolution: Resolution | None = None
    #: When the answer it was read from first arrived, in UTC nanoseconds.
    read_at_ns: int = 0


@dataclass(frozen=True)
class Tick:
    """The last trade's price, per contract."""

    code: str
    price: Decimal | None
    #: When it traded, as the venue stated it; else when the response
    #: arrived, `stated` False.
    at_ns: int
    stated: bool
    #: The venue's own identity for it -- its trade ID -- where it gives one.
    ident: str = ""
    raw_key: str = ""
    unread: tuple[Unread, ...] = ()


@dataclass(frozen=True)
class Top:
    """The best bid and offer per contract, each with its size in contracts;
    a side with no order is None."""

    code: str
    bid: Decimal | None
    ask: Decimal | None
    bid_size: Decimal | None
    ask_size: Decimal | None
    at_ns: int
    stated: bool
    ident: str = ""
    raw_key: str = ""
    unread: tuple[Unread, ...] = ()


@dataclass
class Health:
    """How the venue has answered since the plugin started."""

    calls: int = 0
    rate_limited: int = 0
    failures: int = 0
    last_ok_ns: int = 0
    last_failed_ns: int = 0
    last_error: str = ""
    waited_seconds: float = 0.0


@dataclass(frozen=True)
class Limits:
    """What the venue allows, as its documentation says, and what the plugin
    spends of it."""

    allowed: str
    spent: str


@dataclass(frozen=True)
class Endpoint:
    """One way the plugin reaches the venue."""

    name: str
    address: str
    what: str


@dataclass
class Session:
    """What the plugin connects to, and how it is going."""

    mode: str
    endpoints: tuple[Endpoint, ...]
    limits: Limits
    health: Health = field(default_factory=Health)


class Market(Protocol):
    """A venue's public market data for event contracts, read into the values
    above; every response kept as a raw record before anything is read from
    it. A contract is read by its code, one at a time: the venue's whole
    listing is never read."""

    #: The venue's code as a `symbol`'s source (`polymarket-us`).
    venue: str
    #: The venue's name, as people know it.
    name: str
    #: The identifiers the venue is known by in a venue master, each
    #: (scheme, value, source): Polymarket US's MIC.
    venue_identifiers: tuple[tuple[str, str, str], ...]
    #: The asset its prices and payouts are in.
    cash: Cash
    session: Session

    def contract(self, code: str, watching: bool = False) -> Contract | None:
        """The contract the venue knows by `code`, or None where it knows
        none by it. `watching`: read again for its determination, the answer
        kept as a line of the day's live responses, added only when it
        changed."""
        ...

    def last(self, contract: Contract) -> Tick: ...

    def top(self, contract: Contract) -> Top: ...
