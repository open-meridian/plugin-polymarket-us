"""`make e2e` and `make e2e-recorded`: the plugin end to end on core's plugin
harness (contracts v19, v20 and v23), with sample data, beside a reader
(e2e/reader.py).

1. Launched: the plugin registers its catalogue; the deployment admin's tool
   lists its two datasets: `live`, of prices and quotes, on the UTC day
   ending at 00:00, pulled or streamed, its default licence kept two days;
   and `outcomes`, pushed, kept by default.
2. Sample data on: nothing is asked of Polymarket US and no record minted
   until the lake wants something -- never the venue's list. The reader then
   names a market as a custodian's book holds it, by the custodian's own
   symbol, a market of three sides the same way, a market Polymarket US has
   settled, and the dollar by ISO 4217.
3. Licensed and entitled: the admin sets each dataset's licence as its
   default says -- `live` kept two days, `outcomes` kept -- and entitles the
   reader to both.
4. Prices wanted and recorded: the reader follows the market and reads its
   latest; the lake asks the plugin, which reads the record (W3.6), names it
   Polymarket US's contract by the custodian's symbol, joins its slug to it
   with the class, type and Polymarket US's words offered, resolves the
   dollar, and records its last trade, best bid and offer per contract in
   dollars, exactly as stated; the reader reads and hears them, each naming
   its raw record and the venue as reported.
5. Quotes wanted and recorded: the reader reads its latest quote; the
   plugin records its best bid and offer with their sizes, read and heard.
6. Declined: the market of three sides is declined as not covered.
6a. An outcome (contract v23): the reader asks for the settled market's
   price; the plugin names it and records its outcome, unasked, in
   `outcomes` -- from the contract's side, it pays its full payout, final,
   settling at one dollar, Polymarket US's word (its settlement price, 1)
   kept as reported, valid from when the answer stating it arrived, no
   payout time, no business date -- which the reader hears and reads back
   as version 1.
7. Parity: the plugin's two read tools answer through the deployment's MCP
   what its two pages show: two contracts mapped, each paying one dollar,
   the dollar's record.
8. Its raw responses are in its granted storage, and `store lake` prints
   each row of the live dataset kept, numbered with no holes, the wants
   asked, answered, declined and withdrawn, the venue's miss, and the
   outcome's one row kept.

`make e2e-recorded` (`--recorded=DIR`) runs the same on a developer's
recording of Polymarket US's real answers (e2e/record.py), naming the first
binary market it holds, and holds each row to its shape rather than to the
synthetic exchange's values.

Run from the repository's root by the Makefile, which builds the image,
copies the harness out and writes the plugins' compose file first, and
exports what the compose files read. Standard library only.
"""

import json
import pathlib
import subprocess
import sys
import time
import urllib.parse
from decimal import Decimal

VENUE = "polymarket-us"
NAME = "Polymarket US"
DATASET = f"{VENUE}:live"
OUTCOMES = f"{VENUE}:outcomes"
LOG = ".e2e/runner.log"
RECORDED = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--recorded=")]
EXACT = not RECORDED
COMPOSE = ["docker", "compose", "-p", f"{VENUE}-e2e", "-f", ".e2e/harness/compose.yaml",
           "-f", ".e2e/harness/plugins.yaml", "-f", "e2e/plugin.yaml",
           *[a for a in sys.argv[1:] if not a.startswith("--recorded=")]]
#: The synthetic exchange's market, what its book states, and a market of
#: three sides, which is not binary.
CONTRACT = "syn-nfl-aar-bob-2026-12-06"
NOT_BINARY = "syn-mlb-ws-2026-three-sides"
#: A market Polymarket US has settled, its long side the winner (contract
#: v23), and its outcome.
RESOLVED = "syn-nfl-cra-dev-2026-10-04"
OUTCOME = {"determination": "OUTCOME_DETERMINATION_PAYS", "stage": "OUTCOME_STAGE_FINAL",
           "amount": "1", "as_reported": "polymarket-us:settlement=1", "settled_at_ns": 0,
           "source_times": 0}
