# backend/src/freightcheck/logging_config.py
"""Structured logging setup per Implementation Rules section 3.1.

`configure_logging()` is idempotent and must be called once at application
startup (from `main.py`). Tests typically skip it; `structlog.get_logger()`
still works with default processors.
"""

from __future__ import annotations

import logging
from typing import Any

import structlog

from freightcheck.settings import settings


def configure_logging() -> None:
    """Configure stdlib logging and structlog for the running process."""
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(message)s")

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.LOG_FORMAT == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL),
        ),
        cache_logger_on_first_use=True,
    )


log: structlog.stdlib.BoundLogger = structlog.get_logger()
