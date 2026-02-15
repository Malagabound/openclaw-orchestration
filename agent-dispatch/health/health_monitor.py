"""Health monitor scheduled runner for provider canary tests.

Runs all 4 canary tests for configured providers on a background thread
at a configurable interval (default 6 hours). Stores results in the
provider_health table.

US-063: Adds conformance-based fallback tracking via
check_tool_calling_conformance() that monitors tool_calling and
tool_result_handling pass rates over a rolling 20-check window,
switching to prompt-based mode if reliability drops below 80% and
recovering after 2 consecutive passing runs.

REQ-042: Runs compatibility checks periodically and stores results
in provider_health table with provider='openclawd'.
"""

import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from ..config import DEFAULT_DB_PATH
from ..health.canary_tests import ALL_CANARY_TESTS
from ..llm_provider import LLMProvider
from ..provider_registry import get_provider, ProviderRegistryError

logger = logging.getLogger(__name__)

# Default interval if not specified in config.
_DEFAULT_INTERVAL_HOURS: int = 6

# In-memory tracking of provider tool modes.
# Key: (provider, model), Value: "native" or "prompt_based"
_tool_modes: Dict[Tuple[str, str], str] = {}

# Conformance thresholds
_CONFORMANCE_WINDOW: int = 20
_CONFORMANCE_FAILURE_THRESHOLD: float = 0.80  # switch if pass rate < 80%
_RECOVERY_CONSECUTIVE_PASSES: int = 2


def _get_connection(db_path: str) -> sqlite3.Connection:
    """Create a connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _store_result(
    conn: sqlite3.Connection,
    provider_name: str,
    model: str,
    test_name: str,
    result: Dict[str, Any],
) -> None:
    """Write a single canary test result to the provider_health table."""
    conn.execute(
        """
        INSERT INTO provider_health
            (provider, model, test_name, passed, latency_ms,
             error_message, error_category, raw_response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            provider_name,
            model,
            test_name,
            1 if result["passed"] else 0,
            result["latency_ms"],
            result.get("error_message"),
            result.get("error_category"),
            result.get("raw_response"),
        ),
    )


def detect_regressions(
    provider: str,
    model: str,
    test_name: str,
    current_result: Dict[str, Any],
    conn: sqlite3.Connection,
) -> List[Dict[str, Any]]:
    """Compare current health check result against history to detect regressions.

    Checks for: new failure after success, 3x latency increase, consecutive
    failures, and novel error categories.

    Args:
        provider: Provider name (e.g. "anthropic").
        model: Model identifier (e.g. "claude-sonnet-4-5-20250929").
        test_name: Canary test name (e.g. "simple_completion").
        current_result: Dict with keys passed (bool), latency_ms (float),
            and optionally error_category (str).
        conn: Open sqlite3 connection to coordination.db.

    Returns:
        List of issue dicts, each with 'type' and 'details' keys.
    """
    issues: List[Dict[str, Any]] = []

    # --- 1. Query last successful run ---
    cursor = conn.execute(
        """
        SELECT latency_ms FROM provider_health
        WHERE provider = ? AND model = ? AND test_name = ? AND passed = 1
        ORDER BY tested_at DESC LIMIT 1
        """,
        (provider, model, test_name),
    )
    last_success = cursor.fetchone()

    # --- 2. Detect failure when last run was successful ---
    if not current_result["passed"] and last_success is not None:
        issues.append({
            "type": "failure_after_success",
            "details": (
                f"Current run failed but last run for "
                f"{provider}/{model}/{test_name} passed"
            ),
        })

    # --- 3. Detect latency regression (current > 3x last successful) ---
    if (
        current_result["passed"]
        and last_success is not None
        and last_success[0] is not None
        and last_success[0] > 0
        and current_result["latency_ms"] > 3 * last_success[0]
    ):
        issues.append({
            "type": "latency_regression",
            "details": (
                f"Current latency {current_result['latency_ms']:.1f}ms "
                f"exceeds 3x last successful latency {last_success[0]:.1f}ms "
                f"for {provider}/{model}/{test_name}"
            ),
        })

    # --- 4. Detect consecutive failures (last 2 runs both failed) ---
    cursor = conn.execute(
        """
        SELECT passed FROM provider_health
        WHERE provider = ? AND model = ? AND test_name = ?
        ORDER BY tested_at DESC LIMIT 2
        """,
        (provider, model, test_name),
    )
    recent_runs = cursor.fetchall()
    if (
        not current_result["passed"]
        and len(recent_runs) >= 2
        and all(row[0] == 0 for row in recent_runs)
    ):
        issues.append({
            "type": "consecutive_failures",
            "details": (
                f"Last 2 runs for {provider}/{model}/{test_name} both failed"
            ),
        })

    # --- 5. Detect novel error category ---
    current_category = current_result.get("error_category")
    if current_category is not None:
        cursor = conn.execute(
            """
            SELECT DISTINCT error_category FROM provider_health
            WHERE provider = ? AND model = ? AND test_name = ?
                AND error_category IS NOT NULL
            ORDER BY tested_at DESC LIMIT 20
            """,
            (provider, model, test_name),
        )
        known_categories = {row[0] for row in cursor.fetchall()}
        if current_category not in known_categories:
            issues.append({
                "type": "novel_error_category",
                "details": (
                    f"Error category '{current_category}' not seen in "
                    f"last 20 runs for {provider}/{model}/{test_name}"
                ),
            })

    return issues


