"""Failure memory module for recording and querying past recovery attempts.

Provides functions to record recovery outcomes, query similar past fixes
using a 3-tier similarity strategy, and clean up old entries per retention policy.
"""

import logging
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def record_attempt(
    task_id: int,
    error_code: str,
    agent_name: str,
    diagnostic_summary: str,
    resolution_summary: str,
    success: bool,
    recovery_tier: int,
    task_domain: Optional[str] = None,
    error_pattern: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Insert a row into failure_memory table recording a recovery attempt.

    Args:
        task_id: The task ID that was recovered.
        error_code: Canonical error code from ERROR_TAXONOMY.
        agent_name: Agent that attempted the task.
        diagnostic_summary: Summary from diagnostic agent.
        resolution_summary: What was done to resolve (or attempt to resolve).
        success: Whether the recovery attempt succeeded.
        recovery_tier: Strategy tier used (1-5).
        task_domain: Optional task domain for similarity matching.
        error_pattern: Optional normalized error pattern.
        db_path: Optional database path override.

    Returns:
        True if the record was inserted successfully, False otherwise.
    """
    from ..dispatch_db import get_writer_connection

    conn = get_writer_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO failure_memory "
            "(task_id, agent_name, error_code, error_pattern, "
            "diagnostic_summary, resolution_summary, success, "
            "recovery_tier, task_domain) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                agent_name,
                error_code,
                error_pattern,
                diagnostic_summary,
                resolution_summary,
                1 if success else 0,
                recovery_tier,
                task_domain,
            ),
        )
        conn.commit()
        logger.debug(
            "Recorded failure_memory: task_id=%s error_code=%s success=%s tier=%d",
            task_id, error_code, success, recovery_tier,
        )
        return True
    except sqlite3.Error as e:
        logger.error("Failed to record failure_memory for task %s: %s", task_id, e)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return False
    finally:
        conn.close()


def find_similar_fixes(
    error_code: str,
    agent_name: str,
    task_domain: Optional[str] = None,
    limit: int = 3,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query similar past successful fixes using 3-tier similarity strategy.

    Tier 1: Exact match on error_code + agent_name + success=1
    Tier 2: Match error_code + task_domain + success=1
    Tier 3: Match error_code + success=1 only

    Returns the first tier that produces results, up to limit rows.

    Args:
        error_code: Canonical error code to match.
        agent_name: Agent name for exact matching.
        task_domain: Optional task domain for tier 2 matching.
        limit: Maximum rows to return (default 3).
        db_path: Optional database path override.

    Returns:
        List of dicts with: error_code, resolution_summary,
        diagnostic_summary, recovery_tier.
    """
    from ..dispatch_db import get_reader_connection

    conn = get_reader_connection(db_path)

    def _rows_to_dicts(rows: list) -> List[Dict[str, Any]]:
        result = []
        for row in rows:
            if isinstance(row, sqlite3.Row):
                result.append({
                    "error_code": row["error_code"],
                    "resolution_summary": row["resolution_summary"],
                    "diagnostic_summary": row["diagnostic_summary"],
                    "recovery_tier": row["recovery_tier"],
                })
            else:
                result.append({
                    "error_code": row[0],
                    "resolution_summary": row[1],
                    "diagnostic_summary": row[2],
                    "recovery_tier": row[3],
                })
        return result

    select_cols = "error_code, resolution_summary, diagnostic_summary, recovery_tier"

    try:
        # Tier 1: Exact match on error_code + agent_name + success=1
        rows = conn.execute(
            f"SELECT {select_cols} FROM failure_memory "
            "WHERE error_code = ? AND agent_name = ? AND success = 1 "
            "ORDER BY created_at DESC LIMIT ?",
            (error_code, agent_name, limit),
        ).fetchall()
        if rows:
            return _rows_to_dicts(rows)

        # Tier 2: Match error_code + task_domain + success=1
        if task_domain:
            rows = conn.execute(
                f"SELECT {select_cols} FROM failure_memory "
                "WHERE error_code = ? AND task_domain = ? AND success = 1 "
                "ORDER BY created_at DESC LIMIT ?",
                (error_code, task_domain, limit),
            ).fetchall()
            if rows:
                return _rows_to_dicts(rows)

        # Tier 3: Match error_code + success=1 only
        rows = conn.execute(
            f"SELECT {select_cols} FROM failure_memory "
            "WHERE error_code = ? AND success = 1 "
            "ORDER BY created_at DESC LIMIT ?",
            (error_code, limit),
        ).fetchall()
        if rows:
            return _rows_to_dicts(rows)

        return []

    except sqlite3.Error as e:
        logger.error(
            "Failed to query similar fixes for error_code=%s: %s",
            error_code, e,
        )
        return []


def detect_systemic_pattern(
    error_code: str,
    window_minutes: int = 10,
    threshold_count: int = 3,
    db_path: Optional[str] = None,
) -> bool:
    """Detect systemic failure patterns by counting distinct tasks with same error.

    Queries failure_memory for rows with the given error_code within the
    time window and counts distinct task_ids. Returns True if the count
    meets or exceeds the threshold.

    Args:
        error_code: Canonical error code to check for systemic pattern.
        window_minutes: Time window in minutes to search (default 10).
        threshold_count: Minimum distinct task_ids to trigger (default 3).
        db_path: Optional database path override.

    Returns:
        True if systemic pattern detected (count >= threshold), False otherwise.
    """
    from ..dispatch_db import get_reader_connection

    conn = get_reader_connection(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT task_id) FROM failure_memory "
            "WHERE error_code = ? "
            "AND created_at > datetime('now', '-' || ? || ' minutes')",
            (error_code, str(window_minutes)),
        ).fetchone()
        count = row[0] if row else 0
        if count >= threshold_count:
            logger.warning(
                "Systemic failure pattern detected: error_code=%s count=%d "
                "threshold=%d window=%d minutes",
                error_code, count, threshold_count, window_minutes,
            )
            return True
        return False
    except sqlite3.Error as e:
        logger.error(
            "Failed to detect systemic pattern for error_code=%s: %s",
            error_code, e,
        )
        return False


def cleanup_old_entries(
    retention_days: int = 90,
    db_path: Optional[str] = None,
) -> int:
    """Delete failure_memory rows older than retention_days.

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
            "DELETE FROM failure_memory "
            "WHERE created_at < datetime('now', '-' || ? || ' days')",
            (str(retention_days),),
        )
        deleted = cursor.rowcount
        conn.commit()
        if deleted > 0:
            logger.info(
                "Cleaned up %d failure_memory entries older than %d days",
                deleted, retention_days,
            )
        return deleted
    except sqlite3.Error as e:
        logger.error("Failed to cleanup failure_memory: %s", e)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return 0
    finally:
        conn.close()
