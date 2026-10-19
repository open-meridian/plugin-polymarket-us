"""The plugin's pages, under Manage: the data role's Connection and Datasets
(spec/plugin-pages-follow-their-role), as the SDK draws them for an
event-contract venue (`meridian.roles.data.event_contracts`), Polymarket
US's names and words read from convert.py.

A data plugin shows no market data (ruled 2026-10-03): no price, bid, offer
or size is on either page; viewing prices is for the reading roles.

- **Connection** (`/`, `read_connection`): "Key" -- Live, or Sample data;
  "No key needed"; what Polymarket US entitles it to; the venue master's ID it
  resolved -- "Limits and use", and "Stream": "Does not stream", since it
  reads each contract when it is wanted, at most once a second.
- **Datasets** (`/datasets`, `read_datasets`): "Served" (`live`, and
  `outcomes`), "Wants" (searched and paged), "Subjects", then a section under
  Polymarket US's name: the contract map, the cash its prices and payouts
  are in, each contract's payout, and how a Polymarket US market makes a
  contract (its one instrument, its NO side the instrument held short).

Each page declares the record it renders (`answers=`), so each is also a
read tool on the deployment's MCP surface answering the same record.
"""

from __future__ import annotations

import meridian
from meridian import Figure
from meridian.roles.data import event_contracts

from .convert import ENTITLED as ENTITLED
from .convert import NAME, VENDOR_NOTE, VENUE
from .declared import CATALOGUE

TITLE = NAME
#: The kit the pages are built against: 0.12.0's next step (`data-om-opens`).
KIT = "0.12.0"

pages = meridian.Pages(TITLE, kit=KIT)


class _Held:
    feed: event_contracts.Feed | None = None


HELD = _Held()


def hold(feed: event_contracts.Feed) -> None:
    """The work the pages show."""
    HELD.feed = feed


def connection_now() -> event_contracts.ConnectionRead:
    return event_contracts.connection_read(HELD.feed, NAME, ENTITLED)


def datasets_now() -> event_contracts.DatasetsRead:
    return event_contracts.datasets_read(HELD.feed, CATALOGUE, VENUE, ENTITLED, VENDOR_NOTE)


@pages.page(
    "/",
    "Connection",
    levels="admin",
    answers=event_contracts.ConnectionRead,
    name="read_connection",
)
def connection(request: meridian.Request) -> meridian.Response:
    """How the plugin reaches Polymarket US: the mode, no key needed, what
    Polymarket US entitles it to and the venue master's ID it resolved; its
    limits and what the plugin spends of them, its calls, the last call and
    the last error; and that it does not stream."""
    return pages.answer("meridian/roles/data/event_contracts/connection.html", connection_now())


@pages.page(
    "/datasets", "Datasets", levels="admin", answers=event_contracts.DatasetsRead,
    name="read_datasets",
)  # fmt: skip
def datasets(request: meridian.Request) -> meridian.Response:
    """What the plugin serves the lake: its datasets and whether each is
    licensed, what Polymarket US entitles it to, what it recorded and
    declined; the wants it heard and the standing wants it keeps current;
    whether it may read an instrument's record; and the contract map, the
    cash its prices and payouts are in, and how a Polymarket US market makes
    a contract."""
    return pages.answer(
        "meridian/roles/data/event_contracts/datasets.html", datasets_now(), venue=NAME
    )


def figures_now() -> list[Figure]:
    """The data role's figures on the Summary, in its order: Connection,
    Entitled at the vendor, Stream ("Does not stream") and Last recorded.
    Polymarket US states no running rate to measure against, so Rate use is
    left out."""
    return event_contracts.figures_read(HELD.feed, CATALOGUE)
