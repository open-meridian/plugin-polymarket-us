"""The dgm's behaviour past the suite's cases: each subject named from its
record and nothing else read from the venue, prices and quotes per contract
in the venue's cash, the payout, wants, standing wants, and the venue.

Run against the plugin's synthetic exchange
(tests/venue_cases.py) and a recorder answering batches as the lake does
(conftest.Lake).
"""

from __future__ import annotations

import contextlib
import sys
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import meridian
from meridian.operations import as_decimal, as_money
from meridian.plugin.v1 import operations_pb2 as ops

import venue_cases as venue
from conftest import OTHER, Lake, dgm_on, hear, payout, wanted

PRICE, QUOTE = "meridian.v1.Price", "meridian.v1.Quote"


def _amounts(rows: list[Any], kind: int) -> list[str]:
    return [str(as_decimal(r.price.amount)) for r in rows if r.kind == kind]


async def test_a_contracts_prices_are_its_last_bid_and_ask_per_contract(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    declined = await dgm.record_live([subject], data_type=PRICE)
    rows = lake.rows()
    assert not declined
    assert _amounts(rows, ops.PRICE_KIND_LAST) == [venue.LAST]
    assert _amounts(rows, ops.PRICE_KIND_BID) == [venue.BID]
    assert _amounts(rows, ops.PRICE_KIND_ASK) == [venue.ASK]
    assert all(r.basis == ops.PRICE_BASIS_PER_UNIT for r in rows)
    assert all(r.meta.subjects[0].entity_id == subject for r in rows)
    assert all(not r.meta.business_date and r.meta.valid_until_ns == 0 for r in rows)
    assert all(r.meta.source.dataset == f"{venue.VENUE}:live" for r in rows)
    assert all(r.meta.raw.key.startswith("responses/") for r in rows)
    assert all(r.meta.row_key.startswith(f"{venue.BASE}:") for r in rows)


async def test_a_quote_carries_both_sides_with_their_sizes(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    await dgm.record_live([subject], data_type=QUOTE)
    [quote] = lake.rows("RecordQuotes")
    assert str(as_decimal(quote.bid.amount)) == venue.BID
    assert str(as_decimal(quote.ask.amount)) == venue.ASK
    assert str(as_decimal(quote.bid_quantity)) == venue.BID_SIZE
    assert str(as_decimal(quote.ask_quantity)) == venue.ASK_SIZE
    assert quote.meta.valid_from_ns > 0 and quote.meta.row_key.startswith(f"{venue.BASE}:quote:")
    assert not lake.rows(), "a quote's want records no prices"


async def test_a_side_with_no_order_is_left_unset(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.ONE_SIDED)
    await dgm.record_live([subject])
    [quote] = lake.rows("RecordQuotes")
    assert quote.HasField("bid") and not quote.HasField("ask")
    assert quote.HasField("bid_quantity") and not quote.HasField("ask_quantity")
    assert not _amounts(lake.rows(), ops.PRICE_KIND_ASK)


async def test_a_price_past_a_float_is_recorded_exactly(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.EXACT)
    await dgm.record_live([subject], data_type=PRICE)
    assert venue.EXACT_LAST in _amounts(lake.rows(), ops.PRICE_KIND_LAST)


async def test_every_price_names_the_venues_cash(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    await dgm.record_live([subject])
    monies = [as_money(r.price) for r in lake.rows()]
    monies += [as_money(q.bid) for q in lake.rows("RecordQuotes")]
    cash = dgm.contracts.cash_id
    assert cash, "the cash resolved once a subject was named"
    if venue.STABLE:
        assert all((m.instrument_id, m.currency_code) == (cash, "") for m in monies)
    else:
        assert all((m.currency_code, m.instrument_id) == (venue.CASH, "") for m in monies)


async def test_an_answer_read_again_unchanged_is_the_same_row(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    await dgm.record_live([subject])
    await dgm.record_live([subject])
    assert dgm.counts.recorded == 4 and dgm.counts.unchanged == 4, dgm.counts


async def test_a_price_beyond_the_payout_is_left_unrecorded_and_counted(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    real_top = dgm.market.top

    def past(contract: Any) -> Any:
        return replace(real_top(contract), ask=Decimal("1.5"))

    dgm.market.top = past
    await dgm.record_live([subject])
    assert not _amounts(lake.rows(), ops.PRICE_KIND_ASK)
    [quote] = lake.rows("RecordQuotes")
    assert not quote.HasField("ask") and dgm.counts.unread >= 1


async def test_only_the_contracts_wanted_are_read_never_the_venues_list(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    await dgm.record_live([subject])
    asked = venue.calls(dgm.market)
    assert asked and all(venue.BASE in url for url in asked), asked
    assert not lake.instruments.records.keys() - {subject, dgm.contracts.cash_id}, (
        "no record minted but the cash's"
    )


async def test_a_custodians_symbol_is_named_and_joined_with_the_offers(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = lake.instruments.hold(
        "INS-HELD", meridian.Identifier(scheme="symbol", value=venue.BASE, source=OTHER)
    )
    declined = await dgm.record_live([subject], data_type=PRICE)
    assert not declined and dgm.contracts.subjects == {subject: venue.BASE}
    held = lake.instruments.records[subject]
    assert any((i.scheme, i.value, i.source) == ("symbol", venue.BASE, venue.VENUE) for i in held)
    stated_class, stated_type, words = lake.instruments.offered[subject]
    assert stated_class == ops.ASSET_CLASS_EVENT_CONTRACT
    assert stated_type == ops.INSTRUMENT_TYPE_BINARY_EVENT_CONTRACT
    assert words, "the venue's words offered as its description"


async def test_a_record_already_complete_is_not_resolved_again(lake: Lake) -> None:
    dgm = dgm_on(lake)
    contract = await dgm.contract(venue.BASE)
    subject = lake.instruments.hold(
        "INS-DONE", *dgm.identifiers(contract),
        asset_class=ops.ASSET_CLASS_EVENT_CONTRACT,
        instrument_type=ops.INSTRUMENT_TYPE_BINARY_EVENT_CONTRACT,
    )  # fmt: skip
    await dgm.record_live([subject], data_type=PRICE)
    resolved = [r for r in lake.on("ResolveIdentifier") if r.stated_instrument_type]
    assert not resolved and lake.rows()


async def test_a_security_or_another_type_is_never_named_by_anothers_symbol(lake: Lake) -> None:
    dgm = dgm_on(lake)
    symbol = meridian.Identifier(scheme="symbol", value=venue.BASE, source=OTHER)
    equity = lake.instruments.hold("INS-EQ", symbol, asset_class=ops.ASSET_CLASS_EQUITY)
    fund = lake.instruments.hold(
        "INS-MMF", symbol, asset_class=ops.ASSET_CLASS_EVENT_CONTRACT,
        instrument_type=ops.INSTRUMENT_TYPE_MONEY_MARKET_FUND,
    )  # fmt: skip
    declined = await dgm.record_live([equity, fund])
    assert declined == {equity: "not_covered", fund: "not_covered"}
    assert not venue.calls(dgm.market), "nothing asked of the venue for either"


async def test_a_market_the_venue_does_not_state_as_binary_is_not_covered(lake: Lake) -> None:
    dgm = dgm_on(lake)
    contract = await dgm.contract(venue.NOT_BINARY)
    assert contract is not None and not contract.binary
    subject = lake.instruments.hold("INS-RANGE", *dgm.identifiers(contract))
    unknown = lake.instruments.hold(
        "INS-NONE", meridian.Identifier(scheme="symbol", value="NOT-A-CONTRACT", source=OTHER)
    )
    declined = await dgm.record_live([subject, unknown])
    assert declined == {subject: "not_covered", unknown: "not_covered"}
    assert set(dgm.unnamed.values()) == {sys.modules[type(dgm).__module__].NOT_A_CONTRACT}


async def test_a_payout_the_record_states_otherwise_is_not_served(lake: Lake) -> None:
    dgm = dgm_on(lake)
    other = "EUR"
    subject = await lake.held(dgm, venue.BASE, attributes=payout("1", currency_code=other))
    double = await lake.held(dgm, venue.EXACT, attributes=payout("2", currency_code=venue.CASH))
    declined = await dgm.record_live([subject, double])
    assert declined == {subject: "not_covered", double: "not_covered"}
    venue.page.hold(dgm)
    assert venue.page.datasets_now().payouts_differ == 2


async def test_a_payout_the_record_states_as_the_venues_is_served(lake: Lake) -> None:
    dgm = dgm_on(lake)
    cash = await dgm.cash_id()
    by_code = payout("1", currency_code=venue.CASH) if not venue.STABLE else None
    stated = by_code or payout("1.0", instrument_id=cash)
    subject = await lake.held(dgm, venue.BASE, attributes=stated)
    by_id = await lake.held(dgm, venue.EXACT, attributes=payout(venue.PAYOUT, instrument_id=cash))
    declined = await dgm.record_live([subject, by_id], data_type=PRICE)
    assert not declined and {r.meta.subjects[0].entity_id for r in lake.rows()} == {subject, by_id}


async def test_wants_are_recorded_against_or_declined_with_why(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    past, coming = venue.TODAY - timedelta(days=2), venue.TODAY + timedelta(days=3)
    for want_id, day, subjects in (
        ("WNT-1", None, [subject, "LCL-NOT-COVERED"]),
        ("WNT-2", past, [subject]),
        ("WNT-3", coming, [subject]),
        ("WNT-4", venue.TODAY, [subject]),
    ):
        await hear(lake, dgm, wanted(dgm, want_id, subjects, day=day))
    await hear(lake, dgm, wanted(dgm, "WNT-5", [subject], data_type="meridian.v1.Bar"))
    await hear(lake, dgm, wanted(dgm, "WNT-6", [subject], key="daily"))
    recorded = {p.want_id for p in lake.on("RecordPrices")}
    assert recorded == {"WNT-1", "WNT-4"}
    declined = {(d.want_id, s.entity_id, d.reason) for d in lake.on("DeclineWant")
                for s in d.subjects}  # fmt: skip
    assert declined == {
        ("WNT-1", "LCL-NOT-COVERED", ops.UNANSWERED_REASON_NOT_COVERED),
        ("WNT-2", subject, ops.UNANSWERED_REASON_BEYOND_HISTORY),
        ("WNT-3", subject, ops.UNANSWERED_REASON_SOURCE_SILENT),
        ("WNT-5", subject, ops.UNANSWERED_REASON_NOT_COVERED),
        ("WNT-6", subject, ops.UNANSWERED_REASON_NOT_COVERED),
    }
    assert [h.want_id for h in dgm.heard][:2] == ["WNT-6", "WNT-5"]


async def test_a_quotes_want_records_quotes_against_it(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    await hear(lake, dgm, wanted(dgm, "WNT-Q", [subject], data_type=QUOTE))
    [sent] = lake.on("RecordQuotes")
    assert sent.want_id == "WNT-Q" and not lake.on("RecordPrices")


async def test_a_contract_with_nothing_stated_is_declined_source_silent(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.ONE_SIDED)
    declined = await dgm.record_live([subject], kinds=[ops.PRICE_KIND_LAST], data_type=PRICE)
    assert declined == {subject: "source_silent"}


async def test_a_standing_want_is_kept_current_until_withdrawn(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    event = wanted(dgm, "WNT-9", [subject], data_type=QUOTE, standing=True)
    await hear(lake, dgm, event)
    assert set(dgm.standing) == {"WNT-9"}
    before = len(lake.on("RecordQuotes"))
    await dgm.current()
    assert len(lake.on("RecordQuotes")) == before + 1
    lake.answer("WantWithdrawn", lambda _: [ops.WantWithdrawnEvent(want_id="WNT-9")])
    await lake.receive(want_withdrawn=dgm.on_withdrawn)
    await dgm.current()
    assert not dgm.standing and len(lake.on("RecordQuotes")) == before + 1


async def test_keep_current_paces_itself_and_survives_a_failure(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    dgm.standing["WNT-K"] = venue.Standing("WNT-K", dgm.dataset("live"), PRICE, (subject,),
                                           (ops.PRICE_KIND_LAST,), venue.NOW_NS)  # fmt: skip
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) == 1:
            dgm.market.last = lambda contract: (_ for _ in ()).throw(OSError("down"))
        if len(slept) == 3:
            raise RuntimeError("stop")

    with contextlib.suppress(RuntimeError):
        await dgm.keep_current(sleep=sleep)
    assert slept == [1.0, 1.0, 1.0] and _amounts(lake.rows(), ops.PRICE_KIND_LAST)


async def test_the_venue_resolved_names_each_row(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    await dgm.record_live([subject])
    [asked] = lake.on("ResolveVenue")
    named = {(i.scheme, i.value, i.source) for i in asked.identifiers}
    assert named == set(dgm.market.venue_identifiers)
    assert all(r.meta.source.venue_id == dgm.venue.venue_id != "" for r in lake.rows())


async def test_a_venue_not_held_is_left_empty_and_named_as_reported(lake: Lake) -> None:
    lake.answer("ResolveVenue", lambda _: ops.ResolveVenueResult(found=False))
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    await dgm.record_live([subject])
    await dgm.record_live([subject])
    assert len(lake.on("ReportMissingVenue")) == 1, "reported once"
    for row in lake.rows():
        assert row.meta.source.venue_id == ""
        assert [u.scheme for u in row.meta.unconverted] == [f"{venue.VENUE}:venue"]


async def test_reading_again_asks_the_venue_and_each_contract_again(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    await dgm.record_live([subject])
    await dgm.reread()
    assert len(lake.on("ResolveVenue")) == 2 and dgm.contracts.read_at_ns == venue.NOW_NS


async def test_the_cash_not_resolving_is_reported_once_and_nothing_priced(lake: Lake) -> None:
    dgm = dgm_on(lake)
    for n in (1, 2):
        lake.instruments.hold(f"INS-CASH-{n}", *dgm.cash_identifiers())
    subject = await lake.held(dgm, venue.BASE)
    for _ in range(2):
        declined = await dgm.record_live([subject])
        assert declined == {subject: "not_covered"}
    [missed] = lake.on("ReportMissingInstrument")
    assert missed.reason == ops.MISS_REASON_AMBIGUOUS and not lake.rows()


async def test_a_record_that_cannot_be_read_names_nothing(lake: Lake) -> None:
    def refused(_: Any) -> Any:
        raise meridian.NotGranted("ResolveInstrument", "not granted to a data plugin")

    lake.answer("ResolveInstrument", refused)
    dgm = dgm_on(lake)
    declined = await dgm.record_live(["INS-ANY", "INS-OTHER"])
    assert declined == {"INS-ANY": "not_covered", "INS-OTHER": "not_covered"}
    assert dgm.reads_instruments is False and len(lake.on("ResolveInstrument")) == 1


async def test_the_contract_map_is_kept_and_read_back(lake: Lake, tmp_path: Path) -> None:
    dgm = dgm_on(lake)
    dgm.contracts = venue.ContractMap(tmp_path / "contracts-synthetic.json")
    subject = await lake.held(dgm, venue.BASE)
    await dgm.record_live([subject])
    again = venue.ContractMap(tmp_path / "contracts-synthetic.json")
    assert again.load()
    assert again.subjects == dgm.contracts.subjects and again.cash_id == dgm.contracts.cash_id
    assert again.contracts[venue.BASE] == dgm.contracts.contracts[venue.BASE]
    assert str(again.contracts[venue.BASE].payout) == venue.PAYOUT


async def test_licences_not_answered_leave_it_not_licensed_yet(lake: Lake) -> None:
    def refused(_: Any) -> Any:
        raise meridian.NotGranted("platform.lake.query.datasets", "not granted")

    lake.answer("ListDatasets", refused)
    dgm = dgm_on(lake)
    assert await dgm.read_licences() == frozenset() and dgm.reads_licences is False
    assert await dgm.read_licences() == frozenset(), "asked once, then said"


async def test_what_it_recorded_is_counted_with_when(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    await hear(lake, dgm, wanted(dgm, "WNT-1", [subject]))
    assert dgm.counts.recorded > 0 and dgm.counts.last_ns == venue.NOW_NS


# ── Outcomes (contract v23; the lake plan's "vL1c") ─────────────────────────


async def _resolved(lake: Lake, dgm: Any, code: str) -> str:
    """A subject named as one of the venue's contracts, its outcome recorded."""
    subject = await lake.held(dgm, code)
    await dgm.record_live([subject], data_type=PRICE)
    return subject


def _outcome_name(row: Any) -> tuple[str, str]:
    return (ops.OutcomeDetermination.Name(row.determination), ops.OutcomeStage.Name(row.stage))


async def test_a_resolved_contract_records_its_outcome_from_its_own_side(lake: Lake) -> None:
    dgm = dgm_on(lake)
    subject = await _resolved(lake, dgm, venue.RESOLVED)
    [row] = lake.rows("RecordOutcomes")
    assert _outcome_name(row) == ("OUTCOME_DETERMINATION_PAYS", venue.RESOLVED_STAGE)
    assert as_decimal(row.settlement_value.amount) == Decimal(venue.PAYOUT)
    assert (row.determination_as_reported.scheme, row.determination_as_reported.code) == venue.WORD
    assert row.meta.row_key == f"{venue.RESOLVED}:outcome"
    assert row.meta.source.dataset == f"{venue.VENUE}:outcomes"
    assert row.meta.subjects[0].entity_id == subject and not row.meta.business_date
    assert row.meta.raw.key.startswith("responses/") and row.meta.valid_from_ns > 0
    assert dgm.outcome_counts.recorded == 1 and dgm.counts.recorded >= 0


async def test_a_contract_that_pays_nothing_settles_at_nothing(lake: Lake) -> None:
    dgm = dgm_on(lake)
    await _resolved(lake, dgm, venue.RESOLVED_LOSER)
    [row] = lake.rows("RecordOutcomes")
    assert ops.OutcomeDetermination.Name(row.determination) == "OUTCOME_DETERMINATION_PAYS_NOTHING"
    assert as_decimal(row.settlement_value.amount) == 0


async def test_a_partial_payout_settles_at_its_part(lake: Lake) -> None:
    dgm = dgm_on(lake)
    await _resolved(lake, dgm, venue.PARTIAL)
    [row] = lake.rows("RecordOutcomes")
    assert ops.OutcomeDetermination.Name(row.determination) == "OUTCOME_DETERMINATION_PAYS_PART"
    assert str(as_decimal(row.settlement_value.amount)) == venue.PARTIAL_VALUE


async def test_an_outcome_stated_again_unchanged_sends_nothing_even_after_a_restart(
    lake: Lake, tmp_path: Path
) -> None:
    dgm = dgm_on(lake)
    dgm.contracts = venue.ContractMap(tmp_path / "contracts-synthetic.json")
    subject = await _resolved(lake, dgm, venue.RESOLVED)
    await dgm.record_live([subject], data_type=PRICE)
    assert await dgm.watch_outcomes() == 0
    again = dgm_on(lake)
    again.contracts = venue.ContractMap(tmp_path / "contracts-synthetic.json")
    assert again.contracts.load()
    assert await again.watch_outcomes() == 0 and await again.reread() is again.contracts
    assert len(lake.rows("RecordOutcomes")) == 1


async def test_each_later_stage_is_a_new_version_valid_from_the_determination(lake: Lake) -> None:
    dgm = dgm_on(lake)
    await _resolved(lake, dgm, venue.RESOLVED)
    [first] = lake.rows("RecordOutcomes")
    for directory, stage, settled_at_ns in venue.LATER:
        dgm.market = venue.market(directory=directory)
        assert await dgm.watch_outcomes() == 1
        row = lake.rows("RecordOutcomes")[-1]
        assert ops.OutcomeStage.Name(row.stage) == stage and row.settled_at_ns == settled_at_ns
        assert row.meta.row_key == first.meta.row_key
        assert row.meta.valid_from_ns == first.meta.valid_from_ns
        assert row.determination == first.determination
    assert lake.versions[("outcome", first.meta.row_key)][0] == 1 + len(venue.LATER)


async def test_a_contract_past_its_close_not_yet_determined_records_nothing(lake: Lake) -> None:
    dgm = dgm_on(lake)
    await _resolved(lake, dgm, venue.PENDING)
    asked = dgm.market.session.health.calls
    assert await dgm.watch_outcomes() == 0
    assert dgm.market.session.health.calls == asked + 1, "read again, past its close"
    assert not lake.on("RecordOutcomes")


async def test_a_contract_still_trading_or_final_is_not_read_again(lake: Lake) -> None:
    dgm = dgm_on(lake)
    await _resolved(lake, dgm, venue.BASE)
    asked = dgm.market.session.health.calls
    assert await dgm.watch_outcomes() == 0
    assert dgm.market.session.health.calls == asked, "trading before its close: not read again"
    await _resolved(lake, dgm, venue.RESOLVED)
    for directory, _, _ in venue.LATER:
        dgm.market = venue.market(directory=directory)
        await dgm.watch_outcomes()
    asked = dgm.market.session.health.calls
    assert await dgm.watch_outcomes() == 0
    assert dgm.market.session.health.calls == asked, "final: not read again"
