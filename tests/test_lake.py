"""The plugin's data role class (from 0.12.0, open-meridian 0.35): `Lake`,
the SDK's event-contract feed held until the settings say where to answer
from, its source switched by them, and registered on one connection."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any

from meridian import Settings
from meridian.edge import RawStore
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles import data
from meridian.roles.data.testing import Lake as Recorder

from polymarket_us.__main__ import Lake, contract_map, market
from polymarket_us.declared import KIND, SAMPLE_DATA

import venue_cases as v


class Store(RawStore):
    """A raw store whose days are tended as said, nothing moved."""

    def __init__(self, root: Path) -> None:
        super().__init__(root, KIND)
        self.tended: list[tuple[int, str, date]] = []

    async def tend(self, plugin: Any, window_days: int, past: str, today: date) -> None:
        self.tended.append((window_days, past, today))


def _lake(tmp_path: Path) -> tuple[Lake, Store]:
    store = Store(tmp_path)
    chosen = market(store, synthetic=False)
    lake = Lake(chosen, contract_map(store, chosen.session.mode), store=store)
    Recorder(v.VENUE).bind(lake)
    return lake, store


def test_it_is_the_data_roles_class_hearing_what_the_lake_wants() -> None:
    assert issubclass(Lake, data.Role)
    assert Lake.role == "data"
    assert set(Lake.heard_rows()) == {"ObservationsWanted", "WantWithdrawn"}


async def test_the_settings_switch_it_to_sample_data_and_tend_its_store(tmp_path: Path) -> None:
    lake, store = _lake(tmp_path)
    assert lake.market.session.mode == "live"
    assert not lake.configured.is_set()
    await lake.on_settings(Settings(values={SAMPLE_DATA: True, f"{KIND}_window_days": 3}))
    assert lake.market.session.mode == "synthetic"
    assert lake.configured.is_set()
    assert [(days, past) for days, past, _ in store.tended] == [(3, "kept")]
    await lake.on_settings(Settings(values={SAMPLE_DATA: False}))
    assert lake.market.session.mode == "live"


async def test_a_want_waits_for_the_settings(tmp_path: Path) -> None:
    lake, _ = _lake(tmp_path)
    want = ops.ObservationsWantedEvent(want_id="WNT-1", dataset=f"{v.VENUE}:live")
    heard = asyncio.ensure_future(
        lake.on_observations_wanted(Heard(row="ObservationsWanted", message=want))
    )
    await asyncio.sleep(0.05)
    assert not heard.done()
    await lake.on_settings(Settings(values={SAMPLE_DATA: True}))
    await asyncio.wait_for(heard, 5)
    assert [h.want_id for h in lake.heard] == ["WNT-1"]


async def test_the_venue_is_resolved_through_the_role_not_the_connection(tmp_path: Path) -> None:
    """Registered by `meridian.run`, the class's connection makes no act:
    the venue is resolved through the role object (ruling 1023)."""
    lake, _ = _lake(tmp_path)
    recorder = Recorder(v.VENUE)
    lake._bind(object())  # a connection that makes no act, as the sidecar's
    lake._operate = recorder._operate  # type: ignore[method-assign]
    lake._operations = recorder._operations  # type: ignore[method-assign]
    assert await lake.venue_id()
    assert recorder.on("ResolveVenue")
