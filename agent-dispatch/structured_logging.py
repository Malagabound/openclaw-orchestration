"""
OpenClawd Agent Dispatch System - Structured JSON Logging

US-071: Structured JSON logging to agent-dispatch/logs/supervisor.jsonl
with consistent fields (timestamp, level, component, trace_id, agent_name,
task_id, message, extra) so that logs are machine-readable.

US-031: Recovery-specific event types for observability of the 8-stage
recovery pipeline (capture, classify, diagnose, compensate, strategize,
execute, verify, learn) plus guards and escalation events.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# Path to the JSONL log file (relative to agent-dispatch/)
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE_PATH = os.path.join(_LOG_DIR, "supervisor.jsonl")


# ---------------------------------------------------------------------------
# Recovery event type constants (spec Section 5.7)
# ---------------------------------------------------------------------------
# 8-stage pipeline events
RECOVERY_CAPTURE = "recovery.capture"
RECOVERY_CLASSIFY = "recovery.classify"
RECOVERY_DIAGNOSE_START = "recovery.diagnose.start"
RECOVERY_DIAGNOSE_COMPLETE = "recovery.diagnose.complete"
RECOVERY_COMPENSATE = "recovery.compensate"
RECOVERY_STRATEGY_SELECTED = "recovery.strategy.selected"
RECOVERY_EXECUTE_START = "recovery.execute.start"
RECOVERY_EXECUTE_COMPLETE = "recovery.execute.complete"
RECOVERY_VERIFY = "recovery.verify"
RECOVERY_LEARN = "recovery.learn"

# Escalation & terminal events
RECOVERY_ESCALATE = "recovery.escalate"

# Guard / concurrency events
RECOVERY_CLAIM_SUCCESS = "recovery.claim.success"
RECOVERY_CLAIM_FAILED = "recovery.claim.failed"
RECOVERY_DEFERRED = "recovery.deferred"

# Timeout & budget events
RECOVERY_TIMEOUT = "recovery.timeout"
RECOVERY_HARD_TIMEOUT = "recovery.hard_timeout"
RECOVERY_BUDGET_EXCEEDED = "recovery.budget.exceeded"

# All recovery event types for filtering (used by --recovery log filter)
RECOVERY_EVENT_TYPES = frozenset({
    RECOVERY_CAPTURE,
    RECOVERY_CLASSIFY,
    RECOVERY_DIAGNOSE_START,
    RECOVERY_DIAGNOSE_COMPLETE,
    RECOVERY_COMPENSATE,
    RECOVERY_STRATEGY_SELECTED,
    RECOVERY_EXECUTE_START,
    RECOVERY_EXECUTE_COMPLETE,
    RECOVERY_VERIFY,
    RECOVERY_LEARN,
    RECOVERY_ESCALATE,
    RECOVERY_CLAIM_SUCCESS,
    RECOVERY_CLAIM_FAILED,
    RECOVERY_DEFERRED,
    RECOVERY_TIMEOUT,
    RECOVERY_HARD_TIMEOUT,
    RECOVERY_BUDGET_EXCEEDED,
})


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
            # Promote event_type and duration_ms to top-level for easy filtering
            if "event_type" in extra:
                entry["event_type"] = extra["event_type"]
            if "duration_ms" in extra:
                entry["duration_ms"] = extra["duration_ms"]
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


def is_recovery_event(event_type: Optional[str]) -> bool:
    """Check if an event_type string is a recovery pipeline event."""
    if event_type is None:
        return False
    return event_type.startswith("recovery.")


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
