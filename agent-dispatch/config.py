"""
OpenClawd Agent Dispatch System - Configuration Module

Defines all constants, AGENT_SKILLS mapping, and config loader
with 5-tier path resolution order.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Timing Constants ──────────────────────────────────────────────

POLL_INTERVAL_SECONDS: int = 30
LEASE_SECONDS: int = 300
TIMEOUT_SECONDS: int = 1800

# ── Concurrency Constants ────────────────────────────────────────

MAX_CONCURRENT_AGENTS: int = 3
MAX_TOOL_ITERATIONS: int = 50

# ── Legacy Agent Name Mapping ────────────────────────────────────
# Maps old agent names to new names for backward compatibility with
# tasks already in the database that use the old naming scheme.
LEGACY_AGENT_NAMES: Dict[str, str] = {
    "rex": "research",
    "pixel": "product",
    "scout": "meta",
    "keeper": "ops",
    "nora": "comms",
}


def normalize_agent_name(name: Optional[str]) -> str:
    """Resolve legacy agent names to current names.

    Returns the normalized name, or 'research' as a fallback for None.
    """
    if name is None:
        return "research"
    return LEGACY_AGENT_NAMES.get(name, name)


# ── Agent-to-Skills Mapping ──────────────────────────────────────
# Maps agent names to lists of skill directories they can access.

AGENT_SKILLS: Dict[str, List[str]] = {
    "research": [
        "deep-research",
        "deep-research-pro",
        "product-research",
        "argos-product-research",
        "digital-product-research",
        "competitive-intelligence-market-research",
        "business-acquisition-research",
        "software-subscription-research",
        "firecrawl-search",
        "tavily-search",
    ],
    "product": [
        "digital-product-creator",
        "clawver-digital-products",
        "microsaas-factory",
        "product-validation",
        "saas-idea-discovery",
        "saas",
        "pricing",
    ],
    "comms": [
        "email-agent",
        "email-manager-lite",
        "gmail",
        "himalaya",
        "telegram-group-setup",
        "twitter",
    ],
    "ops": [
        "calendar",
        "quickbooks",
        "subscriptions",
        "supabase",
        "postgres",
        "obsidian",
    ],
    "meta": [
        "self-evolving-skill",
        "self-improving-agent-1-0-2",
        "self-reflection",
        "reflect-learn",
        "recursive-self-improvement",
        "sub-agent-design",
        "mcp-validation",
    ],
    "content": [
        "humanizer",
        "youtube-transcript",
        "soulcraft",
    ],
    "taskr": [
        "taskr",
        "dex",
        "qmd",
    ],
    "security": [
        "security-sentinel",
    ],
    "memory": [
        "supermemory",
    ],
    "haven": [],
    "vault": [],
    "george": [],
}

# ── Default DB Path ──────────────────────────────────────────────

DEFAULT_DB_PATH: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "orchestrator-dashboard",
    "orchestrator-dashboard",
    "coordination.db",
)

# ── Config File Name ─────────────────────────────────────────────

CONFIG_FILENAME: str = "openclawd.config.yaml"


def resolve_config_path(cli_flag: Optional[str] = None) -> Optional[str]:
    """
    Resolve config file path using 5-tier resolution order:
      1. --config CLI flag value
      2. OPENCLAWD_CONFIG environment variable
      3. ./openclawd.config.yaml (current working directory)
      4. agent-dispatch/openclawd.config.yaml (project dir)
      5. ~/.openclawd/openclawd.config.yaml (home dir)

    Returns the path to the first config file found, or None if
    no config file exists at any location.
    """
    candidates: List[str] = []

    # Tier 1: CLI flag
    if cli_flag:
        candidates.append(cli_flag)

    # Tier 2: Environment variable
    env_path = os.environ.get("OPENCLAWD_CONFIG")
    if env_path:
        candidates.append(env_path)

    # Tier 3: Current working directory
    candidates.append(os.path.join(os.getcwd(), CONFIG_FILENAME))

    # Tier 4: Project directory (agent-dispatch/)
    project_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(project_dir, CONFIG_FILENAME))

    # Tier 5: Home directory
    home_dir = os.path.expanduser("~")
    candidates.append(os.path.join(home_dir, ".openclawd", CONFIG_FILENAME))

    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


def ensure_config() -> None:
    """
    Ensure a config file exists, creating a default template if needed.

    On first run, checks for config file in resolution order.
    If no config found, creates ~/.openclawd/ directory and copies
    the template openclawd.config.yaml to ~/.openclawd/openclawd.config.yaml.

    Does not overwrite existing config files.
    """
    # Check for --config in sys.argv
    cli_flag = None
    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            cli_flag = sys.argv[i + 1]
            break

    # Check if any config exists in resolution order
    existing_config = resolve_config_path(cli_flag=cli_flag)

    if existing_config is not None:
        # Config already exists, nothing to do
        return

    # No config found - create default template at ~/.openclawd/openclawd.config.yaml
    home_dir = os.path.expanduser("~")
    config_dir = os.path.join(home_dir, ".openclawd")
    target_config_path = os.path.join(config_dir, CONFIG_FILENAME)

    # Create ~/.openclawd/ directory if it doesn't exist
    os.makedirs(config_dir, exist_ok=True)

    # Get path to the template file (in the same directory as this config.py)
    template_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        CONFIG_FILENAME
    )

    # Check if template exists
    if not os.path.isfile(template_path):
        # Template doesn't exist - this shouldn't happen in normal operation
        # but we handle it gracefully
        return

    # Copy template to ~/.openclawd/openclawd.config.yaml
    shutil.copy2(template_path, target_config_path)

    # Print message to user
    print(f"Config template created at ~/.openclawd/openclawd.config.yaml. Please edit and add your API keys.")


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.

    Args:
        config_path: Explicit path to config file. If None, uses
                     resolve_config_path() to find one.

    Returns:
        Configuration dict. Returns empty dict if no config file found
        or if PyYAML is not installed.
    """
    if config_path is None:
        # Check for --config in sys.argv
        cli_flag = None
        for i, arg in enumerate(sys.argv):
            if arg == "--config" and i + 1 < len(sys.argv):
                cli_flag = sys.argv[i + 1]
                break
        config_path = resolve_config_path(cli_flag=cli_flag)

    if config_path is None:
        return {}

    try:
        import yaml
    except ImportError:
        return {}

    with open(config_path, "r") as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}

    return data


