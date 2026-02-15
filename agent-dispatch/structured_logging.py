"""
OpenClawd Agent Dispatch System - Structured JSON Logging

US-071: Structured JSON logging to agent-dispatch/logs/supervisor.jsonl
with consistent fields (timestamp, level, component, trace_id, agent_name,
task_id, message, extra) so that logs are machine-readable.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# Path to the JSONL log file (relative to agent-dispatch/)
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE_PATH = os.path.join(_LOG_DIR, "supervisor.jsonl")


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects with standard fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }

        # Dispatch-related fields (only included when present)
        for field in ("trace_id", "agent_name", "task_id"):
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value

        # Extra structured data
        extra = getattr(record, "extra_data", None)
        if extra is not None:
            entry["extra"] = extra

        return json.dumps(entry, default=str)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the root 'agent_dispatch' logger with JSON file handler.

    The file handler appends to supervisor.jsonl (does not truncate on restart).
    Calling this function multiple times is safe - it will not add duplicate handlers.

    Args:
        level: Logging level (default INFO).

    Returns:
        The configured 'agent_dispatch' logger.
    """
    logger = logging.getLogger("agent_dispatch")
    logger.setLevel(level)

    # Prevent adding duplicate handlers on repeated calls
    if any(
        isinstance(h, logging.FileHandler) and getattr(h, "_jsonl_handler", False)
        for h in logger.handlers
    ):
        return logger

    # Ensure logs directory exists
    os.makedirs(_LOG_DIR, exist_ok=True)

    handler = logging.FileHandler(LOG_FILE_PATH, mode="a", encoding="utf-8")
    handler._jsonl_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(JSONFormatter())
    handler.setLevel(level)

    logger.addHandler(handler)

    return logger


def get_logger(component: str) -> logging.Logger:
    """Get a child logger for a specific component.

    Args:
        component: Component name (e.g. 'supervisor', 'agent_runner').

    Returns:
        A child logger under 'agent_dispatch.<component>'.
    """
    return logging.getLogger(f"agent_dispatch.{component}")


def log_dispatch_event(
    logger: logging.Logger,
    level: int,
    message: str,
    trace_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    task_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a dispatch-related event with standard context fields.

    Args:
        logger: The logger to use.
        level: Logging level (e.g. logging.INFO).
        message: Log message.
        trace_id: Dispatch trace ID (UUID).
        agent_name: Name of the agent.
        task_id: Task identifier.
        extra: Additional structured data dict.
    """
    kwargs: Dict[str, Any] = {}
    if trace_id is not None:
        kwargs["trace_id"] = trace_id
    if agent_name is not None:
        kwargs["agent_name"] = agent_name
    if task_id is not None:
        kwargs["task_id"] = task_id
    if extra is not None:
        kwargs["extra_data"] = extra

    logger.log(level, message, extra=kwargs)
