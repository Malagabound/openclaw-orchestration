"""Recovery pipeline orchestration for OpenClawd self-healing system.

Defines the core dataclasses used throughout the recovery pipeline:
- PreviousAttemptSummary: Summary of a prior recovery attempt (spec Appendix C.4)
- RecoveryContext: Injected into agent prompts on recovery retries (spec Appendix C.1)
- RecoveryOutcome: Final result of the recovery pipeline (spec Appendix C.9, added by US-021)
- handle_failure(): Orchestrator that runs all 8 recovery stages (US-022)
"""

import datetime
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PreviousAttemptSummary:
    """Summary of a prior recovery attempt, included in RecoveryContext for the agent.

    Fields match spec Appendix C.4.
    """
    attempt_number: int                     # Which attempt this was
    strategy_used: str                      # Strategy name from ladder
    error_code: str                         # Error that occurred
    error_message: str                      # Brief error description (max 200 chars)
    diagnostic_summary: Optional[str]       # One-line diagnostic root cause, or None
    tools_used: list[str] = field(default_factory=list)  # Tool names called during this attempt
    duration_ms: int = 0                    # How long the attempt took

    def __post_init__(self) -> None:
        """Enforce error_message truncation to 200 chars."""
        if self.error_message and len(self.error_message) > 200:
            self.error_message = self.error_message[:200]


@dataclass
class RecoveryContext:
    """Injected into agent prompts on recovery retries via agent_prompts.py.

    Fields match spec Appendix C.1. Used by agent_prompts.build_prompt() to
    inject recovery guidance into the agent's prompt.
    """
    attempt_number: int                     # Current recovery attempt (1-indexed)
    total_max_attempts: int                 # Maximum attempts allowed (from ErrorCategory.max_retries)
    error_code: str                         # Error code from Section 3 taxonomy
    error_message: str                      # Human-readable error description
    error_category: str                     # transient, execution, logic, structural, configuration, resource
    previous_raw_output: Optional[str]      # First 500 chars of previous attempt's raw_output (None on attempt 1)
    tool_call_summary: Optional[str]        # "{count} tool calls: {tool1} x{n}, {tool2} x{m}" (None if no tools)
    diagnostic_analysis: Optional[str]      # DiagnosticOutput.root_cause (None if no diagnosis ran)
    specific_fix: Optional[str]             # DiagnosticOutput.specific_fix (None if no diagnosis ran)
    strategy_name: str                      # Strategy from ladder: fix_specific, rewrite_with_diagnosis, simplify, decompose, escalate
    strategy_description: str               # Human-readable strategy instructions
    constraints: list[str] = field(default_factory=list)  # List of constraints for retry
    previous_attempts: list[PreviousAttemptSummary] = field(default_factory=list)  # Prior attempt summaries
    similar_past_fixes: list[str] = field(default_factory=list)  # Resolution summaries from failure_memory, max 3


@dataclass
class RecoveryOutcome:
    """Final result of the recovery pipeline, returned by handle_failure().

    Fields match spec Appendix C.9. Used by agent_supervisor to determine
    final task disposition after recovery completes.
    """
    task_id: int                            # Task that was recovered
    success: bool                           # Whether recovery resolved the original error
    final_status: str                       # 'completed', 'failed', or 'dispatch_failed'
    attempts_used: int                      # Number of recovery attempts executed
    winning_strategy: Optional[str]         # Strategy name that succeeded, or None if all failed
    escalation_reason: Optional[str]        # Why recovery gave up (None if success=True)
    total_duration_ms: int                  # Total wall-clock time for entire recovery pipeline
    total_cost_usd: float                   # Sum of cost_estimate across all recovery dispatch_runs
    error_code: str                         # Original error code that triggered recovery
    trace_id: str                           # UUID correlating all recovery_events for this pipeline run


logger = logging.getLogger(__name__)

# ── Escalation rate limiting state (in-memory, per-process) ────
# Tracks recent escalation timestamps for global hourly limit and per-task cooldown.
_escalation_timestamps: list[float] = []  # monotonic timestamps of all escalations
_task_escalation_times: dict[int, float] = {}  # task_id -> last escalation monotonic time

# ── Systemic failure alert rate limiting (in-memory, per-process) ────
# Tracks last alert time per error_code to limit to 1 alert per error_code per hour.
_systemic_alert_times: dict[str, float] = {}  # error_code -> last alert monotonic time


def _check_escalation_rate_limit(
    task_id: int,
    config: Any,
) -> bool:
    """Check if escalation notification is allowed by rate limits.

    Returns True if notification should be sent, False if rate-limited.
    Enforces:
      - max_escalations_per_hour (default 5): global limit across all tasks
      - escalation_cooldown_seconds (default 300): per-task cooldown
    """
    recovery_config = (
        config.get("recovery", {})
        if isinstance(config, dict)
        else getattr(config, "recovery", {}) or {}
    )
    if not isinstance(recovery_config, dict):
        recovery_config = {}

    max_per_hour = recovery_config.get("max_escalations_per_hour", 5)
    cooldown_seconds = recovery_config.get("escalation_cooldown_seconds", 300)

    now = time.monotonic()

    # Check per-task cooldown
    last_task_time = _task_escalation_times.get(task_id)
    if last_task_time is not None and (now - last_task_time) < cooldown_seconds:
        return False

    # Check global hourly limit — prune entries older than 1 hour
    one_hour_ago = now - 3600
    _escalation_timestamps[:] = [t for t in _escalation_timestamps if t > one_hour_ago]
    if len(_escalation_timestamps) >= max_per_hour:
        return False

    return True


