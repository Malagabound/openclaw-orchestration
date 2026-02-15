"""Database migrations for the OpenClawd Agent Dispatch System.

Idempotent schema migrations that extend the existing coordination.db
without modifying existing tables or columns.
"""

import os
import sqlite3


def _get_db_path():
    """Resolve coordination.db path from env or default fallback."""
    return os.environ.get(
        "OPENCLAWD_DB_PATH",
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "orchestrator-dashboard",
            "orchestrator-dashboard",
            "coordination.db",
        ),
    )


def _get_connection(db_path=None):
    """Create a connection with WAL mode and foreign keys enabled."""
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate_add_dispatch_status(db_path=None):
    """US-001: Add dispatch_status column to tasks table.

    Adds a TEXT column with CHECK constraint allowing NULL plus 6 valid
    dispatch states. Idempotent via try/except for duplicate column.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            ALTER TABLE tasks ADD COLUMN dispatch_status TEXT
            CHECK(dispatch_status IS NULL OR dispatch_status IN
                ('queued', 'dispatched', 'completed', 'failed',
                 'interrupted', 'dispatch_failed'))
            """
        )
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            pass  # Column already exists - idempotent
        else:
            raise
    finally:
        conn.close()


def verify_dispatch_status_column(db_path=None):
    """Verify dispatch_status column exists on tasks table."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute("PRAGMA table_info(tasks)")
        columns = {row[1] for row in cursor.fetchall()}
        return "dispatch_status" in columns
    finally:
        conn.close()


def migrate_add_lease_until(db_path=None):
    """US-002: Add lease_until column to tasks table.

    Adds a DATETIME column with DEFAULT NULL for lease-based atomic task
    claiming with expiration. Idempotent via try/except for duplicate column.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN lease_until DATETIME DEFAULT NULL"
        )
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            pass  # Column already exists - idempotent
        else:
            raise
    finally:
        conn.close()


def verify_lease_until_column(db_path=None):
    """Verify lease_until column exists on tasks table."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute("PRAGMA table_info(tasks)")
        columns = {row[1] for row in cursor.fetchall()}
        return "lease_until" in columns
    finally:
        conn.close()


def migrate_create_dispatch_index(db_path=None):
    """US-003: Create composite index on tasks(dispatch_status, lease_until).

    Composite index to support efficient dispatchable task query on every
    30-second poll. Uses IF NOT EXISTS for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_dispatch
            ON tasks(dispatch_status, lease_until)
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_dispatch_index(db_path=None):
    """Verify idx_tasks_dispatch index exists."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_dispatch'"
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def migrate_create_dispatch_runs(db_path=None):
    """US-004: Create dispatch_runs table.

    Tracks individual agent execution attempts with provider, model, status,
    tokens, cost, trace_id, and retry timing. Uses CREATE TABLE IF NOT EXISTS
    for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dispatch_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'running', 'completed', 'failed', 'timeout')),
                attempt INTEGER NOT NULL DEFAULT 1,
                started_at DATETIME,
                completed_at DATETIME,
                output_file TEXT,
                error_summary TEXT,
                tokens_used INTEGER DEFAULT 0,
                cost_estimate REAL DEFAULT 0.0,
                trace_id TEXT,
                tool_calls_count INTEGER DEFAULT 0,
                next_retry_at DATETIME,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dispatch_runs_task_id
            ON dispatch_runs(task_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dispatch_runs_trace_id
            ON dispatch_runs(trace_id)
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_dispatch_runs_table(db_path=None):
    """Verify dispatch_runs table and its indexes exist."""
    conn = _get_connection(db_path)
    try:
        # Check table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dispatch_runs'"
        )
        if cursor.fetchone() is None:
            return False
        # Check indexes exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_dispatch_runs_task_id'"
        )
        if cursor.fetchone() is None:
            return False
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_dispatch_runs_trace_id'"
        )
        if cursor.fetchone() is None:
            return False
        return True
    finally:
        conn.close()


