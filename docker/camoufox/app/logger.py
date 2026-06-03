"""Centralized JSON logger for all app modules.

Usage:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("something happened")
    log.warning("watch out", extra={"key": "value"})

Output (one JSON object per line):
    {"ts":"21:05:33","level":"INFO","src":"main:42","msg":"something happened"}
    {"ts":"21:05:34","level":"WARNING","src":"main:55","msg":"watch out","key":"value"}
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from typing import Any


class _JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
            "level": record.levelname,
            "src": f"{record.module}:{record.funcName}:{record.lineno}",
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in _RESERVED and k not in entry:
                entry[k] = v
        return json.dumps(entry, default=str)


_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "relativeCreated",
        "exc_info",
        "exc_text",
        "stack_info",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "pathname",
        "process",
        "processName",
        "thread",
        "threadName",
    }
)


def get_logger(name: str) -> logging.Logger:
    """Get a JSON-line logger writing to stderr."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
