"""Stage 1 CAPTURE: Extract and structure error context from agent failures.

Provides the ErrorContext dataclass and capture_error() function that builds
structured error context from RunnerError, task metadata, and dispatch run data
for consumption by the recovery pipeline.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .error_classifier import detect_error_code, classify_error


@dataclass
class ErrorContext:
    """Structured error context extracted during the CAPTURE stage.

    Contains all failure information needed by the diagnostic agent and
    recovery pipeline. Fields match spec Appendix C.7.
    """
    error_code: str                         # Canonical error code from detect_error_code()
    error_category: str                     # Category from classify_error()
    error_message: str                      # Human-readable error description
    error_pattern: Optional[str]            # Normalized pattern for similarity matching
    task_id: int
    agent_name: str
    task_domain: str
    raw_output: Optional[str]               # Truncated to config.recovery.raw_output_max_chars (default 10000)
    tool_call_log: Optional[list[dict]]     # Tool call history from RunnerError
    stop_reason: Optional[str]              # LLM stop reason
    tokens_used: int
    provider: str                           # Provider name
    model: str                              # Model used
    duration_ms: int                        # Wall clock time
    captured_at: str                        # ISO 8601 timestamp

    @staticmethod
    def now_iso() -> str:
        """Return current UTC time as ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()


def _get_recovery_config(config: Any) -> dict:
    """Extract recovery config section with defaults.

    Args:
        config: Config object (dict or object with .get() or attribute access).

    Returns:
        Dict of recovery configuration values with defaults applied.
    """
    defaults = {
        "raw_output_max_chars": 10000,
    }
    if isinstance(config, dict):
        recovery = config.get("recovery", {})
        if isinstance(recovery, dict):
            for k, v in defaults.items():
                recovery.setdefault(k, v)
            return recovery
    # Fallback: try attribute access
    recovery = getattr(config, "recovery", None)
    if recovery is not None and isinstance(recovery, dict):
        for k, v in defaults.items():
            recovery.setdefault(k, v)
        return recovery
    return defaults


def _truncate(text: Optional[str], max_chars: int) -> Optional[str]:
    """Truncate text to max_chars, returning None if input is None."""
    if text is None:
        return None
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _parse_json_field(value: Any) -> Optional[list]:
    """Parse a JSON TEXT column value into a list, or return as-is if already parsed."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return None


# Regex patterns for normalizing error messages into patterns for similarity matching
_UUID_RE = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
_TASK_ID_RE = re.compile(r'\btask[_\s-]?(?:id)?[_\s:=#]*\d+\b', re.IGNORECASE)
_NUMERIC_ID_RE = re.compile(r'\b(?:id|ID|Id)[_\s:=#]*\d+\b')
_TIMESTAMP_ISO_RE = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?')
_TIMESTAMP_EPOCH_RE = re.compile(r'\b\d{10,13}\b')
_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')


def _normalize_error_pattern(error_message: str) -> str:
    """Normalize an error message into a pattern for similarity matching.

    Strips task-specific IDs, UUIDs, timestamps, and URLs so that similar
    errors match even with different specific values.

    Args:
        error_message: Raw error message string.

    Returns:
        Normalized pattern string with placeholders.
    """
    pattern = error_message
    # Order matters: replace more specific patterns first
    pattern = _URL_RE.sub('<URL>', pattern)
    pattern = _UUID_RE.sub('<UUID>', pattern)
    pattern = _TIMESTAMP_ISO_RE.sub('<TIMESTAMP>', pattern)
    pattern = _TASK_ID_RE.sub('<TASK_ID>', pattern)
    pattern = _NUMERIC_ID_RE.sub('<ID>', pattern)
    pattern = _TIMESTAMP_EPOCH_RE.sub('<EPOCH>', pattern)
    return pattern


def capture_error(
    runner_error: BaseException,
    task_row: dict,
    dispatch_run_row: dict,
    config: Any,
) -> ErrorContext:
    """Extract all failure information and build structured ErrorContext.

    Stage 1 of the recovery pipeline. Reads exception details, agent output,
    tool calls, and task metadata to produce a complete ErrorContext for
    downstream stages (CLASSIFY, DIAGNOSE, STRATEGIZE, etc.).

    Args:
        runner_error: The exception from agent execution (typically AgentRunnerError).
        task_row: Dict from tasks table with id, title, description, domain, etc.
        dispatch_run_row: Dict from dispatch_runs table with raw_output, tool_call_log,
            stop_reason, error_context, tokens_used, provider, model, etc.
        config: Config object (dict or object) with recovery section.

    Returns:
        Populated ErrorContext dataclass.
    """
    recovery_cfg = _get_recovery_config(config)
    max_chars = recovery_cfg.get("raw_output_max_chars", 10000)

    # Extract task metadata
    task_id = task_row.get("id", 0)
    agent_name = dispatch_run_row.get("agent_name", task_row.get("assigned_agent", ""))
    task_domain = task_row.get("domain", "")

    # Extract raw output from dispatch_run_row (populated by agent_runner on failure)
    raw_output = dispatch_run_row.get("raw_output")
    # If not in dispatch_run_row, try to get from runner_error attributes (US-029 adds these)
    if raw_output is None:
        raw_output = getattr(runner_error, "raw_output", None)
    raw_output = _truncate(raw_output, max_chars)

    # Extract tool_call_log
    tool_call_log = _parse_json_field(
        dispatch_run_row.get("tool_call_log") or getattr(runner_error, "tool_call_log", None)
    )

    # Extract stop_reason
    stop_reason = dispatch_run_row.get("stop_reason") or getattr(runner_error, "stop_reason", None)

    # Extract numeric fields
    tokens_used = dispatch_run_row.get("tokens_used", 0) or 0
    provider = dispatch_run_row.get("provider", "")
    model = dispatch_run_row.get("model", "")

    # Calculate duration_ms from dispatch_run timestamps if available
    duration_ms = 0
    started_at = dispatch_run_row.get("started_at")
    completed_at = dispatch_run_row.get("completed_at")
    if started_at and completed_at:
        try:
            start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
            duration_ms = int((end - start).total_seconds() * 1000)
        except (ValueError, TypeError):
            pass

    # Build context for detect_error_code
    # Try to get agent_result if it was partially parsed
    agent_result = getattr(runner_error, "agent_result", None)
    http_status = getattr(runner_error, "http_status", None)
    detection_context: dict[str, Any] = {}
    if tool_call_log:
        detection_context["tool_call_log"] = tool_call_log
    # Pass configured confidence threshold so detect_error_code uses config value
    detection_context["confidence_threshold"] = recovery_cfg.get("min_confidence_score", 0.3)
    # Pass task_domain for domain-specific checks (e.g. INCOMPLETE_RESEARCH)
    if task_domain:
        detection_context["task_domain"] = task_domain

    # Detect and classify error
    error_code = detect_error_code(
        exception=runner_error,
        http_status=http_status,
        agent_result=agent_result,
        context=detection_context,
    )
    error_category_obj = classify_error(error_code)

    return ErrorContext(
        error_code=error_code,
        error_category=error_category_obj.category,
        error_message=str(runner_error),
        error_pattern=_normalize_error_pattern(str(runner_error)),
        task_id=task_id,
        agent_name=agent_name,
        task_domain=task_domain,
        raw_output=raw_output,
        tool_call_log=tool_call_log,
        stop_reason=stop_reason,
        tokens_used=tokens_used,
        provider=provider,
        model=model,
        duration_ms=duration_ms,
        captured_at=ErrorContext.now_iso(),
    )
