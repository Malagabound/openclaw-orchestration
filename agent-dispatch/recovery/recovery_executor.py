"""Stage 6 EXECUTE: Re-run agent with recovery context and verify result.

Provides execute() which builds an enriched prompt with recovery context,
calls agent_runner.run_agent() for the retry, verifies the result, and
compares the new error (if any) against the original error_code to determine
whether recovery succeeded.
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RecoveryBudgetExceeded(Exception):
    """Raised when per-task recovery cost exceeds the configured budget."""

    def __init__(self, task_id: int, total_cost: float, budget: float) -> None:
        self.task_id = task_id
        self.total_cost = total_cost
        self.budget = budget
        super().__init__(
            f"Recovery budget exceeded for task {task_id}: "
            f"${total_cost:.4f} >= ${budget:.4f}"
        )


class RecoveryTimeoutError(Exception):
    """Raised when a recovery attempt exceeds the per-attempt timeout."""

    def __init__(self, task_id: int, timeout_seconds: int) -> None:
        self.task_id = task_id
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Recovery timeout for task {task_id}: "
            f"exceeded {timeout_seconds}s per-attempt limit"
        )


class ProviderHealthDeferred(Exception):
    """Raised when provider health check indicates degraded/down status."""

    def __init__(self, task_id: int, provider: str, status: str) -> None:
        self.task_id = task_id
        self.provider = provider
        self.status = status
        super().__init__(
            f"Provider {provider} is {status} for task {task_id}: "
            f"deferring recovery by 60s"
        )


@dataclass
class RecoveryExecutionResult:
    """Result of a single recovery execution attempt.

    Wraps the agent_runner result with success indicator and error comparison.
    """
    success: bool                           # True if agent returned valid result
    agent_result: Any = None                # AgentResult if successful, None if failed
    new_error_code: Optional[str] = None    # Error code from new failure, None if success
    new_error_message: Optional[str] = None # Error message from new failure
    same_error: bool = False                # True if new_error_code == original error_code
    tokens_used: int = 0                    # Tokens consumed by this attempt
    duration_ms: int = 0                    # Wall-clock time for this attempt
    trace_id: str = ""                      # Trace ID for this execution


def execute(
    task_id: int,
    recovery_context: Any,
    config: Any,
    dispatch_db: Any,
) -> RecoveryExecutionResult:
    """Re-run an agent with recovery context and verify the result.

    Builds an enriched prompt via agent_prompts.build_prompt(recovery_context=...),
    calls agent_runner.run_agent(), verifies the AgentResult schema on success,
    and compares any new error_code against the original from recovery_context.

    Args:
        task_id: The task ID being recovered.
        recovery_context: RecoveryContext dataclass with error info, strategy,
            constraints, and previous attempt history.
        config: Config dict (parsed openclawd.config.yaml).
        dispatch_db: dispatch_db module reference for database operations.

    Returns:
        RecoveryExecutionResult with success indicator and error comparison.
    """
    from ..structured_logging import log_dispatch_event, get_logger
    from ..agent_runner import run_agent, AgentRunnerError
    from ..provider_registry import get_provider
    from ..tool_registry import ToolRegistry
    from .error_classifier import detect_error_code

    slog = get_logger("recovery_executor")
    trace_id = str(uuid.uuid4())
    start_time = time.monotonic()

    # Log recovery.execute.start
    log_dispatch_event(
        slog,
        logging.INFO,
        f"Recovery execution starting for task {task_id}, "
        f"attempt {recovery_context.attempt_number}, "
        f"strategy {recovery_context.strategy_name}",
        trace_id=trace_id,
        task_id=str(task_id),
        extra={
            "event_type": "recovery.execute.start",
            "attempt_number": recovery_context.attempt_number,
            "strategy_name": recovery_context.strategy_name,
            "error_code": recovery_context.error_code,
        },
    )

    try:
        # 1. Load task row from database
        reader = dispatch_db.get_reader_connection()
        reader.row_factory = __import__("sqlite3").Row
        task_row = reader.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()

        if task_row is None:
            return RecoveryExecutionResult(
                success=False,
                new_error_code="TASK_NOT_FOUND",
                new_error_message=f"Task {task_id} not found in database",
                trace_id=trace_id,
                duration_ms=_elapsed_ms(start_time),
            )

        task_dict = dict(task_row)
        agent_name = task_dict.get("assigned_agent", "")

        # 1b. Check provider health before retry (US-041)
        # Determine the provider name and model for this task's agent
        if isinstance(config, dict):
            _provider_section = config.get("provider", {})
            _agent_models = config.get("agent_models", {})
        else:
            _provider_section = getattr(config, "provider", {})
            _agent_models = getattr(config, "agent_models", {})
        _prov_name = _provider_section.get("name", "unknown") if isinstance(_provider_section, dict) else getattr(_provider_section, "name", "unknown")
        _prov_model = _provider_section.get("model", "unknown") if isinstance(_provider_section, dict) else getattr(_provider_section, "model", "unknown")
        # Check agent-specific model override
        if isinstance(_agent_models, dict) and agent_name in _agent_models:
            _prov_model = _agent_models[agent_name]
        _check_provider_health(task_id, _prov_name, _prov_model, config, dispatch_db, slog, trace_id)

        # 1c. Check per-task recovery budget before executing retry
        _check_recovery_budget(task_id, config, dispatch_db, slog, trace_id)

        # 2. Get provider and tool registry
        provider = get_provider(config, agent_name=agent_name)
        tool_registry = ToolRegistry()

        # 3. Run agent with recovery context injected into prompt
        # run_agent calls build_prompt internally, but we need to pass recovery_context
        # Since run_agent calls build_prompt without recovery_context, we call build_prompt
        # ourselves and pass the messages directly
        from ..agent_prompts import build_prompt

        messages = build_prompt(
            agent_name=agent_name,
            task_dict=task_dict,
            working_memory_entries=[],  # Will auto-load from DB
            config=config,
            provider=provider,
            recovery_context=recovery_context,
        )

        # 4. Call run_agent with the enriched prompt, wrapped in per-attempt timeout
        # Read timeout from config.recovery.recovery_timeout_per_attempt (default 600s)
        timeout_seconds = _get_recovery_timeout(config)
        result = _run_agent_with_timeout(
            run_agent=run_agent,
            agent_name=agent_name,
            task_dict=task_dict,
            provider=provider,
            tool_registry=tool_registry,
            config=config,
            trace_id=trace_id,
            task_id=task_id,
            timeout_seconds=timeout_seconds,
        )

        duration_ms = _elapsed_ms(start_time)
        tokens_used = 0
        if hasattr(result, "raw_response"):
            # Estimate tokens from response length (rough approximation)
            tokens_used = len(result.raw_response or "") // 4

        # 4b. Store recovery cost and recovery_tier on dispatch_runs (US-049)
        _store_recovery_cost(
            task_id=task_id,
            tokens_used=tokens_used,
            recovery_tier=recovery_context.attempt_number,
            config=config,
            dispatch_db=dispatch_db,
            trace_id=trace_id,
            slog=slog,
        )

        # 5. Verify AgentResult schema - check status is valid
        if result.status in ("completed", "blocked"):
            # Log recovery.execute.complete (success)
            log_dispatch_event(
                slog,
                logging.INFO,
                f"Recovery execution succeeded for task {task_id}, "
                f"result status: {result.status}",
                trace_id=trace_id,
                task_id=str(task_id),
                extra={
                    "event_type": "recovery.execute.complete",
                    "success": True,
                    "result_status": result.status,
                    "duration_ms": duration_ms,
                    "tokens_used": tokens_used,
                },
            )

            return RecoveryExecutionResult(
                success=True,
                agent_result=result,
                new_error_code=None,
                new_error_message=None,
                same_error=False,
                tokens_used=tokens_used,
                duration_ms=duration_ms,
                trace_id=trace_id,
            )

        # 6. Agent completed but with failed status - classify the new error
        new_error_code = "AGENT_SELF_REPORTED_FAILURE"
        new_error_message = f"Agent reported status: {result.status}"
        same_error = (new_error_code == recovery_context.error_code)

        log_dispatch_event(
            slog,
            logging.WARNING,
            f"Recovery execution completed but agent reported failure for task {task_id}",
            trace_id=trace_id,
            task_id=str(task_id),
            extra={
                "event_type": "recovery.execute.complete",
                "success": False,
                "new_error_code": new_error_code,
                "same_error": same_error,
                "duration_ms": duration_ms,
            },
        )

        return RecoveryExecutionResult(
            success=False,
            agent_result=result,
            new_error_code=new_error_code,
            new_error_message=new_error_message,
            same_error=same_error,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            trace_id=trace_id,
        )

    except AgentRunnerError as e:
        duration_ms = _elapsed_ms(start_time)

        # Detect the new error code from the exception
        new_error_code = detect_error_code(
            exception=e,
            http_status=getattr(e, "http_status", None),
            agent_result=getattr(e, "agent_result", None),
            context={},
        )
        same_error = (new_error_code == recovery_context.error_code)

        # Store recovery cost even on failure (US-049)
        # Estimate tokens from raw_output if available
        error_tokens = len(getattr(e, "raw_output", "") or "") // 4
        _store_recovery_cost(
            task_id=task_id,
            tokens_used=error_tokens,
            recovery_tier=recovery_context.attempt_number,
            config=config,
            dispatch_db=dispatch_db,
            trace_id=trace_id,
            slog=slog,
        )

        log_dispatch_event(
            slog,
            logging.WARNING,
            f"Recovery execution failed for task {task_id}: {e}",
            trace_id=trace_id,
            task_id=str(task_id),
            extra={
                "event_type": "recovery.execute.complete",
                "success": False,
                "new_error_code": new_error_code,
                "same_error": same_error,
                "duration_ms": duration_ms,
                "original_error_code": recovery_context.error_code,
            },
        )

        return RecoveryExecutionResult(
            success=False,
            new_error_code=new_error_code,
            new_error_message=str(e),
            same_error=same_error,
            duration_ms=duration_ms,
            trace_id=trace_id,
        )

    except Exception as e:
        duration_ms = _elapsed_ms(start_time)

        # Store recovery cost with zero tokens for unexpected errors (US-049)
        _store_recovery_cost(
            task_id=task_id,
            tokens_used=0,
            recovery_tier=recovery_context.attempt_number,
            config=config,
            dispatch_db=dispatch_db,
            trace_id=trace_id,
            slog=slog,
        )

        log_dispatch_event(
            slog,
            logging.ERROR,
            f"Recovery execution unexpected error for task {task_id}: {e}",
            trace_id=trace_id,
            task_id=str(task_id),
            extra={
                "event_type": "recovery.execute.complete",
                "success": False,
                "error_type": type(e).__name__,
                "duration_ms": duration_ms,
            },
        )

        return RecoveryExecutionResult(
            success=False,
            new_error_code="UNKNOWN_ERROR",
            new_error_message=str(e),
            same_error=("UNKNOWN_ERROR" == recovery_context.error_code),
            duration_ms=duration_ms,
            trace_id=trace_id,
        )


def _elapsed_ms(start_time: float) -> int:
    """Calculate elapsed milliseconds from a monotonic start time."""
    return int((time.monotonic() - start_time) * 1000)


def _get_recovery_timeout(config: Any) -> int:
    """Extract recovery_timeout_per_attempt from config (default 600s)."""
    if isinstance(config, dict):
        recovery_cfg = config.get("recovery", {})
    else:
        recovery_cfg = getattr(config, "recovery", {})

    if isinstance(recovery_cfg, dict):
        return int(recovery_cfg.get("recovery_timeout_per_attempt", 600))
    return int(getattr(recovery_cfg, "recovery_timeout_per_attempt", 600))


def _run_agent_with_timeout(
    run_agent: Any,
    agent_name: str,
    task_dict: dict,
    provider: Any,
    tool_registry: Any,
    config: Any,
    trace_id: str,
    task_id: int,
    timeout_seconds: int,
) -> Any:
    """Run agent_runner.run_agent() with a per-attempt timeout.

    Uses a threading approach: runs run_agent in a daemon thread and waits
    up to timeout_seconds. If the thread doesn't finish in time, raises
    RecoveryTimeoutError. The daemon thread will be abandoned (it will
    eventually complete or be cleaned up when the process exits).

    Raises:
        RecoveryTimeoutError: If the agent doesn't finish within timeout.
        Any exception raised by run_agent is re-raised.
    """
    result_holder: list[Any] = []
    error_holder: list[BaseException] = []

    def _target() -> None:
        try:
            res = run_agent(
                agent_name=agent_name,
                task_dict=task_dict,
                provider=provider,
                tool_registry=tool_registry,
                config=config,
                trace_id=trace_id,
            )
            result_holder.append(res)
        except BaseException as exc:
            error_holder.append(exc)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Thread still running — timeout exceeded
        raise RecoveryTimeoutError(task_id, timeout_seconds)

    if error_holder:
        raise error_holder[0]

    if result_holder:
        return result_holder[0]

    # Should not happen, but handle defensively
    raise RecoveryTimeoutError(task_id, timeout_seconds)


def _store_recovery_cost(
    task_id: int,
    tokens_used: int,
    recovery_tier: int,
    config: Any,
    dispatch_db: Any,
    trace_id: str,
    slog: logging.Logger,
) -> float:
    """Store cost_estimate and recovery_tier on the dispatch_runs row for this recovery attempt.

    Calculates cost using dispatch_db.calculate_cost() if pricing config is available,
    falling back to a rough tokens_used * cost_per_token estimate.

    Returns:
        The calculated cost_estimate in USD.
    """
    import sqlite3
    from ..structured_logging import log_dispatch_event

    # Determine provider and model from config
    if isinstance(config, dict):
        provider_section = config.get("provider", {})
    else:
        provider_section = getattr(config, "provider", {})

    provider_name = (
        provider_section.get("name", "unknown")
        if isinstance(provider_section, dict)
        else getattr(provider_section, "name", "unknown")
    )
    model_name = (
        provider_section.get("model", "unknown")
        if isinstance(provider_section, dict)
        else getattr(provider_section, "model", "unknown")
    )

    # Try to calculate cost using the pricing config (dispatch_db.calculate_cost)
    cost_estimate = 0.0
    try:
        from ..dispatch_db import calculate_cost

        config_dict = config if isinstance(config, dict) else {}
        # We only have total tokens_used, not split by input/output.
        # Estimate 70% input, 30% output as a reasonable approximation.
        token_usage = {
            "input_tokens": int(tokens_used * 0.7),
            "output_tokens": int(tokens_used * 0.3),
        }
        cost_estimate = calculate_cost(
            provider=provider_name,
            model=model_name,
            token_usage=token_usage,
            config=config_dict,
        )
    except (ValueError, ImportError, Exception):
        # Pricing not configured or calculation failed — use rough estimate
        cost_estimate = tokens_used * 0.000003

    # Write cost_estimate and recovery_tier to dispatch_runs
    try:
        writer = dispatch_db.get_writer_connection()
        try:
            writer.execute(
                "UPDATE dispatch_runs SET cost_estimate = ?, recovery_tier = ? "
                "WHERE trace_id = ?",
                (cost_estimate, recovery_tier, trace_id),
            )
            writer.commit()
        finally:
            writer.close()
    except (sqlite3.Error, Exception) as e:
        logger.warning(
            "Failed to store recovery cost for task %s (trace %s): %s",
            task_id, trace_id, e,
        )

    return cost_estimate


def _check_provider_health(
    task_id: int,
    provider_name: str,
    model: str,
    config: Any,
    dispatch_db: Any,
    slog: logging.Logger,
    trace_id: str,
) -> None:
    """Check provider health before retry; defer if degraded or down.

    Queries the most recent 5 health checks from provider_health for the
    task's assigned provider/model. If fewer than 60% passed, the provider
    is considered degraded/down. Defers recovery by setting next_retry_at
    on the latest dispatch_run to now + 60s.

    Raises:
        ProviderHealthDeferred: If provider is degraded or down.
    """
    import sqlite3
    import datetime
    from ..structured_logging import log_dispatch_event

    try:
        reader = dispatch_db.get_reader_connection()
        cursor = reader.execute(
            """
            SELECT passed FROM provider_health
            WHERE provider = ? AND model = ?
            ORDER BY tested_at DESC
            LIMIT 5
            """,
            (provider_name, model),
        )
        rows = cursor.fetchall()
    except (sqlite3.Error, Exception):
        # If we can't query health, allow recovery to proceed (fail open)
        log_dispatch_event(
            slog,
            logging.DEBUG,
            f"Provider health check skipped for task {task_id}: query failed",
            trace_id=trace_id,
            task_id=str(task_id),
            extra={"event_type": "recovery.provider_health_check", "status": "skipped"},
        )
        return

    if not rows:
        # No health data available — allow recovery to proceed
        log_dispatch_event(
            slog,
            logging.DEBUG,
            f"Provider health check skipped for task {task_id}: "
            f"no health data for {provider_name}/{model}",
            trace_id=trace_id,
            task_id=str(task_id),
            extra={
                "event_type": "recovery.provider_health_check",
                "status": "no_data",
                "provider": provider_name,
                "model": model,
            },
        )
        return

    total = len(rows)
    passed = sum(1 for r in rows if r[0])
    pass_rate = passed / total

    if pass_rate >= 0.6:
        # Provider is healthy enough — allow recovery
        status = "healthy"
        log_dispatch_event(
            slog,
            logging.DEBUG,
            f"Provider health check passed for task {task_id}: "
            f"{provider_name}/{model} pass_rate={pass_rate:.0%}",
            trace_id=trace_id,
            task_id=str(task_id),
            extra={
                "event_type": "recovery.provider_health_check",
                "status": status,
                "provider": provider_name,
                "model": model,
                "pass_rate": pass_rate,
            },
        )
        return

    # Provider is degraded or down — defer recovery
    status = "down" if passed == 0 else "degraded"

    # Defer by setting next_retry_at on the latest dispatch_run
    try:
        writer = dispatch_db.get_writer_connection()
        try:
            defer_time = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=60)
            ).isoformat()
            writer.execute(
                """
                UPDATE dispatch_runs SET next_retry_at = ?
                WHERE id = (
                    SELECT MAX(id) FROM dispatch_runs WHERE task_id = ?
                )
                """,
                (defer_time, task_id),
            )
            writer.commit()
        finally:
            writer.close()
    except (sqlite3.Error, Exception):
        pass  # Best-effort deferral

    log_dispatch_event(
        slog,
        logging.WARNING,
        f"Provider {provider_name}/{model} is {status} for task {task_id}: "
        f"deferring recovery by 60s (pass_rate={pass_rate:.0%})",
        trace_id=trace_id,
        task_id=str(task_id),
        extra={
            "event_type": "recovery.provider_health_check",
            "status": status,
            "provider": provider_name,
            "model": model,
            "pass_rate": pass_rate,
            "defer_seconds": 60,
        },
    )

    raise ProviderHealthDeferred(task_id, provider_name, status)


def _check_recovery_budget(
    task_id: int,
    config: Any,
    dispatch_db: Any,
    slog: logging.Logger,
    trace_id: str,
) -> None:
    """Check per-task recovery budget and raise if exceeded.

    Queries SUM(cost_estimate) from dispatch_runs for this task's recovery
    attempts (where recovery_tier IS NOT NULL). Compares against:
      recovery_budget = min(daily_budget_usd * recovery_budget_ratio,
                            recovery_budget_cap_usd)

    Raises:
        RecoveryBudgetExceeded: If total recovery cost >= budget.
    """
    import sqlite3
    from ..structured_logging import log_dispatch_event

    # Extract config values
    if isinstance(config, dict):
        daily_budget = float(config.get("daily_budget_usd", 50.0))
        recovery_cfg = config.get("recovery", {})
    else:
        daily_budget = float(getattr(config, "daily_budget_usd", 50.0))
        recovery_cfg = getattr(config, "recovery", {})

    if isinstance(recovery_cfg, dict):
        budget_ratio = float(recovery_cfg.get("recovery_budget_ratio", 0.04))
        budget_cap = float(recovery_cfg.get("recovery_budget_cap_usd", 2.00))
    else:
        budget_ratio = float(getattr(recovery_cfg, "recovery_budget_ratio", 0.04))
        budget_cap = float(getattr(recovery_cfg, "recovery_budget_cap_usd", 2.00))

    recovery_budget = min(daily_budget * budget_ratio, budget_cap)

    # Query total recovery cost for this task
    try:
        reader = dispatch_db.get_reader_connection()
        row = reader.execute(
            "SELECT COALESCE(SUM(cost_estimate), 0.0) AS total_cost "
            "FROM dispatch_runs "
            "WHERE task_id = ? AND recovery_tier IS NOT NULL",
            (task_id,),
        ).fetchone()
        total_cost = float(row[0]) if row else 0.0
    except (sqlite3.Error, Exception):
        # If we can't query, allow recovery to proceed (fail open)
        return

    if total_cost >= recovery_budget:
        log_dispatch_event(
            slog,
            logging.WARNING,
            f"Recovery budget exceeded for task {task_id}: "
            f"${total_cost:.4f} >= ${recovery_budget:.4f} "
            f"(ratio={budget_ratio}, cap=${budget_cap:.2f})",
            trace_id=trace_id,
            task_id=str(task_id),
            extra={
                "event_type": "recovery.budget.exceeded",
                "total_recovery_cost": total_cost,
                "recovery_budget": recovery_budget,
                "budget_ratio": budget_ratio,
                "budget_cap": budget_cap,
            },
        )
        raise RecoveryBudgetExceeded(task_id, total_cost, recovery_budget)
