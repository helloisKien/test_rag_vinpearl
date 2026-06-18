"""DA10 — Structured JSON logger (§7 monitoring_plan).

Output: stdout + logs/da10.jsonl (one JSON object per line).
Usage:
    from observability.logging_setup import get_logger
    logger = get_logger()
    logger.info("", extra={"event": "search_completed", "request_id": rid, ...})
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta

_VN = timezone(timedelta(hours=7))


def _now_iso() -> str:
    return datetime.now(_VN).strftime("%Y-%m-%dT%H:%M:%S+07:00")


class _VnJsonFormatter(logging.Formatter):
    """Minimal JSON formatter — avoids dependency on pythonjsonlogger field ordering."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        base = {
            "timestamp": _now_iso(),
            "level": record.levelname,
        }
        # Merge extra fields (from logger.info("", extra={...}))
        skip = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "thread", "threadName", "exc_info", "exc_text",
            "message",
        }
        for k, v in record.__dict__.items():
            if k not in skip:
                base[k] = v

        if record.getMessage():
            base.setdefault("message", record.getMessage())

        return json.dumps(base, ensure_ascii=False, default=str)


_logger: logging.Logger | None = None


def get_logger(name: str = "da10") -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        _logger = logger
        return logger

    fmt = _VnJsonFormatter()

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    os.makedirs("logs", exist_ok=True)
    fh = logging.FileHandler("logs/da10.jsonl", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    _logger = logger
    return logger
