from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER_NAME = "memory_as_contracts"


class MacJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "mac_event", record.getMessage()),
        }
        payload.update(getattr(record, "mac_fields", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True, default=str)


def configure_logging(
    *,
    path: str | Path | None = None,
    level: str | int | None = None,
) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    resolved_level = level or os.getenv("MAC_LOG_LEVEL", "INFO")
    logger.setLevel(resolved_level)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, "_mac_handler", False):
            logger.removeHandler(handler)
            handler.close()

    configured_path = Path(path or os.getenv("MAC_LOG_PATH", ".mac/mac.log"))
    configured_path = configured_path.expanduser().resolve(strict=False)
    configured_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(configured_path, encoding="utf-8")
    handler.setFormatter(MacJsonFormatter())
    handler.setLevel(resolved_level)
    handler._mac_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    logger.log(
        level,
        event,
        extra={"mac_event": event, "mac_fields": fields},
    )
