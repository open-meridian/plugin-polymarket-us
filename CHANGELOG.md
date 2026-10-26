# Changelog

## 0.6.0

On open-meridian 0.33.1, contract v28 (rulings 624 to 626), on core v28's
harness.

- **No bars, and why** (624): open-meridian 0.33.1 lets an event-contract
  venue keep hourly and daily bars (`Market.bars`, `Feed.keep_bars`);
  Polymarket's and Kalshi's plugins do from 0.11.0. This one keeps none and
  declares no `bars` dataset: Polymarket US's public price history is
  "book-derived Yes and No display prices", which "are not individual
  trades" (docs.polymarket.us, "Get Price History", read 2026-10-26), and
  its public trades are only on its WebSocket, which this REST-polled
  plugin does not hold. The README says so; `a-daily-bar` stays not
  presented.
- **The feed delay** (626): the SDK's producer now stands its want on the
  quote where the last trade states no time; this plugin's last trade
  states one, so its case passes as before, on the SDK's producer.
- **The pins**: open-meridian 0.33.1 and plugin-python:0.33.1 by tag and
  digest (`sha256:75ec238c...d5f46bac`); core's runtime and harness stay at
  `8def82a` (chart 0.1.313); `meridian` stays 0.1.52 in check.yaml.

## 0.5.0

On open-meridian 0.33.0, contract v28 (meridian-design `plans/the-v28-build.md`;
task `sdk-contract/venue-plugins-keep-outcome-stages-and-bars`), on core
v28's harness.

- **Fees by market category** (571's category column; task
  `sdk-contract/event-contract-fees-vary-by-market-category`): Connection's
  "Limits and use" gains a "Fees" row, and `read_connection` a `fees`
  record -- Polymarket US's published taker fee rate by market category
  (0.0695; Table Tennis 0.10; combos their own curve), what makers get back,
  the formula, and its source and the day it was read (docs.polymarket.us,
  "Fee Schedule", read 2026-10-26, effective 2026-10-19), for the options
  sample's fee schedule to take (`fees.py`). Each market states its own
  `category` and `feeCoefficient`, which applies to it.
- **Outcomes stay final.** Polymarket US publishes no proposed, determined
  or disputed stage ("All resolutions are final"), so an outcome is still
  recorded once, final, and `challenge_ends_at_ns` stays 0.
- **The suite's v28 cases**: `reports-its-feed-delay` is presented (518: the
  latency cases are required again), a standing want kept current, its
  rows' age at the edge; `a-crossed-quote-is-recorded-invalid` on a
  synthetic market whose book is crossed (`CROSSED`); the option-chain,
  filings, duplicate and gap cases not presented, the SDK's list
  (`EVENT_CONTRACTS_NOT_PRESENTED`, ruling 602).
- **`meridian plugin migrate`** (to_0_33_0): e2e/reader.py's SubjectRefs
  handed to the SDK are `meridian.SubjectRef` (ruling 599).
- **The pins**: open-meridian 0.33.0 and plugin-python:0.33.0 by tag and
  digest (`sha256:c95f1a03...c0fe39c6`); core v28's runtime and harness at
  `8def82a` (chart 0.1.313) by digest; `meridian` stays 0.1.52 in
  check.yaml until 0.1.53 is released.
- The README's "not released" line is gone.

## 0.4.0

On open-meridian 0.32.2, contract v27 (meridian-design `plans/the-v27-build.md`,
§B and §G), on core v27's harness.

- **The e2e in full.** Core v27's stand-in platform (a5da59a) holds
  Polymarket US in its venue master by its MIC, QCEX, so the custodian's
  records are minted by their ticker under QCEX, paying one dollar:
  `HARNESS_HOLDS_NO_QCEX` and the harness-limited path are gone, and every
  step runs -- prices, the quote, no event group, the decline, the outcome,
  both read tools and the lake's record. Each row now names the venue by
  its `VEN-` ID, with no miss.
- **No challenge deadline.** Contract v27's `Outcome.challenge_ends_at_ns`
  stays 0 ("deadline not reported"): every Polymarket US resolution is
  final, so it states no window. Said in the README, AGENTS.md and
  docs/overview.md.
- **The suite's v27 cases** are named not presented through the SDK's
  `EVENT_CONTRACTS_NOT_PRESENTED`: the seven rates cases;
  `records-a-datasets-liveness` (Polymarket US is polled each second, and no
  stream gives a heartbeat); `queries-the-lake-within-bounds`, about trades
  from v27 (it records none); and `reports-its-feed-delay`, about latency,
  with ruling 518's reason (core receives ReportLatency from contract v28,
  ruling 515).
- **No events loop.** It reports no event group, so it runs no
  `Feed.keep_events`, and a range market's bounds, sent with a group's
  report from contract v27 (ruling 464), reach no row here yet.
- **The pins**: open-meridian 0.32.2 and plugin-python:0.32.2 by tag and
  digest (`sha256:2235d96d...54020b80`); core v27's runtime and harness at
  `a5da59a` (chart 0.1.310) by digest; `meridian` 0.1.52 in check.yaml.
  e2e-latest.yaml keeps the harness's hidden logs (`include-hidden-files`).
