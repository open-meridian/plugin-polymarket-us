"""Synthetic mode: Polymarket US's answers from files, never from Polymarket
US.

A developer's setting (`sample_data`, shown only on a development
deployment) turns it on. The client asks exactly as it asks Polymarket US,
keeps each answer as a raw record and reads it the same way; only the
transport differs:

- `Synthetic`: the synthetic exchanges this package carries (`synthetic/`),
  shaped exactly as Polymarket US documents and sends its public answers --
  a market with its `marketSides`, a book's levels and statistics with each
  amount a value as text and its currency, a settlement price as a JSON
  number -- with invented markets, invented slugs and invented values. They
  are what CI and `make e2e` replay.
- `Recorded`: a developer's own recorded exchanges -- the raw records a
  plugin kept of Polymarket US's real answers to its public reads --
  replayed by `make e2e-recorded` from a directory that is never committed
  (the plan's Q11).
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any

from .venue import Response

_HEADERS = {"cache-control": "no-store"}
_FILES = ("markets", "book", "settlement")
#: Polymarket US's answer for a market it knows nothing of, or states no
#: settlement of: a 404 with a gRPC status.
_NOT_FOUND = b'{"code":5, "message":"The server was unable to process your request.", "details":[]}'


def _found(body: Any) -> Response:
    return Response(200, dict(_HEADERS), json.dumps(body).encode("utf-8"))


def _not_found() -> Response:
    return Response(404, dict(_HEADERS), _NOT_FOUND)


def _asked(url: str) -> tuple[str, str] | None:
    """Which call a request is, and of which market's slug."""
    parts = [urllib.parse.unquote(p) for p in urllib.parse.urlsplit(url).path.split("/") if p]
    if len(parts) == 4 and parts[:3] == ["v1", "market", "slug"]:
        return "markets", parts[3]
    if len(parts) == 4 and parts[:2] == ["v1", "markets"] and parts[3] in ("book", "settlement"):
        return parts[3], parts[2]
    return None


class Synthetic:
    """Answers from a directory of synthetic exchanges: `markets.json`, the
    market answer per slug, `book.json`, the book's per slug, and
    `settlement.json`, the settlement's per slug."""

    def __init__(self, directory: Path | None = None) -> None:
        root = directory or Path(str(resources.files("polymarket_us") / "synthetic"))
        self.held: dict[str, dict[str, Any]] = {
            name: json.loads((root / f"{name}.json").read_text(encoding="utf-8")) for name in _FILES
        }

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        asked = _asked(url)
        if asked is None:
            return _not_found()
        call, slug = asked
        body = self.held[call].get(slug)
        return _found(body) if body is not None else _not_found()


class Recorded:
    """Answers from a developer's recorded raw records (raw.py's files under a
    `responses/` directory): the latest answer kept for each call and slug,
    a 404 among them."""

    def __init__(self, directory: Path) -> None:
        self.latest: dict[tuple[str, str], tuple[int, int, str]] = {}
        for path in sorted(directory.rglob("*")):
            if path.suffix == ".json":
                records = [json.loads(path.read_text(encoding="utf-8"))]
            elif path.suffix == ".jsonl":
                records = [
                    json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                ]
            else:
                continue
            for record in records:
                status = int(record.get("status", 0))
                asked = _asked(str(record.get("request", {}).get("url", "")))
                if asked is None or status not in (200, 404):
                    continue
                at = int(record.get("received_at_ns", 0))
                held = self.latest.get(asked)
                if held is None or at >= held[0]:
                    self.latest[asked] = (at, status, str(record["body"]))

    def calls(self) -> set[tuple[str, str]]:
        """Each call and slug the recording answers."""
        return set(self.latest)

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        asked = _asked(url)
        held = self.latest.get(asked) if asked else None
        if held is None:
            return _not_found()
        return Response(held[1], dict(_HEADERS), held[2].encode("utf-8"))
