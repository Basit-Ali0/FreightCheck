# backend/tests/unit/test_env_bootstrap.py
"""``tests/support/env_bootstrap`` resolution rules."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.support import env_bootstrap


def test_read_dotenv_value_parses_unquoted_key(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("GEMINI_API_KEY=secret-from-file\n", encoding="utf-8")
    assert env_bootstrap.read_dotenv_value(p, "GEMINI_API_KEY") == "secret-from-file"


def test_read_dotenv_value_respects_quotes(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text('MONGODB_URI="mongodb://host:27017/db"\n', encoding="utf-8")
    assert env_bootstrap.read_dotenv_value(p, "MONGODB_URI") == "mongodb://host:27017/db"


def test_apply_preserves_nonempty_process_env_over_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Process environment wins; ``.env`` must not replace a real exported key."""
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=from-dotenv-only\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "process-env-real-key-32chars-minimum-xx")
    monkeypatch.setenv("MONGODB_URI", "mongodb://process-only:27017/db")

    env_bootstrap.apply_test_env_defaults(backend_dir=tmp_path, dotenv_file=env_file)

    assert os.environ["GEMINI_API_KEY"] == "process-env-real-key-32chars-minimum-xx"
    assert os.environ["MONGODB_URI"] == "mongodb://process-only:27017/db"


def test_apply_hoists_dotenv_when_process_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEY=hoisted-gemini-key-32chars-minimum-xxx\n"
        "MONGODB_URI=mongodb://from-env-file:27017/mydb\n",
        encoding="utf-8",
    )

    env_bootstrap.apply_test_env_defaults(backend_dir=tmp_path, dotenv_file=env_file)

    assert os.environ["GEMINI_API_KEY"] == "hoisted-gemini-key-32chars-minimum-xxx"
    assert os.environ["MONGODB_URI"] == "mongodb://from-env-file:27017/mydb"


def test_apply_injects_dummy_when_missing_everywhere(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    # No .env file in tmp_path
    env_bootstrap.apply_test_env_defaults(backend_dir=tmp_path, dotenv_file=tmp_path / ".env")

    assert os.environ["GEMINI_API_KEY"] == "test-gemini-key"
    assert os.environ["MONGODB_URI"] == "mongodb://127.0.0.1:27017/freightcheck_test"


def test_is_placeholder_gemini_key_recognizes_known_dummies() -> None:
    assert env_bootstrap.is_placeholder_gemini_key("test-gemini-key") is True
    assert env_bootstrap.is_placeholder_gemini_key("") is True
    assert env_bootstrap.is_placeholder_gemini_key("x" * 40) is False
