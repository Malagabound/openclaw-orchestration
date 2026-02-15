"""OpenClawd Agent Dispatch System - Data Retention Archival Job.

US-069: Implements data retention by archiving completed tasks older than 90 days,
aggregating provider_health records older than 30 days into health_daily_summary,
cleaning up old dispatch_runs/working_memory/agent_activity (90 days),
provider_incidents (180 days, resolved only), and output files for archived tasks.
Runs as a daily scheduled job.

US-073: Daily log rotation with gzip compression. Renames supervisor.jsonl to
supervisor-YYYY-MM-DD.jsonl, gzips old file, deletes gzipped logs older than
config log_retention_days (default 30).

REQ-066: IMPORTANT - audit_log is PERMANENT and NEVER cleaned up.
The audit_log table is permanent per spec. Never add cleanup logic for this table.
The audit_log table uses ON DELETE SET NULL for task_id foreign keys, ensuring
audit entries survive even when tasks are archived/deleted.
"""

import glob
import gzip
import logging
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .config import DEFAULT_DB_PATH, load_config
from .dispatch_db import _get_db_path, get_writer_connection

logger = logging.getLogger(__name__)

# Output directory for agent dispatch results
_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def archive_completed_tasks(conn: sqlite3.Connection) -> int:
    """Archive completed tasks older than 90 days.

    Step 1: INSERT OR IGNORE into tasks_archive from tasks.
    Step 2: DELETE from tasks where id exists in tasks_archive.

    Returns:
        Number of tasks archived.
    """
    # Step 1: Copy completed tasks older than 90 days to archive
    conn.execute(
        """
        INSERT OR IGNORE INTO tasks_archive
        (id, title, description, status, priority, domain, assigned_agent,
         created_by, created_at, updated_at, due_date, deliverable_type,
         deliverable_url, estimated_effort, business_impact,
         dispatch_status, lease_until)
        SELECT id, title, description, status, priority, domain, assigned_agent,
               created_by, created_at, updated_at, due_date, deliverable_type,
               deliverable_url, estimated_effort, business_impact,
               dispatch_status, lease_until
        FROM tasks
        WHERE status = 'completed'
          AND updated_at < datetime('now', '-90 days')
        """
    )

    # Step 2: Delete from tasks only those that made it into the archive
    cursor = conn.execute(
        """
        DELETE FROM tasks
        WHERE status = 'completed'
          AND updated_at < datetime('now', '-90 days')
          AND id IN (SELECT id FROM tasks_archive)
        """
    )
    archived_count = cursor.rowcount
    if archived_count > 0:
        logger.info("Archived and deleted %d completed tasks older than 90 days", archived_count)
    return archived_count


def cleanup_output_files(conn: sqlite3.Connection) -> int:
    """Delete output files matching archived task IDs.

    Scans agent-dispatch/output/ for files whose names contain archived task IDs.

    Returns:
        Number of files deleted.
    """
    if not os.path.isdir(_OUTPUT_DIR):
        return 0

    # Get all archived task IDs
    rows = conn.execute("SELECT id FROM tasks_archive").fetchall()
    archived_ids = {str(row[0]) for row in rows}

    if not archived_ids:
        return 0

    deleted = 0
    for filepath in glob.glob(os.path.join(_OUTPUT_DIR, "*")):
        filename = os.path.basename(filepath)
        # Check if filename starts with or contains a task ID
        for task_id in archived_ids:
            if task_id in filename:
                try:
                    os.remove(filepath)
                    deleted += 1
                    logger.debug("Deleted output file: %s", filepath)
                except OSError as e:
                    logger.warning("Failed to delete output file %s: %s", filepath, e)
                break

    if deleted > 0:
        logger.info("Deleted %d output files for archived tasks", deleted)
    return deleted


def aggregate_provider_health(conn: sqlite3.Connection) -> int:
    """Aggregate provider_health records older than 30 days into health_daily_summary.

    Inserts aggregated SUM/AVG data grouped by date/provider/model, then deletes
    the raw records.

    Returns:
        Number of raw records deleted.
    """
    # Aggregate into health_daily_summary
    conn.execute(
        """
        INSERT OR IGNORE INTO health_daily_summary
        (date, provider, model, tests_run, tests_passed, avg_latency_ms)
        SELECT
            date(tested_at) AS date,
            provider,
            model,
            COUNT(*) AS tests_run,
            SUM(passed) AS tests_passed,
            AVG(latency_ms) AS avg_latency_ms
        FROM provider_health
        WHERE tested_at < datetime('now', '-30 days')
        GROUP BY date(tested_at), provider, model
        """
    )

    # Delete raw records that have been aggregated
    cursor = conn.execute(
        "DELETE FROM provider_health WHERE tested_at < datetime('now', '-30 days')"
    )
    deleted_count = cursor.rowcount
    if deleted_count > 0:
        logger.info(
            "Aggregated and deleted %d provider_health records older than 30 days",
            deleted_count,
        )
    return deleted_count


