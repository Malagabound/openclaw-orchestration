"""File read tool executor with path sandboxing and size limits."""

import logging
import os
import signal

logger = logging.getLogger(__name__)

_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
_TIMEOUT_SECONDS = 10


class FileReadError(Exception):
    """Raised when file read validation or execution fails."""


def _validate_path(path):
    """Validate that the path does not escape the sandbox.

    Rejects absolute paths and paths containing '..' traversal.
    """
    if os.path.isabs(path):
        raise FileReadError(
            f"Absolute paths are not allowed: {path}"
        )
    # Normalize and check for directory traversal
    normalized = os.path.normpath(path)
    if normalized.startswith("..") or os.sep + ".." in normalized:
        raise FileReadError(
            f"Path traversal (..) is not allowed: {path}"
        )


def _timeout_handler(signum, frame):
    raise FileReadError("File read timed out after 10 seconds")


def execute(path):
    """Read file content with sandboxing (path validation, size limit).

    Args:
        path: Relative path to the file to read. Must not be absolute
              or contain '..' traversal components.

    Returns:
        Dict with 'content' (str) and 'encoding' (str).

    Raises:
        FileReadError: If path validation fails, file exceeds 10MB,
                       or read times out.
        FileNotFoundError: If the file does not exist.
    """
    _validate_path(path)

    # Check file size before reading
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    file_size = os.path.getsize(path)
    if file_size > _MAX_SIZE_BYTES:
        raise FileReadError(
            f"File exceeds 10MB limit: {file_size} bytes"
        )

    # Set timeout (Unix only; on Windows this is a no-op)
    old_handler = None
    if hasattr(signal, "SIGALRM"):
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(_TIMEOUT_SECONDS)

    try:
        # Try UTF-8 first
        encoding = "utf-8"
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            # Fall back to latin-1 (never raises UnicodeDecodeError)
            encoding = "latin-1"
            with open(path, "r", encoding="latin-1") as f:
                content = f.read()

        return {"content": content, "encoding": encoding}
    finally:
        # Restore signal handler
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
