"""OpenClawd Agent Dispatch System - Database Connection & Migration Module.

US-018: Provides run_migrations() for idempotent startup schema setup,
get_reader_connection() for long-lived poll connections, and
get_writer_connection() for short-lived claim/update connections.
All connections set WAL mode, busy_timeout=5000, and foreign_keys=ON.

US-049: Adds get_dispatchable_tasks(config, conn) for polling dispatchable
tasks with 7-condition WHERE clause and priority ordering.

US-050: Adds claim_task(task_id, lease_seconds, conn) for atomic task claiming
with dispatch_status and lease_until WHERE guards to prevent double-dispatch.

US-051: Adds handle_task_completion() for 4-step completion sequence with
Block A transaction, and recover_partial_completions() for recovery sweep.

US-052: Adds handle_dispatch_failure() for retry logic with exponential
backoff (immediate, +60s, +300s) and dispatch_failed escalation after 3 attempts.

US-053: Adds cascade_failure(task_id, conn, adapter) for dependency failure
cascading that propagates dispatch_failed status to all dependent tasks
with high-urgency notifications, recursively traversing the dependency graph.
"""

import datetime
import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from .config import DEFAULT_DB_PATH
from . import migrations

logger = logging.getLogger(__name__)

# ── Internal Helpers ─────────────────────────────────────────────

def _get_db_path():
    """Resolve coordination.db path from env var or default fallback."""
    return os.environ.get("OPENCLAWD_DB_PATH", DEFAULT_DB_PATH)


