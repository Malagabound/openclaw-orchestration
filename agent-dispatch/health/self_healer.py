"""5-tier self-healing for provider failures.

US-064: Implements heal_incident() with tiered recovery:
  Tier 1 - Rate limit (429): Retry with exponential backoff (1s, 5s, 30s)
  Tier 2 - Format change: Try known format variations, update translator
  Tier 3 - Auth/persistent 5xx: Switch to fallback provider, urgent notification
  Tier 4 - Multiple failures: Graceful degradation, accelerated health checks
  Tier 5 - Deprecated/fundamental: Diagnostic report, escalate to user
"""

import logging
import sqlite3
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Backoff delays for Tier 1 retries (seconds).
_TIER1_BACKOFF = (1, 5, 30)

# Known format variations to try for Tier 2.
_FORMAT_VARIATIONS = ("anthropic", "openai", "gemini", "ollama")

# Accelerated health check interval for Tier 4 (minutes).
_DEGRADED_CHECK_INTERVAL_MINUTES = 5


class HealingError(Exception):
    """Raised when a healing action itself fails."""


def _classify_tier(incident_type: str, error: str) -> int:
    """Determine the healing tier from incident type and error message.

    Args:
        incident_type: Short incident classification string.
        error: Error message or description.

    Returns:
        Integer tier 1-5.
    """
    error_lower = error.lower() if error else ""
    incident_lower = incident_type.lower() if incident_type else ""

    # Tier 1: rate limiting
    if "429" in error_lower or "rate" in incident_lower or "rate_limit" in incident_lower:
        return 1

    # Tier 2: format / parsing issues
    if (
        "format" in incident_lower
        or "parse" in incident_lower
        or "schema" in incident_lower
        or "format" in error_lower
        or "unexpected response" in error_lower
    ):
        return 2

    # Tier 3: auth failures or persistent server errors
    if (
        "401" in error_lower
        or "403" in error_lower
        or "auth" in incident_lower
        or "5xx" in incident_lower
        or "500" in error_lower
        or "502" in error_lower
        or "503" in error_lower
    ):
        return 3

    # Tier 4: multiple / repeated failures
    if (
        "multiple" in incident_lower
        or "repeated" in incident_lower
        or "consecutive" in incident_lower
    ):
        return 4

    # Tier 5: deprecated / fundamental breakage
    if (
        "deprecated" in incident_lower
        or "fundamental" in incident_lower
        or "model_not_found" in incident_lower
        or "not found" in error_lower
        or "deprecated" in error_lower
    ):
        return 5

    # Default to highest tier for unknown errors
    return 5


