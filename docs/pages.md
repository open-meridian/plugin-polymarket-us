# Pages

The data role's two pages, under **Manage**, for the plugin's admin, laid
out as every data plugin's are: the same sections, rows and words in the
same order. Neither shows a price, a side of the book or a size.

## Connection

- **Key**: the mode (Live, or Sample data on a development deployment),
  "No key needed" -- Polymarket US's market data is public -- what
  Polymarket US entitles it to (a contract read only for an instrument the
  lake asked about), and the venue's ID in the platform's venue master, or
  that your deployment does not hold it.
- **Limits and use**: what Polymarket US allows and what the plugin spends
  of it, how many calls it made and how many met a rate limit and waited it
  out, the last call and the last error; and **Fees**: Polymarket US's
  published taker fee rate by market category, the formula it enters and
  what makers get back, with where it was read and on which day (tap the
  row for the whole). Each market states its own category and rate, which
  applies to it.
- **Stream**: "Does not stream": it reads a contract when it is wanted.

## Datasets

- **Served**: each dataset, `live` and `outcomes`, with its data, how rows
  arrive, its day and default terms, whether a deployment admin has
  licensed it ("Licensed" or "Not licensed yet"), what it recorded and
  declined, and when it last recorded.
- **Wants**: the wants the lake sent it, those it keeps current first, each
  with how many rows it recorded and subjects it declined; the search above
  them narrows them as you type, and the pager pages them.
- **Subjects**: whether your deployment lets it read an instrument's record.
- **Polymarket US**: how many contracts are mapped for the instruments the
  lake asked about, and how many it did not serve and why; the cash its
  prices and payouts are in (the US dollar), your deployment's record for
  it, and what each contract pays; and that each market is one instrument,
  its YES side, paying one dollar if the event happens.

Before anything has been asked of it, Datasets says the next step: "No
wants yet", until a deployment admin licenses its datasets and entitles a
plugin on **Data sources**.

## Tools for agents

Each page is a read tool answering what the page shows, the data role's
fields under the same names as every data plugin's: `read_connection` and
`read_datasets`, for a person holding admin on the plugin.
