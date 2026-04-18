# backend/tests/unit/test_upload_cache.py
"""Unit tests for the in-memory upload cache with TTL semantics."""

from __future__ import annotations

import pytest

from freightcheck.errors import SessionNotFoundError
from freightcheck.services import upload_cache


def test_put_get_roundtrip() -> None:
    raw = {"bol": "b", "invoice": "i", "packing_list": "p"}
    upload_cache.put("sess-1", raw)
    assert upload_cache.get("sess-1") == raw


def test_get_missing_raises_session_not_found() -> None:
    with pytest.raises(SessionNotFoundError):
        upload_cache.get("does-not-exist")


def test_expired_entry_raises_and_is_evicted(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr(upload_cache, "_now", lambda: clock["now"])

    upload_cache.put("sess-2", {"bol": "b", "invoice": "i", "packing_list": "p"})

    clock["now"] += 10_000.0  # well past the default TTL
    with pytest.raises(SessionNotFoundError):
        upload_cache.get("sess-2")

    assert "sess-2" not in upload_cache._cache


def test_delete_is_idempotent() -> None:
    upload_cache.put("sess-3", {"bol": "b", "invoice": "i", "packing_list": "p"})
    upload_cache.delete("sess-3")
    upload_cache.delete("sess-3")
    with pytest.raises(SessionNotFoundError):
        upload_cache.get("sess-3")