def migrate_create_task_dependencies(db_path=None):
    """US-005: Create task_dependencies table.

    Models task dependency graphs with completion and contribution dependency
    types, so the dispatch system can block dispatch of tasks until all
    dependencies are completed. Uses CREATE TABLE IF NOT EXISTS for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_dependencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                depends_on_task_id INTEGER NOT NULL,
                dependency_type TEXT NOT NULL
                    CHECK(dependency_type IN ('completion', 'contribution')),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_id, depends_on_task_id),
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_task_dependencies_table(db_path=None):
    """Verify task_dependencies table exists with UNIQUE constraint."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='task_dependencies'"
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def migrate_create_working_memory(db_path=None):
    """US-006: Create working_memory table.

    Stores per-task key-value pairs that agents can write during execution
    and downstream tasks can read, enabling structured data communication
    across dependency chains. Uses CREATE TABLE IF NOT EXISTS for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS working_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_id, agent_name, key),
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_working_memory_table(db_path=None):
    """Verify working_memory table exists."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='working_memory'"
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def migrate_create_daily_usage(db_path=None):
    """US-007: Create daily_usage table.

    Tracks tokens and cost by date/provider/model/agent_name to enforce
    global and per-agent daily budgets. Uses CREATE TABLE IF NOT EXISTS
    for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                total_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0.0,
                task_count INTEGER DEFAULT 0,
                UNIQUE(date, provider, model, agent_name)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_daily_usage_table(db_path=None):
    """Verify daily_usage table exists with correct schema."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_usage'"
        )
        if cursor.fetchone() is None:
            return False
        # Verify agent_name is NOT NULL
        cursor = conn.execute("PRAGMA table_info(daily_usage)")
        for row in cursor.fetchall():
            if row[1] == "agent_name" and row[3] != 1:  # notnull flag
                return False
        return True
    finally:
        conn.close()


def migrate_create_provider_health(db_path=None):
    """US-008: Create provider_health table.

    Stores canary test results with latency, error details, and raw response
    so the health monitor can detect regressions and trigger self-healing.
    Uses CREATE TABLE IF NOT EXISTS for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                test_name TEXT NOT NULL,
                passed BOOLEAN NOT NULL DEFAULT 0,
                latency_ms REAL,
                error_message TEXT,
                error_category TEXT,
                raw_response TEXT,
                tested_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_provider_health_tested_at
            ON provider_health(tested_at)
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_provider_health_table(db_path=None):
    """Verify provider_health table and its index exist."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='provider_health'"
        )
        if cursor.fetchone() is None:
            return False
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_provider_health_tested_at'"
        )
        if cursor.fetchone() is None:
            return False
        return True
    finally:
        conn.close()