- Its `DatasetLicence` sets none of 0.32.2's five new fields: core v27
  refuses a registration carrying them until a core that accepts them is
  published. The terms page is unchanged.

## 0.3.1

On open-meridian 0.31.1: a range market's bounds on its contract (the gaps
spec's A4).

- **Bounds on the contract.** `convert.contract` sets `Contract.floor` and
  `.cap` from the market's `assetPriceTerms` -- a range bucket's
  `rangeLower` and `rangeUpper`, each inclusive, a tail's open side none;
  an above/below market's `strike`, an inclusive floor -- which 0.3.0 read
  but held off it: 0.31.1's contract map keeps a bound and reads it back.
  `bound_unit` stays empty (a bound here is a price, whose unit is an
  instrument's ID). A bound reaches no row in contract v26; its data path
  is contract v27's (ruling 464).
- **The SDK's check restored.** 0.31.1's
  `test_a_record_already_complete_is_not_resolved_again` holds ruling 312's
  ticker itself, so this plugin's override is gone.
- **The pins**: open-meridian 0.31.1 and plugin-python:0.31.1 by tag and
  digest (`sha256:67781f14...a3535b39`); core v26's runtime and harness and
  `meridian` 0.1.49 as 0.3.0 set them.

## 0.3.0

On open-meridian 0.31.0, contract v26: the data role's work is the SDK's
(sdk-contract/the-sdk-carries-each-roles-common-logic; ruling 234: the v26
plan's "Polymarket US adopts event_contracts"), on core v26's harness. One
version for v26: it carries 0.2.0 (contract v25: the whole declaration and
docs/), which never merged on its own.

- **The data role from the SDK's helpers.** `market.py`, `dgm.py`,
  `contracts.py` and `raw.py` are gone: the work is
  `meridian.roles.data.event_contracts.Feed` (prices, quotes and outcomes)
  over this venue's values (`convert.PolymarketUsMarket`) and
  `ContractMap`, raw records `meridian.edge.RawStore`, and the pages the
  SDK's for an event-contract venue (`page.py` builds them; `templates/`
  gone), answering the kind's `ConnectionRead` and `DatasetsRead`. What it
  records is unchanged: one market one binary contract, its YES side,
  prices in dollars from `{"value", "currency"}`, the book read once for
  the quote and the last trade, outcomes from `/settlement` once a market is
  `MARKET_STATUS_RESOLVED`, final. From open-meridian 0.31.0 each contract
  is sent with its ticker (its slug under `QCEX`) beside its symbol (ruling
  312). `e2e/reader.py` stays as this plugin's own e2e stand-in.
- **suite-same retired.** The tests copied from plugin-kalshi
  (`test_suite`, `test_dgm`, `test_page`, `test_raw`, `conftest`) are one
  class, `tests/test_data_role.py`, running the SDK's `EventContractsChecks`
  against this plugin's conversion and the data suite by name; raw records
  are tested in the SDK. The SDK check
  `test_a_record_already_complete_is_not_resolved_again` is held to ruling
  312's ticker until open-meridian 0.31.1 corrects its own.
- **Event groups are not reported.** Polymarket US groups its markets into
  events (`/v1/events/slug/{slug}`), but a market's answer names no event
  and no public read answers a market's event; the plugin never reads the
  venue's event list, and Polymarket US says not to parse a slug. Its event
  answer states no flag either. So the data suite's `reports-an-event-group`
  and `reports-a-flag-the-venue-does-not-state` are not presented, with why.
- **A range market's bounds** (A4) are read in `convert.py` from its
  `assetPriceTerms` (a bucket's `rangeLower` and `rangeUpper`, each
  inclusive, a tail's open side none; an above/below market's `strike`, a
  floor inclusive), but not yet set on the contract: open-meridian 0.31.0's
  contract map cannot keep a bound and sends none.
- **e2e on core v26's harness**: the custodian states the contract's ticker
  under `QCEX` beside its own symbol (ruling 199), and step 5a reads no
  event group by the contract. The stand-in platform (core 17a13a2,
  `deploy/harness/platform.py`) holds no `QCEX` in its venue master, so it
  mints no Polymarket US contract and the custodian's records stay
  provisional, which the lake does not price: the run proves what that
  harness can (the datasets, nothing asked before a want, the records
  provisional, a price read unanswered, no row) and its later steps wait
  behind `HARNESS_HOLDS_NO_QCEX` for the stand-in to hold Polymarket US.
  On a failure it logs the instruments, the plugin's Datasets record and
  the lake's record, and e2e.yaml keeps the hidden `.e2e/` logs.
- **The pins**: open-meridian 0.31.0 and plugin-python:0.31.0 by tag and
  digest (`sha256:e041f83c...24cf5d2`), which `make image` builds on as an
  upload does; core v26's runtime and harness (17a13a2, merged as 648e25f)
  by digest; `meridian` 0.1.49, the first CLI carrying contract v26's
  suites.

Earlier versions are described in the git history.
