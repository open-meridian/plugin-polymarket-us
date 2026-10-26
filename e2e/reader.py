"""The e2e's reader: a plugin on the SDK standing in for the reading roles, so
the lake has someone whose reads it asks this plugin for. It holds `custody`
only so that it can name the instruments it asks about as a custodian's
book would, by resolving their identifiers (W3.1): a contract by the
custodian's own symbol, never resolved by the venue, a record the plugin
names by reading it (W3.6); `reporting` to read and hear prices, and from
contract v23 an event contract's outcomes; and `signal` to read and hear
quotes, which `reporting` does not read (the plan's Q9).

This plugin's own e2e stand-in, no longer held to a sibling's. It is not
the plugin, and is never built into its image: `make e2e` runs it from this file
in a container of the plugin's image, which carries the SDK, beside the
plugin on core's harness. It answers its page as JSON for the harness's
runner (`page --instance reader --level read PATH`):

  /resolve?name=N&scheme=S&value=V[&source=SRC][&ticker=MIC]
                                       names a record by an identifier --
                                       from contract v26 with the venue's
                                       ticker beside it, under its MIC, as a
                                       broker reports the exchange's symbol
                                       -- and gives every record named so
                                       far;
  /follow?subject=ID...                hears prices, quotes and outcomes
                                       recorded for them;
  /heard                               what it heard, each row's dataset, row
                                       key, kind, amounts and sizes, and each
                                       outcome's determination and stage;
  /prices?subject=ID&dataset=D[&kind=K]
  /quotes?subject=ID&dataset=D         one read: its rows, and what it left
                                       unanswered and why;
  /outcomes?subject=ID                 the outcomes in force (contract v23);
  /groups?subject=ID                   the event groups holding it, as in
                                       force now (contract v26, W3.30).
"""

import asyncio
import http.server
import json
import threading
import urllib.parse

import meridian
from meridian import Interface, Page, SourceChoice
from meridian.operations import as_decimal, as_money
from meridian.plugin.v1 import operations_pb2 as ops

PORT = 8088
LOOP = asyncio.new_event_loop()


def meta_json(meta):
    return {
        "dataset": meta.source.dataset,
        "venue_id": meta.source.venue_id,
        "row_key": meta.row_key,
        "version": meta.version,
        "business_date": meta.business_date,
        "subject": meta.subjects[0].entity_id if meta.subjects else "",
        "unconverted": [u.scheme for u in meta.unconverted],
        "raw": meta.raw.key,
    }


def money_json(prefix, message):
    money = as_money(message)
    return {
        f"{prefix}amount": str(money.amount),
        f"{prefix}instrument_id": money.instrument_id,
        f"{prefix}currency_code": money.currency_code,
    }


def price_json(price):
    return {"row": "price", "kind": ops.PriceKind.Name(price.kind), **meta_json(price.meta),
            **money_json("", price.price)}  # fmt: skip


def quote_json(quote):
    said = {"row": "quote", **meta_json(quote.meta)}
    for side in ("bid", "ask"):
        if quote.HasField(side):
            said.update(money_json(f"{side}_", getattr(quote, side)))
        if quote.HasField(f"{side}_quantity"):
            said[f"{side}_quantity"] = str(as_decimal(getattr(quote, f"{side}_quantity")))
    return said


def outcome_json(outcome):
    said = outcome.determination_as_reported
    return {"row": "outcome", **meta_json(outcome.meta),
            "determination": ops.OutcomeDetermination.Name(outcome.determination),
            "stage": ops.OutcomeStage.Name(outcome.stage),
            "settled_at_ns": outcome.settled_at_ns,
            "as_reported": f"{said.scheme}={said.code}",
            "source_times": len(outcome.meta.source_times),
            **money_json("", outcome.settlement_value)}  # fmt: skip


def group_json(group):
    return {"event_group_id": group.event_group_id, "venue_id": group.venue_id,
            "venue_event_ref": group.venue_event_ref, "title": group.title,
            "members": list(group.member_instrument_ids),
            "mutually_exclusive": ops.EventGroupFlag.Name(group.mutually_exclusive),
            "exhaustive": ops.EventGroupFlag.Name(group.exhaustive),
            "series_id": group.series_id, "version": group.version,
            "provisional": group.provisional}  # fmt: skip


def unanswered_json(answer):
    return [{"subject": u.subject.entity_id, "dataset": u.dataset,
             "reason": ops.UnansweredReason.Name(u.reason)} for u in answer.unanswered]  # fmt: skip