def cleanup_old_records(conn: sqlite3.Connection) -> Dict[str, int]:
    """Delete old records from agent_activity, dispatch_runs, and working_memory.

    All records older than 90 days are deleted.

    IMPORTANT: audit_log is NEVER cleaned up by retention policy (REQ-066).
    The audit_log table is permanent and explicitly excluded from cleanup.

    Returns:
        Dict mapping table name to number of records deleted.
    """
    results = {}

    # REQ-066: audit_log is PERMANENT - never add cleanup logic for audit_log
    # The audit_log table is explicitly excluded from all retention cleanup

    # agent_activity - older than 90 days
    try:
        cursor = conn.execute(
            "DELETE FROM agent_activity WHERE created_at < datetime('now', '-90 days')"
        )
        results["agent_activity"] = cursor.rowcount
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            logger.debug("agent_activity table not found, skipping")
            results["agent_activity"] = 0
        else:
            raise

    # dispatch_runs - older than 90 days
    cursor = conn.execute(
        "DELETE FROM dispatch_runs WHERE started_at < datetime('now', '-90 days')"
    )
    results["dispatch_runs"] = cursor.rowcount

    # working_memory - older than 90 days
    cursor = conn.execute(
        "DELETE FROM working_memory WHERE created_at < datetime('now', '-90 days')"
    )
    results["working_memory"] = cursor.rowcount

    total = sum(results.values())
    if total > 0:
        logger.info(
            "Cleaned up old records: %s",
            ", ".join(f"{k}={v}" for k, v in results.items() if v > 0),
        )
    return results


def cleanup_provider_incidents(conn: sqlite3.Connection) -> int:
    """Delete resolved provider_incidents older than 180 days.

    Only deletes incidents where resolved_at is set and older than threshold.

    Returns:
        Number of incidents deleted.
    """
    cursor = conn.execute(
        """
        DELETE FROM provider_incidents
        WHERE resolved_at IS NOT NULL
          AND resolved_at < datetime('now', '-180 days')
        """
    )
    deleted_count = cursor.rowcount
    if deleted_count > 0:
        logger.info(
            "Deleted %d resolved provider_incidents older than 180 days",
            deleted_count,
        )
    return deleted_count


