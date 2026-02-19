"""Intention Integrity System - Deliverable Verification Module.

Verifies agent claims by inspecting tool call results already captured
during execution. Does NOT re-run tools; operates purely on the
tool_call_log accumulated by agent_runner.py.

Provides:
  - verify_deliverables(): Check tool results for success indicators
  - record_intent_ledger(): Persist verification results to intent_ledger table
"""

import datetime
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Tools that perform write/side-effect operations and need verification
_WRITE_TOOLS = frozenset({
    "file_write",
    "shell_exec",
    "database_write",
    "send_email",
    "python_exec",
})

# Tools that are read-only and can be skipped for verification
_READ_ONLY_TOOLS = frozenset({
    "file_read",
    "web_search",
    "database_query",
})


@dataclass
class VerificationAction:
    """Result of verifying a single tool call."""
    tool_name: str
    arguments: Dict[str, Any]
    result_excerpt: str
    iteration: int
    verified: Optional[bool]  # True=pass, False=fail, None=skipped
    verification_note: str = ""


@dataclass
class VerificationResult:
    """Aggregate verification outcome for a task."""
    passed: bool
    total_actions: int
    verified_count: int
    unverified_count: int
    skipped_count: int
    actions: List[VerificationAction] = field(default_factory=list)
    failure_reasons: List[str] = field(default_factory=list)


def _parse_result_json(result_excerpt: str) -> Optional[Dict[str, Any]]:
    """Attempt to parse a tool result excerpt as JSON.

    Returns None if parsing fails (result is skipped, not failed).
    """
    if not result_excerpt:
        return None
    try:
        parsed = json.loads(result_excerpt)
        if isinstance(parsed, dict):
            return parsed
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def _verify_file_write(result: Dict[str, Any]) -> tuple:
    """Verify file_write: success == True and bytes_written > 0."""
    if result.get("error"):
        return False, f"file_write error: {result['error']}"
    if not result.get("success", False):
        return False, "file_write reported success=False"
    if result.get("bytes_written", 0) <= 0:
        return False, f"file_write bytes_written={result.get('bytes_written', 0)}"
    return True, "file_write succeeded"


def _verify_shell_exec(result: Dict[str, Any]) -> tuple:
    """Verify shell_exec: exit_code == 0."""
    if result.get("error"):
        return False, f"shell_exec error: {result['error']}"
    exit_code = result.get("exit_code")
    if exit_code is None:
        return False, "shell_exec missing exit_code"
    if exit_code != 0:
        return False, f"shell_exec exit_code={exit_code}"
    return True, "shell_exec succeeded"


def _verify_database_write(result: Dict[str, Any]) -> tuple:
    """Verify database_write: rows_affected > 0."""
    if result.get("error"):
        return False, f"database_write error: {result['error']}"
    rows = result.get("rows_affected", 0)
    if rows <= 0:
        return False, f"database_write rows_affected={rows}"
    return True, "database_write succeeded"


def _verify_send_email(result: Dict[str, Any]) -> tuple:
    """Verify send_email: success == True."""
    if result.get("error"):
        return False, f"send_email error: {result['error']}"
    if not result.get("success", False):
        return False, "send_email reported success=False"
    return True, "send_email succeeded"


def _verify_python_exec(result: Dict[str, Any]) -> tuple:
    """Verify python_exec: no 'error' key present."""
    if result.get("error"):
        return False, f"python_exec error: {result['error']}"
    return True, "python_exec succeeded"


# Strategy dispatch table
_VERIFICATION_STRATEGIES = {
    "file_write": _verify_file_write,
    "shell_exec": _verify_shell_exec,
    "database_write": _verify_database_write,
    "send_email": _verify_send_email,
    "python_exec": _verify_python_exec,
}