def _configure_connection(conn):
    """Apply standard PRAGMAs to a connection.

    Sets WAL journal mode, 5-second busy timeout, and enables foreign keys.
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")


def _detect_network_filesystem(db_path):
    """Warn if the database file resides on a network filesystem.

    SQLite WAL mode is unreliable on NFS, SMB, and other network mounts.
    """
    real_path = os.path.realpath(db_path)
    try:
        result = os.statvfs(real_path)
        # Check common NFS/SMB f_type values (Linux)
        # On macOS statvfs doesn't expose f_type, so we fall back to mount check
    except (AttributeError, OSError):
        pass

    # Heuristic: check if path is under common network mount points
    network_indicators = ["/Volumes/", "/mnt/nfs", "/mnt/smb", "/mnt/cifs"]
    for indicator in network_indicators:
        if indicator in real_path:
            logger.warning(
                "coordination.db appears to be on a network filesystem (%s). "
                "SQLite WAL mode is unreliable on NFS/SMB mounts. "
                "Consider using a local path instead.",
                real_path,
            )
            return True

    # Check /proc/mounts on Linux for NFS/CIFS mount types
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3:
                    mount_point = parts[1]
                    fs_type = parts[2]
                    if (
                        real_path.startswith(mount_point)
                        and fs_type in ("nfs", "nfs4", "cifs", "smbfs")
                    ):
                        logger.warning(
                            "coordination.db is on a %s filesystem at %s. "
                            "SQLite WAL mode is unreliable on network filesystems.",
                            fs_type,
                            mount_point,
                        )
                        return True
    except (FileNotFoundError, PermissionError):
        pass  # Not Linux or no access to /proc/mounts

    return False


# ── Reader Connection (Long-lived) ──────────────────────────────

_reader_connection = None


def get_reader_connection(db_path=None):
    """Return a long-lived reader connection for poll queries.

    The connection is cached as a module-level singleton. It uses
    autocommit mode (isolation_level=None) since read-only queries
    don't need explicit transactions.
    """
    global _reader_connection
    if _reader_connection is not None:
        try:
            _reader_connection.execute("SELECT 1")
            return _reader_connection
        except sqlite3.Error:
            _reader_connection = None

    path = db_path or _get_db_path()
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    _configure_connection(conn)
    _reader_connection = conn
    return conn


# ── Writer Connection (Short-lived) ─────────────────────────────


def get_writer_connection(db_path=None):
    """Return a new short-lived writer connection for claims and updates.

    Each call creates a fresh connection with DEFERRED transaction isolation.
    Callers are responsible for committing and closing the connection.
    """
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path, isolation_level="DEFERRED")
    conn.row_factory = sqlite3.Row
    _configure_connection(conn)
    return conn


# ── Dispatchable Task Query ──────────────────────────────────────


def get_dispatchable_tasks(config, conn=None):
    """US-049: Query for tasks ready to be dispatched.

    Checks all 7 conditions:
      1. status IN ('open', 'in_progress')
      2. dispatch_status IS NULL OR dispatch_status = 'queued'
      3. lease_until IS NULL OR lease_until < CURRENT_TIMESTAMP
      4. All task_dependencies reference completed tasks
      5. No dispatch_runs with next_retry_at > CURRENT_TIMESTAMP
      6. Global daily budget not exceeded
      7. Per-agent budget not exceeded for assigned_agent

    Orders by priority DESC, created_at ASC.
    Returns list of dicts with all task columns.
    """
    close_conn = False
    if conn is None:
        conn = get_reader_connection()
        close_conn = False  # reader is cached singleton, don't close

    today = datetime.date.today().isoformat()
    global_budget = float(config.get("daily_budget_usd", 999999.0))
    agent_budgets = config.get("agent_budgets", {})

    # Check global budget first - if exceeded, no tasks are dispatchable
    cursor = conn.execute(
        "SELECT COALESCE(SUM(total_cost_usd), 0.0) FROM daily_usage WHERE date = ?",
        (today,),
    )
    global_spent = cursor.fetchone()[0]
    if global_spent >= global_budget:
        logger.info(
            "Global daily budget exceeded (%.2f >= %.2f), no tasks dispatchable",
            global_spent,
            global_budget,
        )
        return []

    # Main query with conditions 1-5
    rows = conn.execute(
        """
        SELECT t.*
        FROM tasks t
        WHERE
            -- Condition 1: task status is open or in_progress
            t.status IN ('open', 'in_progress')
            -- Condition 2: not already dispatched/completed/failed
            AND (t.dispatch_status IS NULL OR t.dispatch_status = 'queued')
            -- Condition 3: no active lease
            AND (t.lease_until IS NULL OR t.lease_until < datetime('now'))
            -- Condition 4: all dependencies are completed
            AND NOT EXISTS (
                SELECT 1 FROM task_dependencies td
                JOIN tasks dep ON dep.id = td.depends_on_task_id
                WHERE td.task_id = t.id
                AND dep.status != 'completed'
            )
            -- Condition 5: no pending retry backoff
            AND NOT EXISTS (
                SELECT 1 FROM dispatch_runs dr
                WHERE dr.task_id = t.id
                AND dr.next_retry_at > datetime('now')
            )
        ORDER BY t.priority DESC, t.created_at ASC
        """
    ).fetchall()

    # Filter by per-agent budget (condition 7)
    results = []
    # Cache per-agent spending to avoid repeated queries
    agent_spent_cache = {}

    for row in rows:
        task = dict(row)
        agent = task.get("assigned_agent")

        if agent and agent in agent_budgets:
            agent_limit = float(agent_budgets[agent])
            if agent not in agent_spent_cache:
                cur = conn.execute(
                    "SELECT COALESCE(SUM(total_cost_usd), 0.0) "
                    "FROM daily_usage WHERE date = ? AND agent_name = ?",
                    (today, agent),
                )
                agent_spent_cache[agent] = cur.fetchone()[0]

            if agent_spent_cache[agent] >= agent_limit:
                logger.debug(
                    "Agent %s daily budget exceeded (%.2f >= %.2f), skipping task %s",
                    agent,
                    agent_spent_cache[agent],
                    agent_limit,
                    task.get("id"),
                )
                continue

        results.append(task)

    return results


# ── Atomic Task Claim ────────────────────────────────────────────


def claim_task(task_id, lease_seconds, conn=None):
    """US-050: Atomically claim a task by setting dispatch_status and lease_until.

    Executes UPDATE with WHERE guards on dispatch_status and lease_until so that
    concurrent supervisors cannot double-dispatch the same task. Returns True if
    the claim succeeded (rowcount > 0), False if the task was already claimed by
    another supervisor (rowcount == 0).

    Args:
        task_id: The ID of the task to claim.
        lease_seconds: Number of seconds for the lease duration.
        conn: Optional writer connection. If None, a new writer connection is
              created and managed (committed + closed) by this function.
    """
    close_conn = conn is None
    if conn is None:
        conn = get_writer_connection()

    try:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET dispatch_status = 'dispatched',
                lease_until = datetime('now', '+' || ? || ' seconds')
            WHERE id = ?
              AND (dispatch_status IS NULL
                   OR dispatch_status IN ('queued', 'failed', 'interrupted'))
              AND (lease_until IS NULL
                   OR lease_until < CURRENT_TIMESTAMP)
            """,
            (str(lease_seconds), task_id),
        )
        if close_conn:
            conn.commit()
        claimed = cursor.rowcount > 0
        if claimed:
            logger.debug("Claimed task %s with %ds lease", task_id, lease_seconds)
        else:
            logger.debug("Failed to claim task %s (already claimed or ineligible)", task_id)
        return claimed
    except sqlite3.Error:
        logger.exception("Error claiming task %s", task_id)
        if close_conn:
            conn.rollback()
        return False
    finally:
        if close_conn:
            conn.close()


# ── Task Completion Sequence ─────────────────────────────────────


class TaskCompletionError(Exception):
    """Raised when task completion sequence fails."""
    pass


def _validate_agent_result_schema(agent_result) -> None:
    """Validate that agent_result has required fields for completion.

    Args:
        agent_result: AgentResult dataclass or dict with status field.

    Raises:
        TaskCompletionError: If required fields are missing or invalid.
    """
    if agent_result is None:
        raise TaskCompletionError("agent_result is None")

    # Support both dataclass (has .status attr) and dict
    if hasattr(agent_result, "status"):
        status = agent_result.status
    elif isinstance(agent_result, dict):
        status = agent_result.get("status")
    else:
        raise TaskCompletionError(
            f"agent_result must be AgentResult or dict, got {type(agent_result).__name__}"
        )

    if not status:
        raise TaskCompletionError("agent_result missing required field: status")


