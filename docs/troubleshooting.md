# Troubleshooting

## Polymarket US is not answering

The Connection page's status says so, with the last error. The plugin waits
out a rate limit and tries again. Check the deployment can reach
gateway.polymarket.us.

## Venue master: not held

Your deployment does not hold Polymarket US in the platform's venue master
by its ISO 10383 MIC, `QCEX`. Each row is recorded with its venue left empty
and Polymarket US named as reported, and the plugin asks again the next day.

## A subject not served

The Datasets page says why for each:

- **Its record names none of the venue's binary event contracts**: the
  record carries no Polymarket US market slug (nor another source's symbol
  that is one), or the market is not one instrument's long and short side.
  Add the slug as a `symbol` with source `polymarket-us` on the Instruments
  page.
- **Its record states another payout**: the record's payout is not one US
  dollar. Correct it on the Instruments page if it is Polymarket US's
  contract.
- **Its record could not be read**: the deployment does not let the plugin
  read an instrument's record (a runtime before contract v18's ruling of
  2026-10-10).

## Not resolved: USD

Two of your deployment's records carry the US dollar's ISO 4217 code. Merge
them on the Instruments page; nothing is priced until it resolves to one
record.

## No outcome yet

A market past its end records no outcome until Polymarket US publishes its
final settlement (its status reads resolved and its settlement price is
answered). The plugin asks again each minute until it does.