# ── Recovery Configuration Defaults ─────────────────────────────
# All keys from spec Appendix E with their default values.

RECOVERY_DEFAULTS: Dict[str, Any] = {
    # General limits
    "max_recovery_attempts": 5,
    "max_recovery_time_seconds": 1800,
    "max_concurrent_recoveries": 3,
    "recovery_timeout_per_attempt": 600,
    # Diagnostic Agent
    "diagnostic_model": "claude-haiku-4-5",
    "diagnostic_max_input_tokens": 4000,
    "diagnostic_prompt_file": "prompts/diagnostic_sop.md",
    # Budget
    "recovery_budget_ratio": 0.04,
    "recovery_budget_cap_usd": 2.00,
    # Truncation limits
    "raw_output_max_chars": 10000,
    "diagnostic_context_chars": 2000,
    "recovery_prompt_context_chars": 500,
    "error_message_max_chars": 200,
    # Confidence threshold
    "min_confidence_score": 0.3,
    # Systemic failure detection
    "systemic_failure_threshold_count": 3,
    "systemic_failure_window_minutes": 10,
    # Escalation
    "max_escalations_per_hour": 5,
    "escalation_cooldown_seconds": 300,
    # Retention
    "failure_memory_retention_days": 90,
    "recovery_events_retention_days": 90,
}


