"""Checkpointers: Postgres (schema langgraph) for real runs, memory for tests."""

import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from agent import handoffs
from agent.config import Settings, get_config


def serde() -> JsonPlusSerializer:
    """Only our hand-off models may be loaded back from a checkpoint."""
    names = [n for n, c in vars(handoffs).items() if inspect.isclass(c) and issubclass(c, BaseModel)]
    return JsonPlusSerializer(allowed_msgpack_modules=[("agent.handoffs", n) for n in names])


def memory_saver() -> MemorySaver:
    return MemorySaver(serde=serde())


def postgres_dsn(settings: Settings) -> str:
    cfg = settings.checkpointer
    if "-pooler." in cfg.dsn:
        # neon pooler rejects startup options; tables go to public
        return cfg.dsn
    joiner = "&" if "?" in cfg.dsn else "?"
    return f"{cfg.dsn}{joiner}options={quote(f'-csearch_path={cfg.schema_name}')}"


@asynccontextmanager
async def open_saver(settings: Settings | None = None) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    settings = settings or get_config()
    if settings.checkpointer.backend == "memory":
        yield memory_saver()
        return
    async with AsyncPostgresSaver.from_conn_string(postgres_dsn(settings), serde=serde()) as saver:
        await saver.setup()
        yield saver