def monitor_and_vacuum_db(
    config: Dict[str, Any], conn: sqlite3.Connection, adapter=None
) -> Dict[str, Any]:
    """Monitor database file size and run vacuum if needed.

    US-070: Checks DB file size against max_db_size_mb threshold, creates alert
    notification if exceeded, runs PRAGMA incremental_vacuum if auto_vacuum is
    INCREMENTAL, otherwise falls back to full VACUUM only when no active dispatches.

    Args:
        config: Parsed config dict with optional max_db_size_mb key.
        conn: Active database connection.
        adapter: Optional OpenClawdAdapter for creating alert notifications.

    Returns:
        Dict with monitoring results (size_mb, threshold_mb, alert_created,
        vacuum_type, size_before, size_after).
    """
    db_path = _get_db_path()
    max_db_size_mb = float(config.get("max_db_size_mb", 500))

    result: Dict[str, Any] = {
        "size_mb": 0.0,
        "threshold_mb": max_db_size_mb,
        "alert_created": False,
        "vacuum_type": None,
        "size_before": 0,
        "size_after": 0,
    }

    # Get current file size
    try:
        size_bytes = os.path.getsize(db_path)
    except OSError as e:
        logger.warning("Cannot get database file size: %s", e)
        return result

    size_mb = size_bytes / (1024 * 1024)
    result["size_mb"] = round(size_mb, 2)
    result["size_before"] = size_bytes

    # Check threshold and create alert if exceeded
    if size_mb > max_db_size_mb:
        logger.warning(
            "Database size %.2f MB exceeds threshold %.2f MB",
            size_mb, max_db_size_mb,
        )
        if adapter is not None:
            try:
                adapter.create_notification(
                    task_id=None,
                    message=(
                        f"Database size alert: {size_mb:.2f} MB exceeds "
                        f"threshold of {max_db_size_mb:.2f} MB. "
                        f"Path: {db_path}"
                    ),
                    urgency="high",
                )
                result["alert_created"] = True
                logger.info("Created database size alert notification")
            except Exception as e:
                logger.warning("Failed to create size alert notification: %s", e)

    # Check auto_vacuum mode
    auto_vacuum_mode = conn.execute("PRAGMA auto_vacuum").fetchone()[0]
    # auto_vacuum values: 0=NONE, 1=FULL, 2=INCREMENTAL

    if auto_vacuum_mode == 2:
        # INCREMENTAL mode - run incremental vacuum
        pages_to_vacuum = 100  # reclaim up to 100 pages at a time
        conn.execute(f"PRAGMA incremental_vacuum({pages_to_vacuum})")
        result["vacuum_type"] = "incremental"
        logger.info("Ran PRAGMA incremental_vacuum(%d)", pages_to_vacuum)
    else:
        # Check if any active dispatches before full VACUUM
        cursor = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE dispatch_status = ?",
            ("dispatched",),
        )
        active_count = cursor.fetchone()[0]

        if active_count == 0:
            # No active dispatches - safe to run full VACUUM
            # VACUUM cannot run inside a transaction, so we need to commit first
            try:
                conn.commit()
            except sqlite3.Error:
                pass
            conn.execute("VACUUM")
            result["vacuum_type"] = "full"
            logger.info("Ran full VACUUM (no active dispatches)")
        else:
            logger.info(
                "Skipping full VACUUM: %d active dispatches", active_count
            )

    # Get size after vacuum
    try:
        size_after = os.path.getsize(db_path)
        result["size_after"] = size_after
        size_after_mb = size_after / (1024 * 1024)
        logger.info(
            "Database vacuum complete: before=%.2f MB, after=%.2f MB",
            size_mb, size_after_mb,
        )
    except OSError:
        result["size_after"] = size_bytes  # fallback to original size

    return result


