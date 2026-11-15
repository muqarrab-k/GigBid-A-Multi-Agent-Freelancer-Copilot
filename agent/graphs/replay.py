"""Replay a thread from the checkpoint just before a node: make replay THREAD=<id> NODE=<name>."""

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from agent.config import get_config
from agent.graphs.bid_graph import build_bid_graph, pending_approval
from agent.graphs.checkpoint import open_saver
from agent.local_stack import LocalStack, user_for
from agent.nodes.common import BidContext, NodeCache


async def replay(thread: str, node: str, folder: Path) -> None:
    settings = get_config()
    async with open_saver(settings) as saver:
        graph = build_bid_graph(saver)
        config = {"configurable": {"thread_id": thread}}
        target = None
        async for snap in graph.aget_state_history(config):  # type: ignore[arg-type]
            if node in snap.next:
                target = snap
        if target is None:
            raise SystemExit(f"no checkpoint before {node!r} in thread {thread!r}")
        persona = target.values.get("persona", "ai_ml")
        layer = LocalStack(folder).layer(user_for(persona))
        await layer.discover()
        ctx = BidContext(layer=layer, persona=persona, settings=settings, cache=NodeCache(settings.nodes.cache_dir))
        # forks the thread from that checkpoint; writes go to a scratch GigSim
        state = await graph.ainvoke(None, config=target.config, context=ctx)
        print(json.dumps({"from_checkpoint": target.config["configurable"].get("checkpoint_id"), "node": node,
                          "status": state.get("status"), "notes": state.get("notes", []),
                          "errors": state.get("errors", []), "waiting_for_approval": bool(pending_approval(state))},
                         indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a bid thread from before a node")
    parser.add_argument("thread")
    parser.add_argument("node")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(replay(args.thread, args.node, Path(tmp)))


if __name__ == "__main__":
    main()
