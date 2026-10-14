"""Record Polymarket US's real answers for `make e2e-recorded`: the plugin's own
client asks Polymarket US's public gateway -- no key, no account -- for each
market named by its slug, and keeps every answer as the plugin keeps its raw
records, under a directory of its own.

Run in the plugin's image, which carries the package and the SDK, writing
into recordings/ (git-ignored: a recording is the developer's who made it,
never committed; the plan's Q11):

    make image
    docker run --rm --entrypoint python -v "$PWD/e2e":/e2e:ro \\
        -v "$PWD/recordings":/recordings polymarket-us:local /e2e/record.py SLUG [SLUG ...]
    make e2e-recorded RECORDED=recordings/<the directory it printed>

Each market, its book twice a second apart, and its settlement are asked; a
market Polymarket US knows nothing by, or states no settlement of, is kept
as its answer. Standard library and the plugin only.
"""

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from polymarket_us.raw import RawStore
from polymarket_us.venue import Polymarket, VenueError


def main(slugs):
    if not slugs:
        print("name at least one Polymarket US market's slug", file=sys.stderr)
        return 2
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = Path("/recordings") / stamp
    client = Polymarket(RawStore(root))
    for slug in slugs:
        for ask in (client.market, client.book, client.settlement):
            try:
                ask(slug)
            except VenueError as refused:
                print(f"{slug}: {refused}", file=sys.stderr)
        time.sleep(1)
        try:
            client.book(slug)
        except VenueError as refused:
            print(f"{slug}: {refused}", file=sys.stderr)
    print(f"recordings/{stamp}: {client.health.calls} answers kept")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