def handle_task_completion(
    task_id: int,
    agent_result,
    trace_id: str,
    config: Dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
    adapter=None,
) -> bool:
    """US-051: Execute the 4-step task completion sequence.

    Step 1: Validate AgentResult schema
    Step 2 (Block A): Single transaction - SET dispatch_status='completed',
        upsert working_memory, update dispatch_run, write daily_usage
    Step 3: adapter.add_task_contribution(task_id, agent_name, 'deliverable', content)
    Step 4: adapter.complete_task(task_id, agent_name, deliverable_url)

    If any step after Block A fails, logs critical error but does not
    roll back Block A (it already committed).

    Args:
        task_id: The task ID to complete.
        agent_result: AgentResult dataclass or dict with completion data.
        trace_id: Trace ID for the dispatch run.
        config: Parsed config dict.
        conn: Optional writer connection. If None, creates a new one.
        adapter: Optional OpenClawdAdapter instance for steps 3-4.

    Returns:
        True if all steps succeeded, False if any step after Block A failed.

    Raises:
        TaskCompletionError: If schema validation fails (before any writes).
    """
    # ── Step 1: Validate AgentResult schema ──
    _validate_agent_result_schema(agent_result)

    # Extract fields from agent_result (support dataclass or dict)
    if hasattr(agent_result, "status"):
        status = agent_result.status
        deliverable_content = getattr(agent_result, "deliverable_content", "")
        deliverable_url = getattr(agent_result, "deliverable_url", "")
        working_memory_entries = getattr(agent_result, "working_memory_entries", None) or []
        raw_response = getattr(agent_result, "raw_response", "")
    else:
        status = agent_result.get("status", "")
        deliverable_content = agent_result.get("deliverable_content", "")
        deliverable_url = agent_result.get("deliverable_url", "")
        working_memory_entries = agent_result.get("working_memory_entries") or []
        raw_response = agent_result.get("raw_response", "")

    # Determine agent_name from dispatch_runs
    close_conn = conn is None
    if conn is None:
        conn = get_writer_connection()

    agent_name = ""
    try:
        row = conn.execute(
            "SELECT agent_name FROM dispatch_runs WHERE trace_id = ? ORDER BY id DESC LIMIT 1",
            (trace_id,),
        ).fetchone()
        if row:
            agent_name = row["agent_name"] if isinstance(row, sqlite3.Row) else row[0]
    except sqlite3.Error:
        logger.warning("Could not determine agent_name from trace_id %s", trace_id)

    # ── Step 2 (Block A): Single transaction ──
    try:
        # 2a: SET dispatch_status='completed'
        conn.execute(
            "UPDATE tasks SET dispatch_status = 'completed' WHERE id = ?",
            (task_id,),
        )

        # 2b: Upsert working_memory entries
        for entry in working_memory_entries:
            key = entry.get("key")
            value = entry.get("value", "")
            entry_agent = entry.get("agent_name", agent_name)
            if not key:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO working_memory "
                "(task_id, agent_name, key, value) VALUES (?, ?, ?, ?)",
                (task_id, entry_agent, str(key), str(value)),
            )

        # 2c: Update dispatch_run status
        conn.execute(
            "UPDATE dispatch_runs SET status = 'completed', "
            "completed_at = datetime('now'), "
            "output_file = ? "
            "WHERE trace_id = ? AND status = 'running'",
            (raw_response[:1000] if raw_response else "", trace_id),
        )

        # 2d: Write daily_usage
        today = datetime.date.today().isoformat()
        provider_name = config.get("provider", {}).get("name", "unknown")
        model_name = config.get("provider", {}).get("model", "unknown")
        # Use INSERT OR REPLACE with the UNIQUE constraint on (date, provider, model, agent_name)
        conn.execute(
            "INSERT INTO daily_usage (date, provider, model, agent_name, total_tokens, total_cost_usd, task_count) "
            "VALUES (?, ?, ?, ?, 0, 0.0, 1) "
            "ON CONFLICT(date, provider, model, agent_name) "
            "DO UPDATE SET task_count = task_count + 1",
            (today, provider_name, model_name, agent_name or "unknown"),
        )

        conn.commit()
        logger.info(
            "Block A committed for task %s (trace_id=%s)", task_id, trace_id
        )
    except sqlite3.Error as e:
        logger.critical(
            "Block A transaction failed for task %s: %s", task_id, e
        )
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        if close_conn:
            conn.close()
        raise TaskCompletionError(f"Block A transaction failed: {e}") from e

    if close_conn:
        conn.close()

    # ── Step 3: adapter.add_task_contribution ──
    all_succeeded = True
    if adapter is not None:
        try:
            adapter.add_task_contribution(
                task_id=task_id,
                agent_name=agent_name,
                contribution_type="deliverable",
                content=deliverable_content,
            )
            logger.info(
                "Step 3 (add_task_contribution) succeeded for task %s", task_id
            )
        except Exception as e:
            logger.critical(
                "Step 3 (add_task_contribution) failed for task %s: %s",
                task_id, e,
            )
            all_succeeded = False

        # ── Step 4: adapter.complete_task ──
        if all_succeeded:
            try:
                adapter.complete_task(
                    task_id=task_id,
                    agent_name=agent_name,
                    deliverable_url=deliverable_url or None,
                )
                logger.info(
                    "Step 4 (complete_task) succeeded for task %s", task_id
                )
            except Exception as e:
                logger.critical(
                    "Step 4 (complete_task) failed for task %s: %s",
                    task_id, e,
                )
                all_succeeded = False

    return all_succeeded