STATED = {"PRICE_KIND_LAST": "0.4400", "PRICE_KIND_BID": "0.4300", "PRICE_KIND_ASK": "0.4500"}
QUOTE = {"bid_amount": "0.4300", "bid_quantity": "550.5000", "ask_amount": "0.4500",
         "ask_quantity": "125.2500"}


class Failed(Exception):
    pass


def log(text):
    with open(LOG, "a", encoding="utf-8") as kept:
        kept.write(text + "\n")


def compose(*args, check=True):
    done = subprocess.run(COMPOSE + list(args), capture_output=True, text=True, timeout=600)
    log(f"$ compose {' '.join(args)[:300]}\n{done.stdout[-4000:]}{done.stderr[-2000:]}")
    if check and done.returncode != 0:
        raise Failed(f"compose {' '.join(args)[:200]}: {(done.stdout + done.stderr).strip()[-600:]}")
    return done


def runner(*args, check=True):
    done = compose("run", "--rm", "-T", "runner", *args, check=check)
    return done.stdout if check else done


def must(condition, why):
    if not condition:
        raise Failed(why)


def until(seconds, attempt, what):
    deadline = time.monotonic() + seconds
    last = None
    while True:
        try:
            answer = attempt()
        except Failed as failed:
            answer, last = None, failed
        if answer:
            return answer
        if time.monotonic() > deadline:
            raise Failed(f"{what}, in {seconds} seconds" + (f": {last}" if last else ""))
        time.sleep(2)


def page(instance, level, path):
    said = runner("page", "--instance", instance, "--level", level, path)
    status, _, body = said.partition("\n")
    must(status.strip() == "200", f"{instance} {path} answered {said[-600:]}")
    return body


def read(path):
    return json.loads(page("reader", "read", path))


def call(tool, arguments, *outcomes):
    done = runner("mcp", "call", tool, json.dumps(arguments), check=False)
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        raise Failed(f"{tool}: no answer: {(done.stdout + done.stderr)[-400:]}") from None
    must(answer.get("outcome") in outcomes,
         f"{tool} answered {answer.get('outcome')}, not {outcomes}: {done.stdout[-700:]}")
    return answer


