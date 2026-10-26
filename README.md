# plugin-polymarket-us

Polymarket US's public market data for its event contracts, and their
outcomes, in an Open Meridian deployment's lake: a data plugin. Polymarket
US is QCX LLC, a CFTC-designated contract market (ISO 10383 `QCEX`); it is
not the international, on-chain Polymarket, which
[plugin-polymarket](https://github.com/open-meridian/plugin-polymarket)
serves. For each contract a deployment's readers ask about -- each market
one binary event contract -- it records the last trade's price and the best
bid and offer per contract in dollars, the best bid and offer with their
sizes as a quote, and, once Polymarket US publishes its final settlement,
the contract's outcome, every figure exactly as Polymarket US stated it. No
key and no account: Polymarket US's public gateway needs none. It never
trades.

What it does alike with every data plugin of an event-contract venue is the
SDK's (`meridian.roles.data.event_contracts`, open-meridian 0.33.0), never
copied from another plugin: it runs the SDK's data suite and its checks for
an event-contract venue unchanged against its own conversion.

**Status.** 0.5.0, built on open-meridian 0.33.0 (contract v28: its feed delay reported, a crossed quote recorded invalid at the edge, and its published fee schedule on Connection; contract v27, its e2e in full on core's harness, which holds QCEX; contract v26, a range market's bounds on its contract, its work the SDK's role helpers; contract v25's whole declaration and docs/, which a deployment shows on its Documentation tab), holding the
role `data`.

## What it does

Two datasets, declared from code in its catalogue (`declaration.py`):

| Dataset | Data | Modes | Day | Default licence |
|---|---|---|---|---|
| `<instance>:live` | each contract's last trade, best bid and offer as prices; its best bid and offer with sizes as a quote | pull, stream | `Etc/UTC`, ending at 00:00 | kept two days |
| `<instance>:outcomes` | each contract's outcome once Polymarket US settles it | push | `Etc/UTC`, ending at 00:00 | kept |

- **Polled from the public gateway.** It reads `gateway.polymarket.us`
  (docs.polymarket.us, "API Reference"): a market by its slug
  (`/v1/market/slug/{slug}`), its book (`/v1/markets/{slug}/book`) and,
  once settled, its settlement (`/v1/markets/{slug}/settlement`), at most
  five calls a second, a 429 waited out. It does not stream: Polymarket US's
  market WebSocket is on its authenticated API and needs an account's key,
  which this version neither asks for nor holds.
- **Per subject wanted, never the whole venue.** A reader reads a price or
  quote nothing has recorded; the lake asks this plugin (a want). The plugin
  reads the subject's record (W3.6) and names the Polymarket US contract it
  is by its identifiers: the market's slug (`symbol` at `polymarket-us`),
  else another source's symbol that Polymarket US answers as one of its
  markets (never for a record that is a security, or a type other than a
  binary event contract). It asks Polymarket US for that market alone; the
  market list is never read, and no record is minted for a market no reader
  asked about.
- **One market, one instrument, one contract.** A Polymarket US market has
  one instrument: buying it is the YES side, and its NO side is the same
  instrument sold short, with no NO shares of its own ("Market Structure").
  So each market is one binary event contract, its YES side, as Kalshi's
  plugin records a Kalshi market: it pays one dollar if the event happens
  and nothing if not. A market whose `marketSides` are not one long and one
  short side is not served, nor one whose record states another payout.
  Where the record lacks the slug, or its class or type, the slug is
  reported beside the identifier it matched, with `event_contract`,
  `binary_event_contract` and Polymarket US's words (the market's question
  and its YES side) offered, so a person completing the record on the
  Instruments page has them.
- **Money per contract, in dollars.** Polymarket US states every amount as
  `{"value": "0.43", "currency": "USD"}`; a price is that value, what one
  contract costs, never a probability (the implied probability is the price
  over the payout, a reader's computation), named by the dollar's ISO 4217
  code. An amount in another currency is kept as sent and never read as a
  price, and a price outside nothing to the payout is left unrecorded and
  counted.
- **The book read once for both.** The quote is `/book`'s best bid (the
  highest of `bids`) and best offer (the lowest of `offers`), each `px` with
  its `qty`, stated at its `transactTime`; the last trade is the same
  answer's `stats.lastTradePx` at `stats.lastTradeSetTime`. The lighter
  `/bbo` is not read: its `bidShares` and `askShares` are a whole side's
  levels summed and rounded to two significant figures, not the best
  level's size.
