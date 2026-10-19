"""The SDK's checks for a data plugin of an event-contract venue, run
unchanged against this plugin's own conversion
(`meridian.roles.data.testing.EventContractsChecks`): the data suite, the
venue's work past the suite's cases, its outcomes, and the pages.
tests/venue_cases.py names Polymarket US's synthetic exchange for each."""

from __future__ import annotations

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data.testing import EventContractsChecks, event_contract_producers
from meridian.suites import run

import venue_cases


class TestEventContracts(EventContractsChecks):
    venue = venue_cases

    async def test_a_record_already_complete_is_not_resolved_again(self) -> None:
        """The SDK's check, its record complete as 0.31.0 joins one: open-
        meridian 0.31.0's own holds the record with the venue's symbol alone,
        but a venue with an ISO 10383 MIC is sent with its ticker beside it
        (ruling 312), so a record lacking the ticker is not complete. Gone
        once the SDK's check holds the ticker too (0.31.1)."""
        v, lake = self.venue, self.lake()
        feed = self.feed(lake)
        contract = await feed.contract(v.BASE)
        assert contract is not None
        ticker = ops.Identifier(scheme="ticker", value=contract.code, source="QCEX")
        subject = lake.instruments.hold(
            "INS-DONE", *feed.identifiers(contract), ticker,
            asset_class=ops.ASSET_CLASS_EVENT_CONTRACT,
            instrument_type=ops.INSTRUMENT_TYPE_BINARY_EVENT_CONTRACT,
        )  # fmt: skip
        await feed.record_live([subject], data_type="meridian.v1.Price")
        resolved = [r for r in lake.on("ResolveIdentifier") if r.stated_instrument_type]
        assert not resolved and lake.rows()


def test_the_data_suite_passes_unchanged() -> None:
    """The SDK's data suite, each case on this plugin's own exchange
    (`meridian.suites.run`), as `meridian plugin check` asks to see."""
    v = venue_cases
    report = run(
        "data", event_contract_producers(v), not_presented=v.NOT_PRESENTED, instance_id=v.VENUE
    )
    assert report.passed, report.failures
