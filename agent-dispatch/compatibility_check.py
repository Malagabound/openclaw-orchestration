"""
Compatibility Check Module

Validates expected tables, columns, and method signatures at startup
to detect breaking changes in orchestrator-dashboard and enter tiered
degradation mode.

Tiers:
  1 = Additive (new columns/tables added but all expected ones present)
  2 = Breaking (missing columns or changed method signatures)
  3 = Fundamental (missing core tables or classes entirely)
"""

import inspect
import sqlite3
import time
from typing import Any, Dict, List, Optional

from .config import DEFAULT_DB_PATH


# ── Expected Schema ──────────────────────────────────────────────

EXPECTED_TABLES = ["tasks", "agent_activity", "task_contributions", "notifications"]

EXPECTED_TASKS_COLUMNS = [
    "id",
    "title",
    "description",
    "status",
    "priority",
    "domain",
    "assigned_agent",
]

# Expected method signatures: method_name -> list of parameter names (excluding 'self')
EXPECTED_DASHBOARD_METHODS = {
    "create_task": ["title", "description", "domain", "priority", "assigned_agent",
                    "deliverable_type", "estimated_effort", "business_impact"],
    "complete_task": ["task_id", "agent_name", "deliverable_url"],
    "add_task_contribution": ["task_id", "agent_name", "contribution_type", "content"],
    "log_agent_activity": ["agent_name", "task_id", "activity_type", "message"],
    "create_notification": ["task_id", "message", "urgency"],
    "squad_chat_post": ["agent_name", "message", "related_task_id"],
    "get_dashboard_summary": [],
    "agent_checkin": ["agent_name"],
}

EXPECTED_COORDINATOR_METHODS = {
    "_determine_relevant_agents": ["task_content"],
}


def _get_db_path() -> str:
    """Resolve the database path."""
    import os
    return os.environ.get("OPENCLAWD_DB_PATH", DEFAULT_DB_PATH)


def _check_tables(conn: sqlite3.Connection) -> List[str]:
    """Check that all expected tables exist in the database."""
    issues: List[str] = []
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    existing_tables = {row[0] for row in cursor.fetchall()}

    for table in EXPECTED_TABLES:
        if table not in existing_tables:
            issues.append(f"Missing expected table: {table}")

    return issues


def _check_tasks_columns(conn: sqlite3.Connection) -> List[str]:
    """Check that the tasks table has all required columns."""
    issues: List[str] = []

    cursor = conn.execute("PRAGMA table_info(tasks)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for col in EXPECTED_TASKS_COLUMNS:
        if col not in existing_columns:
            issues.append(f"Missing column in tasks table: {col}")

    return issues


def _check_method_signatures(
    cls: Any,
    expected_methods: Dict[str, List[str]],
    class_name: str,
) -> List[str]:
    """Validate method signatures using inspect.signature()."""
    issues: List[str] = []

    for method_name, expected_params in expected_methods.items():
        method = getattr(cls, method_name, None)
        if method is None:
            issues.append(f"{class_name}.{method_name}() not found")
            continue

        try:
            sig = inspect.signature(method)
        except (ValueError, TypeError):
            issues.append(f"Cannot inspect {class_name}.{method_name}() signature")
            continue

        # Get parameter names excluding 'self'
        actual_params = [
            name for name, param in sig.parameters.items()
            if name != "self"
        ]

        for expected_param in expected_params:
            if expected_param not in actual_params:
                issues.append(
                    f"{class_name}.{method_name}() missing parameter: {expected_param}"
                )

    return issues


def _store_compatibility_result(
    result: Dict,
    latency_ms: float,
    db_path: Optional[str] = None,
) -> None:
    """Store compatibility check result in provider_health table.

    Args:
        result: Dict from check_compatibility() with keys: compatible, tier, issues.
        latency_ms: Time taken for the check in milliseconds.
        db_path: Optional database path override.
    """
    db = db_path or _get_db_path()

    try:
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        passed = 1 if result["compatible"] else 0
        error_message = None if result["compatible"] else "; ".join(result["issues"])

        conn.execute(
            """
            INSERT INTO provider_health
                (provider, model, test_name, passed, latency_ms, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "openclawd",
                "system",
                "compatibility_check",
                passed,
                latency_ms,
                error_message,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as exc:
        # Log but don't fail startup if health table isn't available yet
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "Could not store compatibility check result in provider_health: %s", exc
        )


def check_compatibility(db_path: Optional[str] = None, store_result: bool = True) -> Dict:
    """
    Run all compatibility checks and return a result dict.

    Args:
        db_path: Optional database path override.
        store_result: If True, write result to provider_health table (default: True).

    Returns:
        dict with keys:
          - compatible (bool): True if no issues found
          - tier (int): 1=additive, 2=breaking, 3=fundamental
          - issues (list[str]): Human-readable issue descriptions
    """
    start_time = time.time()
    issues: List[str] = []
    db = db_path or _get_db_path()

    # ── Schema checks ───────────────────────────────────────────

    try:
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    except sqlite3.Error as exc:
        result = {
            "compatible": False,
            "tier": 3,
            "issues": [f"Cannot connect to database: {exc}"],
        }
        latency_ms = (time.time() - start_time) * 1000
        if store_result:
            _store_compatibility_result(result, latency_ms, db_path)
        return result

    try:
        table_issues = _check_tables(conn)
        issues.extend(table_issues)

        # Only check columns if tasks table exists
        if not any("Missing expected table: tasks" in i for i in table_issues):
            column_issues = _check_tasks_columns(conn)
            issues.extend(column_issues)
    finally:
        conn.close()

    # ── Method signature checks ─────────────────────────────────

    try:
        from .openclawd_adapter import OrchestratorDashboard, AgentCoordinator, _IMPORT_OK
    except ImportError:
        _IMPORT_OK = False

    if not _IMPORT_OK:
        issues.append("Cannot import OrchestratorDashboard or AgentCoordinator")
    else:
        if OrchestratorDashboard is not None:
            issues.extend(
                _check_method_signatures(
                    OrchestratorDashboard,
                    EXPECTED_DASHBOARD_METHODS,
                    "OrchestratorDashboard",
                )
            )
        if AgentCoordinator is not None:
            issues.extend(
                _check_method_signatures(
                    AgentCoordinator,
                    EXPECTED_COORDINATOR_METHODS,
                    "AgentCoordinator",
                )
            )

    # ── Determine tier ──────────────────────────────────────────

    if not issues:
        result = {"compatible": True, "tier": 1, "issues": []}
    else:
        # Tier 3: Missing core tables or classes
        has_missing_table = any("Missing expected table" in i for i in issues)
        has_import_failure = any("Cannot import" in i for i in issues)
        has_db_failure = any("Cannot connect" in i for i in issues)

        if has_missing_table or has_import_failure or has_db_failure:
            result = {"compatible": False, "tier": 3, "issues": issues}
        else:
            # Tier 2: Missing columns or signature mismatches
            result = {"compatible": False, "tier": 2, "issues": issues}

    # Store result in provider_health table
    latency_ms = (time.time() - start_time) * 1000
    if store_result:
        _store_compatibility_result(result, latency_ms, db_path)

    return result