- **Outcomes from the settlement price** (contract v23; the lake plan's
  "vL1c"). Once a market's `status` is `MARKET_STATUS_RESOLVED` -- "final
  settlement published; the outcome will not change" -- the plugin asks its
  `/settlement` and records the outcome unasked, from the contract's own
  side: its `settlement` is the settlement price of the market's one
  instrument, what one contract settles at; 1 pays, 0 pays nothing, and a
  price between -- an instrument that "may settle at last fair market
  prices" under its market's rules -- pays part. The stage is final, and
  Polymarket US's word is its settlement price as stated
  (`polymarket-us:settlement`). Polymarket US states no time of its
  determination or payout, so the outcome is valid from when the answer
  stating it arrived, and its payout time is left unset. A market past its
  end whose settlement is not yet published (`MARKET_STATUS_RESOLVING`)
  records nothing, and is read again each minute. One row key per contract
  (`<slug>:outcome`). **No challenge deadline** (contract v27's
  `Outcome.challenge_ends_at_ns`, left 0, which pages show as "deadline not
  reported"): "All resolutions are final" under its rulebook, so
  Polymarket US states no window to challenge one.
- **What is never read as anything else.** The `settlementPx` an open
  market's book states (with a calculation method and a time of its own) is
  a daily settlement price, never its outcome. `/v1/price-history` is
  display prices derived from the book -- the YES side's from the best ask,
  the NO side's from one less the best bid -- as floats, "not individual
  trades": neither a close nor a bar, so no daily bar is recorded.
- **Wants**, each recorded against or declined per subject with why:
  `not_covered` (not one of Polymarket US's binary markets), `beyond_history`
  (a day or range already past: its public reads answer now),
  `source_silent` (Polymarket US states nothing for it). A standing want
  keeps its subjects current, at most once a second, until the lake
  withdraws it.
- **Its licences.** `live` keeps its rows two days by default (the plan's
  Q21 for a live dataset); `outcomes` keeps its rows, since an outcome is
  read back by version. The deployment admin states the deployment's own
  licence on the Data sources page, which replaces the default; the default
  claims nothing about Polymarket US's terms, which are for the deployment
  admin and whoever uses the deployment to settle.
- **The venue** is named by its MIC, `QCEX` (as Kalshi's plugin names
  Kalshi by `KLSH`), and from contract v26 each contract is sent with its
  ticker -- its slug under the `ticker` scheme, `QCEX` in source -- beside
  its symbol, which the platform matches and mints on (ruling 312). Where
  the deployment's venue master does not hold the venue, each row has the
  venue left empty and the code beside it as reported, and the miss is
  reported, asked again the next day.
- **No event groups** (contract v26; meridian-design
  `spec/the-contract-gaps-v26-and-v27-close.md`, W3.29). Polymarket US
  groups its markets into events (`/v1/events/slug/{slug}`, its markets
  nested, its `seriesSlug` its series; docs.polymarket.us, "Events API
  Overview"), but a market's own answer names no event, and no public read
  answers the event of a market: finding it would mean reading the venue's
  whole event list, which the plugin never reads, or parsing the market's
  slug, which Polymarket US says not to do ("Crypto Schema"). Its event
  answer states no flag either: whether an event's markets are mutually
  exclusive is stated only in the authenticated reference data, never on
  the public gateway. So the plugin reports no group. A range market's
  bounds (`assetPriceTerms`: a bucket's `rangeLower` and `rangeUpper`, an
  above/below market's `strike`, each inclusive) are on its contract, kept
  in the contract map. Contract v27 sends a range member's bounds with its
  event group's report (ruling 464), so with no group reported they reach
  no row here either; they are sent once a public read names a market's
  event.

### What it does not serve

The SDK's data suite's cases about a kind of data this plugin never
publishes are marked not presented, with why (`tests/venue_cases.py`): daily
closes and bars (its price history is display prices, not trades), trades,
a currency's rate, a stablecoin's price, a security's price, a settlement
calendar or date (an event contract settles on its outcome), and a restart's
gap of trades. `restates-a-disputed-outcome` (`about: disputed outcomes`) is
not presented either: Polymarket US publishes an outcome only once its
final settlement is published, and states no dispute, so no outcome is
recorded before the final one to be restated. Contract v26's
`reports-an-event-group` and `reports-a-flag-the-venue-does-not-state` are
not presented: it reports no group, as above. Every other case passes:
`records-an-outcome` at the final stage (the case takes determined or
final), `records-a-partial-payout` on a settlement price between nothing
and the payout, and `reads-its-datasets-licences` among them;
`hears-and-reads-an-event-group` is answered by the SDK. Contract v27's
cases an event-contract venue never presents are the SDK's list
(`EVENT_CONTRACTS_NOT_PRESENTED`): the seven rates cases (it publishes no
rates); `records-a-datasets-liveness` (Polymarket US is polled over REST
each second, and no stream gives a heartbeat to record); and
`queries-the-lake-within-bounds`, about trades from v27 (it records none).
Contract v28's are the SDK's list too: the option-chain and filings cases
(it lists no chain and publishes no filing), and
`a-duplicate-is-recorded-suspicious` and `rows-after-a-gap-are-suspicious`
(its quotes are polled; no message is numbered).
`a-crossed-quote-is-recorded-invalid` passes on a synthetic market whose
book is crossed, and `reports-its-feed-delay` (required from contract v28,
ruling 518) on a standing want kept current, its rows' age at the edge.

## Settings

| Setting | What it does |
|---|---|
| Sample data (`sample_data`) | A developer's setting, shown only on a development deployment: answer from the synthetic exchanges this plugin carries instead of calling Polymarket US, or from a developer's recorded exchanges where its storage holds them (`recorded/`). |
| Raw responses' window (`responses_window_days`, `responses_past_window`) | The SDK's, for the plugin's one kind of raw record: how long Polymarket US's answers stay in its storage (30 days by default), and whether a day past it is archived, kept or deleted. |

No secret: Polymarket US's public market data needs no key.

## Its pages, under Manage

The data role's two pages (meridian-design
`spec/plugin-pages-follow-their-role.md`), the same sections, rows, labels
and "not set up yet" states as every data plugin's, drawn by the SDK's
templates for an event-contract venue
(`meridian/roles/data/event_contracts/`); Polymarket US's names and words
only where they ask for them. A data plugin shows no market data: viewing prices is for
the reading roles.

- **Connection**: "Key" -- the mode (Live, or Sample data), "No key needed",
  what Polymarket US entitles it to (public data: a contract read only for a
  subject the lake asked for) and, the role's row for a source of one venue,
  the venue master's ID it resolved; "Limits and use" -- what Polymarket US
  allows and what the plugin spends of it, its calls and the rate-limited
  ones waited out, the last call and the last error, and, from 0.5.0,
  "Fees": Polymarket US's published taker fee rate by market category --
  0.0695, and 0.10 for Table Tennis, makers rebated by tier, combos on
  their own curve -- read from docs.polymarket.us/fees on 2026-10-26
  (effective 2026-10-19), for the options sample's fee schedule to take;
  each market states its own `category` and `feeCoefficient`, which
  applies to it (`fees.py`); "Stream" -- "Does not
  stream": it reads a contract when it is wanted, at most once a second.
- **Datasets**: "Served" -- each dataset, its data, how its rows arrive,
  its day, its default terms and whether a deployment admin has licensed it,
  what it recorded and declined and when it last recorded; "Wants" -- the
  wants it heard and the standing wants it keeps current, searched and paged
  by the kit's `om-pager`; "Subjects" -- whether the deployment lets it read
  an instrument's record; then a section under Polymarket US's name: the
  contracts mapped for the subjects the lake asked for and those not served
  with why, the cash its prices and payouts are in (the US dollar) and what
  each contract pays, and that each market is one instrument, its YES side,
  paying one dollar. Before the lake has asked anything it says the next
  step: "No wants yet", a deployment admin licensing its datasets on Data
  sources.

Its Summary carries the data role's figures, in the role's order:
Connection, Entitled at the vendor, Stream ("Does not stream") and Last
recorded. Both pages fit one screen at 1440x900 and 390x844, rows one line
each.

### Offered to agents

Each page is a read tool on the deployment's MCP surface, answering the record
the page shows: `read_connection` and `read_datasets`, at the plugin's admin
level. The plugin has no route that changes anything.

## Raw responses

Every answer Polymarket US sends, an error as much as a book, is kept in
the storage the deployment grants the plugin before anything is read from
it, with the request that asked for it, its status and headers, and when it
arrived (`meridian.edge.RawStore`); a live answer is a line of its day's file, added only
when it changed, and a row read from an unchanged answer names the line and
time it first arrived. Each row names its raw record (`RawRecordRef`); an
outcome names its settlement answer. Kept in units of a UTC day under
`responses/`, moved past the window through the SDK.

## Proven on core's harness

    make e2e

runs the plugin with sample data on core's plugin harness beside the e2e's
reader (`e2e/reader.py`, holding `custody` to name a custodian's records,
`reporting` to read prices and `signal` to read quotes): the catalogue
listed, nothing asked of Polymarket US before a want, a custodian's
contract read and named, its prices and quote recorded in dollars, read and
heard, no event group reported, a market of three sides declined, a settled market's outcome
recorded unasked, final, and read back, both read tools answering what the
pages show, and `store lake` numbering each row with no holes (`e2e/run.py`
says each step). The custodian states the contract's ticker under `QCEX`
beside its own symbol (ruling 199), and core v27's stand-in platform
(a5da59a), whose venue master holds Polymarket US by its MIC, mints its
record by it, paying one dollar; each row names the venue by its `VEN-`
ID, with no miss.

    docker run --rm --entrypoint python -v "$PWD/e2e":/e2e:ro \
        -v "$PWD/recordings":/recordings polymarket-us:local /e2e/record.py SLUG ...
    make e2e-recorded RECORDED=recordings/<directory>

records Polymarket US's real answers to its public reads for the markets
named, with the plugin's own client and no key, into the git-ignored
`recordings/`, then runs the same replaying them, holding each row to its
shape rather than to the synthetic values.

## Working on it

    make ci-local        # every gate: lint, tests, plugin check, the image, e2e
    make test            # the tests, the SDK's data suite among them
    make preview         # preview/: each page on synthetic data, linking the kit
    make install-hooks   # a push to main runs ci-local first; a branch push runs nothing (CI-first)

`AGENTS.md` is for any coding agent working on it; `CLAUDE.md` leads Claude
Code there. The documentation for a deployment admin is in `docs/`.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`. Polymarket is a trademark of its
owner; this project is not affiliated with or endorsed by Polymarket,
Polymarket US or QCX LLC.
