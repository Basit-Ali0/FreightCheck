# backend/src/freightcheck/api/health.py
"""GET /health endpoint per Environment Setup §4.3."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from freightcheck.services.session_store import get_mongo_session_store
from freightcheck.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Return service health including Mongo connectivity and Gemini configuration."""
    store = get_mongo_session_store()
    mongo_ok = await store.ping()
    gemini_configured = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())
    return {
        "status": "ok",
        "mongo": "connected" if mongo_ok else "disconnected",
        "gemini": "configured" if gemini_configured else "not_configured",
    }
