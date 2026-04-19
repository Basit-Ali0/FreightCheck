# backend/tests/conftest.py
"""Pytest fixtures shared across unit and integration tests."""

from __future__ import annotations

from collections.abc import Iterator

# Resolve ``GEMINI_API_KEY`` / ``MONGODB_URI`` before any ``freightcheck`` import:
# prefer process env, then ``backend/.env``, then safe CI defaults (never
# ``setdefault`` over a value that only exists in ``.env``).
from tests.support.env_bootstrap import apply_test_env_defaults

apply_test_env_defaults()

import pytest

from freightcheck.services import upload_cache
from freightcheck.services.session_store import reset_mongo_session_store_for_tests


@pytest.fixture(autouse=True)
def _reset_upload_cache() -> Iterator[None]:
    """Ensure every test starts with an empty upload cache."""
    upload_cache.clear()
    reset_mongo_session_store_for_tests()
    yield
    upload_cache.clear()
    reset_mongo_session_store_for_tests()
