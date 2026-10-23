"""Logging configuration."""

from __future__ import annotations

import logging

from app.core.config import settings

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging() -> None:
    """Configure root logging once, at application startup."""
    level = getattr(logging, settings.app.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format=_FORMAT)

    # Keep noisy third-party loggers at WARNING unless we are debugging.
    if level > logging.DEBUG:
        for name in ("httpx", "httpcore", "websockets", "openai"):
            logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
