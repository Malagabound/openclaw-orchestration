"""Diagnostic agent for analyzing agent execution failures.

Provides DiagnosticInput and DiagnosticOutput dataclasses for structured
diagnostic LLM calls, and the diagnose_failure() function that makes a
lightweight LLM call to analyze non-transient errors.
See spec Appendix C.3 for schema definitions.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DiagnosticInput:
    """Structured input for the diagnostic agent LLM call.

    Contains everything the diagnostic agent needs to analyze a failure:
    task context, error details, evidence from the failed run, history
    of previous attempts, and known similar fixes from failure_memory.
    Fields match spec Appendix C.3.
    """
    # What was being attempted
    task_id: int
    task_title: str
    task_description: str
    task_domain: str
    assigned_agent: str

    # What failed
    error_code: str
    error_message: str
    error_category: str

    # Evidence
    raw_agent_output: Optional[str]         # What the agent produced (truncated to 2000 chars)
    tool_call_log: Optional[list]           # List of tool calls with results
    stop_reason: Optional[str]              # end_turn, tool_use, max_tokens
    tokens_used: int

    # History
    attempt_number: int
    previous_attempts: list = field(default_factory=list)   # List of {strategy, error_code, diagnostic_summary}

    # Known patterns
    similar_past_fixes: list = field(default_factory=list)  # From failure_memory


@dataclass
class DiagnosticOutput:
    """Structured output from the diagnostic agent LLM call.

    Contains the diagnosis: root cause analysis, recommended recovery
    strategy, specific fix instructions, and cycle detection flags.
    Fields match spec Appendix C.3.
    """
    root_cause: str
    root_cause_category: str                # tool_failure, output_format, task_ambiguity,
                                            # resource_limit, approach_wrong, unknown
    confidence: float                       # 0.0 - 1.0
    recommended_strategy: str               # fix_specific, rewrite_with_guidance, simplify,
                                            # decompose, escalate
    specific_fix: Optional[str]             # Detailed instructions for the agent
    tools_to_adjust: list = field(default_factory=list)     # Tools to use differently or avoid
    avoid_approaches: list = field(default_factory=list)    # Approaches that should not be repeated
    needs_human: bool = False
    human_action_needed: Optional[str] = None
    is_repeat_failure: bool = False
    cycle_detected: bool = False


# ── Defaults ────────────────────────────────────────────────────────
_DEFAULT_DIAGNOSTIC_MODEL = "claude-haiku-4-5"
_DEFAULT_MAX_INPUT_TOKENS = 4000
_DEFAULT_PROMPT_FILE = "prompts/diagnostic_sop.md"
_RAW_OUTPUT_TRUNCATE = 1000
_TOOL_LOG_MAX_ENTRIES = 10


def _get_recovery_config(config: Any) -> dict:
    """Extract recovery section from config dict or object with defaults."""
    if isinstance(config, dict):
        return config.get("recovery", {})
    return getattr(config, "recovery", {}) or {}


def _load_prompt_template(config: Any) -> str:
    """Load diagnostic_sop.md prompt template from disk.

    Resolves the path relative to the agent-dispatch directory.
    """
    recovery_cfg = _get_recovery_config(config)
    prompt_file = recovery_cfg.get("diagnostic_prompt_file", _DEFAULT_PROMPT_FILE)

    # Resolve relative to agent-dispatch/ directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prompt_path = os.path.join(base_dir, prompt_file)

    with open(prompt_path, "r") as f:
        return f.read()


def _truncate_for_diagnosis(diagnostic_input: DiagnosticInput) -> DiagnosticInput:
    """Apply truncation to keep diagnostic prompt within token budget.

    Truncation order per spec:
    1. tool_call_log to last 10 entries
    2. raw_output to 1000 chars
    3. previous_attempts to 1-line summaries
    """
    # Truncate tool_call_log to last N entries
    tool_log = diagnostic_input.tool_call_log
    if tool_log and len(tool_log) > _TOOL_LOG_MAX_ENTRIES:
        tool_log = tool_log[-_TOOL_LOG_MAX_ENTRIES:]

    # Truncate raw_agent_output
    raw_output = diagnostic_input.raw_agent_output
    if raw_output and len(raw_output) > _RAW_OUTPUT_TRUNCATE:
        raw_output = raw_output[:_RAW_OUTPUT_TRUNCATE] + "...[truncated]"

    # Truncate previous_attempts to 1-line summaries
    prev_attempts = diagnostic_input.previous_attempts
    if prev_attempts:
        prev_attempts = [
            {
                "attempt": a.get("attempt", "?"),
                "strategy": a.get("strategy", "unknown"),
                "error_code": a.get("error_code", "unknown"),
                "summary": str(a.get("diagnostic_summary", ""))[:100],
            }
            for a in prev_attempts
        ]

    # Return a new DiagnosticInput with truncated fields
    return DiagnosticInput(
        task_id=diagnostic_input.task_id,
        task_title=diagnostic_input.task_title,
        task_description=diagnostic_input.task_description,
        task_domain=diagnostic_input.task_domain,
        assigned_agent=diagnostic_input.assigned_agent,
        error_code=diagnostic_input.error_code,
        error_message=diagnostic_input.error_message,
        error_category=diagnostic_input.error_category,
        raw_agent_output=raw_output,
        tool_call_log=tool_log,
        stop_reason=diagnostic_input.stop_reason,
        tokens_used=diagnostic_input.tokens_used,
        attempt_number=diagnostic_input.attempt_number,
        previous_attempts=prev_attempts,
        similar_past_fixes=diagnostic_input.similar_past_fixes,
    )


def _render_prompt(template: str, di: DiagnosticInput) -> str:
    """Inject DiagnosticInput fields into prompt template."""
    # Format tool call log as readable summary
    tool_summary = "None"
    if di.tool_call_log:
        lines = []
        for tc in di.tool_call_log:
            tool_name = tc.get("name", tc.get("tool", "unknown"))
            result_preview = str(tc.get("result", ""))[:200]
            lines.append(f"- {tool_name}: {result_preview}")
        tool_summary = "\n".join(lines)

    # Format previous attempts
    prev_summary = "None"
    if di.previous_attempts:
        lines = []
        for a in di.previous_attempts:
            lines.append(
                f"- Attempt {a.get('attempt', '?')}: "
                f"strategy={a.get('strategy', '?')}, "
                f"error={a.get('error_code', '?')}, "
                f"{a.get('summary', '')}"
            )
        prev_summary = "\n".join(lines)

    # Format similar past fixes
    fixes_summary = "None"
    if di.similar_past_fixes:
        lines = []
        for fix in di.similar_past_fixes:
            lines.append(
                f"- error_code={fix.get('error_code', '?')}, "
                f"resolution={fix.get('resolution_summary', '?')}, "
                f"tier={fix.get('recovery_tier', '?')}"
            )
        fixes_summary = "\n".join(lines)

    replacements = {
        "{{task_title}}": di.task_title,
        "{{task_description}}": di.task_description,
        "{{task_domain}}": di.task_domain,
        "{{assigned_agent}}": di.assigned_agent,
        "{{error_code}}": di.error_code,
        "{{error_category}}": di.error_category,
        "{{error_message}}": di.error_message,
        "{{attempt_number}}": str(di.attempt_number),
        "{{raw_agent_output}}": di.raw_agent_output or "None",
        "{{tool_call_summary}}": tool_summary,
        "{{stop_reason}}": di.stop_reason or "None",
        "{{tokens_used}}": str(di.tokens_used),
        "{{previous_attempts}}": prev_summary,
        "{{similar_past_fixes}}": fixes_summary,
    }

    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)

    return rendered


def _parse_diagnostic_output(response_text: str) -> DiagnosticOutput:
    """Parse LLM response JSON into DiagnosticOutput dataclass.

    Handles JSON wrapped in markdown fences and missing fields.
    """
    text = response_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    data = json.loads(text)

    return DiagnosticOutput(
        root_cause=data.get("root_cause", "Unable to determine root cause"),
        root_cause_category=data.get("root_cause_category", "unknown"),
        confidence=float(data.get("confidence", 0.3)),
        recommended_strategy=data.get("recommended_strategy", "fix_specific"),
        specific_fix=data.get("specific_fix"),
        tools_to_adjust=data.get("tools_to_adjust", []),
        avoid_approaches=data.get("avoid_approaches", []),
        needs_human=bool(data.get("needs_human", False)),
        human_action_needed=data.get("human_action_needed"),
        is_repeat_failure=bool(data.get("is_repeat_failure", False)),
        cycle_detected=bool(data.get("cycle_detected", False)),
    )


def _default_diagnosis(error_code: str, error_message: str) -> DiagnosticOutput:
    """Return a low-confidence default diagnosis when LLM call or parsing fails."""
    return DiagnosticOutput(
        root_cause=f"Diagnostic agent could not analyze: {error_message}",
        root_cause_category="unknown",
        confidence=0.1,
        recommended_strategy="fix_specific",
        specific_fix=None,
        tools_to_adjust=[],
        avoid_approaches=[],
        needs_human=False,
        human_action_needed=None,
        is_repeat_failure=False,
        cycle_detected=False,
    )


def _get_diagnostic_provider(config: Any) -> Any:
    """Get an LLM provider configured for diagnostic calls.

    Uses config.recovery.diagnostic_model (default claude-haiku-4-5).
    Falls back to primary provider if diagnostic_model not configured.
    """
    from ..provider_registry import get_provider, ProviderRegistryError

    recovery_cfg = _get_recovery_config(config)
    diagnostic_model = recovery_cfg.get("diagnostic_model", _DEFAULT_DIAGNOSTIC_MODEL)

    config_dict = config if isinstance(config, dict) else getattr(config, "_raw", config)
    if not isinstance(config_dict, dict):
        config_dict = {}

    # Build a config dict with the diagnostic model override
    diag_config = dict(config_dict)
    if "provider" in diag_config:
        diag_provider = dict(diag_config["provider"])
        diag_provider["model"] = diagnostic_model
        diag_config["provider"] = diag_provider

    try:
        return get_provider(diag_config)
    except ProviderRegistryError:
        # Fall back to primary provider
        return get_provider(config_dict)


def diagnose_failure(
    diagnostic_input: DiagnosticInput,
    config: Any,
) -> DiagnosticOutput:
    """Make a lightweight LLM call to diagnose a non-transient agent failure.

    Loads the diagnostic_sop.md prompt template, injects the DiagnosticInput
    context, calls the diagnostic model (default claude-haiku-4-5), and parses
    the response into a DiagnosticOutput.

    Args:
        diagnostic_input: Structured input with task context, error details,
            evidence, previous attempts, and similar past fixes.
        config: Config dict or object with recovery section.

    Returns:
        DiagnosticOutput with root cause analysis and recovery recommendations.
        On LLM or parse failure, returns a low-confidence default diagnosis.
    """
    from ..llm_provider import Message

    # Apply truncation to stay within token budget
    truncated_input = _truncate_for_diagnosis(diagnostic_input)

    # Load and render prompt template
    try:
        template = _load_prompt_template(config)
    except (FileNotFoundError, OSError):
        return _default_diagnosis(
            diagnostic_input.error_code,
            f"Could not load diagnostic prompt template: {diagnostic_input.error_message}",
        )

    rendered_prompt = _render_prompt(template, truncated_input)

    # Get provider configured for diagnostic model
    try:
        provider = _get_diagnostic_provider(config)
    except Exception:
        return _default_diagnosis(
            diagnostic_input.error_code,
            f"Could not initialize diagnostic provider: {diagnostic_input.error_message}",
        )

    # Make LLM call
    try:
        messages = [
            Message(role="user", content=rendered_prompt),
        ]
        response = provider.complete(messages, max_tokens=2048)
        response_text = response.content
    except Exception:
        return _default_diagnosis(
            diagnostic_input.error_code,
            f"Diagnostic LLM call failed: {diagnostic_input.error_message}",
        )

    # Parse response into DiagnosticOutput
    try:
        return _parse_diagnostic_output(response_text)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return _default_diagnosis(
            diagnostic_input.error_code,
            f"Could not parse diagnostic response: {diagnostic_input.error_message}",
        )