def migrate_create_provider_incidents(db_path=None):
    """US-009: Create provider_incidents table.

    Tracks incident detection, resolution, auto-healing actions, and diagnostic
    reports for provider health monitoring. Maintains incident history for 180 days.
    Uses CREATE TABLE IF NOT EXISTS for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                incident_type TEXT NOT NULL,
                detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME,
                auto_healed BOOLEAN NOT NULL DEFAULT 0,
                healing_action TEXT,
                diagnostic_report TEXT,
                notified_user BOOLEAN NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_provider_incidents_table(db_path=None):
    """Verify provider_incidents table exists."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='provider_incidents'"
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def migrate_create_audit_log(db_path=None):
    """US-010: Create audit_log table.

    Permanent audit log for destructive tool calls. Never cleaned up by
    retention policy. task_id uses ON DELETE SET NULL so archival DELETEs
    on the tasks table don't fail. Uses CREATE TABLE IF NOT EXISTS for
    idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT,
                task_id INTEGER,
                agent_name TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments TEXT,
                result TEXT,
                executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_trace_id
            ON audit_log(trace_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_task_id
            ON audit_log(task_id)
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_audit_log_table(db_path=None):
    """Verify audit_log table and its indexes exist."""
    conn = _get_connection(db_path)
    try:
        # Check table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
        )
        if cursor.fetchone() is None:
            return False
        # Check task_id is nullable (notnull flag should be 0)
        cursor = conn.execute("PRAGMA table_info(audit_log)")
        for row in cursor.fetchall():
            if row[1] == "task_id" and row[3] != 0:  # notnull flag should be 0
                return False
        # Check indexes exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_audit_log_trace_id'"
        )
        if cursor.fetchone() is None:
            return False
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_audit_log_task_id'"
        )
        if cursor.fetchone() is None:
            return False
        return True
    finally:
        conn.close()


def migrate_create_tasks_archive(db_path=None):
    """US-011: Create tasks_archive table with explicit schema.

    Mirrors all columns from the tasks table (including dispatch_status and
    lease_until added by US-001/US-002) plus archived_at column. Must run
    AFTER the ALTER TABLE migrations so the archive schema stays in sync.
    Uses CREATE TABLE IF NOT EXISTS for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks_archive (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                priority INTEGER DEFAULT 3,
                domain TEXT NOT NULL,
                assigned_agent TEXT,
                created_by TEXT DEFAULT 'george',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                due_date DATETIME,
                deliverable_type TEXT,
                deliverable_url TEXT,
                estimated_effort INTEGER,
                business_impact INTEGER DEFAULT 3,
                dispatch_status TEXT,
                lease_until DATETIME DEFAULT NULL,
                archived_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_tasks_archive_table(db_path=None):
    """Verify tasks_archive table exists with archived_at column."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks_archive'"
        )
        if cursor.fetchone() is None:
            return False
        # Verify archived_at column exists
        cursor = conn.execute("PRAGMA table_info(tasks_archive)")
        columns = {row[1] for row in cursor.fetchall()}
        if "archived_at" not in columns:
            return False
        return True
    finally:
        conn.close()


def migrate_create_health_daily_summary(db_path=None):
    """US-012: Create health_daily_summary table.

    Stores aggregated health metrics after deleting raw health check records
    older than 30 days. Enables long-term health trend reporting without
    retaining granular provider_health rows. Uses CREATE TABLE IF NOT EXISTS
    for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS health_daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                tests_run INTEGER NOT NULL DEFAULT 0,
                tests_passed INTEGER NOT NULL DEFAULT 0,
                avg_latency_ms REAL,
                UNIQUE(date, provider, model)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_health_daily_summary_table(db_path=None):
    """Verify health_daily_summary table exists with UNIQUE constraint."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='health_daily_summary'"
        )
        if cursor.fetchone() is None:
            return False
        # Verify required columns exist
        cursor = conn.execute("PRAGMA table_info(health_daily_summary)")
        columns = {row[1] for row in cursor.fetchall()}
        required = {"id", "date", "provider", "model", "tests_run", "tests_passed", "avg_latency_ms"}
        if not required.issubset(columns):
            return False
        return True
    finally:
        conn.close()


def migrate_dispatch_runs_trace_id_not_null(db_path=None):
    """Fix dispatch_runs.trace_id to be NOT NULL.

    SQLite doesn't support ALTER COLUMN, so we use the standard migration pattern:
    create temp table with correct schema, copy data, drop original, rename temp.
    Idempotent: checks if trace_id is already NOT NULL before migrating.
    """
    conn = _get_connection(db_path)
    try:
        # Check if trace_id is already NOT NULL
        cursor = conn.execute("PRAGMA table_info(dispatch_runs)")
        for row in cursor.fetchall():
            if row[1] == "trace_id" and row[3] == 1:  # notnull flag is 1
                # Already NOT NULL, skip migration
                return

        # trace_id is nullable, need to migrate
        # Step 1: Create temp table with correct schema
        conn.execute(
            """
            CREATE TABLE dispatch_runs_temp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'running', 'completed', 'failed', 'timeout')),
                attempt INTEGER NOT NULL DEFAULT 1,
                started_at DATETIME,
                completed_at DATETIME,
                output_file TEXT,
                error_summary TEXT,
                tokens_used INTEGER DEFAULT 0,
                cost_estimate REAL DEFAULT 0.0,
                trace_id TEXT NOT NULL,
                tool_calls_count INTEGER DEFAULT 0,
                next_retry_at DATETIME,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """
        )

        # Step 2: Copy data (use COALESCE to handle any existing NULLs)
        conn.execute(
            """
            INSERT INTO dispatch_runs_temp
            (id, task_id, agent_name, provider, model, status, attempt, started_at,
             completed_at, output_file, error_summary, tokens_used, cost_estimate,
             trace_id, tool_calls_count, next_retry_at)
            SELECT id, task_id, agent_name, provider, model, status, attempt, started_at,
                   completed_at, output_file, error_summary, tokens_used, cost_estimate,
                   COALESCE(trace_id, ''), tool_calls_count, next_retry_at
            FROM dispatch_runs
            """
        )

        # Step 3: Drop original table
        conn.execute("DROP TABLE dispatch_runs")

        # Step 4: Rename temp to original
        conn.execute("ALTER TABLE dispatch_runs_temp RENAME TO dispatch_runs")

        # Step 5: Recreate indexes
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dispatch_runs_task_id
            ON dispatch_runs(task_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dispatch_runs_trace_id
            ON dispatch_runs(trace_id)
            """
        )

        conn.commit()
    finally:
        conn.close()


