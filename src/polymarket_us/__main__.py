"""Polymarket US's public market data as an Open Meridian data plugin.

It connects to the sidecar it is launched beside, declaring its catalogue,
its storage and its settings (declaration.py) and its pages (page.py), and
serves them. Then it hears what the lake wants of it, names each subject as
one of Polymarket US's contracts (contracts.py) and records it, records each
contract's outcome once Polymarket US settles it, and keeps each standing want
current (dgm.py), until stopped. Everything goes through the sidecar; nothing
but Polymarket US's public gateway is called, and with sample data not even
that (synthetic.py). Nothing is asked of Polymarket US until the lake wants
something of it, and then only the contracts wanted.

It holds nothing it cannot lose: Polymarket US's raw responses and the contract map
are kept in the storage the deployment grants it (decisions/028), and a
restart reads the map back and hears again what the lake wants.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Mapping
from datetime import UTC, datetime

import meridian

from . import raw
from .contracts import ContractMap
from .convert import PolymarketMarket
from .declaration import DECLARATION, SAMPLE_DATA
from .dgm import Dgm, cancelled
from .page import TITLE, figures_now, hold, pages
from .raw import RawStore, storage_root, tend
from .synthetic import Recorded, Synthetic
from .venue import Polymarket

log = logging.getLogger("polymarket-us")

#: Where a developer's recorded exchanges are replayed from, under the
#: plugin's storage, when `make e2e-recorded` mounts them there.
RECORDED = "recorded"


def market(store: RawStore, synthetic: bool) -> PolymarketMarket:
    """Polymarket US itself, or with sample data its answers from files: a
    developer's recorded exchanges where storage holds them, else this
    package's synthetic ones."""
    if not synthetic:
        return PolymarketMarket(Polymarket(store), "live")
    recorded = store.root / RECORDED
    if recorded.is_dir():
        return PolymarketMarket(Polymarket(store, transport=Recorded(recorded)), "recorded")
    return PolymarketMarket(Polymarket(store, transport=Synthetic()), "synthetic")


def contract_map(store: RawStore, mode: str) -> ContractMap:
    held = ContractMap(store.root / f"contracts-{mode}.json")
    held.load()
    return held


async def watch_settings(
    plugin: meridian.Plugin, dgm: Dgm, store: RawStore, configured: asyncio.Event
) -> None:
    """Each delivery of the settings: the source switched where synthetic
    mode changed, its own contract map read back from storage, and each day's
    raw responses past their window moved. Whatever it answers from, nothing
    is asked of the venue, and nothing resolved, until the lake wants
    something of it."""
    while True:
        try:
            await _apply_settings(plugin, dgm, store, configured)
        except Exception as failed:  # noqa: BLE001 - the stream broke: said, and watched again
            log.warning("the settings' stream broke, watching again: %s", failed)
        await asyncio.sleep(2)


async def _apply_settings(
    plugin: meridian.Plugin, dgm: Dgm, store: RawStore, configured: asyncio.Event
) -> None:
    async for delivered in plugin.settings():
        values = delivered.values
        log.info("settings delivered: sample data %s", values.get(SAMPLE_DATA))
        synthetic = values.get(SAMPLE_DATA) is True
        mode = dgm.market.session.mode
        if synthetic != (mode != "live"):
            chosen = market(store, synthetic)
            dgm.use(chosen, contract_map(store, chosen.session.mode))
            log.info("answering from %s", chosen.session.mode)
        configured.set()
        await tend_now(plugin, store, values)


async def tend_now(plugin: meridian.Plugin, store: RawStore, values: Mapping[str, object]) -> None:
    window = values.get(f"{raw.KIND}_window_days")
    past = values.get(f"{raw.KIND}_past_window")
    await tend(
        plugin,
        store,
        window if isinstance(window, int) else raw.WINDOW_DAYS,
        past if isinstance(past, str) else "kept",
        datetime.now(UTC).date(),
    )


async def hear_wants(plugin: meridian.Plugin, dgm: Dgm, configured: asyncio.Event) -> None:
    """What the lake wants, once the settings have said where to answer from."""
    await configured.wait()
    await plugin.receive(observations_wanted=dgm.on_want, want_withdrawn=dgm.on_withdrawn)


async def report_health(plugin: meridian.Plugin, dgm: Dgm) -> None:
    """Each minute: its datasets' licences read again (contract v20), and
    on the heartbeat whether Polymarket US answers, with the data role's figures."""
    while True:
        try:
            await dgm.read_licences()
        except meridian.MeridianError as failed:
            log.warning("licences not read: %s", failed)
        health = dgm.market.session.health
        healthy = health.last_ok_ns >= health.last_failed_ns
        detail = f"{dgm.market.name} answers" if healthy else health.last_error
        try:
            await plugin.report(healthy=healthy, detail=detail[:200], figures=figures_now())
        except (meridian.MeridianError, ValueError) as failed:
            log.warning("health not reported: %s", failed)
        await asyncio.sleep(60)


def _said(task: asyncio.Task[None]) -> None:
    """A task that stopped, said with why, and the plugin stopped with it: a
    restart starts it again."""
    if not task.cancelled() and task.exception() is not None:
        log.error("stopped: %r", task.exception(), exc_info=task.exception())
        os._exit(1)


async def run() -> None:
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(stop, stopped.set)

    port = int(os.environ.get("REFERENCE_PAGE_PORT", "8000"))
    async with await meridian.connect(
        interface=meridian.Interface(port=port, title=TITLE, pages=pages),
        declaration=DECLARATION,
        settings=DECLARATION.settings,
    ) as plugin:
        log.info("registered as %s, roles %s", plugin.identity.instance_id, plugin.identity.roles)
        store = RawStore(storage_root())
        chosen = market(store, synthetic=False)
        dgm = Dgm(plugin, chosen, contract_map(store, chosen.session.mode))
        hold(dgm)
        served = pages.serve(plugin, port)
        configured = asyncio.Event()
        tasks = [
            asyncio.create_task(watch_settings(plugin, dgm, store, configured)),
            asyncio.create_task(hear_wants(plugin, dgm, configured)),
            asyncio.create_task(dgm.keep_current()),
            asyncio.create_task(report_health(plugin, dgm)),
        ]
        for task in tasks:
            task.add_done_callback(_said)
        await stopped.wait()
        log.info("stopping")
        for task in tasks:
            await cancelled(task)
        served.shutdown()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
