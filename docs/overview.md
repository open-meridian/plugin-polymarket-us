# Overview

The Polymarket US plugin puts Polymarket US's public market data for its
event contracts, and each contract's outcome once it settles, into your
deployment's lake, where the plugins that watch and value your book read it.
Polymarket US is QCX LLC, a CFTC-designated exchange: it is not the
international Polymarket, and this plugin reads nothing of that venue. It
needs no key and no account: Polymarket US's public market data is open.

It is a data plugin: its first-use path, its two pages and its Summary figures are every data plugin's, described once on [Using a data plugin](https://open-meridian.dev/how-to/using-a-data-plugin/). These sections cover what is Polymarket US's own.

## Its role

It holds one role, `data`: it records prices, quotes and outcomes into the
lake, with Polymarket US's contracts named as your deployment's instruments,
and keeps Polymarket US's answers in its own storage. It shows no prices
itself: reading them is for the reporting, portfolio, signal and other
reading plugins. It never trades.

## What it records

- **Prices and quotes** (`<instance>:live`): for each contract a reader asks
  about, now, the last trade's price and the best bid and offer, per
  contract in dollars, and the best bid and offer with their sizes as a
  quote, at most once a second for each contract while a reader keeps
  asking. It polls Polymarket US's public gateway; it does not stream, since
  Polymarket US's market stream needs an account's key.
- **Outcomes** (`<instance>:outcomes`): once Polymarket US publishes a
  contract's final settlement, its outcome -- it pays its full dollar, pays
  nothing, or pays part -- with what one contract settles at and Polymarket
  US's settlement price kept as reported. It is recorded unasked for each
  contract a reader asked about.

It records what readers ask for, not the whole exchange: when a reader asks
for a price nothing has recorded, the lake asks the plugin, which asks
Polymarket US for that one market and its book and records it, or says why
it cannot.

## One market, one instrument

A Polymarket US market ("Will the Chiefs win?") has one instrument: buying
it is the YES side, and the NO side is the same instrument sold short. So
each market is one binary event contract in your deployment, known by its
slug, paying one dollar if the event happens and nothing if not, with its
own prices and its own outcome. A market that is not one instrument's long
and short side is not served.

## How it names what it prices

Each instrument a reader asks about is one of your deployment's records. The
plugin reads it and looks for the market's slug on it (as Polymarket US's
own symbol, source `polymarket-us`), or another source's symbol that is a
Polymarket US slug.

Where the record lacks the slug, its class or its type, the plugin offers
them, with Polymarket US's words for it (the market's question and its YES
side), so you can complete the record on the Instruments page. If the record
already states a payout that is not one US dollar, the plugin does not serve
it.

## Prices are money, not probabilities

A price is what one contract costs: 0.43 means 0.43 dollars for a contract
that pays one dollar. The market's implied probability (43%) is that price
over the payout, which a reading plugin may compute; the lake stores only
the price.

## Outcomes are final

Polymarket US publishes a market's settlement only once it is final ("the
outcome will not change"), so each outcome is recorded once, final. A market
past its end whose settlement is not yet published records nothing, and the
plugin asks again each minute. Polymarket US states no time of its
determination or payout, so an outcome is valid from when the answer stating
it arrived. Paying holders is not the lake's: until the book's servicing
records payouts, a custodian's payout shows as a break.

## Events

Polymarket US groups its markets into events (a game, an election), but it
does not say, on a market, which event the market belongs to. So the plugin
reports no event groups: your deployment holds no group for a Polymarket US
contract, and each contract is priced on its own. Polymarket US's public
data does not state whether an event's markets exclude one another either.

## What it never makes up

- A figure is recorded exactly as Polymarket US stated it, never rounded and
  never through a float.
- A side of the book with no order is left empty, never zero.
- Nothing is recorded for a day already past: Polymarket US's public reads
  answer now.
- The daily settlement price Polymarket US states on an open market is never
  taken for its outcome, and its price history -- display prices derived
  from the book, not trades -- is never taken for a close or a bar.

## What it keeps

Polymarket US's answers, as received, in the storage your deployment gives
the plugin, for 30 days by default, each row naming the answer it came from.
Past that window, a day's answers are archived, kept or deleted as you set
it. Its live dataset's default licence keeps its rows two days; its outcomes
dataset's keeps them.