def recover_partial_completions(
    conn: Optional[sqlite3.Connection] = None,
    adapter=None,
    config: Optional[Dict[str, Any]] = None,
) -> List[int]:
    """US-051: Recovery sweep for partially-completed tasks.

    Finds tasks where dispatch_status='completed' but status!='completed',
    indicating Block A succeeded but steps 3-4 failed. Retries from the
    last successful step (checks dispatch_runs for Block A completion,
    working_memory for step 3 evidence).

    Creates urgent notification after 3 failed recovery attempts.

    Args:
        conn: Optional reader connection for querying.
        adapter: Optional OpenClawdAdapter for retrying steps 3-4.
        config: Optional config dict.

    Returns:
        List of task IDs that were successfully recovered.
    """
    if config is None:
        config = {}

    read_conn = conn if conn is not None else get_reader_connection()

    # Find partially-completed tasks
    try:
        rows = read_conn.execute(
            "SELECT t.id, t.assigned_agent, t.dispatch_status, t.status "
            "FROM tasks t "
            "WHERE t.dispatch_status = 'completed' AND t.status != 'completed'"
        ).fetchall()
    except sqlite3.Error as e:
        logger.error("Failed to query partial completions: %s", e)
        return []

    if not rows:
        return []

    logger.info("Found %d partially-completed tasks for recovery", len(rows))
    recovered = []

    for row in rows:
        task_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
        agent_name = row["assigned_agent"] if isinstance(row, sqlite3.Row) else row[1]

        if adapter is None:
            logger.warning(
                "No adapter available for recovery of task %s", task_id
            )
            continue

        # Check how many recovery attempts have been made
        # (count dispatch_runs with status='completed' for this task)
        try:
            attempt_row = read_conn.execute(
                "SELECT COUNT(*) FROM dispatch_runs "
                "WHERE task_id = ? AND status = 'completed'",
                (task_id,),
            ).fetchone()
            attempt_count = attempt_row[0] if attempt_row else 0
        except sqlite3.Error:
            attempt_count = 0

        if attempt_count >= 3:
            # Create urgent notification after 3 failed recovery attempts
            logger.critical(
                "Task %s has %d recovery attempts, creating urgent notification",
                task_id, attempt_count,
            )
            try:
                adapter.create_notification(
                    task_id=task_id,
                    message=(
                        f"Task {task_id} stuck in partial completion after "
                        f"{attempt_count} recovery attempts. "
                        f"dispatch_status='completed' but status != 'completed'. "
                        f"Manual intervention required."
                    ),
                    urgency="urgent",
                )
            except Exception as e:
                logger.error(
                    "Failed to create urgent notification for task %s: %s",
                    task_id, e,
                )
            continue

        # Determine which step to retry from
        # Check if working_memory has entries for this task (Step 3 evidence)
        has_contribution = False
        try:
            wm_row = read_conn.execute(
                "SELECT COUNT(*) FROM working_memory WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            has_contribution = (wm_row[0] if wm_row else 0) > 0
        except sqlite3.Error:
            pass

        # Get deliverable info from dispatch_runs
        deliverable_content = ""
        deliverable_url = ""
        try:
            dr_row = read_conn.execute(
                "SELECT output_file FROM dispatch_runs "
                "WHERE task_id = ? AND status = 'completed' "
                "ORDER BY id DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if dr_row:
                deliverable_content = (
                    dr_row["output_file"] if isinstance(dr_row, sqlite3.Row) else dr_row[0]
                ) or ""
        except sqlite3.Error:
            pass

        # Retry from last failed step
        try:
            if not has_contribution:
                # Retry Step 3: add_task_contribution
                adapter.add_task_contribution(
                    task_id=task_id,
                    agent_name=agent_name or "unknown",
                    contribution_type="deliverable",
                    content=deliverable_content,
                )
                logger.info("Recovery Step 3 succeeded for task %s", task_id)

            # Retry Step 4: complete_task
            adapter.complete_task(
                task_id=task_id,
                agent_name=agent_name or "unknown",
                deliverable_url=deliverable_url or None,
            )
            logger.info("Recovery Step 4 succeeded for task %s", task_id)
            recovered.append(task_id)

        except Exception as e:
            logger.critical(
                "Recovery failed for task %s (attempt %d): %s",
                task_id, attempt_count + 1, e,
            )

    return recovered


# ── Dispatch Failure & Retry Logic ───────────────────────────────

# Backoff schedule: attempt → seconds to add for next_retry_at
_BACKOFF_SCHEDULE = {
    1: None,   # immediate retry (next_retry_at = NULL)
    2: 60,     # +60 seconds
    3: 300,    # +300 seconds
}

_MAX_RETRIES = 3


def handle_dispatch_failure(
    task_id: int,
    attempt: int,
    error: str,
    trace_id: str,
    conn: Optional[sqlite3.Connection] = None,
    adapter=None,
) -> None:
    """US-052: Handle a failed dispatch run with exponential backoff.

    Updates the dispatch_run with status='failed' and error_summary.
    Sets next_retry_at based on attempt number:
      - Attempt 1: NULL (immediate retry)
      - Attempt 2: +60 seconds
      - Attempt 3: +300 seconds

    For retryable failures (attempt < 3), sets task dispatch_status='failed'.
    When max retries exceeded (attempt >= 3), sets dispatch_status='dispatch_failed'
    and creates an urgent notification.

    Args:
        task_id: The task ID that failed.
        attempt: Current attempt number (1-based).
        error: Error message/summary.
        trace_id: Trace ID for the dispatch run.
        conn: Optional writer connection. If None, creates a new one.
        adapter: Optional OpenClawdAdapter for creating notifications.
    """
    close_conn = conn is None
    if conn is None:
        conn = get_writer_connection()

    error_summary = str(error)[:500] if error else "Unknown error"

    try:
        # Update dispatch_run with failure status and error
        backoff_seconds = _BACKOFF_SCHEDULE.get(attempt)

        if backoff_seconds is not None:
            # Set next_retry_at to future time
            conn.execute(
                "UPDATE dispatch_runs "
                "SET status = 'failed', "
                "    error_summary = ?, "
                "    completed_at = datetime('now'), "
                "    next_retry_at = datetime('now', '+' || ? || ' seconds') "
                "WHERE trace_id = ? AND status = 'running'",
                (error_summary, str(backoff_seconds), trace_id),
            )
        else:
            # Attempt 1: immediate retry (next_retry_at = NULL)
            conn.execute(
                "UPDATE dispatch_runs "
                "SET status = 'failed', "
                "    error_summary = ?, "
                "    completed_at = datetime('now'), "
                "    next_retry_at = NULL "
                "WHERE trace_id = ? AND status = 'running'",
                (error_summary, trace_id),
            )

        if attempt >= _MAX_RETRIES:
            # Max retries exceeded: mark as dispatch_failed
            conn.execute(
                "UPDATE tasks SET dispatch_status = 'dispatch_failed' WHERE id = ?",
                (task_id,),
            )
            logger.warning(
                "Task %s exceeded max retries (%d), dispatch_status='dispatch_failed'",
                task_id, _MAX_RETRIES,
            )
        else:
            # Retryable: set dispatch_status='failed' so it can be picked up again
            conn.execute(
                "UPDATE tasks SET dispatch_status = 'failed' WHERE id = ?",
                (task_id,),
            )
            logger.info(
                "Task %s dispatch attempt %d failed, will retry (backoff=%s)",
                task_id, attempt,
                f"{backoff_seconds}s" if backoff_seconds else "immediate",
            )

        conn.commit()

    except sqlite3.Error as e:
        logger.error(
            "Failed to record dispatch failure for task %s: %s", task_id, e
        )
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        if close_conn:
            conn.close()
        return

    if close_conn:
        conn.close()

    # Create urgent notification when max retries exceeded
    if attempt >= _MAX_RETRIES and adapter is not None:
        try:
            adapter.create_notification(
                task_id=task_id,
                message=(
                    f"Task {task_id} failed after {attempt} dispatch attempts. "
                    f"Last error: {error_summary}. "
                    f"dispatch_status set to 'dispatch_failed'. "
                    f"Manual intervention required."
                ),
                urgency="urgent",
            )
            logger.info(
                "Created urgent notification for task %s max retries exceeded",
                task_id,
            )
        except Exception as e:
            logger.error(
                "Failed to create urgent notification for task %s: %s",
                task_id, e,
            )


# ── Dependency Failure Cascading ─────────────────────────────────


def cascade_failure(
    task_id: int,
    conn: Optional[sqlite3.Connection] = None,
    adapter=None,
) -> List[int]:
    """US-053: Cascade dispatch_failed status to all dependent tasks.

    When a task fails permanently (dispatch_failed), all tasks that depend
    on it are also marked as dispatch_failed since they can never run.
    Recursively cascades through the entire dependency graph.

    Creates a high-urgency notification for each affected dependent task
    indicating which upstream task caused the failure.

    Args:
        task_id: The failed task ID whose dependents should be cascaded.
        conn: Optional writer connection. If None, creates a new one.
        adapter: Optional OpenClawdAdapter for creating notifications.

    Returns:
        List of task IDs that were marked as dispatch_failed.
    """
    close_conn = conn is None
    if conn is None:
        conn = get_writer_connection()

    cascaded = []
    # Track visited task IDs to avoid infinite loops in case of circular deps
    visited = set()

    def _cascade(failed_task_id: int) -> None:
        if failed_task_id in visited:
            return
        visited.add(failed_task_id)

        # Find all tasks that depend on the failed task
        try:
            rows = conn.execute(
                "SELECT td.task_id FROM task_dependencies td "
                "WHERE td.depends_on_task_id = ?",
                (failed_task_id,),
            ).fetchall()
        except sqlite3.Error as e:
            logger.error(
                "Failed to query dependents of task %s: %s",
                failed_task_id, e,
            )
            return

        for row in rows:
            dependent_id = row["task_id"] if isinstance(row, sqlite3.Row) else row[0]

            # Skip if already visited (handles diamond dependencies)
            if dependent_id in visited:
                continue

            # Mark dependent as dispatch_failed
            try:
                conn.execute(
                    "UPDATE tasks SET dispatch_status = 'dispatch_failed' "
                    "WHERE id = ?",
                    (dependent_id,),
                )
                cascaded.append(dependent_id)
                logger.info(
                    "Cascaded dispatch_failed to task %s (upstream failure: task %s)",
                    dependent_id, failed_task_id,
                )
            except sqlite3.Error as e:
                logger.error(
                    "Failed to cascade dispatch_failed to task %s: %s",
                    dependent_id, e,
                )
                continue

            # Create high-urgency notification
            if adapter is not None:
                try:
                    adapter.create_notification(
                        task_id=dependent_id,
                        message=(
                            f"Task {dependent_id} marked as dispatch_failed: "
                            f"upstream dependency task {failed_task_id} failed permanently. "
                            f"This task cannot proceed until the upstream failure is resolved."
                        ),
                        urgency="high",
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to create cascade notification for task %s: %s",
                        dependent_id, e,
                    )

            # Recursively cascade to dependents of this dependent
            _cascade(dependent_id)

    _cascade(task_id)

    # Commit all changes in one transaction
    try:
        conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to commit cascade_failure transaction: %s", e)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        if close_conn:
            conn.close()
        return []

    if close_conn:
        conn.close()

    if cascaded:
        logger.info(
            "Cascaded dispatch_failed from task %s to %d dependent tasks: %s",
            task_id, len(cascaded), cascaded,
        )

    return cascaded


# ── Interrupted Task Recovery ─────────────────────────────────────


def recover_interrupted_tasks(
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str] = None,
) -> List[int]:
    """US-056/US-038: Recover tasks marked 'interrupted' or 'recovering' on supervisor restart.

    Queries all tasks with dispatch_status='interrupted' and re-queues them
    by setting dispatch_status='queued' and lease_until=NULL, incrementing
    the retry attempt counter.

    Also queries tasks with dispatch_status='recovering' (crashed recovery
    pipeline) and resets them to dispatch_status='failed' so they re-enter
    the recovery pipeline on the next poll cycle.

    Args:
        conn: Optional writer connection. If None, creates a new one.
        db_path: Optional database path override.

    Returns:
        List of task IDs that were recovered.
    """
    close_conn = conn is None
    if conn is None:
        conn = get_writer_connection(db_path)

    # --- Phase 1: Recover 'interrupted' tasks (US-056) ---
    try:
        rows = conn.execute(
            "SELECT id, assigned_agent FROM tasks WHERE dispatch_status = 'interrupted'"
        ).fetchall()
    except sqlite3.Error as e:
        logger.error("Failed to query interrupted tasks: %s", e)
        if close_conn:
            conn.close()
        return []

    recovered = []

    for row in rows:
        task_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
        agent_name = row["assigned_agent"] if isinstance(row, sqlite3.Row) else row[1]

        try:
            # Re-queue the task
            conn.execute(
                "UPDATE tasks SET dispatch_status = 'queued', lease_until = NULL "
                "WHERE id = ?",
                (task_id,),
            )

            # Get current attempt count for this task
            attempt_row = conn.execute(
                "SELECT COUNT(*) FROM dispatch_runs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            attempt_count = (attempt_row[0] if attempt_row else 0) + 1

            # Insert a new dispatch_run to track the recovery attempt
            conn.execute(
                "INSERT INTO dispatch_runs "
                "(task_id, agent_name, provider, model, status, attempt, trace_id, "
                " error_summary) "
                "VALUES (?, ?, 'recovery', 'recovery', 'failed', ?, ?, ?)",
                (
                    task_id,
                    agent_name or "unknown",
                    attempt_count,
                    f"recovery-{task_id}-{attempt_count}",
                    "Recovered from interrupted state on supervisor restart",
                ),
            )

            recovered.append(task_id)
            logger.info(
                "Recovered interrupted task %s (attempt %d), re-queued for dispatch",
                task_id, attempt_count,
            )

        except sqlite3.Error as e:
            logger.error("Failed to recover interrupted task %s: %s", task_id, e)

    # --- Phase 2: Reset 'recovering' tasks to 'failed' (US-038) ---
    recovering_count = 0
    try:
        recovering_rows = conn.execute(
            "SELECT id FROM tasks WHERE dispatch_status = 'recovering'"
        ).fetchall()

        for row in recovering_rows:
            task_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
            try:
                conn.execute(
                    "UPDATE tasks SET dispatch_status = 'failed', lease_until = NULL "
                    "WHERE id = ? AND dispatch_status = 'recovering'",
                    (task_id,),
                )
                recovered.append(task_id)
                recovering_count += 1
            except sqlite3.Error as e:
                logger.error(
                    "Failed to reset recovering task %s to failed: %s", task_id, e
                )

        if recovering_count > 0:
            logger.info(
                "Reset %d recovering task(s) to 'failed' for re-entry into recovery pipeline",
                recovering_count,
            )
    except sqlite3.Error as e:
        logger.error("Failed to query recovering tasks: %s", e)

    # --- Phase 3: Clear stale 'queued' tasks with expired leases ---
    # Safety net: prior to the dispatched-status fix, claim_task set
    # dispatch_status='queued' instead of 'dispatched', so tasks could be
    # left with stale leases that block re-claiming on restart.
    stale_count = 0
    try:
        stale_rows = conn.execute(
            "SELECT id FROM tasks "
            "WHERE dispatch_status = 'queued' "
            "AND lease_until IS NOT NULL "
            "AND lease_until < datetime('now')"
        ).fetchall()

        for row in stale_rows:
            task_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
            try:
                conn.execute(
                    "UPDATE tasks SET lease_until = NULL "
                    "WHERE id = ? AND dispatch_status = 'queued' "
                    "AND lease_until IS NOT NULL AND lease_until < datetime('now')",
                    (task_id,),
                )
                recovered.append(task_id)
                stale_count += 1
            except sqlite3.Error as e:
                logger.error(
                    "Failed to clear stale lease on queued task %s: %s", task_id, e
                )

        if stale_count > 0:
            logger.info(
                "Cleared stale leases on %d queued task(s) for re-dispatch",
                stale_count,
            )
    except sqlite3.Error as e:
        logger.error("Failed to query stale queued tasks: %s", e)

    if not recovered:
        logger.debug("No interrupted, recovering, or stale tasks to recover")
        if close_conn:
            conn.close()
        return []

    # Commit all recovery changes in one transaction
    try:
        conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to commit interrupted task recovery: %s", e)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        if close_conn:
            conn.close()
        return []

    if close_conn:
        conn.close()

    if recovered:
        logger.info(
            "Recovered %d task(s) on startup (interrupted + recovering + stale): %s",
            len(recovered), recovered,
        )

    return recovered


# ── Migrations ──────────────────────────────────────────────────


def run_migrations(db_path=None):
    """Execute all schema migrations idempotently.

    Calls every migrate_* function from the migrations module in the
    correct order (ALTER TABLE first, then CREATE TABLE).
    Detects network filesystem before running.
    """
    path = db_path or _get_db_path()

    _detect_network_filesystem(path)

    # ALTER TABLE migrations (must run first)
    migrations.migrate_add_dispatch_status(path)
    migrations.migrate_add_lease_until(path)

    # Index migrations
    migrations.migrate_create_dispatch_index(path)

    # CREATE TABLE migrations
    migrations.migrate_create_dispatch_runs(path)
    migrations.migrate_create_task_dependencies(path)
    migrations.migrate_create_working_memory(path)
    migrations.migrate_create_daily_usage(path)
    migrations.migrate_create_provider_health(path)
    migrations.migrate_create_provider_incidents(path)
    migrations.migrate_create_audit_log(path)

    # Archive table (after ALTER TABLE migrations so schema is in sync)
    migrations.migrate_create_tasks_archive(path)

    # Summary tables
    migrations.migrate_create_health_daily_summary(path)

    # NOT NULL constraint fixes (idempotent — skip if already correct)
    migrations.migrate_dispatch_runs_trace_id_not_null(path)
    migrations.migrate_audit_log_not_null_fixes(path)
    migrations.migrate_working_memory_value_not_null(path)

    # Recovery pipeline columns (self-healing system)
    migrations.migrate_add_recovery_columns_to_dispatch_runs(path)

    # Add 'recovering' to dispatch_status CHECK constraint (self-healing system)
    migrations.migrate_add_recovering_dispatch_status(path)

    # Create failure_memory table (self-healing system)
    migrations.migrate_create_failure_memory(path)

    # Create recovery_events table (self-healing system)
    migrations.migrate_create_recovery_events(path)

    # Create intent_ledger table (intention integrity system)
    migrations.migrate_create_intent_ledger(path)

    logger.info("All dispatch schema migrations completed successfully.")


def close_reader_connection():
    """Close the cached reader connection if open."""
    global _reader_connection
    if _reader_connection is not None:
        try:
            _reader_connection.close()
        except sqlite3.Error:
            pass
        _reader_connection = None


# ── Cost Tracking & Budget Enforcement (US-066) ─────────────────


def record_cost(
    date: str,
    provider: str,
    model: str,
    agent_name: str,
    tokens_used: int,
    cost_estimate: float,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """US-066: Record cost by upserting to daily_usage table.

    Uses INSERT ... ON CONFLICT to increment total_tokens, total_cost_usd,
    and task_count atomically, leveraging the UNIQUE(date, provider, model,
    agent_name) constraint.

    Args:
        date: ISO date string (e.g. '2026-02-14').
        provider: Provider name (e.g. 'anthropic').
        model: Model name (e.g. 'claude-sonnet-4-5').
        agent_name: Agent name (e.g. 'research').
        tokens_used: Number of tokens used in this dispatch.
        cost_estimate: Estimated cost in USD for this dispatch.
        conn: Optional writer connection. If None, creates and manages one.
    """
    close_conn = conn is None
    if conn is None:
        conn = get_writer_connection()

    try:
        conn.execute(
            "INSERT INTO daily_usage (date, provider, model, agent_name, "
            "total_tokens, total_cost_usd, task_count) "
            "VALUES (?, ?, ?, ?, ?, ?, 1) "
            "ON CONFLICT(date, provider, model, agent_name) "
            "DO UPDATE SET "
            "  total_tokens = total_tokens + excluded.total_tokens, "
            "  total_cost_usd = total_cost_usd + excluded.total_cost_usd, "
            "  task_count = task_count + 1",
            (date, provider, model, agent_name, tokens_used, cost_estimate),
        )
        if close_conn:
            conn.commit()
        logger.debug(
            "Recorded cost: date=%s provider=%s model=%s agent=%s "
            "tokens=%d cost=%.6f",
            date, provider, model, agent_name, tokens_used, cost_estimate,
        )
    except sqlite3.Error as e:
        logger.error("Failed to record cost: %s", e)
        if close_conn:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
        raise
    finally:
        if close_conn:
            conn.close()


def calculate_cost(
    provider: str,
    model: str,
    token_usage: Dict[str, int],
    config: Dict[str, Any],
) -> float:
    """US-068: Calculate cost estimate from token usage and configured pricing.

    Reads pricing section from config, multiplies input_tokens by
    input_per_1m_tokens and output_tokens by output_per_1m_tokens,
    divides by 1_000_000. Warns if pricing_updated_at is older than 90 days.

    Args:
        provider: Provider name (e.g. 'anthropic', 'openai').
        model: Model name (e.g. 'claude-sonnet-4-5').
        token_usage: Dict with 'input_tokens' and 'output_tokens' keys.
        config: Parsed openclawd.config.yaml dict.

    Returns:
        Cost estimate in USD as float.

    Raises:
        ValueError: If pricing is not configured for the provider/model.
    """
    pricing = config.get("pricing", {})
    if not isinstance(pricing, dict):
        raise ValueError(
            f"Pricing not configured for provider '{provider}' model '{model}'"
        )

    provider_pricing = pricing.get(provider)
    if not isinstance(provider_pricing, dict):
        raise ValueError(
            f"Pricing not configured for provider '{provider}'"
        )

    model_pricing = provider_pricing.get(model)
    if not isinstance(model_pricing, dict):
        raise ValueError(
            f"Pricing not configured for provider '{provider}' model '{model}'"
        )

    input_price = model_pricing.get("input_per_1m_tokens", 0)
    output_price = model_pricing.get("output_per_1m_tokens", 0)

    input_tokens = token_usage.get("input_tokens", 0)
    output_tokens = token_usage.get("output_tokens", 0)

    cost_estimate = (
        input_tokens * input_price + output_tokens * output_price
    ) / 1_000_000

    # Check pricing staleness
    pricing_updated_at = config.get("pricing_updated_at")
    if pricing_updated_at:
        try:
            if isinstance(pricing_updated_at, str):
                updated_date = datetime.datetime.fromisoformat(pricing_updated_at)
            else:
                updated_date = pricing_updated_at
            age = datetime.datetime.now() - updated_date
            if age.days > 90:
                logger.warning(
                    "Pricing data is %d days old (updated: %s). "
                    "Consider updating pricing in config.",
                    age.days,
                    pricing_updated_at,
                )
        except (ValueError, TypeError) as e:
            logger.warning("Could not parse pricing_updated_at: %s", e)
    else:
        logger.warning(
            "No pricing_updated_at in config. "
            "Consider adding a date to track pricing freshness."
        )

    return cost_estimate


def check_budget(
    config: Dict[str, Any],
    agent_name: str,
    conn: Optional[sqlite3.Connection] = None,
    adapter=None,
) -> Dict[str, bool]:
    """US-066: Check global and per-agent daily budget status.

    Queries daily_usage SUM(total_cost_usd) for today globally and
    filtered by agent_name. Compares against config daily_budget_usd
    (global) and config agent_budgets[agent_name] (per-agent).

    Creates an alert notification via adapter when alert_threshold_usd
    is reached (checked against global spend only).

    Args:
        config: Parsed openclawd.config.yaml dict.
        agent_name: The agent to check per-agent budget for.
        conn: Optional reader connection. If None, uses cached reader.
        adapter: Optional OpenClawdAdapter for alert notifications.

    Returns:
        Dict with keys:
          - global_exceeded (bool): True if global daily budget exceeded.
          - agent_exceeded (bool): True if per-agent daily budget exceeded.
    """
    if conn is None:
        conn = get_reader_connection()

    today = datetime.date.today().isoformat()
    global_budget = float(config.get("daily_budget_usd", 999999.0))
    alert_threshold = float(config.get("alert_threshold_usd", 999999.0))
    agent_budgets = config.get("agent_budgets", {})
    agent_limit = float(agent_budgets.get(agent_name, 999999.0))

    result = {"global_exceeded": False, "agent_exceeded": False}

    try:
        # Global spend for today
        cursor = conn.execute(
            "SELECT COALESCE(SUM(total_cost_usd), 0.0) "
            "FROM daily_usage WHERE date = ?",
            (today,),
        )
        global_spent = cursor.fetchone()[0]

        if global_spent >= global_budget:
            result["global_exceeded"] = True
            logger.info(
                "Global daily budget exceeded: $%.2f >= $%.2f",
                global_spent, global_budget,
            )

        # Alert threshold check
        if global_spent >= alert_threshold and adapter is not None:
            try:
                adapter.create_notification(
                    task_id=None,
                    message=(
                        f"Daily spend alert: ${global_spent:.2f} has reached "
                        f"the alert threshold of ${alert_threshold:.2f}. "
                        f"Global budget limit is ${global_budget:.2f}."
                    ),
                    urgency="high",
                )
                logger.info(
                    "Created alert notification: spend $%.2f >= threshold $%.2f",
                    global_spent, alert_threshold,
                )
            except Exception as e:
                logger.warning("Failed to create alert notification: %s", e)

        # Per-agent spend for today
        cursor = conn.execute(
            "SELECT COALESCE(SUM(total_cost_usd), 0.0) "
            "FROM daily_usage WHERE date = ? AND agent_name = ?",
            (today, agent_name),
        )
        agent_spent = cursor.fetchone()[0]

        if agent_spent >= agent_limit:
            result["agent_exceeded"] = True
            logger.info(
                "Agent %s daily budget exceeded: $%.2f >= $%.2f",
                agent_name, agent_spent, agent_limit,
            )

    except sqlite3.Error as e:
        logger.error("Failed to check budget: %s", e)

    return result
