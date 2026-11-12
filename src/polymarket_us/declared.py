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

**Its terms and pricing** (contract 30, ruling 1032): no dataset declares a
licence. Each describes Polymarket US's published terms in plain words
(`TERMS`), shown on Data sources and in the plugin's docs: the deployment
admin settles them and sets the deployment's licence on the Data sources
page, which is the one enforced.

**How a gap is recovered** (W10.14): both datasets are `stream_only` --
Polymarket US serves no history of a book, nor of a market's settlement
before it is final, and a want of `outcomes` is not answered. No dataset
names a sessions calendar.

`venue_id` is empty: the venue master's ID for Polymarket US is minted by
the platform, not known to the code a catalogue is declared from, so each
row names the venue by the ID it resolves at run time (the SDK's
`meridian.roles.data.event_contracts.Feed`), by its ISO 10383 MIC, `QCEX`.

**Its storage**: one kind of raw record, Polymarket US's responses as
received, kept a month by default (`KIND`, kept by the SDK's
`meridian.edge.RawStore`); the SDK declares the kind's two window settings.
**Its settings**: sample data, a developer's (synthetic.py). No secret:
Polymarket US's public market data needs no key, and this version reads
nothing that does (its market WebSocket needs an account's API key, so it
polls instead).
"""

import meridian
from meridian import DatasetDeclaration

VENDOR = "Polymarket US"
SAMPLE_DATA = "sample_data"

#: Its one kind of raw record, Polymarket US's responses as received: a month
#: of them by default, enough to re-convert a row a person questions. An admin
#: sets the window in Settings.
KIND = "responses"
LABEL = "Raw responses"
WINDOW_DAYS = 30

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

#: Polymarket US's published terms, in plain words (ruling 1032).
TERMS = (
    "Polymarket US's public market data API (gateway.polymarket.us): free, no key or account; "
    "its documentation states no rate limit and no terms of its own for the data, which falls "
    "under Polymarket US's Terms of Service for its site and services. Its exchange (QCX "
    "LLC, MIC QCEX) is open to eligible persons in the United States."
)

CATALOGUE = [
    DatasetDeclaration(
        key="live",
        vendor=VENDOR,
        data_types=["meridian.v1.Price", "meridian.v1.Quote"],
        modes=["pull", "stream"],
        cadence=1,
        history=0,
        terms_and_pricing=TERMS,
        gap_recovery="stream_only",
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
        terms_and_pricing=TERMS,
        gap_recovery="stream_only",
        day_time_zone="Etc/UTC",
        day_end_minute=0,
    ),
]
