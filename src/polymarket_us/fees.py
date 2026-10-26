"""Polymarket US's published taker fee rate by market category, as it states
it, with where and when it was read (571's category column; task
sdk-contract/event-contract-fees-vary-by-market-category).

Read from docs.polymarket.us, "Fee Schedule" (`/fees`), on 2026-10-26,
"Effective exchange-wide from 1:00 PM ET, Monday, October 19, 2026":
"Fee = Θ x C x p x (1 - p)", C the contracts and p the trade price; the
taker's Θ 0.0695, and 0.10 for Table Tennis markets; makers pay none and are
rebated at their maker tier's Θ (-0.0035 to -0.0104; none below Tier 2);
combos take their own curve, "C x p x [0.0695 x (1 - p) + 0.06 x (1 -
p)^4]", with no maker rebate. Each market also states its own `category`
and `feeCoefficient` in its answer, which applies to it.

The rates are Polymarket US's words, kept as text and never computed with
here: the options sample's fee schedule (its settings) takes them, each
with this source and date. A newer schedule is read and dated again at the
plugin's next version.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rate:
    """One category's row, in the venue's words: its taker and maker fee
    rates as text, and its maker rebate ("" where the venue lists none)."""

    category: str
    taker: str
    maker: str
    maker_rebate: str = ""


@dataclass(frozen=True)
class Fees:
    """A venue's published fee schedule: where and when it was read, its
    formula, its rows, what makers pay, and where it states a market's own
    rate; why a rate is left out, where the schedule could not be read."""

    source: str = ""
    read_on: str = ""
    formula: str = ""
    rates: list[Rate] = field(default_factory=list)
    makers: str = ""
    per_market: str = ""
    not_read: str = ""


SOURCE = "https://docs.polymarket.us/fees"
READ_ON = "2026-10-26"

FEES = Fees(
    source=SOURCE,
    read_on=READ_ON,
    formula=(
        "fee = Θ x C x p x (1 - p), C contracts at price p; effective 2026-10-19; combos "
        "C x p x [0.0695 x (1 - p) + 0.06 x (1 - p)^4]"
    ),
    rates=[
        Rate("Every category but Table Tennis", "0.0695", "0", "-0.0035 to -0.0104 by maker tier"),
        Rate("Table Tennis", "0.10", "0", "-0.0035 to -0.0104 by maker tier"),
        Rate("Combos", "own curve", "0", "none"),
    ],
    makers="none charged; rebated by maker tier, none below Tier 2",
    per_market="each market states its own category and feeCoefficient, which applies to it",
)
