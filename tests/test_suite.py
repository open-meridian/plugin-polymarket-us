"""The SDK's data suite, run unchanged against this plugin's own conversion.

Each of the suite's cases (meridian.suites, contract v19) is mapped
to the plugin's own synthetic exchange for it, named in tests/venue_cases.py,
the one module that knows which venue this is; the plugin's real client,
raw records, conversion and data plugin's work run against the SDK's `Recorder`, its typed
operations recorded rather than sent, and the runner compares what it sent
with the case. The outcome is tested, never the route.

A case about a kind of data the plugin declares it never publishes -- daily
closes, bars, trades, a currency's rate, a security's price, from contract
v22 a settlement calendar or date -- is named in
`not_presented` with why (venue_cases.NOT_PRESENTED), as the suite allows
from contract v19; every other case is mapped and passes. From contract v23
the outcome cases are each mapped to the venue's own exchange for it
(venue_cases.DETERMINED, DISPUTED and PARTIAL), an outcome recorded at the
stage the venue states; a venue that never states a dispute names
restates-a-disputed-outcome (`about: disputed outcomes`) not presented, with
why.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.suites import Recorder, names, run, suite

import venue_cases as venue
from conftest import Instruments, held

Producer = Callable[[Recorder], Awaitable[None]]

PRICE, QUOTE = "meridian.v1.Price", "meridian.v1.Quote"
NOT_PRESENTED = venue.NOT_PRESENTED


def _dgm(recorder: Recorder, **mutations: Any) -> tuple[Any, Instruments]:
    """The plugin's work (Dgm) on the recorder, which resolves from an instrument
    store of the deployment's records."""
    store = Instruments().answering(recorder)
    dgm = venue.Dgm(recorder, venue.market(), venue.ContractMap(),
                    clock_ns=lambda: venue.NOW_NS)  # fmt: skip
    for name, mutated in mutations.items():
        setattr(dgm, name, mutated.__get__(dgm))
    return dgm, store


def _want(want_id: str, dataset: str, subjects: list[str], standing: bool = False) -> Any:
    return ops.ObservationsWantedEvent(
        want_id=want_id,
        dataset=dataset,
        data_type=PRICE,
        subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
        standing=standing,
    )


def producers(**mutations: Any) -> dict[str, Producer]:
    """Each case's producer: the plugin's own steps on its own exchange."""

    def live(code: str, data_type: str) -> Producer:
        async def produce(recorder: Recorder) -> None:
            dgm, store = _dgm(recorder, **mutations)
            subject = await held(store, dgm, code)
            await dgm.record_live([subject], data_type=data_type)

        return produce

    async def ambiguous(recorder: Recorder) -> None:
        # Two records already carry the venue's cash's identifiers: the cash
        # its prices are in meets both, and nothing is priced in it.
        dgm, store = _dgm(recorder)
        for n in (1, 2):
            store.hold(f"INS-CASH-{n}", *dgm.cash_identifiers())
        subject = await held(store, dgm, venue.BASE)
        await dgm.record_live([subject], data_type=PRICE)

    async def venue_not_held(recorder: Recorder) -> None:
        recorder.answer(
            "ResolveVenue",
            lambda _: ops.ResolveVenueResult(found=False, miss_reason=ops.MISS_REASON_NOT_FOUND),
        )
        await _dgm(recorder)[0].venue_id()

    def wanted(covered: bool) -> Producer:
        async def produce(recorder: Recorder) -> None:
            dgm, store = _dgm(recorder)
            subject = await held(store, dgm, venue.BASE) if covered else "LCL-NOT-COVERED"
            want = _want("WNT-1", dgm.dataset("live"), [subject])
            recorder.answer("ObservationsWanted", lambda _: want)
            await recorder.receive(observations_wanted=dgm.on_want)

        return produce

    async def withdrawn(recorder: Recorder) -> None:
        dgm, store = _dgm(recorder)
        subject = await held(store, dgm, venue.BASE)
        dgm.standing["WNT-2"] = venue.Standing(
            "WNT-2", dgm.dataset("live"), PRICE, (subject,), (ops.PRICE_KIND_LAST,), venue.NOW_NS
        )
        recorder.answer(
            "WantWithdrawn",
            lambda _: [ops.WantWithdrawnEvent(want_id="WNT-2", dataset=dgm.dataset("live"))],
        )
        await recorder.receive(want_withdrawn=dgm.on_withdrawn)
        await dgm.current()  # one pass keeping current: nothing stands now

    def outcome(code: str | None, later: tuple[Path, ...] = ()) -> Producer | None:
        # Contract v23: a contract the venue has determined, named for a
        # subject, its outcome recorded; then each later answer of the venue
        # for it, read again as a contract past its close is.
        if code is None:
            return None

        async def produce(recorder: Recorder) -> None:
            dgm, store = _dgm(recorder, **mutations)
            subject = await held(store, dgm, code)
            await dgm.name([subject])
            await dgm.record_outcomes([dgm.contracts.serving(subject)])
            for directory in later:
                dgm.market = venue.market(directory=directory)
                await dgm.watch_outcomes()

        return produce

    async def licences(recorder: Recorder) -> None:
        # On start (contract v20): a deployment admin has licensed its live
        # dataset, and another plugin's dataset is no concern of this one's.
        dgm, _ = _dgm(recorder)
        recorder.answer("ListDatasets", lambda _: ops.ListDatasetsResult(licences=[
            ops.DatasetLicence(dataset=dgm.dataset("live")),
            ops.DatasetLicence(dataset="another-1:live"),
        ]))  # fmt: skip
        assert await dgm.read_licences() == frozenset({dgm.dataset("live")})

    made: dict[str, Producer] = {
        "an-exact-price": live(venue.EXACT, PRICE),
        "a-stablecoin-quote": live(venue.BASE, PRICE),
        "an-asset-that-does-not-resolve": ambiguous,
        "a-venue-resolved": live(venue.BASE, PRICE),
        "a-venue-not-held": venue_not_held,
        "a-want-recorded-against": wanted(covered=True),
        "a-subject-declined": wanted(covered=False),
        "a-standing-want-withdrawn": withdrawn,
        "a-quote-recorded": live(venue.BASE, QUOTE),
        "a-one-sided-quote": live(venue.ONE_SIDED, QUOTE),
        "reads-its-datasets-licences": licences,
    }
    outcomes = {
        "records-an-outcome": outcome(venue.DETERMINED),
        "restates-a-disputed-outcome": outcome(*venue.DISPUTED) if venue.DISPUTED else None,
        "records-a-partial-payout": outcome(venue.PARTIAL),
    }
    made.update({name: each for name, each in outcomes.items() if each is not None})
    return {name: made[name] for name in made if name not in NOT_PRESENTED}


