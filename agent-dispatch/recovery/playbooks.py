"""Deterministic recovery playbooks for known error scenarios.

Each playbook replaces ONLY the STRATEGIZE step (step 5) of the recovery
pipeline by producing a RecoveryStrategy with pre-defined prompt modifications
and constraints. All other pipeline stages (DIAGNOSE, COMPENSATE, EXECUTE,
VERIFY, LEARN) still run normally.

See spec Section 7 for the 7 playbook scenario descriptions and Appendix C.6
for the PlaybookStep/Playbook dataclass definitions.
"""

from dataclasses import dataclass, field
from typing import Optional

from .error_classifier import ErrorCategory
from .strategy_selector import RecoveryStrategy


@dataclass
class PlaybookStep:
    """A single step in a deterministic recovery playbook."""
    stage: str                              # Pipeline stage: classify, diagnose, compensate, strategize, execute
    action: str                             # What to do (e.g., "retry_with_backoff", "switch_provider", "escalate")
    parameters: dict = field(default_factory=dict)  # Stage-specific parameters
    condition: Optional[str] = None         # When this step applies, or None for always


@dataclass
class Playbook:
    """A deterministic recovery sequence for a specific error code."""
    error_code: str                         # The error code this playbook handles
    steps: list[PlaybookStep] = field(default_factory=list)  # Ordered steps to execute

    def select_strategy(
        self,
        attempt: int,
        error_code: str,
        classification: ErrorCategory,
    ) -> RecoveryStrategy:
        """Select the appropriate RecoveryStrategy for the given attempt number.

        Uses the playbook's deterministic steps to produce prompt modifications
        and constraints instead of the generic strategy ladder. The rest of the
        pipeline (DIAGNOSE, COMPENSATE, EXECUTE, VERIFY, LEARN) still runs
        normally -- only the STRATEGIZE step is replaced.

        Args:
            attempt: Current recovery attempt number (1-based).
            error_code: The canonical error code being recovered.
            classification: ErrorCategory from the taxonomy.

        Returns:
            RecoveryStrategy with playbook-specific prompt_modifications and constraints.
        """
        # Find the strategize step for this attempt number
        strategize_steps = [s for s in self.steps if s.stage == "strategize"]

        # Use attempt number to index into strategize steps (0-based)
        step_idx = min(attempt - 1, len(strategize_steps) - 1)
        if step_idx < 0 or not strategize_steps:
            # No strategize steps defined; fall back to escalate
            return RecoveryStrategy(
                strategy_name="escalate",
                tier=5,
                strategy_description=f"Playbook {self.error_code} has no strategy for attempt {attempt}.",
                is_terminal=True,
            )

        step = strategize_steps[step_idx]
        params = step.parameters

        # Determine if this is terminal
        is_terminal = step.action in ("escalate", "decompose")
        # Determine tier from attempt or params
        tier = params.get("tier", min(attempt, 5))

        return RecoveryStrategy(
            strategy_name=params.get("strategy_name", step.action),
            tier=tier,
            strategy_description=params.get("description", step.action),
            constraints=params.get("constraints", []),
            prompt_modifications=params.get("prompt_modifications", {}),
            scope_reduction=params.get("scope_reduction"),
            is_terminal=is_terminal,
        )


# ---------------------------------------------------------------------------
# Playbook registry
# ---------------------------------------------------------------------------

_PLAYBOOKS: dict[str, Playbook] = {}


def has_playbook(error_code: str) -> bool:
    """Check if a deterministic playbook exists for the given error code."""
    return error_code in _PLAYBOOKS


def get_playbook(error_code: str) -> Playbook:
    """Get the playbook for the given error code.

    Raises KeyError if no playbook exists for the error code.
    """
    return _PLAYBOOKS[error_code]


