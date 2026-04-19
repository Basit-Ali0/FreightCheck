# backend/tests/support/env_bootstrap.py
"""Resolve ``GEMINI_API_KEY`` / ``MONGODB_URI`` for pytest before ``freightcheck`` imports.

``os.environ.setdefault`` would win over ``backend/.env`` once pydantic-settings
loads (env overrides file). We only inject safe CI defaults when the process
environment has no non-empty value *and* the project ``.env`` does not supply
one either.
"""

from __future__ import annotations

import os
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ENV_FILE = _BACKEND_ROOT / ".env"

_DUMMY_GEMINI_KEYS = frozenset(
    {
        "test-gemini-key",
        "test-gemini-key-for-ci",
    },
)

_DUMMY_MONGODB_URIS = frozenset(
    {
        "mongodb://127.0.0.1:27017/freightcheck_test",
    },
)

_FALLBACK_GEMINI = "test-gemini-key"
_FALLBACK_MONGO = "mongodb://127.0.0.1:27017/freightcheck_test"


def backend_root() -> Path:
    """``backend/`` directory (contains ``src/`` and ``tests/``)."""
    return _BACKEND_ROOT


def read_dotenv_value(env_file: Path, key: str) -> str | None:
    """Read a single ``KEY=value`` from a dotenv-style file (minimal parser)."""
    if not env_file.is_file():
        return None
    try:
        text = env_file.read_text(encoding="utf-8")
    except OSError:
        return None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() != key:
            continue
        val = v.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        return val or None
    return None


def is_placeholder_gemini_key(key: str) -> bool:
    """Values that must never run live Gemini integration tests."""
    s = key.strip()
    if not s:
        return True
    if s in _DUMMY_GEMINI_KEYS:
        return True
    # Short keys are not Google-style API keys; keeps CI dummies out of live runs.
    return len(s) < 32


def is_placeholder_mongodb_uri(uri: str) -> bool:
    """URIs used only as offline test defaults (live tests still require ping)."""
    s = uri.strip()
    if not s:
        return True
    return s in _DUMMY_MONGODB_URIS


def _process_env_raw(key: str) -> str | None:
    v = os.environ.get(key)
    if v is None:
        return None
    stripped = v.strip()
    return stripped if stripped else None


def _resolve_bootstrap_value(
    *,
    key: str,
    dotenv_file: Path,
    fallback: str,
) -> str:
    """Value to place in ``os.environ`` so ``Settings()`` can import."""
    proc = _process_env_raw(key)
    if proc is not None:
        return proc
    from_file = read_dotenv_value(dotenv_file, key)
    if from_file is not None and from_file.strip():
        return from_file.strip()
    return fallback


def apply_test_env_defaults(
    *,
    backend_dir: Path | None = None,
    dotenv_file: Path | None = None,
) -> None:
    """Hoist ``.env`` into the process environment when needed; else set fallbacks.

    Call **before** any ``import freightcheck``. Idempotent for keys that
    already have a non-empty process-environment value.
    """
    root = backend_dir or _BACKEND_ROOT
    env_path = dotenv_file if dotenv_file is not None else (root / ".env")

    gemini = _resolve_bootstrap_value(
        key="GEMINI_API_KEY",
        dotenv_file=env_path,
        fallback=_FALLBACK_GEMINI,
    )
    mongo = _resolve_bootstrap_value(
        key="MONGODB_URI",
        dotenv_file=env_path,
        fallback=_FALLBACK_MONGO,
    )
    os.environ["GEMINI_API_KEY"] = gemini
    os.environ["MONGODB_URI"] = mongo