def check_tool_calling_conformance(
    provider: str,
    model: str,
    conn: sqlite3.Connection,
) -> str:
    """Check tool-calling reliability and switch modes if needed.

    Queries the last 20 tool_calling and tool_result_handling health checks
    for this provider/model. If the pass rate is below 80% (4+ failures),
    switches to prompt-based tool mode. If already in prompt-based mode and
    the last 2 consecutive runs both passed for both test types, switches
    back to native mode.

    Args:
        provider: Provider name (e.g. "anthropic").
        model: Model identifier (e.g. "claude-sonnet-4-5-20250929").
        conn: Open sqlite3 connection to coordination.db.

    Returns:
        Current tool mode: "native" or "prompt_based".
    """
    key = (provider, model)
    current_mode = _tool_modes.get(key, "native")

    # Query last 20 health checks for tool_calling and tool_result_handling
    cursor = conn.execute(
        """
        SELECT test_name, passed FROM provider_health
        WHERE provider = ? AND model = ?
            AND test_name IN ('tool_calling', 'tool_result_handling')
        ORDER BY tested_at DESC
        LIMIT ?
        """,
        (provider, model, _CONFORMANCE_WINDOW),
    )
    rows = cursor.fetchall()

    if not rows:
        return current_mode

    # Calculate pass rate
    total = len(rows)
    failures = sum(1 for _, passed in rows if not passed)
    pass_rate = (total - failures) / total

    if current_mode == "native":
        # Check if we need to switch to prompt-based mode
        if pass_rate < _CONFORMANCE_FAILURE_THRESHOLD:
            _tool_modes[key] = "prompt_based"
            reason = (
                f"Tool-calling pass rate {pass_rate:.0%} ({failures}/{total} failures) "
                f"below {_CONFORMANCE_FAILURE_THRESHOLD:.0%} threshold"
            )
            logger.warning(
                "Switching %s/%s to prompt-based tool mode: %s",
                provider, model, reason,
            )
            _log_mode_switch(conn, provider, "native", "prompt_based", reason)
            return "prompt_based"
    else:
        # In prompt-based mode: check recovery condition
        # Last 2 consecutive runs must both pass for both test types
        if _check_recovery(provider, model, conn):
            _tool_modes[key] = "native"
            reason = (
                f"Last {_RECOVERY_CONSECUTIVE_PASSES} consecutive runs passed "
                f"for both tool_calling and tool_result_handling"
            )
            logger.info(
                "Recovering %s/%s to native tool mode: %s",
                provider, model, reason,
            )
            _log_mode_switch(conn, provider, "prompt_based", "native", reason)
            return "native"

    return current_mode


def _check_recovery(
    provider: str,
    model: str,
    conn: sqlite3.Connection,
) -> bool:
    """Check if both tool tests passed in the last 2 consecutive runs.

    For recovery, we need the most recent 2 results for each of
    tool_calling and tool_result_handling to all be passed=true.
    """
    for test_name in ("tool_calling", "tool_result_handling"):
        cursor = conn.execute(
            """
            SELECT passed FROM provider_health
            WHERE provider = ? AND model = ? AND test_name = ?
            ORDER BY tested_at DESC
            LIMIT ?
            """,
            (provider, model, test_name, _RECOVERY_CONSECUTIVE_PASSES),
        )
        recent = cursor.fetchall()
        if len(recent) < _RECOVERY_CONSECUTIVE_PASSES:
            return False
        if not all(row[0] for row in recent):
            return False
    return True


