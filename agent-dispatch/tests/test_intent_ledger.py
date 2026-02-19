"""Tests for the intent_ledger migration and recording.

Covers:
  - Migration idempotency
  - Ledger recording on completion (verified)
  - Ledger recording on failure (failed)
"""

import sys
import os
import sqlite3
import tempfile
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

# Register submodules
for _modname in ["config", "verification", "migrations"]:
    _modpath = os.path.join(_agent_dispatch_dir, f"{_modname}.py")
    if os.path.exists(_modpath):
        full_name = f"agent_dispatch.{_modname}"
        spec = importlib.util.spec_from_file_location(full_name, _modpath)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = mod
        setattr(_agent_dispatch_mod, _modname, mod)
        spec.loader.exec_module(mod)

from agent_dispatch.migrations import (
    migrate_create_intent_ledger,
    verify_intent_ledger_table,
)
from agent_dispatch.verification import (
    VerificationAction,
    VerificationResult,
    record_intent_ledger,
)


class TestIntentLedgerMigration(unittest.TestCase):
    """Tests for intent_ledger table creation and verification."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        # Create minimal tasks table for FK
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
            "description TEXT NOT NULL, domain TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO tasks (id, title, description, domain) "
            "VALUES (1, 'Test Task', 'desc', 'research')"
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_ledger_migration_creates_table(self):
        migrate_create_intent_ledger(self.db_path)
        self.assertTrue(verify_intent_ledger_table(self.db_path))

    def test_ledger_migration_idempotent(self):
        """Running migration twice should not raise."""
        migrate_create_intent_ledger(self.db_path)
        migrate_create_intent_ledger(self.db_path)
        self.assertTrue(verify_intent_ledger_table(self.db_path))

    def test_ledger_migration_indexes_exist(self):
        migrate_create_intent_ledger(self.db_path)
        conn = sqlite3.connect(self.db_path)
        for idx_name in [
            "idx_intent_ledger_task_id",
            "idx_intent_ledger_trace_id",
            "idx_intent_ledger_status_created",
        ]:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (idx_name,),
            )
            self.assertIsNotNone(
                cursor.fetchone(),
                f"Index {idx_name} should exist",
            )
        conn.close()


class TestIntentLedgerRecording(unittest.TestCase):
    """Tests for recording entries in the intent_ledger."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        # Create tasks table + intent_ledger
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
            "description TEXT NOT NULL, domain TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO tasks (id, title, description, domain) "
            "VALUES (1, 'Test Task', 'desc', 'research')"
        )
        conn.commit()
        conn.close()
        migrate_create_intent_ledger(self.db_path)

    def tearDown(self):
        os.unlink(self.db_path)

    def test_ledger_creation_on_completion(self):
        """Verified task should be recorded with status='verified'."""
        v_result = VerificationResult(
            passed=True,
            total_actions=1,
            verified_count=1,
            unverified_count=0,
            skipped_count=0,
            actions=[
                VerificationAction(
                    tool_name="file_write",
                    arguments={"path": "/tmp/out.txt"},
                    result_excerpt='{"success": true, "bytes_written": 10}',
                    iteration=1,
                    verified=True,
                    verification_note="file_write succeeded",
                )
            ],
            failure_reasons=[],
        )
        record_intent_ledger(
            task_id=1,
            trace_id="trace-001",
            agent_name="research",
            user_request="Write a report",
            tool_call_log=[{"name": "file_write", "arguments": {}, "result_excerpt": '{"success": true}', "iteration": 1}],
            verification_result=v_result,
            confidence_score=0.9,
            db_path=self.db_path,
        )
        # Verify the record exists
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT verification_status, confidence_score FROM intent_ledger WHERE trace_id = 'trace-001'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "verified")
        self.assertAlmostEqual(row[1], 0.9)
        conn.close()

    def test_ledger_creation_on_failure(self):
        """Failed verification should be recorded with status='failed'."""
        v_result = VerificationResult(
            passed=False,
            total_actions=1,
            verified_count=0,
            unverified_count=1,
            skipped_count=0,
            actions=[
                VerificationAction(
                    tool_name="shell_exec",
                    arguments={"command": "false"},
                    result_excerpt='{"exit_code": 1}',
                    iteration=1,
                    verified=False,
                    verification_note="shell_exec exit_code=1",
                )
            ],
            failure_reasons=["shell_exec (iter 1): shell_exec exit_code=1"],
        )
        record_intent_ledger(
            task_id=1,
            trace_id="trace-002",
            agent_name="research",
            user_request="Run a script",
            tool_call_log=[{"name": "shell_exec", "arguments": {}, "result_excerpt": '{"exit_code": 1}', "iteration": 1}],
            verification_result=v_result,
            confidence_score=0.5,
            db_path=self.db_path,
        )
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT verification_status FROM intent_ledger WHERE trace_id = 'trace-002'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "failed")
        conn.close()


if __name__ == "__main__":
    unittest.main()