# ---------------------------------------------------------------------------
# Playbook 1: SEARCH_API_UNAVAILABLE (spec Section 7.1)
# Web search API down with backoff retries
# ---------------------------------------------------------------------------
_PLAYBOOKS["SEARCH_API_UNAVAILABLE"] = Playbook(
    error_code="SEARCH_API_UNAVAILABLE",
    steps=[
        PlaybookStep(
            stage="strategize",
            action="retry_with_backoff",
            parameters={
                "strategy_name": "fix_specific",
                "tier": 1,
                "description": (
                    "Web search API returned an error. Retrying with backoff. "
                    "The search executor will attempt its full fallback chain "
                    "(SerpAPI -> Brave Search -> DuckDuckGo)."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "backoff_seconds": 30,
                },
                "constraints": [],
            },
            condition=None,
        ),
        PlaybookStep(
            stage="strategize",
            action="retry_with_backoff",
            parameters={
                "strategy_name": "fix_specific",
                "tier": 1,
                "description": (
                    "Search API still unavailable after first retry. "
                    "Retrying with longer backoff."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "backoff_seconds": 60,
                },
                "constraints": [],
            },
            condition="if first retry failed",
        ),
        PlaybookStep(
            stage="strategize",
            action="retry_alternative",
            parameters={
                "strategy_name": "rewrite_with_diagnosis",
                "tier": 2,
                "description": (
                    "Search API unavailable after multiple retries. "
                    "Try different search terms or use database_query "
                    "to search local knowledge base instead."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "inject_diagnosis": True,
                    "suggest_alternative_tools": True,
                },
                "constraints": [
                    "Web search API is currently unavailable",
                    "Try completely different search terms or strategies",
                    "Consider using database_query for local knowledge base",
                ],
            },
            condition="if backoff retries exhausted",
        ),
        PlaybookStep(
            stage="strategize",
            action="escalate",
            parameters={
                "strategy_name": "escalate",
                "tier": 5,
                "description": (
                    "Search APIs unavailable after all retries. "
                    "Check SerpAPI/Brave API status. DuckDuckGo fallback "
                    "also failing. Tasks will retry when APIs recover."
                ),
                "prompt_modifications": {},
                "constraints": [],
            },
            condition="if all retries exhausted",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Playbook 2: TOOL_CALL_MALFORMED (spec Section 7.2)
# Malformed LLM tool calls with schema examples
# Maps to RESULT_PARSE_FAILED or TOOL_RESULT_MALFORMED depending on sub-type
# ---------------------------------------------------------------------------
_PLAYBOOKS["TOOL_RESULT_MALFORMED"] = Playbook(
    error_code="TOOL_RESULT_MALFORMED",
    steps=[
        PlaybookStep(
            stage="strategize",
            action="fix_with_schema",
            parameters={
                "strategy_name": "fix_specific",
                "tier": 1,
                "description": (
                    "Your previous tool call was malformed. "
                    "Review the error details and retry with valid arguments "
                    "matching the tool's expected schema."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "inject_tool_schema": True,
                },
                "constraints": [
                    "Ensure tool call arguments match the expected schema exactly",
                    "Validate JSON structure before making tool calls",
                ],
            },
            condition=None,
        ),
        PlaybookStep(
            stage="strategize",
            action="rewrite_with_diagnosis",
            parameters={
                "strategy_name": "rewrite_with_diagnosis",
                "tier": 2,
                "description": (
                    "Tool call malformation persists. Review diagnostic analysis "
                    "and use a completely different approach to tool usage."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "inject_diagnosis": True,
                    "suggest_provider_fallback": True,
                },
                "constraints": [
                    "Use simple, well-formed JSON for all tool arguments",
                    "Avoid complex nested structures in tool calls",
                ],
            },
            condition="if same provider fails again",
        ),
        PlaybookStep(
            stage="strategize",
            action="escalate",
            parameters={
                "strategy_name": "escalate",
                "tier": 5,
                "description": (
                    "Tool call malformation persists across retry attempts. "
                    "Provider tool-calling reliability issue detected."
                ),
                "prompt_modifications": {},
                "constraints": [],
            },
            condition="if fallback also produces malformed calls",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Playbook 3: RESULT_SCHEMA_INVALID (spec Section 7.3)
# AgentResult validation failure with format enforcement
# ---------------------------------------------------------------------------
_PLAYBOOKS["RESULT_SCHEMA_INVALID"] = Playbook(
    error_code="RESULT_SCHEMA_INVALID",
    steps=[
        PlaybookStep(
            stage="strategize",
            action="fix_with_format",
            parameters={
                "strategy_name": "fix_specific",
                "tier": 1,
                "description": (
                    "Your response was received but could not be parsed. "
                    "Your response must include an <agent-result> block with "
                    "valid JSON containing: status (completed|blocked|needs_input|failed), "
                    "deliverable_summary (string), deliverable_content (string). "
                    "Please try again with correct format."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "reinforce_sop_format": True,
                },
                "constraints": [
                    "Response MUST include a valid <agent-result> JSON block",
                    "Status must be one of: completed, blocked, needs_input, failed",
                    "Include both deliverable_summary and deliverable_content fields",
                ],
            },
            condition=None,
        ),
        PlaybookStep(
            stage="strategize",
            action="rewrite_with_diagnosis",
            parameters={
                "strategy_name": "rewrite_with_diagnosis",
                "tier": 2,
                "description": (
                    "Schema validation still failing. Diagnostic analysis provided. "
                    "If output is being truncated, keep deliverable under 10000 characters."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "inject_diagnosis": True,
                    "reinforce_sop_format": True,
                },
                "constraints": [
                    "Keep deliverable_content under 10000 characters",
                    "Response MUST include a valid <agent-result> JSON block",
                    "Do not include any text after the closing </agent-result> tag",
                ],
            },
            condition="if same parse error on retry",
        ),
        PlaybookStep(
            stage="strategize",
            action="simplify_output",
            parameters={
                "strategy_name": "simplify",
                "tier": 3,
                "description": (
                    "Produce the SHORTEST possible valid response. "
                    "Your ENTIRE response should be the <agent-result> block "
                    "and nothing else. Focus on status and deliverable_summary only."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "simplify_mode": True,
                    "reinforce_sop_format": True,
                },
                "constraints": [
                    "Your ENTIRE response must be ONLY the <agent-result> block",
                    "Include only status and deliverable_summary at minimum",
                    "Produce the shortest possible valid response",
                ],
                "scope_reduction": (
                    "Focus only on producing a valid <agent-result> block. "
                    "Minimize deliverable_content length."
                ),
            },
            condition="if validation still failing",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Playbook 4: TOOL_LOOP_DETECTED (spec Section 7.4)
# Agent stuck in tool call loop with tool constraints
# ---------------------------------------------------------------------------
_PLAYBOOKS["TOOL_LOOP_DETECTED"] = Playbook(
    error_code="TOOL_LOOP_DETECTED",
    steps=[
        PlaybookStep(
            stage="strategize",
            action="constrain_tools",
            parameters={
                "strategy_name": "fix_specific",
                "tier": 1,
                "description": (
                    "Your previous attempt got stuck in a tool call loop, "
                    "repeating the same tool calls without making progress. "
                    "Take a completely different approach and avoid repeating "
                    "the same tool calls."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "inject_tool_call_history": True,
                    "max_tool_iterations": 15,
                },
                "constraints": [
                    "Do NOT repeat the same tool call with the same arguments",
                    "If a tool call returns no useful results, try a different approach",
                    "Plan your approach before calling any tools",
                ],
            },
            condition=None,
        ),
        PlaybookStep(
            stage="strategize",
            action="strict_tool_limit",
            parameters={
                "strategy_name": "rewrite_with_diagnosis",
                "tier": 2,
                "description": (
                    "Tool loop detected again. Strict tool call limit enforced. "
                    "Plan your approach carefully before making any tool calls."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "inject_diagnosis": True,
                    "max_tool_iterations": 10,
                },
                "constraints": [
                    "You have a maximum of 10 tool calls total",
                    "Plan your entire approach BEFORE calling any tools",
                    "Do NOT call the same tool with the same arguments twice",
                    "If a search returns no results, do NOT retry it",
                ],
            },
            condition="if loop recurs on first retry",
        ),
        PlaybookStep(
            stage="strategize",
            action="escalate",
            parameters={
                "strategy_name": "escalate",
                "tier": 5,
                "description": (
                    "Agent stuck in tool call loop after multiple constrained retries. "
                    "Escalating to operator."
                ),
                "prompt_modifications": {},
                "constraints": [],
            },
            condition="if loop persists after constrained retry",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Playbook 5: STALE_DATA (spec Section 7.5)
# Task keeps failing despite completed dependencies
# Uses STALE_DATA error code (closest match for dependency-related failures)
# ---------------------------------------------------------------------------
_PLAYBOOKS["STALE_DATA"] = Playbook(
    error_code="STALE_DATA",
    steps=[
        PlaybookStep(
            stage="strategize",
            action="recheck_dependencies",
            parameters={
                "strategy_name": "rewrite_with_diagnosis",
                "tier": 2,
                "description": (
                    "This task has failed despite completed dependencies. "
                    "Diagnostic analysis will determine if dependency data is usable "
                    "or if the task description needs clarification. "
                    "Focus on the most literal interpretation of the task."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "inject_diagnosis": True,
                    "recheck_dependency_data": True,
                },
                "constraints": [
                    "Verify that dependency data from upstream tasks is still valid",
                    "Focus on the most literal interpretation of the task title",
                    "Ignore edge cases and produce a minimal valid deliverable",
                ],
            },
            condition=None,
        ),
        PlaybookStep(
            stage="strategize",
            action="decompose",
            parameters={
                "strategy_name": "decompose",
                "tier": 4,
                "description": (
                    "Task keeps failing despite completed dependencies. "
                    "Consider decomposing this task or revising the task description. "
                    "Use 'openclawd pipeline create' to split the task."
                ),
                "prompt_modifications": {
                    "decomposition_suggestion": (
                        "This task may be too complex for a single agent execution. "
                        "Consider splitting into smaller sub-tasks that can each "
                        "independently verify their dependency data."
                    ),
                },
                "constraints": [],
            },
            condition="if recheck fails",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Playbook 6: COMPLETION_SEQUENCE_STUCK (spec Section 7.6)
# Supervisor daemon crash recovery
# Maps to COMPLETION_SEQUENCE_STUCK which handles supervisor-level failures
# ---------------------------------------------------------------------------
_PLAYBOOKS["COMPLETION_SEQUENCE_STUCK"] = Playbook(
    error_code="COMPLETION_SEQUENCE_STUCK",
    steps=[
        PlaybookStep(
            stage="strategize",
            action="state_recovery",
            parameters={
                "strategy_name": "fix_specific",
                "tier": 1,
                "description": (
                    "Task completion sequence was stuck, possibly due to supervisor "
                    "crash or restart. State has been recovered. Retrying task "
                    "completion from clean state."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "clean_state_retry": True,
                },
                "constraints": [
                    "Previous task state may be inconsistent",
                    "Re-verify all outputs before claiming completion",
                ],
            },
            condition=None,
        ),
        PlaybookStep(
            stage="strategize",
            action="retry_with_reset",
            parameters={
                "strategy_name": "fix_specific",
                "tier": 1,
                "description": (
                    "Completion sequence still stuck after state recovery. "
                    "Retrying with full lease and state reset."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "clean_state_retry": True,
                    "full_reset": True,
                },
                "constraints": [
                    "Start from scratch — do not rely on any prior partial state",
                ],
            },
            condition="if first recovery attempt fails",
        ),
        PlaybookStep(
            stage="strategize",
            action="escalate",
            parameters={
                "strategy_name": "escalate",
                "tier": 5,
                "description": (
                    "Completion sequence stuck after multiple recovery attempts. "
                    "Possible persistent state corruption. Escalating to operator."
                ),
                "prompt_modifications": {},
                "constraints": [],
            },
            condition="if state recovery fails repeatedly",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Playbook 7: SYSTEMIC_FAILURE (spec Section 7.7)
# Multiple tasks fail with same error - system-level alert and deferral
# Note: This is not a standard ERROR_TAXONOMY code but is used by the
# systemic failure detection logic in failure_memory/recovery_pipeline
# ---------------------------------------------------------------------------
_PLAYBOOKS["PROVIDER_5XX"] = Playbook(
    error_code="PROVIDER_5XX",
    steps=[
        PlaybookStep(
            stage="strategize",
            action="defer_for_provider_recovery",
            parameters={
                "strategy_name": "fix_specific",
                "tier": 1,
                "description": (
                    "Provider is experiencing errors (5xx). Deferring retry "
                    "to allow provider-level self-healing to complete. "
                    "The health monitoring system will trigger provider fallback "
                    "if needed."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "backoff_seconds": 120,
                    "defer_for_provider": True,
                },
                "constraints": [
                    "Provider may be experiencing an outage",
                    "Retry will use fallback provider if primary is still down",
                ],
            },
            condition=None,
        ),
        PlaybookStep(
            stage="strategize",
            action="retry_with_fallback",
            parameters={
                "strategy_name": "rewrite_with_diagnosis",
                "tier": 2,
                "description": (
                    "Provider still failing. Health system should have activated "
                    "fallback provider. Retrying with diagnosis."
                ),
                "prompt_modifications": {
                    "inject_error_feedback": True,
                    "inject_diagnosis": True,
                    "backoff_seconds": 300,
                },
                "constraints": [],
            },
            condition="if provider still failing after deferral",
        ),
        PlaybookStep(
            stage="strategize",
            action="escalate",
            parameters={
                "strategy_name": "escalate",
                "tier": 5,
                "description": (
                    "Provider outage persists. Multiple tasks affected. "
                    "Escalating with systemic failure alert."
                ),
                "prompt_modifications": {},
                "constraints": [],
            },
            condition="if provider outage persists",
        ),
    ],
)