def _log_mode_switch(
    conn: sqlite3.Connection,
    provider: str,
    from_mode: str,
    to_mode: str,
    reason: str,
) -> None:
    """Record a tool mode switch in provider_incidents."""
    try:
        conn.execute(
            """
            INSERT INTO provider_incidents
                (provider, incident_type, healing_action, auto_healed)
            VALUES (?, ?, ?, ?)
            """,
            (
                provider,
                f"tool_mode_switch_{from_mode}_to_{to_mode}",
                reason,
                1,
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.error("Failed to log mode switch for %s: %s", provider, exc)


def get_tool_mode(provider: str, model: str) -> str:
    """Return the current tool mode for a provider/model pair.

    Returns:
        "native" or "prompt_based".
    """
    return _tool_modes.get((provider, model), "native")


def _run_tests_for_provider(
    provider: LLMProvider,
    provider_name: str,
    model: str,
    conn: sqlite3.Connection,
) -> None:
    """Run all canary tests for a single provider and store results."""
    for test_name, test_fn in ALL_CANARY_TESTS:
        try:
            result = test_fn(provider)
        except Exception as exc:
            logger.error(
                "Canary test %s crashed for %s/%s: %s",
                test_name, provider_name, model, exc,
            )
            result = {
                "passed": False,
                "latency_ms": 0.0,
                "error_message": f"Test crashed: {exc}",
                "error_category": "test_crash",
                "raw_response": None,
            }
        try:
            _store_result(conn, provider_name, model, test_name, result)
        except sqlite3.Error as exc:
            logger.error(
                "Failed to store health result for %s/%s/%s: %s",
                provider_name, model, test_name, exc,
            )
    conn.commit()


def _run_compatibility_check(conn: sqlite3.Connection) -> None:
    """Run OpenClawd compatibility check and store result in provider_health.

    REQ-042: System compatibility verification as a health check.
    """
    try:
        from ..compatibility_check import check_compatibility
        # Run check with store_result=True (default) to write to provider_health
        result = check_compatibility(store_result=True)
        if result["compatible"]:
            logger.info("OpenClawd compatibility check passed (tier %d)", result["tier"])
        else:
            logger.warning(
                "OpenClawd compatibility check failed (tier %d): %s",
                result["tier"], result["issues"]
            )
    except Exception as exc:
        logger.error("Compatibility check crashed: %s", exc)


def run_health_checks(
    config: Dict[str, Any],
    conn: sqlite3.Connection,
) -> None:
    """Run all 4 canary tests for primary and fallback providers.

    Reads provider configuration from config dict, instantiates providers
    via the provider registry, runs every canary test, and writes results
    to the provider_health table with tested_at timestamp (auto-set by
    DEFAULT CURRENT_TIMESTAMP).

    REQ-042: Also runs OpenClawd compatibility check and stores result.

    Args:
        config: Parsed openclawd.config.yaml dict.
        conn: Open sqlite3 connection to coordination.db.
    """
    # Run compatibility check first
    _run_compatibility_check(conn)

    # Run tests for primary provider
    provider_section = config.get("provider", {})
    provider_name = provider_section.get("name", "unknown")
    model = provider_section.get("model", "unknown")

    try:
        primary = get_provider(config)
        logger.info("Running canary tests for primary provider %s/%s", provider_name, model)
        _run_tests_for_provider(primary, provider_name, model, conn)
    except ProviderRegistryError as exc:
        logger.error("Cannot instantiate primary provider: %s", exc)

    # Run tests for fallback provider if configured
    fallback_section = config.get("fallback")
    if fallback_section and isinstance(fallback_section, dict):
        fb_name = fallback_section.get("name")
        fb_model = fallback_section.get("model")
        if fb_name and fb_model:
            # Build a config dict that looks like a primary provider config
            # so get_provider can instantiate it.
            fallback_config = {
                "provider": {
                    "name": fb_name,
                    "api_key_env": fallback_section.get("api_key_env", ""),
                    "model": fb_model,
                    "base_url": fallback_section.get("base_url"),
                },
            }
            try:
                fallback = get_provider(fallback_config)
                logger.info(
                    "Running canary tests for fallback provider %s/%s",
                    fb_name, fb_model,
                )
                _run_tests_for_provider(fallback, fb_name, fb_model, conn)
            except ProviderRegistryError as exc:
                logger.error("Cannot instantiate fallback provider: %s", exc)


class HealthMonitorThread(threading.Thread):
    """Background daemon thread that runs health checks on a schedule.

    Args:
        config: Parsed openclawd.config.yaml dict.
        db_path: Path to coordination.db. Defaults to DEFAULT_DB_PATH.
        interval_hours: Override for health_check_interval_hours.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        db_path: Optional[str] = None,
        interval_hours: Optional[int] = None,
    ) -> None:
        super().__init__(daemon=True, name="health-monitor")
        self.config = config
        self.db_path = db_path or DEFAULT_DB_PATH
        self._interval_hours: int = (
            interval_hours
            if interval_hours is not None
            else config.get("health_check_interval_hours", _DEFAULT_INTERVAL_HOURS)
        )
        self._stop_event = threading.Event()

    @property
    def interval_seconds(self) -> float:
        return self._interval_hours * 3600.0

    def stop(self) -> None:
        """Signal the monitor thread to stop."""
        self._stop_event.set()

    def run(self) -> None:
        """Main loop: run health checks, then sleep for the interval."""
        logger.info(
            "Health monitor started (interval=%dh, db=%s)",
            self._interval_hours, self.db_path,
        )
        while not self._stop_event.is_set():
            try:
                conn = _get_connection(self.db_path)
                try:
                    run_health_checks(self.config, conn)
                finally:
                    conn.close()
            except Exception as exc:
                logger.error("Health check cycle failed: %s", exc)

            # Sleep in small increments so stop() is responsive.
            self._stop_event.wait(timeout=self.interval_seconds)

        logger.info("Health monitor stopped.")


def start_health_monitor(
    config: Dict[str, Any],
    db_path: Optional[str] = None,
) -> HealthMonitorThread:
    """Start the health monitor background thread.

    Args:
        config: Parsed openclawd.config.yaml dict.
        db_path: Path to coordination.db. Defaults to DEFAULT_DB_PATH.

    Returns:
        The running HealthMonitorThread instance.
    """
    thread = HealthMonitorThread(config=config, db_path=db_path)
    thread.start()
    return thread
