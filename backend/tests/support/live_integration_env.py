# backend/tests/support/live_integration_env.py
"""Readiness checks for ``@pytest.mark.integration`` live service tests.

Uses ``freightcheck.settings`` — import only from live tests after bootstrap.
"""

from __future__ import annotations

from freightcheck.settings import settings
from tests.support.env_bootstrap import (
    is_placeholder_gemini_key,
    is_placeholder_mongodb_uri,
)


def is_real_gemini_api_key_configured() -> bool:
    """True when ``settings`` holds a non-placeholder Gemini API key."""
    key = (settings.GEMINI_API_KEY or "").strip()
    return bool(key) and not is_placeholder_gemini_key(key)


def is_real_mongodb_uri_for_live_integration() -> bool:
    """True when ``settings`` holds a non-canonical-test MongoDB URI."""
    uri = (settings.MONGODB_URI or "").strip()
    return bool(uri) and not is_placeholder_mongodb_uri(uri)