def test_every_case_is_mapped_or_said_not_presented_with_why() -> None:
    assert set(names("data")) == set(producers()) | set(NOT_PRESENTED)
    assert not set(producers()) & set(NOT_PRESENTED)
    assert all(why.strip() for why in NOT_PRESENTED.values())


def test_only_a_case_about_a_kind_never_published_is_not_presented() -> None:
    about = {case.name: case.about or case.about_field for case in suite("data").cases}
    assert all(about[name] for name in NOT_PRESENTED), "a required case is never skipped"
    assert "reads-its-datasets-licences" not in NOT_PRESENTED


def test_every_case_the_venue_presents_passes_unchanged() -> None:
    report = run("data", producers(), not_presented=NOT_PRESENTED, instance_id=venue.VENUE)
    assert report.passed, report.failures
    assert len(report.passed_cases) == len(list(names("data"))) - len(NOT_PRESENTED)


def test_a_price_read_through_a_float_fails_the_suite() -> None:
    def through_float(self: Any, mapped: Any, kind: str, amount: Any, seen: Any) -> Any:
        return type(self).price(self, mapped, kind, Decimal(float(amount)), seen)

    report = run("data", producers(price=through_float), not_presented=NOT_PRESENTED,
                 instance_id=venue.VENUE)  # fmt: skip
    assert "an-exact-price" in report.failures


def test_a_quote_dropping_its_sizes_fails_the_suite() -> None:
    def sizeless(self: Any, mapped: Any, top: Any) -> Any:
        from dataclasses import replace

        return type(self).quote(self, mapped, replace(top, bid_size=None, ask_size=None))

    report = run("data", producers(quote=sizeless), not_presented=NOT_PRESENTED,
                 instance_id=venue.VENUE)  # fmt: skip
    assert "a-quote-recorded" in report.failures


def test_a_token_price_as_its_currency_fails_the_suite() -> None:
    if not venue.STABLE:
        return  # a venue pricing in a currency names it by its code, as it should
    from meridian import Money

    def as_fiat(self: Any, amount: Any, mapped: Any) -> Any:
        return Money(amount, "USD")

    report = run("data", producers(_money=as_fiat), not_presented=NOT_PRESENTED,
                 instance_id=venue.VENUE)  # fmt: skip
    assert "a-stablecoin-quote" in report.failures


def test_an_outcome_read_as_its_full_payout_fails_the_suite() -> None:
    def in_full(self: Any, value: Any, contract: Any) -> str:
        return "pays"

    report = run("data", producers(_determination=in_full), not_presented=NOT_PRESENTED,
                 instance_id=venue.VENUE)  # fmt: skip
    assert "records-a-partial-payout" in report.failures
