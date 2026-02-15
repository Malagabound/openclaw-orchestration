"""Compensating actions for pre-retry cleanup in the recovery pipeline.

Clears partial artifacts from failed attempts so that retry starts from a
known-good state. Called by handle_failure() (US-022) when the error category
has requires_compensation=True.
"""

import json
import logging
import sqlite3
from typing import Optional

from .error_classifier import classify_error

logger = logging.getLogger(__name__)


def compensate(
    task_id: int,
    agent_name: str,
    error_code: str,
    db_path: Optional[str] = None,
) -> bool:
    """Clean up failed attempt artifacts so retry starts from known-good state.

    Executes compensating actions based on the error code's compensating_action_keys:
    - clear_working_memory: DELETE working_memory rows for this task+agent
    - reset_lease: Reset dispatch_status to 'queued' and clear lease_until
    - log_abandoned_output: Log that raw output from failed attempt was abandoned
    - defer_to_us051: Skip compensation, let recover_partial_completions handle it

    Args:
        task_id: The task ID to compensate.
        agent_name: The agent that failed.
        error_code: Canonical error code for determining which actions to run.
        db_path: Optional database path override.

    Returns:
        True if all compensating actions succeeded, False if any failed.
    """
    from ..dispatch_db import get_writer_connection
    from ..structured_logging import get_logger, log_dispatch_event

    slog = get_logger("recovery.compensate")

    category = classify_error(error_code)
    if not category.requires_compensation:
        return True

    action_keys = category.compensating_action_keys
    if not action_keys:
        return True

    # defer_to_us051 means "don't compensate here, let the completion recovery sweep handle it"
    if "defer_to_us051" in action_keys:
        log_dispatch_event(
            slog, logging.INFO,
            f"Deferring compensation to recover_partial_completions for task {task_id}",
            task_id=str(task_id),
            extra={"event_type": "recovery.compensate", "error_code": error_code,
                   "action": "defer_to_us051"},
        )
        return True

    conn = get_writer_connection(db_path)
    success = True
    actions_taken = []

    try:
        # Action: clear_working_memory
        if "clear_working_memory" in action_keys:
            try:
                cursor = conn.execute(
                    "DELETE FROM working_memory WHERE task_id = ? AND agent_name = ?",
                    (task_id, agent_name),
                )
                deleted = cursor.rowcount
                actions_taken.append(f"clear_working_memory({deleted} rows)")
                logger.debug(
                    "Cleared %d working_memory rows for task %s agent %s",
                    deleted, task_id, agent_name,
                )
            except sqlite3.Error as e:
                logger.error(
                    "Failed to clear working_memory for task %s: %s", task_id, e,
                )
                success = False

        # Action: reset_lease
        if "reset_lease" in action_keys:
            try:
                cursor = conn.execute(
                    "UPDATE tasks SET dispatch_status = 'queued', lease_until = NULL "
                    "WHERE id = ? AND dispatch_status IN ('failed', 'recovering', 'dispatched')",
                    (task_id,),
                )
                if cursor.rowcount > 0:
                    actions_taken.append("reset_lease")
                    logger.debug("Reset lease for task %s", task_id)
                else:
                    actions_taken.append("reset_lease(no-op)")
            except sqlite3.Error as e:
                logger.error(
                    "Failed to reset lease for task %s: %s", task_id, e,
                )
                success = False

        # Action: log_abandoned_output
        if "log_abandoned_output" in action_keys:
            try:
                row = conn.execute(
                    "SELECT raw_output FROM dispatch_runs "
                    "WHERE task_id = ? ORDER BY id DESC LIMIT 1",
                    (task_id,),
                ).fetchone()
                abandoned_output = ""
                if row:
                    abandoned_output = (
                        row["raw_output"] if isinstance(row, sqlite3.Row) else row[0]
                    ) or ""
                actions_taken.append(
                    f"log_abandoned_output({len(abandoned_output)} chars)"
                )
                logger.info(
                    "Abandoned output for task %s (%d chars): %s",
                    task_id, len(abandoned_output),
                    abandoned_output[:200] + "..." if len(abandoned_output) > 200 else abandoned_output,
                )
            except sqlite3.Error as e:
                logger.error(
                    "Failed to log abandoned output for task %s: %s", task_id, e,
                )
                # Non-critical — don't fail compensation for logging issues

        conn.commit()

    except sqlite3.Error as e:
        logger.error("Compensation transaction failed for task %s: %s", task_id, e)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        success = False
    finally:
        conn.close()

    # Log compensation event to structured logging
    log_dispatch_event(
        slog, logging.INFO,
        f"Compensating actions for task {task_id}: {', '.join(actions_taken)}",
        task_id=str(task_id),
        extra={
            "event_type": "recovery.compensate",
            "error_code": error_code,
            "agent_name": agent_name,
            "actions": actions_taken,
            "success": success,
        },
    )

    return success
