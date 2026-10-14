"""The tests run with no deployment: the SDK's `Recorder` stands in for the
sidecar, and the synthetic exchanges this package carries stand in for the
venue (tests/venue_cases.py says which venue)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.suites import Recorder

import venue_cases as venue

#: Another source the deployment holds records from: a custodian's book.
OTHER = "custodian"


def _same(one: Any, other: Any) -> bool:
    return bool((one.scheme, one.value, one.source) == (other.scheme, other.value, other.source))


def payout(
    amount: str, currency_code: str = "", instrument_id: str = ""
) -> ops.BinaryEventContract:
    """A binary event contract's attributes as a record states them: its
    payout, a Money naming its cash instrument by code or by record."""
    sign, digits, exponent = Decimal(amount).as_tuple()
    integer = int("".join(map(str, digits))) * (-1 if sign else 1)
    scale = -int(exponent) if int(exponent) < 0 else 0
    wire = ops.Decimal(high=integer >> 64, low=integer & (2**64 - 1), scale=scale)
    money = ops.Money(amount=wire, currency_code=currency_code, instrument_id=instrument_id)
    return ops.BinaryEventContract(payout=money)


class Instruments:
    """The deployment's instrument store as the tests hold it. ResolveInstrument
    reads a record by its ID (W3.6); ResolveIdentifier answers the one record
    the identifiers meet, the others joined to it and what it states offered,
    a record minted where they meet none, and ambiguous where they meet two
    (W3.1)."""

    def __init__(self) -> None:
        self.records: dict[str, list[ops.Identifier]] = {}
        self.classes: dict[str, int] = {}
        self.types: dict[str, int] = {}
        self.payouts: dict[str, ops.BinaryEventContract] = {}
        #: What each resolve offered, by the record it met: (class, type,
        #: description).
        self.offered: dict[str, tuple[int, int, str]] = {}

    def hold(
        self,
        instrument_id: str,
        *identifiers: ops.Identifier,
        asset_class: int = 0,
        instrument_type: int = 0,
        attributes: ops.BinaryEventContract | None = None,
    ) -> str:
        self.records[instrument_id] = list(identifiers)
        self.classes[instrument_id] = asset_class
        self.types[instrument_id] = instrument_type
        if attributes is not None:
            self.payouts[instrument_id] = attributes
        return instrument_id

    def read(self, params: Any) -> Any:
        held = self.records.get(params.instrument_id)
        if held is None:
            return ops.ResolveInstrumentResult(found=False)
        record = ops.InstrumentRecord(
            instrument_id=params.instrument_id,
            identifiers=held,
            asset_class=self.classes.get(params.instrument_id, 0),  # type: ignore[arg-type]
            instrument_type=self.types.get(params.instrument_id, 0),  # type: ignore[arg-type]
        )
        if params.instrument_id in self.payouts:
            record.binary_event_contract.CopyFrom(self.payouts[params.instrument_id])
        return ops.ResolveInstrumentResult(found=True, instrument=record)

    def resolve(self, params: Any) -> Any:
        given = list(params.identifiers)
        met = [key for key, held in self.records.items()
               if any(_same(g, h) for g in given for h in held)]  # fmt: skip
        if len(met) > 1:
            return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_AMBIGUOUS)
        offer = (params.stated_asset_class, params.stated_instrument_type,
                 params.stated_description)  # fmt: skip
        if met:
            held = self.records[met[0]]
            held.extend(g for g in given if not any(_same(g, h) for h in held))
            self.offered[met[0]] = offer
            return ops.ResolveIdentifierResult(found=True, instrument_id=met[0])
        minted = self.hold(f"LCL-{given[0].value[:24]}", *given)
        self.offered[minted] = offer
        return ops.ResolveIdentifierResult(found=True, instrument_id=minted, minted=True)

    def answering(self, recorder: Recorder) -> Instruments:
        recorder.answer("ResolveIdentifier", self.resolve)
        recorder.answer("ResolveInstrument", self.read)
        return self


async def held(store: Instruments, dgm: Any, code: str, **kw: Any) -> str:
    """A record the deployment holds for one of the venue's contracts, carrying
    the venue's code, as a record a person completed from this venue would."""
    contract = await dgm.contract(code)
    assert contract is not None, f"the venue states no contract {code}"
    return store.hold(f"INS-{code[-12:]}", *dgm.identifiers(contract), **kw)


