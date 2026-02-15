"""Python code executor with subprocess sandboxing, timeout, and temp file cleanup."""

import json
import logging
import os
import platform
import sqlite3
import subprocess
import tempfile

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 60


class PythonExecError(Exception):
    """Raised when Python code validation or execution fails."""


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
            ("python_exec_executor", tool_name, json.dumps(arguments), json.dumps(result)),
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


def execute(code, timeout=None):
    """Execute Python code in a subprocess with sandboxing.

    Writes code to a temporary file, spawns a subprocess to run it,
    captures stdout/stderr, and attempts to evaluate the last expression
    for a return value.

    Args:
        code: Python code string to execute.
        timeout: Maximum execution time in seconds (default 30, max 60).

    Returns:
        Dict with 'stdout' (str), 'stderr' (str), 'result' (str or None).

    Raises:
        PythonExecError: If code validation fails or execution errors occur.
    """
    if not code or not code.strip():
        raise PythonExecError("Code must not be empty")

    # Enforce timeout bounds
    if timeout is None:
        timeout = _DEFAULT_TIMEOUT
    timeout = min(max(1, int(timeout)), _MAX_TIMEOUT)

    # Build wrapper that runs the code and tries to eval the last expression
    # The wrapper prints a sentinel-delimited result to separate it from user output
    _SENTINEL = "__OPENCLAWD_RESULT_SENTINEL__"
    wrapper = (
        "import sys as _sys\n"
        "_code = " + repr(code) + "\n"
        "_lines = _code.strip().splitlines()\n"
        "# Execute the full code first\n"
        "exec(_code)\n"
        "# Try to eval the last line as an expression\n"
        "if _lines:\n"
        "    try:\n"
        "        _val = eval(_lines[-1])\n"
        "        if _val is not None:\n"
        "            print(" + repr(_SENTINEL) + " + repr(_val), file=_sys.stderr)\n"
        "    except:\n"
        "        pass\n"
    )

    # Determine if we should apply resource limits (Unix-like systems only)
    preexec_fn = None
    if platform.system() != 'Windows':
        preexec_fn = _set_resource_limits

    tmp_file = None
    try:
        tmp_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="openclawd_exec_",
            delete=False,
        )
        tmp_file.write(wrapper)
        tmp_file.close()

        proc = subprocess.run(
            ["python3", tmp_file.name],
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=preexec_fn,
        )

        stdout = proc.stdout
        stderr = proc.stderr
        result_value = None

        # Extract result from stderr sentinel
        if _SENTINEL in stderr:
            idx = stderr.rfind(_SENTINEL)
            result_value = stderr[idx + len(_SENTINEL):]
            stderr = stderr[:idx]

        result = {
            "stdout": stdout,
            "stderr": stderr,
            "result": result_value,
        }

        _log_audit(
            "python_exec",
            {"code_length": len(code), "timeout": timeout},
            {"exit_code": proc.returncode, "has_result": result_value is not None},
        )

        return result
    except subprocess.TimeoutExpired:
        raise PythonExecError(f"Code execution timed out after {timeout} seconds") from None
    except PythonExecError:
        raise
    except Exception as e:
        raise PythonExecError(f"Failed to execute Python code: {e}") from e
    finally:
        if tmp_file is not None:
            try:
                os.unlink(tmp_file.name)
            except OSError:
                pass
