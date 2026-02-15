"""Error taxonomy lookup table and classification for the OpenClawd recovery pipeline.

Maps error codes to categories with recovery parameters (max retries, backoff,
diagnosis/compensation requirements). See spec Section 3 for error code definitions.
"""

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Optional


@dataclass(frozen=True)
class ErrorCategory:
    """Recovery parameters for a specific error code.

    Each error code maps to an ErrorCategory that determines how the recovery
    pipeline handles it: how many retries, whether diagnosis is needed, backoff
    timing, and which compensating actions to run.
    """
    category: str                   # transient, execution, logic, structural, configuration, resource
    max_retries: int                # Max recovery attempts for this specific error code
    requires_diagnosis: bool        # Whether Diagnostic Agent should be invoked (Tier 2+)
    requires_compensation: bool     # Whether compensating actions should run before retry
    initial_backoff_seconds: int    # Delay before first retry (0 = immediate)
    backoff_multiplier: float       # Multiplier for subsequent retries
    max_backoff_seconds: int        # Cap on backoff delay
    compensating_action_keys: tuple = ()  # Keys for compensating_actions.py dispatch
                                          # Valid keys: "clear_working_memory", "reset_lease",
                                          # "log_abandoned_output", "defer_to_us051"


# Immutable error taxonomy mapping error codes to recovery parameters.
# See spec Appendix B for the full lookup table.
ERROR_TAXONOMY: dict[str, ErrorCategory] = MappingProxyType({
    # --- Transient errors (infrastructure-level, self-resolving) ---
    "RATE_LIMITED":              ErrorCategory("transient", 5, False, False, 30, 2.0, 300),
    "PROVIDER_5XX":             ErrorCategory("transient", 5, False, False, 30, 2.0, 300),
    "PROVIDER_TIMEOUT":         ErrorCategory("transient", 5, False, False, 30, 2.0, 300),
    "NETWORK_ERROR":            ErrorCategory("transient", 5, False, False, 30, 2.0, 300),
    "SEARCH_API_UNAVAILABLE":   ErrorCategory("transient", 3, False, False, 30, 2.0, 120),
    "DB_LOCKED":                ErrorCategory("transient", 3, False, False, 5, 2.0, 30),
    "TOOL_TIMEOUT":             ErrorCategory("transient", 2, False, False, 10, 2.0, 60),

    # --- Execution errors (agent ran, output is wrong) ---
    "RESULT_SCHEMA_INVALID":    ErrorCategory("execution", 3, True, False, 0, 1, 0),
    "RESULT_PARSE_FAILED":      ErrorCategory("execution", 3, True, False, 0, 1, 0),
    "DELIVERABLE_EMPTY":        ErrorCategory("execution", 3, True, False, 0, 1, 0),
    "DELIVERABLE_TRUNCATED":    ErrorCategory("execution", 2, True, False, 0, 1, 0),
    "STATUS_INVALID":           ErrorCategory("execution", 3, False, False, 0, 1, 0),
    "CONFIDENCE_TOO_LOW":       ErrorCategory("execution", 2, True, False, 0, 1, 0),
    "TOOL_RESULT_MALFORMED":    ErrorCategory("execution", 2, True, False, 0, 1, 0),
    "AGENT_SELF_REPORTED_FAILURE": ErrorCategory("execution", 2, True, False, 0, 1, 0),

    # --- Logic errors (agent completed, output is semantically wrong) ---
    "VALIDATION_REJECTED":      ErrorCategory("logic", 2, True, False, 0, 1, 0),
    "TASK_MISMATCH":            ErrorCategory("logic", 2, True, False, 0, 1, 0),
    "INCOMPLETE_RESEARCH":      ErrorCategory("logic", 2, True, False, 0, 1, 0),
    "STALE_DATA":               ErrorCategory("logic", 1, True, False, 0, 1, 0),
    "CONTRADICTORY_OUTPUT":     ErrorCategory("logic", 2, True, True, 0, 1, 0, ("clear_working_memory",)),

    # --- Structural errors (workflow is stuck) ---
    "TOOL_LOOP_DETECTED":       ErrorCategory("structural", 2, True, True, 0, 1, 0, ("clear_working_memory", "log_abandoned_output")),
    "TOOL_DEPTH_EXCEEDED":      ErrorCategory("structural", 2, True, True, 0, 1, 0, ("clear_working_memory", "log_abandoned_output")),
    "STUCK_TASK":               ErrorCategory("structural", 2, True, True, 0, 1, 0, ("reset_lease", "log_abandoned_output")),
    "DEPENDENCY_DEADLOCK":      ErrorCategory("structural", 0, False, False, 0, 1, 0),
    "COMPLETION_SEQUENCE_STUCK": ErrorCategory("structural", 3, False, True, 5, 2.0, 30, ("defer_to_us051",)),

    # --- Configuration errors (execution impossible without environmental changes) ---
    "API_KEY_MISSING":          ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "API_KEY_INVALID":          ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "PROVIDER_NOT_CONFIGURED":  ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "TOOL_NOT_AVAILABLE":       ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "AGENT_NOT_FOUND":          ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "DB_SCHEMA_INCOMPATIBLE":   ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "SEARCH_API_NO_KEYS":       ErrorCategory("configuration", 0, False, False, 0, 1, 0),

    # --- Resource errors (budget/capacity limits) ---
    "GLOBAL_BUDGET_EXCEEDED":   ErrorCategory("resource", 0, False, False, 0, 1, 0),
    "AGENT_BUDGET_EXCEEDED":    ErrorCategory("resource", 0, False, False, 0, 1, 0),
    "CONTEXT_OVERFLOW":         ErrorCategory("resource", 1, False, False, 0, 1, 0),
    "MAX_TOKENS_EXCEEDED":      ErrorCategory("resource", 1, False, False, 0, 1, 0),
    "DISK_SPACE_LOW":           ErrorCategory("resource", 0, False, False, 0, 1, 0),
})

