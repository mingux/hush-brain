"""The `hush` CLI: serve the construct, or talk to the brain directly."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

BANNER = r"""
  _   _  _   _  ___  _  _    ___  ___    _    ___  _  _
 | |_| || | | |/ __|| || |  | _ )| _ \  /_\  |_ _|| \| |
 |  _  || |_| |\__ \|  _  | | _ \|   / / _ \  | | | .` |
 |_| |_| \___/ |___/|_||_|  |___/|_|_\/_/ \_\|___||_|\_|
             wake up... the construct is loading
"""


def _data_dir(args) -> Path:
    from .server import default_data_dir

    return Path(args.data_dir) if args.data_dir else default_data_dir()


def cmd_serve(args) -> None:
    import uvicorn

    from .server import create_app

    print(BANNER)
    app = create_app(_data_dir(args))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def cmd_ask(args) -> None:
    async def run() -> None:
        from .brain import Brain
        from .bus import EventBus
        from .db import EventStore
        from .orchestrator import Orchestrator
        from .providers import resolve_provider

        data_dir = _data_dir(args)
        store = EventStore(data_dir / "hush.db")
        bus = EventBus(store)
        brain = Brain(data_dir / "brain")
        provider = await resolve_provider()
        orchestrator = Orchestrator(bus, brain, provider)
        queue = bus.subscribe()
        run_ = await orchestrator.spawn("oracle", {"question": args.question})
        while True:
            event = await queue.get()
            if event["kind"] == "agent.output" and event["agent"] == run_.name:
                print(event["payload"]["text"])
                if event["payload"].get("citations"):
                    print("\nsources: " + ", ".join(f"[[{c}]]" for c in event["payload"]["citations"]))
            if event["kind"] in ("agent.done", "agent.error") and event["agent"] == run_.name:
                if event["kind"] == "agent.error":
                    print(f"agent failed: {event['payload'].get('error')}")
                break
        store.close()

    asyncio.run(run())


def cmd_remember(args) -> None:
    from .brain import Brain

    brain = Brain(_data_dir(args) / "brain")
    memory = brain.remember(args.title, args.content)
    print(f"remembered [[{memory['slug']}]] -> {memory['path']}")


def cmd_recall(args) -> None:
    from .brain import Brain

    brain = Brain(_data_dir(args) / "brain")
    hits = brain.recall(args.query)
    if not hits:
        print("the brain holds nothing on that. yet.")
        return
    for hit in hits:
        print(f"[[{hit['slug']}]] (score {hit['score']}) {hit['title']}\n    {hit['excerpt']}")


def cmd_status(args) -> None:
    from .brain import Brain
    from .db import EventStore

    data_dir = _data_dir(args)
    store = EventStore(data_dir / "hush.db")
    brain = Brain(data_dir / "brain")
    print(json.dumps({"events": store.count(), "tokens": store.token_totals(), "brain": brain.stats()}, indent=2))
    store.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="hush", description="Hush Brain — agent orchestrator, monitor, and markdown brain.")
    parser.add_argument("--data-dir", help="data directory (default: ~/.hush-brain or $HUSH_HOME)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="start the server + Matrix dashboard")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8199)
    p_serve.set_defaults(func=cmd_serve)

    p_ask = sub.add_parser("ask", help="ask the Oracle a question (grounded in the brain)")
    p_ask.add_argument("question")
    p_ask.set_defaults(func=cmd_ask)

    p_rem = sub.add_parser("remember", help="write a memory into the brain")
    p_rem.add_argument("title")
    p_rem.add_argument("content")
    p_rem.set_defaults(func=cmd_remember)

    p_rec = sub.add_parser("recall", help="search the brain")
    p_rec.add_argument("query")
    p_rec.set_defaults(func=cmd_recall)

    p_status = sub.add_parser("status", help="print store/brain stats")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
