"""The contract map, kept in the plugin's own storage (the plan's "Identifiers
for a pair"): which of the venue's binary event contracts each subject the
lake asked for is, each contract as the venue last stated it, and the
deployment's instrument the venue's cash resolved to.

**Per subject wanted, never the whole venue.** The lake wants instruments by
the deployment's ID; the plugin reads each record (W3.6, a data plugin's from
contract v18 as ruled 2026-10-10), names the venue's contract it is by its
identifiers, and asks the venue for that one contract. Nothing else is read
from the venue, and nothing is resolved for a contract no subject is, so no
record is minted for each market the venue lists.

**The cash** -- the asset the venue's prices and payouts are in -- is resolved
through W3.1 once, by the identifiers the venue's own statements give it: a
currency by its ISO 4217 code, the venue's own token instrument by its code
with the venue as source. A record is minted only where none resolves; one
that does not resolve (its identifiers meet two records) is reported through
W3.2, once, and nothing is priced until it does.

**The outcomes recorded** (contract v23): each contract's determination as
last recorded in the lake -- its stage, its settlement value, the venue's
word, its valid time and the raw record it was read from -- so a version is
recorded only when the venue's statement changes, and a restart sends
nothing the lake holds already.

It is the plugin's to rebuild: kept as `contracts-<mode>.json` beside the raw
records, read at start, and each contract read again from the venue once a
day. Nothing else reads it (decisions/028).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .market import Contract, Resolution, Unread


@dataclass(frozen=True)
class Recorded:
    """A contract's outcome as last recorded in the lake (contract v23)."""

    stage: str
    #: What one contract settles at, in the venue's cash, as text.
    value: str
    scheme: str
    word: str
    text: str
    settled_at_ns: int
    #: Its valid time, the determination's, and whether the venue stated it.
    valid_from_ns: int
    stated: bool
    raw_key: str

    def says(self) -> tuple[str, Decimal, str, str, str, int]:
        """What the venue stated, which a new version changes."""
        return (self.stage, Decimal(self.value), self.scheme, self.word, self.text,
                self.settled_at_ns)  # fmt: skip


@dataclass(frozen=True)
class Mapped:
    """A contract serving a subject, the venue's cash resolved."""

    contract: Contract
    subject: str
    cash_id: str


def _resolution(held: dict[str, Any] | None) -> Resolution | None:
    if not held:
        return None
    value = held.get("value")
    return Resolution(
        stage=held["stage"],
        value=None if value is None else Decimal(value),
        scheme=held.get("scheme", ""),
        word=held.get("word", ""),
        text=held.get("text", ""),
        determined_at_ns=int(held.get("determined_at_ns", 0)),
        settled_at_ns=int(held.get("settled_at_ns", 0)),
        unread=tuple(Unread(**u) for u in held.get("unread", [])),
    )


def _contract(held: dict[str, Any]) -> Contract:
    payout = held.get("payout")
    return Contract(
        code=held["code"],
        title=held.get("title", ""),
        binary=bool(held.get("binary", False)),
        payout=None if payout is None else Decimal(payout),
        closes_at_ns=int(held.get("closes_at_ns", 0)),
        tradable=bool(held.get("tradable", True)),
        status=held.get("status", ""),
        market=held.get("market", ""),
        raw_key=held.get("raw_key", ""),
        unread=tuple(Unread(**u) for u in held.get("unread", [])),
        resolution=_resolution(held.get("resolution")),
        read_at_ns=int(held.get("read_at_ns", 0)),
    )


def _held(contract: Contract) -> dict[str, Any]:
    body = asdict(contract)
    body["payout"] = None if contract.payout is None else str(contract.payout)
    if contract.resolution is not None:
        value = contract.resolution.value
        body["resolution"]["value"] = None if value is None else str(value)
    return body


class ContractMap:
    """The contracts the lake's subjects are, and what the cash resolved to."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        #: Each contract read, by the venue's code.
        self.contracts: dict[str, Contract] = {}
        #: Which contract each subject is, by the deployment's instrument ID,
        #: read from its record.
        self.subjects: dict[str, str] = {}
        #: The deployment's instrument for the venue's cash, once resolved.
        self.cash_id = ""
        #: Each asset or contract reported as missing, by the venue's code,
        #: and why.
        self.missing: dict[str, str] = {}
        #: When the contracts were last read again, in UTC nanoseconds.
        self.read_at_ns = 0
        #: Each contract's outcome as last recorded, by the venue's code.
        self.outcomes: dict[str, Recorded] = {}

    # ── Kept ─────────────────────────────────────────────────────────────

    def load(self) -> bool:
        """Read the map kept in storage; whether there was one."""
        if self.path is None or not self.path.is_file():
            return False
        held: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        self.contracts = {c["code"]: _contract(c) for c in held.get("contracts", [])}
        self.subjects = dict(held.get("subjects", {}))
        self.cash_id = str(held.get("cash_id", ""))
        self.missing = dict(held.get("missing", {}))
        self.read_at_ns = int(held.get("read_at_ns", 0))
        self.outcomes = {code: Recorded(**o) for code, o in held.get("outcomes", {}).items()}
        return True

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "contracts": [_held(c) for _, c in sorted(self.contracts.items())],
            "subjects": self.subjects,
            "cash_id": self.cash_id,
            "missing": self.missing,
            "read_at_ns": self.read_at_ns,
            "outcomes": {code: asdict(o) for code, o in sorted(self.outcomes.items())},
        }
        written = self.path.with_suffix(".tmp")
        written.write_text(json.dumps(body, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(written, self.path)

    # ── Read ─────────────────────────────────────────────────────────────

    def serving(self, subject: str) -> Mapped | None:
        """The contract a subject is, where the cash has resolved; None
        otherwise."""
        code = self.subjects.get(subject, "")
        contract = self.contracts.get(code)
        if contract is None or not self.cash_id:
            return None
        return Mapped(contract, subject, self.cash_id)

    def mapped(self) -> list[Mapped]:
        """Every contract serving a subject, each once, for the first subject
        it serves."""
        seen: dict[str, Mapped] = {}
        for subject in sorted(self.subjects):
            mapped = self.serving(subject)
            if mapped is not None:
                seen.setdefault(mapped.contract.code, mapped)
        return [seen[code] for code in sorted(seen)]

    def code_of(self, instrument_id: str) -> str:
        """The venue's code a subject is, or the cash resolved to; empty if
        none."""
        if instrument_id in self.subjects:
            return self.subjects[instrument_id]
        return "cash" if instrument_id and instrument_id == self.cash_id else ""
