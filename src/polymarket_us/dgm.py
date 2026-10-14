"""The data plugin's work (the role `data`, contracts v20 and v23): a venue's
binary event contracts into the lake, converted at the edge.

Polymarket US's answers are read in `convert.py` into the values of
market.py, and everything from there to the lake is here, once.

**One dataset** (declaration.py; the plan's Q21): `live`, each contract's last
trade price and best bid and offer as prices, and its best bid and offer with
their sizes as a quote, recorded at most once a second per subject. A price
is money per contract in the venue's cash, never a probability; the implied
probability is a reader's computation (W10.6; plans/the-lake-prices-the-book,
"The event contract").

**And `outcomes`** (contract v23; the lake plan's "vL1c"): each contract's
determination as the venue states it, from the contract's own side -- it
pays its full payout, pays nothing, or pays part -- with what one contract
settles at, in the venue's cash, the venue's own word kept as reported, and
when the venue paid out where it says. One row key per contract
(`<code>:outcome`); each change of stage the venue states (proposed,
determined, disputed, final) or of its determination is a new version under
it, and nothing is sent while the venue's statement is unchanged (the
contract map keeps what was last recorded). A stage stated with no
determination of its own carries the determination already recorded, and
is not recorded before one is. Its valid time is the determination's: the
venue's own time where it states one (an event source time), else when the
answer first stating it arrived, kept from version to version until the
determination itself changes. It names no business date and answers no want:
it is recorded, unasked, for each contract a subject the lake asked for is
-- when the subject is named, when the contracts are read again each day,
and each minute for a contract past its close or no longer trading, until
its final stage is recorded.

**Per subject wanted, never the whole venue** (W3.6, W3.1, W3.14;
contracts.py): each subject the lake asks for is the deployment's record,
read and named as one of the venue's contracts by its identifiers -- the
venue's own code first (`symbol` with the venue as source), then another
source's symbol that the venue answers as one of its contracts, the latter
never for a record that is a security (a class other than an event contract,
a security's identifier) or a type other than a binary event contract --
and the venue asked for that one contract. A contract the venue does not
state as binary, or whose payout its record states otherwise (another
amount, another asset), is not served. Where the record lacks the venue's
code, or its class or type, the venue's code is reported beside the one it
matched (W3.1) with the class, the type and the venue's words offered, so a
person completing the record has them; where that resolve meets another
record it is reported (W3.2), and the subject is still served.

**The cash and the venue** are resolved once: the asset the venue's prices
and payouts are in by the identifiers the venue's own statements give it --
a currency by its ISO 4217 code, the venue's own token by its code with the
venue as source -- and the venue by its identifiers in the venue master.
What does not resolve is reported (W3.2, W3.15) and never guessed: nothing is
priced in a cash that did not resolve, and a venue not held is left empty on
each row with its code beside it as reported, asked again at the next day's
reading.

**A row** names the contract's record as its subject, its dataset, the
venue's ID, its time and the raw record it was read from (raw.py). A price
is a `Money` in the venue's cash -- a currency by its code, a token by its
own instrument, never a fiat code -- from the venue's own text, and one
outside nothing to the payout is left unrecorded and counted. A quote keeps
a side the venue states no order on unset. Every row is keyed by its
contract, kind and the venue's identity for what it read, or the line of the
raw record it was first read from, so an answer read again unchanged is the
same row.

**Wants** (W10.7): the lake asks for the latest of the live dataset, or a
day or range covering now, for subjects; each subject is recorded against
the want, or declined: `not_covered` where its record names none of the
venue's binary event contracts, `beyond_history` for a day or range already
past (the venue's public reads answer now), `source_silent` where the venue
states nothing for it. A standing want keeps its subjects current until it
is withdrawn, at most once a second.

**Its licences** (contract v20, W10.9): it reads its own declared dataset's
licence from the deployment (`list_datasets`), on start and each minute, so
its Datasets page says "Licensed" or "Not licensed yet" exactly. It records
no trades, so a restart leaves no gap of trades to read back (W10.6): the
live dataset is read again when it is next wanted.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import meridian
from meridian import Money, ObservationMeta, Outcome, Price, Quote, SourceTime
from meridian.operations import as_money
from meridian.plugin.v1 import operations_pb2 as ops

from .contracts import ContractMap, Mapped, Recorded
from .market import FINAL, NANOS_PER_SECOND, Contract, Market, Tick, Top, Unread, utc_day

log = logging.getLogger(__name__)

LIVE = "live"
#: The dataset of each contract's outcome (contract v23).
OUTCOMES = "outcomes"
PRICE, QUOTE = "meridian.v1.Price", "meridian.v1.Quote"
#: The live dataset's pace: each subject at most once a second.
LIVE_EVERY_SECONDS = 1.0
#: How often a contract past its close, its final stage not yet recorded,
#: is read again for its determination.
OUTCOME_EVERY_SECONDS = 60.0
#: Each contract, and the venue, read again once a day.
REREAD_SECONDS = 86_400
#: The lake's batch: 1 to 500 rows.
BATCH = 500
#: How many of the wants heard the Datasets page lists.
RECENT = 200
#: The longest description offered from the venue's words.
MOST_DESCRIPTION = 500

#: A record's classes that may be an event contract's: none yet, or one.
_EVENT_CLASSES = {ops.ASSET_CLASS_UNSPECIFIED, ops.ASSET_CLASS_EVENT_CONTRACT}
#: A record's types that may be a binary event contract's: none yet, or one.
_BINARY_TYPES = {ops.INSTRUMENT_TYPE_UNSPECIFIED, ops.INSTRUMENT_TYPE_BINARY_EVENT_CONTRACT}
#: Identifiers only a security carries.
_SECURITY_SCHEMES = {"cusip", "isin", "sedol", "figi"}
_LIVE_KINDS = {ops.PRICE_KIND_LAST, ops.PRICE_KIND_BID, ops.PRICE_KIND_ASK}

#: Why a subject is not served, as the Datasets page counts them.
NOT_A_CONTRACT = "its record names none of the venue's binary event contracts"
PAYOUT_DIFFERS = "its record states another payout"
NOT_READ = "its record could not be read"

Plugin = Any  # meridian.Plugin, or the suite's Recorder: the SDK's typed operations


@dataclass(frozen=True)
class Standing:
    """A standing want, kept current until it is withdrawn."""

    want_id: str
    dataset: str
    data_type: str
    subjects: tuple[str, ...]
    kinds: tuple[int, ...]
    since_ns: int


@dataclass(frozen=True)
class Heard:
    """One want as the Datasets page lists it."""

    want_id: str
    dataset: str
    asked: str
    subjects: int
    recorded: int
    declined: int
    standing: bool
    at_ns: int


@dataclass
class Counts:
    """What the plugin has sent the lake since it started."""

    recorded: int = 0
    restated: int = 0
    unchanged: int = 0
    unread: int = 0
    declined: int = 0
    wants: int = 0
    #: When it last recorded, 0 before it has.
    last_ns: int = 0


@dataclass
class Venue:
    """The venue's ID in the venue master, once resolved."""

    venue_id: str = ""
    missing: bool = False
    asked: bool = False