def recorded_contract(directory):
    """The first binary market a recording holds, by its slug."""
    for path in sorted(pathlib.Path(directory).rglob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("call") == "market" and record.get("status") == 200:
            market = json.loads(record["body"]).get("market", {})
            sides = [s.get("long") for s in market.get("marketSides") or []]
            if sorted(sides, key=str) == [False, True]:
                return market["slug"]
    raise Failed(f"no binary market is recorded under {directory}")


def run():
    started = time.time()
    contract = recorded_contract(RECORDED[0]) if RECORDED else CONTRACT
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    compose("up", "-d")
    for instance in (VENUE, "reader"):
        runner("ready", "--instance", instance)
    runner("grant", "--instance", "reader", "--level", "read", "--role", "reporting")
    runner("grant", "--instance", VENUE, "--level", "admin")
    runner("mcp", "connect", "--covers", "deployment_admin", "--covers", f"{VENUE}:admin")
    tools = runner("mcp", "list").split()
    named = {t.rsplit("__", 1)[-1]: t for t in tools}
    for name in ("dashboard__list_datasets", "read_connection", "read_datasets"):
        must(name.rsplit("__", 1)[-1] in named, f"step 1, {name} is listed: {tools}")

    # 1. The catalogue, as the deployment admin's tool lists it.
    def datasets():
        held = {d["dataset"]: d for d in
                call("dashboard__list_datasets", {}, "read", "unchanged")["data"]["datasets"]}
        return held if DATASET in held else None
    held = until(90, datasets, "step 1, the dataset was not listed")
    must(OUTCOMES in held, f"step 1, the outcomes dataset is listed: {sorted(held)}")
    entry, licence = held[OUTCOMES]["catalogue_entry"], held[OUTCOMES]["licence"]
    must(entry["modes"] == ["push"] and licence["kept"] is True
         and licence["set_by_the_deployment"] is False,
         f"step 1, outcomes pushed and kept by default: {entry}, {licence}")
    entry, licence = held[DATASET]["catalogue_entry"], held[DATASET]["licence"]
    must(entry["modes"] == ["pull", "stream"] and entry["day_time_zone"] == "Etc/UTC"
         and entry.get("day_end_minute", 0) == 0, f"step 1, its entry: {entry}")
    must(licence["kept"] is True and licence["retention_days"] == 2
         and licence["set_by_the_deployment"] is False,
         f"step 1, its default licence kept two days: {licence}")

    # 2. Sample data: nothing asked, nothing minted; then the reader's
    # records, as a custodian's book holds them.
    runner("settings", "--instance", VENUE, "sample_data=true")
    served = until(90, lambda: call(named["read_datasets"], {}, "read", "unchanged")["data"],
                   "step 2, read_datasets did not answer")
    connection = call(named["read_connection"], {}, "read", "unchanged")["data"]
    must(served["contracts_read"] == 0 and connection["calls"] == 0,
         f"step 2, nothing read of the venue before a want: {served}, {connection}")
    listed = runner("instruments")
    log("instruments, before any want:\n" + listed)
    must(f"({VENUE})" not in listed and "syn-" not in listed,
         f"step 2, no record minted before a want: {listed}")
    for name, scheme, value, source in (("contract", "symbol", contract, "e2e-custodian"),
                                        ("range", "symbol", NOT_BINARY, "e2e-custodian"),
                                        ("resolved", "symbol", RESOLVED, "e2e-custodian"),
                                        ("usd", "iso4217", "USD", "")):
        query = urllib.parse.urlencode({"name": name, "scheme": scheme, "value": value,
                                        "source": source})
        ids = read(f"/resolve?{query}")
    subject, ranged, resolved, usd = ids["contract"], ids["range"], ids["resolved"], ids["usd"]

    # 3. Licensed as the default says, and entitled.
    runner("licence", DATASET, "kept=true", "retention_days=2", "display=true",
           "personal_use=false", "note=Kept two days, for the e2e's reader.")
    runner("entitle", "--instance", "reader", DATASET, "note=The e2e's reader.")
    runner("licence", OUTCOMES, "kept=true", "retention_days=0", "display=true",
           "personal_use=false", "note=Kept, as the default says, for the e2e's reader.")
    runner("entitle", "--instance", "reader", OUTCOMES, "note=The e2e's reader.")

    # 4. Prices wanted, recorded, read and heard.
    read(f"/follow?subject={subject}&subject={resolved}")
    first = read(f"/prices?subject={subject}&dataset={DATASET}")
    # The lake asks the plugin at once: unanswered as asked or, where the
    # plugin's answer is already in, the rows it recorded.
    must(first["unanswered"] or first["prices"],
         f"step 4, a price not recorded is asked of the plugin: {first}")

    def heard(row, kinds):
        rows = [h for h in read("/heard")["heard"]
                if h["row"] == row and h["dataset"] == DATASET and h["subject"] == subject]
        return rows if {h.get("kind", "") for h in rows} >= kinds else None
    prices = until(90, lambda: heard("price", set(STATED) if EXACT else set()),
                   "step 4, the prices were not heard")
    kept = until(60, lambda: read(f"/prices?subject={subject}&dataset={DATASET}")["prices"],
                 "step 4, the prices kept were not read")
    must({r["kind"] for r in kept} <= set(STATED), f"step 4, the latest read: {kept}")
    for row in prices + kept:
        amount = Decimal(row["amount"])
        must((row["amount"] == STATED[row["kind"]] or not EXACT) and 0 <= amount <= 1,
             f"step 4, {row['kind']} per contract as Polymarket US stated it: {row}")
        must(row["instrument_id"] == usd or (row["currency_code"] == "USD"
                                             and row["instrument_id"] in ("", usd)),
             f"step 4, in dollars, the dollar's record: {row}")
        must(row["venue_id"] == "" and row["unconverted"] == [f"{VENUE}:venue"]
             and row["raw"].startswith("responses/") and not row["business_date"],
             f"step 4, the venue not held named as reported, its raw record: {row}")
    listed = runner("instruments")
    log("instruments, after the want:\n" + listed)
    joined = [line for line in listed.splitlines() if line.startswith(subject)]
    must(joined and f"symbol ({VENUE}): {contract}" in joined[0],
         f"step 4, Polymarket US's slug joined to the custodian's record: {listed}")

    # 5. Quotes wanted, recorded, heard.
    read(f"/quotes?subject={subject}&dataset={DATASET}")
    quotes = until(90, lambda: heard("quote", {""}), "step 5, the quote was not heard")
    quote = quotes[-1]
    must("bid_amount" in quote or "ask_amount" in quote, f"step 5, a side quoted: {quote}")
    for field, stated in QUOTE.items():
        must(not EXACT or quote.get(field) == stated,
             f"step 5, the quote's {field} as stated: {quote}")
    if not EXACT and "ask_amount" in quote and "bid_amount" in quote:
        must(Decimal(quote["bid_amount"]) <= Decimal(quote["ask_amount"]),
             f"step 5, the offer above the bid: {quote}")

    # 6. Declined: a market of three sides is not binary.
    read(f"/prices?subject={ranged}&dataset={DATASET}")

    # 6a. An outcome: the settled market named, its outcome recorded unasked,
    # heard and read back.
    if EXACT:
        read(f"/prices?subject={resolved}&dataset={DATASET}")

        def outcome_heard():
            rows = [h for h in read("/heard")["heard"]
                    if h["row"] == "outcome" and h["subject"] == resolved]
            return rows or None
        [row] = until(90, outcome_heard, "step 6a, the outcome was not heard")
        listed = read(f"/outcomes?subject={resolved}")["outcomes"]
        must(len(listed) == 1, f"step 6a, one outcome in force: {listed}")
        for said in (row, listed[0]):
            must(all(said[k] == v for k, v in OUTCOME.items())
                 and (said["currency_code"] == "USD" or said["instrument_id"] == usd),
                 f"step 6a, the outcome from the contract's side, its word kept: {said}")
            must(said["dataset"] == OUTCOMES and said["row_key"] == f"{RESOLVED}:outcome"
                 and said["version"] == 1 and not said["business_date"]
                 and said["raw"].startswith("responses/"),
                 f"step 6a, one row key per contract, version 1, its raw record: {said}")

    # 7. Parity: each read tool answers what its page shows.
    connection = call(named["read_connection"], {}, "read", "unchanged")["data"]
    must(connection["mode"] == "Sample data" and connection["venue"] == NAME
         and connection["credentials"] == [] and connection["sessions"] is None
         and connection["venue_held"] is False and connection["calls"] > 0,
         f"step 7, read_connection: {connection}")
    shown = page(VENUE, "admin", "/")
    must("Sample data: the plugin answers from recorded responses" in shown
         and "No key needed" in shown and "Does not stream" in shown and NAME in shown,
         "step 7, the Connection page shows the same")
    served = call(named["read_datasets"], {}, "read", "unchanged")["data"]
    mapped = 2 if EXACT else 1
    must([d["dataset"] for d in served["served"]] == [DATASET, OUTCOMES]
         and served["contracts_mapped"] == mapped and served["subjects_named"] == mapped
         and served["cash"] == "USD" and served["cash_instrument"] == usd
         and served["payouts"] == ["1.00 USD"] and served["served"][0]["recorded"] >= 3
         and served["served"][1]["recorded"] == (1 if EXACT else 0),
         f"step 7, read_datasets: {served}")
    def licensed():
        rows = call(named["read_datasets"], {}, "read", "unchanged")["data"]["served"]
        return rows if rows[0]["licensed"] else None
    until(90, licensed, "step 7, read_datasets did not say the dataset licensed")
    shown = page(VENUE, "admin", "/datasets")
    must("Not licensed yet" not in shown and "Licensed" in shown,
         "step 7, the Datasets page says the dataset licensed")
    many = "2 contracts mapped for 2 subjects" if EXACT else "1 contract mapped for 1 subject"
    must(many in shown and "each contract pays 1.00 USD" in shown,
         "step 7, the Datasets page shows the same")

    # 8. Raw responses kept, and the lake's record.
    kept = compose("exec", "-T", VENUE, "python", "-c",
                   "from meridian import edge; "
                   "print(sum(1 for p in (edge.storage_dir() / 'responses').rglob('*') if p.is_file()))")
    must(int(kept.stdout.strip() or 0) >= 3, f"step 8, raw responses in storage: {kept.stdout}")
    names = {subject: "CONTRACT", ranged: "RANGE", resolved: "RESOLVED", usd: "USD"}

    def lake():
        lines = compose("run", "--rm", "-T", "store", "lake").stdout.split("\n")
        for instrument_id, name in names.items():
            lines = [line.replace(instrument_id, name) for line in lines]
        withdrawn = any(line.startswith(f"want|{DATASET}|withdrawn|") for line in lines)
        declined = any(line.startswith(f"want|{DATASET}|declined|RANGE|") for line in lines)
        return lines if withdrawn and declined else None
    lines = until(240, lake, "step 8, the standing want was not withdrawn, or the range not "
                             "declined")
    log("store lake:\n" + "\n".join(lines))
    rows = [line.split("|") for line in lines if line.startswith(f"row|{DATASET}|")]
    sequences = sorted(int(row[3]) for row in rows)
    must(sequences == list(range(1, len(sequences) + 1))
         and len(sequences) >= (4 if EXACT else 2),
         f"step 8, the rows kept numbered from 1 with no holes: {sequences}")
    must({row[6] for row in rows} == {"CONTRACT"} and all(row[9] == "" for row in rows),
         f"step 8, each row the contract's, with no business date: {rows}")
    kept_rows = [line.split("|") for line in lines if line.startswith(f"row|{OUTCOMES}|")]
    must(not EXACT or [(r[4], r[5], r[6]) for r in kept_rows] == [(f"{RESOLVED}:outcome", "1",
                                                                    "RESOLVED")],
         f"step 8, the outcome's one version kept: {kept_rows}")
    # The settled market is followed beside the contract, so a want may ask
    # for both.
    must(any(line.startswith(f"want|{DATASET}|asked|")
             and "CONTRACT" in line.split("|")[3].split(",") for line in lines),
         f"step 8, the want asked: {lines}")
    must(any(line.startswith(f"miss|{VENUE}|") for line in lines),
         f"step 8, the venue's miss counted: {lines}")

    print(f"e2e OK in {int(time.time() - started)}s: on core's plugin harness, the live "
          "dataset of prices and quotes listed by the deployment admin's tool, kept two days "
          "by default; nothing asked of Polymarket US and no record minted before a want; a "
          "custodian's contract, known by its own symbol, read and named, Polymarket US's slug "
          "joined to it, and its last trade, bid and offer recorded per contract in dollars, "
          "read and heard; its quote with sizes; the market of three sides declined as not "
          "covered; a settled market's outcome recorded unasked from the contract's side, final, "
          "kept, heard and read back; read_connection and read_datasets answering what the "
          "pages show, the dataset licensed, the payout one dollar; raw responses in storage; "
          "and `store lake` numbering each row with no holes, the wants and the miss")


def main():
    open(LOG, "w").close()
    try:
        run()
    except (Failed, subprocess.TimeoutExpired, KeyError, ValueError, IndexError) as failed:
        print(f"e2e FAILED: {failed}; the run is in {LOG}, the components' logs in "
              ".e2e/components.log", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