def _record_escalation(task_id: int) -> None:
    """Record that an escalation notification was sent."""
    now = time.monotonic()
    _escalation_timestamps.append(now)
    _task_escalation_times[task_id] = now


def _send_escalation_notification(
    task_id: int,
    task_row: dict,
    error_code: str,
    diagnostic_summary: Optional[str],
    attempts_used: int,
    escalation_reason: Optional[str],
    trace_id: str,
    config: Any,
    slog: Any,
) -> None:
    """Send urgent notification for terminal recovery failure.

    Respects max_escalations_per_hour and per-task cooldown limits.
    Notification failures are logged but never raise exceptions.
    """
    from ..notification_delivery import deliver_notification

    # Check rate limits
    if not _check_escalation_rate_limit(task_id, config):
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.escalate.rate_limited",
            f"Escalation notification suppressed for task {task_id} (rate limited)",
            level=logging.WARNING,
            error_code=error_code,
        )
        return

    task_description = task_row.get("description", task_row.get("title", f"Task {task_id}"))
    task_title = task_row.get("title", f"Task {task_id}")

    notification_dict = {
        "title": f"Recovery Escalation: {error_code}",
        "message": (
            f"Task {task_id} ({task_title}) failed permanently after "
            f"{attempts_used} recovery attempts.\n\n"
            f"Error code: {error_code}\n"
            f"Diagnostic summary: {diagnostic_summary or 'No diagnosis available'}\n"
            f"Escalation reason: {escalation_reason or 'Unknown'}\n"
            f"Task description: {task_description[:500]}"
        ),
        "task_id": task_id,
        "error_code": error_code,
        "diagnostic_summary": diagnostic_summary,
        "attempts_used": attempts_used,
        "escalation_reason": escalation_reason,
        "trace_id": trace_id,
    }

    try:
        config_dict = config if isinstance(config, dict) else getattr(config, "_data", config)
        if not isinstance(config_dict, dict):
            config_dict = {}
        deliver_notification(notification_dict, "urgent", config_dict)
        _record_escalation(task_id)
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.escalate.notified",
            f"Sent urgent escalation notification for task {task_id}: {error_code}",
            error_code=error_code,
            escalation_reason=escalation_reason,
        )
    except Exception as exc:
        logger.warning(
            "Failed to send escalation notification for task %d: %s",
            task_id, exc,
        )


def _send_decomposition_notification(
    task_id: int,
    task_row: dict,
    error_code: str,
    diagnostic_summary: Optional[str],
    attempts_used: int,
    strategy: Any,
    trace_id: str,
    config: Any,
    slog: Any,
) -> None:
    """Send high-urgency notification with decomposition guidance for Tier 4.

    Includes decomposition suggestions from the diagnostic agent and
    recommends operator use 'openclawd pipeline create' to split the task.
    Respects the same escalation rate limits as _send_escalation_notification.
    Notification failures are logged but never raise exceptions.
    """
    from ..notification_delivery import deliver_notification

    # Check rate limits (shared with escalation)
    if not _check_escalation_rate_limit(task_id, config):
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.decompose.rate_limited",
            f"Decomposition notification suppressed for task {task_id} (rate limited)",
            level=logging.WARNING,
            error_code=error_code,
        )
        return

    task_title = task_row.get("title", f"Task {task_id}")
    task_description = task_row.get("description", task_row.get("title", f"Task {task_id}"))

    # Extract decomposition suggestions from strategy prompt_modifications
    decomposition_suggestion = strategy.prompt_modifications.get("decomposition_suggestion", "")
    decomposition_root_cause = strategy.prompt_modifications.get("decomposition_root_cause", "")

    message_parts = [
        f"Task {task_id} ({task_title}) requires manual decomposition after "
        f"{attempts_used} failed recovery attempts.",
        "",
        f"Error code: {error_code}",
        f"Diagnostic summary: {diagnostic_summary or 'No diagnosis available'}",
    ]

    if decomposition_root_cause:
        message_parts.append(f"Root cause: {decomposition_root_cause}")

    if decomposition_suggestion:
        message_parts.append("")
        message_parts.append(f"Decomposition guidance: {decomposition_suggestion}")

    message_parts.append("")
    message_parts.append(
        "Recommended action: Use 'openclawd pipeline create' to split this "
        "task into smaller sub-tasks that can be dispatched individually."
    )
    message_parts.append(f"Task description: {task_description[:500]}")

    notification_dict = {
        "title": f"Decomposition Required: {error_code}",
        "message": "\n".join(message_parts),
        "task_id": task_id,
        "error_code": error_code,
        "diagnostic_summary": diagnostic_summary,
        "decomposition_suggestion": decomposition_suggestion,
        "attempts_used": attempts_used,
        "trace_id": trace_id,
    }

    try:
        config_dict = config if isinstance(config, dict) else getattr(config, "_data", config)
        if not isinstance(config_dict, dict):
            config_dict = {}
        deliver_notification(notification_dict, "high", config_dict)
        _record_escalation(task_id)
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.decompose.notified",
            f"Sent decomposition notification for task {task_id}: {error_code}",
            error_code=error_code,
            decomposition_suggestion=decomposition_suggestion or "none",
        )
    except Exception as exc:
        logger.warning(
            "Failed to send decomposition notification for task %d: %s",
            task_id, exc,
        )


