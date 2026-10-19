"""Polymarket US's answers read into the venue's values: one market, one
instrument, its YES side the contract, paying one dollar; its book and last
trade from one answer; its outcome only once its final settlement is
published."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from meridian.roles.data.event_contracts import FINAL, Contract

from polymarket_us import convert
from polymarket_us.venue import Fetched

import venue_cases as venue

CONTRACT = Contract(code="aec-x", title="A vs. B: A", binary=True, payout=Decimal("1.00"))


def _usd(value: str, currency: str = "USD") -> dict[str, str]:
    return {"value": value, "currency": currency}


def _side(words: str, long: bool, price: str = "0.5") -> dict[str, Any]:
    return {"id": "1", "identifier": "aec-x", "description": words, "long": long,
            "price": price, "quote": _usd(price)}  # fmt: skip


MARKET = {
    "id": "4",
    "question": "Atlanta vs. New England",
    "slug": "aec-x",
    "title": "Atlanta vs. New England",
    "endDate": "2026-12-31T23:59:00Z",
    "active": True,
    "closed": False,
    "status": "MARKET_STATUS_OPEN",
    "marketSides": [_side("Falcons", True), _side("Patriots", False)],
}


def _top(book: dict[str, Any]) -> Any:
    return convert.top(CONTRACT, {"marketData": book}, "responses/2026-10-10/book/aec-x.jsonl#0", 7)


def test_a_market_is_one_binary_contract_its_yes_side_paying_one_dollar() -> None:
    read = convert.contract(MARKET, "raw", 5)
    assert read.code == "aec-x" and read.binary and read.payout == Decimal("1.00")
    assert read.title == "Atlanta vs. New England: Falcons", "the long side's own words"
    assert read.market == "4" and read.tradable and read.status == "MARKET_STATUS_OPEN"
    assert read.closes_at_ns == 1_798_761_540 * 1_000_000_000
    assert read.resolution is None and read.raw_key == "raw" and read.read_at_ns == 5
    yes_no = MARKET | {"question": "Champion", "title": "Herons",
                       "marketSides": [_side("Yes", True), _side("No", False)]}  # fmt: skip
    assert convert.contract(yes_no, "raw").title == "Champion: Herons"


def test_a_market_not_one_long_and_one_short_side_is_not_binary() -> None:
    three = MARKET | {"marketSides": [_side("A", True), _side("B", True), _side("C", False)]}
    assert not convert.contract(three, "raw").binary
    assert not convert.contract(MARKET | {"marketSides": []}, "raw").binary


def test_only_an_open_market_trades() -> None:
    for status in ("MARKET_STATUS_CLOSED", "MARKET_STATUS_HALTED", "MARKET_STATUS_RESOLVING"):
        assert not convert.contract(MARKET | {"status": status}, "raw").tradable
    unstated = MARKET | {"status": "MARKET_STATUS_UNSPECIFIED"}
    assert convert.contract(unstated, "raw").tradable
    assert not convert.contract(unstated | {"closed": True}, "raw").tradable


def test_an_amount_in_another_currency_is_kept_as_sent() -> None:
    euros = MARKET | {"marketSides": [_side("A", True) | {"quote": _usd("0.5", "EUR")},
                                      _side("B", False)]}  # fmt: skip
    assert [(u.field, u.text) for u in convert.contract(euros, "raw").unread] == [
        ("marketSides.quote.currency", "EUR")
    ]


def test_the_best_bid_is_the_highest_and_the_best_offer_the_lowest() -> None:
    top = _top({
        "bids": [{"px": _usd("0.4100"), "qty": "1200"}, {"px": _usd("0.4300"), "qty": "550.5"}],
        "offers": [{"px": _usd("0.4700"), "qty": "300"}, {"px": _usd("0.4500"), "qty": "125.25"}],
        "transactTime": "2026-10-10T11:59:50.123456789Z",
    })  # fmt: skip
    assert (str(top.bid), str(top.bid_size), str(top.ask), str(top.ask_size)) == (
        "0.4300", "550.5", "0.4500", "125.25",
    )  # fmt: skip
    assert top.stated and top.at_ns == 1_791_633_590_123_456_789


def test_an_empty_side_is_unset_and_a_level_that_does_not_read_kept_as_sent() -> None:
    top = _top({
        "bids": [{"px": _usd("x"), "qty": "1"}, {"px": _usd("0.2"), "qty": "?"},
                 {"px": _usd("0.3", "EUR"), "qty": "1"}],
        "offers": [],
        "transactTime": None,
    })  # fmt: skip
    assert str(top.bid) == "0.2" and top.bid_size is None and top.ask is None
    assert {u.field for u in top.unread} == {
        "marketData.bids.px.value", "marketData.bids.qty", "marketData.bids.px.currency",
    }  # fmt: skip
    assert top.stated is False and top.at_ns == 7


def test_the_last_trade_is_the_books_statistics_at_its_time() -> None:
    body = {"marketData": {"stats": {"lastTradePx": _usd("0.4400"),
                                     "lastTradeSetTime": "2026-10-10T11:59:41.5Z",
                                     "settlementPx": _usd("0.4000")}}}  # fmt: skip
    tick = convert.tick(CONTRACT, body, "k", 9)
    assert str(tick.price) == "0.4400" and tick.stated
    assert tick.at_ns == 1_791_633_581_500_000_000 and not tick.ident
    never = convert.tick(CONTRACT, {"marketData": {"stats": {"lastPriceSample": None}}}, "k", 9)
    assert never.price is None and not never.unread and never.at_ns == 9


def test_an_outcome_is_the_settlement_price_final_its_raw_record_the_settlement() -> None:
    settled = Fetched({"slug": "aec-x", "settlement": 1}, "responses/settlement/aec-x", 11)
    resolved = MARKET | {"status": "MARKET_STATUS_RESOLVED", "active": False, "closed": True}
    read = convert.contract(resolved, "raw", 5, settled)
    said = read.resolution
    assert said is not None and said.stage == FINAL and said.value == 1
    assert (said.scheme, said.word, said.text) == ("polymarket-us:settlement", "1", "1")
    assert said.settled_at_ns == 0 and said.determined_at_ns == 0, "Polymarket US states neither"
    assert (read.raw_key, read.read_at_ns) == ("responses/settlement/aec-x", 11)
    part = convert.resolution({"settlement": Decimal("0.45")})
    assert part.value == Decimal("0.45") and part.word == "0.45"
    unread = convert.resolution({"settlement": "n/a"})
    assert unread.value is None and unread.unread


def test_the_synthetic_exchange_reads_as_the_cases_say() -> None:
    market = venue.market()
    base = market.contract(venue.BASE)
    assert base is not None and str(base.payout) == venue.PAYOUT and base.resolution is None
    assert str(market.last(base).price) == venue.LAST
    top = market.top(base)
    assert (str(top.bid), str(top.ask)) == (venue.BID, venue.ASK)
    one = market.contract(venue.ONE_SIDED)
    assert one is not None and market.last(one).price is None, "never traded"
    assert market.contract("no-such-market") is None
    assert market.cash.currency_code == "USD"
    assert market.venue_identifiers == (("iso10383", "QCEX", ""),)


def test_the_book_is_read_once_for_the_last_trade_and_the_quote() -> None:
    market = venue.market()
    base = market.contract(venue.BASE)
    assert base is not None
    before = market.session.health.calls
    market.last(base)
    market.top(base)
    assert market.session.health.calls == before + 1
    market.top(base)
    assert market.session.health.calls == before + 2, "held for the one quote that follows"


def test_a_resolved_market_is_asked_its_settlement_and_no_other() -> None:
    market = venue.market()
    resolved = market.contract(venue.RESOLVED)
    assert resolved is not None and resolved.resolution is not None
    assert "/settlement" in resolved.raw_key or "settlement" in resolved.raw_key
    unsettled = market.contract(venue.UNSETTLED)
    assert unsettled is not None and unsettled.resolution is None
    pending = market.contract(venue.PENDING)
    assert pending is not None and pending.resolution is None and not pending.tradable
    asked = venue.calls(market)
    assert sum("/settlement" in url for url in asked) == 2, asked


# ── Contract v26: a range market's bounds ───────────────────────────────────


def _bounds(**terms: Any) -> Any:
    unread: list[Any] = []
    return convert.bounds({"assetPriceTerms": terms}, unread), unread


def test_a_range_buckets_bounds_are_inclusive_and_a_tail_has_one() -> None:
    (floor, cap), _ = _bounds(marketType=convert.RANGE, rangeKind="ASSET_PRICE_RANGE_KIND_INTERIOR",
                              rangeLower=_usd("74000.00"), rangeUpper=_usd("74499.99"))  # fmt: skip
    assert (str(floor.value), floor.inclusive, str(cap.value), cap.inclusive) == (
        "74000.00", True, "74499.99", True,
    )  # fmt: skip
    (floor, cap), _ = _bounds(marketType=convert.RANGE, rangeKind="ASSET_PRICE_RANGE_KIND_BELOW",
                              rangeLower=None, rangeUpper=_usd("73999.99"))  # fmt: skip
    assert floor is None and str(cap.value) == "73999.99" and cap.inclusive
    (floor, cap), _ = _bounds(marketType=convert.RANGE, rangeKind="ASSET_PRICE_RANGE_KIND_ABOVE",
                              rangeLower=_usd("76000.00"), rangeUpper=None)  # fmt: skip
    assert str(floor.value) == "76000.00" and floor.inclusive and cap is None


def test_an_above_below_strike_is_a_floor_inclusive_and_other_terms_none() -> None:
    (floor, cap), _ = _bounds(marketType=convert.ABOVE_BELOW, strike=_usd("74000"))
    assert (str(floor.value), floor.inclusive, cap) == ("74000", True, None)
    up_down = _bounds(marketType="ASSET_PRICE_MARKET_TYPE_UP_DOWN", priceToBeat=_usd("81650.14"))
    assert up_down[0] == (None, None)
    touch = _bounds(marketType="ASSET_PRICE_MARKET_TYPE_ONE_TOUCH", strike=_usd("90000"))
    assert touch[0] == (None, None)
    assert convert.bounds(MARKET, []) == (None, None), "a market without terms states none"
    assert convert.bounds(MARKET | {"assetPriceTerms": None}, []) == (None, None)


def test_a_bound_that_does_not_read_is_kept_as_sent_and_one_that_does_is_on_the_contract() -> None:
    (floor, _), unread = _bounds(marketType=convert.ABOVE_BELOW, strike=_usd("74000", "EUR"))
    assert floor is None and [(u.field, u.text) for u in unread] == [
        ("assetPriceTerms.strike.currency", "EUR")
    ]
    terms = {"marketType": convert.RANGE, "rangeLower": _usd("1"), "rangeUpper": _usd("2")}
    ranged = MARKET | {"assetPriceTerms": terms}
    read = convert.contract(ranged, "raw")
    assert read.floor is not None and read.cap is not None
    assert (str(read.floor.value), read.floor.inclusive) == ("1", True)
    assert (str(read.cap.value), read.cap.inclusive) == ("2", True)
    assert read.bound_unit == ""
