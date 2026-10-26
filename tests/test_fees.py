"""Polymarket US's published taker fee rate by market category, on
Connection and in `read_connection` (fees.py; from 0.5.0): each rate as its
fee schedule states it, with its source and the day it was read."""

from __future__ import annotations

from decimal import Decimal

from meridian.testing import PageClient

from polymarket_us import page
from polymarket_us.fees import FEES


def test_each_rate_is_the_venues_text() -> None:
    assert FEES.source == "https://docs.polymarket.us/fees"
    assert FEES.read_on == "2026-10-26" and not FEES.not_read
    rates = {r.category: r.taker for r in FEES.rates}
    assert Decimal(rates["Every category but Table Tennis"]) == Decimal("0.0695")
    assert Decimal(rates["Table Tennis"]) == Decimal("0.10")
    assert "effective 2026-10-19" in FEES.formula


def test_connection_answers_and_shows_the_fees() -> None:
    client = PageClient(page.pages)
    fees = client.call_tool("read_connection", level="admin").data["fees"]
    assert fees["source"] == FEES.source and len(fees["rates"]) == len(FEES.rates)
    shown = client.get("/", "admin").text
    assert "Taker by category: Every category but Table Tennis 0.0695" in shown