class Lake(Recorder):
    """The SDK's recorder, answering a batch as the lake does: a row key new is
    recorded, the same values again unchanged (by decimal value: 0.43 is
    0.4300), a changed value the next version; and resolving from its own
    instrument store."""

    def __init__(self, instance_id: str = venue.VENUE) -> None:
        super().__init__(instance_id)
        self.versions: dict[tuple[str, str], tuple[int, tuple[Any, ...]]] = {}
        self.instruments = Instruments().answering(self)
        self.answer("RecordPrices", self._prices)
        self.answer("RecordQuotes", self._quotes)
        self.answer("RecordOutcomes", self._outcomes)

    def _prices(self, params: Any) -> Any:
        recorded, restated, unchanged = self._record(params.prices, "price")
        return ops.RecordPricesResult(recorded=recorded, restated=restated, unchanged=unchanged)

    def _quotes(self, params: Any) -> Any:
        recorded, restated, unchanged = self._record(params.quotes, "quote")
        return ops.RecordQuotesResult(recorded=recorded, restated=restated, unchanged=unchanged)

    def _outcomes(self, params: Any) -> Any:
        recorded, restated, unchanged = self._record(params.outcomes, "outcome")
        return ops.RecordOutcomesResult(recorded=recorded, restated=restated, unchanged=unchanged)

    def on(self, row: str) -> list[Any]:
        return list(super().on(row))

    @staticmethod
    def _values(row: Any, kind: str) -> tuple[Any, ...]:
        if kind == "outcome":
            return (row.determination, row.stage, as_decimal(row.settlement_value.amount),
                    row.settled_at_ns, row.determination_as_reported.code)  # fmt: skip
        if kind == "price":
            return (as_decimal(row.price.amount),)
        return tuple(
            as_decimal(getattr(row, f).amount) if row.HasField(f) else None for f in ("bid", "ask")
        ) + tuple(
            as_decimal(getattr(row, f)) if row.HasField(f) else None
            for f in ("bid_quantity", "ask_quantity")
        )

    def _record(self, rows: Any, kind: str) -> tuple[int, int, int]:
        recorded = restated = unchanged = 0
        for row in rows:
            values = self._values(row, kind)
            key = (kind, row.meta.row_key)
            held = self.versions.get(key)
            if held is None:
                self.versions[key] = (1, values)
                recorded += 1
            elif held[1] == values:
                unchanged += 1
            else:
                self.versions[key] = (held[0] + 1, values)
                restated += 1
        return recorded, restated, unchanged

    def rows(self, row: str = "RecordPrices") -> list[Any]:
        field = {"RecordPrices": "prices", "RecordQuotes": "quotes",
                 "RecordOutcomes": "outcomes"}[row]  # fmt: skip
        return [r for params in self.on(row) for r in getattr(params, field)]

    async def held(self, dgm: Any, code: str, **kw: Any) -> str:
        return await held(self.instruments, dgm, code, **kw)


@pytest.fixture
def lake() -> Lake:
    return Lake()


def dgm_on(lake: Recorder, now_ns: int = venue.NOW_NS, **kw: Any) -> Any:
    return venue.Dgm(lake, venue.market(now_ns, **kw), venue.ContractMap(), clock_ns=lambda: now_ns)


def wanted(
    dgm: Any,
    want_id: str,
    subjects: list[str],
    *,
    key: str = "live",
    data_type: str = "meridian.v1.Price",
    kinds: tuple[Any, ...] = (),
    day: Any = None,
    standing: bool = False,
) -> ops.ObservationsWantedEvent:
    """A want as the lake sends one: the latest, or for a business date."""
    return ops.ObservationsWantedEvent(
        want_id=want_id,
        dataset=dgm.dataset(key),
        data_type=data_type,
        kinds=list(kinds),
        subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
        business_date=day.isoformat() if day else "",
        standing=standing,
    )


async def hear(lake: Recorder, dgm: Any, event: ops.ObservationsWantedEvent) -> None:
    """The want delivered to the plugin's own handler, through its receive."""
    lake.answer("ObservationsWanted", lambda _: event)
    await lake.receive(observations_wanted=dgm.on_want)
