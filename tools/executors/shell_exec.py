"""Shell command executor with subprocess sandboxing, timeout, and audit logging."""

import json
import logging
import os
import platform
import sqlite3
import subprocess

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 60


class ShellExecError(Exception):
    """Raised when shell command validation or execution fails."""


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
    """Log tool call to the audit_log table."""
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO audit_log (agent_name, tool_name, arguments, result) VALUES (?, ?, ?, ?)",
            ("shell_exec_executor", tool_name, json.dumps(arguments), json.dumps(result)),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to write audit log: %s", e)


def _set_resource_limits():
    """Set memory and CPU limits for sandboxed tool execution.

    REQ-065: Resource limits to prevent runaway processes.
    - 512MB memory limit
    - 60 second CPU time limit

    Note: Only works on Unix-like systems (not Windows).
    """
    try:
        import resource
        # 512MB memory limit
        memory_limit = 512 * 1024 * 1024  # 512MB in bytes
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
        # 60 second CPU time limit
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    except (ImportError, OSError, ValueError) as e:
        # Resource module not available (Windows) or limits not supported
        logger.debug("Resource limits not applied: %s", e)


def execute(command, cwd=None, timeout=None):
    """Execute a shell command with subprocess sandboxing.

    Args:
        command: Shell command string to execute.
        cwd: Working directory for command execution (optional).
        timeout: Maximum execution time in seconds (default 30, max 60).

    Returns:
        Dict with 'stdout' (str), 'stderr' (str), 'exit_code' (int).

    Raises:
        ShellExecError: If command validation fails or execution errors occur.
    """
    if not command or not command.strip():
        raise ShellExecError("Command must not be empty")

    # Enforce timeout bounds
    if timeout is None:
        timeout = _DEFAULT_TIMEOUT
    timeout = min(max(1, int(timeout)), _MAX_TIMEOUT)

    # Validate cwd if provided
    if cwd is not None and not os.path.isdir(cwd):
        raise ShellExecError(f"Working directory does not exist: {cwd}")

    # Determine if we should apply resource limits (Unix-like systems only)
    preexec_fn = None
    if platform.system() != 'Windows':
        preexec_fn = _set_resource_limits

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            preexec_fn=preexec_fn,
        )

        result = {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
        }

        _log_audit(
            "shell_exec",
            {"command": command, "cwd": cwd, "timeout": timeout},
            {"exit_code": proc.returncode},
        )

        return result
    except subprocess.TimeoutExpired:
        raise ShellExecError(f"Command timed out after {timeout} seconds") from None
    except Exception as e:
        raise ShellExecError(f"Failed to execute command: {e}") from e
