"""Database write tool executor for INSERT/UPDATE/DELETE with audit logging."""

import json
import logging
import os
import signal
import sqlite3

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30
_ALLOWED_PREFIXES = ("INSERT", "UPDATE", "DELETE")


class DatabaseWriteError(Exception):
    """Raised when database write validation or execution fails."""


def _get_db_path():
    """Resolve coordination.db path from env or default fallback."""
    return os.environ.get(
        "OPENCLAWD_DB_PATH",
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "orchestrator-dashboard",
            "orchestrator-dashboard",
            "coordination.db",
        ),
    )


def _timeout_handler(signum, frame):
    raise DatabaseWriteError("Query timed out after 30 seconds")


def _log_audit(tool_name, arguments, result):
    """Log a destructive tool call to the audit_log table."""
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO audit_log (agent_name, tool_name, arguments, result) VALUES (?, ?, ?, ?)",
            ("database_write_executor", tool_name, json.dumps(arguments), json.dumps(result)),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to write audit log: %s", e)


def execute(query, params=None):
    """Execute an INSERT/UPDATE/DELETE query against coordination.db.

    Args:
        query: SQL INSERT, UPDATE, or DELETE query string.
        params: List of parameterized values for ? placeholders.

    Returns:
        Dict with 'rows_affected' (int).

    Raises:
        DatabaseWriteError: If query is not INSERT/UPDATE/DELETE,
                            execution fails, or query times out.
    """
    if params is None:
        params = []

    # Validate query starts with INSERT, UPDATE, or DELETE
    stripped = query.strip()
    first_word = stripped.split()[0].upper() if stripped else "(empty)"
    if first_word not in _ALLOWED_PREFIXES:
        raise DatabaseWriteError(
            "Only INSERT, UPDATE, and DELETE queries are allowed. "
            f"Query starts with: {first_word}"
        )

    # Set timeout (Unix only)
    old_handler = None
    if hasattr(signal, "SIGALRM"):
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_TIMEOUT_SECONDS)

    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        cursor = conn.execute(query, params)
        rows_affected = cursor.rowcount
        conn.commit()

        conn.close()

        result = {"rows_affected": rows_affected}

        _log_audit(
            "database_write",
            {"query": query, "params_count": len(params)},
            result,
        )

        return result
    except DatabaseWriteError:
        raise
    except sqlite3.Error as e:
        raise DatabaseWriteError(f"Database error: {e}") from e
    except Exception as e:
        raise DatabaseWriteError(f"Unexpected error: {e}") from e
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