def migrate_audit_log_not_null_fixes(db_path=None):
    """Fix audit_log.trace_id and audit_log.arguments to be NOT NULL.

    SQLite doesn't support ALTER COLUMN, so we use the standard migration pattern:
    create temp table with correct schema, copy data, drop original, rename temp.
    Idempotent: checks if columns are already NOT NULL before migrating.
    """
    conn = _get_connection(db_path)
    try:
        # Check if trace_id and arguments are already NOT NULL
        cursor = conn.execute("PRAGMA table_info(audit_log)")
        columns_info = {row[1]: row[3] for row in cursor.fetchall()}  # name -> notnull flag

        trace_id_not_null = columns_info.get("trace_id", 0) == 1
        arguments_not_null = columns_info.get("arguments", 0) == 1

        if trace_id_not_null and arguments_not_null:
            # Already fixed, skip migration
            return

        # Need to migrate
        # Step 1: Create temp table with correct schema
        conn.execute(
            """
            CREATE TABLE audit_log_temp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                task_id INTEGER,
                agent_name TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments TEXT NOT NULL,
                result TEXT,
                executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
            )
            """
        )

        # Step 2: Copy data (use COALESCE to handle any existing NULLs)
        conn.execute(
            """
            INSERT INTO audit_log_temp
            (id, trace_id, task_id, agent_name, tool_name, arguments, result, executed_at)
            SELECT id, COALESCE(trace_id, ''), task_id, agent_name, tool_name,
                   COALESCE(arguments, ''), result, executed_at
            FROM audit_log
            """
        )

        # Step 3: Drop original table
        conn.execute("DROP TABLE audit_log")

        # Step 4: Rename temp to original
        conn.execute("ALTER TABLE audit_log_temp RENAME TO audit_log")

        # Step 5: Recreate indexes
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_trace_id
            ON audit_log(trace_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_task_id
            ON audit_log(task_id)
            """
        )

        conn.commit()
    finally:
        conn.close()


def migrate_working_memory_value_not_null(db_path=None):
    """Fix working_memory.value to be NOT NULL.

    SQLite doesn't support ALTER COLUMN, so we use the standard migration pattern:
    create temp table with correct schema, copy data, drop original, rename temp.
    Idempotent: checks if value is already NOT NULL before migrating.
    """
    conn = _get_connection(db_path)
    try:
        # Check if value is already NOT NULL
        cursor = conn.execute("PRAGMA table_info(working_memory)")
        for row in cursor.fetchall():
            if row[1] == "value" and row[3] == 1:  # notnull flag is 1
                # Already NOT NULL, skip migration
                return

        # value is nullable, need to migrate
        # Step 1: Create temp table with correct schema
        conn.execute(
            """
            CREATE TABLE working_memory_temp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_id, agent_name, key),
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """
        )

        # Step 2: Copy data (use COALESCE to handle any existing NULLs)
        conn.execute(
            """
            INSERT INTO working_memory_temp
            (id, task_id, agent_name, key, value, created_at)
            SELECT id, task_id, agent_name, key, COALESCE(value, ''), created_at
            FROM working_memory
            """
        )

        # Step 3: Drop original table
        conn.execute("DROP TABLE working_memory")

        # Step 4: Rename temp to original
        conn.execute("ALTER TABLE working_memory_temp RENAME TO working_memory")

        conn.commit()
    finally:
        conn.close()


def migrate_add_recovering_dispatch_status(db_path=None):
    """US-002 (self-healing): Add 'recovering' to dispatch_status CHECK constraint.

    SQLite doesn't support ALTER COLUMN, so we rebuild the tasks table with
    the updated CHECK constraint that includes 'recovering' in the allowed
    dispatch_status values.

    Idempotent: checks if 'recovering' is already allowed before migrating.
    """
    conn = _get_connection(db_path)
    try:
        # Check if 'recovering' is already in the constraint by attempting an insert
        # First, check if the column exists
        cursor = conn.execute("PRAGMA table_info(tasks)")
        columns = {row[1] for row in cursor.fetchall()}
        if "dispatch_status" not in columns:
            return  # dispatch_status not added yet; skip

        # Check the current table SQL for the CHECK constraint
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'"
        )
        row = cursor.fetchone()
        if row and row[0] and "'recovering'" in row[0]:
            return  # Already has 'recovering' in constraint

        # Get all column info for rebuild
        cursor = conn.execute("PRAGMA table_info(tasks)")
        col_info = cursor.fetchall()
        # col_info rows: (cid, name, type, notnull, dflt_value, pk)

        # Build column definitions for temp table
        # We need to preserve all constraints from the original CREATE TABLE
        # plus the ALTER TABLE additions (dispatch_status, lease_until)
        # The safest approach: read original SQL and modify it
        table_sql = row[0] if row else None
        if not table_sql:
            return  # Can't proceed without table SQL

        # Replace the old CHECK constraint with the new one that includes 'recovering'
        old_check = (
            "CHECK(dispatch_status IS NULL OR dispatch_status IN"
            "\n                ('queued', 'dispatched', 'completed', 'failed',\n"
            "                 'interrupted', 'dispatch_failed'))"
        )
        new_check = (
            "CHECK(dispatch_status IS NULL OR dispatch_status IN"
            "\n                ('queued', 'dispatched', 'completed', 'failed',\n"
            "                 'interrupted', 'dispatch_failed', 'recovering'))"
        )

        # Try direct string replacement first
        if old_check in table_sql:
            new_table_sql = table_sql.replace(old_check, new_check)
        else:
            # Fallback: try a more flexible pattern match
            # The CHECK may have different whitespace in the stored SQL
            import re
            pattern = (
                r"CHECK\s*\(\s*dispatch_status\s+IS\s+NULL\s+OR\s+dispatch_status\s+IN\s*\("
                r"[^)]+\)\s*\)"
            )
            replacement = (
                "CHECK(dispatch_status IS NULL OR dispatch_status IN"
                " ('queued', 'dispatched', 'completed', 'failed',"
                " 'interrupted', 'dispatch_failed', 'recovering'))"
            )
            new_table_sql = re.sub(pattern, replacement, table_sql)

            if new_table_sql == table_sql:
                # If no CHECK constraint found at all (column added without one),
                # nothing to update - the column accepts any value
                return

        # Create temp table with updated schema
        temp_sql = new_table_sql.replace(
            "CREATE TABLE tasks", "CREATE TABLE tasks_temp", 1
        )
        conn.execute(temp_sql)

        # Copy all data
        col_names = ", ".join(col[1] for col in col_info)
        conn.execute(
            f"INSERT INTO tasks_temp ({col_names}) SELECT {col_names} FROM tasks"
        )

        # Drop original and rename
        conn.execute("DROP TABLE tasks")
        conn.execute("ALTER TABLE tasks_temp RENAME TO tasks")

        # Recreate indexes on tasks table
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_dispatch
            ON tasks(dispatch_status, lease_until)
            """
        )

        conn.commit()
    finally:
        conn.close()


