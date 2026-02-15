"""Database query tool executor for read-only SELECT queries."""

import logging
import os
import signal
import sqlite3

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30
_MAX_ROWS = 1000


class DatabaseQueryError(Exception):
    """Raised when database query validation or execution fails."""


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
    raise DatabaseQueryError("Query timed out after 30 seconds")


def execute(query, params=None):
    """Execute a read-only SELECT query against coordination.db.

    Args:
        query: SQL SELECT query string.
        params: List of parameterized values for ? placeholders.

    Returns:
        Dict with 'rows' (list of tuples) and 'columns' (list of strings).

    Raises:
        DatabaseQueryError: If query is not SELECT, execution fails,
                            or query times out.
    """
    if params is None:
        params = []

    # Validate query starts with SELECT
    stripped = query.strip()
    if not stripped.upper().startswith("SELECT"):
        raise DatabaseQueryError(
            "Only SELECT queries are allowed. "
            f"Query starts with: {stripped.split()[0] if stripped else '(empty)'}"
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
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchmany(_MAX_ROWS)

        conn.close()

        return {"rows": rows, "columns": columns}
    except DatabaseQueryError:
        raise
    except sqlite3.Error as e:
        raise DatabaseQueryError(f"Database error: {e}") from e
    except Exception as e:
        raise DatabaseQueryError(f"Unexpected error: {e}") from e
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
