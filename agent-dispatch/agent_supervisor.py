"""OpenClawd Agent Dispatch System - Supervisor Poll Loop.

US-054: Main supervisor daemon with 30-second poll loop that queries
dispatchable tasks, claims atomically, spawns agent runners in a thread
pool (max_workers from config), extends leases via heartbeat thread every
2 minutes, and enforces agent_timeout_seconds hard cap.

US-055: Graceful shutdown on SIGTERM/SIGINT - stops accepting new tasks,
waits 60s for running agents, marks remaining as interrupted.

US-056: Interrupted task recovery on startup - re-queues tasks marked
'interrupted' from previous shutdown, counting toward retry limit.

US-057: SIGUSR1 (immediate poll) and SIGUSR2 (immediate health check)
signal handlers for operational control without restarting daemon.

US-058: PID file at agent-dispatch/supervisor.pid with stale-PID detection.
On startup checks for existing PID, exits if active, removes if stale.
Writes current PID on start, deletes on graceful shutdown.
"""

import logging
import os
import signal
import sqlite3
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set

from .config import (
    DEFAULT_DB_PATH,
    LEASE_SECONDS,
    MAX_CONCURRENT_AGENTS,
    POLL_INTERVAL_SECONDS,
    TIMEOUT_SECONDS,
    load_config,
)
from .dispatch_db import (
    check_budget,
    claim_task,
    close_reader_connection,
    get_dispatchable_tasks,
    get_reader_connection,
    get_writer_connection,
    handle_dispatch_failure,
    handle_task_completion,
    recover_interrupted_tasks,
    recover_partial_completions,
    run_migrations,
)

logger = logging.getLogger(__name__)

# PID file path (relative to agent-dispatch directory)
_PID_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "supervisor.pid")

# US-059: Heartbeat file path (written each poll cycle)
_HEARTBEAT_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "supervisor.heartbeat")

# Heartbeat interval: extend leases every 2 minutes
_HEARTBEAT_INTERVAL_SECONDS = 120

# Graceful shutdown: max seconds to wait for running agents
_SHUTDOWN_WAIT_SECONDS = 60


class _ActiveTask:
    """Tracks a running agent task for heartbeat and timeout enforcement."""

    __slots__ = ("task_id", "trace_id", "future", "started_at", "agent_name", "attempt")

    def __init__(
        self,
        task_id: int,
        trace_id: str,
        future: Future,
        started_at: float,
        agent_name: str,
        attempt: int,
    ):
        self.task_id = task_id
        self.trace_id = trace_id
        self.future = future
        self.started_at = started_at
        self.agent_name = agent_name
        self.attempt = attempt


