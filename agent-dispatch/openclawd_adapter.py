"""
OpenClawd Adapter - Isolation Layer

This is the ONLY module in agent-dispatch that imports from orchestrator-dashboard.
All interactions with the existing OpenClawd system go through this module.

Wraps every call in try/except catching TypeError (signature changes)
and sqlite3.Error (schema changes) to report compatibility issues gracefully.
"""

import os
import sys
import sqlite3
from typing import Any, Dict, List, Optional

from .config import DEFAULT_DB_PATH


class OpenClawdIncompatibleError(Exception):
    """Raised when an orchestrator-dashboard method is incompatible."""

    def __init__(self, method: str, original_error: Exception):
        self.method = method
        self.original_error = original_error
        super().__init__(
            f"OpenClawd incompatible: {method}() failed with "
            f"{type(original_error).__name__}: {original_error}"
        )


# ── Import orchestrator-dashboard modules with defensive wrapping ──

_orchestrator_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "orchestrator-dashboard",
)

if _orchestrator_dir not in sys.path:
    sys.path.insert(0, _orchestrator_dir)

try:
    from dashboard import OrchestratorDashboard
    from agent_coordinator import AgentCoordinator
    from heartbeat_integration import george_coordination_summary as _george_coordination_summary

    _IMPORT_OK = True
    _IMPORT_ERROR: Optional[str] = None
except ImportError as exc:
    _IMPORT_OK = False
    _IMPORT_ERROR = str(exc)
    OrchestratorDashboard = None  # type: ignore[assignment,misc]
    AgentCoordinator = None  # type: ignore[assignment,misc]
    _george_coordination_summary = None  # type: ignore[assignment]


def _get_db_path() -> str:
    """Resolve the database path using env var with fallback."""
    return os.environ.get("OPENCLAWD_DB_PATH", DEFAULT_DB_PATH)


class OpenClawdAdapter:
    """
    Single integration point between agent-dispatch and orchestrator-dashboard.

    Every public method wraps the underlying call in try/except to catch
    TypeError (signature changes) and sqlite3.Error (schema changes).
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _get_db_path()
        self._dashboard: Any = None
        self._coordinator: Any = None

        if not _IMPORT_OK:
            raise OpenClawdIncompatibleError(
                "__init__",
                ImportError(_IMPORT_ERROR or "orchestrator-dashboard import failed"),
            )

        try:
            self._dashboard = OrchestratorDashboard(db_path=self._db_path)
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("OrchestratorDashboard.__init__", exc)

        try:
            self._coordinator = AgentCoordinator()
            # Monkey-patch the coordinator's dashboard with our correctly-configured instance
            self._coordinator.dashboard = self._dashboard
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("AgentCoordinator.__init__", exc)

    # ── Task Management ─────────────────────────────────────────

    def create_task(
        self,
        title: str,
        description: str,
        domain: str,
        priority: int = 3,
        assigned_agent: Optional[str] = None,
        deliverable_type: str = "report",
        estimated_effort: int = 5,
        business_impact: int = 3,
    ) -> int:
        """Create a new task via the orchestrator dashboard."""
        try:
            return self._dashboard.create_task(
                title=title,
                description=description,
                domain=domain,
                priority=priority,
                assigned_agent=assigned_agent,
                deliverable_type=deliverable_type,
                estimated_effort=estimated_effort,
                business_impact=business_impact,
            )
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("create_task", exc)

    def complete_task(
        self,
        task_id: int,
        agent_name: str,
        deliverable_url: Optional[str] = None,
    ) -> bool:
        """Mark a task as completed."""
        try:
            return self._dashboard.complete_task(
                task_id=task_id,
                agent_name=agent_name,
                deliverable_url=deliverable_url,
            )
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("complete_task", exc)

    def add_task_contribution(
        self,
        task_id: int,
        agent_name: str,
        contribution_type: str,
        content: str,
    ) -> bool:
        """Add a contribution to a task."""
        try:
            return self._dashboard.add_task_contribution(
                task_id=task_id,
                agent_name=agent_name,
                contribution_type=contribution_type,
                content=content,
            )
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("add_task_contribution", exc)

    # ── Activity / Notifications ────────────────────────────────

    def log_agent_activity(
        self,
        agent_name: str,
        task_id: Optional[int],
        activity_type: str,
        message: str,
    ) -> None:
        """Log agent activity."""
        try:
            self._dashboard.log_agent_activity(
                agent_name=agent_name,
                task_id=task_id,
                activity_type=activity_type,
                message=message,
            )
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("log_agent_activity", exc)

    def create_notification(
        self,
        task_id: Optional[int],
        message: str,
        urgency: str = "normal",
    ) -> None:
        """Create a notification for Alan/George."""
        try:
            self._dashboard.create_notification(
                task_id=task_id,
                message=message,
                urgency=urgency,
            )
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("create_notification", exc)

    def squad_chat_post(
        self,
        agent_name: str,
        message: str,
        related_task_id: Optional[int] = None,
    ) -> None:
        """Post to squad chat."""
        try:
            self._dashboard.squad_chat_post(
                agent_name=agent_name,
                message=message,
                related_task_id=related_task_id,
            )
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("squad_chat_post", exc)

    def get_dashboard_summary(self) -> Dict:
        """Get overview for dashboard display."""
        try:
            return self._dashboard.get_dashboard_summary()
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("get_dashboard_summary", exc)

    # ── Agent Coordination ──────────────────────────────────────

    def agent_checkin(self, agent_name: str) -> Dict:
        """Process agent check-in and return relevant tasks."""
        try:
            return self._dashboard.agent_checkin(agent_name=agent_name)
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("agent_checkin", exc)

    def determine_agents(self, task_content: str) -> List[str]:
        """Determine which agents should handle a task."""
        try:
            return self._coordinator._determine_relevant_agents(task_content)
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("determine_agents", exc)

    def get_coordination_summary(self) -> str:
        """Get George's coordination summary."""
        try:
            return _george_coordination_summary()
        except (TypeError, sqlite3.Error) as exc:
            raise OpenClawdIncompatibleError("get_coordination_summary", exc)
