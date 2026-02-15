"""File write tool executor with path sandboxing and audit logging."""

import json
import logging
import os
import signal
import sqlite3

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10
_VALID_MODES = {"w", "a", "wb"}


class FileWriteError(Exception):
    """Raised when file write validation or execution fails."""


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


def _log_audit(tool_name, arguments, result):
    """Log a destructive tool call to the audit_log table."""
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO audit_log (agent_name, tool_name, arguments, result) VALUES (?, ?, ?, ?)",
            ("file_write_executor", tool_name, json.dumps(arguments), json.dumps(result)),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to write audit log: %s", e)


def _validate_path(path):
    """Validate that the path does not contain dangerous patterns.

    Rejects absolute paths and paths containing '..' traversal.
    """
    if os.path.isabs(path):
        raise FileWriteError(f"Absolute paths are not allowed: {path}")
    normalized = os.path.normpath(path)
    if normalized.startswith("..") or os.sep + ".." in normalized:
        raise FileWriteError(f"Path traversal (..) is not allowed: {path}")


def _timeout_handler(signum, frame):
    raise FileWriteError("File write timed out after 10 seconds")


def execute(path, content, mode="w"):
    """Write content to a file with sandboxing and audit logging.

    Args:
        path: Relative path to the file to write. Must not be absolute
              or contain '..' traversal components.
        content: The content to write to the file.
        mode: Write mode - 'w' (overwrite), 'a' (append), or 'wb' (binary write).

    Returns:
        Dict with 'success' (bool) and 'bytes_written' (int).

    Raises:
        FileWriteError: If path validation fails or write times out.
    """
    _validate_path(path)

    if mode not in _VALID_MODES:
        raise FileWriteError(f"Invalid mode '{mode}'. Must be one of: {_VALID_MODES}")

    # Create parent directories if needed
    parent_dir = os.path.dirname(path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # Set timeout (Unix only)
    old_handler = None
    if hasattr(signal, "SIGALRM"):
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_TIMEOUT_SECONDS)

    try:
        if mode == "wb":
            if isinstance(content, str):
                content = content.encode("utf-8")
            with open(path, "wb") as f:
                bytes_written = f.write(content)
        else:
            with open(path, mode, encoding="utf-8") as f:
                bytes_written = f.write(content)

        result = {"success": True, "bytes_written": bytes_written}

        _log_audit(
            "file_write",
            {"path": path, "mode": mode, "bytes_written": bytes_written},
            result,
        )

        return result
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
