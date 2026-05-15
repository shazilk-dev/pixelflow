import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import override

from core.config import settings

_LOG_FILE = "/app/logs/pipeline.log"


class _JSONFormatter(logging.Formatter):
    """Formats every log record as a single-line JSON object."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "worker_id": settings.WORKER_ID or "api",
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _build_handlers() -> list[logging.Handler]:
    formatter = _JSONFormatter()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [stdout_handler]

    try:
        os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
        file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except OSError:
        # Running outside Docker — /app/logs/ may not exist; stdout only.
        pass

    return handlers


_handlers = _build_handlers()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        for h in _handlers:
            logger.addHandler(h)
        logger.propagate = False
    return logger
