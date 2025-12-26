"""Structured JSON logging."""

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from app.config import config


class StructuredJsonFormatter(logging.Formatter):
    """Formatter that outputs structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "method"):
            log_data["method"] = record.method
        if hasattr(record, "path"):
            log_data["path"] = record.path
        if hasattr(record, "status"):
            log_data["status"] = record.status
        if hasattr(record, "latency_ms"):
            log_data["latency_ms"] = record.latency_ms
        if hasattr(record, "message_id"):
            log_data["message_id"] = record.message_id
        if hasattr(record, "dup"):
            log_data["dup"] = record.dup
        if hasattr(record, "result"):
            log_data["result"] = record.result

        return json.dumps(log_data)


def setup_logging() -> logging.Logger:
    """Configure structured JSON logging."""
    logger = logging.getLogger("webhook_app")
    logger.setLevel(config.LOG_LEVEL)

    handler = logging.StreamHandler()
    formatter = StructuredJsonFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


logger = setup_logging()


def log_request(
    method: str,
    path: str,
    status: int,
    latency_ms: float,
    request_id: Optional[str] = None,
    **extra: Any,
) -> None:
    """Log HTTP request with structured data."""
    if request_id is None:
        request_id = str(uuid.uuid4())

    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        "",
        0,
        f"{method} {path}",
        (),
        None,
    )
    record.request_id = request_id
    record.method = method
    record.path = path
    record.status = status
    record.latency_ms = int(latency_ms)

    for key, value in extra.items():
        setattr(record, key, value)

    logger.handle(record)


def log_error(
    message: str, request_id: Optional[str] = None, **extra: Any
) -> None:
    """Log error with structured data."""
    if request_id is None:
        request_id = str(uuid.uuid4())

    record = logger.makeRecord(
        logger.name,
        logging.ERROR,
        "",
        0,
        message,
        (),
        None,
    )
    record.request_id = request_id

    for key, value in extra.items():
        setattr(record, key, value)

    logger.handle(record)
