# backend/src/freightcheck/services/session_store.py
"""Mongo persistence for agent checkpoints and final session snapshots (Flow Spec §7)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import DuplicateKeyError, PyMongoError

from freightcheck.errors import DatabaseError, DuplicateAuditError
from freightcheck.settings import settings

log = structlog.get_logger()

_store: MongoSessionStore | None = None


class MongoSessionStore:
    """Upserts and reads audit session documents keyed by `session_id`."""

    def __init__(self, uri: str, db_name: str) -> None:
        self._client: AsyncIOMotorClient[dict[str, Any]] = AsyncIOMotorClient(
            uri,
            serverSelectionTimeoutMS=3000,
        )
        self._sessions: AsyncIOMotorCollection[dict[str, Any]] = self._client[db_name][
            "audit_sessions"
        ]
        self._indexes_ready = False
        self._index_lock = asyncio.Lock()
        self._pending_tasks: set[asyncio.Task[None]] = set()

    async def ensure_indexes(self) -> None:
        """Idempotent index creation for session lookups."""
        if self._indexes_ready:
            return
        async with self._index_lock:
            if self._indexes_ready:
                return
            try:
                await self._sessions.create_index("session_id", unique=True)
                await self._sessions.create_index([("created_at", -1)])
            except PyMongoError:
                log.exception("mongo.ensure_indexes_failed")
            finally:
                self._indexes_ready = True

    async def _ensure_indexes_once(self) -> None:
        await self.ensure_indexes()

    async def create_audit_session_if_absent(self, session_id: str, doc: dict[str, Any]) -> None:
        """Insert the initial audit session row exactly once (``POST /audit``).

        Uses ``insert_one`` so a duplicate ``session_id`` hits the unique index
        and surfaces as ``DuplicateAuditError`` — never read-then-write.
        """
        await self._ensure_indexes_once()
        now = datetime.now(UTC)
        payload = {**doc, "session_id": session_id, "updated_at": now}
        try:
            await self._sessions.insert_one(payload)
            log.info(
                "mongo.write",
                session_id=session_id,
                collection="audit_sessions",
                operation="create_audit_session",
            )
        except DuplicateKeyError as exc:
            raise DuplicateAuditError(
                f"An audit has already been triggered for session_id '{session_id}'. "
                "Poll /sessions/:id for results.",
                session_id=session_id,
            ) from exc
        except PyMongoError as exc:
            log.exception(
                "mongo.error",
                session_id=session_id,
                operation="create_audit_session",
            )
            raise DatabaseError(
                "Failed to create audit session. Please try again.",
                session_id=session_id,
            ) from exc

    async def upsert_checkpoint_async(self, session_id: str, doc: dict[str, Any]) -> None:
        """Merge `doc` into the session row (checkpoint mirror or final fields)."""
        await self._ensure_indexes_once()
        now = datetime.now(UTC)
        payload = {**doc, "session_id": session_id, "updated_at": now}
        try:
            await self._sessions.update_one(
                {"session_id": session_id},
                {
                    "$set": payload,
                    "$setOnInsert": {"created_at": doc.get("created_at", now)},
                },
                upsert=True,
            )
            log.info(
                "mongo.write",
                session_id=session_id,
                collection="audit_sessions",
                operation="upsert_checkpoint",
            )
        except PyMongoError:
            log.exception("mongo.error", session_id=session_id, operation="upsert_checkpoint")

    def upsert_checkpoint(self, session_id: str, doc: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.upsert_checkpoint_async(session_id, doc))
            return

        task = loop.create_task(self.upsert_checkpoint_async(session_id, doc))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    # ---- Read helpers (M5) -----------------------------------------------

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Fetch a single session by `session_id`.  Returns ``None`` if absent."""
        await self._ensure_indexes_once()
        try:
            doc = await self._sessions.find_one({"session_id": session_id}, {"_id": 0})
            return dict(doc) if doc else None
        except PyMongoError as exc:
            log.exception("mongo.error", session_id=session_id, operation="get_session")
            raise DatabaseError(
                "Failed to retrieve session. Please try again.",
                session_id=session_id,
            ) from exc

    async def list_sessions(self) -> list[dict[str, Any]]:
        """Return all sessions sorted by ``created_at`` descending."""
        await self._ensure_indexes_once()
        try:
            cursor = self._sessions.find({}, {"_id": 0}).sort("created_at", -1)
            docs: list[dict[str, Any]] = [doc async for doc in cursor]
            return docs
        except PyMongoError as exc:
            log.exception("mongo.error", operation="list_sessions")
            raise DatabaseError(
                "Failed to retrieve sessions. Please try again.",
            ) from exc

    async def ping(self) -> bool:
        """Return ``True`` if the Mongo connection is alive."""
        try:
            await self._client.admin.command("ping")
            return True
        except PyMongoError:
            return False


def get_mongo_session_store() -> MongoSessionStore:
    """Process-wide singleton — tests may call `reset_mongo_session_store_for_tests`."""
    global _store  # noqa: PLW0603
    if _store is None:
        _store = MongoSessionStore(settings.MONGODB_URI, settings.MONGODB_DB)
    return _store


def reset_mongo_session_store_for_tests() -> None:
    """Drop the cached store so the next access builds a fresh client."""
    global _store  # noqa: PLW0603
    if _store is not None:
        _store._client.close()
    _store = None
