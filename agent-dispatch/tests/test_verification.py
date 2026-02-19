"""Tests for the deliverable verification module.

Covers verification strategies for all tool types, edge cases
(empty logs, disabled config, unparseable results), and the
verify_deliverables() aggregation logic.
"""

import sys
import os
import unittest

# Resolve import path for agent-dispatch package
_agent_dispatch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_project_root = os.path.dirname(_agent_dispatch_dir)

if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

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

# Register submodules needed by verification
for _modname in ["config", "verification"]:
    _modpath = os.path.join(_agent_dispatch_dir, f"{_modname}.py")
    if os.path.exists(_modpath):
        full_name = f"agent_dispatch.{_modname}"
        spec = importlib.util.spec_from_file_location(full_name, _modpath)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = mod
        setattr(_agent_dispatch_mod, _modname, mod)
        spec.loader.exec_module(mod)

from agent_dispatch.verification import verify_deliverables, VerificationResult


class TestVerifyFileWrite(unittest.TestCase):
    """Tests for file_write verification strategy."""

    def test_verify_file_write_success(self):
        log = [
            {
                "name": "file_write",
                "arguments": {"path": "/tmp/out.txt", "content": "hello"},
                "result_excerpt": '{"success": true, "bytes_written": 5}',
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertTrue(result.passed)
        self.assertEqual(result.verified_count, 1)
        self.assertEqual(result.unverified_count, 0)

    def test_verify_file_write_failure(self):
        log = [
            {
                "name": "file_write",
                "arguments": {"path": "/tmp/out.txt", "content": "hello"},
                "result_excerpt": '{"success": false, "bytes_written": 0}',
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertFalse(result.passed)
        self.assertEqual(result.unverified_count, 1)
        self.assertTrue(len(result.failure_reasons) > 0)

    def test_verify_file_write_error_key(self):
        log = [
            {
                "name": "file_write",
                "arguments": {"path": "/tmp/out.txt"},
                "result_excerpt": '{"error": "Permission denied"}',
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertFalse(result.passed)
        self.assertEqual(result.unverified_count, 1)


class TestVerifyShellExec(unittest.TestCase):
    """Tests for shell_exec verification strategy."""

    def test_verify_shell_exec_success(self):
        log = [
            {
                "name": "shell_exec",
                "arguments": {"command": "echo hello"},
                "result_excerpt": '{"exit_code": 0, "stdout": "hello"}',
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertTrue(result.passed)
        self.assertEqual(result.verified_count, 1)

    def test_verify_shell_exec_nonzero_exit(self):
        log = [
            {
                "name": "shell_exec",
                "arguments": {"command": "false"},
                "result_excerpt": '{"exit_code": 1, "stderr": "error"}',
                "iteration": 2,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertFalse(result.passed)
        self.assertEqual(result.unverified_count, 1)
        self.assertIn("exit_code=1", result.failure_reasons[0])


class TestVerifyDatabaseWrite(unittest.TestCase):
    """Tests for database_write verification strategy."""

    def test_verify_database_write_zero_rows(self):
        log = [
            {
                "name": "database_write",
                "arguments": {"query": "INSERT INTO t VALUES (1)"},
                "result_excerpt": '{"rows_affected": 0}',
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertFalse(result.passed)
        self.assertEqual(result.unverified_count, 1)

    def test_verify_database_write_success(self):
        log = [
            {
                "name": "database_write",
                "arguments": {"query": "INSERT INTO t VALUES (1)"},
                "result_excerpt": '{"rows_affected": 1}',
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertTrue(result.passed)


class TestVerifyMixedActions(unittest.TestCase):
    """Tests for mixed tool call logs."""

    def test_verify_mixed_actions_correct_counts(self):
        log = [
            {
                "name": "file_write",
                "arguments": {"path": "/tmp/a.txt"},
                "result_excerpt": '{"success": true, "bytes_written": 10}',
                "iteration": 1,
            },
            {
                "name": "shell_exec",
                "arguments": {"command": "ls"},
                "result_excerpt": '{"exit_code": 1}',
                "iteration": 2,
            },
            {
                "name": "file_read",
                "arguments": {"path": "/tmp/b.txt"},
                "result_excerpt": '{"content": "data"}',
                "iteration": 3,
            },
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertFalse(result.passed)
        self.assertEqual(result.verified_count, 1)   # file_write passed
        self.assertEqual(result.unverified_count, 1)  # shell_exec failed
        self.assertEqual(result.skipped_count, 1)     # file_read skipped
        self.assertEqual(result.total_actions, 3)


class TestVerifyReadOnlyTools(unittest.TestCase):
    """Tests for read-only tool skipping."""

    def test_verify_read_only_tools_skipped(self):
        log = [
            {
                "name": "web_search",
                "arguments": {"query": "test"},
                "result_excerpt": '{"results": []}',
                "iteration": 1,
            },
            {
                "name": "database_query",
                "arguments": {"query": "SELECT 1"},
                "result_excerpt": '{"rows": []}',
                "iteration": 2,
            },
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertTrue(result.passed)
        self.assertEqual(result.skipped_count, 2)
        self.assertEqual(result.verified_count, 0)
        self.assertEqual(result.unverified_count, 0)


class TestVerifyEmptyLog(unittest.TestCase):
    """Tests for empty tool call logs."""

    def test_verify_empty_tool_call_log(self):
        result = verify_deliverables([], "completed", {})
        self.assertTrue(result.passed)
        self.assertEqual(result.total_actions, 0)
        self.assertEqual(result.verified_count, 0)
        self.assertEqual(result.unverified_count, 0)
        self.assertEqual(result.skipped_count, 0)


class TestVerifyDisabledByConfig(unittest.TestCase):
    """Tests for verification disabled via config."""

    def test_verify_disabled_by_config(self):
        log = [
            {
                "name": "shell_exec",
                "arguments": {"command": "rm -rf /"},
                "result_excerpt": '{"exit_code": 1}',
                "iteration": 1,
            }
        ]
        config = {"verification": {"enabled": False}}
        result = verify_deliverables(log, "completed", config)
        self.assertTrue(result.passed)
        self.assertEqual(result.total_actions, 0)


class TestVerifyUnparseableResult(unittest.TestCase):
    """Tests for results that aren't valid JSON."""

    def test_unparseable_result_is_skipped(self):
        log = [
            {
                "name": "file_write",
                "arguments": {"path": "/tmp/out.txt"},
                "result_excerpt": "not json at all",
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        # Unparseable result is skipped, not failed
        self.assertTrue(result.passed)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.unverified_count, 0)


class TestVerifySendEmail(unittest.TestCase):
    """Tests for send_email verification strategy."""

    def test_send_email_success(self):
        log = [
            {
                "name": "send_email",
                "arguments": {"to": "a@b.com", "body": "hi"},
                "result_excerpt": '{"success": true, "message_id": "abc123"}',
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertTrue(result.passed)

    def test_send_email_failure(self):
        log = [
            {
                "name": "send_email",
                "arguments": {"to": "a@b.com"},
                "result_excerpt": '{"success": false, "error": "SMTP timeout"}',
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertFalse(result.passed)


class TestVerifyPythonExec(unittest.TestCase):
    """Tests for python_exec verification strategy."""

    def test_python_exec_success(self):
        log = [
            {
                "name": "python_exec",
                "arguments": {"code": "print(1+1)"},
                "result_excerpt": '{"output": "2"}',
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertTrue(result.passed)

    def test_python_exec_error(self):
        log = [
            {
                "name": "python_exec",
                "arguments": {"code": "raise Exception()"},
                "result_excerpt": '{"error": "Exception raised"}',
                "iteration": 1,
            }
        ]
        result = verify_deliverables(log, "completed", {})
        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