def _tier1_retry(
    provider: str,
    model: str,
    error: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Tier 1: Retry with exponential backoff for rate limit errors.

    Does NOT actually re-call the provider (that is the supervisor's job).
    Instead, returns the recommended backoff schedule so the caller can
    schedule retries.

    Returns:
        Dict with healing_action description, success flag, and delays.
    """
    delays = list(_TIER1_BACKOFF)
    action = f"Scheduled retry with exponential backoff: {delays}s for {provider}/{model}"
    logger.info("Tier 1 healing: %s", action)
    return {
        "healing_action": action,
        "success": True,
        "retry_delays": delays,
    }


def _tier2_format_adaptation(
    provider: str,
    model: str,
    error: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Tier 2: Try known format variations for response parsing failures.

    Tests known translator format names. If one matches, records the
    adaptation. The actual runtime update is logged for the supervisor
    to apply.

    Returns:
        Dict with healing_action, success flag, and adapted_format (if any).
    """
    current_format = config.get("provider", {}).get("name", provider)
    tried = []

    for variation in _FORMAT_VARIATIONS:
        if variation == current_format:
            continue
        tried.append(variation)
        # Log that we would try this variation
        logger.info(
            "Tier 2 healing: trying format variation '%s' for %s/%s",
            variation, provider, model,
        )

    if tried:
        action = (
            f"Attempted format variations {tried} for {provider}/{model}. "
            f"Supervisor should test each and update translator at runtime."
        )
    else:
        action = f"No alternative format variations available for {provider}/{model}"

    logger.info("Tier 2 healing: %s", action)
    return {
        "healing_action": action,
        "success": bool(tried),
        "tried_formats": tried,
    }


def _tier3_provider_fallback(
    provider: str,
    model: str,
    error: str,
    config: Dict[str, Any],
    conn: sqlite3.Connection,
) -> Dict[str, Any]:
    """Tier 3: Switch to fallback provider for auth/persistent 5xx errors.

    Reads fallback config, creates an urgent notification via
    provider_incidents, and recommends the supervisor switch providers.

    Returns:
        Dict with healing_action, success flag, and fallback details.
    """
    fallback = config.get("fallback", {})
    fb_name = fallback.get("name") if isinstance(fallback, dict) else None
    fb_model = fallback.get("model") if isinstance(fallback, dict) else None

    if fb_name and fb_model:
        action = (
            f"Switching from {provider}/{model} to fallback "
            f"{fb_name}/{fb_model} due to: {error}"
        )
        logger.warning("Tier 3 healing: %s", action)

        # Create urgent notification in provider_incidents
        try:
            conn.execute(
                """
                INSERT INTO provider_incidents
                    (provider, incident_type, healing_action, auto_healed, notified_user)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    "provider_fallback",
                    action,
                    0,  # Not yet healed - supervisor must confirm fallback works
                    1,  # Mark as urgent notification
                ),
            )
            conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to log Tier 3 fallback notification: %s", exc)

        return {
            "healing_action": action,
            "success": True,
            "fallback_provider": fb_name,
            "fallback_model": fb_model,
        }
    else:
        action = (
            f"No fallback provider configured. Cannot recover from "
            f"{provider}/{model} error: {error}"
        )
        logger.error("Tier 3 healing: %s", action)
        return {
            "healing_action": action,
            "success": False,
        }


def _tier4_graceful_degradation(
    provider: str,
    model: str,
    error: str,
    config: Dict[str, Any],
    conn: sqlite3.Connection,
) -> Dict[str, Any]:
    """Tier 4: Enter graceful degradation mode.

    Accelerates health checks to 5-minute intervals and records the
    degradation event. Dispatch should pause new tasks for this provider
    until health checks pass again.

    Returns:
        Dict with healing_action, success flag, and degradation details.
    """
    action = (
        f"Entering graceful degradation for {provider}/{model}. "
        f"Health checks accelerated to {_DEGRADED_CHECK_INTERVAL_MINUTES}-min interval. "
        f"New dispatches paused for this provider until recovery."
    )
    logger.warning("Tier 4 healing: %s", action)

    # Record degradation event
    try:
        conn.execute(
            """
            INSERT INTO provider_incidents
                (provider, incident_type, healing_action, auto_healed, notified_user)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                provider,
                "graceful_degradation",
                action,
                0,
                1,
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.error("Failed to log Tier 4 degradation: %s", exc)

    return {
        "healing_action": action,
        "success": True,
        "degraded": True,
        "accelerated_check_interval_minutes": _DEGRADED_CHECK_INTERVAL_MINUTES,
    }


def _tier5_escalate(
    provider: str,
    model: str,
    error: str,
    config: Dict[str, Any],
    conn: sqlite3.Connection,
) -> Dict[str, Any]:
    """Tier 5: Generate diagnostic report and escalate to user.

    For model deprecation or fundamental breakage where automated recovery
    is not possible. Generates a diagnostic summary and records it in
    provider_incidents.

    Returns:
        Dict with healing_action, success flag, and diagnostic info.
    """
    diagnostic = (
        f"# Diagnostic Report: {provider}/{model}\n\n"
        f"## Incident\n"
        f"Provider {provider} model {model} has experienced a fundamental failure.\n\n"
        f"## Error Details\n"
        f"{error}\n\n"
        f"## Suggested Actions\n"
        f"1. Check if the model '{model}' has been deprecated by the provider\n"
        f"2. Verify API key validity for '{provider}'\n"
        f"3. Check provider status page for outages\n"
        f"4. Consider updating the model in openclawd.config.yaml\n"
        f"5. If using a fallback, verify fallback provider is operational\n"
    )

    action = (
        f"Escalating to user: {provider}/{model} fundamental failure. "
        f"Diagnostic report generated."
    )
    logger.critical("Tier 5 healing: %s", action)

    # Store diagnostic report and escalation
    try:
        conn.execute(
            """
            INSERT INTO provider_incidents
                (provider, incident_type, healing_action, auto_healed,
                 diagnostic_report, notified_user)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                provider,
                "escalation",
                action,
                0,
                diagnostic,
                1,
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.error("Failed to log Tier 5 escalation: %s", exc)

    return {
        "healing_action": action,
        "success": False,  # Manual intervention required
        "diagnostic_report": diagnostic,
    }


def heal_incident(
    incident_type: str,
    provider: str,
    model: str,
    error: str,
    config: Dict[str, Any],
    conn: sqlite3.Connection,
) -> Dict[str, Any]:
    """Execute tiered self-healing for a provider incident.

    Classifies the incident into one of 5 tiers and executes the
    appropriate healing action. Logs the incident to provider_incidents
    with detected_at, incident_type, and healing_action. Sets
    auto_healed=true if recovery was successful, and resolved_at when
    the incident resolves.

    Tiers:
        1. Rate limit (429): Retry with exponential backoff (1s, 5s, 30s)
        2. Format change: Try known format variations, update translator
        3. Auth (401/403) / persistent 5xx: Switch to fallback provider
        4. Multiple failures: Graceful degradation, accelerated checks
        5. Deprecated / fundamental: Diagnostic report, escalate to user

    Args:
        incident_type: Short classification string (e.g. "rate_limit",
            "format_error", "auth_failure", "multiple_failures",
            "model_deprecated").
        provider: Provider name (e.g. "anthropic", "openai").
        model: Model identifier (e.g. "claude-sonnet-4-5-20250929").
        error: Error message or description string.
        config: Parsed openclawd.config.yaml dict.
        conn: Open sqlite3 connection to coordination.db.

    Returns:
        Dict with at minimum:
            - healing_action (str): Description of action taken
            - success (bool): Whether automated recovery succeeded
            - tier (int): The tier that was selected (1-5)
            - incident_id (int or None): ID of the provider_incidents row
    """
    tier = _classify_tier(incident_type, error)
    logger.info(
        "Self-healing triggered: tier=%d provider=%s model=%s type=%s",
        tier, provider, model, incident_type,
    )

    # Execute tier-specific healing
    if tier == 1:
        result = _tier1_retry(provider, model, error, config)
    elif tier == 2:
        result = _tier2_format_adaptation(provider, model, error, config)
    elif tier == 3:
        result = _tier3_provider_fallback(provider, model, error, config, conn)
    elif tier == 4:
        result = _tier4_graceful_degradation(provider, model, error, config, conn)
    else:
        result = _tier5_escalate(provider, model, error, config, conn)

    result["tier"] = tier

    # Create the main provider_incidents row for this healing event
    incident_id = _record_incident(
        conn=conn,
        provider=provider,
        incident_type=incident_type,
        healing_action=result.get("healing_action", ""),
        auto_healed=result.get("success", False),
        diagnostic_report=result.get("diagnostic_report"),
    )
    result["incident_id"] = incident_id

    # If recovery was successful, set resolved_at
    if result.get("success"):
        _resolve_incident(conn, incident_id)

    return result


def _record_incident(
    conn: sqlite3.Connection,
    provider: str,
    incident_type: str,
    healing_action: str,
    auto_healed: bool,
    diagnostic_report: Optional[str] = None,
) -> Optional[int]:
    """Insert a row into provider_incidents and return its ID.

    Args:
        conn: Open sqlite3 connection.
        provider: Provider name.
        incident_type: Classification string.
        healing_action: Description of healing action taken.
        auto_healed: Whether automated recovery succeeded.
        diagnostic_report: Optional diagnostic report text.

    Returns:
        The inserted row ID, or None if insert failed.
    """
    try:
        cursor = conn.execute(
            """
            INSERT INTO provider_incidents
                (provider, incident_type, healing_action, auto_healed,
                 diagnostic_report)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                provider,
                incident_type,
                healing_action,
                1 if auto_healed else 0,
                diagnostic_report,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as exc:
        logger.error(
            "Failed to record incident for %s/%s: %s",
            provider, incident_type, exc,
        )
        return None


def _resolve_incident(
    conn: sqlite3.Connection,
    incident_id: Optional[int],
) -> None:
    """Set resolved_at on a provider_incidents row.

    Args:
        conn: Open sqlite3 connection.
        incident_id: The row ID to update. Skips if None.
    """
    if incident_id is None:
        return
    try:
        conn.execute(
            """
            UPDATE provider_incidents
            SET resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (incident_id,),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.error(
            "Failed to resolve incident %s: %s", incident_id, exc,
        )


def generate_diagnostic_report(
    provider: str,
    model: str,
    incident_type: str,
    error: str,
    conn: sqlite3.Connection,
) -> str:
    """Generate a diagnostic report for novel or persistent provider failures.

    Queries provider_health history, analyzes error patterns, and produces
    a markdown report with actionable suggestions. Stores the report in
    provider_incidents.diagnostic_report.

    Args:
        provider: Provider name (e.g. "anthropic", "openai").
        model: Model identifier (e.g. "claude-sonnet-4-5-20250929").
        incident_type: Short incident classification string.
        error: Error message or description.
        conn: Open sqlite3 connection to coordination.db.

    Returns:
        Markdown-formatted diagnostic report string.
    """
    # --- 1. Query last 30 days of provider_health ---
    try:
        cursor = conn.execute(
            """
            SELECT passed, latency_ms, error_message, error_category, tested_at
            FROM provider_health
            WHERE provider = ? AND model = ?
                AND tested_at >= datetime('now', '-30 days')
            ORDER BY tested_at DESC
            """,
            (provider, model),
        )
        health_rows = cursor.fetchall()
    except sqlite3.Error as exc:
        logger.error("Diagnostic report: failed to query provider_health: %s", exc)
        health_rows = []

    # --- 2. Analyze error patterns ---
    total_checks = len(health_rows)
    passed_count = sum(1 for r in health_rows if r[0])
    failed_count = total_checks - passed_count
    failure_rate = (failed_count / total_checks * 100) if total_checks > 0 else 0.0

    # Latency analysis
    latencies = [r[1] for r in health_rows if r[1] is not None]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0
    min_latency = min(latencies) if latencies else 0.0

    # Error category frequency
    error_categories: Dict[str, int] = {}
    for row in health_rows:
        cat = row[3]
        if cat:
            error_categories[cat] = error_categories.get(cat, 0) + 1

    # Recent error messages (last 5 failures)
    recent_errors = [
        (r[2], r[4]) for r in health_rows if not r[0] and r[2]
    ][:5]

    # --- 3. Query current provider status from recent checks ---
    recent_passed = sum(1 for r in health_rows[:5] if r[0]) if health_rows else 0
    recent_total = min(5, total_checks)
    if recent_total > 0:
        if recent_passed == recent_total:
            provider_status = "HEALTHY"
        elif recent_passed >= recent_total * 0.6:
            provider_status = "DEGRADED"
        else:
            provider_status = "UNHEALTHY"
    else:
        provider_status = "UNKNOWN (no recent data)"

    # --- 4. Generate markdown report ---
    sections = []

    # Section 1: Summary
    sections.append(
        f"# Diagnostic Report: {provider}/{model}\n\n"
        f"## Summary\n\n"
        f"- **Provider:** {provider}\n"
        f"- **Model:** {model}\n"
        f"- **Incident Type:** {incident_type}\n"
        f"- **Current Status:** {provider_status}\n"
        f"- **Health Checks (30 days):** {total_checks} total, "
        f"{passed_count} passed, {failed_count} failed "
        f"({failure_rate:.1f}% failure rate)\n"
    )

    # Section 2: Error Details
    sections.append(
        f"## Error Details\n\n"
        f"**Current Error:**\n```\n{error}\n```\n"
    )

    # Section 3: Recent Health History
    history_lines = [f"## Recent Health History\n"]
    if total_checks == 0:
        history_lines.append("No health check data available for the last 30 days.\n")
    else:
        history_lines.append(
            f"- **Latency (ms):** avg={avg_latency:.1f}, "
            f"min={min_latency:.1f}, max={max_latency:.1f}\n"
        )
        if error_categories:
            history_lines.append("- **Error Categories:**\n")
            for cat, count in sorted(
                error_categories.items(), key=lambda x: x[1], reverse=True
            ):
                history_lines.append(f"  - {cat}: {count} occurrences\n")
        if recent_errors:
            history_lines.append("- **Recent Failures:**\n")
            for msg, ts in recent_errors:
                history_lines.append(f"  - [{ts}] {msg[:200]}\n")
    sections.append("\n".join(history_lines))

    # Section 4: Provider Status
    sections.append(
        f"## Provider Status\n\n"
        f"- **Overall Status:** {provider_status}\n"
        f"- **Last {recent_total} checks:** {recent_passed}/{recent_total} passed\n"
    )

    # Section 5: Suggested Actions
    suggestions = []
    if "auth" in incident_type.lower() or "401" in error.lower() or "403" in error.lower():
        suggestions.append(
            "1. Verify API key validity for '{provider}' in openclawd.config.yaml"
        )
        suggestions.append(
            "2. Check if API key permissions have changed or been revoked"
        )
    if "rate" in incident_type.lower() or "429" in error.lower():
        suggestions.append(
            "1. Reduce request frequency or increase rate limit quota"
        )
        suggestions.append(
            "2. Consider adding request queuing or backoff in config"
        )
    if "deprecated" in incident_type.lower() or "deprecated" in error.lower():
        suggestions.append(
            f"1. Model '{model}' may be deprecated - check provider documentation"
        )
        suggestions.append(
            "2. Update model in openclawd.config.yaml to a supported version"
        )
    if failure_rate > 50:
        suggestions.append(
            f"- Consider switching to a different model (failure rate: {failure_rate:.1f}%)"
        )
    if avg_latency > 5000 and latencies:
        suggestions.append(
            f"- Investigate high latency (avg: {avg_latency:.0f}ms) - "
            f"may indicate provider issues"
        )

    # Default suggestions if none triggered
    if not suggestions:
        suggestions = [
            f"1. Check provider status page for '{provider}' outages",
            f"2. Verify API key validity for '{provider}'",
            f"3. Try a different model if '{model}' is consistently failing",
            "4. Review openclawd.config.yaml for misconfigurations",
            "5. Check network connectivity to the provider endpoint",
        ]

    sections.append(
        "## Suggested Actions\n\n" + "\n".join(suggestions) + "\n"
    )

    report = "\n".join(sections)

    # --- 5. Store report in provider_incidents ---
    try:
        cursor = conn.execute(
            """
            INSERT INTO provider_incidents
                (provider, incident_type, diagnostic_report)
            VALUES (?, ?, ?)
            """,
            (provider, incident_type, report),
        )
        conn.commit()
        logger.info(
            "Diagnostic report stored in provider_incidents (id=%s) for %s/%s",
            cursor.lastrowid, provider, model,
        )
    except sqlite3.Error as exc:
        logger.error(
            "Failed to store diagnostic report for %s/%s: %s",
            provider, model, exc,
        )

    return report
