"""Stage 5 STRATEGIZE: Select recovery strategy from the 5-tier ladder.

Provides the RecoveryStrategy dataclass and select_strategy() function that
chooses the appropriate recovery approach based on attempt number, error
classification, and diagnostic guidance. See spec Section 4.3 for the ladder.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from .error_classifier import ErrorCategory
from .diagnostic_agent import DiagnosticOutput


@dataclass
class RecoveryStrategy:
    """Structured output from the strategy ladder selection.

    Fields match spec Appendix C.5. The strategy_name determines which
    recovery approach is used, and prompt_modifications/constraints guide
    the retry execution.
    """
    strategy_name: str                      # One of: fix_specific, rewrite_with_diagnosis, simplify, decompose, escalate
    tier: int                               # 1-5
    strategy_description: str               # Human-readable description of recovery approach
    constraints: list[str] = field(default_factory=list)  # Constraints applied to retry
    prompt_modifications: dict = field(default_factory=dict)  # Modifications to agent prompt
    scope_reduction: Optional[str] = None   # Scope reduction instructions (Tier 3+)
    is_terminal: bool = False               # True for decompose/escalate (no more retries)


def select_strategy(
    attempt_number: int,
    error_category: ErrorCategory,
    diagnostic_output: Optional[DiagnosticOutput],
    config: Any = None,
) -> RecoveryStrategy:
    """Choose recovery strategy based on attempt number and diagnostic guidance.

    Implements the 5-tier strategy ladder from spec Section 4.3:
      Tier 1 (attempt 1): Fix Specific - feed exact error back
      Tier 2 (attempt 2): Rewrite with Diagnosis - invoke diagnostic guidance
      Tier 3 (attempt 3): Simplify + Constrain - reduce scope, limit tools
      Tier 4 (attempt 4): Decompose (terminal) - recommend task split to operator
      Tier 5 (attempt 5+): Escalate (terminal) - all recovery exhausted

    Special case: When error_category.max_retries == 1 AND requires_diagnosis
    is True, skip Tier 1 and use Tier 2 directly on the first attempt.

    Args:
        attempt_number: Current recovery attempt (1-based).
        error_category: ErrorCategory from error_classifier with recovery params.
        diagnostic_output: DiagnosticOutput from diagnostic agent (may be None
            if diagnosis was not required or failed).
        config: Config dict or object (currently unused, reserved for future
            strategy customization).

    Returns:
        RecoveryStrategy with tier, constraints, and prompt modifications.
    """
    # Special case: single-retry errors that need diagnosis skip Tier 1
    effective_tier = attempt_number
    if error_category.max_retries == 1 and error_category.requires_diagnosis:
        effective_tier = attempt_number + 1  # attempt 1 -> tier 2

    if effective_tier >= 5:
        return _tier5_escalate(diagnostic_output)
    if effective_tier == 4:
        return _tier4_decompose(diagnostic_output)
    if effective_tier == 3:
        return _tier3_simplify(diagnostic_output)
    if effective_tier == 2:
        return _tier2_rewrite_with_diagnosis(diagnostic_output)
    # effective_tier <= 1
    return _tier1_fix_specific(error_category, diagnostic_output)


def _tier1_fix_specific(
    error_category: ErrorCategory,
    diagnostic_output: Optional[DiagnosticOutput],
) -> RecoveryStrategy:
    """Tier 1: Feed the exact error back to the agent."""
    description = (
        "Your previous attempt failed. Review the error feedback below "
        "and fix the specific issue. Produce a complete, valid deliverable."
    )
    prompt_mods: dict = {
        "inject_error_feedback": True,
    }
    if diagnostic_output and diagnostic_output.specific_fix:
        prompt_mods["hint"] = diagnostic_output.specific_fix

    return RecoveryStrategy(
        strategy_name="fix_specific",
        tier=1,
        strategy_description=description,
        constraints=[],
        prompt_modifications=prompt_mods,
        scope_reduction=None,
        is_terminal=False,
    )


def _tier2_rewrite_with_diagnosis(
    diagnostic_output: Optional[DiagnosticOutput],
) -> RecoveryStrategy:
    """Tier 2: Rewrite with diagnostic guidance."""
    description = "Previous attempt failed."
    constraints: list[str] = []
    prompt_mods: dict = {
        "inject_error_feedback": True,
        "inject_diagnosis": True,
    }

    if diagnostic_output:
        description = (
            f"Previous attempt failed because: {diagnostic_output.root_cause}. "
            "Take a different approach."
        )
        if diagnostic_output.specific_fix:
            description += f" Specifically: {diagnostic_output.specific_fix}"
            prompt_mods["specific_fix"] = diagnostic_output.specific_fix
        if diagnostic_output.avoid_approaches:
            constraints.extend(
                f"Do NOT use approach: {a}" for a in diagnostic_output.avoid_approaches
            )
        if diagnostic_output.tools_to_adjust:
            constraints.extend(
                f"Adjust tool usage: {t}" for t in diagnostic_output.tools_to_adjust
            )

    return RecoveryStrategy(
        strategy_name="rewrite_with_diagnosis",
        tier=2,
        strategy_description=description,
        constraints=constraints,
        prompt_modifications=prompt_mods,
        scope_reduction=None,
        is_terminal=False,
    )


def _tier3_simplify(
    diagnostic_output: Optional[DiagnosticOutput],
) -> RecoveryStrategy:
    """Tier 3: Simplify + Constrain - reduce scope and limit tools."""
    scope_reduction = (
        "Focus only on the most critical aspect of this task. "
        "Produce a minimal but valid deliverable."
    )
    description = (
        "Multiple recovery attempts have failed. Simplify your approach. "
        f"{scope_reduction}"
    )
    constraints = [
        "Produce a minimal but valid deliverable",
        "Do not attempt complex multi-step approaches",
    ]
    prompt_mods: dict = {
        "inject_error_feedback": True,
        "inject_diagnosis": True,
        "simplify_mode": True,
    }

    if diagnostic_output:
        if diagnostic_output.tools_to_adjust:
            for tool in diagnostic_output.tools_to_adjust:
                constraints.append(f"Do NOT use {tool}")
        if diagnostic_output.specific_fix:
            prompt_mods["specific_fix"] = diagnostic_output.specific_fix
        if diagnostic_output.avoid_approaches:
            for approach in diagnostic_output.avoid_approaches:
                constraints.append(f"Avoid: {approach}")

    return RecoveryStrategy(
        strategy_name="simplify",
        tier=3,
        strategy_description=description,
        constraints=constraints,
        prompt_modifications=prompt_mods,
        scope_reduction=scope_reduction,
        is_terminal=False,
    )


def _tier4_decompose(
    diagnostic_output: Optional[DiagnosticOutput],
) -> RecoveryStrategy:
    """Tier 4: Recommend task decomposition to operator (terminal)."""
    description = (
        "Automatic recovery has not resolved the issue after multiple attempts. "
        "This task should be decomposed into smaller sub-tasks by an operator."
    )
    prompt_mods: dict = {}

    if diagnostic_output:
        if diagnostic_output.specific_fix:
            description += (
                f" Diagnostic suggestion: {diagnostic_output.specific_fix}"
            )
            prompt_mods["decomposition_suggestion"] = diagnostic_output.specific_fix
        if diagnostic_output.root_cause:
            prompt_mods["decomposition_root_cause"] = diagnostic_output.root_cause
        if diagnostic_output.tools_to_adjust:
            prompt_mods["decomposition_tools_to_adjust"] = diagnostic_output.tools_to_adjust

    return RecoveryStrategy(
        strategy_name="decompose",
        tier=4,
        strategy_description=description,
        constraints=[],
        prompt_modifications=prompt_mods,
        scope_reduction=None,
        is_terminal=True,
    )


def _tier5_escalate(
    diagnostic_output: Optional[DiagnosticOutput],
) -> RecoveryStrategy:
    """Tier 5: Escalate - all automatic recovery exhausted (terminal)."""
    description = (
        "All automatic recovery attempts exhausted. "
        "Escalating to operator with full diagnostic history."
    )
    prompt_mods: dict = {}

    if diagnostic_output and diagnostic_output.root_cause:
        prompt_mods["final_root_cause"] = diagnostic_output.root_cause

    return RecoveryStrategy(
        strategy_name="escalate",
        tier=5,
        strategy_description=description,
        constraints=[],
        prompt_modifications=prompt_mods,
        scope_reduction=None,
        is_terminal=True,
    )
