"""The declaration: the catalogue declared from code, as registration and
`meridian plugin upload` read it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from polymarket_us.declaration import DECLARATION
from polymarket_us.declared import CATALOGUE, SAMPLE_DATA, TERMS


def test_a_live_dataset_of_prices_and_quotes() -> None:
    live, _ = CATALOGUE
    assert (live.key, live.vendor, live.day_time_zone, live.day_end_minute) == (
        "live",
        "Polymarket US",
        "Etc/UTC",
        0,
    )
    assert list(live.data_types) == ["meridian.v1.Price", "meridian.v1.Quote"]
    assert live.venue_id == "", "the venue's ID is resolved at run time, never invented"
    # Contract 30 (ruling 1032): Polymarket US's terms in words, no licence;
    # a gap is not fetched again, Polymarket US serving no history of a book.
    assert (live.terms_and_pricing, live.gap_recovery) == (TERMS, "stream_only")


def test_an_outcomes_dataset_pushed() -> None:
    _, outcomes = CATALOGUE
    assert (outcomes.key, outcomes.vendor) == ("outcomes", "Polymarket US")
    assert list(outcomes.data_types) == ["meridian.v1.Outcome"]
    assert outcomes.venue_id == "" and outcomes.history == 0
    assert (outcomes.terms_and_pricing, outcomes.gap_recovery) == (TERMS, "stream_only")


def test_polymarket_uss_terms_in_words() -> None:
    assert 0 < len(TERMS) <= 2000 and "no key" in TERMS and "Terms of Service" in TERMS


def test_no_key_needed_and_sample_data_a_developers_setting() -> None:
    # The data role's settings (spec/plugin-pages-follow-their-role): one
    # environment and no credential, so sample data alone, labelled as the
    # SDK's helper labels it.
    assert isinstance(DECLARATION.settings, tuple)
    [setting] = DECLARATION.settings
    assert (setting.name, setting.developer, setting.secret) == (SAMPLE_DATA, True, False)
    assert (setting.label, setting.default) == ("Sample data", False)
    assert DECLARATION.storage is not None


def test_upload_reads_the_same_declaration() -> None:
    printed = subprocess.run(
        [str(Path(sys.executable).parent / "meridian-declaration"),
         "polymarket_us.declaration:DECLARATION"],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    datasets = json.loads(printed.stdout)["catalogue"]["datasets"]
    assert [d["key"] for d in datasets] == ["live", "outcomes"]
    assert [d["modes"] for d in datasets] == [["pull", "stream"], ["push"]]
