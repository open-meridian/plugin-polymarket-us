# Changelog

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