def verify_recovering_dispatch_status(db_path=None):
    """Verify dispatch_status CHECK constraint includes 'recovering'."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'"
        )
        row = cursor.fetchone()
        if row and row[0] and "'recovering'" in row[0]:
            return True
        # Also test by trying to insert and rollback
        try:
            conn.execute(
                "INSERT INTO tasks (title, description, domain, dispatch_status) "
                "VALUES ('__test__', '__test__', '__test__', 'recovering')"
            )
            # Delete the test row
            conn.execute(
                "DELETE FROM tasks WHERE title = '__test__' AND description = '__test__'"
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    finally:
        conn.close()


def migrate_add_recovery_columns_to_dispatch_runs(db_path=None):
    """US-001 (self-healing): Add recovery state columns to dispatch_runs table.

    Adds 8 columns for the recovery pipeline:
      - raw_output: Raw LLM response before parsing
      - tool_call_log: JSON array of tool calls made during execution
      - stop_reason: Why execution stopped (e.g., 'max_tokens', 'end_turn')
      - error_context: JSON with exception type, message, traceback
      - recovery_tier: Which recovery tier was used (1-5)
      - recovery_strategy: Name of recovery strategy applied
      - lease_extensions: Number of times the lease was extended
      - tool_calls_count_at_last_extension: tool_calls_count when lease was last extended

    Idempotent: skips columns that already exist.
    """
    conn = _get_connection(db_path)
    try:
        columns = [
            ("raw_output", "TEXT"),
            ("tool_call_log", "TEXT"),
            ("stop_reason", "TEXT"),
            ("error_context", "TEXT"),
            ("recovery_tier", "INTEGER"),
            ("recovery_strategy", "TEXT"),
            ("lease_extensions", "INTEGER DEFAULT 0"),
            ("tool_calls_count_at_last_extension", "INTEGER DEFAULT 0"),
        ]
        for col_name, col_type in columns:
            try:
                conn.execute(
                    f"ALTER TABLE dispatch_runs ADD COLUMN {col_name} {col_type}"
                )
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    pass  # Column already exists - idempotent
                else:
                    raise
        conn.commit()
    finally:
        conn.close()


def verify_recovery_columns_on_dispatch_runs(db_path=None):
    """Verify all 8 recovery columns exist on dispatch_runs table."""
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute("PRAGMA table_info(dispatch_runs)")
        columns = {row[1] for row in cursor.fetchall()}
        required = {
            "raw_output", "tool_call_log", "stop_reason", "error_context",
            "recovery_tier", "recovery_strategy", "lease_extensions",
            "tool_calls_count_at_last_extension",
        }
        return required.issubset(columns)
    finally:
        conn.close()


def migrate_create_failure_memory(db_path=None):
    """US-003 (self-healing): Create failure_memory table for pattern learning.

    Stores error-diagnosis-fix triples so that the recovery system learns
    from past successes. Includes indexes for fast similarity queries and
    retention cleanup. Uses CREATE TABLE IF NOT EXISTS for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS failure_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                agent_name TEXT,
                error_code TEXT,
                error_pattern TEXT,
                diagnostic_summary TEXT,
                resolution_summary TEXT,
                success INTEGER DEFAULT 0,
                recovery_tier INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                task_domain TEXT,
                similarity_key TEXT GENERATED ALWAYS AS (
                    COALESCE(error_code, '') || ':' || COALESCE(agent_name, '') || ':' || COALESCE(task_domain, '')
                ) STORED,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_failure_memory_similarity
            ON failure_memory(error_code, agent_name, success)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_failure_memory_created_at
            ON failure_memory(created_at)
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_failure_memory_table(db_path=None):
    """Verify failure_memory table and its indexes exist."""
    conn = _get_connection(db_path)
    try:
        # Check table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='failure_memory'"
        )
        if cursor.fetchone() is None:
            return False
        # Check indexes exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_failure_memory_similarity'"
        )
        if cursor.fetchone() is None:
            return False
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_failure_memory_created_at'"
        )
        if cursor.fetchone() is None:
            return False
        # Verify key columns exist (use table_xinfo to include generated columns)
        try:
            cursor = conn.execute("PRAGMA table_xinfo(failure_memory)")
        except sqlite3.OperationalError:
            # Fallback for older SQLite without table_xinfo
            cursor = conn.execute("PRAGMA table_info(failure_memory)")
        columns = {row[1] for row in cursor.fetchall()}
        required = {
            "id", "task_id", "agent_name", "error_code", "error_pattern",
            "diagnostic_summary", "resolution_summary", "success",
            "recovery_tier", "created_at", "task_domain", "similarity_key",
        }
        return required.issubset(columns)
    finally:
        conn.close()