def rotate_logs(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Rotate supervisor.jsonl log file with gzip compression.

    US-073: Renames supervisor.jsonl to supervisor-YYYY-MM-DD.jsonl, gzips the
    renamed file, deletes gzipped logs older than log_retention_days, and creates
    a new empty supervisor.jsonl for continued logging.

    Args:
        config: Parsed config dict. Uses config['log_retention_days'] (default 30).

    Returns:
        Dict with rotation results (rotated, gzipped, deleted_count, errors).
    """
    if config is None:
        config = {}

    log_retention_days = int(config.get("log_retention_days", 30))
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    log_file = os.path.join(log_dir, "supervisor.jsonl")

    result: Dict[str, Any] = {
        "rotated": False,
        "gzipped": False,
        "deleted_count": 0,
        "errors": [],
    }

    # Ensure logs directory exists
    os.makedirs(log_dir, exist_ok=True)

    # Step 1: Rename supervisor.jsonl to supervisor-YYYY-MM-DD.jsonl
    if not os.path.isfile(log_file):
        logger.debug("No supervisor.jsonl found, nothing to rotate")
        # Still create the file for continued logging
        open(log_file, "a").close()
        return result

    # Check if file is empty - skip rotation but ensure file exists
    if os.path.getsize(log_file) == 0:
        logger.debug("supervisor.jsonl is empty, skipping rotation")
        return result

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rotated_name = f"supervisor-{today}.jsonl"
    rotated_path = os.path.join(log_dir, rotated_name)
    gz_path = rotated_path + ".gz"

    # If today's rotated file already exists, append a counter
    if os.path.exists(rotated_path) or os.path.exists(gz_path):
        counter = 1
        while True:
            rotated_name = f"supervisor-{today}-{counter}.jsonl"
            rotated_path = os.path.join(log_dir, rotated_name)
            gz_path = rotated_path + ".gz"
            if not os.path.exists(rotated_path) and not os.path.exists(gz_path):
                break
            counter += 1

    try:
        shutil.move(log_file, rotated_path)
        result["rotated"] = True
        logger.info("Rotated supervisor.jsonl to %s", rotated_name)
    except OSError as e:
        result["errors"].append(f"Failed to rename log file: {e}")
        logger.error("Failed to rotate supervisor.jsonl: %s", e)
        return result

    # Step 2: Gzip the renamed file
    try:
        with open(rotated_path, "rb") as f_in:
            with gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(rotated_path)
        result["gzipped"] = True
        logger.info("Gzipped %s", rotated_name)
    except OSError as e:
        result["errors"].append(f"Failed to gzip rotated log: {e}")
        logger.error("Failed to gzip %s: %s", rotated_name, e)

    # Step 3: Delete .gz files older than log_retention_days
    deleted = 0
    for filepath in glob.glob(os.path.join(log_dir, "supervisor-*.jsonl.gz")):
        try:
            file_mtime = os.path.getmtime(filepath)
            age_days = (time.time() - file_mtime) / 86400
            if age_days > log_retention_days:
                os.remove(filepath)
                deleted += 1
                logger.debug("Deleted old log: %s (%.1f days old)", filepath, age_days)
        except OSError as e:
            result["errors"].append(f"Failed to delete {filepath}: {e}")
            logger.warning("Failed to delete old log %s: %s", filepath, e)
    result["deleted_count"] = deleted
    if deleted > 0:
        logger.info("Deleted %d gzipped log files older than %d days", deleted, log_retention_days)

    # Step 4: Create new empty supervisor.jsonl for continued logging
    try:
        open(log_file, "a").close()
        logger.debug("Created new empty supervisor.jsonl")
    except OSError as e:
        result["errors"].append(f"Failed to create new log file: {e}")
        logger.error("Failed to create new supervisor.jsonl: %s", e)

    return result


def run_retention_job(config: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Execute the full data retention archival job.

    Runs all retention operations in a single transaction:
    1. Archive completed tasks (90 days)
    2. Delete output files for archived tasks
    3. Aggregate provider_health (30 days)
    4. Clean up old records (90 days) - EXCEPT audit_log which is permanent
    5. Clean up resolved provider_incidents (180 days)

    IMPORTANT (REQ-066): audit_log is PERMANENT and never cleaned up.

    Args:
        config: Optional parsed config dict (unused currently, reserved for
                future configurable retention periods).

    Returns:
        Dict with counts of records affected per operation.
    """
    if config is None:
        config = {}

    conn = get_writer_connection()
    results = {}

    try:
        results["tasks_archived"] = archive_completed_tasks(conn)
        results["output_files_deleted"] = cleanup_output_files(conn)
        results["provider_health_aggregated"] = aggregate_provider_health(conn)

        old_records = cleanup_old_records(conn)
        results.update(old_records)

        results["provider_incidents_deleted"] = cleanup_provider_incidents(conn)

        conn.commit()

        # Log rotation (filesystem operation, outside DB transaction)
        log_rotation = rotate_logs(config)
        results["logs_rotated"] = log_rotation.get("rotated", False)
        results["old_logs_deleted"] = log_rotation.get("deleted_count", 0)

        logger.info("Data retention job completed: %s", results)

    except Exception as e:
        logger.error("Data retention job failed: %s", e)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()

    return results


# ── Scheduled Job (Daily Heartbeat) ──────────────────────────────

_retention_thread: Optional[threading.Thread] = None
_retention_stop_event = threading.Event()


def start_retention_scheduler(config: Optional[Dict[str, Any]] = None) -> None:
    """Start the daily retention job on a background daemon thread.

    Runs once immediately on start, then every 24 hours.
    """
    global _retention_thread

    if _retention_thread is not None and _retention_thread.is_alive():
        logger.warning("Retention scheduler already running")
        return

    _retention_stop_event.clear()

    def _run_daily():
        interval = 86400  # 24 hours in seconds
        while not _retention_stop_event.is_set():
            try:
                run_retention_job(config)
            except Exception as e:
                logger.error("Retention job error: %s", e)
            _retention_stop_event.wait(timeout=interval)

    _retention_thread = threading.Thread(
        target=_run_daily,
        name="retention-scheduler",
        daemon=True,
    )
    _retention_thread.start()
    logger.info("Retention scheduler started (daily heartbeat)")


def stop_retention_scheduler() -> None:
    """Stop the daily retention scheduler."""
    global _retention_thread
    _retention_stop_event.set()
    if _retention_thread is not None:
        _retention_thread.join(timeout=5)
        _retention_thread = None
        logger.info("Retention scheduler stopped")
