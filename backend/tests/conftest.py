# backend/tests/conftest.py
"""Pytest fixtures shared across unit and integration tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from freightcheck.services import upload_cache


@pytest.fixture(autouse=True)
def _reset_upload_cache() -> Iterator[None]:
    """Ensure every test starts with an empty upload cache."""
    upload_cache.clear()
    yield
    upload_cache.clear()