def get_recovery_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the recovery section from config with fallback to defaults.

    Reads config["recovery"] and merges with RECOVERY_DEFAULTS so that
    any missing key falls back to its default value.

    Args:
        config: Full config dict from load_config().

    Returns:
        Recovery config dict with all keys guaranteed present.
    """
    user_recovery = config.get("recovery", {})
    if not isinstance(user_recovery, dict):
        user_recovery = {}
    merged = dict(RECOVERY_DEFAULTS)
    merged.update(user_recovery)
    return merged


# ── SDK Module Mapping ──────────────────────────────────────────
# Maps provider names to their SDK import module names.
_SDK_MODULES: Dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "google.generativeai",
    "ollama": "ollama",
}


def validate_config(config_dict: Dict[str, Any], db_path: str) -> List[str]:
    """Validate config before dispatch starts.

    Checks API key env vars, SDK imports, DB connectivity, and numeric
    ranges. Returns a list of error strings (empty if all valid).

    Args:
        config_dict: Parsed openclawd.config.yaml as a dict.
        db_path: Path to the SQLite coordination database.

    Returns:
        List of error description strings. Empty list means valid.
    """
    import sqlite3

    errors: List[str] = []

    # ── 1. Check api_key_env values exist in os.environ ──────────
    # Check primary provider
    provider_section = config_dict.get("provider", {})
    if isinstance(provider_section, dict):
        api_key_env = provider_section.get("api_key_env")
        if api_key_env and not os.environ.get(api_key_env):
            errors.append(
                f"Environment variable '{api_key_env}' (provider.api_key_env) is not set"
            )

    # Check fallback provider
    fallback_section = config_dict.get("fallback", {})
    if isinstance(fallback_section, dict):
        fallback_key_env = fallback_section.get("api_key_env")
        if fallback_key_env and not os.environ.get(fallback_key_env):
            errors.append(
                f"Environment variable '{fallback_key_env}' (fallback.api_key_env) is not set"
            )

    # ── 2. Attempt import of SDK modules ─────────────────────────
    for provider_name, module_name in _SDK_MODULES.items():
        try:
            __import__(module_name)
        except ImportError:
            errors.append(
                f"SDK module '{module_name}' for provider '{provider_name}' is not installed"
            )

    # ── 3. Test sqlite3.connect() to db_path ─────────────────────
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
    except (sqlite3.Error, OSError) as exc:
        errors.append(f"Cannot connect to database at '{db_path}': {exc}")

    # ── 4. Validate numeric ranges ───────────────────────────────
    _check_positive_int(config_dict, "max_concurrent_agents", errors)
    _check_non_negative_float(config_dict, "daily_budget_usd", errors)
    _check_non_negative_float(config_dict, "alert_threshold_usd", errors)
    _check_positive_int(config_dict, "max_tool_iterations", errors)
    _check_positive_int(config_dict, "agent_timeout_seconds", errors)
    _check_positive_int(config_dict, "dispatch_lease_seconds", errors)
    _check_positive_int(config_dict, "max_tokens_per_task", errors)
    _check_positive_int(config_dict, "health_check_interval_hours", errors)

    # Retention days must all be > 0
    retention = config_dict.get("retention", {})
    if isinstance(retention, dict):
        for key, value in retention.items():
            if isinstance(value, (int, float)) and value <= 0:
                errors.append(
                    f"retention.{key} must be > 0, got {value}"
                )

    return errors


def _check_positive_int(
    config: Dict[str, Any], key: str, errors: List[str]
) -> None:
    """Append error if config[key] exists but is not a positive number."""
    value = config.get(key)
    if value is not None and isinstance(value, (int, float)) and value <= 0:
        errors.append(f"'{key}' must be > 0, got {value}")


def _check_non_negative_float(
    config: Dict[str, Any], key: str, errors: List[str]
) -> None:
    """Append error if config[key] exists but is negative."""
    value = config.get(key)
    if value is not None and isinstance(value, (int, float)) and value < 0:
        errors.append(f"'{key}' must be >= 0, got {value}")