def _check_systemic_and_alert(
    task_id: int,
    error_code: str,
    trace_id: str,
    config: Any,
    slog: Any,
) -> None:
    """Check for systemic failure pattern and send alert if detected.

    After each failure_memory record, checks if the same error_code is
    affecting multiple distinct tasks within the configured time window.
    Rate-limited to max 1 alert per error_code per hour.

    Args:
        task_id: Task that just failed.
        error_code: The error code to check for systemic pattern.
        trace_id: Recovery pipeline trace ID for event correlation.
        config: Config dict or object.
        slog: Structured logger instance.
    """
    from . import failure_memory
    from ..notification_delivery import deliver_notification

    # Read config for systemic detection thresholds
    recovery_config = (
        config.get("recovery", {})
        if isinstance(config, dict)
        else getattr(config, "recovery", {}) or {}
    )
    if not isinstance(recovery_config, dict):
        recovery_config = {}

    window_minutes = recovery_config.get("systemic_failure_window_minutes", 10)
    threshold_count = recovery_config.get("systemic_failure_threshold_count", 3)

    try:
        is_systemic = failure_memory.detect_systemic_pattern(
            error_code=error_code,
            window_minutes=window_minutes,
            threshold_count=threshold_count,
        )
    except Exception:
        return  # fail silently — systemic detection is best-effort

    if not is_systemic:
        return

    # Rate limit: max 1 alert per error_code per hour
    now = time.monotonic()
    last_alert_time = _systemic_alert_times.get(error_code)
    if last_alert_time is not None and (now - last_alert_time) < 3600:
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.systemic_alert.rate_limited",
            f"Systemic failure alert suppressed for {error_code} (rate limited, max 1/hour)",
            level=logging.DEBUG,
            error_code=error_code,
        )
        return

    # Log systemic failure detection event
    _log_recovery_event(
        slog, trace_id, task_id, "recovery.systemic_failure_detected",
        f"Systemic failure pattern detected: {error_code} affecting >= "
        f"{threshold_count} distinct tasks in last {window_minutes} minutes",
        level=logging.WARNING,
        error_code=error_code,
        threshold_count=threshold_count,
        window_minutes=window_minutes,
    )

    # Send urgent notification
    notification_dict = {
        "title": f"Systemic Failure Detected: {error_code}",
        "message": (
            f"Systemic failure pattern detected: error code {error_code} "
            f"is affecting {threshold_count}+ distinct tasks within the last "
            f"{window_minutes} minutes.\n\n"
            f"Latest affected task: {task_id}\n\n"
            f"Recommended actions:\n"
            f"- Check provider health: openclawd doctor\n"
            f"- Review API keys and configuration\n"
            f"- Check database connectivity and schema\n"
            f"- Review recovery logs: openclawd logs --recovery\n"
            f"- Consider pausing dispatch until root cause identified"
        ),
        "task_id": task_id,
        "error_code": error_code,
        "threshold_count": threshold_count,
        "window_minutes": window_minutes,
        "trace_id": trace_id,
    }

    try:
        config_dict = config if isinstance(config, dict) else getattr(config, "_data", config)
        if not isinstance(config_dict, dict):
            config_dict = {}
        deliver_notification(notification_dict, "urgent", config_dict)
        _systemic_alert_times[error_code] = now
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.systemic_alert.notified",
            f"Sent systemic failure alert for {error_code}",
            error_code=error_code,
        )
    except Exception as exc:
        logger.warning(
            "Failed to send systemic failure notification for %s: %s",
            error_code, exc,
        )


def _log_recovery_event(
    slog: logging.Logger,
    trace_id: str,
    task_id: int,
    event_type: str,
    message: str,
    level: int = logging.INFO,
    **extra_fields: Any,
) -> None:
    """Log a recovery pipeline event with standard fields."""
    from ..structured_logging import log_dispatch_event

    log_dispatch_event(
        slog,
        level,
        message,
        trace_id=trace_id,
        task_id=str(task_id),
        extra={"event_type": event_type, **extra_fields},
    )


def _build_tool_call_summary(tool_call_log: Optional[list]) -> Optional[str]:
    """Summarize tool calls as '{count} tool calls: {tool1} x{n}, ...'."""
    if not tool_call_log:
        return None
    counts: dict[str, int] = {}
    for tc in tool_call_log:
        name = tc.get("name", tc.get("tool", "unknown")) if isinstance(tc, dict) else "unknown"
        counts[name] = counts.get(name, 0) + 1
    total = sum(counts.values())
    parts = [f"{name} x{count}" for name, count in counts.items()]
    return f"{total} tool calls: {', '.join(parts)}"