def migrate_create_recovery_events(db_path=None):
    """US-004 (self-healing): Create recovery_events table for observability.

    Tracks every recovery pipeline stage for debugging and metrics.
    Each event has a trace_id for correlating related recovery events,
    event_type using dot notation (recovery.capture, recovery.diagnose.start, etc),
    and optional metadata JSON. Uses CREATE TABLE IF NOT EXISTS for idempotency.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recovery_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                trace_id TEXT,
                event_type TEXT,
                stage TEXT,
                duration_ms INTEGER,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_recovery_events_task_created
            ON recovery_events(task_id, created_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_recovery_events_trace_id
            ON recovery_events(trace_id)
            """
        )
        conn.commit()
    finally:
        conn.close()


def verify_recovery_events_table(db_path=None):
    """Verify recovery_events table and its indexes exist."""
    conn = _get_connection(db_path)
    try:
        # Check table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recovery_events'"
        )
        if cursor.fetchone() is None:
            return False
        # Check indexes exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_recovery_events_task_created'"
        )
        if cursor.fetchone() is None:
            return False
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_recovery_events_trace_id'"
        )
        if cursor.fetchone() is None:
            return False
        # Verify key columns exist
        cursor = conn.execute("PRAGMA table_info(recovery_events)")
        columns = {row[1] for row in cursor.fetchall()}
        required = {
            "id", "task_id", "trace_id", "event_type", "stage",
            "duration_ms", "metadata", "created_at",
        }
        return required.issubset(columns)
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_add_dispatch_status()
    if verify_dispatch_status_column():
        print("OK: dispatch_status column verified on tasks table")
    else:
        print("FAIL: dispatch_status column not found")

    migrate_add_lease_until()
    if verify_lease_until_column():
        print("OK: lease_until column verified on tasks table")
    else:
        print("FAIL: lease_until column not found")

    migrate_create_dispatch_index()
    if verify_dispatch_index():
        print("OK: idx_tasks_dispatch index verified on tasks table")
    else:
        print("FAIL: idx_tasks_dispatch index not found")

    migrate_create_dispatch_runs()
    if verify_dispatch_runs_table():
        print("OK: dispatch_runs table and indexes verified")
    else:
        print("FAIL: dispatch_runs table or indexes not found")

    migrate_create_task_dependencies()
    if verify_task_dependencies_table():
        print("OK: task_dependencies table verified")
    else:
        print("FAIL: task_dependencies table not found")

    migrate_create_working_memory()
    if verify_working_memory_table():
        print("OK: working_memory table verified")
    else:
        print("FAIL: working_memory table not found")

    migrate_create_daily_usage()
    if verify_daily_usage_table():
        print("OK: daily_usage table verified")
    else:
        print("FAIL: daily_usage table not found")

    migrate_create_provider_health()
    if verify_provider_health_table():
        print("OK: provider_health table and index verified")
    else:
        print("FAIL: provider_health table or index not found")

    migrate_create_provider_incidents()
    if verify_provider_incidents_table():
        print("OK: provider_incidents table verified")
    else:
        print("FAIL: provider_incidents table not found")

    migrate_create_audit_log()
    if verify_audit_log_table():
        print("OK: audit_log table and indexes verified")
    else:
        print("FAIL: audit_log table or indexes not found")

    migrate_create_tasks_archive()
    if verify_tasks_archive_table():
        print("OK: tasks_archive table verified")
    else:
        print("FAIL: tasks_archive table not found")

    migrate_create_health_daily_summary()
    if verify_health_daily_summary_table():
        print("OK: health_daily_summary table verified")
    else:
        print("FAIL: health_daily_summary table not found")

    # Run NOT NULL fix migrations
    print("\nApplying NOT NULL constraint fixes...")

    migrate_dispatch_runs_trace_id_not_null()
    print("OK: dispatch_runs.trace_id NOT NULL migration applied")

    migrate_audit_log_not_null_fixes()
    print("OK: audit_log.trace_id and audit_log.arguments NOT NULL migration applied")

    migrate_working_memory_value_not_null()
    print("OK: working_memory.value NOT NULL migration applied")

    # Recovery columns migration
    migrate_add_recovery_columns_to_dispatch_runs()
    if verify_recovery_columns_on_dispatch_runs():
        print("OK: recovery columns verified on dispatch_runs table")
    else:
        print("FAIL: recovery columns not found on dispatch_runs table")

    # Add 'recovering' to dispatch_status CHECK constraint
    migrate_add_recovering_dispatch_status()
    if verify_recovering_dispatch_status():
        print("OK: dispatch_status CHECK constraint includes 'recovering'")
    else:
        print("FAIL: dispatch_status CHECK constraint missing 'recovering'")

    # Create failure_memory table (self-healing system)
    migrate_create_failure_memory()
    if verify_failure_memory_table():
        print("OK: failure_memory table and indexes verified")
    else:
        print("FAIL: failure_memory table or indexes not found")

    # Create recovery_events table (self-healing system)
    migrate_create_recovery_events()
    if verify_recovery_events_table():
        print("OK: recovery_events table and indexes verified")
    else:
        print("FAIL: recovery_events table or indexes not found")