def verify_deliverables(
    tool_call_log: List[Dict[str, Any]],
    agent_result_status: str,
    config: Dict[str, Any],
) -> VerificationResult:
    """Verify agent deliverables by inspecting tool call results.

    Operates on the tool_call_log captured during execution -- does NOT
    re-run any tools. Each write-operation tool call is checked for
    success indicators in its result_excerpt.

    A task with zero write actions passes automatically.
    Read-only tools are skipped (not counted as failures).
    If result_excerpt isn't valid JSON, the action is skipped (not failed).

    Args:
        tool_call_log: List of tool call dicts from agent execution, each with
            keys: name, arguments, result_excerpt, iteration.
        agent_result_status: The agent's self-reported status string.
        config: Full config dict (used for future extensibility).

    Returns:
        VerificationResult with pass/fail and per-action details.
    """
    from .config import get_verification_config
    verification_cfg = get_verification_config(config)

    if not verification_cfg.get("enabled", True):
        return VerificationResult(
            passed=True,
            total_actions=0,
            verified_count=0,
            unverified_count=0,
            skipped_count=0,
            actions=[],
            failure_reasons=["verification disabled"],
        )

    actions: List[VerificationAction] = []
    verified_count = 0
    unverified_count = 0
    skipped_count = 0
    failure_reasons: List[str] = []

    for entry in tool_call_log:
        tool_name = entry.get("name", "")
        arguments = entry.get("arguments", {})
        result_excerpt = entry.get("result_excerpt", "")
        iteration = entry.get("iteration", 0)

        # Skip read-only tools
        if tool_name in _READ_ONLY_TOOLS:
            actions.append(VerificationAction(
                tool_name=tool_name,
                arguments=arguments,
                result_excerpt=result_excerpt,
                iteration=iteration,
                verified=None,
                verification_note="read-only tool, skipped",
            ))
            skipped_count += 1
            continue

        # Skip tools we don't have strategies for
        if tool_name not in _VERIFICATION_STRATEGIES:
            actions.append(VerificationAction(
                tool_name=tool_name,
                arguments=arguments,
                result_excerpt=result_excerpt,
                iteration=iteration,
                verified=None,
                verification_note=f"no verification strategy for {tool_name}",
            ))
            skipped_count += 1
            continue

        # Parse result JSON
        parsed_result = _parse_result_json(result_excerpt)
        if parsed_result is None:
            # Can't parse result -- skip, not fail
            actions.append(VerificationAction(
                tool_name=tool_name,
                arguments=arguments,
                result_excerpt=result_excerpt,
                iteration=iteration,
                verified=None,
                verification_note="result_excerpt not valid JSON, skipped",
            ))
            skipped_count += 1
            continue

        # Apply verification strategy
        strategy = _VERIFICATION_STRATEGIES[tool_name]
        passed, note = strategy(parsed_result)

        actions.append(VerificationAction(
            tool_name=tool_name,
            arguments=arguments,
            result_excerpt=result_excerpt,
            iteration=iteration,
            verified=passed,
            verification_note=note,
        ))

        if passed:
            verified_count += 1
        else:
            unverified_count += 1
            failure_reasons.append(f"{tool_name} (iter {iteration}): {note}")

    total_actions = verified_count + unverified_count + skipped_count

    # A task with zero write actions passes automatically
    # A task passes if there are no unverified actions
    overall_passed = unverified_count == 0

    return VerificationResult(
        passed=overall_passed,
        total_actions=total_actions,
        verified_count=verified_count,
        unverified_count=unverified_count,
        skipped_count=skipped_count,
        actions=actions,
        failure_reasons=failure_reasons,
    )


def record_intent_ledger(
    task_id: int,
    trace_id: str,
    agent_name: str,
    user_request: str,
    tool_call_log: List[Dict[str, Any]],
    verification_result: VerificationResult,
    confidence_score: float,
    db_path: str,
) -> None:
    """Record a verification result in the intent_ledger table.

    Always records (pass or fail) to maintain a complete audit trail.

    Args:
        task_id: Task ID being verified.
        trace_id: Dispatch trace ID.
        agent_name: Agent that executed the task.
        user_request: Original task description/user request.
        tool_call_log: Raw tool call log from execution.
        verification_result: Output from verify_deliverables().
        confidence_score: Agent's self-reported confidence score.
        db_path: Path to coordination.db.
    """
    # Determine verification_status from result
    if verification_result.passed:
        if verification_result.unverified_count == 0 and verification_result.verified_count > 0:
            status = "verified"
        elif verification_result.total_actions == 0:
            status = "skipped"
        else:
            status = "verified"
    else:
        if verification_result.verified_count > 0:
            status = "partial"
        else:
            status = "failed"

    # Serialize actions for storage
    verified_actions_json = json.dumps(
        [
            {
                "tool_name": a.tool_name,
                "verified": a.verified,
                "verification_note": a.verification_note,
                "iteration": a.iteration,
            }
            for a in verification_result.actions
        ],
        default=str,
    )

    tool_call_log_json = json.dumps(tool_call_log, default=str)
    now = datetime.datetime.utcnow().isoformat() + "Z"

    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO intent_ledger "
            "(task_id, trace_id, agent_name, user_request, tool_call_log, "
            " verified_actions, verification_status, confidence_score, verified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                trace_id,
                agent_name,
                user_request[:2000] if user_request else "",
                tool_call_log_json,
                verified_actions_json,
                status,
                confidence_score,
                now,
            ),
        )
        conn.commit()
        conn.close()
        logger.info(
            "Recorded intent ledger: task=%s trace=%s status=%s "
            "verified=%d unverified=%d skipped=%d",
            task_id, trace_id, status,
            verification_result.verified_count,
            verification_result.unverified_count,
            verification_result.skipped_count,
        )
    except sqlite3.Error as e:
        logger.warning("Failed to record intent_ledger entry: %s", e)
