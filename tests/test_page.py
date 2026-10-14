"""The pages, Connection and Datasets, and their read tools.

Asked in-process as the sidecar would ask them
(`meridian.testing`), after the plugin has answered wants on its synthetic
exchange: each page is served under Manage alone, shows no price, bid,
offer or size, fits its rows on one line each, holds the data role's
sections in the role's order, and its tool answers what the page shows
under the role's names; the wants, which grow, carry the kit's search and
pager; Datasets says whether a deployment admin licensed its dataset
(contract v20); and the role's figures come in the role's order.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest
from meridian.operations import as_decimal
from meridian.testing import PageClient

import venue_cases as venue
from conftest import Lake, dgm_on, hear, wanted

TOOLS = {"read_connection": "/", "read_datasets": "/datasets"}


@pytest.fixture
async def worked() -> tuple[Any, Lake]:
    lake = Lake()
    dgm = dgm_on(lake)
    subject = await lake.held(dgm, venue.BASE)
    await hear(lake, dgm, wanted(dgm, "WNT-1", [subject]))
    await hear(lake, dgm, wanted(dgm, "WNT-2", [subject], data_type="meridian.v1.Quote",
                                 standing=True))  # fmt: skip
    venue.page.hold(dgm)
    return dgm, lake


def _figures(lake: Lake) -> set[str]:
    """Every price, side and size the plugin recorded, as its text."""
    shown = {str(as_decimal(r.price.amount)) for r in lake.rows()}
    for quote in lake.rows("RecordQuotes"):
        shown |= {str(as_decimal(getattr(quote, f).amount)) for f in ("bid", "ask")
                  if quote.HasField(f)}  # fmt: skip
        shown |= {str(as_decimal(getattr(quote, f))) for f in ("bid_quantity", "ask_quantity")
                  if quote.HasField(f)}  # fmt: skip
    return shown


def test_each_page_is_served_under_manage_alone(worked: tuple[Any, Lake]) -> None:
    client = PageClient(venue.page.pages)
    served = {(r.page.path, r.level): r.response.status for r in client.every_page()}
    assert {path for path, _ in served} == {"/", "/datasets"}
    for (_, level), status in served.items():
        assert status == (200 if level == "admin" else 403), (level, status)


def test_no_page_shows_a_price_a_side_or_a_size(worked: tuple[Any, Lake]) -> None:
    _, lake = worked
    figures = _figures(lake)
    assert figures, "the plugin recorded prices and quotes for the pages to leave out"
    for path in TOOLS.values():
        text = PageClient(venue.page.pages).get(path, "admin").text
        shown = [f for f in figures if re.search(rf"(?<![\d.]){re.escape(f)}(?![\d.])", text)]
        assert not shown, (path, shown)


def test_every_table_is_one_line_rows(worked: tuple[Any, Lake]) -> None:
    for path in TOOLS.values():
        text = PageClient(venue.page.pages).get(path, "admin").text
        tables = re.findall(r"<table[^>]*>", text)
        assert tables and all('class="one-line"' in t for t in tables), (path, tables)


def _sections(text: str) -> list[str]:
    return re.findall(r"<h2>([^<]*)</h2>", text)


def test_each_page_holds_the_roles_sections_in_its_order(worked: tuple[Any, Lake]) -> None:
    client = PageClient(venue.page.pages)
    assert _sections(client.get("/", "admin").text) == ["Key", "Limits and use", "Stream"]
    assert _sections(client.get("/datasets", "admin").text) == [
        "Served", "Wants", "Subjects", venue.page.TITLE,
    ]  # fmt: skip


def test_the_tools_answer_what_the_pages_show(worked: tuple[Any, Lake]) -> None:
    dgm, _ = worked
    client = PageClient(venue.page.pages)
    assert {t.name for t in venue.page.pages.tools} >= set(TOOLS)
    connection = client.call_tool("read_connection", level="admin")
    assert connection.outcome == "unchanged", connection.json
    data = connection.data
    # The role's common fields, under the role's names.
    assert (data["mode"], data["credentials"], data["entitled_at_vendor"]) == (
        "Sample data", [], venue.page.ENTITLED,
    )  # fmt: skip
    assert data["calls"] > 0 and data["last_call_at"] and data["sessions"] is None
    # The venue's, beside them.
    assert (data["venue"], data["venue_id"], data["healthy"]) == (
        dgm.market.name, dgm.venue.venue_id, True,
    )  # fmt: skip
    page = client.get("/", "admin").text.replace("&#39;", "'")
    assert "No key needed" in page and "Does not stream" in page
    assert dgm.venue.venue_id in page and data["allowed"] in page

    datasets = client.call_tool("read_datasets", level="admin").data
    assert [d["dataset"] for d in datasets["served"]] == [
        f"{venue.VENUE}:live",
        f"{venue.VENUE}:outcomes",
    ]
    assert [d["data"] for d in datasets["served"]] == ["Price, Quote", "Outcome"]
    assert [d["arrives"] for d in datasets["served"]] == ["pull, stream", "push"]
    assert datasets["served"][1]["default_terms"].startswith("kept"), "outcomes are kept"
    assert all(d["day"] == "Etc/UTC, ends 00:00" for d in datasets["served"])
    assert datasets["served"][0]["recorded"] > 0 and datasets["served"][0]["last_recorded"]
    assert datasets["served"][1]["recorded"] == 0, "no contract it serves is determined"
    assert datasets["standing_wants"] == 1
    assert [(w["want_id"], w["kept_current"]) for w in datasets["wants"]] == [
        ("WNT-2", True),
        ("WNT-1", False),
    ]
    assert (datasets["contracts_mapped"], datasets["subjects_named"]) == (1, 1)
    assert datasets["cash"] == venue.CASH and datasets["cash_instrument"] == dgm.contracts.cash_id
    assert datasets["payouts"] == [f"{venue.PAYOUT} {venue.CASH}"]
    assert datasets["reads_instruments"] is True
    shown = client.get("/datasets", "admin").text.replace("&#39;", "'")
    assert "1 contract mapped for 1 subject the lake asked for" in shown
    assert f"each contract pays {venue.PAYOUT} {venue.CASH}" in shown
    assert dgm.contracts.cash_id in shown and "Kept current" in shown
    assert datasets["vendor_note"] in shown


def test_datasets_says_whether_a_deployment_admin_licensed_it(worked: tuple[Any, Lake]) -> None:
    dgm, _ = worked
    client = PageClient(venue.page.pages)
    assert client.call_tool("read_datasets", level="admin").data["served"][0]["licensed"] is False
    assert "Not licensed yet" in client.get("/datasets", "admin").text
    dgm.licensed = frozenset({dgm.dataset("live"), dgm.dataset("outcomes")})
    served = client.call_tool("read_datasets", level="admin").data["served"]
    assert [d["licensed"] for d in served] == [True, True]
    shown = client.get("/datasets", "admin").text
    assert "Not licensed yet" not in shown and "Licensed" in shown


def test_an_outcome_recorded_counts_on_its_own_dataset(worked: tuple[Any, Lake]) -> None:
    dgm, lake = worked
    live = dgm.counts.recorded

    async def resolved() -> None:
        subject = await lake.held(dgm, venue.RESOLVED)
        await dgm.name([subject])
        await dgm.record_outcomes([dgm.contracts.serving(subject)])

    asyncio.run(resolved())
    served = PageClient(venue.page.pages).call_tool("read_datasets", level="admin").data["served"]
    assert [d["recorded"] for d in served] == [live, 1] and served[1]["last_recorded"]


def test_the_wants_carry_the_kits_search_beside_its_pager(worked: tuple[Any, Lake]) -> None:
    client = PageClient(venue.page.pages)
    text = client.get("/datasets", "admin").text
    assert re.findall(r"<om-pager[^>]*>", text) == ['<om-pager search="Search wants">']
    wants = text[text.index("<h2>Wants</h2>") : text.index("<h2>Subjects</h2>")]
    assert '<om-pager search="Search wants"><table class="one-line">' in wants
    assert "</table></om-pager>" in wants
    assert "/.meridian/ui/0.12.0/" in text, "built against the kit with the next step"
    assert len(client.call_tool("read_datasets", level="admin").data["wants"]) == 2


def test_with_no_wants_datasets_says_the_next_step(lake: Lake) -> None:
    venue.page.hold(dgm_on(lake))
    asked = PageClient(venue.page.pages).get("/datasets", "admin").text
    assert "No wants yet" in asked and "Ask a deployment admin to license them." in asked
    assert "<om-pager" not in asked
    admin = PageClient(venue.page.pages, deployment_admin=True).get("/datasets", "admin").text
    assert 'data-om-opens="data-sources"' in admin


def test_the_roles_figures_in_its_order(worked: tuple[Any, Lake]) -> None:
    figures = venue.page.figures_now()
    assert [f.label for f in figures] == [
        "Connection", "Entitled at the vendor", "Stream", "Last recorded",
    ]  # fmt: skip
    assert [f.value for f in figures[:3]] == ["Sample data", "2 of 2 datasets", "Does not stream"]


def test_a_tool_is_refused_below_manage(worked: tuple[Any, Lake]) -> None:
    client = PageClient(venue.page.pages)
    for name in TOOLS:
        assert client.call_tool(name, level="read").status == 403


def test_the_pages_say_nothing_of_the_venues_terms(worked: tuple[Any, Lake]) -> None:
    client = PageClient(venue.page.pages)
    for path in TOOLS.values():
        text = client.get(path, "admin").text.lower()
        assert "terms allow" not in text and "regulat" not in text and "complian" not in text
