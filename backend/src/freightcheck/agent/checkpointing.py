# backend/src/freightcheck/agent/checkpointing.py
"""Checkpointing: in-memory LangGraph state plus optional Mongo mirror (Flow Spec §7)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata
from langgraph.checkpoint.memory import InMemorySaver

log = structlog.get_logger()

MongoWriteFn = Callable[[str, dict[str, Any]], None]


def _strip_for_mongo(channel_values: dict[str, Any]) -> dict[str, Any]:
    """Persistable projection: drop bulky `raw_texts` (Flow Spec §10)."""
    doc = {k: v for k, v in channel_values.items() if k != "raw_texts"}
    err = doc.pop("error", None)
    doc["error_message"] = err
    return doc


class MongoMirroringSaver(InMemorySaver):
    """In-memory checkpoints for LangGraph correctness, plus optional Mongo upsert."""

    def __init__(
        self,
        *,
        on_checkpoint: MongoWriteFn | None = None,
    ) -> None:
        super().__init__()
        self._on_checkpoint = on_checkpoint

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | int | float],
    ) -> RunnableConfig:
        out = super().put(config, checkpoint, metadata, new_versions)
        if self._on_checkpoint is not None:
            thread_id = str(config["configurable"]["thread_id"])
            values = checkpoint.get("channel_values") or {}
            try:
                self._on_checkpoint(thread_id, _strip_for_mongo(dict(values)))
            except Exception:
                log.exception("agent.checkpoint_mongo_failed", session_id=thread_id)
        return out