class AgentSupervisor:
    """Supervisor daemon that polls for tasks and dispatches agent runners.

    Attributes:
        config: Parsed openclawd.config.yaml dict.
        adapter: Optional OpenClawdAdapter instance.
        shutdown_requested: Flag checked each poll iteration.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        adapter=None,
        db_path: Optional[str] = None,
    ):
        self.config = config or load_config()
        self.adapter = adapter
        self.db_path = db_path or os.environ.get("OPENCLAWD_DB_PATH", DEFAULT_DB_PATH)

        # Configurable values with fallbacks to module constants
        self._poll_interval = int(
            self.config.get("poll_interval_seconds", POLL_INTERVAL_SECONDS)
        )
        self._lease_seconds = int(
            self.config.get("dispatch_lease_seconds", LEASE_SECONDS)
        )
        self._timeout_seconds = int(
            self.config.get("agent_timeout_seconds", TIMEOUT_SECONDS)
        )
        self._max_workers = int(
            self.config.get("max_concurrent_agents", MAX_CONCURRENT_AGENTS)
        )

        # Thread pool for agent runners
        self._executor: Optional[ThreadPoolExecutor] = None

        # Active task tracking (guarded by _lock)
        self._lock = threading.Lock()
        self._active_tasks: Dict[int, _ActiveTask] = {}

        # Heartbeat thread
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()

        # Shutdown flag
        self.shutdown_requested = False

        # US-057: Immediate poll flag (set by SIGUSR1 handler)
        self._immediate_poll = threading.Event()

    # ── Public API ───────────────────────────────────────────────

    def _register_signal_handlers(self) -> None:
        """Register SIGTERM, SIGINT, SIGUSR1, and SIGUSR2 handlers."""
        def _handle_shutdown_signal(signum: int, frame: Any) -> None:
            sig_name = signal.Signals(signum).name
            logger.info("Received %s, initiating graceful shutdown...", sig_name)
            self.shutdown_requested = True

        def _handle_sigusr1(signum: int, frame: Any) -> None:
            logger.info("Received SIGUSR1, setting immediate poll flag")
            self._immediate_poll.set()

        def _handle_sigusr2(signum: int, frame: Any) -> None:
            logger.info("Received SIGUSR2, spawning immediate health check")
            t = threading.Thread(
                target=self._run_health_check,
                name="sigusr2-health-check",
                daemon=True,
            )
            t.start()

        signal.signal(signal.SIGTERM, _handle_shutdown_signal)
        signal.signal(signal.SIGINT, _handle_shutdown_signal)
        signal.signal(signal.SIGUSR1, _handle_sigusr1)
        signal.signal(signal.SIGUSR2, _handle_sigusr2)
        logger.info("Registered signal handlers for SIGTERM, SIGINT, SIGUSR1, SIGUSR2")

    # ── PID File Management (US-058) ────────────────────────────

    def _check_pid_file(self) -> None:
        """Check for existing PID file and handle stale/active processes.

        Raises SystemExit if another supervisor instance is already running.
        """
        if not os.path.exists(_PID_FILE_PATH):
            return

        try:
            with open(_PID_FILE_PATH, "r") as f:
                pid_str = f.read().strip()
            if not pid_str:
                logger.warning("Found empty PID file at %s, removing", _PID_FILE_PATH)
                os.remove(_PID_FILE_PATH)
                return
            old_pid = int(pid_str)
        except (ValueError, OSError) as e:
            logger.warning(
                "Could not read PID file %s (%s), removing", _PID_FILE_PATH, e
            )
            try:
                os.remove(_PID_FILE_PATH)
            except OSError:
                pass
            return

        # Check if the process is still running
        if self._is_pid_running(old_pid):
            logger.error(
                "Another supervisor is already running (PID %d). Exiting.", old_pid
            )
            raise SystemExit(1)

        # PID is stale - remove and proceed
        logger.warning(
            "Found stale PID file (PID %d is not running), removing %s",
            old_pid,
            _PID_FILE_PATH,
        )
        try:
            os.remove(_PID_FILE_PATH)
        except OSError:
            pass

    @staticmethod
    def _is_pid_running(pid: int) -> bool:
        """Check if a process with the given PID is still running."""
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we don't have permission to signal it
            return True
        except OSError:
            return False

    def _write_pid_file(self) -> None:
        """Write current process PID to the PID file."""
        try:
            with open(_PID_FILE_PATH, "w") as f:
                f.write(str(os.getpid()))
            logger.info("Wrote PID %d to %s", os.getpid(), _PID_FILE_PATH)
        except OSError:
            logger.exception("Failed to write PID file %s", _PID_FILE_PATH)

    def _remove_pid_file(self) -> None:
        """Remove the PID file on graceful shutdown."""
        try:
            if os.path.exists(_PID_FILE_PATH):
                os.remove(_PID_FILE_PATH)
                logger.info("Removed PID file %s", _PID_FILE_PATH)
        except OSError:
            logger.exception("Failed to remove PID file %s", _PID_FILE_PATH)

    def _graceful_shutdown(self) -> None:
        """Graceful shutdown: wait for running agents, then mark remaining as interrupted.

        Waits up to _SHUTDOWN_WAIT_SECONDS (60s) for active agent futures
        to complete. After the timeout, any tasks still in 'dispatched'
        state are marked 'interrupted' with lease_until cleared.
        """
        from concurrent.futures import wait as futures_wait, FIRST_EXCEPTION

        logger.info("Graceful shutdown: stopping heartbeat...")
        self._stop_heartbeat()

        if self._executor is not None:
            with self._lock:
                active_futures = [at.future for at in self._active_tasks.values()]

            if active_futures:
                logger.info(
                    "Graceful shutdown: waiting up to %ds for %d running agent(s)...",
                    _SHUTDOWN_WAIT_SECONDS,
                    len(active_futures),
                )
                # Wait for futures with timeout
                futures_wait(active_futures, timeout=_SHUTDOWN_WAIT_SECONDS)

            # Shut down the executor (don't wait again - we already waited)
            self._executor.shutdown(wait=False, cancel_futures=True)

        # Mark any tasks still in 'dispatched' state as 'interrupted'
        self._mark_interrupted_tasks()

        # US-058: Remove PID file on graceful shutdown
        self._remove_pid_file()

        close_reader_connection()
        logger.info("Graceful shutdown complete.")

    def _mark_interrupted_tasks(self) -> None:
        """Mark tasks with dispatch_status='dispatched' as 'interrupted' and clear lease_until."""
        try:
            conn = get_writer_connection(self.db_path)
            cursor = conn.execute(
                "UPDATE tasks SET dispatch_status = 'interrupted', lease_until = NULL "
                "WHERE dispatch_status = 'dispatched'"
            )
            count = cursor.rowcount
            conn.commit()
            conn.close()
            if count > 0:
                logger.info(
                    "Marked %d dispatched task(s) as interrupted during shutdown", count
                )
        except sqlite3.Error:
            logger.exception("Failed to mark interrupted tasks during shutdown")

    def run(self) -> None:
        """Start the supervisor poll loop.

        Runs migrations, registers signal handlers, starts the heartbeat
        thread, then enters the main poll loop sleeping 30s between
        iterations. Each iteration:
          1. Runs recovery sweep (recover_partial_completions)
          2. Queries dispatchable tasks
          3. Claims each task atomically
          4. Spawns run_agent in the thread pool

        On SIGTERM/SIGINT, gracefully shuts down: waits for running agents
        (up to 60s), then marks remaining dispatched tasks as interrupted.
        """
        logger.info(
            "Supervisor starting (poll=%ds, lease=%ds, timeout=%ds, workers=%d)",
            self._poll_interval,
            self._lease_seconds,
            self._timeout_seconds,
            self._max_workers,
        )

        # US-058: Check for existing PID file (exits if another instance active)
        self._check_pid_file()
        self._write_pid_file()

        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()

        # Run schema migrations
        run_migrations(self.db_path)

        # US-056: Recover tasks interrupted by previous shutdown
        try:
            recovered = recover_interrupted_tasks(db_path=self.db_path)
            if recovered:
                logger.info(
                    "Startup recovery: re-queued %d interrupted task(s)", len(recovered)
                )
        except Exception:
            logger.exception("Startup recovery of interrupted tasks failed")

        # Start thread pool
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)

        # Start heartbeat thread
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="supervisor-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()

        try:
            self._poll_loop()
        finally:
            self._graceful_shutdown()

    # ── Main Poll Loop ───────────────────────────────────────────

    def _poll_loop(self) -> None:
        """Main loop: sleep, recover, query, claim, dispatch.

        US-057: Checks _immediate_poll flag each second. If set by SIGUSR1,
        skips remaining sleep and runs poll cycle immediately.
        """
        while not self.shutdown_requested:
            try:
                self._poll_once()
            except Exception:
                logger.exception("Unhandled error in poll loop iteration")

            # Sleep in small increments to check shutdown and immediate_poll flags
            for _ in range(self._poll_interval):
                if self.shutdown_requested:
                    break
                if self._immediate_poll.is_set():
                    self._immediate_poll.clear()
                    logger.info("Immediate poll triggered by SIGUSR1")
                    break
                time.sleep(1)

    def _write_heartbeat_file(self) -> None:
        """US-059: Write current ISO 8601 timestamp to supervisor.heartbeat file."""
        try:
            from datetime import datetime, timezone

            ts = datetime.now(timezone.utc).isoformat()
            with open(_HEARTBEAT_FILE_PATH, "w") as f:
                f.write(ts)
        except OSError:
            logger.exception("Failed to write heartbeat file %s", _HEARTBEAT_FILE_PATH)

    def _poll_once(self) -> None:
        """Single poll iteration."""
        # US-059: Write heartbeat timestamp on each poll cycle
        self._write_heartbeat_file()

        # US-040: Detect stuck tasks before recovery sweep
        try:
            self._detect_stuck_tasks()
        except Exception:
            logger.exception("Stuck task detection failed")

        # Step 1: Recovery sweep
        try:
            recovered = recover_partial_completions(
                adapter=self.adapter, config=self.config
            )
            if recovered:
                logger.info("Recovered %d partial completions: %s", len(recovered), recovered)
        except Exception:
            logger.exception("Recovery sweep failed")

        # Reap completed futures before checking capacity
        self._reap_completed()

        # Step 2: Query dispatchable tasks
        try:
            tasks = get_dispatchable_tasks(self.config)
        except Exception:
            logger.exception("Failed to query dispatchable tasks")
            return

        if not tasks:
            logger.debug("No dispatchable tasks found")
            return

        logger.info("Found %d dispatchable tasks", len(tasks))

        # US-066: Check global budget before claiming any tasks
        global_budget_status = check_budget(
            self.config, agent_name="__global__", adapter=self.adapter,
        )
        if global_budget_status["global_exceeded"]:
            logger.info("Global daily budget exceeded, skipping all dispatch")
            return

        # Step 3-4: Claim and dispatch each task
        for task in tasks:
            if self.shutdown_requested:
                break

            # Check concurrency limit
            with self._lock:
                if len(self._active_tasks) >= self._max_workers:
                    logger.debug(
                        "At max concurrent agents (%d), skipping remaining tasks",
                        self._max_workers,
                    )
                    break

            task_id = task.get("id")
            if task_id is None:
                continue

            # Skip if already active
            with self._lock:
                if task_id in self._active_tasks:
                    continue

            # US-066: Check per-agent budget before claiming
            agent_name = task.get("assigned_agent", "research")
            budget_status = check_budget(
                self.config, agent_name=agent_name, adapter=self.adapter,
            )
            if budget_status["global_exceeded"]:
                logger.info("Global daily budget exceeded, stopping dispatch")
                break
            if budget_status["agent_exceeded"]:
                logger.debug(
                    "Agent %s daily budget exceeded, skipping task %s",
                    agent_name, task_id,
                )
                continue

            # Claim atomically
            claimed = claim_task(task_id, self._lease_seconds)
            if not claimed:
                logger.debug("Could not claim task %s", task_id)
                continue

            # Determine agent and attempt
            agent_name = task.get("assigned_agent", "research")
            attempt = self._get_attempt_count(task_id) + 1
            trace_id = str(uuid.uuid4())

            # Create dispatch_run record
            self._create_dispatch_run(task_id, agent_name, trace_id, attempt)

            # Spawn in thread pool
            future = self._executor.submit(
                self._run_agent_task,
                task_id=task_id,
                task_dict=task,
                agent_name=agent_name,
                trace_id=trace_id,
                attempt=attempt,
            )

            with self._lock:
                self._active_tasks[task_id] = _ActiveTask(
                    task_id=task_id,
                    trace_id=trace_id,
                    future=future,
                    started_at=time.monotonic(),
                    agent_name=agent_name,
                    attempt=attempt,
                )

            logger.info(
                "Dispatched task %s to agent %s (trace=%s, attempt=%d)",
                task_id, agent_name, trace_id, attempt,
            )

    # ── Agent Runner Wrapper ─────────────────────────────────────

    def _run_agent_task(
        self,
        task_id: int,
        task_dict: Dict[str, Any],
        agent_name: str,
        trace_id: str,
        attempt: int,
    ) -> None:
        """Run an agent task (called in thread pool).

        Handles completion and failure recording.
        """
        from .agent_runner import AgentResult, AgentRunnerError, run_agent
        from .provider_registry import ProviderRegistryError, get_provider
        from .tool_registry import ToolRegistry

        try:
            # Get provider
            provider = get_provider(self.config, agent_name=agent_name)

            # Get tool registry
            tool_registry = ToolRegistry()

            # Update dispatch_run to running
            self._update_dispatch_run_status(trace_id, "running")

            # Run agent
            result = run_agent(
                agent_name=agent_name,
                task_dict=task_dict,
                provider=provider,
                tool_registry=tool_registry,
                config=self.config,
                db_path=self.db_path,
                trace_id=trace_id,
            )

            # Handle completion
            handle_task_completion(
                task_id=task_id,
                agent_result=result,
                trace_id=trace_id,
                config=self.config,
                adapter=self.adapter,
            )

            logger.info("Task %s completed successfully (trace=%s)", task_id, trace_id)

        except Exception as e:
            logger.error("Task %s failed (trace=%s): %s", task_id, trace_id, e)
            self._handle_agent_failure(
                task_id=task_id,
                task_dict=task_dict,
                agent_name=agent_name,
                trace_id=trace_id,
                attempt=attempt,
                error=e,
            )

        finally:
            # Remove from active tasks
            with self._lock:
                self._active_tasks.pop(task_id, None)

    # ── Recovery Pipeline Integration (US-028) ────────────────────

    def _handle_agent_failure(
        self,
        task_id: int,
        task_dict: Dict[str, Any],
        agent_name: str,
        trace_id: str,
        attempt: int,
        error: Exception,
    ) -> None:
        """Handle agent failure with recovery pipeline, falling back to simple retry.

        If recovery is enabled (config has 'recovery' section or defaults),
        calls recovery_pipeline.handle_failure() and processes RecoveryOutcome:
          - final_status='completed': calls handle_task_completion()
          - final_status='failed': updates next_retry_at for next poll cycle
          - final_status='dispatch_failed': creates urgent notification

        Falls back to dispatch_db.handle_dispatch_failure() if recovery pipeline
        is disabled or raises an unexpected error.
        """
        # Check if recovery is enabled (disabled via config.recovery.enabled=False)
        recovery_config = (
            self.config.get("recovery", {})
            if isinstance(self.config, dict)
            else getattr(self.config, "recovery", {}) or {}
        )
        recovery_enabled = (
            recovery_config.get("enabled", True)
            if isinstance(recovery_config, dict)
            else getattr(recovery_config, "enabled", True)
        )

        if not recovery_enabled:
            logger.debug(
                "Recovery disabled, falling back to simple retry for task %s", task_id
            )
            self._fallback_handle_failure(task_id, attempt, error, trace_id)
            return

        try:
            from . import dispatch_db as dispatch_db_module
            from .recovery.recovery_pipeline import handle_failure as recovery_handle_failure

            # Get dispatch_run_row for the current trace
            dispatch_run_row = self._get_dispatch_run_row(trace_id)

            logger.info(
                "Invoking recovery pipeline for task %s (trace=%s)", task_id, trace_id
            )

            outcome = recovery_handle_failure(
                task_id=task_id,
                runner_error=error,
                task_row=task_dict,
                dispatch_run_row=dispatch_run_row,
                config=self.config,
                dispatch_db=dispatch_db_module,
            )

            logger.info(
                "Recovery pipeline result for task %s: success=%s, final_status=%s, "
                "attempts_used=%d, strategy=%s",
                task_id, outcome.success, outcome.final_status,
                outcome.attempts_used, outcome.winning_strategy,
            )

            # Handle RecoveryOutcome
            if outcome.final_status == "completed":
                # Recovery succeeded — flow result to completion handler
                logger.info(
                    "Task %s recovered successfully via strategy '%s' (trace=%s)",
                    task_id, outcome.winning_strategy, trace_id,
                )
                # Note: handle_task_completion is already called inside
                # recovery_executor.execute() when agent succeeds, so the
                # task status is already updated. No additional action needed.

            elif outcome.final_status == "failed":
                # Recovery deferred or exhausted but retryable — set next_retry_at
                logger.info(
                    "Task %s recovery deferred/failed, will retry next poll cycle "
                    "(reason=%s, trace=%s)",
                    task_id, outcome.escalation_reason, trace_id,
                )
                # next_retry_at is already set by the recovery pipeline
                # (concurrency guard or exhaustion handling)

            elif outcome.final_status == "dispatch_failed":
                # Terminal failure — create urgent notification
                logger.warning(
                    "Task %s recovery exhausted, dispatch_failed (reason=%s, trace=%s)",
                    task_id, outcome.escalation_reason, trace_id,
                )
                if self.adapter is not None:
                    try:
                        self.adapter.create_notification(
                            task_id=task_id,
                            message=(
                                f"Task {task_id} recovery exhausted after "
                                f"{outcome.attempts_used} attempt(s). "
                                f"Error: {outcome.error_code}. "
                                f"Escalation: {outcome.escalation_reason}. "
                                f"Manual intervention required."
                            ),
                            urgency="urgent",
                        )
                    except Exception:
                        logger.exception(
                            "Failed to create escalation notification for task %s",
                            task_id,
                        )

        except Exception:
            logger.exception(
                "Recovery pipeline failed for task %s, falling back to simple retry",
                task_id,
            )
            self._fallback_handle_failure(task_id, attempt, error, trace_id)

    def _fallback_handle_failure(
        self, task_id: int, attempt: int, error: Exception, trace_id: str
    ) -> None:
        """Fall back to the original simple retry logic."""
        try:
            handle_dispatch_failure(
                task_id=task_id,
                attempt=attempt,
                error=str(error),
                trace_id=trace_id,
                adapter=self.adapter,
            )
        except Exception:
            logger.exception(
                "Failed to record dispatch failure for task %s", task_id
            )

    def _get_dispatch_run_row(self, trace_id: str) -> dict:
        """Fetch the dispatch_run row for a given trace_id as a dict."""
        try:
            conn = get_reader_connection(self.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM dispatch_runs WHERE trace_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (trace_id,),
            ).fetchone()
            if row:
                return dict(row)
        except sqlite3.Error:
            logger.exception(
                "Failed to fetch dispatch_run for trace %s", trace_id
            )
        return {}

    # ── Stuck Task Detection (US-040) ──────────────────────────────

    def _detect_stuck_tasks(self) -> None:
        """US-040: Detect tasks stuck in 'dispatched' status and trigger recovery.

        Queries for tasks where:
          - dispatch_status = 'dispatched'
          - lease_until < now (lease expired)
          - duration since dispatch_runs.started_at > agent_timeout_seconds

        Also checks alternative detection: lease extended 3+ times with no
        tool_calls_count increment (stalled agent making no progress).

        For each stuck task found, transitions to 'failed' and triggers
        the recovery pipeline with a STUCK_TASK error code.
        """
        from .agent_runner import AgentRunnerError
        from .structured_logging import log_dispatch_event

        try:
            conn = get_reader_connection(self.db_path)
        except sqlite3.Error:
            logger.exception("Failed to get reader connection for stuck task detection")
            return

        timeout_seconds = self._timeout_seconds

        # Query 1: Tasks with expired lease and long duration
        try:
            stuck_rows = conn.execute(
                """
                SELECT t.id, t.assigned_agent, t.title,
                       dr.trace_id, dr.started_at, dr.lease_extensions,
                       dr.tool_calls_count, dr.tool_calls_count_at_last_extension
                FROM tasks t
                LEFT JOIN dispatch_runs dr ON dr.id = (
                    SELECT MAX(dr2.id) FROM dispatch_runs dr2
                    WHERE dr2.task_id = t.id
                )
                WHERE t.dispatch_status = 'dispatched'
                  AND t.lease_until IS NOT NULL
                  AND t.lease_until < datetime('now')
                  AND dr.started_at IS NOT NULL
                  AND (
                      -- Primary: duration exceeds timeout
                      (julianday('now') - julianday(dr.started_at)) * 86400 > ?
                      -- Alternative: 3+ lease extensions with no tool_calls progress
                      OR (
                          COALESCE(dr.lease_extensions, 0) >= 3
                          AND COALESCE(dr.tool_calls_count, 0) <= COALESCE(dr.tool_calls_count_at_last_extension, 0)
                      )
                  )
                """,
                (timeout_seconds,),
            ).fetchall()
        except sqlite3.Error:
            logger.exception("Failed to query stuck tasks")
            return

        if not stuck_rows:
            return

        logger.info("Detected %d stuck task(s)", len(stuck_rows))

        for row in stuck_rows:
            task_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
            agent_name = row["assigned_agent"] if isinstance(row, sqlite3.Row) else row[1]
            task_title = row["title"] if isinstance(row, sqlite3.Row) else row[2]
            trace_id = row["trace_id"] if isinstance(row, sqlite3.Row) else row[3]
            started_at = row["started_at"] if isinstance(row, sqlite3.Row) else row[4]
            lease_extensions = row["lease_extensions"] if isinstance(row, sqlite3.Row) else row[5]
            tool_calls_count = row["tool_calls_count"] if isinstance(row, sqlite3.Row) else row[6]

            # Skip if already being handled by this supervisor's active tasks
            with self._lock:
                if task_id in self._active_tasks:
                    continue

            # Transition to 'failed' so recovery pipeline can pick it up
            try:
                w_conn = get_writer_connection(self.db_path)
                cursor = w_conn.execute(
                    "UPDATE tasks SET dispatch_status = 'failed' "
                    "WHERE id = ? AND dispatch_status = 'dispatched'",
                    (task_id,),
                )
                if cursor.rowcount == 0:
                    w_conn.close()
                    continue  # Already transitioned by another process

                # Update dispatch_run with failure info
                w_conn.execute(
                    "UPDATE dispatch_runs SET status = 'failed', "
                    "error_summary = 'STUCK_TASK: task stuck in dispatched status with expired lease', "
                    "completed_at = datetime('now') "
                    "WHERE trace_id = ? AND status IN ('pending', 'running')",
                    (trace_id or "",),
                )
                w_conn.commit()
                w_conn.close()
            except sqlite3.Error:
                logger.exception("Failed to transition stuck task %s to failed", task_id)
                continue

            # Log detection event
            log_dispatch_event(
                logger=logger,
                level=logging.WARNING,
                message=f"Stuck task detected: task {task_id} ({task_title}) "
                        f"agent={agent_name} started_at={started_at} "
                        f"lease_extensions={lease_extensions} "
                        f"tool_calls_count={tool_calls_count}",
                trace_id=trace_id,
                agent_name=agent_name,
                task_id=str(task_id),
                extra={
                    "event_type": "recovery.stuck_task_detected",
                    "started_at": started_at,
                    "lease_extensions": lease_extensions,
                    "tool_calls_count": tool_calls_count,
                    "timeout_seconds": timeout_seconds,
                },
            )

            # Build task_dict and dispatch_run_row for recovery pipeline
            task_dict = {
                "id": task_id,
                "assigned_agent": agent_name,
                "title": task_title or "",
                "description": "",
                "domain": "",
            }
            # Create AgentRunnerError with STUCK_TASK context
            stuck_error = AgentRunnerError(
                f"STUCK_TASK: Task {task_id} stuck in dispatched status. "
                f"Lease expired, started_at={started_at}, "
                f"lease_extensions={lease_extensions}, "
                f"tool_calls_count={tool_calls_count}",
                stop_reason="stuck_task",
            )

            # Get attempt count for recovery
            attempt = self._get_attempt_count(task_id)

            # Trigger recovery pipeline
            self._handle_agent_failure(
                task_id=task_id,
                task_dict=task_dict,
                agent_name=agent_name or "unknown",
                trace_id=trace_id or str(uuid.uuid4()),
                attempt=attempt,
                error=stuck_error,
            )

            logger.warning(
                "Stuck task %s transitioned to 'failed' and sent to recovery pipeline",
                task_id,
            )

    # ── Heartbeat Loop ───────────────────────────────────────────

    def _heartbeat_loop(self) -> None:
        """Extend leases and enforce timeouts every 2 minutes."""
        while not self._heartbeat_stop.wait(timeout=_HEARTBEAT_INTERVAL_SECONDS):
            self._heartbeat_once()

    def _heartbeat_once(self) -> None:
        """Single heartbeat iteration: extend leases, enforce timeouts."""
        now = time.monotonic()

        with self._lock:
            active_copy = list(self._active_tasks.values())

        for at in active_copy:
            elapsed = now - at.started_at

            # Hard timeout enforcement
            if elapsed > self._timeout_seconds:
                logger.warning(
                    "Task %s exceeded timeout (%ds > %ds), cancelling",
                    at.task_id, int(elapsed), self._timeout_seconds,
                )
                at.future.cancel()
                # Record failure
                try:
                    handle_dispatch_failure(
                        task_id=at.task_id,
                        attempt=at.attempt,
                        error=f"Hard timeout exceeded ({int(elapsed)}s > {self._timeout_seconds}s)",
                        trace_id=at.trace_id,
                        adapter=self.adapter,
                    )
                except Exception:
                    logger.exception(
                        "Failed to record timeout failure for task %s", at.task_id
                    )
                # Remove from active
                with self._lock:
                    self._active_tasks.pop(at.task_id, None)
                continue

            # Extend lease
            try:
                conn = get_writer_connection(self.db_path)
                conn.execute(
                    "UPDATE tasks SET lease_until = datetime('now', '+' || ? || ' seconds') "
                    "WHERE id = ?",
                    (str(self._lease_seconds), at.task_id),
                )
                conn.commit()
                conn.close()
                logger.debug("Extended lease for task %s", at.task_id)
            except sqlite3.Error:
                logger.exception("Failed to extend lease for task %s", at.task_id)

    def _stop_heartbeat(self) -> None:
        """Signal heartbeat thread to stop and wait for it."""
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)

    # ── Health Check (US-057) ────────────────────────────────────

    def _run_health_check(self) -> None:
        """Run a health check against configured providers.

        Spawned in a background thread by SIGUSR2 handler. Logs results
        and records them in the provider_health table.
        """
        logger.info("Health check started (triggered by SIGUSR2)")
        try:
            from .provider_registry import get_provider

            provider_name = self.config.get("provider", {}).get("name", "unknown")
            model_name = self.config.get("provider", {}).get("model", "unknown")

            start = time.monotonic()
            provider = get_provider(self.config)
            latency_ms = (time.monotonic() - start) * 1000

            # Record success in provider_health table
            try:
                conn = get_writer_connection(self.db_path)
                conn.execute(
                    "INSERT INTO provider_health "
                    "(provider, model, test_name, passed, latency_ms) "
                    "VALUES (?, ?, 'sigusr2_health_check', 1, ?)",
                    (provider_name, model_name, latency_ms),
                )
                conn.commit()
                conn.close()
            except sqlite3.Error:
                logger.exception("Failed to record health check result")

            logger.info(
                "Health check passed: provider=%s model=%s latency=%.1fms",
                provider_name, model_name, latency_ms,
            )

        except Exception as e:
            logger.error("Health check failed: %s", e)
            try:
                provider_name = self.config.get("provider", {}).get("name", "unknown")
                model_name = self.config.get("provider", {}).get("model", "unknown")
                conn = get_writer_connection(self.db_path)
                conn.execute(
                    "INSERT INTO provider_health "
                    "(provider, model, test_name, passed, error_message) "
                    "VALUES (?, ?, 'sigusr2_health_check', 0, ?)",
                    (provider_name, model_name, str(e)[:500]),
                )
                conn.commit()
                conn.close()
            except sqlite3.Error:
                logger.exception("Failed to record health check failure")

    # ── Helper Methods ───────────────────────────────────────────

    def _reap_completed(self) -> None:
        """Remove completed futures from active tasks."""
        with self._lock:
            done_ids = [
                tid for tid, at in self._active_tasks.items() if at.future.done()
            ]
            for tid in done_ids:
                self._active_tasks.pop(tid, None)

    def _get_attempt_count(self, task_id: int) -> int:
        """Get the number of existing dispatch attempts for a task."""
        try:
            conn = get_reader_connection(self.db_path)
            row = conn.execute(
                "SELECT COUNT(*) FROM dispatch_runs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            return row[0] if row else 0
        except sqlite3.Error:
            return 0

    def _create_dispatch_run(
        self, task_id: int, agent_name: str, trace_id: str, attempt: int
    ) -> None:
        """Insert a new dispatch_run record with status='pending'."""
        try:
            provider_name = self.config.get("provider", {}).get("name", "unknown")
            model_name = self.config.get("provider", {}).get("model", "unknown")
            conn = get_writer_connection(self.db_path)
            conn.execute(
                "INSERT INTO dispatch_runs "
                "(task_id, agent_name, provider, model, status, attempt, trace_id) "
                "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (task_id, agent_name, provider_name, model_name, attempt, trace_id),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error:
            logger.exception(
                "Failed to create dispatch_run for task %s", task_id
            )

    def _update_dispatch_run_status(self, trace_id: str, status: str) -> None:
        """Update dispatch_run status (e.g., pending -> running)."""
        try:
            conn = get_writer_connection(self.db_path)
            conn.execute(
                "UPDATE dispatch_runs SET status = ?, started_at = datetime('now') "
                "WHERE trace_id = ? AND status = 'pending'",
                (status, trace_id),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error:
            logger.exception(
                "Failed to update dispatch_run status for trace %s", trace_id
            )