@dataclass
class Dgm:
    """The plugin's work: resolving, recording, and answering wants."""

    plugin: Plugin
    market: Market
    contracts: ContractMap
    clock_ns: Callable[[], int] = time.time_ns
    standing: dict[str, Standing] = field(default_factory=dict)
    counts: Counts = field(default_factory=Counts)
    venue: Venue = field(default_factory=Venue)
    heard: deque[Heard] = field(default_factory=lambda: deque(maxlen=RECENT))
    #: Whether the deployment answers this plugin's ResolveInstrument: a
    #: runtime from before the ruling of 2026-10-10 does not.
    reads_instruments: bool = True
    #: Subjects not served, and why, until the contracts are read again.
    unnamed: dict[str, str] = field(default_factory=dict)
    #: Its datasets a deployment admin has licensed, as rows name them, as
    #: last read (contract v20); and whether the deployment answers that read.
    licensed: frozenset[str] = frozenset()
    reads_licences: bool = True
    #: What it has sent the lake of its outcomes (contract v23), apart from
    #: the live dataset's.
    outcome_counts: Counts = field(default_factory=Counts)
    #: Contracts whose stated determination did not read, counted once each.
    unreadable: set[str] = field(default_factory=set)

    # ── Names ────────────────────────────────────────────────────────────

    def dataset(self, key: str) -> str:
        """A dataset as rows name it: the instance, a colon and the key."""
        return f"{self.plugin.identity.instance_id}:{key}"

    def _key_of(self, dataset: str) -> str:
        instance, _, key = dataset.partition(":")
        return key if instance == self.plugin.identity.instance_id else ""

    def use(self, market: Market, contracts: ContractMap) -> None:
        """Answer from another source (synthetic mode switched): its own map,
        the venue asked again; standing wants carry over."""
        self.market, self.contracts, self.venue = market, contracts, Venue()
        self.unnamed.clear()

    # ── Licences ─────────────────────────────────────────────────────────

    async def read_licences(self) -> frozenset[str]:
        """Its own declared dataset's licence (contract v20, W10.9): whether a
        deployment admin has licensed it, by the name rows give it. A dataset
        with none is served by its catalogue's default terms until one is
        set. A runtime from before v20 does not answer, which is said once
        and leaves it "Not licensed yet"."""
        if not self.reads_licences:
            return self.licensed
        try:
            answered = await self.plugin.list_datasets()
        except meridian.NotGranted:
            log.warning("this data plugin may not read its datasets' licences")
            self.reads_licences = False
            return self.licensed
        mine = {self.dataset(LIVE), self.dataset(OUTCOMES)}
        self.licensed = frozenset(
            licence.dataset for licence in answered.licences if licence.dataset in mine
        )
        return self.licensed

    # ── Resolving ────────────────────────────────────────────────────────

    def venue_identifiers(self) -> list[ops.Identifier]:
        return [
            meridian.Identifier(scheme=scheme, value=value, source=source)
            for scheme, value, source in self.market.venue_identifiers
        ]

    async def venue_id(self) -> str:
        """The venue master's ID for the venue, asked once per reading by its
        identifiers; a venue not held is reported once and left empty."""
        if self.venue.asked:
            return self.venue.venue_id
        named = self.venue_identifiers()
        now = self.clock_ns()
        found = await self.plugin.resolve_venue(identifiers=named, as_of_ns=now)
        self.venue.asked = True
        if found.found and found.venue.venue_id:
            self.venue.venue_id, self.venue.missing = found.venue.venue_id, False
        else:
            self.venue.venue_id, self.venue.missing = "", True
            await self.plugin.report_missing_venue(
                source=self.market.venue,
                identifiers=named,
                as_of_ns=now,
                reason=found.miss_reason or "not_found",
                observed_at_ns=now,
            )
        return self.venue.venue_id

    def cash_identifiers(self) -> list[ops.Identifier]:
        """The identifiers the venue's own statements give its cash: a
        currency's ISO 4217 code, or the venue's own token by its code."""
        cash = self.market.cash
        if cash.scheme:
            return [meridian.Identifier(scheme=cash.scheme, value=cash.value)]
        return [meridian.Identifier(scheme="symbol", value=cash.code, source=self.market.venue)]

    async def cash_id(self) -> str:
        """The deployment's instrument for the venue's cash, resolved once
        (W3.1); what does not resolve is reported once per reason."""
        if self.contracts.cash_id:
            return self.contracts.cash_id
        cash = self.market.cash
        now = self.clock_ns()
        found = await self.plugin.resolve_identifier(
            identifiers=self.cash_identifiers(),
            as_of_ns=now,
            stated_asset_class="cash",
            stated_description=cash.name,
        )
        if found.found and found.instrument_id:
            self.contracts.cash_id = str(found.instrument_id)
            self.contracts.missing.pop(cash.code, None)
            self.contracts.save()
            return self.contracts.cash_id
        reason = ops.MissReason.Name(found.miss_reason or ops.MISS_REASON_NOT_FOUND)
        if self.contracts.missing.get(cash.code) != reason:
            await self.plugin.report_missing_instrument(
                source=self.market.venue,
                asset_class="cash",
                identifiers=self.cash_identifiers(),
                as_of_ns=now,
                reason=found.miss_reason or "not_found",
                observed_at_ns=now,
            )
        self.contracts.missing[cash.code] = reason
        return ""

    def identifiers(self, contract: Contract) -> list[ops.Identifier]:
        """The identifiers the venue's own statements give a contract: its
        code, as a `symbol` with the venue as source."""
        return [meridian.Identifier(scheme="symbol", value=contract.code, source=self.market.venue)]

    @staticmethod
    def _same(one: ops.Identifier, other: ops.Identifier) -> bool:
        return (one.scheme, one.value, one.source) == (other.scheme, other.value, other.source)

    def _candidates(self, record: ops.InstrumentRecord) -> list[ops.Identifier]:
        """The record's identifiers that may name one of the venue's
        contracts, in order: the venue's own code, then another source's
        symbol -- never for a record that is a security, or of another type."""
        held = list(record.identifiers)
        venue = self.market.venue
        own = [i for i in held if i.scheme == "symbol" and i.source == venue and i.value]
        if (
            record.asset_class not in _EVENT_CLASSES
            or record.instrument_type not in _BINARY_TYPES
            or any(i.scheme in _SECURITY_SCHEMES for i in held)
        ):
            return own
        return own + [i for i in held if i.scheme == "symbol" and i.source != venue and i.value]

    async def contract(self, code: str) -> Contract | None:
        """The venue's contract by its code: as read already, else asked of
        the venue, one contract at a time."""
        held = self.contracts.contracts.get(code)
        if held is not None:
            return held
        read: Contract | None = await self._asked(self.market.contract, code)
        if read is not None:
            self.contracts.contracts[code] = read
        return read

    async def _payout_differs(self, record: ops.InstrumentRecord, contract: Contract) -> bool:
        """Whether the record states a payout the venue's does not match: another
        amount, or another asset than the venue's cash."""
        if not record.HasField("binary_event_contract") or contract.payout is None:
            return False
        stated = as_money(record.binary_event_contract.payout)
        if not stated.amount and not stated.currency_code and not stated.instrument_id:
            return False
        if Decimal(stated.amount) != contract.payout:
            return True
        cash = self.market.cash
        if stated.currency_code:
            return stated.currency_code != cash.currency_code
        return stated.instrument_id != await self.cash_id()

    async def _join(
        self, subject: str, contract: Contract, matched: ops.Identifier, record: Any
    ) -> None:
        """Report the venue's code beside the one the record matched (W3.1),
        with the class, the type and the venue's words offered, where the
        record lacks any of them; meeting another record is a miss (W3.2),
        reported once, and the subject is served all the same."""
        held = list(record.identifiers)
        own = self.identifiers(contract)
        if (
            all(any(self._same(o, h) for h in held) for o in own)
            and record.asset_class == ops.ASSET_CLASS_EVENT_CONTRACT
            and record.instrument_type == ops.INSTRUMENT_TYPE_BINARY_EVENT_CONTRACT
        ):
            return
        named = own + ([] if any(self._same(matched, o) for o in own) else [matched])
        now = self.clock_ns()
        found = await self.plugin.resolve_identifier(
            identifiers=named,
            as_of_ns=now,
            stated_asset_class="event_contract",
            stated_instrument_type="binary_event_contract",
            stated_currency=self.market.cash.currency_code,
            stated_description=contract.title[:MOST_DESCRIPTION],
        )
        if found.found and found.instrument_id == subject:
            return
        # Matched another record: two records for one contract, which a
        # person merges (W3.13).
        miss = ops.MISS_REASON_AMBIGUOUS if found.found else found.miss_reason
        reason = ops.MissReason.Name(miss or ops.MISS_REASON_AMBIGUOUS)
        if self.contracts.missing.get(contract.code) != reason:
            await self.plugin.report_missing_instrument(
                source=self.market.venue,
                asset_class="event_contract",
                identifiers=named,
                as_of_ns=now,
                reason=miss or ops.MISS_REASON_AMBIGUOUS,
                observed_at_ns=now,
            )
        self.contracts.missing[contract.code] = reason

    async def _named(self, subject: str) -> str:
        """The venue's code for the contract a subject is, read from its
        record; empty, with why, where it names none of the venue's binary
        event contracts or cannot be read."""
        if not self.reads_instruments:
            self.unnamed[subject] = NOT_READ
            return ""
        try:
            found = await self.plugin.resolve_instrument(
                instrument_id=subject, as_of_ns=self.clock_ns()
            )
        except meridian.NotGranted:
            # A runtime from before the ruling of 2026-10-10 grants a data plugin no
            # read of what an instrument is (W3.6). Asked once, and said on
            # the Datasets page.
            log.warning("this dgm may not read an instrument's record; nothing is named")
            self.reads_instruments = False
            self.unnamed[subject] = NOT_READ
            return ""
        if not found.found:
            self.unnamed[subject] = NOT_READ
            return ""
        record = found.instrument
        for matched in self._candidates(record):
            contract = await self.contract(matched.value)
            if contract is None or not contract.binary:
                continue
            if await self._payout_differs(record, contract):
                log.warning("%s's record states another payout than %s's", subject, contract.code)
                self.unnamed[subject] = PAYOUT_DIFFERS
                return ""
            await self._join(subject, contract, matched, record)
            return contract.code
        self.unnamed[subject] = NOT_A_CONTRACT
        return ""

    async def name(self, subjects: Iterable[str]) -> None:
        """Name each subject not named yet as one of the venue's contracts, and
        resolve the venue's cash once one is; the map kept in storage."""
        changed = False
        for subject in subjects:
            if subject in self.contracts.subjects or subject in self.unnamed:
                continue
            code = await self._named(subject)
            if code:
                self.contracts.subjects[subject] = code
                changed = True
        # The cash is asked once a subject is named, and again after a miss
        # only when a subject is newly named or the day's reading cleared it.
        cash = self.market.cash.code
        if (
            self.contracts.subjects
            and not self.contracts.cash_id
            and (changed or cash not in self.contracts.missing)
        ):
            await self.cash_id()
        if changed:
            self.contracts.save()

    async def reread(self) -> ContractMap:
        """Read each contract serving a subject again from the venue, and ask
        for the venue again; a subject not named is read again when next
        asked."""
        for code in sorted(set(self.contracts.subjects.values())):
            read = await self._asked(self.market.contract, code)
            if read is not None:
                self.contracts.contracts[code] = read
        self.contracts.read_at_ns = self.clock_ns()
        self.contracts.missing.pop(self.market.cash.code, None)
        self.unnamed.clear()
        self.contracts.save()
        self.venue.asked = False
        await self.venue_id()
        await self._outcomes_of(self.contracts.mapped())
        return self.contracts

    # ── Rows ─────────────────────────────────────────────────────────────

    def _money(self, amount: Any, mapped: Mapped) -> Money:
        """An amount in the venue's cash: a currency by its code, the venue's
        token by its own instrument, never a fiat code."""
        code = self.market.cash.currency_code
        if code:
            return Money(amount, code)
        return Money(amount, instrument_id=mapped.cash_id)

    @staticmethod
    def _within(amount: Decimal | None, contract: Contract) -> bool:
        """Whether a price per contract is one: nothing to the payout."""
        if amount is None or amount < 0:
            return False
        return contract.payout is None or amount <= contract.payout

    def _unconverted(self, unread: Iterable[Unread]) -> list[ops.AsReported]:
        said = [
            ops.AsReported(scheme=f"{self.market.venue}:{u.field}"[:64], code=u.text[:128] or "?",
                           text=u.text[:256] or "?")
            for u in unread
        ]  # fmt: skip
        if self.venue.missing:
            said.append(ops.AsReported(scheme=f"{self.market.venue}:venue",
                                       code=self.market.venue, text=self.market.name))  # fmt: skip
        return said

    @staticmethod
    def _ident(seen: Tick | Top) -> str:
        """What a row read from `seen` is keyed by: the venue's identity for
        it, else the day and line of the raw record it was first read from,
        else when it arrived."""
        if seen.ident:
            return seen.ident
        path, _, line = seen.raw_key.partition("#")
        day = next((p for p in path.split("/") if len(p) == 10 and p[4] == "-"), "")
        return f"{day}#{line}" if day and line else str(seen.at_ns)

    def _meta(self, row_key: str, mapped: Mapped, seen: Tick | Top) -> ObservationMeta:
        times = [SourceTime(kind="event", at_ns=seen.at_ns)] if seen.stated else []
        return ObservationMeta(
            row_key=row_key[:128],
            subjects=[ops.SubjectRef(entity_id=mapped.subject)],
            source=ops.Source(dataset=self.dataset(LIVE), venue_id=self.venue.venue_id),
            valid_from_ns=seen.at_ns,
            source_times=times,
            raw=self.plugin.raw_record(seen.raw_key),
            unconverted=self._unconverted(seen.unread),
        )

    def price(self, mapped: Mapped, kind: str, amount: Any, seen: Tick | Top) -> Price:
        """A price per contract of one kind, in the venue's cash."""
        return Price(
            meta=self._meta(f"{mapped.contract.code}:{kind}:{self._ident(seen)}", mapped, seen),
            kind=kind,
            price=self._money(amount, mapped),
            basis="per_unit",
        )

    def quote(self, mapped: Mapped, top: Top) -> Quote | None:
        """The best bid and offer with their sizes; a side the venue states no
        order on, or whose price is no price per contract, left unset."""
        bid = top.bid if self._within(top.bid, mapped.contract) else None
        ask = top.ask if self._within(top.ask, mapped.contract) else None
        if bid is None and ask is None:
            return None
        return Quote(
            meta=self._meta(f"{mapped.contract.code}:quote:{self._ident(top)}", mapped, top),
            bid=None if bid is None else self._money(bid, mapped),
            ask=None if ask is None else self._money(ask, mapped),
            bid_quantity=None if bid is None else top.bid_size,
            ask_quantity=None if ask is None else top.ask_size,
        )

    # ── Recording ────────────────────────────────────────────────────────

    async def _send(self, prices: list[Price], quotes: list[Quote], want_id: str) -> None:
        for start in range(0, len(prices), BATCH):
            done = await self.plugin.record_prices(prices=prices[start : start + BATCH],
                                                   want_id=want_id)  # fmt: skip
            self._count(done)
        for start in range(0, len(quotes), BATCH):
            done = await self.plugin.record_quotes(quotes=quotes[start : start + BATCH],
                                                   want_id=want_id)  # fmt: skip
            self._count(done)

    def _count(self, done: Any, counts: Counts | None = None) -> None:
        counts = counts or self.counts
        counts.recorded += int(getattr(done, "recorded", 0))
        counts.restated += int(getattr(done, "restated", 0))
        counts.unchanged += int(getattr(done, "unchanged", 0))
        counts.last_ns = self.clock_ns()

    async def _asked(self, call: Callable[..., Any], *args: Any) -> Any:
        """One question of the venue, off the loop: what it answered, or None
        where it refused or did not answer -- said on the Connection page,
        and the other subjects still asked."""
        try:
            return await asyncio.to_thread(call, *args)
        except Exception as failed:  # noqa: BLE001 - the venue's refusal, kept in its raw record
            log.warning("asked of %s, not answered: %s", self.market.name, failed)
            return None

    async def record_live(
        self,
        subjects: Iterable[str],
        kinds: Iterable[int] = (),
        want_id: str = "",
        data_type: str = "",
    ) -> dict[str, str]:
        """Each subject's last trade price and best bid and offer now, as
        prices (`data_type` Price), as a quote (Quote), or both (empty); what
        was declined, by subject and reason."""
        await self.venue_id()
        subjects = list(subjects)
        await self.name(subjects)
        asked = set(kinds) or set(_LIVE_KINDS)
        priced = data_type in ("", PRICE)
        quoted = data_type in ("", QUOTE)
        declined: dict[str, str] = {}
        prices: list[Price] = []
        quotes: list[Quote] = []
        for subject in subjects:
            mapped = self.contracts.serving(subject)
            if mapped is None:
                declined[subject] = "not_covered"
                continue
            before = len(prices) + len(quotes)
            contract = mapped.contract
            if priced and ops.PRICE_KIND_LAST in asked:
                tick = await self._asked(self.market.last, contract)
                if tick and self._within(tick.price, contract):
                    prices.append(self.price(mapped, "last", tick.price, tick))
                elif tick and (tick.price is not None or tick.unread):
                    self.counts.unread += 1
            if quoted or (priced and asked & {ops.PRICE_KIND_BID, ops.PRICE_KIND_ASK}):
                best = await self._asked(self.market.top, contract)
                if best is not None:
                    for kind, amount in (("bid", best.bid), ("ask", best.ask)):
                        wanted = priced and getattr(ops, f"PRICE_KIND_{kind.upper()}") in asked
                        if wanted and self._within(amount, contract):
                            prices.append(self.price(mapped, kind, amount, best))
                        elif amount is not None and not self._within(amount, contract):
                            self.counts.unread += 1
                    self.counts.unread += len(best.unread)
                    if quoted and (row := self.quote(mapped, best)):
                        quotes.append(row)
            if len(prices) + len(quotes) == before:
                declined[subject] = "source_silent"
        await self._send(prices, quotes, want_id)
        await self._outcomes_of(self.contracts.serving(s) for s in subjects)
        return declined

    # ── Outcomes (contract v23) ──────────────────────────────────────────

    @staticmethod
    def _determination(value: Decimal, contract: Contract) -> str | None:
        """What a settlement value per contract says the contract pays: its
        full payout, nothing, or part of it; None for no value per contract."""
        if value < 0:
            return None
        if value == 0:
            return "pays_nothing"
        if contract.payout is None or value > contract.payout:
            return None
        return "pays" if value == contract.payout else "pays_part"

    def outcome(self, mapped: Mapped) -> tuple[Outcome, Recorded] | None:
        """The contract's outcome as the venue now states it, and what to keep
        of it once recorded; None where the venue states no determination,
        or states what was last recorded."""
        contract = mapped.contract
        said = contract.resolution
        if said is None:
            return None
        held = self.contracts.outcomes.get(contract.code)
        value, scheme, word, text = said.value, said.scheme, said.word, said.text
        if value is None or not word:
            # A stage stated with no determination of its own: the one held.
            if held is None:
                return None
            value, scheme, word, text = Decimal(held.value), held.scheme, held.word, held.text
        determination = self._determination(value, contract)
        if determination is None:
            if contract.code not in self.unreadable:
                log.warning("%s's settlement value %s is no value per contract", contract.code,
                            value)  # fmt: skip
                self.unreadable.add(contract.code)
                self.outcome_counts.unread += 1
            return None
        if held is not None and held.says() == (said.stage, value, scheme, word, text,
                                                said.settled_at_ns):  # fmt: skip
            return None
        if said.determined_at_ns:
            at, stated = said.determined_at_ns, True
        elif held is not None and (Decimal(held.value), held.word) == (value, word):
            at, stated = held.valid_from_ns, held.stated
        else:
            at, stated = contract.read_at_ns or self.clock_ns(), False
        kept = Recorded(said.stage, str(value), scheme, word, text, said.settled_at_ns, at,
                        stated, contract.raw_key)  # fmt: skip
        row = Outcome(
            meta=ObservationMeta(
                row_key=f"{contract.code}:outcome"[:128],
                subjects=[ops.SubjectRef(entity_id=mapped.subject)],
                source=ops.Source(dataset=self.dataset(OUTCOMES), venue_id=self.venue.venue_id),
                valid_from_ns=at,
                source_times=[SourceTime(kind="event", at_ns=at)] if stated else [],
                raw=self.plugin.raw_record(contract.raw_key),
                unconverted=self._unconverted(said.unread),
            ),
            determination=determination,
            stage=said.stage,
            settlement_value=self._money(value, mapped),
            settled_at_ns=said.settled_at_ns,
            determination_as_reported=ops.AsReported(
                scheme=scheme[:64], code=word[:128], text=(text or word)[:256]
            ),
        )
        return row, kept

    async def record_outcomes(self, mapped: Iterable[Mapped | None]) -> int:
        """Each contract's outcome where the venue's statement of it changed,
        in batches; how many versions were sent."""
        serving = [m for m in mapped if m is not None and m.contract.resolution is not None]
        if not serving:
            return 0
        await self.venue_id()
        rows: list[Outcome] = []
        kept: dict[str, Recorded] = {}
        for each in serving:
            if each.contract.code in kept:
                continue
            built = self.outcome(each)
            if built is not None:
                rows.append(built[0])
                kept[each.contract.code] = built[1]
        for start in range(0, len(rows), BATCH):
            done = await self.plugin.record_outcomes(outcomes=rows[start : start + BATCH])
            self._count(done, self.outcome_counts)
        if kept:
            self.contracts.outcomes.update(kept)
            self.contracts.save()
        return len(rows)

    async def _outcomes_of(self, mapped: Iterable[Mapped | None]) -> None:
        """Record outcomes beside other work, a refusal said and not raised:
        the work it is beside still answers."""
        try:
            await self.record_outcomes(mapped)
        except Exception as failed:  # noqa: BLE001 - said; the next pass tries again
            log.warning("outcomes not recorded: %s", failed)

    async def watch_outcomes(self) -> int:
        """Read again each contract past its close or no longer trading, its
        final stage not yet recorded, and record its outcome where the
        venue's statement changed."""
        now = self.clock_ns()
        due: list[Mapped] = []
        for mapped in self.contracts.mapped():
            contract = mapped.contract
            held = self.contracts.outcomes.get(contract.code)
            if held is not None and held.stage == FINAL:
                continue
            if contract.tradable and contract.closes_at_ns > now:
                continue
            read = await self._asked(self.market.contract, contract.code, True)
            if read is None:
                continue
            self.contracts.contracts[contract.code] = read
            due.append(Mapped(read, mapped.subject, mapped.cash_id))
        if due:
            self.contracts.save()
        return await self.record_outcomes(due)

    # ── Wants ────────────────────────────────────────────────────────────

    async def _decline(self, want_id: str, declined: dict[str, str]) -> None:
        by_reason: dict[str, list[str]] = {}
        for subject, reason in declined.items():
            by_reason.setdefault(reason, []).append(subject)
        for reason, subjects in sorted(by_reason.items()):
            await self.plugin.decline_want(
                want_id=want_id,
                subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
                reason=reason,
            )
            self.counts.declined += len(subjects)

    async def on_want(self, heard: meridian.Heard[ops.ObservationsWantedEvent]) -> None:
        """Record what the lake wants, or decline it per subject."""
        want = heard.message
        self.counts.wants += 1
        subjects = [s.entity_id for s in want.subjects]
        key = self._key_of(want.dataset)
        kinds = tuple(want.kinds)
        before = self.counts.recorded + self.counts.restated + self.counts.unchanged
        declined: dict[str, str] = {}
        asked = want.business_date or (
            f"{want.valid_from_ns}..{want.valid_until_ns}" if want.valid_from_ns else "latest"
        )
        try:
            declined = await self._answer(want, key, subjects, kinds)
        except Exception as failed:  # noqa: BLE001 - the venue or the lake refused; said, not raised
            log.warning("want %s not answered: %s", want.want_id, failed)
            declined = {s: "source_silent" for s in subjects}
        await self._decline(want.want_id, declined)
        after = self.counts.recorded + self.counts.restated + self.counts.unchanged
        self.heard.appendleft(
            Heard(want.want_id, want.dataset, asked, len(subjects), after - before,
                  len(declined), want.standing, self.clock_ns())
        )  # fmt: skip

    def _when(self, want: ops.ObservationsWantedEvent) -> str:
        """Whether a want's day or range is past, to come, or covers now: the
        venue's public reads answer now alone."""
        now = self.clock_ns()
        if want.business_date:
            day = date.fromisoformat(want.business_date)
            today = utc_day(now // NANOS_PER_SECOND)
            return "past" if day < today else "coming" if day > today else "now"
        if want.valid_from_ns:
            if want.valid_from_ns > now:
                return "coming"
            if want.valid_until_ns and want.valid_until_ns <= now - NANOS_PER_SECOND:
                return "past"
        return "now"

    async def _answer(
        self,
        want: ops.ObservationsWantedEvent,
        key: str,
        subjects: list[str],
        kinds: tuple[int, ...],
    ) -> dict[str, str]:
        if (
            key != LIVE
            or want.data_type not in ("", PRICE, QUOTE)
            or (want.data_type != QUOTE and kinds and not set(kinds) & _LIVE_KINDS)
        ):
            return {s: "not_covered" for s in subjects}
        when = self._when(want)
        if when != "now":
            return {s: "beyond_history" if when == "past" else "source_silent" for s in subjects}
        if want.standing:
            self.standing[want.want_id] = Standing(
                want.want_id, want.dataset, want.data_type, tuple(subjects), kinds,
                self.clock_ns(),
            )  # fmt: skip
        return await self.record_live(subjects, kinds, want.want_id, want.data_type)

    async def on_withdrawn(self, heard: meridian.Heard[ops.WantWithdrawnEvent]) -> None:
        """A standing want withdrawn: its subjects are no longer kept current."""
        self.standing.pop(heard.message.want_id, None)

    # ── Keeping current ──────────────────────────────────────────────────

    async def current(self) -> None:
        """One pass keeping each standing want's subjects current."""
        for data_type, kinds, subjects in _grouped(self.standing.values()):
            await self.record_live(subjects, kinds, data_type=data_type)

    async def keep_current(self, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        """Keep each standing want's subjects current, until cancelled: at most
        once a second; each contract, and the venue, read again once a day;
        and each minute the contracts due for their outcome."""
        last_read = last_watched = time.monotonic()
        while True:
            now = time.monotonic()
            try:
                if now - last_read >= REREAD_SECONDS:
                    await self.reread()
                    last_read = now
                if now - last_watched >= OUTCOME_EVERY_SECONDS:
                    last_watched = now
                    await self.watch_outcomes()
                await self.current()
            except Exception as failed:  # noqa: BLE001 - said, and tried again next time
                log.warning("keeping current stopped this time: %s", failed)
            await sleep(LIVE_EVERY_SECONDS)


def _grouped(wants: Iterable[Standing]) -> list[tuple[str, tuple[int, ...], list[str]]]:
    """The standing wants' subjects, once each, by the data type and kinds
    asked."""
    by_ask: dict[tuple[str, tuple[int, ...]], set[str]] = {}
    for want in wants:
        by_ask.setdefault((want.data_type, tuple(sorted(want.kinds))), set()).update(want.subjects)
    return [(dt, kinds, sorted(subjects)) for (dt, kinds), subjects in sorted(by_ask.items())]


async def cancelled(task: asyncio.Task[Any]) -> None:
    """Cancel a task and wait for it."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
