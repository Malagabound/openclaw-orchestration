"""OpenClawd Agent Dispatch System - CLI Entry Point.

US-081: Provides 'openclawd' CLI with subcommands: status, tasks, dispatch,
run, daemon, stop, kick. All commands support --json flag for
machine-readable output.

US-090: Adds rich library integration for formatted tables and progress bars
with plain-text fallback.

Entry point: main() function, registered via setup.py console_scripts.
"""

import argparse
import json
import os
import shutil
import signal
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional

from .config import DEFAULT_DB_PATH, CONFIG_FILENAME, load_config, resolve_config_path, ensure_config

# Try to import rich library for formatted output
try:
    from rich.table import Table
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# PID file path (mirrors agent_supervisor._PID_FILE_PATH)
_PID_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_PID_FILE_PATH = os.path.join(_PID_FILE_DIR, "supervisor.pid")


def _get_db_path(config: Dict[str, Any]) -> str:
    """Resolve database path from env var or default."""
    return os.environ.get("OPENCLAWD_DB_PATH", DEFAULT_DB_PATH)


def _get_connection(db_path: str) -> sqlite3.Connection:
    """Create a read-only connection with standard PRAGMAs."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _read_pid_file() -> Optional[int]:
    """Read PID from supervisor.pid. Returns None if file doesn't exist or is invalid."""
    if not os.path.exists(_PID_FILE_PATH):
        return None
    try:
        with open(_PID_FILE_PATH, "r") as f:
            pid_str = f.read().strip()
        if not pid_str:
            return None
        return int(pid_str)
    except (ValueError, OSError):
        return None


