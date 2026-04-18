# backend/src/freightcheck/services/upload_cache.py
"""In-memory TTL cache for raw text extracted during `/upload` per Error Handling section 7.

Lives for the lifetime of the process. `POST /audit` reads from this cache
to avoid re-parsing PDFs. Cache is lost on restart, which is acceptable at
MVP scale given the 10-minute TTL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from freightcheck.errors import SessionNotFoundError
from freightcheck.settings import settings


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    raw_texts: dict[str, str]
    expires_at: float  # time.monotonic() seconds


_cache: dict[str, _CacheEntry] = {}


def _now() -> float:
    """Monotonic clock seconds — indirection exists so tests can patch it."""
    return time.monotonic()


def put(session_id: str, raw_texts: dict[str, str]) -> None:
    """Store `raw_texts` under `session_id` with the configured TTL."""
    _cache[session_id] = _CacheEntry(
        raw_texts=raw_texts,
        expires_at=_now() + settings.UPLOAD_CACHE_TTL_SECONDS,
    )


def get(session_id: str) -> dict[str, str]:
    """Fetch the raw texts for `session_id` or raise `SessionNotFoundError`.

    Expired entries are removed on access. The caller receives the same dict
    reference the writer stored, so mutation is discouraged.
    """
    entry = _cache.get(session_id)
    if entry is None:
        raise SessionNotFoundError(
            f"SessionNotFoundError: No upload found for session_id '{session_id}'. "
            "Upload documents first via POST /upload.",
            session_id=session_id,
        )
    if entry.expires_at <= _now():
        _cache.pop(session_id, None)
        raise SessionNotFoundError(
            f"SessionNotFoundError: Upload for session_id '{session_id}' has expired. "
            "Upload documents first via POST /upload.",
            session_id=session_id,
        )
    return entry.raw_texts


def delete(session_id: str) -> None:
    """Remove an entry; no-op if absent. Useful once the audit has started."""
    _cache.pop(session_id, None)


def clear() -> None:
    """Wipe the cache. Test-only helper — production code must not call this."""
    _cache.clear()