# Default for unknown errors: treat as execution error with diagnosis
DEFAULT_CATEGORY = ErrorCategory("unknown", 1, True, False, 0, 1, 0)

# Alias for the unknown default (used by classify_error for unknown codes)
UNKNOWN_ERROR_CATEGORY = DEFAULT_CATEGORY


def detect_error_code(
    exception: Optional[BaseException] = None,
    http_status: Optional[int] = None,
    agent_result: Optional[Any] = None,
    context: Optional[dict] = None,
) -> str:
    """Map raw exceptions and context to canonical error codes.

    Inspects exception types, HTTP status codes, AgentResult fields, and
    additional context to produce a deterministic error code string from
    ERROR_TAXONOMY.

    Args:
        exception: The exception that triggered the failure (if any).
        http_status: HTTP status code from provider response (if any).
        agent_result: Parsed AgentResult dataclass (if agent produced output).
        context: Additional context dict with keys like 'tool_loop_detected',
                 'raw_output', 'confidence_threshold', etc.

    Returns:
        Canonical error code string from ERROR_TAXONOMY.
    """
    if context is None:
        context = {}

    # --- Exception-based detection ---
    if exception is not None:
        exc_type = type(exception).__name__
        exc_module = type(exception).__module__ or ""
        exc_msg = str(exception).lower()

        # anthropic.RateLimitError (or any rate limit exception)
        if exc_type == "RateLimitError" and "anthropic" in exc_module:
            return "RATE_LIMITED"

        # requests.Timeout or urllib3 timeout
        if exc_type in ("Timeout", "ConnectTimeout", "ReadTimeout"):
            return "PROVIDER_TIMEOUT"

        # requests.ConnectionError / network errors
        if exc_type == "ConnectionError" or "connection" in exc_type.lower():
            return "NETWORK_ERROR"

        # json.JSONDecodeError on agent output parsing
        if isinstance(exception, (ValueError,)) and exc_type == "JSONDecodeError":
            return "RESULT_PARSE_FAILED"

        # AgentRunnerError with specific messages
        if exc_type == "AgentRunnerError":
            if "no <agent-result> block" in exc_msg:
                return "RESULT_PARSE_FAILED"
            if "invalid json in <agent-result>" in exc_msg:
                return "RESULT_PARSE_FAILED"
            if "missing required fields" in exc_msg:
                return "RESULT_SCHEMA_INVALID"
            if "loop detected" in exc_msg:
                return "TOOL_LOOP_DETECTED"
            if "max iterations" in exc_msg:
                return "STUCK_TASK"
            if "provider call failed" in exc_msg:
                # Try to extract more specific info from the cause
                cause = exception.__cause__
                if cause is not None:
                    return detect_error_code(exception=cause, http_status=http_status,
                                             agent_result=agent_result, context=context)
                return "PROVIDER_5XX"

        # HTTP 429 (rate limit)
        if "rate" in exc_msg and "limit" in exc_msg:
            return "RATE_LIMITED"

        # HTTP 5xx from provider
        if "500" in exc_msg or "502" in exc_msg or "503" in exc_msg or "504" in exc_msg:
            return "PROVIDER_5XX"

        # Budget exceeded
        if "budget" in exc_msg and "exceeded" in exc_msg:
            if "global" in exc_msg or "daily" in exc_msg:
                return "GLOBAL_BUDGET_EXCEEDED"
            return "AGENT_BUDGET_EXCEEDED"

        # Context overflow / max tokens
        if "context" in exc_msg and ("overflow" in exc_msg or "too long" in exc_msg):
            return "CONTEXT_OVERFLOW"
        if "max_tokens" in exc_msg or "maximum" in exc_msg and "token" in exc_msg:
            return "MAX_TOKENS_EXCEEDED"

    # --- HTTP status code detection ---
    if http_status is not None:
        if http_status == 429:
            return "RATE_LIMITED"
        if http_status >= 500:
            return "PROVIDER_5XX"

    # --- Context-based detection ---
    if context.get("tool_loop_detected"):
        return "TOOL_LOOP_DETECTED"

    # --- AgentResult-based detection (post-completion checks) ---
    if agent_result is not None:
        status = getattr(agent_result, "status", None)
        confidence_score = getattr(agent_result, "confidence_score", None)
        deliverable_content = getattr(agent_result, "deliverable_content", None)

        # Agent self-reported failure
        if status == "failed":
            return "AGENT_SELF_REPORTED_FAILURE"

        # Confidence too low (only for completed results)
        if status == "completed" and confidence_score is not None:
            threshold = context.get("confidence_threshold", 0.3)
            if confidence_score < threshold:
                return "CONFIDENCE_TOO_LOW"

        # Empty deliverable
        if status == "completed" and (deliverable_content is None or
                                       str(deliverable_content).strip() == ""):
            return "DELIVERABLE_EMPTY"

        # Incomplete research: research tasks with fewer than 3 distinct URLs
        if status == "completed" and deliverable_content is not None:
            task_domain = context.get("task_domain")
            if task_domain == "research":
                urls = set(re.findall(r'https?://[^\s<>"\')\]]+', str(deliverable_content)))
                if len(urls) < 3:
                    return "INCOMPLETE_RESEARCH"

    # --- Fallback ---
    return "UNKNOWN_ERROR"


def classify_error(error_code: str) -> ErrorCategory:
    """Look up error code in ERROR_TAXONOMY and return its recovery parameters.

    Args:
        error_code: Canonical error code string (e.g. 'RATE_LIMITED').

    Returns:
        ErrorCategory with recovery parameters. Returns DEFAULT_CATEGORY
        for unknown error codes (category='unknown', max_retries=1,
        requires_diagnosis=True).
    """
    return ERROR_TAXONOMY.get(error_code, DEFAULT_CATEGORY)