def _is_pid_running(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _get_status_color(status: str) -> str:
    """Get rich color string for a status value."""
    status_lower = str(status).lower()
    if status_lower in ("completed", "success", "pass", "ok", "running"):
        return "green"
    elif status_lower in ("failed", "fail", "error", "stopped"):
        return "red"
    elif status_lower in ("in_progress", "dispatched", "queued", "warning"):
        return "yellow"
    else:
        return "white"


def _output(data: Any, as_json: bool) -> None:
    """Print output as JSON or human-readable text."""
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    elif isinstance(data, dict):
        for key, value in data.items():
            print(f"{key}: {value}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                parts = [f"{k}={v}" for k, v in item.items()]
                print("  ".join(parts))
            else:
                print(item)
    else:
        print(data)


# ── Subcommand Handlers ─────────────────────────────────────────


def cmd_status(args: argparse.Namespace) -> None:
    """Print supervisor status (running/stopped, PID, active tasks)."""
    config = load_config()
    result = _get_status_dict(config)

    if args.json:
        _output(result, True)
    elif HAS_RICH:
        console = Console()
        table = Table(title="Supervisor Status", show_header=True, header_style="bold magenta")
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        # Status row with color
        status_val = result.get("status", "unknown")
        status_color = _get_status_color(status_val)
        table.add_row("Status", f"[{status_color}]{status_val}[/{status_color}]")

        # PID row
        pid_val = result.get("pid")
        table.add_row("PID", str(pid_val) if pid_val else "N/A")

        # Active tasks
        table.add_row("Active Tasks", str(result.get("active_tasks", 0)))

        # Queued tasks
        table.add_row("Queued Tasks", str(result.get("queued_tasks", 0)))

        # Budget usage
        budget = result.get("budget_usage", {})
        if budget:
            table.add_row("Today Cost (USD)", f"${budget.get('today_cost_usd', 0.0):.4f}")
            table.add_row("Today Tokens", str(budget.get("today_tokens", 0)))

        # Health summary
        health = result.get("health_summary", {})
        if health:
            passed = health.get("passed", 0)
            total = health.get("total_checks", 0)
            table.add_row("Health Checks", f"{passed}/{total} passed")

        console.print(table)
    else:
        _output(result, False)


def cmd_tasks(args: argparse.Namespace) -> None:
    """List tasks with optional filters (status, agent, priority)."""
    config = load_config()
    db_path = _get_db_path(config)

    conditions = []
    params: List[Any] = []

    if args.status:
        conditions.append("dispatch_status = ?")
        params.append(args.status)

    if args.agent:
        conditions.append("assigned_agent = ?")
        params.append(args.agent)

    if args.priority:
        conditions.append("priority >= ?")
        params.append(int(args.priority))

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"SELECT * FROM tasks WHERE {where_clause} ORDER BY priority DESC, created_at ASC"

    try:
        conn = _get_connection(db_path)
        rows = conn.execute(query, params).fetchall()
        tasks = [dict(row) for row in rows]
        conn.close()
    except (sqlite3.Error, OSError) as e:
        _output({"error": str(e)}, args.json)
        sys.exit(1)

    if args.json:
        _output(tasks, True)
    elif HAS_RICH:
        console = Console()
        table = Table(title=f"Tasks ({len(tasks)} found)", show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan", no_wrap=True, width=6)
        table.add_column("Title", style="white", width=30)
        table.add_column("Status", style="white", width=15)
        table.add_column("Agent", style="white", width=15)
        table.add_column("Priority", style="white", width=8)

        for task in tasks:
            task_id = str(task.get("id", ""))
            title = str(task.get("title", ""))[:28] + ("..." if len(str(task.get("title", ""))) > 28 else "")
            status = str(task.get("dispatch_status") or task.get("status", ""))
            agent = str(task.get("assigned_agent", ""))[:13] + ("..." if len(str(task.get("assigned_agent", ""))) > 13 else "")
            priority = str(task.get("priority", ""))

            # Color-code status column
            status_color = _get_status_color(status)
            status_display = f"[{status_color}]{status}[/{status_color}]"

            table.add_row(task_id, title, status_display, agent, priority)

        console.print(table)
    else:
        _output(tasks, False)


def cmd_dispatch(args: argparse.Namespace) -> None:
    """Manually dispatch a specific task by ID."""
    config = load_config()
    db_path = _get_db_path(config)

    task_id = args.task_id

    try:
        from .dispatch_db import claim_task
        claimed = claim_task(task_id, lease_seconds=300)
        if claimed:
            result = {"dispatched": True, "task_id": task_id}
        else:
            result = {"dispatched": False, "task_id": task_id, "reason": "Could not claim task (already claimed or ineligible)"}
    except Exception as e:
        result = {"dispatched": False, "task_id": task_id, "error": str(e)}

    _output(result, args.json)
    if not result.get("dispatched", False):
        sys.exit(1)


def cmd_run(args: argparse.Namespace) -> None:
    """Run a single poll cycle and exit."""
    config = load_config()

    from .agent_supervisor import AgentSupervisor
    supervisor = AgentSupervisor(config=config)

    try:
        from .dispatch_db import run_migrations
        run_migrations(supervisor.db_path)
        supervisor._poll_once()
        result = {"ran": True, "message": "Single poll cycle completed"}
    except Exception as e:
        result = {"ran": False, "error": str(e)}

    _output(result, args.json)
    if not result.get("ran", False):
        sys.exit(1)


def cmd_daemon(args: argparse.Namespace) -> None:
    """Start the persistent supervisor loop."""
    config = load_config()

    from .agent_supervisor import AgentSupervisor
    supervisor = AgentSupervisor(config=config)

    print("Starting OpenClawd supervisor daemon...")
    try:
        supervisor.run()
    except SystemExit as e:
        if e.code != 0:
            print(f"Supervisor exited with code {e.code}", file=sys.stderr)
            sys.exit(e.code)
    except KeyboardInterrupt:
        print("\nSupervisor stopped.")


def cmd_stop(args: argparse.Namespace) -> None:
    """Send SIGTERM to the supervisor PID."""
    pid = _read_pid_file()

    if pid is None:
        result = {"stopped": False, "reason": "No PID file found"}
        _output(result, args.json)
        sys.exit(1)

    if not _is_pid_running(pid):
        result = {"stopped": False, "reason": f"Process {pid} is not running (stale PID file)"}
        # Clean up stale PID file
        try:
            os.remove(_PID_FILE_PATH)
        except OSError:
            pass
        _output(result, args.json)
        sys.exit(1)

    try:
        os.kill(pid, signal.SIGTERM)
        result = {"stopped": True, "pid": pid, "signal": "SIGTERM"}
    except OSError as e:
        result = {"stopped": False, "pid": pid, "error": str(e)}

    _output(result, args.json)
    if not result.get("stopped", False):
        sys.exit(1)


def cmd_kick(args: argparse.Namespace) -> None:
    """Send SIGUSR1 to trigger an immediate poll cycle."""
    pid = _read_pid_file()

    if pid is None:
        result = {"kicked": False, "reason": "No PID file found"}
        _output(result, args.json)
        sys.exit(1)

    if not _is_pid_running(pid):
        result = {"kicked": False, "reason": f"Process {pid} is not running (stale PID file)"}
        _output(result, args.json)
        sys.exit(1)

    try:
        os.kill(pid, signal.SIGUSR1)
        result = {"kicked": True, "pid": pid, "signal": "SIGUSR1"}
    except OSError as e:
        result = {"kicked": False, "pid": pid, "error": str(e)}

    _output(result, args.json)
    if not result.get("kicked", False):
        sys.exit(1)


def cmd_health(args: argparse.Namespace) -> None:
    """Run provider health checks and print results."""
    config = load_config()
    db_path = _get_db_path(config)

    from .health.canary_tests import ALL_CANARY_TESTS
    from .provider_registry import get_provider, ProviderRegistryError

    results: List[Dict[str, Any]] = []

    # Collect providers to test: primary + fallback
    providers_to_test: List[Dict[str, str]] = []
    provider_section = config.get("provider", {})
    if isinstance(provider_section, dict) and provider_section.get("name"):
        providers_to_test.append({
            "name": provider_section.get("name", "unknown"),
            "model": provider_section.get("model", "unknown"),
            "type": "primary",
        })

    fallback_section = config.get("fallback")
    if fallback_section and isinstance(fallback_section, dict):
        fb_name = fallback_section.get("name")
        fb_model = fallback_section.get("model")
        if fb_name and fb_model:
            providers_to_test.append({
                "name": fb_name,
                "model": fb_model,
                "type": "fallback",
            })

    # Progress bar for long operation
    if HAS_RICH and not args.json:
        console = Console()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task_progress = progress.add_task("Running health checks...", total=None)

            for prov_info in providers_to_test:
                if prov_info["type"] == "fallback":
                    prov_config = {
                        "provider": {
                            "name": prov_info["name"],
                            "api_key_env": config.get("fallback", {}).get("api_key_env", ""),
                            "model": prov_info["model"],
                            "base_url": config.get("fallback", {}).get("base_url"),
                        },
                    }
                else:
                    prov_config = config

                try:
                    provider = get_provider(prov_config)
                except ProviderRegistryError as exc:
                    for test_name, _ in ALL_CANARY_TESTS:
                        results.append({
                            "provider": prov_info["name"],
                            "model": prov_info["model"],
                            "test": test_name,
                            "passed": False,
                            "latency_ms": 0.0,
                            "error": f"Cannot instantiate provider: {exc}",
                        })
                    continue

                for test_name, test_fn in ALL_CANARY_TESTS:
                    try:
                        result = test_fn(provider)
                    except Exception as exc:
                        result = {
                            "passed": False,
                            "latency_ms": 0.0,
                            "error_message": f"Test crashed: {exc}",
                        }
                    results.append({
                        "provider": prov_info["name"],
                        "model": prov_info["model"],
                        "test": test_name,
                        "passed": result["passed"],
                        "latency_ms": round(result["latency_ms"], 1),
                        "error": result.get("error_message"),
                    })
    else:
        # No progress bar - run silently or with JSON output
        for prov_info in providers_to_test:
            if prov_info["type"] == "fallback":
                prov_config = {
                    "provider": {
                        "name": prov_info["name"],
                        "api_key_env": config.get("fallback", {}).get("api_key_env", ""),
                        "model": prov_info["model"],
                        "base_url": config.get("fallback", {}).get("base_url"),
                    },
                }
            else:
                prov_config = config

            try:
                provider = get_provider(prov_config)
            except ProviderRegistryError as exc:
                for test_name, _ in ALL_CANARY_TESTS:
                    results.append({
                        "provider": prov_info["name"],
                        "model": prov_info["model"],
                        "test": test_name,
                        "passed": False,
                        "latency_ms": 0.0,
                        "error": f"Cannot instantiate provider: {exc}",
                    })
                continue

            for test_name, test_fn in ALL_CANARY_TESTS:
                try:
                    result = test_fn(provider)
                except Exception as exc:
                    result = {
                        "passed": False,
                        "latency_ms": 0.0,
                        "error_message": f"Test crashed: {exc}",
                    }
                results.append({
                    "provider": prov_info["name"],
                    "model": prov_info["model"],
                    "test": test_name,
                    "passed": result["passed"],
                    "latency_ms": round(result["latency_ms"], 1),
                    "error": result.get("error_message"),
                })

    # Store results in DB if possible
    try:
        conn = _get_connection(db_path)
        from .health.health_monitor import run_health_checks
        run_health_checks(config, conn)
        conn.close()
    except Exception:
        pass

    if args.json:
        _output(results, True)
    elif HAS_RICH:
        console = Console()
        table = Table(title="Provider Health Checks", show_header=True, header_style="bold magenta")
        table.add_column("Provider", style="cyan", width=15)
        table.add_column("Model", style="white", width=25)
        table.add_column("Test", style="white", width=25)
        table.add_column("Status", style="white", width=8)
        table.add_column("Latency", style="white", width=10)
        table.add_column("Error", style="white", width=30)

        for r in results:
            provider = r["provider"]
            model = r["model"][:23] + ("..." if len(r["model"]) > 23 else "")
            test = r["test"][:23] + ("..." if len(r["test"]) > 23 else "")
            passed = r["passed"]
            status_color = "green" if passed else "red"
            status = f"[{status_color}]{'PASS' if passed else 'FAIL'}[/{status_color}]"
            latency = f"{r['latency_ms']}ms" if r["latency_ms"] else "-"
            error = r.get("error") or ""
            if len(error) > 28:
                error = error[:25] + "..."

            table.add_row(provider, model, test, status, latency, error)

        console.print(table)

        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        summary_color = "green" if passed == total else ("yellow" if passed > 0 else "red")
        console.print(f"\n[{summary_color}]{passed}/{total} checks passed[/{summary_color}]")
    else:
        if not results:
            print("No providers configured.")
            return
        # Print as table
        print(f"{'Provider':<15} {'Model':<30} {'Test':<25} {'Status':<8} {'Latency':<12} {'Error'}")
        print("-" * 100)
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            latency = f"{r['latency_ms']}ms" if r["latency_ms"] else "-"
            error = r.get("error") or ""
            if len(error) > 30:
                error = error[:27] + "..."
            print(f"{r['provider']:<15} {r['model']:<30} {r['test']:<25} {status:<8} {latency:<12} {error}")

        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        print(f"\n{passed}/{total} checks passed")


def cmd_logs(args: argparse.Namespace) -> None:
    """Tail supervisor.jsonl with optional filters."""
    from .structured_logging import LOG_FILE_PATH

    log_path = LOG_FILE_PATH

    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    def _matches(entry: Dict[str, Any]) -> bool:
        if args.level and entry.get("level", "").upper() != args.level.upper():
            return False
        if args.agent and entry.get("agent_name") != args.agent:
            return False
        if args.task and str(entry.get("task_id", "")) != str(args.task):
            return False
        if args.trace and entry.get("trace_id") != args.trace:
            return False
        return True

    def _format_entry(entry: Dict[str, Any], as_json: bool) -> str:
        if as_json:
            return json.dumps(entry, default=str)
        ts = entry.get("timestamp", "")
        level = entry.get("level", "?")
        component = entry.get("component", "")
        message = entry.get("message", "")
        parts = [f"{ts} [{level}] {component}: {message}"]
        for field in ("trace_id", "agent_name", "task_id"):
            val = entry.get(field)
            if val is not None:
                parts[0] += f" {field}={val}"
        return parts[0]

    def _read_last_n(path: str, n: int) -> List[Dict[str, Any]]:
        """Read last n valid JSON lines from file."""
        entries: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError as e:
            print(f"Error reading log file: {e}", file=sys.stderr)
            sys.exit(1)
        return entries[-n:] if len(entries) > n else entries

    # Print last 50 (or filtered subset)
    entries = _read_last_n(log_path, 500)  # read more to account for filtering
    matching = [e for e in entries if _matches(e)]
    recent = matching[-50:]

    for entry in recent:
        print(_format_entry(entry, args.json))

    if args.follow:
        # Tail the file continuously
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                # Seek to end
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if line:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if _matches(entry):
                            print(_format_entry(entry, args.json))
                    else:
                        time.sleep(0.5)
        except KeyboardInterrupt:
            pass


def cmd_config_validate(args: argparse.Namespace) -> None:
    """Validate config file against schema and check API keys."""
    from .config import validate_config, resolve_config_path, DEFAULT_DB_PATH

    config = load_config()
    config_path = resolve_config_path()
    db_path = os.environ.get("OPENCLAWD_DB_PATH", DEFAULT_DB_PATH)

    errors: List[str] = []

    # Check config file exists
    if config_path is None:
        errors.append("No config file found in any search path")
    elif not config:
        errors.append(f"Config file at '{config_path}' is empty or invalid YAML")

    # Check required sections
    required_sections = ["provider"]
    for section in required_sections:
        if section not in config:
            errors.append(f"Missing required section: '{section}'")

    # Run the full config validator (API key env vars, numeric ranges, DB)
    validation_errors = validate_config(config, db_path)
    errors.extend(validation_errors)

    if errors:
        result = {
            "valid": False,
            "config_path": config_path,
            "errors": errors,
        }
        if args.json:
            _output(result, True)
        else:
            print(f"Config: {config_path or 'NOT FOUND'}")
            print(f"\nValidation FAILED ({len(errors)} error(s)):\n")
            for i, err in enumerate(errors, 1):
                print(f"  {i}. {err}")
        sys.exit(1)
    else:
        result = {
            "valid": True,
            "config_path": config_path,
            "errors": [],
        }
        if args.json:
            _output(result, True)
        else:
            print(f"Config: {config_path}")
            print("\nValidation PASSED - configuration is valid.")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run full system diagnostic and print report."""
    config = load_config()
    db_path = _get_db_path(config)

    report: Dict[str, Any] = {
        "config": {"status": "unknown", "issues": []},
        "database": {"status": "unknown", "issues": []},
        "providers": {"status": "unknown", "issues": []},
        "disk_space": {"status": "unknown"},
        "compatibility": {"status": "unknown", "issues": []},
    }

    # 1. Config validation
    config_path = resolve_config_path()
    if config_path is None:
        report["config"]["status"] = "warning"
        report["config"]["issues"].append("No config file found")
    else:
        report["config"]["path"] = config_path
        # Check required sections
        required_sections = ["provider"]
        missing = [s for s in required_sections if s not in config]
        if missing:
            report["config"]["status"] = "error"
            report["config"]["issues"].append(f"Missing sections: {', '.join(missing)}")
        else:
            report["config"]["status"] = "ok"

        # Check API key env vars
        provider_section = config.get("provider", {})
        if isinstance(provider_section, dict):
            api_key_env = provider_section.get("api_key_env")
            if api_key_env:
                if os.environ.get(api_key_env):
                    report["config"]["api_key_set"] = True
                else:
                    report["config"]["status"] = "warning"
                    report["config"]["issues"].append(
                        f"Environment variable '{api_key_env}' is not set"
                    )
                    report["config"]["api_key_set"] = False

    # 2. Database connection
    try:
        conn = _get_connection(db_path)
        conn.execute("SELECT 1")
        # Check expected tables
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        report["database"]["status"] = "ok"
        report["database"]["path"] = db_path
        report["database"]["tables"] = sorted(tables)
        expected = {"tasks", "agent_activity", "task_contributions", "notifications"}
        missing_tables = expected - tables
        if missing_tables:
            report["database"]["status"] = "warning"
            report["database"]["issues"].append(
                f"Missing tables: {', '.join(sorted(missing_tables))}"
            )
        conn.close()
    except (sqlite3.Error, OSError) as exc:
        report["database"]["status"] = "error"
        report["database"]["path"] = db_path
        report["database"]["issues"].append(f"Cannot connect: {exc}")

    # 3. Provider API key validation
    provider_issues: List[str] = []
    provider_section = config.get("provider", {})
    if isinstance(provider_section, dict):
        api_key_env = provider_section.get("api_key_env")
        prov_name = provider_section.get("name", "unknown")
        if api_key_env:
            if os.environ.get(api_key_env):
                report["providers"]["primary"] = {"name": prov_name, "api_key": "set"}
            else:
                provider_issues.append(f"Primary provider '{prov_name}': {api_key_env} not set")
                report["providers"]["primary"] = {"name": prov_name, "api_key": "missing"}

    fallback_section = config.get("fallback", {})
    if isinstance(fallback_section, dict) and fallback_section.get("name"):
        fb_key_env = fallback_section.get("api_key_env")
        fb_name = fallback_section.get("name")
        if fb_key_env:
            if os.environ.get(fb_key_env):
                report["providers"]["fallback"] = {"name": fb_name, "api_key": "set"}
            else:
                provider_issues.append(f"Fallback provider '{fb_name}': {fb_key_env} not set")
                report["providers"]["fallback"] = {"name": fb_name, "api_key": "missing"}

    report["providers"]["issues"] = provider_issues
    report["providers"]["status"] = "ok" if not provider_issues else "warning"

    # 4. Disk space
    try:
        usage = shutil.disk_usage(os.path.dirname(db_path))
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        report["disk_space"]["free_gb"] = round(free_gb, 2)
        report["disk_space"]["total_gb"] = round(total_gb, 2)
        report["disk_space"]["percent_used"] = round((usage.used / usage.total) * 100, 1)
        if free_gb < 1.0:
            report["disk_space"]["status"] = "warning"
            report["disk_space"]["message"] = "Less than 1 GB free"
        else:
            report["disk_space"]["status"] = "ok"
    except OSError as exc:
        report["disk_space"]["status"] = "error"
        report["disk_space"]["message"] = str(exc)

    # 5. Compatibility check
    try:
        from .compatibility_check import check_compatibility
        compat = check_compatibility(db_path=db_path)
        report["compatibility"]["compatible"] = compat["compatible"]
        report["compatibility"]["tier"] = compat["tier"]
        report["compatibility"]["issues"] = compat["issues"]
        report["compatibility"]["status"] = "ok" if compat["compatible"] else "warning"
    except Exception as exc:
        report["compatibility"]["status"] = "error"
        report["compatibility"]["issues"] = [str(exc)]

    if args.json:
        _output(report, True)
    else:
        print("OpenClawd System Diagnostic Report")
        print("=" * 50)
        for section_name, section_data in report.items():
            status = section_data.get("status", "unknown")
            status_icon = {"ok": "[OK]", "warning": "[WARN]", "error": "[ERR]", "unknown": "[??]"}.get(status, "[??]")
            print(f"\n{status_icon} {section_name.replace('_', ' ').title()}")

            for key, value in section_data.items():
                if key in ("status", "issues"):
                    continue
                print(f"  {key}: {value}")

            issues = section_data.get("issues", [])
            if issues:
                for issue in issues:
                    print(f"  ! {issue}")

        # Summary
        all_statuses = [s.get("status") for s in report.values()]
        if "error" in all_statuses:
            print("\nOverall: ERRORS FOUND - some components are not working")
        elif "warning" in all_statuses:
            print("\nOverall: WARNINGS - some components may need attention")
        else:
            print("\nOverall: ALL CHECKS PASSED")


def cmd_demo(args: argparse.Namespace) -> None:
    """Create a demo task, dispatch it, poll for completion, and clean up."""
    config = load_config()
    db_path = _get_db_path(config)

    # Create demo task via adapter
    if not args.json and HAS_RICH:
        console = Console()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Creating demo task...", total=None)
            try:
                from .openclawd_adapter import OpenClawdAdapter
                adapter = OpenClawdAdapter(db_path=db_path)
                task_id = adapter.create_task(
                    title="Demo: What is SQLite WAL mode?",
                    description="Research and explain what SQLite WAL (Write-Ahead Logging) mode is, how it works, and its benefits.",
                    domain="research",
                    priority=3,
                    assigned_agent="research",
                    deliverable_type="report",
                    estimated_effort=2,
                    business_impact=1,
                )
            except Exception as e:
                _output({"demo": False, "error": f"Failed to create demo task: {e}"}, args.json)
                sys.exit(1)
    else:
        print("Creating demo task...")
        try:
            from .openclawd_adapter import OpenClawdAdapter
            adapter = OpenClawdAdapter(db_path=db_path)
            task_id = adapter.create_task(
                title="Demo: What is SQLite WAL mode?",
                description="Research and explain what SQLite WAL (Write-Ahead Logging) mode is, how it works, and its benefits.",
                domain="research",
                priority=3,
                assigned_agent="research",
                deliverable_type="report",
                estimated_effort=2,
                business_impact=1,
            )
        except Exception as e:
            _output({"demo": False, "error": f"Failed to create demo task: {e}"}, args.json)
            sys.exit(1)

    print(f"Demo task created: ID={task_id}")

    # Try to trigger immediate dispatch via kick (SIGUSR1) or direct dispatch
    pid = _read_pid_file()
    if pid is not None and _is_pid_running(pid):
        try:
            os.kill(pid, signal.SIGUSR1)
            print("Sent kick signal to supervisor for immediate dispatch.")
        except OSError:
            pass
    else:
        # No daemon running, try direct dispatch via claim_task
        try:
            from .dispatch_db import claim_task
            claimed = claim_task(task_id, lease_seconds=300)
            if claimed:
                print("Task claimed for direct dispatch.")
            else:
                print("Could not claim task (may need daemon running).")
        except Exception:
            pass

    # Poll for completion up to 5 minutes (300 seconds)
    print("Waiting for task completion (timeout: 5 minutes)...")
    timeout = 300
    poll_interval = 5
    elapsed = 0

    completed = False
    task_result: Optional[Dict[str, Any]] = None

    try:
        while elapsed < timeout:
            try:
                conn = _get_connection(db_path)
                row = conn.execute(
                    "SELECT id, title, status, dispatch_status, description FROM tasks WHERE id = ?",
                    (task_id,),
                ).fetchone()
                conn.close()

                if row:
                    task_result = dict(row)
                    ds = task_result.get("dispatch_status")
                    st = task_result.get("status")
                    if ds == "completed" or st == "completed":
                        completed = True
                        break
                    elif ds in ("dispatch_failed",):
                        print(f"Task dispatch failed (dispatch_status={ds}).")
                        break
            except (sqlite3.Error, OSError):
                pass

            time.sleep(poll_interval)
            elapsed += poll_interval
            if elapsed % 30 == 0:
                print(f"  Still waiting... ({elapsed}s elapsed)")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    # Print result
    if completed and task_result:
        # Try to get deliverable content from dispatch_runs or working_memory
        deliverable = ""
        try:
            conn = _get_connection(db_path)
            dr_row = conn.execute(
                "SELECT output_file FROM dispatch_runs WHERE task_id = ? AND status = 'completed' ORDER BY id DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if dr_row:
                deliverable = dict(dr_row).get("output_file", "")
            conn.close()
        except (sqlite3.Error, OSError):
            pass

        result = {
            "demo": True,
            "task_id": task_id,
            "status": "completed",
            "title": task_result.get("title", ""),
            "output_file": deliverable,
        }
        if args.json:
            _output(result, True)
        else:
            print(f"\nDemo task completed!")
            print(f"  Task ID: {task_id}")
            print(f"  Title: {task_result.get('title', '')}")
            if deliverable:
                print(f"  Output: {deliverable}")
    elif task_result and task_result.get("dispatch_status") == "dispatch_failed":
        result = {
            "demo": False,
            "task_id": task_id,
            "status": "dispatch_failed",
        }
        _output(result, args.json)
    else:
        result = {
            "demo": False,
            "task_id": task_id,
            "status": "timeout",
            "message": f"Task did not complete within {timeout} seconds",
        }
        if args.json:
            _output(result, True)
        else:
            print(f"\nDemo task timed out after {timeout} seconds.")
            print(f"  Task ID: {task_id}")
            print("  The task may still be processing. Check with: openclawd tasks --status dispatched")

    # Clean up demo task
    print("Cleaning up demo task...")
    try:
        conn = _get_connection(db_path)
        # Delete from dispatch_runs first (foreign key)
        conn.execute("DELETE FROM dispatch_runs WHERE task_id = ?", (task_id,))
        # Delete from working_memory
        conn.execute("DELETE FROM working_memory WHERE task_id = ?", (task_id,))
        # Delete from task_dependencies
        conn.execute("DELETE FROM task_dependencies WHERE task_id = ? OR depends_on_task_id = ?", (task_id, task_id))
        # Delete the task itself
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        print("Demo task cleaned up.")
    except (sqlite3.Error, OSError) as e:
        print(f"Warning: Failed to clean up demo task {task_id}: {e}")


def _get_status_dict(config: Dict[str, Any]) -> Dict[str, Any]:
    """Build the status JSON dict (shared by cmd_status and serve endpoint)."""
    db_path = _get_db_path(config)

    pid = _read_pid_file()
    running = pid is not None and _is_pid_running(pid)

    active_tasks = 0
    queued_tasks = 0
    try:
        conn = _get_connection(db_path)
        row = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE dispatch_status = 'dispatched'"
        ).fetchone()
        active_tasks = row[0] if row else 0

        row = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE dispatch_status IS NULL OR dispatch_status = 'queued'"
        ).fetchone()
        queued_tasks = row[0] if row else 0
        conn.close()
    except (sqlite3.Error, OSError):
        pass

    # Budget usage
    budget_usage: Dict[str, Any] = {}
    try:
        conn = _get_connection(db_path)
        import datetime
        today = datetime.date.today().isoformat()
        row = conn.execute(
            "SELECT SUM(total_cost_usd) as cost, SUM(total_tokens) as tokens FROM daily_usage WHERE date = ?",
            (today,),
        ).fetchone()
        if row and row[0] is not None:
            budget_usage["today_cost_usd"] = round(row[0], 4)
            budget_usage["today_tokens"] = row[1] or 0
        else:
            budget_usage["today_cost_usd"] = 0.0
            budget_usage["today_tokens"] = 0
        conn.close()
    except (sqlite3.Error, OSError):
        budget_usage["today_cost_usd"] = 0.0
        budget_usage["today_tokens"] = 0

    # Health summary
    health_summary: Dict[str, Any] = {}
    try:
        conn = _get_connection(db_path)
        rows = conn.execute(
            "SELECT passed, COUNT(*) as cnt FROM provider_health GROUP BY passed"
        ).fetchall()
        total = sum(dict(r)["cnt"] for r in rows)
        passed = sum(dict(r)["cnt"] for r in rows if dict(r)["passed"])
        health_summary["total_checks"] = total
        health_summary["passed"] = passed
        health_summary["failed"] = total - passed
        conn.close()
    except (sqlite3.Error, OSError):
        health_summary["total_checks"] = 0
        health_summary["passed"] = 0
        health_summary["failed"] = 0

    return {
        "status": "running" if running else "stopped",
        "pid": pid if running else None,
        "active_tasks": active_tasks,
        "queued_tasks": queued_tasks,
        "budget_usage": budget_usage,
        "health_summary": health_summary,
    }


def cmd_serve(args: argparse.Namespace) -> None:
    """Start lightweight HTTP server exposing GET /status endpoint."""
    import datetime
    from http.server import HTTPServer, BaseHTTPRequestHandler

    config = load_config()
    port = args.port

    class StatusHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/status" or self.path == "/status/":
                status_data = _get_status_dict(config)
                body = json.dumps(status_data, indent=2, default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                body = json.dumps({"error": "Not found", "available_endpoints": ["/status"]}).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, format: str, *log_args: Any) -> None:
            ts = datetime.datetime.now().isoformat()
            print(f"[{ts}] {self.client_address[0]} - {format % log_args}")

    server = HTTPServer(("127.0.0.1", port), StatusHandler)
    print(f"OpenClawd status server listening on http://127.0.0.1:{port}")
    print(f"  GET /status - Returns supervisor status as JSON")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


def cmd_init(args: argparse.Namespace) -> None:
    """Interactive init wizard to generate openclawd.config.yaml."""
    output_path = os.path.join(os.getcwd(), CONFIG_FILENAME)

    # Check if config already exists
    if os.path.exists(output_path):
        confirm = input(
            f"Config file already exists at {output_path}. Overwrite? [y/N]: "
        ).strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted. Existing config was not modified.")
            return

    # Provider selection
    providers = ["anthropic", "openai", "gemini", "ollama"]
    print("\nAvailable providers:")
    for i, p in enumerate(providers, 1):
        print(f"  {i}. {p}")
    while True:
        choice = input(f"Select provider [1-{len(providers)}] (default: 1): ").strip()
        if not choice:
            provider_name = providers[0]
            break
        try:
            idx = int(choice)
            if 1 <= idx <= len(providers):
                provider_name = providers[idx - 1]
                break
        except ValueError:
            pass
        print(f"Invalid choice. Enter a number between 1 and {len(providers)}.")

    # Model name
    default_models = {
        "anthropic": "claude-sonnet-4-5",
        "openai": "gpt-4o",
        "gemini": "gemini-pro",
        "ollama": "llama3",
    }
    default_model = default_models.get(provider_name, "default")
    model = input(f"Model name (default: {default_model}): ").strip()
    if not model:
        model = default_model

    # API key env var
    default_keys = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "ollama": "",
    }
    default_key = default_keys.get(provider_name, "")
    if default_key:
        api_key_env = input(
            f"API key environment variable name (default: {default_key}): "
        ).strip()
        if not api_key_env:
            api_key_env = default_key
    else:
        api_key_env = input(
            "API key environment variable name (leave blank if none): "
        ).strip()

    # Max concurrent agents
    while True:
        raw = input("Max concurrent agents (default: 3): ").strip()
        if not raw:
            max_concurrent = 3
            break
        try:
            max_concurrent = int(raw)
            if max_concurrent > 0:
                break
        except ValueError:
            pass
        print("Please enter a positive integer.")

    # Daily budget
    while True:
        raw = input("Daily budget in USD (default: 50.00): ").strip()
        if not raw:
            daily_budget = 50.00
            break
        try:
            daily_budget = float(raw)
            if daily_budget >= 0:
                break
        except ValueError:
            pass
        print("Please enter a non-negative number.")

    # Generate YAML content
    lines = [
        "# OpenClawd Agent Dispatch System - Configuration",
        f"# Generated by 'openclawd init'",
        "",
        "provider:",
        f'  name: "{provider_name}"',
    ]
    if api_key_env:
        lines.append(f'  api_key_env: "{api_key_env}"')
    lines.extend([
        f'  model: "{model}"',
        "  base_url: null",
        "",
        f"max_concurrent_agents: {max_concurrent}",
        f"daily_budget_usd: {daily_budget:.2f}",
        "",
    ])

    yaml_content = "\n".join(lines)

    with open(output_path, "w") as f:
        f.write(yaml_content)

    print(f"\nConfig written to {output_path}")
    print("\nNext steps:")
    print(f"  1. Set your API key: export {api_key_env or 'YOUR_API_KEY'}=<key>")
    print("  2. Validate config: openclawd config validate")
    print("  3. Run health check: openclawd health")
    print("  4. Start the daemon: openclawd daemon")


def cmd_pipeline_create(args: argparse.Namespace) -> None:
    """Interactively create a task dependency chain (pipeline)."""
    config = load_config()
    db_path = _get_db_path(config)

    from .openclawd_adapter import OpenClawdAdapter

    try:
        adapter = OpenClawdAdapter(db_path=db_path)
    except Exception as e:
        _output({"error": f"Failed to initialize adapter: {e}"}, args.json)
        sys.exit(1)

    conn = _get_connection(db_path)

    # Step 1: Parent task - use existing or create new
    parent_choice = input("Use existing task as parent? [y/N]: ").strip().lower()
    parent_task_id: Optional[int] = None

    if parent_choice in ("y", "yes"):
        while True:
            raw_id = input("Enter parent task ID: ").strip()
            try:
                parent_task_id = int(raw_id)
                row = conn.execute(
                    "SELECT id, title FROM tasks WHERE id = ?", (parent_task_id,)
                ).fetchone()
                if row:
                    print(f"  Parent: [{row['id']}] {row['title']}")
                    break
                else:
                    print(f"  Task ID {parent_task_id} not found. Try again.")
            except ValueError:
                print("  Please enter a valid integer.")
    else:
        # Create a new parent task
        title = input("Parent task title: ").strip()
        if not title:
            print("Title cannot be empty.")
            conn.close()
            sys.exit(1)
        description = input("Parent task description: ").strip() or title
        domain = input("Domain (default: general): ").strip() or "general"
        try:
            parent_task_id = adapter.create_task(
                title=title,
                description=description,
                domain=domain,
                priority=3,
                deliverable_type="report",
                estimated_effort=5,
                business_impact=3,
            )
            print(f"  Created parent task: ID={parent_task_id}")
        except Exception as e:
            _output({"error": f"Failed to create parent task: {e}"}, args.json)
            conn.close()
            sys.exit(1)

    # Step 2: Number of child tasks
    while True:
        raw_count = input("Number of child tasks: ").strip()
        try:
            child_count = int(raw_count)
            if child_count > 0:
                break
        except ValueError:
            pass
        print("  Please enter a positive integer.")

    # Step 3: Dependency type
    while True:
        dep_type = input("Dependency type (completion/contribution) [default: completion]: ").strip().lower()
        if not dep_type:
            dep_type = "completion"
        if dep_type in ("completion", "contribution"):
            break
        print("  Must be 'completion' or 'contribution'.")

    # Step 4: Create each child task
    created_children: List[Dict[str, Any]] = []
    for i in range(1, child_count + 1):
        print(f"\n--- Child task {i}/{child_count} ---")
        child_title = input(f"  Title: ").strip()
        if not child_title:
            child_title = f"Pipeline child {i}"
        child_desc = input(f"  Description: ").strip() or child_title
        child_agent = input(f"  Assigned agent (leave blank for none): ").strip() or None

        try:
            child_id = adapter.create_task(
                title=child_title,
                description=child_desc,
                domain="general",
                priority=3,
                assigned_agent=child_agent,
                deliverable_type="report",
                estimated_effort=5,
                business_impact=3,
            )
        except Exception as e:
            print(f"  ERROR creating child task: {e}")
            continue

        # Create dependency row linking child to parent
        try:
            conn.execute(
                "INSERT INTO task_dependencies (task_id, depends_on_task_id, dependency_type) VALUES (?, ?, ?)",
                (child_id, parent_task_id, dep_type),
            )
            conn.commit()
        except sqlite3.Error as e:
            print(f"  WARNING: Failed to create dependency link: {e}")

        created_children.append({
            "id": child_id,
            "title": child_title,
            "assigned_agent": child_agent,
            "dependency_type": dep_type,
        })
        print(f"  Created child task: ID={child_id}")

    conn.close()

    # Print summary
    summary = {
        "parent_task_id": parent_task_id,
        "dependency_type": dep_type,
        "children_created": len(created_children),
        "children": created_children,
    }

    if args.json:
        _output(summary, True)
    else:
        print(f"\n{'=' * 40}")
        print(f"Pipeline Summary")
        print(f"{'=' * 40}")
        print(f"Parent task ID: {parent_task_id}")
        print(f"Dependency type: {dep_type}")
        print(f"Children created: {len(created_children)}")
        for child in created_children:
            agent_str = f" (agent: {child['assigned_agent']})" if child['assigned_agent'] else ""
            print(f"  [{child['id']}] {child['title']}{agent_str}")


def cmd_tool_test(args: argparse.Namespace) -> None:
    """Run tool test blocks from YAML definitions to verify tool executors work."""
    from .tool_registry import ToolRegistry, ToolRegistryError
    import importlib

    tool_name = args.tool_name
    registry = ToolRegistry()

    # Load tool definition
    try:
        tool = registry.get_tool(tool_name)
    except ToolRegistryError as e:
        _output({"tool": tool_name, "passed": False, "error": str(e)}, args.json)
        sys.exit(1)

    # Check for test block
    if tool.test is None:
        _output({"tool": tool_name, "passed": False, "error": "No test block defined in tool YAML"}, args.json)
        sys.exit(1)

    test_input = tool.test.get("input", {})
    expected = tool.test.get("expected", {})

    # Import and call tool executor
    module_path = tool.execution["module"]
    function_name = tool.execution["function"]

    try:
        mod = importlib.import_module(module_path)
    except ImportError as e:
        _output({"tool": tool_name, "passed": False, "error": f"Cannot import executor module '{module_path}': {e}"}, args.json)
        sys.exit(1)

    func = getattr(mod, function_name, None)
    if func is None:
        _output({"tool": tool_name, "passed": False, "error": f"Function '{function_name}' not found in module '{module_path}'"}, args.json)
        sys.exit(1)

    # Execute the tool with test inputs
    try:
        result = func(**test_input)
    except Exception as e:
        _output({"tool": tool_name, "passed": False, "error": f"Executor raised {type(e).__name__}: {e}"}, args.json)
        sys.exit(1)

    # Validate output structure against expected shape
    errors: List[str] = []

    # Check has_fields: output must be a dict containing these keys
    has_fields = expected.get("has_fields", [])
    if has_fields:
        if not isinstance(result, dict):
            errors.append(f"Expected dict output with fields {has_fields}, got {type(result).__name__}")
        else:
            for field_name in has_fields:
                if field_name not in result:
                    errors.append(f"Missing expected field: '{field_name}'")

    # Check type: output must match the expected type name
    expected_type = expected.get("type")
    if expected_type:
        type_map = {"dict": dict, "list": list, "str": str, "int": int, "float": float, "bool": bool}
        expected_cls = type_map.get(expected_type)
        if expected_cls and not isinstance(result, expected_cls):
            errors.append(f"Expected type '{expected_type}', got '{type(result).__name__}'")

    passed = len(errors) == 0

    output = {
        "tool": tool_name,
        "passed": passed,
        "test_input": test_input,
        "result_type": type(result).__name__,
    }
    if has_fields and isinstance(result, dict):
        output["result_fields"] = list(result.keys())
    if errors:
        output["errors"] = errors

    if args.json:
        _output(output, True)
    else:
        if passed:
            print(f"PASS: tool '{tool_name}' test passed")
            print(f"  Input: {test_input}")
            print(f"  Output type: {type(result).__name__}")
            if isinstance(result, dict):
                print(f"  Output fields: {list(result.keys())}")
        else:
            print(f"FAIL: tool '{tool_name}' test failed")
            print(f"  Input: {test_input}")
            for err in errors:
                print(f"  Error: {err}")
            sys.exit(1)


# ── Main Entry Point ────────────────────────────────────────────


def main() -> None:
    """CLI entry point for the 'openclawd' command."""
    # Ensure config exists before processing any commands
    ensure_config()

    parser = argparse.ArgumentParser(
        prog="openclawd",
        description="OpenClawd Agent Dispatch System CLI",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output in machine-readable JSON format",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    sub_status = subparsers.add_parser("status", help="Print supervisor status")
    sub_status.set_defaults(func=cmd_status)

    # tasks
    sub_tasks = subparsers.add_parser("tasks", help="List tasks with optional filters")
    sub_tasks.add_argument("--status", type=str, default=None, help="Filter by dispatch_status")
    sub_tasks.add_argument("--agent", type=str, default=None, help="Filter by assigned_agent")
    sub_tasks.add_argument("--priority", type=int, default=None, help="Minimum priority filter")
    sub_tasks.set_defaults(func=cmd_tasks)

    # dispatch
    sub_dispatch = subparsers.add_parser("dispatch", help="Manually dispatch a specific task")
    sub_dispatch.add_argument("task_id", type=int, help="Task ID to dispatch")
    sub_dispatch.set_defaults(func=cmd_dispatch)

    # run
    sub_run = subparsers.add_parser("run", help="Run a single poll cycle and exit")
    sub_run.set_defaults(func=cmd_run)

    # daemon
    sub_daemon = subparsers.add_parser("daemon", help="Start persistent supervisor loop")
    sub_daemon.set_defaults(func=cmd_daemon)

    # stop
    sub_stop = subparsers.add_parser("stop", help="Send SIGTERM to supervisor PID")
    sub_stop.set_defaults(func=cmd_stop)

    # kick
    sub_kick = subparsers.add_parser("kick", help="Send SIGUSR1 for immediate poll")
    sub_kick.set_defaults(func=cmd_kick)

    # health
    sub_health = subparsers.add_parser("health", help="Run provider health checks")
    sub_health.set_defaults(func=cmd_health)

    # doctor
    sub_doctor = subparsers.add_parser("doctor", help="Run full system diagnostic")
    sub_doctor.set_defaults(func=cmd_doctor)

    # logs
    sub_logs = subparsers.add_parser("logs", help="Tail supervisor log with filters")
    sub_logs.add_argument("--follow", "-f", action="store_true", default=False, help="Follow log output continuously")
    sub_logs.add_argument("--level", type=str, default=None, help="Filter by log level (e.g. ERROR, INFO)")
    sub_logs.add_argument("--agent", type=str, default=None, help="Filter by agent_name")
    sub_logs.add_argument("--task", type=str, default=None, help="Filter by task_id")
    sub_logs.add_argument("--trace", type=str, default=None, help="Filter by trace_id")
    sub_logs.set_defaults(func=cmd_logs)

    # serve
    sub_serve = subparsers.add_parser("serve", help="Start HTTP server exposing /status endpoint")
    sub_serve.add_argument("--port", type=int, default=8377, help="Port to listen on (default: 8377)")
    sub_serve.set_defaults(func=cmd_serve)

    # demo
    sub_demo = subparsers.add_parser("demo", help="Create and dispatch a demo task to verify end-to-end")
    sub_demo.set_defaults(func=cmd_demo)

    # config (with sub-subcommands)
    sub_config = subparsers.add_parser("config", help="Configuration management commands")
    config_subparsers = sub_config.add_subparsers(dest="config_command", help="Config subcommands")
    sub_config_validate = config_subparsers.add_parser("validate", help="Validate config file")
    sub_config_validate.set_defaults(func=cmd_config_validate)
    sub_config.set_defaults(func=lambda a: sub_config.print_help())

    # init
    sub_init = subparsers.add_parser("init", help="Interactive setup wizard to generate config")
    sub_init.set_defaults(func=cmd_init)

    # tool (with sub-subcommands)
    sub_tool = subparsers.add_parser("tool", help="Tool management commands")
    tool_subparsers = sub_tool.add_subparsers(dest="tool_command", help="Tool subcommands")
    sub_tool_test = tool_subparsers.add_parser("test", help="Run tool test block from YAML definition")
    sub_tool_test.add_argument("tool_name", type=str, help="Name of the tool to test")
    sub_tool_test.set_defaults(func=cmd_tool_test)
    sub_tool.set_defaults(func=lambda a: sub_tool.print_help())

    # pipeline (with sub-subcommands)
    sub_pipeline = subparsers.add_parser("pipeline", help="Task pipeline management commands")
    pipeline_subparsers = sub_pipeline.add_subparsers(dest="pipeline_command", help="Pipeline subcommands")
    sub_pipeline_create = pipeline_subparsers.add_parser("create", help="Interactively create a task dependency chain")
    sub_pipeline_create.set_defaults(func=cmd_pipeline_create)
    sub_pipeline.set_defaults(func=lambda a: sub_pipeline.print_help())

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
