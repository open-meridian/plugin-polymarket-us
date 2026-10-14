"""The client: every answer kept before it is read, the rate limit honoured, a
429 waited out, a 404 an answer rather than a failure, no key ever sent, and
synthetic mode's two transports answering as Polymarket US does."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from polymarket_us.raw import RawStore
from polymarket_us.synthetic import Recorded, Synthetic
from polymarket_us.venue import GATEWAY, Polymarket, RateLimiter, Response, VenueError

import venue_cases as venue

S = venue.BASE


def _client(tmp_path: Path, transport: object) -> Polymarket:
    clock = iter(range(1_791_633_600_000_000_000, 1_791_633_700_000_000_000, 1_000))
    return Polymarket(
        RawStore(tmp_path),
        transport=transport,  # type: ignore[arg-type]
        limiter=RateLimiter(1000.0, 1000, sleep=lambda _: None),
        clock_ns=lambda: next(clock),
        sleep=lambda _: None,
    )


class Scripted:
    def __init__(self, *answers: Response) -> None:
        self.answers = list(answers)
        self.asked: list[str] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        self.asked.append(url)
        assert "User-Agent" in headers, "named"
        assert not {h.lower() for h in headers} & {
            "authorization", "x-pm-access-key", "x-pm-signature", "x-pm-timestamp",
        }, "no key, ever"  # fmt: skip
        return self.answers.pop(0)


def test_every_answer_is_kept_before_it_is_read(tmp_path: Path) -> None:
    client = _client(tmp_path, Scripted(Response(200, {"date": "Sat"}, b'{"market":{}}')))
    fetched = client.market(S)
    kept = client.store.get(fetched.raw_key)
    assert kept is not None and kept["body"] == '{"market":{}}'
    assert kept["headers"] == {"date": "Sat"} and kept["status"] == 200
    assert fetched.raw_key.startswith("responses/2026-10-10/market/")


def test_each_call_asks_the_public_gateway_for_one_market(tmp_path: Path) -> None:
    scripted = Scripted(*[Response(200, {}, b"{}") for _ in range(3)])
    client = _client(tmp_path, scripted)
    client.market(S)
    client.book(S)
    client.settlement(S)
    assert GATEWAY == "https://gateway.polymarket.us"
    assert scripted.asked == [
        f"{GATEWAY}/v1/market/slug/{S}",
        f"{GATEWAY}/v1/markets/{S}/book",
        f"{GATEWAY}/v1/markets/{S}/settlement",
    ]


def test_a_slug_is_one_path_segment(tmp_path: Path) -> None:
    scripted = Scripted(Response(200, {}, b"{}"))
    _client(tmp_path, scripted).book("a/b?c")
    assert scripted.asked == [f"{GATEWAY}/v1/markets/a%2Fb%3Fc/book"]


def test_a_429_is_waited_out_and_counted(tmp_path: Path) -> None:
    scripted = Scripted(Response(429, {"retry-after": "1"}, b'{"status":429,"message":"slow"}'),
                        Response(200, {}, b'{"marketData":{}}'))  # fmt: skip
    client = _client(tmp_path, scripted)
    assert client.book(S).value == {"marketData": {}}
    assert (client.health.rate_limited, client.health.calls) == (1, 2)


def test_a_404_is_an_answer_kept_and_said_not_a_failure(tmp_path: Path) -> None:
    body = b'{"code":5, "message":"Settlement not found for market x", "details":[]}'
    client = _client(tmp_path, Scripted(Response(404, {}, body)))
    with pytest.raises(VenueError) as refused:
        client.settlement("x")
    assert refused.value.status == 404 and "Settlement not found" in str(refused.value)
    assert client.store.get(refused.value.raw_key) is not None
    assert client.health.failures == 0 and client.health.last_ok_ns > 0


def test_an_error_is_kept_and_said(tmp_path: Path) -> None:
    client = _client(tmp_path, Scripted(Response(500, {}, b'{"code":13,"message":"broken"}')))
    with pytest.raises(VenueError) as refused:
        client.market(S)
    assert "broken" in str(refused.value) and client.store.get(refused.value.raw_key)
    assert client.health.failures == 1 and "broken" in client.health.last_error


def test_no_answer_is_said(tmp_path: Path) -> None:
    def down(url: str, headers: Mapping[str, str]) -> Response:
        raise OSError("connection refused")

    client = _client(tmp_path, down)
    with pytest.raises(VenueError):
        client.book(S)
    assert client.health.failures == 1


def test_a_settlement_number_reads_as_a_decimal_never_a_float(tmp_path: Path) -> None:
    client = _client(tmp_path, Scripted(Response(200, {}, b'{"slug":"x","settlement":0.45}')))
    value = client.settlement("x").value["settlement"]
    assert not isinstance(value, float) and str(value) == "0.45"


def test_a_live_answer_unchanged_is_the_line_and_time_first_kept(tmp_path: Path) -> None:
    client = _client(tmp_path, Synthetic())
    first, second = client.book(S), client.book(S)
    assert first.raw_key == second.raw_key and first.raw_key.endswith(".jsonl#0")
    assert first.received_at_ns == second.received_at_ns


def test_synthetic_answers_polymarket_uss_shapes(tmp_path: Path) -> None:
    client = _client(tmp_path, Synthetic())
    market = client.market(S).value["market"]
    assert market["slug"] == S and [s["long"] for s in market["marketSides"]] == [True, False]
    assert client.book(S).value["marketData"]["bids"][0]["px"]["currency"] == "USD"
    assert client.settlement(venue.RESOLVED).value["settlement"] == 1
    for call, slug in ((client.market, "x"), (client.settlement, S)):
        with pytest.raises(VenueError) as refused:
            call(slug)
        assert refused.value.status == 404


def test_recorded_exchanges_are_replayed_from_a_plugins_raw_records(tmp_path: Path) -> None:
    recording = _client(tmp_path / "kept", Synthetic())
    recording.market(venue.RESOLVED)
    recording.book(S)
    recording.settlement(venue.RESOLVED)
    with pytest.raises(VenueError):
        recording.settlement(S)
    recorded = Recorded(tmp_path / "kept" / "responses")
    assert {("markets", venue.RESOLVED), ("book", S), ("settlement", venue.RESOLVED),
            ("settlement", S)} <= recorded.calls()  # fmt: skip
    replay = _client(tmp_path / "replayed", recorded)
    assert replay.market(venue.RESOLVED).value == recording.market(venue.RESOLVED).value
    assert replay.book(S).value == recording.book(S).value
    assert replay.settlement(venue.RESOLVED).value == recording.settlement(venue.RESOLVED).value
    for call, slug in ((replay.settlement, S), (replay.market, "never-recorded")):
        with pytest.raises(VenueError) as refused:
            call(slug)
        assert refused.value.status == 404