def handle_failure(
    task_id: int,
    runner_error: BaseException,
    task_row: dict,
    dispatch_run_row: dict,
    config: Any,
    dispatch_db: Any,
) -> RecoveryOutcome:
    """Orchestrate all 8 recovery stages for a failed task.

    Stages:
      1. CAPTURE - Extract structured error context
      2. CLASSIFY - Look up error category and recovery parameters
      3. DIAGNOSE - LLM-based root cause analysis (if required)
      4. COMPENSATE - Clean up failed attempt artifacts (if required)
      5. STRATEGIZE - Select recovery strategy from ladder (or playbook)
      6. EXECUTE - Re-run agent with recovery context
      7. VERIFY - Check if recovery succeeded
      8. LEARN - Record outcome in failure_memory

    Args:
        task_id: The task ID that failed.
        runner_error: The exception from agent execution.
        task_row: Dict from tasks table.
        dispatch_run_row: Dict from dispatch_runs table.
        config: Config dict or object.
        dispatch_db: dispatch_db module reference for database operations.

    Returns:
        RecoveryOutcome with success indicator and final disposition.
    """
    from ..structured_logging import get_logger
    from .error_capture import capture_error
    from .error_classifier import classify_error
    from .diagnostic_agent import diagnose_failure, DiagnosticInput, DiagnosticOutput
    from .compensating_actions import compensate
    from .strategy_selector import select_strategy
    from .recovery_executor import execute as recovery_execute, RecoveryBudgetExceeded, RecoveryTimeoutError, ProviderHealthDeferred
    from . import failure_memory

    slog = get_logger("recovery_pipeline")
    trace_id = str(uuid.uuid4())
    pipeline_start = time.monotonic()
    attempts_used = 0
    total_cost_usd = 0.0
    previous_attempts: list[PreviousAttemptSummary] = []
    diagnostic_output: Optional[DiagnosticOutput] = None

    # ── Concurrency guard: max concurrent recoveries ──────────────
    # Check how many tasks are already in 'recovering' state. If at
    # or over the limit, defer this recovery by setting next_retry_at
    # on the latest dispatch_run so the next poll cycle retries.
    recovery_config = config.get("recovery", {}) if isinstance(config, dict) else getattr(config, "recovery", {}) or {}
    max_concurrent = recovery_config.get("max_concurrent_recoveries", 3) if isinstance(recovery_config, dict) else getattr(recovery_config, "max_concurrent_recoveries", 3)
    try:
        reader_conn = dispatch_db.get_reader_connection()
        row = reader_conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE dispatch_status = 'recovering'"
        ).fetchone()
        recovering_count = row[0] if row else 0
    except Exception:
        recovering_count = 0  # fail open — allow recovery if query fails

    if recovering_count >= max_concurrent:
        # Defer: set next_retry_at on the latest dispatch_run for this task
        defer_seconds = 60
        defer_until = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=defer_seconds)
        ).isoformat()
        try:
            defer_conn = dispatch_db.get_writer_connection()
            try:
                defer_conn.execute(
                    "UPDATE dispatch_runs SET next_retry_at = ? "
                    "WHERE task_id = ? AND id = ("
                    "  SELECT MAX(id) FROM dispatch_runs WHERE task_id = ?"
                    ")",
                    (defer_until, task_id, task_id),
                )
                defer_conn.commit()
            except sqlite3.Error:
                try:
                    defer_conn.rollback()
                except sqlite3.Error:
                    pass
            finally:
                defer_conn.close()
        except Exception:
            pass  # best effort

        _log_recovery_event(
            slog, trace_id, task_id, "recovery.deferred",
            f"Recovery deferred: {recovering_count} concurrent recoveries "
            f"(limit {max_concurrent}), retry in {defer_seconds}s",
            level=logging.WARNING,
            recovering_count=recovering_count,
            max_concurrent=max_concurrent,
            defer_seconds=defer_seconds,
        )
        return RecoveryOutcome(
            task_id=task_id,
            success=False,
            final_status="failed",
            attempts_used=0,
            winning_strategy=None,
            escalation_reason="concurrency_limit",
            total_duration_ms=_elapsed_ms(pipeline_start),
            total_cost_usd=0.0,
            error_code="UNKNOWN_ERROR",
            trace_id=trace_id,
        )

    # ── Atomic claim: failed → recovering ─────────────────────────
    # Prevents duplicate recovery by atomically transitioning
    # dispatch_status from 'failed' to 'recovering'. If rowcount=0,
    # another process already claimed this task for recovery.
    try:
        claim_conn = dispatch_db.get_writer_connection()
        try:
            cursor = claim_conn.execute(
                "UPDATE tasks SET dispatch_status = 'recovering' "
                "WHERE id = ? AND dispatch_status = 'failed'",
                (task_id,),
            )
            claim_conn.commit()
            claimed = cursor.rowcount > 0
        except sqlite3.Error:
            try:
                claim_conn.rollback()
            except sqlite3.Error:
                pass
            claimed = False
        finally:
            claim_conn.close()
    except Exception:
        claimed = False

    if not claimed:
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.claim.failed",
            f"Failed to claim task {task_id} for recovery "
            f"(dispatch_status is not 'failed', already recovering or claimed)",
            level=logging.WARNING,
        )
        return RecoveryOutcome(
            task_id=task_id,
            success=False,
            final_status="failed",
            attempts_used=0,
            winning_strategy=None,
            escalation_reason="duplicate_recovery",
            total_duration_ms=_elapsed_ms(pipeline_start),
            total_cost_usd=0.0,
            error_code="UNKNOWN_ERROR",
            trace_id=trace_id,
        )

    _log_recovery_event(
        slog, trace_id, task_id, "recovery.claim.success",
        f"Claimed task {task_id} for recovery (failed → recovering)",
    )

    # ── Stage 1: CAPTURE ───────────────────────────────────────────
    error_context = capture_error(runner_error, task_row, dispatch_run_row, config)
    _log_recovery_event(
        slog, trace_id, task_id, "recovery.capture",
        f"Captured error context: {error_context.error_code} ({error_context.error_category})",
        error_code=error_context.error_code,
        error_category=error_context.error_category,
    )

    # ── Stage 2: CLASSIFY ──────────────────────────────────────────
    error_category = classify_error(error_context.error_code)
    _log_recovery_event(
        slog, trace_id, task_id, "recovery.classify",
        f"Classified error: category={error_category.category}, "
        f"max_retries={error_category.max_retries}, "
        f"requires_diagnosis={error_category.requires_diagnosis}",
        error_code=error_context.error_code,
        category=error_category.category,
        max_retries=error_category.max_retries,
    )

    # No retries allowed — escalate immediately
    if error_category.max_retries == 0:
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.escalate",
            f"No retries allowed for {error_context.error_code}, escalating immediately",
            level=logging.WARNING,
            error_code=error_context.error_code,
        )
        # Stage 8: LEARN (record failed attempt)
        failure_memory.record_attempt(
            task_id=task_id,
            error_code=error_context.error_code,
            agent_name=error_context.agent_name,
            diagnostic_summary="No retries allowed for this error category",
            resolution_summary=f"Escalated immediately: {error_context.error_code}",
            success=False,
            recovery_tier=0,
            task_domain=error_context.task_domain,
            error_pattern=error_context.error_pattern,
        )
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.learn",
            f"Recorded escalation for {error_context.error_code}",
        )
        _check_systemic_and_alert(task_id, error_context.error_code, trace_id, config, slog)
        no_retry_reason = (
            f"No retries allowed for error code {error_context.error_code} "
            f"(category: {error_category.category})"
        )
        _send_escalation_notification(
            task_id=task_id,
            task_row=task_row,
            error_code=error_context.error_code,
            diagnostic_summary="No retries allowed for this error category",
            attempts_used=0,
            escalation_reason=no_retry_reason,
            trace_id=trace_id,
            config=config,
            slog=slog,
        )
        return RecoveryOutcome(
            task_id=task_id,
            success=False,
            final_status="dispatch_failed",
            attempts_used=0,
            winning_strategy=None,
            escalation_reason=no_retry_reason,
            total_duration_ms=_elapsed_ms(pipeline_start),
            total_cost_usd=0.0,
            error_code=error_context.error_code,
            trace_id=trace_id,
        )

    max_attempts = error_category.max_retries

    # ── Stage 3: DIAGNOSE (if required) ────────────────────────────
    if error_category.requires_diagnosis:
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.diagnose.start",
            f"Starting diagnostic analysis for {error_context.error_code}",
            error_code=error_context.error_code,
        )
        diag_start = time.monotonic()

        # Query similar fixes for diagnostic context
        similar_fixes = failure_memory.find_similar_fixes(
            error_code=error_context.error_code,
            agent_name=error_context.agent_name,
            task_domain=error_context.task_domain,
        )

        diagnostic_input = DiagnosticInput(
            task_id=task_id,
            task_title=task_row.get("title", ""),
            task_description=task_row.get("description", ""),
            task_domain=error_context.task_domain,
            assigned_agent=error_context.agent_name,
            error_code=error_context.error_code,
            error_message=error_context.error_message,
            error_category=error_context.error_category,
            raw_agent_output=error_context.raw_output,
            tool_call_log=error_context.tool_call_log,
            stop_reason=error_context.stop_reason,
            tokens_used=error_context.tokens_used,
            attempt_number=1,
            previous_attempts=[],
            similar_past_fixes=similar_fixes,
        )
        diagnostic_output = diagnose_failure(diagnostic_input, config)
        diag_duration = _elapsed_ms(diag_start)

        _log_recovery_event(
            slog, trace_id, task_id, "recovery.diagnose.complete",
            f"Diagnosis complete: root_cause={diagnostic_output.root_cause_category}, "
            f"confidence={diagnostic_output.confidence}, "
            f"recommended={diagnostic_output.recommended_strategy}",
            duration_ms=diag_duration,
            confidence=diagnostic_output.confidence,
            root_cause_category=diagnostic_output.root_cause_category,
            recommended_strategy=diagnostic_output.recommended_strategy,
        )

    # ── Stage 4: COMPENSATE (if required) ──────────────────────────
    if error_category.requires_compensation:
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.compensate",
            f"Running compensating actions for {error_context.error_code}",
            error_code=error_context.error_code,
        )
        compensate(
            task_id=task_id,
            agent_name=error_context.agent_name,
            error_code=error_context.error_code,
        )

    # ── Recovery retry loop (Stages 5-7) ───────────────────────────
    max_recovery_time = recovery_config.get("max_recovery_time_seconds", 1800) if isinstance(recovery_config, dict) else getattr(recovery_config, "max_recovery_time_seconds", 1800)

    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt

        # ── Hard timeout check ─────────────────────────────────────
        elapsed_s = (time.monotonic() - pipeline_start)
        if elapsed_s > max_recovery_time:
            _log_recovery_event(
                slog, trace_id, task_id, "recovery.hard_timeout",
                f"Recovery hard timeout: {elapsed_s:.1f}s elapsed exceeds "
                f"max_recovery_time_seconds={max_recovery_time}s",
                level=logging.WARNING,
                elapsed_seconds=round(elapsed_s, 1),
                max_recovery_time_seconds=max_recovery_time,
                attempt=attempt,
            )
            # Stage 8: LEARN (hard timeout)
            failure_memory.record_attempt(
                task_id=task_id,
                error_code=error_context.error_code,
                agent_name=error_context.agent_name,
                diagnostic_summary=(
                    diagnostic_output.root_cause if diagnostic_output else "No diagnosis"
                ),
                resolution_summary=f"Hard timeout after {elapsed_s:.1f}s ({attempt - 1} attempts completed)",
                success=False,
                recovery_tier=attempt,
                task_domain=error_context.task_domain,
                error_pattern=error_context.error_pattern,
            )
            _log_recovery_event(
                slog, trace_id, task_id, "recovery.learn",
                f"Recorded hard timeout for {error_context.error_code}",
            )
            _check_systemic_and_alert(task_id, error_context.error_code, trace_id, config, slog)
            _send_escalation_notification(
                task_id=task_id,
                task_row=task_row,
                error_code=error_context.error_code,
                diagnostic_summary=(
                    diagnostic_output.root_cause if diagnostic_output else "No diagnosis"
                ),
                attempts_used=attempts_used - 1,
                escalation_reason="max_recovery_time_exceeded",
                trace_id=trace_id,
                config=config,
                slog=slog,
            )
            return RecoveryOutcome(
                task_id=task_id,
                success=False,
                final_status="dispatch_failed",
                attempts_used=attempts_used - 1,
                winning_strategy=None,
                escalation_reason="max_recovery_time_exceeded",
                total_duration_ms=_elapsed_ms(pipeline_start),
                total_cost_usd=total_cost_usd,
                error_code=error_context.error_code,
                trace_id=trace_id,
            )

        # ── Stage 5: STRATEGIZE ────────────────────────────────────
        # Check for deterministic playbook first (US-051)
        strategy = None
        try:
            from .playbooks import has_playbook, get_playbook
            if has_playbook(error_context.error_code):
                playbook = get_playbook(error_context.error_code)
                strategy = playbook.select_strategy(attempt, error_context.error_code, error_category)
        except ImportError:
            pass  # playbooks.py not yet created (US-051)

        if strategy is None:
            strategy = select_strategy(attempt, error_category, diagnostic_output, config)

        _log_recovery_event(
            slog, trace_id, task_id, "recovery.strategy.selected",
            f"Selected strategy: {strategy.strategy_name} (tier {strategy.tier}), "
            f"terminal={strategy.is_terminal}",
            strategy_name=strategy.strategy_name,
            tier=strategy.tier,
            is_terminal=strategy.is_terminal,
            attempt=attempt,
        )

        # Terminal strategies (decompose/escalate) — stop retrying
        if strategy.is_terminal:
            escalation_reason = (
                f"Terminal strategy '{strategy.strategy_name}' selected at "
                f"attempt {attempt}: {strategy.strategy_description}"
            )
            # Stage 8: LEARN
            failure_memory.record_attempt(
                task_id=task_id,
                error_code=error_context.error_code,
                agent_name=error_context.agent_name,
                diagnostic_summary=(
                    diagnostic_output.root_cause if diagnostic_output else "No diagnosis"
                ),
                resolution_summary=f"Escalated via {strategy.strategy_name}",
                success=False,
                recovery_tier=strategy.tier,
                task_domain=error_context.task_domain,
                error_pattern=error_context.error_pattern,
            )
            _log_recovery_event(
                slog, trace_id, task_id, "recovery.learn",
                f"Recorded escalation via {strategy.strategy_name}",
            )
            _check_systemic_and_alert(task_id, error_context.error_code, trace_id, config, slog)

            if strategy.strategy_name == "decompose":
                # Tier 4: send decomposition notification (urgency=high)
                _log_recovery_event(
                    slog, trace_id, task_id, "recovery.decompose",
                    f"Recommending task decomposition for task {task_id}: "
                    f"{strategy.prompt_modifications.get('decomposition_suggestion', 'no specific guidance')}",
                    level=logging.WARNING,
                    error_code=error_context.error_code,
                    decomposition_suggestion=strategy.prompt_modifications.get("decomposition_suggestion", ""),
                )
                _send_decomposition_notification(
                    task_id=task_id,
                    task_row=task_row,
                    error_code=error_context.error_code,
                    diagnostic_summary=(
                        diagnostic_output.root_cause if diagnostic_output else "No diagnosis"
                    ),
                    attempts_used=attempts_used,
                    strategy=strategy,
                    trace_id=trace_id,
                    config=config,
                    slog=slog,
                )
            else:
                # Tier 5 escalation or other terminal strategies
                _log_recovery_event(
                    slog, trace_id, task_id, "recovery.escalate",
                    f"Recovery escalated: {escalation_reason}",
                    level=logging.WARNING,
                )
                _send_escalation_notification(
                    task_id=task_id,
                    task_row=task_row,
                    error_code=error_context.error_code,
                    diagnostic_summary=(
                        diagnostic_output.root_cause if diagnostic_output else "No diagnosis"
                    ),
                    attempts_used=attempts_used,
                    escalation_reason=escalation_reason,
                    trace_id=trace_id,
                    config=config,
                    slog=slog,
                )

            return RecoveryOutcome(
                task_id=task_id,
                success=False,
                final_status="dispatch_failed",
                attempts_used=attempts_used,
                winning_strategy=None,
                escalation_reason=escalation_reason,
                total_duration_ms=_elapsed_ms(pipeline_start),
                total_cost_usd=total_cost_usd,
                error_code=error_context.error_code,
                trace_id=trace_id,
            )

        # Build tool call summary for recovery context
        tool_call_summary = _build_tool_call_summary(error_context.tool_call_log)

        # Build similar past fixes as list of resolution summary strings
        similar_fix_strings: list[str] = []
        try:
            similar = failure_memory.find_similar_fixes(
                error_code=error_context.error_code,
                agent_name=error_context.agent_name,
                task_domain=error_context.task_domain,
            )
            similar_fix_strings = [
                fix.get("resolution_summary", "") for fix in similar if fix.get("resolution_summary")
            ]
        except Exception:
            pass

        # Build RecoveryContext for the retry prompt
        recovery_context = RecoveryContext(
            attempt_number=attempt,
            total_max_attempts=max_attempts,
            error_code=error_context.error_code,
            error_message=error_context.error_message,
            error_category=error_context.error_category,
            previous_raw_output=error_context.raw_output[:500] if error_context.raw_output else None,
            tool_call_summary=tool_call_summary,
            diagnostic_analysis=diagnostic_output.root_cause if diagnostic_output else None,
            specific_fix=diagnostic_output.specific_fix if diagnostic_output else None,
            strategy_name=strategy.strategy_name,
            strategy_description=strategy.strategy_description,
            constraints=strategy.constraints,
            previous_attempts=previous_attempts[:],
            similar_past_fixes=similar_fix_strings,
        )

        # ── Stage 6: EXECUTE ──────────────────────────────────────
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.execute.start",
            f"Executing recovery attempt {attempt}/{max_attempts} "
            f"with strategy {strategy.strategy_name}",
            attempt=attempt,
            strategy_name=strategy.strategy_name,
        )

        try:
            exec_result = recovery_execute(
                task_id=task_id,
                recovery_context=recovery_context,
                config=config,
                dispatch_db=dispatch_db,
            )
        except RecoveryBudgetExceeded as budget_err:
            escalation_reason = str(budget_err)
            # Stage 8: LEARN (budget exceeded)
            failure_memory.record_attempt(
                task_id=task_id,
                error_code=error_context.error_code,
                agent_name=error_context.agent_name,
                diagnostic_summary=(
                    diagnostic_output.root_cause if diagnostic_output else "No diagnosis"
                ),
                resolution_summary=f"Recovery budget exceeded: ${budget_err.total_cost:.4f} >= ${budget_err.budget:.4f}",
                success=False,
                recovery_tier=strategy.tier,
                task_domain=error_context.task_domain,
                error_pattern=error_context.error_pattern,
            )
            _log_recovery_event(
                slog, trace_id, task_id, "recovery.learn",
                f"Recorded budget exceeded for {error_context.error_code}",
            )
            _check_systemic_and_alert(task_id, error_context.error_code, trace_id, config, slog)
            _log_recovery_event(
                slog, trace_id, task_id, "recovery.escalate",
                f"Recovery budget exceeded, escalating: {escalation_reason}",
                level=logging.WARNING,
            )
            _send_escalation_notification(
                task_id=task_id,
                task_row=task_row,
                error_code=error_context.error_code,
                diagnostic_summary=(
                    diagnostic_output.root_cause if diagnostic_output else "No diagnosis"
                ),
                attempts_used=attempts_used,
                escalation_reason=escalation_reason,
                trace_id=trace_id,
                config=config,
                slog=slog,
            )
            return RecoveryOutcome(
                task_id=task_id,
                success=False,
                final_status="dispatch_failed",
                attempts_used=attempts_used,
                winning_strategy=None,
                escalation_reason=escalation_reason,
                total_duration_ms=_elapsed_ms(pipeline_start),
                total_cost_usd=total_cost_usd,
                error_code=error_context.error_code,
                trace_id=trace_id,
            )
        except ProviderHealthDeferred as health_err:
            # Provider is degraded/down — defer recovery, return early (not a terminal failure)
            _log_recovery_event(
                slog, trace_id, task_id, "recovery.provider_health_check",
                f"Recovery deferred for task {task_id}: provider {health_err.provider} "
                f"is {health_err.status}, deferring by 60s",
                level=logging.WARNING,
                provider=health_err.provider,
                provider_status=health_err.status,
            )
            return RecoveryOutcome(
                task_id=task_id,
                success=False,
                final_status="failed",
                attempts_used=attempts_used,
                winning_strategy=None,
                escalation_reason="provider_health_deferred",
                total_duration_ms=_elapsed_ms(pipeline_start),
                total_cost_usd=total_cost_usd,
                error_code=error_context.error_code,
                trace_id=trace_id,
            )
        except RecoveryTimeoutError as timeout_err:
            # Timeout is a failed attempt — proceed to next tier if retries remain
            _log_recovery_event(
                slog, trace_id, task_id, "recovery.timeout",
                f"Recovery attempt {attempt} timed out after "
                f"{timeout_err.timeout_seconds}s for task {task_id}",
                level=logging.WARNING,
                timeout_seconds=timeout_err.timeout_seconds,
                attempt=attempt,
            )

            # Record as failed attempt and continue to next iteration
            previous_attempts.append(PreviousAttemptSummary(
                attempt_number=attempt,
                strategy_used=strategy.strategy_name,
                error_code="RECOVERY_TIMEOUT",
                error_message=str(timeout_err),
                diagnostic_summary=diagnostic_output.root_cause if diagnostic_output else None,
                duration_ms=timeout_err.timeout_seconds * 1000,
            ))
            continue
        total_cost_usd += exec_result.tokens_used * 0.000003  # rough cost estimate

        _log_recovery_event(
            slog, trace_id, task_id, "recovery.execute.complete",
            f"Recovery attempt {attempt} {'succeeded' if exec_result.success else 'failed'}"
            f"{f', new error: {exec_result.new_error_code}' if exec_result.new_error_code else ''}",
            success=exec_result.success,
            duration_ms=exec_result.duration_ms,
            tokens_used=exec_result.tokens_used,
            new_error_code=exec_result.new_error_code,
            same_error=exec_result.same_error,
        )

        # ── Stage 7: VERIFY ───────────────────────────────────────
        if exec_result.success:
            _log_recovery_event(
                slog, trace_id, task_id, "recovery.verify",
                f"Recovery verified: attempt {attempt} succeeded with "
                f"strategy {strategy.strategy_name}",
                success=True,
                attempt=attempt,
                strategy_name=strategy.strategy_name,
            )
            # Stage 8: LEARN (success)
            failure_memory.record_attempt(
                task_id=task_id,
                error_code=error_context.error_code,
                agent_name=error_context.agent_name,
                diagnostic_summary=(
                    diagnostic_output.root_cause if diagnostic_output else "No diagnosis"
                ),
                resolution_summary=f"Recovered via {strategy.strategy_name} on attempt {attempt}",
                success=True,
                recovery_tier=strategy.tier,
                task_domain=error_context.task_domain,
                error_pattern=error_context.error_pattern,
            )
            _log_recovery_event(
                slog, trace_id, task_id, "recovery.learn",
                f"Recorded successful recovery via {strategy.strategy_name}",
            )
            return RecoveryOutcome(
                task_id=task_id,
                success=True,
                final_status="completed",
                attempts_used=attempts_used,
                winning_strategy=strategy.strategy_name,
                escalation_reason=None,
                total_duration_ms=_elapsed_ms(pipeline_start),
                total_cost_usd=total_cost_usd,
                error_code=error_context.error_code,
                trace_id=trace_id,
            )

        # Verify failed — record attempt summary for next iteration
        _log_recovery_event(
            slog, trace_id, task_id, "recovery.verify",
            f"Recovery verify failed: attempt {attempt}, "
            f"same_error={exec_result.same_error}",
            success=False,
            same_error=exec_result.same_error,
        )

        previous_attempts.append(PreviousAttemptSummary(
            attempt_number=attempt,
            strategy_used=strategy.strategy_name,
            error_code=exec_result.new_error_code or error_context.error_code,
            error_message=exec_result.new_error_message or error_context.error_message,
            diagnostic_summary=diagnostic_output.root_cause if diagnostic_output else None,
            duration_ms=exec_result.duration_ms,
        ))

    # All attempts exhausted
    _log_recovery_event(
        slog, trace_id, task_id, "recovery.escalate",
        f"All {max_attempts} recovery attempts exhausted for {error_context.error_code}",
        level=logging.WARNING,
        attempts_used=attempts_used,
    )

    # Stage 8: LEARN (exhausted)
    failure_memory.record_attempt(
        task_id=task_id,
        error_code=error_context.error_code,
        agent_name=error_context.agent_name,
        diagnostic_summary=(
            diagnostic_output.root_cause if diagnostic_output else "No diagnosis"
        ),
        resolution_summary=f"All {max_attempts} attempts exhausted",
        success=False,
        recovery_tier=max_attempts,
        task_domain=error_context.task_domain,
        error_pattern=error_context.error_pattern,
    )
    _log_recovery_event(
        slog, trace_id, task_id, "recovery.learn",
        f"Recorded exhausted recovery for {error_context.error_code}",
    )
    _check_systemic_and_alert(task_id, error_context.error_code, trace_id, config, slog)

    return RecoveryOutcome(
        task_id=task_id,
        success=False,
        final_status="failed",
        attempts_used=attempts_used,
        winning_strategy=None,
        escalation_reason=f"All {max_attempts} recovery attempts exhausted",
        total_duration_ms=_elapsed_ms(pipeline_start),
        total_cost_usd=total_cost_usd,
        error_code=error_context.error_code,
        trace_id=trace_id,
    )


def cleanup_recovery_events(
    retention_days: int = 90,
    db_path: Optional[str] = None,
) -> int:
    """Delete recovery_events rows older than retention_days.

    Args:
        retention_days: Number of days to retain entries (default 90).
        db_path: Optional database path override.

    Returns:
        Number of deleted rows.
    """
    from ..dispatch_db import get_writer_connection

    conn = get_writer_connection(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM recovery_events "
            "WHERE created_at < datetime('now', '-' || ? || ' days')",
            (str(retention_days),),
        )
        deleted = cursor.rowcount
        conn.commit()
        if deleted > 0:
            logger.info(
                "Cleaned up %d recovery_events entries older than %d days",
                deleted, retention_days,
            )
        return deleted
    except sqlite3.Error as e:
        logger.error("Failed to cleanup recovery_events: %s", e)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return 0
    finally:
        conn.close()


def _elapsed_ms(start_time: float) -> int:
    """Calculate elapsed milliseconds from a monotonic start time."""
    return int((time.monotonic() - start_time) * 1000)
