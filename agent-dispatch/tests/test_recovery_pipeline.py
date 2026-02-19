"""Integration test for the full recovery pipeline on RESULT_SCHEMA_INVALID error.

Simulates a task that fails with RESULT_SCHEMA_INVALID on the first attempt
and succeeds on the second. Verifies all 8 recovery stages execute correctly:
1. CAPTURE - ErrorContext populated
2. CLASSIFY - Error classified as Execution Error
3. DIAGNOSE - Diagnostic agent called (requires_diagnosis=True for execution errors)
4. COMPENSATE - Skipped (requires_compensation=False for RESULT_SCHEMA_INVALID)
5. STRATEGIZE - Recovery strategy selected
6. EXECUTE - Retry executed with recovery context
7. VERIFY - Success verified
8. LEARN - Failure memory recorded

US-050: Integration test for full recovery pipeline on schema error.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

# Resolve import path: agent-dispatch/ is not a valid Python package name,
# so we add its parent to sys.path and register an alias in sys.modules.
_agent_dispatch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_project_root = os.path.dirname(_agent_dispatch_dir)

# Make the agent-dispatch directory importable as a package.
# Since the directory already has __init__.py, we just need Python to find it.
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Register agent-dispatch as agent_dispatch in sys.modules via importlib
import importlib
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "agent_dispatch",
    os.path.join(_agent_dispatch_dir, "__init__.py"),
    submodule_search_locations=[_agent_dispatch_dir],
)
_agent_dispatch_mod = importlib.util.module_from_spec(_spec)
sys.modules["agent_dispatch"] = _agent_dispatch_mod
_spec.loader.exec_module(_agent_dispatch_mod)

# Register subpackages and submodules needed for patching
_recovery_dir = os.path.join(_agent_dispatch_dir, "recovery")

def _register_submodule(parent_name, parent_mod, name, path):
    """Register a submodule so patch() can resolve dotted paths."""
    full_name = f"{parent_name}.{name}"
    spec = importlib.util.spec_from_file_location(
        full_name, path,
        submodule_search_locations=[os.path.dirname(path)] if os.path.basename(path) == "__init__.py" else None,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = mod
    setattr(parent_mod, name, mod)
    spec.loader.exec_module(mod)
    return mod

# Register recovery package
_recovery_mod = _register_submodule(
    "agent_dispatch", _agent_dispatch_mod, "recovery",
    os.path.join(_recovery_dir, "__init__.py"),
)

# Register individual recovery modules that need patching
for _modname in [
    "error_classifier", "error_capture", "diagnostic_agent",
    "strategy_selector", "compensating_actions", "failure_memory",
    "recovery_executor", "recovery_pipeline",
]:
    _register_submodule(
        "agent_dispatch.recovery", _recovery_mod, _modname,
        os.path.join(_recovery_dir, f"{_modname}.py"),
    )

# Register other agent_dispatch modules used by recovery (via relative imports)
for _modname in ["structured_logging", "dispatch_db", "config"]:
    _modpath = os.path.join(_agent_dispatch_dir, f"{_modname}.py")
    if os.path.exists(_modpath):
        _register_submodule("agent_dispatch", _agent_dispatch_mod, _modname, _modpath)


class AgentRunnerError(Exception):
    """Mock AgentRunnerError matching the real agent_runner.AgentRunnerError signature."""

    def __init__(self, message, raw_output=None, tool_call_log=None, stop_reason=None):
        super().__init__(message)
        self.raw_output = raw_output
        self.tool_call_log = tool_call_log or []
        self.stop_reason = stop_reason


class TestRecoveryPipelineSchemaError(unittest.TestCase):
    """Integration test: RESULT_SCHEMA_INVALID -> recovery -> success on retry."""

    def setUp(self):
        """Set up mocks for all external dependencies."""
        # ── Config ───────────────────────────────────────────
        self.config = {
            "recovery": {
                "enabled": True,
                "max_recovery_attempts": 5,
                "max_recovery_time_seconds": 1800,
                "max_concurrent_recoveries": 3,
                "recovery_timeout_per_attempt": 600,
                "diagnostic_model": "claude-haiku-4-5",
                "diagnostic_max_input_tokens": 4000,
                "diagnostic_prompt_file": "prompts/diagnostic_sop.md",
                "recovery_budget_ratio": 0.04,
                "recovery_budget_cap_usd": 2.00,
                "raw_output_max_chars": 10000,
                "min_confidence_score": 0.3,
                "failure_memory_retention_days": 90,
                "recovery_events_retention_days": 90,
                "systemic_failure_threshold_count": 3,
                "systemic_failure_window_minutes": 10,
                "max_escalations_per_hour": 5,
                "escalation_cooldown_seconds": 300,
            },
            "daily_budget_usd": 50.0,
            "provider": {"name": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        }

        # ── Task row ─────────────────────────────────────────
        self.task_row = {
            "id": 42,
            "title": "Research AI trends",
            "description": "Investigate the latest AI trends in 2026",
            "domain": "research",
            "assigned_agent": "scout",
            "dispatch_status": "failed",
        }

        # ── Dispatch run row ─────────────────────────────────
        self.dispatch_run_row = {
            "id": 100,
            "task_id": 42,
            "agent_name": "scout",
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "status": "failed",
            "attempt": 1,
            "started_at": "2026-02-15T10:00:00+00:00",
            "completed_at": "2026-02-15T10:05:00+00:00",
            "tokens_used": 5000,
            "cost_estimate": 0.015,
            "trace_id": "original-trace-id",
            "raw_output": '{"partial": "output with missing required fields"}',
            "tool_call_log": '[{"name": "web_search", "arguments": {"query": "AI trends"}, "result_excerpt": "results...", "iteration": 1}]',
            "stop_reason": "validation_error",
            "error_context": '{"exception_type": "AgentRunnerError", "message": "missing required fields in agent-result"}',
        }

        # ── Runner error simulating RESULT_SCHEMA_INVALID ────
        self.runner_error = AgentRunnerError(
            "missing required fields in agent-result",
            raw_output='{"partial": "output"}',
            tool_call_log=[
                {"name": "web_search", "arguments": {"query": "AI trends"}, "result_excerpt": "results...", "iteration": 1}
            ],
            stop_reason="validation_error",
        )

        # ── Mock dispatch_db ─────────────────────────────────
        self.mock_dispatch_db = MagicMock()

        # Reader connection mock
        self.mock_reader = MagicMock()
        self.mock_dispatch_db.get_reader_connection.return_value = self.mock_reader

        # Writer connection mock
        self.mock_writer = MagicMock()
        self.mock_dispatch_db.get_writer_connection.return_value = self.mock_writer

        # Concurrency guard: no active recoveries
        mock_count_cursor = MagicMock()
        mock_count_cursor.fetchone.return_value = (0,)

        # Atomic claim: succeed (rowcount=1)
        mock_claim_cursor = MagicMock()
        mock_claim_cursor.rowcount = 1

        def reader_execute_side_effect(sql, params=None):
            if "SELECT COUNT" in sql and "recovering" in sql:
                return mock_count_cursor
            if "SUM(cost_estimate)" in sql:
                mock_budget = MagicMock()
                mock_budget.fetchone.return_value = (0.0,)
                return mock_budget
            if "provider_health" in sql:
                mock_health = MagicMock()
                mock_health.fetchall.return_value = []
                return mock_health
            if "SELECT * FROM tasks" in sql:
                mock_task = MagicMock()
                mock_task.fetchone.return_value = self._make_row(self.task_row)
                return mock_task
            return MagicMock()

        self.mock_reader.execute = MagicMock(side_effect=reader_execute_side_effect)

        def writer_execute_side_effect(sql, params=None):
            if "UPDATE tasks SET dispatch_status" in sql:
                return mock_claim_cursor
            if "INSERT INTO failure_memory" in sql:
                mock_insert = MagicMock()
                mock_insert.rowcount = 1
                return mock_insert
            if "UPDATE dispatch_runs" in sql:
                mock_update = MagicMock()
                mock_update.rowcount = 1
                return mock_update
            return MagicMock()

        self.mock_writer.execute = MagicMock(side_effect=writer_execute_side_effect)

    def _make_row(self, d):
        """Create a mock sqlite3.Row-like object from dict."""
        row = MagicMock()
        row.__getitem__ = lambda self_row, key: d[key]
        row.keys = lambda: d.keys()
        row.__iter__ = lambda self_row: iter(d)
        row.__len__ = lambda self_row: len(d)
        return row

    @patch("agent_dispatch.recovery.recovery_pipeline._check_systemic_and_alert")
    @patch("agent_dispatch.recovery.recovery_pipeline._send_escalation_notification")
    @patch("agent_dispatch.recovery.recovery_pipeline._send_decomposition_notification")
    @patch("agent_dispatch.recovery.failure_memory.record_attempt")
    @patch("agent_dispatch.recovery.failure_memory.find_similar_fixes")
    @patch("agent_dispatch.recovery.failure_memory.detect_systemic_pattern")
    @patch("agent_dispatch.recovery.compensating_actions.compensate")
    @patch("agent_dispatch.recovery.diagnostic_agent.diagnose_failure")
    @patch("agent_dispatch.recovery.recovery_executor.execute")
    @patch("agent_dispatch.recovery.recovery_pipeline._log_recovery_event")
    def test_full_recovery_pipeline_schema_error(
        self,
        mock_log_event,
        mock_executor_execute,
        mock_diagnose,
        mock_compensate,
        mock_detect_systemic,
        mock_find_similar,
        mock_record_attempt,
        mock_decomp_notif,
        mock_escalation_notif,
        mock_systemic_alert,
    ):
        """Test: RESULT_SCHEMA_INVALID fails first attempt, succeeds on retry."""
        from agent_dispatch.recovery.recovery_pipeline import handle_failure, RecoveryOutcome
        from agent_dispatch.recovery.recovery_executor import RecoveryExecutionResult

        # find_similar_fixes returns empty (no history)
        mock_find_similar.return_value = []

        # diagnose_failure returns a diagnostic output
        from agent_dispatch.recovery.diagnostic_agent import DiagnosticOutput
        mock_diagnostic_output = DiagnosticOutput(
            root_cause="Agent output missing required 'status' and 'deliverable_content' fields in <agent-result> block",
            root_cause_category="output_format",
            confidence=0.85,
            recommended_strategy="fix_specific",
            specific_fix="Ensure agent wraps output in proper <agent-result> XML with all required fields: status, deliverable_content, confidence_score",
            tools_to_adjust=[],
            avoid_approaches=["Do not truncate the agent-result block"],
            needs_human=False,
            is_repeat_failure=False,
            cycle_detected=False,
        )
        mock_diagnose.return_value = mock_diagnostic_output

        # compensate not needed (requires_compensation=False for RESULT_SCHEMA_INVALID)
        mock_compensate.return_value = True

        # recovery_executor.execute: succeed on first call (attempt 1)
        mock_exec_success = RecoveryExecutionResult(
            success=True,
            agent_result=SimpleNamespace(
                status="completed",
                deliverable_content="AI trends report with comprehensive findings",
                confidence_score=0.9,
            ),
            new_error_code=None,
            new_error_message=None,
            same_error=False,
            tokens_used=3000,
            duration_ms=15000,
            trace_id="recovery-trace-123",
        )
        mock_executor_execute.return_value = mock_exec_success

        # record_attempt succeeds
        mock_record_attempt.return_value = True

        # detect_systemic returns False
        mock_detect_systemic.return_value = False

        # ── Execute the recovery pipeline ─────────────────────
        outcome = handle_failure(
            task_id=42,
            runner_error=self.runner_error,
            task_row=self.task_row,
            dispatch_run_row=self.dispatch_run_row,
            config=self.config,
            dispatch_db=self.mock_dispatch_db,
        )

        # ── Verify RecoveryOutcome ────────────────────────────
        self.assertIsInstance(outcome, RecoveryOutcome)
        self.assertTrue(outcome.success, "Recovery should succeed")
        self.assertEqual(outcome.final_status, "completed")
        self.assertEqual(outcome.task_id, 42)
        self.assertEqual(outcome.attempts_used, 1)
        self.assertIsNotNone(outcome.winning_strategy)
        self.assertEqual(outcome.winning_strategy, "fix_specific")
        self.assertIsNone(outcome.escalation_reason)
        self.assertGreater(outcome.total_duration_ms, 0)
        self.assertEqual(outcome.error_code, "RESULT_SCHEMA_INVALID")
        self.assertIsNotNone(outcome.trace_id)

        # ── Verify Stage 1: CAPTURE ───────────────────────────
        # capture_error is called internally (not mocked) — verified by
        # the error_code in the outcome being RESULT_SCHEMA_INVALID
        self.assertEqual(outcome.error_code, "RESULT_SCHEMA_INVALID")

        # ── Verify Stage 3: DIAGNOSE ──────────────────────────
        mock_diagnose.assert_called_once()
        diag_call_args = mock_diagnose.call_args
        diagnostic_input = diag_call_args[0][0] if diag_call_args[0] else diag_call_args[1].get("diagnostic_input")
        self.assertIsNotNone(diagnostic_input)

        # ── Verify Stage 4: COMPENSATE ────────────────────────
        # RESULT_SCHEMA_INVALID has requires_compensation=False
        mock_compensate.assert_not_called()

        # ── Verify Stage 6: EXECUTE ───────────────────────────
        mock_executor_execute.assert_called_once()
        exec_call = mock_executor_execute.call_args
        exec_kwargs = exec_call[1] if exec_call[1] else {}
        if exec_call[0]:
            self.assertEqual(exec_call[0][0], 42)
        else:
            self.assertEqual(exec_kwargs.get("task_id"), 42)

        # ── Verify Stage 8: LEARN ─────────────────────────────
        mock_record_attempt.assert_called_once()
        learn_call = mock_record_attempt.call_args
        learn_kwargs = learn_call[1] if learn_call[1] else {}
        self.assertEqual(learn_kwargs.get("task_id"), 42)
        self.assertEqual(learn_kwargs.get("error_code"), "RESULT_SCHEMA_INVALID")
        self.assertTrue(learn_kwargs.get("success"))
        self.assertEqual(learn_kwargs.get("recovery_tier"), 1)

        # ── Verify recovery events logged for all stages ──────
        event_types_logged = []
        for c in mock_log_event.call_args_list:
            args = c[0]
            if len(args) >= 4:
                event_types_logged.append(args[3])

        expected_events = [
            "recovery.claim.success",
            "recovery.capture",
            "recovery.classify",
            "recovery.diagnose.start",
            "recovery.diagnose.complete",
            "recovery.strategy.selected",
            "recovery.execute.start",
            "recovery.execute.complete",
            "recovery.verify",
            "recovery.learn",
        ]
        for expected_event in expected_events:
            self.assertIn(
                expected_event,
                event_types_logged,
                f"Expected recovery event '{expected_event}' not found in logged events: {event_types_logged}",
            )

    @patch("agent_dispatch.recovery.recovery_pipeline._check_systemic_and_alert")
    @patch("agent_dispatch.recovery.recovery_pipeline._send_escalation_notification")
    @patch("agent_dispatch.recovery.failure_memory.record_attempt")
    @patch("agent_dispatch.recovery.failure_memory.find_similar_fixes")
    @patch("agent_dispatch.recovery.compensating_actions.compensate")
    @patch("agent_dispatch.recovery.diagnostic_agent.diagnose_failure")
    @patch("agent_dispatch.recovery.recovery_executor.execute")
    @patch("agent_dispatch.recovery.recovery_pipeline._log_recovery_event")
    def test_recovery_pipeline_fails_then_succeeds_on_second_attempt(
        self,
        mock_log_event,
        mock_executor_execute,
        mock_diagnose,
        mock_compensate,
        mock_find_similar,
        mock_record_attempt,
        mock_escalation_notif,
        mock_systemic_alert,
    ):
        """Test: First recovery attempt fails, second succeeds (Tier 2 strategy)."""
        from agent_dispatch.recovery.recovery_pipeline import handle_failure, RecoveryOutcome
        from agent_dispatch.recovery.recovery_executor import RecoveryExecutionResult
        from agent_dispatch.recovery.diagnostic_agent import DiagnosticOutput

        mock_find_similar.return_value = []

        mock_diagnose.return_value = DiagnosticOutput(
            root_cause="Missing <agent-result> block wrapper",
            root_cause_category="output_format",
            confidence=0.8,
            recommended_strategy="fix_specific",
            specific_fix="Wrap output in <agent-result> XML",
            needs_human=False,
            is_repeat_failure=False,
            cycle_detected=False,
        )

        # First execution fails, second succeeds
        mock_exec_fail = RecoveryExecutionResult(
            success=False,
            new_error_code="RESULT_SCHEMA_INVALID",
            new_error_message="Still missing fields",
            same_error=True,
            tokens_used=2000,
            duration_ms=10000,
            trace_id="trace-fail-1",
        )
        mock_exec_success = RecoveryExecutionResult(
            success=True,
            agent_result=SimpleNamespace(
                status="completed",
                deliverable_content="Complete output",
                confidence_score=0.95,
            ),
            tokens_used=3500,
            duration_ms=12000,
            trace_id="trace-success-2",
        )
        mock_executor_execute.side_effect = [mock_exec_fail, mock_exec_success]
        mock_record_attempt.return_value = True

        outcome = handle_failure(
            task_id=42,
            runner_error=self.runner_error,
            task_row=self.task_row,
            dispatch_run_row=self.dispatch_run_row,
            config=self.config,
            dispatch_db=self.mock_dispatch_db,
        )

        # Should succeed on second attempt
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.final_status, "completed")
        self.assertEqual(outcome.attempts_used, 2)
        self.assertEqual(outcome.winning_strategy, "rewrite_with_diagnosis")
        self.assertEqual(outcome.error_code, "RESULT_SCHEMA_INVALID")

        # Executor called twice (fail then succeed)
        self.assertEqual(mock_executor_execute.call_count, 2)

        # record_attempt called once for the successful recovery
        mock_record_attempt.assert_called_once()
        learn_kwargs = mock_record_attempt.call_args[1]
        self.assertTrue(learn_kwargs["success"])


class TestRecoveryPipelineNoStructuredResult(unittest.TestCase):
    """Test: NO_STRUCTURED_RESULT error code classification and recovery routing."""

    def setUp(self):
        """Set up mocks for external dependencies."""
        self.config = {
            "recovery": {
                "enabled": True,
                "max_recovery_attempts": 5,
                "max_recovery_time_seconds": 1800,
                "max_concurrent_recoveries": 3,
                "recovery_timeout_per_attempt": 600,
                "diagnostic_model": "claude-haiku-4-5",
                "diagnostic_max_input_tokens": 4000,
                "diagnostic_prompt_file": "prompts/diagnostic_sop.md",
                "recovery_budget_ratio": 0.04,
                "recovery_budget_cap_usd": 2.00,
                "raw_output_max_chars": 10000,
                "min_confidence_score": 0.3,
                "failure_memory_retention_days": 90,
                "recovery_events_retention_days": 90,
                "systemic_failure_threshold_count": 3,
                "systemic_failure_window_minutes": 10,
                "max_escalations_per_hour": 5,
                "escalation_cooldown_seconds": 300,
            },
            "daily_budget_usd": 50.0,
            "provider": {"name": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        }

        self.task_row = {
            "id": 99,
            "title": "Generate report",
            "description": "Create a summary report",
            "domain": "research",
            "assigned_agent": "research",
            "dispatch_status": "failed",
        }

        self.dispatch_run_row = {
            "id": 200,
            "task_id": 99,
            "agent_name": "research",
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "status": "failed",
            "attempt": 1,
            "started_at": "2026-02-15T10:00:00+00:00",
            "completed_at": "2026-02-15T10:05:00+00:00",
            "tokens_used": 3000,
            "cost_estimate": 0.01,
            "trace_id": "no-result-trace",
            "raw_output": "Here is my analysis but I forgot the agent-result block...",
            "tool_call_log": "[]",
            "stop_reason": "no_structured_result",
            "error_context": '{"exception_type": "AgentRunnerError", "message": "No <agent-result> block found in agent response for research"}',
        }

        self.runner_error = AgentRunnerError(
            "No <agent-result> block found in agent response for research",
            raw_output="Here is my analysis but I forgot the agent-result block...",
            tool_call_log=[],
            stop_reason="no_structured_result",
        )

    def test_no_structured_result_error_code(self):
        """Verify NO_STRUCTURED_RESULT error code is correctly detected."""
        from agent_dispatch.recovery.error_classifier import detect_error_code

        code = detect_error_code(exception=self.runner_error)
        self.assertEqual(code, "NO_STRUCTURED_RESULT")

    def test_no_structured_result_taxonomy(self):
        """Verify NO_STRUCTURED_RESULT has correct recovery parameters."""
        from agent_dispatch.recovery.error_classifier import classify_error

        category = classify_error("NO_STRUCTURED_RESULT")
        self.assertEqual(category.category, "execution")
        self.assertEqual(category.max_retries, 3)
        self.assertTrue(category.requires_diagnosis)

    def test_verification_failed_error_code(self):
        """Verify VERIFICATION_FAILED error code is correctly detected."""
        from agent_dispatch.recovery.error_classifier import detect_error_code

        err = AgentRunnerError(
            "Deliverable verification failed: 2/3 actions unverified",
            stop_reason="verification_failed",
        )
        code = detect_error_code(exception=err)
        self.assertEqual(code, "VERIFICATION_FAILED")

    def test_verification_failed_taxonomy(self):
        """Verify VERIFICATION_FAILED has correct recovery parameters."""
        from agent_dispatch.recovery.error_classifier import classify_error

        category = classify_error("VERIFICATION_FAILED")
        self.assertEqual(category.category, "execution")
        self.assertEqual(category.max_retries, 2)
        self.assertTrue(category.requires_diagnosis)


if __name__ == "__main__":
    unittest.main()