class Reader:
    def __init__(self, plugin):
        self.plugin = plugin
        self.heard = []
        self.following = None
        self.ids = {}

    async def resolve(self, query):
        one = lambda name: query.get(name, [""])[0]  # noqa: E731
        if one("name") and one("name") not in self.ids:
            named = [ops.Identifier(scheme=one("scheme"), value=one("value"), source=one("source"))]
            stated = {}
            if one("ticker"):
                # Contract v26 (rulings 199, 204): the custodian states the
                # venue's ticker beside its own symbol, an event contract,
                # so the platform matches or mints it by the venue's code.
                named.append(ops.Identifier(scheme="ticker", value=one("value"),
                                            source=one("ticker")))
                stated = {"stated_asset_class": "event_contract",
                          "stated_instrument_type": "binary_event_contract"}
            # Contract v24 (W3.7): a source thinner than an identifier, a
            # description and a currency mints nothing, so the custodian
            # states the contract's description and currency, as its
            # statement would.
            found = await self.plugin.resolve_identifier(
                identifiers=named,
                stated_description=one("description"),
                stated_currency=one("currency"),
                **stated,
            )
            if not found.instrument_id:
                raise RuntimeError(f"{one('name')} did not resolve: {found}")
            self.ids[one("name")] = found.instrument_id
        return dict(self.ids)

    async def on_price(self, heard):
        self.heard.append(price_json(heard.message.price))

    async def on_quote(self, heard):
        self.heard.append(quote_json(heard.message.quote))

    async def on_outcome(self, heard):
        self.heard.append(outcome_json(heard.message.outcome))

    async def answer(self, path, query):
        one = lambda name: query.get(name, [""])[0]  # noqa: E731
        if path == "/resolve":
            return await self.resolve(query)
        if path == "/follow":
            if self.following is None:
                self.following = asyncio.ensure_future(self.plugin.receive(
                    prices_recorded=self.on_price, quotes_recorded=self.on_quote,
                    outcomes_recorded=self.on_outcome, subjects=query["subject"]))  # fmt: skip
            return {"following": query["subject"]}
        if path == "/heard":
            return {"heard": self.heard}
        if path == "/outcomes":
            answer = await self.plugin.list_outcomes(
                subjects=[meridian.SubjectRef(entity_id=s) for s in query["subject"]])
            return {"outcomes": [outcome_json(o) for o in answer.outcomes]}
        if path == "/groups":
            answer = await self.plugin.list_event_groups(instrument_ids=query["subject"])
            return {"groups": [group_json(g) for g in answer.event_groups]}
        asked = {"subjects": [meridian.SubjectRef(entity_id=s) for s in query["subject"]]}
        if one("dataset"):
            asked["sources"] = SourceChoice(named=[one("dataset")])
        if path == "/prices":
            if one("kind"):
                asked["kinds"] = [one("kind")]
            answer = await self.plugin.list_prices(**asked)
            return {"prices": [price_json(p) for p in answer.prices],
                    "unanswered": unanswered_json(answer)}  # fmt: skip
        if path == "/quotes":
            answer = await self.plugin.list_quotes(**asked)
            return {"quotes": [quote_json(q) for q in answer.quotes],
                    "unanswered": unanswered_json(answer)}  # fmt: skip
        return {"page": "the e2e's reader"}


def serve(reader):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            asked = reader.answer(parsed.path, urllib.parse.parse_qs(parsed.query))
            future = asyncio.run_coroutine_threadsafe(asked, LOOP)
            try:
                body, status = json.dumps(future.result(timeout=60), sort_keys=True), 200
            except Exception as failed:  # said on the page, for the run to quote
                body, status = json.dumps({"failed": f"{type(failed).__name__}: {failed}"}), 500
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


#: What the stand-in registers, its whole declaration (contract v25): the
#: e2e prints it with meridian-declaration and the harness holds the
#: stand-in's registration to it.
DECLARATION = meridian.Declaration(
    interface=Interface(
        PORT,
        "The e2e's reader",
        pages=[Page("/", "Rows", levels=["read"], roles=["reporting"])],
    )
)


async def main():
    plugin = await meridian.connect(
        # Contract v25: what the stand-in registers is its declaration.
        declaration=DECLARATION
    )  # fmt: skip
    reader = Reader(plugin)
    threading.Thread(target=serve, args=(reader,), daemon=True).start()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.set_event_loop(LOOP)
    LOOP.run_until_complete(main())
