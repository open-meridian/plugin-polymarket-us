"""What this version declares beside its role (W8.1, W4.1; contracts v19 and
v23).

**Its catalogue** (spec/the-lake, "The catalogue"; the plan's Q21), declared
from code and read the same way at registration and by `meridian plugin
upload`:

- `live`: each Polymarket US contract's last trade price and best bid and
  offer as prices, and its best bid and offer with their sizes as a quote,
  polled from the public gateway at most once a second per subject, pulled
  for the latest or kept current for a standing want. Its day is the UTC day
  (`day_time_zone` `Etc/UTC`, `day_end_minute` 0): Polymarket US trades
  nearly around the clock, and the dataset records no daily value.
- `outcomes` (contract v23): each contract's outcome once Polymarket US
  publishes its final settlement, recorded unasked (`push`) for each
  contract a subject the lake asked for is, a contract past its end read
  again each minute until its outcome is recorded. It names no business
  date; its day is declared as the live dataset's.

**Its licence defaults**: `live` keeps its rows two days (the plan's Q21 for
a live dataset). `outcomes` is kept: an outcome is read back by the version
in force or as of a time, which a dataset not kept cannot answer (a plugin's
choice within contract v23, approved 2026-10-13). Neither default claims
anything about Polymarket US's terms, which the deployment admin settles
with whoever uses the deployment; the admin states the deployment's licence
on the Data sources page, which replaces it.

`venue_id` is empty: the venue master's ID for Polymarket US is minted by
the platform, not known to the code a catalogue is declared from, so each
row names the venue by the ID it resolves at run time (dgm.py), by its
ISO 10383 MIC, `QCEX`.

**Its storage**: one kind of raw record, Polymarket US's responses as
received, kept a month by default (raw.py); the SDK declares the kind's two
window settings. **Its settings**: sample data, a developer's
(synthetic.py). No secret: Polymarket US's public market data needs no key,
and this version reads nothing that does (its market WebSocket needs an
account's API key, so it polls instead).
"""

import meridian
from meridian import DatasetDeclaration, DatasetLicence

VENDOR = "Polymarket US"
SAMPLE_DATA = "sample_data"

#: Its settings, in the data role's order (spec/plugin-pages-follow-their-role):
#: no environment and no credential -- Polymarket US's public market data has
#: one environment and needs no key -- so only sample data, a developer's.
SETTINGS = [
    meridian.sample_data(
        description=(
            "Answer from built-in made-up Polymarket US responses, or a developer's recorded "
            "ones, instead of calling Polymarket US. Development deployments only."
        )
    ),
]

CATALOGUE = [
    DatasetDeclaration(
        key="live",
        vendor=VENDOR,
        data_types=["meridian.v1.Price", "meridian.v1.Quote"],
        modes=["pull", "stream"],
        cadence=1,
        history=0,
        licence_default=DatasetLicence(kept=True, retention_days=2),
        day_time_zone="Etc/UTC",
        day_end_minute=0,
    ),
    DatasetDeclaration(
        key="outcomes",
        vendor=VENDOR,
        data_types=["meridian.v1.Outcome"],
        modes=["push"],
        cadence=60,
        history=0,
        licence_default=DatasetLicence(kept=True),
        day_time_zone="Etc/UTC",
        day_end_minute=0,
    ),
]
