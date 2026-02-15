# Self-Healing Implementation Guide for OpenClawd Agent Dispatch System

**Date:** 2026-02-14
**Status:** Implementation mapping (pre-build)
**Source documents:**
- Best-practice reference: `/Users/alanwalker/hyve/agent-os/specs/self-healing-system-design.md`
- OpenClawd spec: `/Users/alanwalker/openclaw-orchestration/agent-os/specs/2026-02-14-openclawd-agent-dispatch-system/spec.md`
- PRD/Stories: `/Users/alanwalker/openclaw-orchestration/agent-os/specs/2026-02-14-openclawd-agent-dispatch-system/prd.json`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Assessment](#2-current-state-assessment)
3. [Error Taxonomy for OpenClawd's Domain](#3-error-taxonomy-for-openclawds-domain)
4. [Recovery Pipeline Mapping](#4-recovery-pipeline-mapping)
5. [Component-by-Component Mapping](#5-component-by-component-mapping)
6. [Conflicts and Incompatibilities](#6-conflicts-and-incompatibilities)
7. [Specific Scenario Playbooks](#7-specific-scenario-playbooks)
8. [Database Schema Additions](#8-database-schema-additions)
9. [File Structure and Module Placement](#9-file-structure-and-module-placement)
10. [User Story Impact Analysis](#10-user-story-impact-analysis)
11. [Implementation Phasing](#11-implementation-phasing)
12. [Success Metrics Adapted for OpenClawd](#12-success-metrics-adapted-for-openclawd)

---

## 1. Executive Summary

The best-practice self-healing design assumes a CI/CD development pipeline where agents write code, CI runs tests, and recovery means fixing compilation errors or test failures. OpenClawd is fundamentally different: its agents are knowledge workers (researchers, analysts, validators) whose tools are web searches, database queries, email, and Python execution -- not git commits and CI gates.

This creates a significant translation challenge. The architectural patterns (error taxonomy, 8-stage recovery pipeline, diagnostic agent, strategy ladder, failure memory, concurrency guards) are universally applicable and should be adopted. But the specific error codes, playbooks, compensating actions, and verification strategies must be completely rewritten for OpenClawd's domain.

**What OpenClawd already has (in spec or code):**
- 5-tier provider-level self-healing (US-064 in `health/self_healer.py`)
- Retry with exponential backoff for dispatch failures (US-052)
- Provider health monitoring with canary tests (US-060, US-061, US-062)
- Provider incident tracking (`provider_incidents` table, built)
- Diagnostic report generation (US-065 in `health/diagnostic_report.py`)
- Partial error handling in spec: dispatch errors, provider errors, database errors, agent output errors

**What is missing entirely:**
- Task-level self-healing (the spec only has provider-level healing)
- Error taxonomy beyond provider errors
- Diagnostic agent for task failures (distinct from provider diagnostic reports)
- Recovery pipeline with staged escalation for agent execution failures
- Failure memory / pattern database
- Error-specific playbooks for agent task domains
- Concurrency guards on recovery attempts
- Recovery context injection into agent prompts
- Compensating actions framework
- Task-level observability of recovery events

The gap is large. The OpenClawd spec's "self-healing" is focused on keeping LLM providers operational. It has no concept of healing an agent that produces bad output, gets stuck in a tool loop, or fails because a search API returned garbage. This guide bridges that gap.

### Agent Naming Convention

The existing `config.py` uses skill-group category names (`research`, `product`, `comms`, `ops`, `meta`, `content`, `taskr`, `security`, `memory`) as agent identifiers in the `AGENT_SKILLS` mapping. The parent spec uses persona names (Rex, Pixel, Haven, Vault, Nora, Scout, Keeper) informally. **The canonical `agent_name` value used in all database tables, queries, and recovery logic is the category name from `config.py`** (e.g., `research`, `product`, `ops`). This guide uses persona names for readability only. The mapping is:

| Persona (Informal) | `agent_name` (Canonical) | Domain |
|---|---|---|
| Rex | `research` | Research, market analysis |
| Pixel | `product` | Digital products, validation |
| Haven | N/A (real estate) | Maps to `research` skill group |
| Vault | N/A (acquisitions) | Maps to `research` skill group |
| Nora | `ops` | Operations, financial management |
| Scout | N/A (validation) | Maps to `security` skill group |
| Keeper | `ops` | Maintenance, automation |

### Detection Scope for Logic Errors

`VALIDATION_REJECTED` and `CONTRADICTORY_OUTPUT` error codes require operator intervention to trigger. They are NOT auto-detected by the dispatch system. The operator creates a Scout review task as a dependency via `openclawd pipeline create`. If that review task's agent returns a rejection, the operator manually classifies the upstream task's error. Future automation of this workflow is out of scope for the initial implementation.

---

## 2. Current State Assessment

### 2.1 Built (US-001 through US-019, all passing)

| Component | File | Relevance to Self-Healing |
|---|---|---|
| Database schema (all 9 new tables) | `agent-dispatch/migrations.py` | `provider_health` and `provider_incidents` tables are the only recovery-relevant schemas |
| `dispatch_status` column on `tasks` | `agent-dispatch/migrations.py` | States include `failed`, `interrupted`, `dispatch_failed` -- recovery transitions exist but no handler for them |
| Config loader with validation | `agent-dispatch/config.py` | Can validate config on startup but no runtime self-healing config |
| Adapter isolation layer | `agent-dispatch/openclawd_adapter.py` | Wraps all OpenClawd calls with error catching; raises `OpenClawdIncompatibleError` |
| Compatibility check | `agent-dispatch/compatibility_check.py` | Tiered degradation on startup schema mismatch |
| Connection strategy (reader/writer) | `agent-dispatch/dispatch_db.py` | WAL mode, busy_timeout, foreign keys -- all connection resilience is built |

### 2.2 Specified but Not Built (US-020 through US-092)

The following unbuilt stories are directly relevant to self-healing:

| User Story | Component | Self-Healing Relevance |
|---|---|---|
| US-048 | `agent_runner.py` | Tool call loop with depth/loop detection -- a form of structural error prevention |
| US-052 | Retry with backoff | Dispatch-level retry logic (immediate, +60s, +300s) -- covers transient errors only |
| US-053 | Dependency failure cascade | Propagates `dispatch_failed` to dependents -- structural error handling |
| US-054 | Supervisor poll loop | Core loop that would trigger recovery sweeps |
| US-056 | Interrupted task recovery | Re-queues interrupted tasks on restart -- compensating action for daemon crash |
| US-060 | Canary tests | Provider health validation |
| US-061 | Health monitor runner | Scheduled provider testing |
| US-062 | Regression detection | Detects provider degradation |
| US-063 | Conformance tracking | Tool-calling reliability fallback |
| US-064 | 5-tier self-healing | Provider-level recovery tiers (retry, format adapt, fallback, degrade, report) |
| US-065 | Diagnostic report | Provider failure analysis |

### 2.3 What the Spec's 5-Tier Self-Healing Actually Covers

The spec's self-healing in `health/self_healer.py` (US-064) is scoped to **provider-level** failures:

| Tier | What it handles | What it does NOT handle |
|---|---|---|
| 1 | Rate limits (429) | Agent producing wrong output |
| 2 | Tool format changes | Agent getting stuck in tool loops |
| 3 | Auth failures (401/403), persistent 5xx | Search API returning no results |
| 4 | Multiple provider failures | Schema validation failures on agent output |
| 5 | Model deprecated | Task-level logic errors |

This is analogous to the best-practice doc's **Transient Errors** category only. The other five error categories (Execution, Logic, Structural, Configuration, Resource) have no coverage at the task/agent level in the current spec.

---

## 3. Error Taxonomy for OpenClawd's Domain

The best-practice document defines 6 error categories with examples drawn from CI/CD pipelines. Below is the full translation to OpenClawd's domain, where agents do research, analysis, validation, and communication.

### 3.1 Transient Errors (infrastructure-level, self-resolving)

**Recovery:** Exponential backoff retry with no context change.

| Error Code | Description | OpenClawd Trigger |
|---|---|---|
| `RATE_LIMITED` | LLM API rate limit hit | Anthropic/OpenAI returns 429 |
| `PROVIDER_5XX` | LLM provider server error | Any 5xx from provider API |
| `PROVIDER_TIMEOUT` | LLM API call timed out | `provider.complete()` exceeds timeout |
| `NETWORK_ERROR` | Connection failed | DNS failure, connection refused, SSL error |
| `SEARCH_API_UNAVAILABLE` | Web search API temporarily down | SerpAPI/Brave returns 5xx or timeout |
| `DB_LOCKED` | SQLite database locked despite busy_timeout | `coordination.db` contention (WAL writer conflict) |
| `TOOL_TIMEOUT` | Individual tool execution timed out | `web_search`, `shell_exec`, `python_exec` hit their `timeout_seconds` |

**Parameters:** Max retries: 5 for provider-level transient errors. Tool and DB transient errors use lower retry counts (see Appendix B lookup table for per-error-code values). Backoff schedule for 5-retry provider errors (`initial_backoff_seconds=30, backoff_multiplier=2.0, max_backoff_seconds=300`): Retry 1: 30s. Retry 2: 60s. Retry 3: 120s. Retry 4: 240s. Retry 5: 300s (capped). Execution/logic errors have `initial_backoff_seconds=0` (immediate retry with context enrichment, no backoff delay).

**When to stop:** After max retries for that error code, reclassify as a different error type. A "transient" error that persists is likely a configuration error (wrong API key, endpoint removed, search API deprecated).

### 3.2 Execution Errors (agent ran, output is wrong)

In the best-practice doc, these are CI/test failures. In OpenClawd, there are no CI tests. The equivalent is: the agent ran to completion but its output does not satisfy structural requirements -- schema validation, format compliance, content quality thresholds.

**Recovery:** Feed the specific validation failure back to the agent as context.

| Error Code | Description | OpenClawd Trigger |
|---|---|---|
| `RESULT_SCHEMA_INVALID` | AgentResult missing required fields or wrong types | `agent_runner.py` validates `<agent-result>` block against AgentResult schema |
| `RESULT_PARSE_FAILED` | Agent output has no parseable `<agent-result>` block | Agent responded but didn't include the XML result block |
| `DELIVERABLE_EMPTY` | Agent returned status=completed but deliverable_content is blank | Validation in `handle_task_completion()` |
| `DELIVERABLE_TRUNCATED` | deliverable_content exceeds 50000 char limit (truncated) | Content length enforcement in security sanitizer |
| `STATUS_INVALID` | Agent returned a status not in the allowlist | Status not in `(completed, blocked, needs_input, failed)` |
| `CONFIDENCE_TOO_LOW` | Agent returned confidence_score below acceptable threshold | Enabled by default. If `AgentResult.confidence_score` is not None and `< recovery.min_confidence_score` (default: 0.3, configurable in `openclawd.config.yaml`), classify as unreliable |
| `TOOL_RESULT_MALFORMED` | Tool executor returned data the agent could not process | Tool returns error dict but agent treats it as success |
| `AGENT_SELF_REPORTED_FAILURE` | Agent returned `status: "failed"` in AgentResult | Agent self-reports inability to complete the task. The agent's `deliverable_summary` contains its explanation. |

**Parameters:** Max retries: 3 with context enrichment on each attempt. `AGENT_SELF_REPORTED_FAILURE` gets max_retries=2 with requires_diagnosis=True.

**Non-recovery statuses:** `blocked` and `needs_input` AgentResult statuses are NOT recovery scenarios. They are handled by the existing notification path in the supervisor (the spec's result handling sets task to blocked and creates high-urgency notification). The recovery pipeline is only invoked when `dispatch_status` transitions to `failed`.

### 3.3 Logic Errors (agent completed, output is semantically wrong)

In the best-practice doc, these are QA verification failures. In OpenClawd, the equivalent is: Scout (validation agent) reviews another agent's work and finds problems, or the deliverable does not address the original task.

**Recovery:** Diagnostic analysis of the gap between task requirements and agent output, then targeted retry with enriched instructions.

| Error Code | Description | OpenClawd Trigger |
|---|---|---|
| `VALIDATION_REJECTED` | Scout agent rejects deliverable quality | Operator-initiated only. Operator creates a Scout review task via `openclawd pipeline create`. Not auto-detected. |
| `TASK_MISMATCH` | Agent completed work that does not match the task description | Detected only via Diagnostic Agent reclassification during Tier 2+ analysis, or operator manual classification. Not auto-detected on initial completion. |
| `INCOMPLETE_RESEARCH` | Research agent found insufficient sources or data | Auto-detected: count URL patterns (http/https) in `deliverable_content`. If fewer than 3 distinct URLs, classify as incomplete. Detection runs in `error_capture.py` post-completion check. |
| `STALE_DATA` | Agent's output contains outdated information | Operator-only manual classification. Not auto-detected. |
| `CONTRADICTORY_OUTPUT` | Agent's deliverable contains internal contradictions | Operator-only manual classification, or Diagnostic Agent may reclassify during Tier 2+ analysis. Not auto-detected. |

**Parameters:** Max retries: 2 with diagnostic analysis between each.

### 3.4 Structural Errors (workflow is stuck, not individual agent output)

**Recovery:** Compensating actions + state cleanup + restart from known-good state.

| Error Code | Description | OpenClawd Trigger |
|---|---|---|
| `TOOL_LOOP_DETECTED` | Agent calling the same tool with same arguments repeatedly | `agent_runner.py` detects identical-call loop (US-048: same tool+args 3x in a row) |
| `TOOL_DEPTH_EXCEEDED` | Agent exceeded max tool call iterations (default 20) | Tool call loop hits `max_tool_iterations` limit |
| `STUCK_TASK` | Task dispatched but no progress for extended period | Detected when: (a) `dispatch_status='dispatched'` for longer than `agent_timeout_seconds` (default 1800s), OR (b) lease extended 3+ times with no `tool_calls_count` increment between extensions, OR (c) `dispatch_runs.started_at` older than `agent_timeout_seconds` with `status='running'` |
| `DEPENDENCY_DEADLOCK` | Circular dependency prevents task from becoming dispatchable | `task_dependencies` graph has a cycle |
| `COMPLETION_SEQUENCE_STUCK` | Task stuck between `dispatch_status=completed` and `tasks.status!=completed` | Handled by existing US-051 recovery sweep (`recover_partial_completions()`), NOT by the new recovery pipeline. The recovery pipeline defers to the sweep and only escalates if the sweep reports failure after its own 3 retries. Do not double-retry. |

**Parameters:** Max retries: 2 with compensating actions between each. Exception: `COMPLETION_SEQUENCE_STUCK` uses US-051's own retry logic (3 retries). `DEPENDENCY_DEADLOCK` gets 0 retries (immediate escalation).

### 3.5 Configuration Errors (execution impossible without environmental changes)

**Recovery:** No automatic retry. Alert with remediation instructions.

| Error Code | Description | OpenClawd Trigger |
|---|---|---|
| `API_KEY_MISSING` | Required API key env var not set | `validate_config()` finds missing env var at dispatch time |
| `API_KEY_INVALID` | API key present but provider rejects it (401) | Provider returns auth failure |
| `PROVIDER_NOT_CONFIGURED` | No provider configured for agent | `get_provider()` finds no matching config for agent |
| `TOOL_NOT_AVAILABLE` | Agent needs a tool that has no executor | Tool YAML exists but executor module missing or broken |
| `AGENT_NOT_FOUND` | Task assigned to unknown agent name | `assigned_agent` not in known agent list |
| `DB_SCHEMA_INCOMPATIBLE` | `compatibility_check.py` returns tier 2 or 3 | Schema validation fails on startup |
| `SEARCH_API_NO_KEYS` | All search APIs need keys but none configured; DuckDuckGo also failing | web_search fallback chain fully exhausted |

**Parameters:** Max retries: 0. Immediate alert with exact remediation steps.

### 3.6 Resource Errors (budget/capacity limits)

**Recovery:** Budget errors: no retry, alert. Capacity errors: 1 retry with scope reduction.

| Error Code | Description | OpenClawd Trigger |
|---|---|---|
| `GLOBAL_BUDGET_EXCEEDED` | Daily spend across all agents exceeds `daily_budget_usd` | `check_budget()` returns `global_exceeded=True` |
| `AGENT_BUDGET_EXCEEDED` | Per-agent daily spend exceeds `agent_budgets[agent]` | `check_budget()` returns `agent_exceeded=True` |
| `CONTEXT_OVERFLOW` | Task + prompt + skills exceeds provider's context window | `count_tokens()` returns value exceeding `max_context_tokens` |
| `MAX_TOKENS_EXCEEDED` | Task consumed more tokens than `max_tokens_per_task` | Token usage tracking exceeds config limit |
| `DISK_SPACE_LOW` | Database or output directory running out of space | `monitor_and_vacuum_db()` detects db > threshold; or output write fails |

**Parameters:** Budget errors: 0 retries. Context overflow: 1 retry with prompt trimming (reduce skill summaries, summarize task description).

---

## 4. Recovery Pipeline Mapping

### 4.1 Best-Practice 8-Stage Pipeline Mapped to OpenClawd

| Stage | Best Practice | OpenClawd Implementation | File Location |
|---|---|---|---|
| 1. CAPTURE | Extract CI logs, git diffs, compiler errors | Extract agent output, tool call history, provider response, error traces | `agent-dispatch/recovery/error_capture.py` (NEW) |
| 2. CLASSIFY | Lookup table mapping error codes to taxonomy | Deterministic classifier using error codes from Section 3 | `agent-dispatch/recovery/error_classifier.py` (NEW) |
| 3. DIAGNOSE | Diagnostic Agent LLM call for non-transient errors | Lightweight LLM call using cheaper model (Haiku) to analyze failure | `agent-dispatch/recovery/diagnostic_agent.py` (NEW) |
| 4. COMPENSATE | Revert git changes, reset loop counters | Clear partial results, reset dispatch_status, clean stale leases | `agent-dispatch/recovery/compensating_actions.py` (NEW) |
| 5. STRATEGIZE | Strategy ladder based on attempt number | Adapted strategy ladder (Section 4.3 below) | `agent-dispatch/recovery/strategy_selector.py` (NEW) |
| 6. EXECUTE | Re-run agent with enriched context | Re-dispatch task with recovery context injected into prompt | `agent-dispatch/recovery/recovery_executor.py` (NEW) |
| 7. VERIFY | Confirm recovery succeeded | Re-validate AgentResult + check original error didn't recur | `agent-dispatch/recovery/recovery_verifier.py` (NEW) |
| 8. LEARN | Record error-diagnosis-fix triple | Write to `failure_memory` table | `agent-dispatch/recovery/failure_memory.py` (NEW) |

### 4.2 What OpenClawd Captures (Stage 1) vs. Best Practice

The best-practice doc specifies capturing CI logs, compiler errors, test failures, and git diffs. None of these exist in OpenClawd. Here is the translated capture list:

| Data Point | OpenClawd Source | Where to Store |
|---|---|---|
| Error code + message | Exception or validation error from `agent_runner.py` | `dispatch_runs.error_summary` (exists) + new `error_context` JSON column |
| Failed task details | `tasks` table row | Passed to diagnostic agent as context |
| Agent's full output | Raw LLM response content | New `dispatch_runs.raw_output` column (TEXT, nullable) |
| Tool call history | Accumulated during tool loop in `agent_runner.py` | New `dispatch_runs.tool_call_log` column (JSON TEXT) |
| Provider response metadata | `LLMResponse` object (tokens, model, stop_reason) | `dispatch_runs.tokens_used` (exists) + new `dispatch_runs.stop_reason` column |
| Previous recovery history | `dispatch_runs` rows for same task_id with attempt > 1 | Query existing `dispatch_runs` table |
| Task context (description, dependencies) | `tasks` table + `working_memory` table | Passed to diagnostic agent |
| Time elapsed | `dispatch_runs.started_at` to now | Computed at capture time |
| Upstream working memory | `working_memory` rows from dependency chain tasks | Passed to prompt builder |

### 4.3 Strategy Ladder Adapted for OpenClawd

| Attempt | Strategy | OpenClawd-Specific Description |
|---|---|---|
| 1 | Fix Specific | Feed the exact error back. "Your output failed validation: {error}. The deliverable_content field was empty. Produce a complete deliverable." |
| 2 | Rewrite with Diagnosis | Invoke Diagnostic Agent. Feed diagnosis to original agent. "Previous attempt failed because {diagnosis}. Take a different approach. Specifically: {specific_fix}." |
| 3 | Simplify + Constrain | Reduce task scope. "Focus only on the most critical aspect of this task. Do not use {tool that failed}. Produce a minimal but valid deliverable." |
| 4 | Recommend Decomposition (manual) | Create an urgent notification with the Diagnostic Agent's decomposition suggestions. The operator uses `openclawd pipeline create` to manually split the task. The task enters `dispatch_status='dispatch_failed'` (terminal). No further automatic recovery is attempted. Decompose is the terminal automatic action. |
| 5 | Escalate | All automatic recovery exhausted. Create urgent notification with full history. Pause the task. |

**Special case:** When an error code has `max_retries=1` AND `requires_diagnosis=True` (e.g., `STALE_DATA`), the single retry attempt uses Tier 2 (Rewrite with Diagnosis) directly, skipping Tier 1 (Fix Specific). Rationale: if diagnosis is required, a simple error-feedback retry (Tier 1) is unlikely to help.

### 4.4 Recovery Prompt Template for OpenClawd

When re-running an agent after failure, `agent_prompts.py` must inject recovery context:

```
## Task
{Original task description from tasks.description}

## Recovery Context
This is recovery attempt {N} for this task. Previous attempts failed.

### Attempt {N-1} Result
- Error: {error_code} -- {error_message}
- Agent Output (excerpt): {first 500 chars of previous raw output -- NOTE: diagnostic agent gets 2000 chars, recovery prompt gets 500 chars to preserve token budget}
- Tool Calls Made: {count and summary of tools called}
- Diagnosis: {diagnostic_analysis from Diagnostic Agent, if available}

### Recovery Strategy
{strategy_description from strategy ladder}

### Constraints
- Do NOT repeat the approach from attempt {N-1}: {description of failed approach}
- {Additional constraints, e.g. "Do not use web_search; use database_query instead"}

### Previous Attempts Summary
{For each prior attempt: what was tried, what error occurred, diagnostic summary}
```

---

## 5. Component-by-Component Mapping

### 5.1 Error Taxonomy

| Aspect | Best Practice | OpenClawd Status | Action Required |
|---|---|---|---|
| 6 error categories | Transient, Execution, Logic, Structural, Configuration, Resource | **Partially covered.** Provider errors map to Transient. Dispatch retry (US-052) is a flat 3-retry backoff with no classification. | Create `agent-dispatch/recovery/error_classifier.py` with lookup table mapping all error codes from Section 3 to categories. Integrate into `agent_runner.py` and `agent_supervisor.py`. |
| Deterministic classification | Lookup table, not LLM | **Not implemented.** The spec's error handling is procedural (if/else in various modules). No centralized taxonomy. | Build centralized `ERROR_TAXONOMY` dict in `error_classifier.py`. |
| Category-specific recovery params | Different max retries, backoff, escalation per category | **Not implemented.** US-052 uses flat 3-retry backoff for all failures. | Enhance `handle_dispatch_failure()` to read per-category params from `ERROR_TAXONOMY`. |

### 5.2 Recovery Pipeline (8 Stages)

| Stage | Best Practice | OpenClawd Status | Action Required |
|---|---|---|---|
| 1. CAPTURE | Comprehensive error context extraction | **Partially exists.** `dispatch_runs.error_summary` stores a text summary. No structured error context, no tool call logs, no raw agent output. | Add columns to `dispatch_runs` (see Section 8). Create `error_capture.py` module. |
| 2. CLASSIFY | Deterministic error code to category mapping | **Missing entirely.** | Create `error_classifier.py` with two-layer classification: (a) `detect_error_code(exception, http_status, agent_result, context) -> str` maps raw Python exceptions and HTTP status codes to error codes (e.g., `anthropic.RateLimitError -> RATE_LIMITED`, `requests.Timeout -> PROVIDER_TIMEOUT`, `json.JSONDecodeError on agent output -> RESULT_PARSE_FAILED`, `AgentResult.status == "failed" -> AGENT_SELF_REPORTED_FAILURE`, `AgentResult.confidence_score < threshold -> CONFIDENCE_TOO_LOW`). (b) `classify_error(error_code) -> ErrorCategory` looks up the category from `ERROR_TAXONOMY` dict. |
| 3. DIAGNOSE | Diagnostic Agent (lightweight LLM call) | **Missing at task level.** `health/diagnostic_report.py` (US-065) generates reports for provider failures only, not agent task failures. | Create `recovery/diagnostic_agent.py` that calls a cheap model (Haiku) with the Diagnostic Agent prompt template. |
| 4. COMPENSATE | Clean up failed attempt artifacts | **Partially exists.** `recover_partial_completions()` in US-051 handles the completion sequence failure. `recover_interrupted_tasks()` in US-056 re-queues interrupted tasks. Neither handles general pre-retry cleanup. | Create `compensating_actions.py` with actions per error type. |
| 5. STRATEGIZE | Strategy ladder varying by attempt | **Missing.** US-052 retries with the same approach on all attempts. | Create `strategy_selector.py` implementing the 5-step ladder from Section 4.3. |
| 6. EXECUTE | Re-run with enriched context | **Partially exists.** `agent_runner.py` (US-048) can run agents. But no mechanism to inject recovery context into the prompt. | Enhance `agent_prompts.py` to accept optional `recovery_context` parameter. Enhance `agent_supervisor.py` to call the runner with recovery context on retry. |
| 7. VERIFY | Confirm original error resolved, no new errors | **Missing.** Retry just checks if the agent returned successfully. No verification that the specific original error didn't recur. | Add verification logic to `recovery_executor.py`: compare new error (if any) against original error code. |
| 8. LEARN | Record error-fix pattern for future reference | **Missing entirely.** No failure memory. | Create `failure_memory.py` + `failure_memory` table (Section 8). |

### 5.3 Diagnostic Agent

| Aspect | Best Practice | OpenClawd Status | Action Required |
|---|---|---|---|
| Separate analytical LLM call | Uses cheaper/faster model for diagnosis | **Not implemented at task level.** `health/diagnostic_report.py` generates text reports for provider failures but does not make LLM calls for analysis. | Create `recovery/diagnostic_agent.py` with structured input/output schemas. Uses model specified in `recovery.diagnostic_model` config key (default: `claude-haiku-4-5`). Fallback: if `recovery.diagnostic_model` is not configured, use the primary provider's model. Max input tokens: `recovery.diagnostic_max_input_tokens` (default: 4000). If assembled context exceeds this, truncate: (1) tool_call_log to last 10 entries, (2) raw_agent_output to 1000 chars, (3) previous_attempts to 1-line summaries. |
| Input schema | Task spec + error details + evidence + history + past fixes | **No schema exists.** | Define `DiagnosticInput` and `DiagnosticOutput` dataclasses in `recovery/diagnostic_agent.py`. |
| Output schema | root_cause, category, confidence, strategy recommendation, files_to_modify | **No schema exists.** Adapt: `files_to_modify` becomes `tools_to_adjust` or `approach_to_change`. | Define output schema adapted for OpenClawd's domain (no files, no git -- tasks and tools instead). |
| Prompt template | Analytical prompt with rules about specificity, evidence, cycles | **No template exists.** | Write `agent-dispatch/prompts/diagnostic_sop.md` with adapted rules. Target: < 1500 tokens for the system prompt itself (excluding injected context). |
| Does NOT fix, only diagnoses | Separation of concerns | **Correct pattern to follow.** | Enforce in implementation: diagnostic agent returns analysis dict, runner receives it as recovery context. |

### 5.4 Strategy Ladder

| Aspect | Best Practice | OpenClawd Status | Action Required |
|---|---|---|---|
| 5-level escalation with different strategies per attempt | Fix Specific -> Rewrite with Diagnosis -> Simplify + Constrain -> Decompose -> Escalate | **Not implemented.** US-052 has flat retry. US-064 has 5-tier provider healing but that is a different concern (provider availability vs. task completion). | Implement in `recovery/strategy_selector.py`. Each strategy returns a `RecoveryStrategy` dataclass with prompt modifications, constraints, and scope adjustments. |
| Strategy informed by diagnosis | If diagnostic says "spec ambiguous" -> different path than "wrong tool" | **Not implemented.** | Wire `diagnostic_agent.py` output into `strategy_selector.py` input. |

### 5.5 Failure Memory

| Aspect | Best Practice | OpenClawd Status | Action Required |
|---|---|---|---|
| Error-diagnosis-fix triples stored for similarity matching | error_signature, recovery_attempt, outcome | **Missing entirely.** | Create `failure_memory` table (Section 8) and `recovery/failure_memory.py` module. |
| Similarity matching before retry | Match on error_code, message pattern, task domain | **Missing.** | Implement `find_similar_fixes(error_code, agent_name, task_domain) -> list` in `failure_memory.py`. Uses three-tier SQL queries: (1) Exact match on `error_code` AND `agent_name` AND `success=TRUE`, ordered by `created_at DESC`, limit 3. (2) If no results, match on `error_code` AND `task_domain`, limit 3. (3) If still no results, match on `error_code` alone, limit 3. Return the first tier that produces results. No embedding or fuzzy matching in initial implementation. |
| Pattern detection across tasks | "Same error 15 times in 24h" -> systemic issue | **Missing.** | Add pattern detection queries in `failure_memory.py`. Surface in `openclawd doctor` and in escalation alerts. |

### 5.6 Concurrency Guards

| Aspect | Best Practice | OpenClawd Status | Action Required |
|---|---|---|---|
| Duplicate recovery prevention | Atomic status transition `WHERE status = 'failed'` | **Partially exists.** The claim_task() in US-050 uses atomic UPDATE with WHERE guards for dispatch. But no `recovering` status exists. | Add `recovering` to `dispatch_status` CHECK constraint. Use atomic UPDATE to transition `failed -> recovering` before starting recovery. |
| Recovery-during-recovery prevention | Hard ceiling on total recovery attempts | **Partially exists.** US-052 limits to 3 retries. But this is flat retry count, not tiered recovery count. | Track `recovery_tier` and `total_recovery_attempts` in `dispatch_runs` or a new `recovery_state` JSON field. |
| Pipeline advancement during recovery | Blocked tasks don't advance while recovering | **Exists.** The dispatchable task query (US-049) checks `dispatch_status` and `lease_until`. A task with `dispatch_status='failed'` or `dispatch_status='recovering'` would not match. | Ensure `recovering` status is excluded from the dispatchable set (it already would be since condition 2 only matches NULL or `queued`). |

### 5.7 Observability

| Aspect | Best Practice | OpenClawd Status | Action Required |
|---|---|---|---|
| Recovery timeline logging | Every recovery event with timestamp, event type, duration | **Partially covered.** US-071 (structured JSON logging) will log to `supervisor.jsonl`. But no specific recovery event types are defined. | Define recovery-specific log events: `recovery.capture`, `recovery.classify`, `recovery.diagnose.start/complete`, `recovery.strategy.selected`, `recovery.execute.start/complete`, `recovery.verify`, `recovery.learn`, `recovery.escalate`. |
| Dashboard visibility | Per-task recovery status and history | **Not covered by spec.** The spec has no dashboard beyond `openclawd serve` (US-089) which exposes `GET /status`. | Extend the `/status` JSON payload to include recovery state for active tasks. Add `openclawd logs --recovery` filter. |
| Alerting at tier boundaries | Alert when recovery escalates beyond Tier 1 | **Partially covered.** US-078 (urgency-based notification routing) provides the delivery mechanism. But no recovery-specific alerts are defined. | Define alert rules: Tier 2+ reached -> `high` urgency. Tier 4+ -> `urgent`. Tier 5 -> `urgent` with full diagnostic. |

### 5.8 Error-Specific Playbooks

The best-practice doc defines 7 playbooks for CI-specific errors. None of these apply directly. Section 7 of this document provides the OpenClawd-domain playbooks.

### 5.9 Story Status Lifecycle

| Aspect | Best Practice | OpenClawd Status | Action Required |
|---|---|---|---|
| Status lifecycle (pending -> in_progress -> completed/blocked) | Defines `recovering` as a critical status | **Partially exists.** `dispatch_status` has: `NULL, queued, dispatched, completed, failed, interrupted, dispatch_failed`. No `recovering` status. The existing `tasks.status` CHECK constraint is `('open', 'in_progress', 'review', 'completed', 'blocked')` and cannot be modified. | Add `recovering` to the `dispatch_status` CHECK constraint. Do NOT modify `tasks.status` (OpenClawd constraint). The `dispatch_status` is the dispatch system's own status column -- it can be extended. |
| `blocked` triggers immediate recovery | Event-driven recovery on failure | **Not implemented.** US-052 handles failure by setting `next_retry_at` on the dispatch_run and waiting for the next poll cycle. Recovery is poll-driven, not event-driven. | This is acceptable for OpenClawd's 30-second poll interval. A 30-second delay before recovery starts is tolerable. No immediate trigger needed. |

### 5.10 Performance Boundaries

| Dimension | Best Practice | OpenClawd Adaptation |
|---|---|---|
| Max recovery attempts per task | 5 | 5 (keep as-is; currently spec says 3 in US-052 -- increase) |
| Max time in recovery per task | 30 minutes | 30 minutes (matches `agent_timeout_seconds: 1800`) |
| Max Diagnostic Agent calls per task | 3 | 3 (one per tier that uses it: Tier 2, 3, and 4) |
| Max token spend on recovery per task | Per-task recovery cost cap | `recovery_budget = min(daily_budget_usd * 0.04, 2.00)`. This allocates 4% of the daily budget per task recovery, capped at $2.00. Before each recovery attempt, check if cost of all recovery attempts for this task (`SUM(cost_estimate) FROM dispatch_runs WHERE recovery_tier IS NOT NULL AND task_id = ?`) exceeds `recovery_budget`. If so, escalate immediately. |
| Max concurrent recoveries | 3 | 3 (fits within `max_concurrent_agents: 5` leaving 2 slots for new tasks). Enforcement: before starting recovery, query `SELECT COUNT(*) FROM tasks WHERE dispatch_status='recovering'`. If >= `recovery.max_concurrent_recoveries` (default: 3), defer recovery: set `dispatch_runs.next_retry_at` to 60 seconds from now and return. Next poll cycle re-evaluates. |
| Recovery timeout per attempt | 10 minutes | 10 minutes |
| Failure memory retention | 90 days | 90 days (aligned with `retention.dispatch_runs_days: 90`) |
| Max escalations per hour | 5 | 5 (implement in notification delivery to prevent alert fatigue) |

---

## 6. Conflicts and Incompatibilities

### 6.1 No Git, No CI, No PRs

**Best-practice assumptions that do not apply:**

| Assumption | Why It Doesn't Apply | Adaptation |
|---|---|---|
| Git branch state as checkpoint | OpenClawd agents don't write code to git | Checkpoint = `dispatch_runs` row snapshot. Save `raw_output` and `tool_call_log` before retry so the recovery context is preserved. |
| CI gate as verification | No CI pipeline | Verification = AgentResult schema validation + optional Scout review |
| Git diff as evidence | No code changes | Evidence = tool call history + raw agent output |
| PR workflow for escalation | No pull requests | Escalation = urgent notification with diagnostic report via webhook/email/desktop |
| Revert branch as compensating action | No branches to revert | Compensating action = reset `dispatch_status` to `queued`, clear working_memory written by the failing agent for the current task (`DELETE FROM working_memory WHERE task_id = ? AND agent_name = ?` -- only clears entries from the failing agent, never upstream dependency data from other tasks), log the abandoned output |
| Build cache cleanup | No builds | N/A -- no equivalent needed |

### 6.2 Single-Turn vs. Multi-Step Pipeline

The best-practice doc assumes a multi-step workflow pipeline where a story progresses through: implement -> CI gate -> QA -> review. OpenClawd agents execute in a single turn: prompt in, result out. There is no multi-step pipeline per task.

**Impact:** The concepts of "step-level failure" and "restart from current step" mostly do not apply. In OpenClawd, failure is at the task level (the whole agent execution failed or produced bad output), not at a step within a workflow.

**Adaptation:** The recovery pipeline operates at the task level. When a task fails, the entire agent execution is retried (not a sub-step within it). The "steps" in the recovery pipeline (CAPTURE -> CLASSIFY -> DIAGNOSE -> etc.) are the recovery system's own pipeline, not the agent's execution steps.

**Exception:** The tool call loop within `agent_runner.py` IS a multi-step process. A `TOOL_LOOP_DETECTED` or `TOOL_DEPTH_EXCEEDED` error occurs at a specific point in the tool call sequence. Recovery could potentially resume from that point by providing the accumulated tool results so far. This is a future enhancement -- for now, retry the entire agent execution with recovery context noting which tools were problematic.

### 6.3 Task Completion Sequence is Already Multi-Boundary

One area where multi-step recovery IS relevant: the task completion sequence (Block A -> Step 3 -> Step 4) described in the spec. This already has its own recovery sweep in US-051 (`recover_partial_completions`). This is conceptually a "compensating action" in the best-practice framework. The existing design is correct and does not need replacement -- but it should be integrated into the broader recovery pipeline as a structural error handler.

### 6.4 No "Story Foreach" Iterator

The best-practice doc references a foreach iterator that processes stories sequentially. OpenClawd dispatches tasks from a priority queue. There is no sequential iteration.

**Impact:** Concepts like "pause the pipeline at the failed story" translate to "leave the task in `dispatch_status=failed/recovering` so it doesn't get re-dispatched until recovery is complete." This already works with the existing dispatchable task query.

### 6.5 Agent Decomposition is Manual, Not Automatic

The best-practice strategy ladder includes "Decompose" (break task into sub-tasks) as Tier 4. The OpenClawd spec explicitly puts task decomposition out of scope for automatic operation (see "Out of Scope: Agent-initiated task decomposition"). Manual decomposition via `openclawd pipeline create` IS in scope.

**Adaptation:** Tier 4 (Decompose) creates an urgent notification recommending the operator decompose the task, rather than automatically splitting it. Include the diagnostic agent's decomposition suggestions in the alert. The operator can then use `openclawd pipeline create` to manually split it.

---

## 7. Specific Scenario Playbooks

### 7.1 Playbook: Web Search API Down

**Scenario:** Rex (research agent) calls `web_search` but the search API is down.

```
1. CAPTURE:
   - Error source: tools/executors/web_search.py
   - Error type: HTTP 5xx from SerpAPI, or timeout, or ConnectionError
   - Context: Task was "{task.description}", agent was mid-research
   - Tool call log shows: web_search(query="...") -> error

2. CLASSIFY: SEARCH_API_UNAVAILABLE -> Transient Error
   (Unless: all three APIs in the fallback chain fail -- then Configuration Error)

3. RECOVERY PATH (Transient):
   a. web_search executor already has its own fallback chain:
      SerpAPI -> Brave Search -> DuckDuckGo
   b. If the executor's internal fallback handled it, no recovery needed
   c. If ALL three APIs fail:
      - Retry 1 (immediate): Try the full chain again
      - Retry 2 (after 30s): Try again
      - Retry 3 (after 60s): Try again
      - Retry 4 (after 120s): Try again
      - Retry 5 (after 300s): Try again
      - If still failing after 5 retries:

4. RECLASSIFY: SEARCH_API_NO_KEYS -> Configuration Error
   (if no API keys configured and DuckDuckGo scraping is also blocked)
   OR: Escalate as persistent transient error

5. COMPENSATE: No partial state to clean. Agent hadn't produced output yet.

6. STRATEGIZE (if the tool itself works but search returned no useful results):
   - Attempt 2 strategy: Add recovery context suggesting different search terms:
     "Your previous search for '{query}' returned no results. Try broader terms
     or a completely different search strategy." The agent decides the actual query.
   - Attempt 3 strategy: "Use database_query to search local knowledge base
     instead of web_search. The web search API is currently unavailable."

7. ESCALATE (if all retries fail):
   - Urgent notification: "Search APIs unavailable. Rex cannot complete
     research tasks. Check SerpAPI/Brave API status. DuckDuckGo fallback
     also failing (possible IP block or site change)."
   - Task stays in dispatch_status='failed', not dispatch_failed
   - Next poll cycle will retry when search APIs recover
```

**Key file touchpoints:**
- `agent-dispatch/tools/executors/web_search.py` -- executor already has API fallback chain
- `agent-dispatch/recovery/error_classifier.py` -- classify `SEARCH_API_UNAVAILABLE`
- `agent-dispatch/recovery/compensating_actions.py` -- no-op for this error
- `agent-dispatch/recovery/strategy_selector.py` -- query modification strategy

### 7.2 Playbook: Malformed LLM Tool Calls

**Scenario:** The LLM provider returns a tool call with invalid JSON arguments or calls a tool that does not exist.

```
1. CAPTURE:
   - Error source: agent_runner.py tool call loop
   - Error type: JSON parse error on tool_call.arguments, or
     tool name not in registry, or arguments don't match schema
   - Context: Provider={provider}, model={model}, tool_call={raw_json}
   - This is evidence of provider tool-calling degradation

2. CLASSIFY: Depends on sub-type:
   a. Malformed JSON -> RESULT_PARSE_FAILED -> Execution Error
   b. Unknown tool name -> likely a hallucination -> Execution Error
   c. Wrong argument types -> TOOL_RESULT_MALFORMED -> Execution Error

3. IMMEDIATE ACTION (before full recovery pipeline):
   - Log to provider_health as a tool_calling failure
   - Check conformance tracking (US-063): if this is the Nth failure
     in the rolling 20-check window, trigger prompt-based tool fallback
   - This is a DUAL failure: both a provider health issue AND a task failure

4. RECOVERY PATH (Execution Error):
   - Attempt 1: Re-run the agent with exact error fed back:
     "Your previous tool call was malformed: {error_details}.
      Tool '{tool_name}' expects arguments: {correct_schema}.
      Please retry with valid arguments."
   - Attempt 2: If same provider fails again, switch to fallback provider
     (align with health/self_healer.py Tier 3)
   - Attempt 3: If fallback also produces malformed calls, switch to
     prompt-based tool mode per conformance-based fallback (US-063).
     If US-063 is not yet built, escalate to Tier 3 strategy (simplify
     + constrain) instead. Note: prompt-based tool mode specification
     is owned by US-063, not the recovery system.

5. VERIFY: On success, record in failure memory. On persistent failure,
   escalate with diagnostic report noting provider tool-calling reliability.

6. LEARN: Record that {provider}/{model} produced malformed tool calls for
   {tool_name}. Future similar errors can shortcut to fallback provider.
```

**Key file touchpoints:**
- `agent-dispatch/agent_runner.py` -- tool call loop error handling
- `agent-dispatch/health/health_monitor.py` -- log tool_calling failure
- `agent-dispatch/health/self_healer.py` -- provider fallback trigger
- `agent-dispatch/recovery/error_classifier.py` -- classify tool call errors
- `agent-dispatch/recovery/failure_memory.py` -- record pattern

### 7.3 Playbook: AgentResult Schema Validation Failure

**Scenario:** An agent produces output but it fails AgentResult schema validation.

```
1. CAPTURE:
   - Error source: agent_runner.py result parsing / validation
   - What failed: missing <agent-result> block, missing required fields,
     invalid status value, malformed JSON inside the XML block
   - Raw output: full agent response text (store in dispatch_runs.raw_output)
   - Tool calls made: full log of tool calls during execution

2. CLASSIFY: RESULT_SCHEMA_INVALID or RESULT_PARSE_FAILED -> Execution Error

3. RECOVERY PATH:
   - Attempt 1 (Fix Specific):
     Feed exact validation error back to agent:
     "Your response was received but could not be parsed. Error: {validation_error}.
      Your response must include an <agent-result> block with valid JSON containing:
      status (completed|blocked|needs_input|failed), deliverable_summary (string),
      deliverable_content (string). Please try again."
     Include the FULL base_sop.md instructions in the retry prompt to reinforce format.

   - Attempt 2 (Rewrite with Diagnosis):
     Diagnose: Is the agent ignoring the SOP? Is the output too long and the
     result block got truncated? Did the agent get confused by tool results?
     Feed diagnosis: "Diagnostic analysis: {root_cause}. {specific_fix}"
     If the issue is truncation (context overflow), add constraint:
     "Keep your deliverable under 10000 characters."

   - Attempt 3 (Simplify + Constrain):
     "Produce the SHORTEST possible valid response. Your ENTIRE response
      should be the <agent-result> block and nothing else. Focus on status
      and deliverable_summary only."

4. COMPENSATE: Clear any working_memory entries written by the failed attempt
   (since the result was invalid, we cannot trust mid-execution writes).

5. VERIFY: Parse the new response. If same parse error, increment attempt.
   If different error (e.g., agent now returns valid schema but wrong content),
   treat as new error starting from CAPTURE.
```

**Key file touchpoints:**
- `agent-dispatch/agent_runner.py` -- `<agent-result>` parsing
- `agent-dispatch/agent_prompts.py` -- inject recovery context with format reminders
- `agent-dispatch/recovery/compensating_actions.py` -- clear partial working_memory
- `agent-dispatch/prompts/base_sop.md` -- the SOP that agents should follow

### 7.4 Playbook: Agent Stuck in Tool Call Loop

**Scenario:** An agent calls `web_search` with the same query repeatedly, or alternates between `web_search` and `database_query` without making progress.

```
1. CAPTURE:
   - Error source: agent_runner.py loop detection (US-048)
   - Error type: identical-call loop (same tool+args 3x in a row) or
     depth limit exceeded (20 iterations with no <agent-result>)
   - Tool call log: full sequence of tool calls made
   - Pattern: which tools, which arguments, how many times

2. CLASSIFY: TOOL_LOOP_DETECTED or TOOL_DEPTH_EXCEEDED -> Structural Error

3. DIAGNOSE:
   Diagnostic Agent analyzes the tool call sequence:
   - Is the agent repeating because tool results are insufficient?
     "web_search returned empty results 3 times for query X"
   - Is the agent confused about how to use the tool?
     "Agent calling database_query with natural language instead of SQL"
   - Is the agent in a genuine loop (not making progress)?
     "Agent alternating between search and query with same inputs"

4. COMPENSATE:
   - Reset tool iteration counter
   - Clear working_memory for this agent+task: `DELETE FROM working_memory WHERE task_id = ? AND agent_name = ?`
   - Log the abandoned tool call sequence for analysis

5. STRATEGIZE based on diagnosis:
   a. If tool results are empty/useless:
      "Previous attempt got stuck searching for '{query}'. The search
       returned no useful results. Try a completely different approach:
       {alternative_approach_from_diagnosis}."
      Also: add to recovery prompt: "Do NOT call {tool_name} with arguments
       matching '{pattern}'. This combination produced no useful results on the
       previous attempt." Blacklisting is via prompt injection only, not runtime
       filtering. The agent is responsible for respecting this constraint.

   b. If agent misused the tool:
      "Previous attempt misused the {tool_name} tool. Correct usage:
       {tool_schema_description}. Example: {example_from_tool_yaml_test_block}."

   c. If genuine infinite loop:
      Reduce max_tool_iterations to 10 for the retry.
      Add constraint: "You have a maximum of 10 tool calls. Plan your
       approach before calling any tools."

6. VERIFY: If the agent loops again on retry, escalate to Tier 3
   (simplify). If Tier 3 also loops, escalate to human.
```

**Key file touchpoints:**
- `agent-dispatch/agent_runner.py` -- loop detection (same tool+args 3x check)
- `agent-dispatch/recovery/diagnostic_agent.py` -- analyze tool call sequence
- `agent-dispatch/recovery/strategy_selector.py` -- tool-specific strategies
- `agent-dispatch/recovery/compensating_actions.py` -- reset counters, clear memory

### 7.5 Playbook: Task Keeps Failing Despite Completed Dependencies

**Scenario:** All of a task's dependencies are completed, but the task itself keeps failing after multiple dispatches.

```
1. CAPTURE:
   - Error source: agent_supervisor.py (task dispatched, agent fails)
   - Error history: all dispatch_runs for this task_id
   - Dependency data: working_memory from upstream tasks
   - Pattern: is it the same error each time or different errors?

2. CLASSIFY: Depends on the specific failure:
   - Same error every time -> likely Configuration or Logic error
   - Different error each time -> likely Structural or Logic error
   - First attempt worked partially -> likely Execution error

3. DIAGNOSE (critical for this scenario):
   Diagnostic Agent receives:
   - All dispatch_runs for this task (including error_summary for each)
   - The working_memory from upstream dependencies
   - The task description
   Questions for the diagnostic:
   - Is the working_memory from dependencies usable?
   - Is the task description clear enough?
   - Are the failed errors related to each other?

4. RECOVERY PATH:
   a. If dependency data is bad:
      Consider marking the upstream task as needing re-execution.
      This is a MANUAL escalation -- do not automatically re-run
      completed upstream tasks.

   b. If task description is ambiguous:
      Strategy: Simplify + Constrain (Tier 3)
      "This task has failed {N} times. Focus on the most literal
       interpretation of: '{task.title}'. Ignore edge cases."

   c. If errors are unrelated (different each time):
      This suggests environmental instability. Check:
      - Provider health (recent canary test results)
      - Budget (approaching limit causing throttling)
      - System load (too many concurrent agents)
      Escalate with systemic analysis.

5. ESCALATE (after 5 total attempts):
   Urgent notification including:
   - Full attempt history with errors
   - Dependency chain with upstream task outcomes
   - Diagnostic agent's analysis
   - Recommendation: "Consider decomposing this task with
     'openclawd pipeline create' or revising the task description."
```

**Key file touchpoints:**
- `agent-dispatch/dispatch_db.py` -- query all dispatch_runs for task
- `agent-dispatch/recovery/diagnostic_agent.py` -- multi-attempt analysis
- `agent-dispatch/recovery/failure_memory.py` -- pattern detection
- `agent-dispatch/agent_supervisor.py` -- escalation trigger

### 7.6 Playbook: Supervisor Daemon Crashes and Restarts

**Scenario:** The supervisor process dies (OOM, segfault, power loss, manual kill) and restarts.

```
1. DETECT (on startup):
   - PID file exists with stale PID (US-058)
   - Tasks with dispatch_status='dispatched' and expired lease_until
   - Tasks with dispatch_status='interrupted' (from prior graceful shutdown)

2. RECOVER (already specified in US-056 and US-054):
   a. Stale PID detection: delete stale PID, write new PID, log warning
   b. Interrupted tasks: set dispatch_status='queued', increment attempt
   c. Expired leases: on next poll, dispatchable query picks up tasks with
      expired lease_until (condition 3: lease_until < CURRENT_TIMESTAMP)
   d. Partial completions: recover_partial_completions() handles tasks
      where dispatch_status='completed' but tasks.status!='completed'

3. ADDITIONAL RECOVERY (new, from self-healing guide):
   a. Check for tasks with dispatch_status='recovering' from a prior
      recovery attempt that was in progress when the daemon crashed.
      Reset to dispatch_status='failed' so recovery can restart.
   b. On daemon restart after crash, ALL tasks with
      dispatch_status='dispatched' are treated as orphaned (agent
      processes do not survive their parent dying). Set
      dispatch_status='interrupted' and lease_until=NULL for ALL
      such tasks immediately. Do NOT wait for lease expiry -- the
      PID file already ensures single-supervisor operation, so there
      is no concurrent supervisor to conflict with.

4. HEARTBEAT RESTART:
   - Write fresh timestamp to supervisor.heartbeat
   - Resume normal poll loop

5. LOG: Log the full recovery sequence with details of how many tasks
   were recovered and what state they were in.
```

**Key file touchpoints:**
- `agent-dispatch/agent_supervisor.py` -- startup recovery sequence (US-056, US-058)
- `agent-dispatch/dispatch_db.py` -- queries for orphaned tasks
- `agent-dispatch/recovery/compensating_actions.py` -- lease cleanup

### 7.7 Playbook: Multiple Tasks Fail with Same Error

**Scenario:** Three tasks fail simultaneously with `PROVIDER_TIMEOUT`. Is it three independent failures or one systemic issue?

```
1. DETECT:
   Pattern detection in the recovery pipeline's CLASSIFY stage or in
   failure_memory.py. On each new failure, check:
   - How many tasks failed with the same error_code in the last N minutes?
     (N = `recovery.systemic_failure_window_minutes`, default: 10)
   - Are they all using the same provider/model?
   - Are they all the same agent?

2. CLASSIFY AS SYSTEMIC if:
   - `recovery.systemic_failure_threshold_count` (default: 3) or more tasks fail with same error_code within `recovery.systemic_failure_window_minutes` (default: 10)
   - All failures are against the same provider
   -> Reclassify from individual task failures to PROVIDER-LEVEL incident

3. RESPONSE:
   a. Do NOT retry all three tasks individually (waste of tokens and time)
   b. Instead, trigger the PROVIDER-LEVEL self-healing pipeline
      (health/self_healer.py, US-064):
      - Tier 1: Provider might be rate-limiting; back off all dispatches
        for this provider for 2 minutes
      - Tier 2: Run canary health check immediately (SIGUSR2 equivalent)
      - Tier 3: If canary also fails, switch to fallback provider
   c. Hold all affected tasks in dispatch_status='failed' with
      next_retry_at set to 5 minutes from now (give provider time to recover)
   d. Once provider health check passes, all held tasks become
      dispatchable again on the next poll cycle

4. ALERT:
   - High urgency: "Provider {provider} appears to be experiencing an
     outage. {N} tasks affected. Automatic fallback to {fallback_provider}
     activated. Tasks will retry in 5 minutes."

5. LEARN:
   - Record systemic incident in failure_memory with all affected task_ids
   - Future pattern detection can identify "same provider, multiple tasks"
     more quickly and shortcut to provider fallback immediately
```

**Key file touchpoints:**
- `agent-dispatch/recovery/failure_memory.py` -- cross-task pattern detection
- `agent-dispatch/health/self_healer.py` -- provider-level healing
- `agent-dispatch/health/health_monitor.py` -- immediate canary test
- `agent-dispatch/agent_supervisor.py` -- batch retry delay

---

## 8. Database Schema Additions

### 8.1 New Columns on `dispatch_runs`

These columns are needed to support the CAPTURE stage and provide evidence to the Diagnostic Agent.

```sql
-- Store the full raw output from the agent (for diagnostic analysis)
-- Max 10000 characters; truncate with '[TRUNCATED]' marker if longer.
ALTER TABLE dispatch_runs ADD COLUMN raw_output TEXT;

-- Store the tool call sequence as JSON array
-- Format: [{"tool": "web_search", "args": {...}, "result_summary": "...", "duration_ms": 1234}, ...]
ALTER TABLE dispatch_runs ADD COLUMN tool_call_log TEXT;

-- Store the LLM's stop_reason (end_turn, tool_use, max_tokens)
ALTER TABLE dispatch_runs ADD COLUMN stop_reason TEXT;

-- Store structured error context as JSON for recovery pipeline
-- Format: {"error_code": "...", "error_category": "...", "error_details": "...", "captured_at": "..."}
ALTER TABLE dispatch_runs ADD COLUMN error_context TEXT;

-- Track which recovery tier this attempt belongs to (NULL = original attempt, 1-5 = recovery tier)
ALTER TABLE dispatch_runs ADD COLUMN recovery_tier INTEGER;

-- Track the recovery strategy used for this attempt
ALTER TABLE dispatch_runs ADD COLUMN recovery_strategy TEXT;

-- STUCK_TASK detection: count of lease extensions for this run
ALTER TABLE dispatch_runs ADD COLUMN lease_extensions INTEGER DEFAULT 0;

-- STUCK_TASK detection: tool_calls_count snapshot at last lease extension
-- If this value equals current tool_calls_count after 3+ extensions, task is stuck
ALTER TABLE dispatch_runs ADD COLUMN tool_calls_count_at_last_extension INTEGER DEFAULT 0;
```

### 8.2 New Column on `dispatch_status` CHECK Constraint

The existing CHECK constraint is:
```sql
CHECK(dispatch_status IN ('queued', 'dispatched', 'completed', 'failed', 'interrupted', 'dispatch_failed'))
```

**Problem:** SQLite does not allow altering CHECK constraints on existing columns. The `dispatch_status` column was added via `ALTER TABLE` with the CHECK constraint baked in.

**Solution:** SQLite does not enforce CHECK constraints on columns added via `ALTER TABLE ADD COLUMN`. The `dispatch_status` column was added via ALTER TABLE in migration US-001. Therefore the CHECK constraint is definitively NOT enforced, and the `'recovering'` value can be used directly. No migration is needed.

Verify this with a unit test in the recovery test suite:

```python
def test_recovering_status_allowed():
    """Verify SQLite allows 'recovering' value on ALTER TABLE-added column."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, status TEXT)")
    conn.execute("ALTER TABLE test ADD COLUMN dispatch_status TEXT CHECK(dispatch_status IN ('queued','failed'))")
    conn.execute("INSERT INTO test (id, dispatch_status) VALUES (1, 'recovering')")
    result = conn.execute("SELECT dispatch_status FROM test WHERE id = 1").fetchone()
    assert result[0] == "recovering"  # CHECK not enforced on ALTER TABLE columns
    conn.close()
```

### 8.3 New Table: `failure_memory`

```sql
CREATE TABLE IF NOT EXISTS failure_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Error signature for similarity matching
    error_code TEXT NOT NULL,
    error_pattern TEXT,          -- Regex-friendly pattern from error message.
                                 -- Generated by error_capture.py: take error_message[:100],
                                 -- replace numeric values with \d+, replace quoted strings with .*
                                 -- Example: 'Rate limit exceeded: 429 for model "claude-sonnet"'
                                 -- becomes 'Rate limit exceeded: \d+ for model .*'
    task_domain TEXT,            -- From tasks.domain
    agent_name TEXT,             -- Which agent encountered this
    tool_name TEXT,              -- Which tool was involved (if any)

    -- What was tried
    recovery_strategy TEXT NOT NULL,
    recovery_tier INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL,
    diagnostic_summary TEXT,
    additional_context TEXT,     -- What extra info was given to the agent

    -- Outcome
    success BOOLEAN NOT NULL,
    resolution_summary TEXT,     -- What actually fixed it (or why it didn't work)
    time_to_recover_ms INTEGER,

    -- Metadata
    task_id INTEGER,             -- Reference (nullable in case task is archived)
    trace_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_failure_memory_error_code ON failure_memory(error_code);
CREATE INDEX IF NOT EXISTS idx_failure_memory_created_at ON failure_memory(created_at);
CREATE INDEX IF NOT EXISTS idx_failure_memory_agent ON failure_memory(agent_name);
CREATE INDEX IF NOT EXISTS idx_failure_memory_lookup ON failure_memory(error_code, agent_name, task_domain, success);
```

### 8.4 New Table: `recovery_events` (observability timeline)

```sql
CREATE TABLE IF NOT EXISTS recovery_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    trace_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'error_captured', 'error_classified', 'diagnosis_started',
        'diagnosis_completed', 'strategy_selected', 'compensate_started',
        'compensate_completed', 'retry_started', 'retry_completed',
        'verify_passed', 'verify_failed', 'escalated', 'recovery_succeeded',
        'pipeline_error'
    )),
    recovery_tier INTEGER,
    attempt_number INTEGER,
    details TEXT,               -- JSON with event-specific data
    duration_ms INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_recovery_events_task ON recovery_events(task_id);
CREATE INDEX IF NOT EXISTS idx_recovery_events_trace ON recovery_events(trace_id);
```

### 8.5 Retention Policy for New Tables

| Table | Retention | Cleanup Method |
|---|---|---|
| `failure_memory` | 90 days (configurable: `recovery.failure_memory_retention_days`) | DELETE WHERE created_at < datetime('now', '-90 days') |
| `recovery_events` | 90 days | `DELETE FROM recovery_events WHERE created_at < datetime('now', '-90 days')` in daily retention cleanup job. Also CASCADE deletes when parent task is archived. |

### 8.6 Recovery Event `details` JSON Schemas

Each `recovery_events.event_type` has a specific JSON schema for the `details` column:

| Event Type | JSON Keys |
|---|---|
| `error_captured` | `{"error_code": str, "error_message": str, "task_id": int, "agent_name": str}` |
| `error_classified` | `{"error_code": str, "category": str, "max_retries": int, "requires_diagnosis": bool}` |
| `diagnosis_started` | `{"model": str, "input_token_estimate": int}` |
| `diagnosis_completed` | `{"root_cause_category": str, "confidence": float, "recommended_strategy": str, "duration_ms": int}` |
| `strategy_selected` | `{"strategy": str, "tier": int, "constraints": [str]}` |
| `compensate_started` | `{"actions": [str]}` |
| `compensate_completed` | `{"actions_taken": [str], "duration_ms": int}` |
| `retry_started` | `{"attempt_number": int, "strategy": str, "provider": str, "model": str}` |
| `retry_completed` | `{"success": bool, "error_code": str or null, "duration_ms": int, "tokens_used": int}` |
| `verify_passed` | `{"original_error_code": str, "new_errors": []}` |
| `verify_failed` | `{"original_error_code": str, "new_error_code": str, "same_error": bool}` |
| `escalated` | `{"tier": int, "reason": str, "notification_urgency": str}` |
| `recovery_succeeded` | `{"total_attempts": int, "winning_strategy": str, "total_duration_ms": int, "total_cost_usd": float}` |
| `pipeline_error` | `{"stage": str, "exception_type": str, "exception_message": str, "task_reset_to": str}` |

---

## 9. File Structure and Module Placement

### 9.1 New `recovery/` Package

All self-healing logic lives in a new `agent-dispatch/recovery/` package, separate from the existing `health/` package. The `health/` package handles provider-level monitoring; `recovery/` handles task-level self-healing.

```
agent-dispatch/
  recovery/
    __init__.py               # Exports: handle_failure, classify_error, RecoveryContext, RecoveryOutcome, ErrorCategory, ErrorContext, RecoveryStrategy, DiagnosticInput, DiagnosticOutput, PreviousAttemptSummary, PlaybookStep, Playbook
                              # NOTE: RunnerError and RunnerResult are defined in agent_runner.py, not in recovery/. Import them from agent_runner, not from this package.
    error_classifier.py      # Stage 2: detect_error_code() + classify_error() two-layer
    error_capture.py          # Stage 1: Extract and structure error context
    diagnostic_agent.py       # Stage 3: Lightweight LLM call for root cause analysis
    compensating_actions.py   # Stage 4: Clean up failed attempt artifacts
    strategy_selector.py      # Stage 5: Choose recovery strategy (generic ladder, used when no playbook exists)
    recovery_executor.py      # Stage 6+7: Re-run agent with context + verify
    failure_memory.py         # Stage 8: Record and query error-fix patterns
    recovery_pipeline.py      # Orchestrates all 8 stages in sequence (see public API below)
    playbooks.py              # Error-specific deterministic recovery sequences (replaces ONLY the STRATEGIZE step of strategy_selector when a playbook exists for the error_code; all other pipeline stages still run)
```

### 9.1.1 `recovery_pipeline.py` Public API and Control Flow

```python
def handle_failure(
    task_id: int,
    runner_error: RunnerError,
    db: DispatchDB,
    config: dict,
) -> RecoveryOutcome:
    """
    Entry point for the recovery pipeline. Called by agent_supervisor.py
    when a task's agent execution fails.

    Control flow:
    1. Check max concurrent recoveries. If at limit, defer (set next_retry_at + 60s, return).
    2. Atomic transition: UPDATE tasks SET dispatch_status='recovering'
       WHERE id=? AND dispatch_status='failed'. If 0 rows affected, return (another process handling it).
    3. Generate trace_id = f"recovery-{task_id}-{uuid4().hex[:8]}"
    4. CAPTURE: Call error_capture.capture(runner_error, task_id, db) -> ErrorContext
    5. CLASSIFY: Call error_classifier.classify(error_context) -> ErrorCategory
    6. Check recovery budget: if total recovery cost for this task > recovery_budget, escalate immediately.
    6a. Initialize total_attempts_used = 0.
    6b. Hard ceiling: max_total_attempts = config.recovery.max_recovery_attempts (default: 5).
        This is an ABSOLUTE ceiling across all re-classifications. Even if step 7f re-classifies
        to a new error with higher max_retries, total_attempts_used cannot exceed max_total_attempts.
    7. Loop from attempt=1 to error_category.max_retries:
       CEILING CHECK: if total_attempts_used >= config.recovery.max_recovery_attempts (default: 5),
       escalate immediately regardless of per-error-code max_retries. This prevents unbounded
       retries when step 7f re-classifies to a new error code with its own max_retries.
       a. If error_category.requires_diagnosis and (attempt >= 2 or (error_category.max_retries == 1)):
          DIAGNOSE: Call diagnostic_agent.diagnose(diagnostic_input) -> DiagnosticOutput
          Note: the `max_retries == 1` clause handles the special case from Section 4.3 where
          single-retry errors skip Tier 1 and go directly to Tier 2 (Rewrite with Diagnosis).
       b. If error_category.requires_compensation:
          COMPENSATE: Call compensating_actions.compensate(error_code, task_id, db)
       c. STRATEGIZE: Call strategy_selector.select(attempt, error_category, diagnostic_output) -> RecoveryStrategy
          Override rule: if playbooks.has_playbook(error_code), the playbook replaces ONLY the
          STRATEGIZE step (step c). It produces a RecoveryStrategy with pre-defined prompt
          modifications and constraints. The rest of the pipeline (DIAGNOSE, COMPENSATE, EXECUTE,
          VERIFY, LEARN) still runs normally. A playbook does NOT replace the entire recovery loop --
          it just provides a deterministic strategy instead of the generic ladder.
       d. Build RecoveryContext from all above data.
       e. EXECUTE: Call recovery_executor.execute(task_id, recovery_context, db, config) -> RunnerResult
       f. VERIFY: If RunnerResult is success, break loop. If same error, continue loop.
          If different error, re-CLASSIFY (get new ErrorCategory), reset attempt counter to 1
          for the new error code, but total_attempts_used still increments (enforcing global ceiling).
       f2. total_attempts_used += 1
       g. LEARN: Call failure_memory.record(error_code, strategy, success, ...) after each attempt.
       h. Log recovery_event for each stage.
    8. If loop exhausted without success:
       - Set dispatch_status='dispatch_failed' (terminal).
       - Send urgent notification with full history.
    9. If success:
       - The VERIFY step already confirmed the AgentResult is valid.
       - Set dispatch_status='completed' (NOT 'queued'). The recovery executor
         ran the agent and got a valid result -- the task is done.
       - Call the same handle_task_completion() path that the normal supervisor
         uses: write deliverable to working_memory, set tasks.status='completed',
         notify dependents.
       - Do NOT set dispatch_status='queued' for re-dispatch. Re-dispatching
         would discard the successful recovery result and run the agent again.
    10. Return RecoveryOutcome.

    Error handling for the pipeline itself:
    - If any stage raises an unexpected exception, catch it, log to recovery_events
      as event_type='pipeline_error' with the exception details, set dispatch_status
      back to 'failed' (so the next poll cycle can retry recovery), and return a
      RecoveryOutcome with success=False and escalation_reason='recovery_pipeline_internal_error'.
    - The pipeline NEVER leaves a task in dispatch_status='recovering' permanently.
      If the pipeline crashes, supervisor startup recovery resets 'recovering' -> 'failed'.
    """
```

### 9.1.2 STUCK_TASK Detection Sweep

The supervisor poll loop (US-054) must include a STUCK_TASK detection sweep on each cycle. This runs BEFORE the normal task dispatch logic.

```python
def detect_stuck_tasks(db: DispatchDB, config: dict) -> list[int]:
    """
    Called by supervisor on each poll cycle. Detects tasks that appear stuck
    and transitions them to 'failed' with error_code='STUCK_TASK' so the
    recovery pipeline can handle them.

    Detection criteria (ANY triggers classification as stuck):
    1. dispatch_status='dispatched' AND (now - dispatch_runs.started_at) > agent_timeout_seconds
       Meaning: agent has been running longer than the hard timeout.
    2. dispatch_status='dispatched' AND lease extended 3+ times AND tool_calls_count
       unchanged between the last 2 lease extensions.
       Meaning: agent is alive (extending lease) but making no progress.
    3. dispatch_status='recovering' AND (now - last recovery_event timestamp) > 600s
       Meaning: recovery pipeline itself is stuck (safety net).

    For each stuck task:
    1. Set dispatch_status='failed'
    2. Write error_summary='STUCK_TASK: {criterion that matched}'
    3. The next poll cycle's failure handler invokes recovery_pipeline.handle_failure()
       which classifies it as STUCK_TASK (structural error).

    Returns: list of task_ids that were marked as stuck.

    SQL for criterion 1:
      SELECT t.id FROM tasks t
      JOIN dispatch_runs dr ON dr.task_id = t.id AND dr.status = 'running'
      WHERE t.dispatch_status = 'dispatched'
      AND dr.started_at < datetime('now', '-{agent_timeout_seconds} seconds')

    SQL for criterion 2:
      SELECT t.id FROM tasks t
      JOIN dispatch_runs dr ON dr.task_id = t.id AND dr.status = 'running'
      WHERE t.dispatch_status = 'dispatched'
      AND dr.lease_extensions >= 3
      AND dr.tool_calls_count = dr.tool_calls_count_at_last_extension

    Note: criterion 2 requires adding two columns to dispatch_runs:
      - lease_extensions INTEGER DEFAULT 0
      - tool_calls_count_at_last_extension INTEGER DEFAULT 0
    These are updated by the lease extension logic in agent_runner.py.
    """
```

### 9.2 Modifications to Existing (Planned) Files

| File | Modification | Purpose |
|---|---|---|
| `agent-dispatch/agent_runner.py` (US-048) | Add structured error capture on failure. Return `RunnerError` with error_code, raw_output, tool_call_log, stop_reason instead of raising generic exception. | Provides data for Stage 1 (CAPTURE) |
| `agent-dispatch/agent_prompts.py` (US-045) | Add optional `recovery_context: Optional[RecoveryContext]` parameter to `build_prompt()`. When present, inject recovery section from template. | Provides enriched prompt for Stage 6 (EXECUTE) |
| `agent-dispatch/agent_supervisor.py` (US-054) | On task failure, call `recovery_pipeline.handle_failure()` instead of `handle_dispatch_failure()` directly. `handle_dispatch_failure()` becomes a low-level function called by the recovery pipeline. | Integrates recovery pipeline into supervisor loop |
| `agent-dispatch/dispatch_db.py` (US-018) | Add migrations for new columns on `dispatch_runs`, new `failure_memory` and `recovery_events` tables. | Schema support for recovery data |
| `agent-dispatch/migrations.py` | Add `migrate_add_dispatch_runs_recovery_columns()`, `migrate_create_failure_memory()`, `migrate_create_recovery_events()` | New migration functions |
| `agent-dispatch/health/self_healer.py` (US-064) | Add hook: after provider-level healing, check if any tasks should be retried. Expose `is_provider_healthy(provider, model) -> bool` for recovery pipeline. Contract: returns True if the most recent `provider_health` row for this provider/model has `passed=TRUE` AND there is no open (unresolved) incident in `provider_incidents` for this provider. Returns True if no health data exists (assume healthy until proven otherwise). | Cross-system coordination |
| `agent-dispatch/cli.py` (US-081) | Add `openclawd recovery status` subcommand showing active recoveries, and `openclawd recovery history` showing failure_memory patterns. | Observability |

### 9.3 New Prompt File

| File | Purpose |
|---|---|
| `agent-dispatch/prompts/diagnostic_sop.md` | System prompt for the Diagnostic Agent. Adapted from best-practice Section 4.5 but rewritten for OpenClawd's domain (no CI, no git, focus on tools and task completion). |

---

## 10. User Story Impact Analysis

### 10.1 Existing Stories That Need Enhancement

| Story | Current Scope | Enhancement for Self-Healing |
|---|---|---|
| US-048 (`agent_runner.py`) | Tool call loop with depth/loop detection | Return structured `RunnerError` on failure (not just raise). Capture raw_output, tool_call_log, stop_reason. |
| US-045 (`agent_prompts.py`) | Prompt assembly | Accept `recovery_context` parameter. Inject recovery section when present. |
| US-052 (Retry logic) | Flat 3-retry with exponential backoff | Replace with call to `recovery_pipeline.handle_failure()`. Backoff becomes the Tier 1 strategy; further tiers add diagnosis and strategy variation. Increase total attempts from 3 to 5. |
| US-054 (Supervisor poll loop) | Query, claim, dispatch, heartbeat | On agent completion/failure, route through recovery pipeline. Add cross-task pattern detection on each failure. |
| US-064 (5-tier self-healing) | Provider-level healing only | Add coordination hook: notify recovery pipeline when provider switches to fallback. Recovery pipeline checks provider health before retrying. |
| US-065 (Diagnostic report) | Provider failure analysis | Separate from the Diagnostic Agent. `diagnostic_report.py` continues to handle provider-level reports. `diagnostic_agent.py` (new) handles task-level diagnosis. |

### 10.2 New Stories Required

| New Story | Description | Priority | Depends On |
|---|---|---|---|
| US-093 | Create `recovery/error_classifier.py` with error taxonomy lookup table mapping all error codes to categories with recovery parameters | High | US-048 |
| US-094 | Create `recovery/error_capture.py` to extract structured error context from agent failures | High | US-048 |
| US-095 | Create `recovery/diagnostic_agent.py` with Diagnostic Agent prompt, input/output schemas, and LLM call using cheapest configured model | High | US-020, US-021 |
| US-096 | Create `recovery/compensating_actions.py` with per-error-type cleanup actions | Medium | US-093 |
| US-097 | Create `recovery/strategy_selector.py` implementing 5-tier strategy ladder | High | US-093, US-095 |
| US-098 | Create `recovery/recovery_executor.py` to re-run agent with enriched context and verify recovery | High | US-048, US-045 |
| US-099 | Create `recovery/failure_memory.py` with `failure_memory` table, similarity matching, and pattern detection | Medium | US-018 |
| US-100 | Create `recovery/recovery_pipeline.py` orchestrating all 8 stages | High | US-093 through US-099 |
| US-101 | Create `failure_memory` and `recovery_events` database tables with migrations | Medium | US-018 |
| US-102 | Add `raw_output`, `tool_call_log`, `stop_reason`, `error_context`, `recovery_tier`, `recovery_strategy`, `lease_extensions`, `tool_calls_count_at_last_extension` columns to `dispatch_runs` | Medium | US-018, US-101 (must run AFTER US-101 migration to maintain migration ordering) |
| US-103 | Create `prompts/diagnostic_sop.md` system prompt for the Diagnostic Agent | Medium | None |
| US-104 | Create `recovery/playbooks.py` with deterministic playbook sequences for each error code | Medium | US-093 |
| US-105 | Add `recovering` to `dispatch_status` valid states (test CHECK constraint enforcement, implement table rebuild migration if needed) | High | US-001 |
| US-106 | Integrate recovery pipeline into supervisor poll loop: on task failure, call `recovery_pipeline.handle_failure()` instead of flat retry | High | US-054, US-100 |
| US-107 | Add cross-task pattern detection: when 3+ tasks fail with same error in 10 minutes, trigger provider-level healing instead of individual task recovery | Medium | US-099, US-064 |
| US-108 | Add `openclawd recovery status` and `openclawd recovery history` CLI commands | Low | US-081, US-100 |
| US-109 | Add recovery-specific structured log events (recovery.capture, recovery.classify, etc.) | Low | US-071 |
| US-110 | Implement max concurrent recoveries limit (default 3) with queuing for excess | Medium | US-100, US-054 |

### 10.3 Acceptance Criteria for New Stories

**US-093 (error_classifier.py):**
- `ERROR_TAXONOMY` dict contains all 37 error codes from Section 3 with correct `ErrorCategory` values.
- `detect_error_code(exception, http_status, agent_result, context) -> str` correctly maps: `anthropic.RateLimitError -> RATE_LIMITED`, `requests.Timeout -> PROVIDER_TIMEOUT`, `json.JSONDecodeError on agent output -> RESULT_PARSE_FAILED`, `AgentResult.status == "failed" -> AGENT_SELF_REPORTED_FAILURE`, `AgentResult.confidence_score < threshold -> CONFIDENCE_TOO_LOW`.
- `classify_error(error_code) -> ErrorCategory` returns the matching entry or `DEFAULT_CATEGORY` for unknown codes.
- Unit tests for all 37 error codes confirming correct classification.

**US-094 (error_capture.py):**
- `capture(runner_error: RunnerError, task_id: int, db: DispatchDB) -> ErrorContext` extracts all data points from Section 4.2.
- Writes `error_context` JSON to `dispatch_runs` row.
- Stores `raw_output` truncated to 10000 chars with `[TRUNCATED]` marker.
- Stores `tool_call_log` as JSON array.
- Post-completion check: if `AgentResult.status == "completed"` and deliverable has < 3 URLs, set `error_code = INCOMPLETE_RESEARCH` (for research agents only).
- Unit tests with mock `RunnerError` instances.

**US-095 (diagnostic_agent.py):**
- `diagnose(input: DiagnosticInput, db: DispatchDB, config: dict) -> DiagnosticOutput` makes a single LLM call using `recovery.diagnostic_model` (default: `claude-haiku-4-5`).
- Assembles prompt from `diagnostic_sop.md` + `DiagnosticInput` fields.
- Truncation: if assembled context > `recovery.diagnostic_max_input_tokens` (default: 4000 tokens), truncate (1) `tool_call_log` to last 10 entries, (2) `raw_agent_output` to 1000 chars, (3) `previous_attempts` to 1-line summaries.
- Parses LLM response as JSON. Parsing algorithm: (1) Try `json.loads(response)`. (2) If fails, regex search for `\{[\s\S]*\}` to extract JSON block. (3) If still fails, return `DiagnosticOutput` with `root_cause="Diagnostic parse failed"`, `confidence=0.0`, `recommended_strategy="escalate"`.
- Returns valid `DiagnosticOutput` dataclass.
- Unit test with mock provider returning known JSON.

**US-096 (compensating_actions.py):**
- `compensate(error_code: str, task_id: int, agent_name: str, db: DispatchDB) -> list[str]` returns list of actions taken.
- Actions per error code: `TOOL_LOOP_DETECTED`/`TOOL_DEPTH_EXCEEDED` -> clear working_memory for agent+task, log abandoned output. `CONTRADICTORY_OUTPUT` -> clear working_memory for agent+task. `STUCK_TASK` -> reset lease_until to NULL. `COMPLETION_SEQUENCE_STUCK` -> defer to US-051 sweep.
- For errors without `requires_compensation=True`, returns empty list.
- Unit tests for each compensating action.

**US-097 (strategy_selector.py):**
- `select(attempt: int, category: ErrorCategory, diagnostic: Optional[DiagnosticOutput], failure_history: list) -> RecoveryStrategy` returns strategy matching the tier from Section 4.3.
- Attempt 1 -> Fix Specific. Attempt 2 -> Rewrite with Diagnosis. Attempt 3 -> Simplify + Constrain. Attempt 4 -> Recommend Decomposition (manual). Attempt 5 -> Escalate.
- When `max_retries=1` and `requires_diagnosis=True`, use Tier 2 (Rewrite with Diagnosis) directly on the single retry attempt.
- Checks `failure_memory` for similar past fixes and incorporates into strategy.
- Unit tests for each tier selection.

**US-098 (recovery_executor.py):**
- `execute(task_id: int, recovery_context: RecoveryContext, db: DispatchDB, config: dict) -> RunnerResult` re-runs the agent via `agent_runner.run()` with recovery context injected.
- Passes `RecoveryContext` to `agent_prompts.build_prompt()` for enriched prompt.
- After execution, verifies: (a) no error -> success, (b) same error code as original -> continue recovery, (c) different error -> re-classify as new error.
- Records `recovery_tier` and `recovery_strategy` on the `dispatch_runs` row.
- Unit test with mock agent runner.

**US-099 (failure_memory.py):**
- `record(error_code, agent_name, task_domain, strategy, tier, attempt, success, resolution_summary, ...) -> int` writes to `failure_memory` table, returns row ID.
- `find_similar_fixes(error_code, agent_name, task_domain) -> list[dict]` implements three-tier SQL lookup from Section 5.5.
- `detect_patterns(error_code, window_minutes=10) -> Optional[dict]` returns pattern info if 3+ tasks failed with same error in window.
- Retention cleanup: `cleanup(retention_days=90)` deletes old entries.
- Unit tests for write, three-tier lookup, and pattern detection.

**US-100 (recovery_pipeline.py):**
- `handle_failure(task_id, runner_error, db, config) -> RecoveryOutcome` implements full control flow from Section 9.1.1.
- Orchestrates all 8 stages in correct order.
- Logs `recovery_events` for every stage transition.
- Checks recovery budget before each attempt.
- Handles pipeline-internal errors gracefully (catch, log, reset to 'failed').
- Integration test: full pipeline run with mock provider.

**US-101 (database tables):**
- `migrate_create_failure_memory()` creates `failure_memory` table matching Section 8.3 schema exactly.
- `migrate_create_recovery_events()` creates `recovery_events` table matching Section 8.4 schema exactly.
- All indexes from Section 8.3 and 8.4 are created.
- Retention cleanup function exists.
- Migration is idempotent (`CREATE TABLE IF NOT EXISTS`).

**US-102 (dispatch_runs columns):**
- All 8 new columns from Section 8.1 are added via `ALTER TABLE`: `raw_output`, `tool_call_log`, `stop_reason`, `error_context`, `recovery_tier`, `recovery_strategy`, `lease_extensions`, `tool_calls_count_at_last_extension`.
- Migration runs AFTER US-101 to maintain ordering.
- All columns are nullable or have defaults (existing rows unaffected).
- Unit test: write and read each new column.

**US-103 (diagnostic_sop.md):**
- Prompt file exists at `agent-dispatch/prompts/diagnostic_sop.md`.
- Content matches Appendix A adapted for OpenClawd domain.
- Includes all 6 rules and the JSON output format.
- Prompt fits within 1500 tokens (measured with tiktoken or equivalent).

**US-104 (playbooks.py):**
- `has_playbook(error_code: str) -> bool` returns True for error codes with deterministic recovery sequences.
- `get_playbook(error_code: str) -> list[PlaybookStep]` returns ordered steps for the error code.
- Playbooks exist for all 7 scenarios from Section 7.
- When a playbook exists, it replaces only the STRATEGIZE step; all other pipeline stages (DIAGNOSE, COMPENSATE, EXECUTE, VERIFY, LEARN) still run normally.
- Unit tests for each playbook.

**US-105 (recovering status):**
- Unit test confirms `'recovering'` can be written to and read from `dispatch_status` column.
- `'recovering'` is excluded from the dispatchable task query (tasks with this status are not picked up for dispatch).
- Supervisor startup recovery resets `'recovering'` -> `'failed'`.

**US-106 (supervisor integration):**
- `agent_supervisor.py` calls `recovery_pipeline.handle_failure()` on task failure instead of `handle_dispatch_failure()` directly.
- `handle_dispatch_failure()` becomes a low-level function called internally by the recovery pipeline for flat retry (Tier 1 transient only).
- Integration test: task failure triggers recovery pipeline.

**US-107 (cross-task patterns):**
- On each new failure, calls `failure_memory.detect_patterns()`.
- If systemic pattern detected (3+ same error in 10 min), triggers provider-level healing via `health/self_healer.py`.
- Holds affected tasks with `next_retry_at` = 5 minutes from now.
- Sends high-urgency notification.
- Unit test with mock failures.

**US-108 (CLI commands):**
- `openclawd recovery status` outputs: task_id, error_code, recovery_tier, attempt, started_at for all tasks with `dispatch_status='recovering'`.
- `openclawd recovery history` outputs: error_code, count, success_rate, last_seen for the top 20 error codes in `failure_memory`.
- Both commands work with `--json` flag for machine-readable output.

**US-109 (log events):**
- All recovery event types from Section 5.7 are emitted as structured JSON log entries.
- Log entries include: `event_type`, `task_id`, `trace_id`, `timestamp`, `details`.
- `openclawd logs --recovery` filter shows only recovery-related log entries.

**US-110 (concurrent recovery limit):**
- Before starting recovery, checks `SELECT COUNT(*) FROM tasks WHERE dispatch_status='recovering'`.
- If >= `recovery.max_concurrent_recoveries` (default: 3), sets `next_retry_at` = 60s from now and returns.
- Configurable via `openclawd.config.yaml` under `recovery.max_concurrent_recoveries`.
- Unit test: verify deferral when limit reached.

### 10.4 Story Dependency Graph

```
US-018 (dispatch_db.py) [BUILT]
  |
  +-> US-101 (failure_memory + recovery_events tables)
  |     |
  |     +-> US-102 (dispatch_runs recovery columns) -- must run AFTER US-101

US-048 (agent_runner.py) [NOT BUILT]
  |
  +-> US-093 (error_classifier)
  +-> US-094 (error_capture)
  |     |
  |     +-> US-096 (compensating_actions)
  |     +-> US-104 (playbooks)
  |
  +-> US-098 (recovery_executor)

US-020/021 (provider base + registry) [NOT BUILT]
  |
  +-> US-095 (diagnostic_agent)
  |     |
  |     +-> US-097 (strategy_selector)
  |
  +-> US-103 (diagnostic SOP prompt)

US-099 (failure_memory module) depends on US-101 (tables)

US-100 (recovery_pipeline) depends on US-093, 094, 095, 096, 097, 098, 099

US-106 (supervisor integration) depends on US-054, US-100

US-107 (cross-task patterns) depends on US-099, US-064
```

---

## 11. Implementation Phasing

Given that OpenClawd is approximately 1/3 built (Phase 1 foundation complete, Phases 2-6 not started), the self-healing system should be integrated as follows:

### Phase A: Build Recovery Foundations (alongside Phase 3/4 of main spec)

Build the recovery infrastructure while the agent execution pipeline is being built. This ensures that when `agent_runner.py` and `agent_supervisor.py` are implemented, they can integrate recovery from day one.

**Stories:** US-093, US-094, US-101, US-102, US-103, US-105

**Testing strategy:** Since the agent runner and provider abstraction do not exist yet, Phase A tests use mock objects. Create `tests/mocks/mock_runner_error.py` that returns pre-built `RunnerError` instances for each error code. Tests validate that `error_classifier.classify()` returns the correct `ErrorCategory` and that `error_capture.capture()` produces valid `ErrorContext` from mock data. No real LLM calls in Phase A tests.

**Hard dependencies from main spec:** US-018 (dispatch_db.py) must be complete (it is). US-001 (schema) must be complete (it is). No other main-spec dependencies block Phase A.

**Completion criteria:** Phase A is complete when: (1) All 37 error codes in `ERROR_TAXONOMY` have unit tests confirming correct classification. (2) `error_capture.py` can produce structured `ErrorContext` from a mock `RunnerError`. (3) All 3 new database tables/columns exist with migration functions. (4) `diagnostic_sop.md` prompt exists and has been reviewed. (5) `'recovering'` status can be written to `dispatch_status` (verified by unit test).

**Rationale:** Error classification, error capture, and database schemas are foundational. They do not require a working agent pipeline to build. The Diagnostic Agent prompt can be written before the LLM providers are fully wired up.

### Phase B: Build Recovery Logic (alongside Phase 4 of main spec)

Build the recovery pipeline stages once the agent runner exists.

**Stories:** US-095, US-096, US-097, US-098, US-099, US-104

**Hard dependencies from main spec:** US-048 (agent_runner.py) and US-020/US-021 (provider base + registry) must be complete before Phase B can start. Phase A must be fully complete.

**Completion criteria:** Phase B is complete when: (1) `diagnostic_agent.py` can make a real LLM call (using test provider) and return valid `DiagnosticOutput`. (2) `compensating_actions.py` has actions for all error codes with `requires_compensation=True`. (3) `strategy_selector.py` returns correct strategy for each tier 1-5. (4) `recovery_executor.py` can re-run an agent with `RecoveryContext` injected. (5) `failure_memory.py` can write and query the three-tier similarity lookup. (6) `playbooks.py` has deterministic sequences for all 7 playbook scenarios from Section 7.

**Rationale:** These modules need `agent_runner.py` to exist so they can re-run agents with recovery context. The Diagnostic Agent (US-095) needs the provider abstraction layer to make LLM calls.

### Phase C: Integrate and Wire Up (alongside Phase 5 of main spec)

Wire the recovery pipeline into the supervisor loop and health system.

**Stories:** US-100, US-106, US-107, US-110

**Hard dependencies from main spec:** US-054 (supervisor poll loop) and US-064 (5-tier self-healing) must be complete. Phase B must be fully complete.

**Completion criteria:** Phase C is complete when: (1) `recovery_pipeline.handle_failure()` orchestrates all 8 stages end-to-end. (2) Supervisor calls `handle_failure()` on task failure instead of flat retry. (3) Cross-task pattern detection triggers provider-level healing when 3+ tasks fail with same error in 10 minutes. (4) Max concurrent recoveries limit is enforced with deferred retry. (5) Integration test: inject a `RESULT_PARSE_FAILED` error and verify the full pipeline runs through classify -> diagnose -> strategize -> execute -> verify -> learn.

**Rationale:** The orchestration layer (`recovery_pipeline.py`) coordinates all stages. It integrates into the supervisor's failure handling path. Cross-task pattern detection bridges the gap between task-level and provider-level healing.

### Phase D: Observability and CLI (alongside Phase 6 of main spec)

Add visibility into recovery operations.

**Stories:** US-108, US-109

**Hard dependencies from main spec:** US-081 (CLI framework) and US-071 (structured logging) must be complete. Phase C must be fully complete.

**Completion criteria:** Phase D is complete when: (1) `openclawd recovery status` shows active recoveries with task_id, error_code, tier, and attempt. (2) `openclawd recovery history` shows failure_memory patterns with success/failure rates per error_code. (3) All recovery-specific log events from Section 5.7 are emitted during recovery runs. (4) Recovery events are visible in `openclawd logs --recovery` filter.

**Rationale:** CLI commands and logging events are polish. They require the recovery system to be functional before they can display anything useful.

---

## 12. Success Metrics Adapted for OpenClawd

| Metric | Target | How to Measure (SQL) |
|---|---|---|
| First-attempt success rate | > 70% | `SELECT CAST(SUM(CASE WHEN attempt_number = 1 AND status = 'completed' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) FROM dispatch_runs WHERE attempt_number = 1 AND created_at > datetime('now', '-7 days')` |
| Tier 1 recovery success rate | > 50% | `SELECT CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) FROM failure_memory WHERE recovery_tier = 1 AND created_at > datetime('now', '-7 days')` |
| Overall automatic recovery rate | > 75% | `SELECT 1.0 - (CAST(SUM(CASE WHEN dispatch_status = 'dispatch_failed' THEN 1 ELSE 0 END) AS REAL) / COUNT(*)) FROM tasks WHERE dispatch_status IN ('completed', 'dispatch_failed') AND updated_at > datetime('now', '-7 days')` |
| Mean time to recovery | < 10 minutes | `SELECT AVG(re_end.duration_ms) FROM recovery_events re_end WHERE re_end.event_type = 'recovery_succeeded' AND re_end.created_at > datetime('now', '-7 days')` (uses `total_duration_ms` from the `recovery_succeeded` event details JSON) |
| Human escalation rate | < 25% | Inverse of overall automatic recovery rate: `CAST(SUM(CASE WHEN dispatch_status = 'dispatch_failed' THEN 1 ELSE 0 END) AS REAL) / COUNT(*)` from same query |
| Diagnostic Agent accuracy | > 70% | Of Tier 2+ recoveries that succeeded: `SELECT CAST(SUM(CASE WHEN fm.diagnostic_summary IS NOT NULL AND fm.success = 1 THEN 1 ELSE 0 END) AS REAL) / NULLIF(SUM(CASE WHEN fm.recovery_tier >= 2 AND fm.success = 1 THEN 1 ELSE 0 END), 0) FROM failure_memory fm WHERE fm.recovery_tier >= 2 AND fm.created_at > datetime('now', '-7 days')`. Note: this measures "did the diagnostic contribute to a successful recovery" not "did the diagnostic predict the exact strategy." True accuracy requires comparing `DiagnosticOutput.recommended_strategy` to the `recovery_strategy` that actually succeeded, tracked in `failure_memory.recovery_strategy`. |
| Recovery cost ratio | < 0.3x | `SELECT SUM(CASE WHEN dr.recovery_tier IS NOT NULL THEN dr.cost_estimate ELSE 0 END) / NULLIF(SUM(CASE WHEN dr.recovery_tier IS NULL THEN dr.cost_estimate ELSE 0 END), 0) FROM dispatch_runs dr WHERE dr.created_at > datetime('now', '-7 days')` |
| Repeat failure rate | < 15% | `SELECT CAST(COUNT(DISTINCT fm2.id) AS REAL) / NULLIF(COUNT(DISTINCT fm1.id), 0) FROM failure_memory fm1 JOIN failure_memory fm2 ON fm1.error_code = fm2.error_code AND fm1.task_domain = fm2.task_domain AND fm2.created_at > fm1.created_at AND fm2.created_at < datetime(fm1.created_at, '+7 days') WHERE fm1.success = 1 AND fm1.created_at > datetime('now', '-30 days')` |
| Cross-task pattern detection time | < 5 minutes | `SELECT AVG(julianday(re.created_at) - julianday(MIN(dr.started_at))) * 86400000 FROM recovery_events re JOIN dispatch_runs dr ON re.details LIKE '%systemic%' WHERE re.event_type = 'escalated' AND re.created_at > datetime('now', '-7 days')` (approximate -- exact measurement requires correlating first failure timestamp with systemic alert timestamp) |
| Provider fallback success rate | > 90% | `SELECT CAST(SUM(CASE WHEN dr.status = 'completed' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) FROM dispatch_runs dr WHERE dr.recovery_strategy LIKE '%fallback%' AND dr.created_at > datetime('now', '-7 days')` |

Note: These targets are less aggressive than the best-practice doc (which targets >85% automatic recovery and <15% escalation). OpenClawd's agents operate in less deterministic domains (research, analysis) where "correct output" is harder to verify automatically. A 75% automatic recovery rate with 25% escalation is a realistic starting target.

---

## Appendix A: Diagnostic Agent Prompt for OpenClawd

File: `agent-dispatch/prompts/diagnostic_sop.md`

```markdown
You are a Diagnostic Agent for the OpenClawd multi-agent orchestration system.
Your job is to analyze why an agent task failed and recommend a recovery strategy.

You are NOT implementing the fix. You are providing analysis and recommendations
that the recovery system will use to configure the next retry attempt.

## Rules
1. Be specific. "The agent failed" is not a diagnosis. "The agent called web_search
   3 times with query 'competitive analysis widget market' and received empty results
   each time, indicating the query is too specific or the search API returned no data"
   is a diagnosis.
2. Always reference the evidence. Your diagnosis must be grounded in the error context,
   tool call history, or agent output -- never speculative.
3. If you cannot determine the root cause from the available evidence, say so.
   Low confidence is better than a wrong diagnosis.
4. Check for cycles. If the same error occurred on previous attempts, the previous
   strategy did not work. Recommend a fundamentally different approach.
5. Consider whether the TASK DESCRIPTION might be unclear, not just the agent's execution.
   Sometimes agents fail because the task is ambiguous or impossible as stated.
6. Consider whether the TOOLS are the right ones for this task. If web_search keeps
   failing, maybe database_query or python_exec would work better.

## Output Format
Respond with a JSON object:
{
  "root_cause": "Human-readable explanation of why the failure occurred",
  "root_cause_category": "tool_failure | output_format | task_ambiguity | resource_limit | approach_wrong | unknown",
  "confidence": 0.0 to 1.0,
  "recommended_strategy": "fix_specific | rewrite_with_guidance | simplify | decompose | escalate",
  "specific_fix": "Detailed instructions for the agent on the next attempt, or null",
  "tools_to_adjust": ["list of tools to use differently or avoid"],
  "avoid_approaches": ["list of approaches that should NOT be repeated"],
  "needs_human": true/false,
  "human_action_needed": "What the human should do, or null",
  "is_repeat_failure": true/false,
  "cycle_detected": true/false
}
```

**Parsing the Diagnostic Agent's response:**

The `diagnostic_agent.py` module parses the LLM response into `DiagnosticOutput` using this algorithm:

1. Try `json.loads(response_text)` on the full response.
2. If that fails, search for the first `{...}` block using regex `r'\{[\s\S]*\}'` and try `json.loads()` on the match.
3. If that also fails, return a fallback `DiagnosticOutput` with `root_cause="Diagnostic parse failed: could not extract JSON from response"`, `confidence=0.0`, `recommended_strategy="escalate"`, `needs_human=True`. Log the raw response for debugging.
4. If JSON parsing succeeds but required fields are missing, fill them with defaults: `confidence=0.5`, `recommended_strategy="fix_specific"`, `tools_to_adjust=[]`, `avoid_approaches=[]`, `needs_human=False`.

---

## Appendix B: Error Taxonomy Lookup Table

File: `agent-dispatch/recovery/error_classifier.py` (data structure)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ErrorCategory:
    category: str                   # transient, execution, logic, structural, configuration, resource
    max_retries: int                # Max recovery attempts for THIS specific error code (overrides category default)
    requires_diagnosis: bool        # Whether Diagnostic Agent should be invoked (Tier 2+)
    requires_compensation: bool     # Whether compensating actions should run before retry
    initial_backoff_seconds: int    # Delay before first retry (0 = immediate)
    backoff_multiplier: float       # Multiplier for subsequent retries
    max_backoff_seconds: int        # Cap on backoff delay
    compensating_action_keys: tuple = ()  # Keys for compensating_actions.py dispatch
                                          # Valid keys: "clear_working_memory", "reset_lease",
                                          # "log_abandoned_output", "defer_to_us051"

ERROR_TAXONOMY = {
    # Transient errors
    "RATE_LIMITED":              ErrorCategory("transient", 5, False, False, 30, 2.0, 300),
    "PROVIDER_5XX":             ErrorCategory("transient", 5, False, False, 30, 2.0, 300),
    "PROVIDER_TIMEOUT":         ErrorCategory("transient", 5, False, False, 30, 2.0, 300),
    "NETWORK_ERROR":            ErrorCategory("transient", 5, False, False, 30, 2.0, 300),
    "SEARCH_API_UNAVAILABLE":   ErrorCategory("transient", 3, False, False, 30, 2.0, 120),
    "DB_LOCKED":                ErrorCategory("transient", 3, False, False, 5, 2.0, 30),
    "TOOL_TIMEOUT":             ErrorCategory("transient", 2, False, False, 10, 2.0, 60),

    # Execution errors
    "RESULT_SCHEMA_INVALID":    ErrorCategory("execution", 3, True, False, 0, 1, 0),
    "RESULT_PARSE_FAILED":      ErrorCategory("execution", 3, True, False, 0, 1, 0),
    "DELIVERABLE_EMPTY":        ErrorCategory("execution", 3, True, False, 0, 1, 0),
    "DELIVERABLE_TRUNCATED":    ErrorCategory("execution", 2, True, False, 0, 1, 0),
    "STATUS_INVALID":           ErrorCategory("execution", 3, False, False, 0, 1, 0),
    "CONFIDENCE_TOO_LOW":       ErrorCategory("execution", 2, True, False, 0, 1, 0),
    "TOOL_RESULT_MALFORMED":    ErrorCategory("execution", 2, True, False, 0, 1, 0),
    "AGENT_SELF_REPORTED_FAILURE": ErrorCategory("execution", 2, True, False, 0, 1, 0),

    # Logic errors
    "VALIDATION_REJECTED":      ErrorCategory("logic", 2, True, False, 0, 1, 0),
    "TASK_MISMATCH":            ErrorCategory("logic", 2, True, False, 0, 1, 0),
    "INCOMPLETE_RESEARCH":      ErrorCategory("logic", 2, True, False, 0, 1, 0),
    "STALE_DATA":               ErrorCategory("logic", 1, True, False, 0, 1, 0),
    "CONTRADICTORY_OUTPUT":     ErrorCategory("logic", 2, True, True, 0, 1, 0, ("clear_working_memory",)),

    # Structural errors
    "TOOL_LOOP_DETECTED":       ErrorCategory("structural", 2, True, True, 0, 1, 0, ("clear_working_memory", "log_abandoned_output")),
    "TOOL_DEPTH_EXCEEDED":      ErrorCategory("structural", 2, True, True, 0, 1, 0, ("clear_working_memory", "log_abandoned_output")),
    "STUCK_TASK":               ErrorCategory("structural", 2, True, True, 0, 1, 0, ("reset_lease", "log_abandoned_output")),
    "DEPENDENCY_DEADLOCK":      ErrorCategory("structural", 0, False, False, 0, 1, 0),
    "COMPLETION_SEQUENCE_STUCK":ErrorCategory("structural", 3, False, True, 5, 2.0, 30, ("defer_to_us051",)),

    # Configuration errors
    "API_KEY_MISSING":          ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "API_KEY_INVALID":          ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "PROVIDER_NOT_CONFIGURED":  ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "TOOL_NOT_AVAILABLE":       ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "AGENT_NOT_FOUND":          ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "DB_SCHEMA_INCOMPATIBLE":   ErrorCategory("configuration", 0, False, False, 0, 1, 0),
    "SEARCH_API_NO_KEYS":       ErrorCategory("configuration", 0, False, False, 0, 1, 0),

    # Resource errors
    "GLOBAL_BUDGET_EXCEEDED":   ErrorCategory("resource", 0, False, False, 0, 1, 0),
    "AGENT_BUDGET_EXCEEDED":    ErrorCategory("resource", 0, False, False, 0, 1, 0),
    "CONTEXT_OVERFLOW":         ErrorCategory("resource", 1, False, False, 0, 1, 0),
    "MAX_TOKENS_EXCEEDED":      ErrorCategory("resource", 1, False, False, 0, 1, 0),
    "DISK_SPACE_LOW":           ErrorCategory("resource", 0, False, False, 0, 1, 0),
}

# Default for unknown errors: treat as execution error with diagnosis
DEFAULT_CATEGORY = ErrorCategory("execution", 2, True, False, 0, 1, 0)
```

---

## Appendix C: Core Dataclass Definitions for OpenClawd Recovery

### C.1 RecoveryContext (passed to agent_prompts.py for enriched retries)

File: `agent-dispatch/recovery/recovery_pipeline.py`

```python
@dataclass
class RecoveryContext:
    """Injected into agent prompts on recovery retries via agent_prompts.py."""
    attempt_number: int                     # Current recovery attempt (1-indexed)
    total_max_attempts: int                 # Maximum attempts allowed (from ErrorCategory.max_retries)
    error_code: str                         # Error code from Section 3 taxonomy
    error_message: str                      # Human-readable error description
    error_category: str                     # transient, execution, logic, structural, configuration, resource
    previous_raw_output: Optional[str]      # First 500 chars of previous attempt's raw_output (None on attempt 1)
    tool_call_summary: Optional[str]        # "{count} tool calls: {tool1} x{n}, {tool2} x{m}" (None if no tools)
    diagnostic_analysis: Optional[str]      # DiagnosticOutput.root_cause (None if no diagnosis ran)
    specific_fix: Optional[str]             # DiagnosticOutput.specific_fix (None if no diagnosis ran)
    strategy_name: str                      # Strategy from ladder: fix_specific, rewrite_with_diagnosis, simplify, decompose, escalate
    strategy_description: str               # Human-readable strategy instructions
    constraints: list[str]                  # List of constraints, e.g. ["Do NOT use web_search", "Keep response under 10000 chars"]
    previous_attempts: list                 # List of PreviousAttemptSummary (see C.4)
    similar_past_fixes: list[str]           # Resolution summaries from failure_memory, max 3
```

### C.2 RunnerError (returned by agent_runner.py on failure)

File: `agent-dispatch/agent_runner.py`

```python
@dataclass
class RunnerError:
    """Structured error returned by agent_runner.py instead of raising generic exceptions."""
    error_code: str                         # Error code from Section 3 taxonomy (e.g., RESULT_PARSE_FAILED)
    error_message: str                      # Human-readable description
    raw_output: Optional[str]               # Full raw LLM response text (may be None if provider error)
    tool_call_log: Optional[list[dict]]     # List of {"tool": str, "args": dict, "result_summary": str, "duration_ms": int}
    stop_reason: Optional[str]              # LLM stop reason: end_turn, tool_use, max_tokens
    tokens_used: int                        # Total tokens consumed (input + output)
    provider: str                           # Provider name (e.g., "anthropic")
    model: str                              # Model used (e.g., "claude-haiku-4-5")
    http_status: Optional[int]              # HTTP status code if provider error (e.g., 429, 500), None otherwise
    exception_type: Optional[str]           # Python exception class name if applicable (e.g., "RateLimitError")
    duration_ms: int                        # Wall clock time for the agent run
    agent_result: Optional[dict]            # Parsed AgentResult dict if parsing succeeded but validation failed, None otherwise
```

### C.3 Diagnostic Agent Input/Output Schemas

File: `agent-dispatch/recovery/diagnostic_agent.py` (dataclass definitions)

```python
@dataclass
class DiagnosticInput:
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
    raw_agent_output: Optional[str]     # What the agent produced (truncated to 2000 chars)
    tool_call_log: Optional[list]       # List of tool calls with results
    stop_reason: Optional[str]          # end_turn, tool_use, max_tokens
    tokens_used: int

    # History
    attempt_number: int
    previous_attempts: list             # List of {strategy, error_code, diagnostic_summary}

    # Known patterns
    similar_past_fixes: list            # From failure_memory

@dataclass
class DiagnosticOutput:
    root_cause: str
    root_cause_category: str            # tool_failure, output_format, task_ambiguity,
                                        # resource_limit, approach_wrong, unknown
    confidence: float                   # 0.0 - 1.0
    recommended_strategy: str           # fix_specific, rewrite_with_guidance, simplify,
                                        # decompose, escalate
    specific_fix: Optional[str]         # Detailed instructions for the agent
    tools_to_adjust: list               # Tools to use differently or avoid
    avoid_approaches: list              # Approaches that should not be repeated
    needs_human: bool
    human_action_needed: Optional[str]
    is_repeat_failure: bool
    cycle_detected: bool
```

### C.4 PreviousAttemptSummary (used in RecoveryContext.previous_attempts)

File: `agent-dispatch/recovery/recovery_pipeline.py`

```python
@dataclass
class PreviousAttemptSummary:
    """Summary of a prior recovery attempt, included in RecoveryContext for the agent."""
    attempt_number: int                     # Which attempt this was
    strategy_used: str                      # Strategy name from ladder
    error_code: str                         # Error that occurred
    error_message: str                      # Brief error description (max 200 chars)
    diagnostic_summary: Optional[str]       # One-line diagnostic root cause, or None
    tools_used: list[str]                   # Tool names called during this attempt
    duration_ms: int                        # How long the attempt took
```

### C.5 RecoveryStrategy (returned by strategy_selector.select())

File: `agent-dispatch/recovery/strategy_selector.py`

```python
@dataclass
class RecoveryStrategy:
    """Describes the recovery approach for a specific retry attempt."""
    strategy_name: str                      # fix_specific, rewrite_with_diagnosis, simplify, decompose, escalate
    tier: int                               # 1-5
    strategy_description: str               # Human-readable instructions for the recovery prompt
    constraints: list[str]                  # Restrictions to add to recovery prompt
    prompt_modifications: dict              # e.g., {"max_tool_iterations": 10, "excluded_tools": ["web_search"]}
    scope_reduction: Optional[str]          # Instruction for simplifying the task scope, or None
    is_terminal: bool                       # True for decompose/escalate (no automatic retry after this)
```

### C.6 PlaybookStep (used in playbooks.py)

File: `agent-dispatch/recovery/playbooks.py`

```python
@dataclass
class PlaybookStep:
    """A single step in a deterministic recovery playbook."""
    stage: str                              # Pipeline stage: classify, diagnose, compensate, strategize, execute
    action: str                             # What to do (e.g., "retry_with_backoff", "switch_provider", "escalate")
    parameters: dict                        # Stage-specific parameters (e.g., {"backoff_seconds": 30, "provider": "openai"})
    condition: Optional[str]                # When this step applies (e.g., "if all APIs in fallback chain failed"), or None for always

@dataclass
class Playbook:
    """A deterministic recovery sequence for a specific error code."""
    error_code: str                         # The error code this playbook handles
    steps: list[PlaybookStep]               # Ordered steps to execute
    def select_strategy(self, attempt: int, error: 'RunnerError', classification: 'ErrorCategory') -> 'RecoveryStrategy':
        """Select the appropriate RecoveryStrategy for the given attempt number.
        Uses the playbook's deterministic steps to produce prompt modifications
        and constraints instead of the generic strategy ladder. The rest of the
        pipeline (DIAGNOSE, COMPENSATE, EXECUTE, VERIFY, LEARN) still runs
        normally -- only the STRATEGIZE step is replaced."""
        ...
```

### C.7 ErrorContext (returned by error_capture.capture())

File: `agent-dispatch/recovery/error_capture.py`

```python
@dataclass
class ErrorContext:
    """Structured error context extracted during the CAPTURE stage."""
    error_code: str                         # Canonical error code from detect_error_code()
    error_category: str                     # Category from classify_error()
    error_message: str                      # Human-readable error description
    error_pattern: Optional[str]            # Normalized pattern for similarity matching (see Section 8.3)
    task_id: int
    agent_name: str
    task_domain: str
    raw_output: Optional[str]               # Truncated to recovery.raw_output_max_chars (default 10000)
    tool_call_log: Optional[list[dict]]     # Tool call history from RunnerError
    stop_reason: Optional[str]              # LLM stop reason
    tokens_used: int
    provider: str                           # Provider name
    model: str                              # Model used
    duration_ms: int                        # Wall clock time
    captured_at: str                        # ISO 8601 timestamp
```

### C.8 RunnerResult (returned by agent_runner.run() and recovery_executor.execute())

File: `agent-dispatch/agent_runner.py`

```python
@dataclass
class RunnerResult:
    """Result of an agent execution, whether successful or failed."""
    success: bool                           # True if agent produced valid AgentResult with status != 'failed'
    agent_result: Optional[dict]            # Parsed AgentResult dict on success, None on failure
    error: Optional['RunnerError']          # RunnerError on failure, None on success
    tokens_used: int                        # Total tokens consumed
    duration_ms: int                        # Wall clock time
    stop_reason: Optional[str]             # LLM stop reason
    tool_calls_count: int                   # Number of tool calls made
```

### C.9 RecoveryOutcome (returned by recovery_pipeline.handle_failure())

File: `agent-dispatch/recovery/recovery_pipeline.py`

```python
@dataclass
class RecoveryOutcome:
    """Result of the full recovery pipeline for a single task failure."""
    task_id: int
    success: bool                           # True if recovery resolved the failure
    final_status: str                       # dispatch_status to set: 'completed' (success), 'failed' (retryable), 'dispatch_failed' (terminal)
    attempts_used: int                      # How many recovery attempts were executed
    winning_strategy: Optional[str]         # Strategy that worked, or None
    escalation_reason: Optional[str]        # Why escalated, or None if recovered
    total_duration_ms: int                  # Wall clock from start to finish
    total_cost_usd: float                   # Estimated cost of all recovery attempts
    error_code: str                         # Original error code
    trace_id: str                           # Trace ID for correlating recovery_events
```

---

## Appendix D: Integration Checklist

When implementing, verify each of these integration points is wired correctly:

- [ ] `agent_runner.py` -> `error_capture.py`: On any failure, capture structured error context before returning
- [ ] `agent_supervisor.py` -> `recovery_pipeline.py`: On task failure, call `handle_failure()` instead of direct retry
- [ ] `recovery_pipeline.py` -> `error_classifier.py`: Classify every captured error
- [ ] `recovery_pipeline.py` -> `diagnostic_agent.py`: For non-transient errors with `requires_diagnosis=True`
- [ ] `recovery_pipeline.py` -> `compensating_actions.py`: For errors with `requires_compensation=True`
- [ ] `recovery_pipeline.py` -> `strategy_selector.py`: Select strategy before every retry
- [ ] `strategy_selector.py` -> `failure_memory.py`: Query similar past fixes before selecting strategy
- [ ] `recovery_pipeline.py` -> `agent_prompts.py`: Pass `RecoveryContext` for enriched retry prompts
- [ ] `recovery_pipeline.py` -> `recovery_executor.py`: Execute retry with context and verify
- [ ] `recovery_executor.py` -> `failure_memory.py`: Record outcome after every recovery attempt
- [ ] `recovery_pipeline.py` -> `recovery_events` table: Log every stage transition
- [ ] `recovery_pipeline.py` -> notification delivery: Escalate on Tier 5
- [ ] `recovery_pipeline.py` -> `health/self_healer.py`: Check provider health before retry; trigger provider healing on systemic pattern
- [ ] `agent_supervisor.py` startup -> recover `dispatch_status='recovering'` tasks (daemon crash recovery)
- [ ] `failure_memory.py` -> pattern detection: On each new failure, check for cross-task correlation
- [ ] `dispatch_db.py` -> migrations for all new tables and columns
- [ ] `openclawd.config.yaml` -> add `recovery` section (see Appendix E for complete YAML schema)

---

## Appendix E: Recovery Configuration YAML Schema

Add this section to `openclawd.config.yaml`:

```yaml
# ── Recovery / Self-Healing Configuration ─────────────────────────
recovery:
  # -- General limits --
  max_recovery_attempts: 5              # Max total recovery attempts per task (maps to strategy ladder tiers)
  max_recovery_time_seconds: 1800       # Hard timeout for entire recovery pipeline per task (30 min)
  max_concurrent_recoveries: 3          # Max tasks in dispatch_status='recovering' at once
  recovery_timeout_per_attempt: 600     # Hard timeout per individual recovery attempt (10 min)

  # -- Diagnostic Agent --
  diagnostic_model: "claude-haiku-4-5"  # Model for diagnostic LLM calls (use cheapest available)
  diagnostic_max_input_tokens: 4000     # Max tokens for diagnostic agent input context
  diagnostic_prompt_file: "prompts/diagnostic_sop.md"  # Path to diagnostic system prompt

  # -- Budget --
  # Recovery budget per task = min(daily_budget_usd * recovery_budget_ratio, recovery_budget_cap_usd)
  recovery_budget_ratio: 0.04           # 4% of daily_budget_usd allocated per task recovery
  recovery_budget_cap_usd: 2.00         # Hard cap on per-task recovery spend

  # -- Truncation limits --
  raw_output_max_chars: 10000           # Max chars stored in dispatch_runs.raw_output
  diagnostic_context_chars: 2000        # Max chars of raw_output sent to Diagnostic Agent
  recovery_prompt_context_chars: 500    # Max chars of raw_output included in recovery prompt to agent
  error_message_max_chars: 200          # Max chars for error messages in PreviousAttemptSummary

  # -- Confidence threshold --
  min_confidence_score: 0.3             # AgentResult.confidence_score below this triggers CONFIDENCE_TOO_LOW

  # -- Systemic failure detection --
  systemic_failure_threshold_count: 3   # Number of same-error failures to trigger systemic response
  systemic_failure_window_minutes: 10   # Time window for counting correlated failures

  # -- Escalation --
  max_escalations_per_hour: 5           # Prevent alert fatigue
  escalation_cooldown_seconds: 300      # Min time between escalations for same task

  # -- Retention --
  failure_memory_retention_days: 90     # Days to keep failure_memory entries
  recovery_events_retention_days: 90    # Days to keep recovery_events entries
```

All values shown are defaults. Every key is optional -- if omitted, the default value is used. The `config.py` loader reads this section and falls back to defaults for missing keys.

---

## Appendix F: dispatch_status State Transition Diagram

The full `dispatch_status` lifecycle including the new `recovering` state:

```
                                    ┌──────────────────────┐
                                    │    NULL (no dispatch) │
                                    └──────────┬───────────┘
                                               │
                                    task enters dispatch queue
                                               │
                                               ▼
                                    ┌──────────────────────┐
                              ┌─────│       queued          │◄────────────────────┐
                              │     └──────────┬───────────┘                      │
                              │                │                                  │
                              │     claim_task() atomic UPDATE                    │
                              │                │                                  │
                              │                ▼                                  │
                              │     ┌──────────────────────┐                      │
                              │     │     dispatched        │                      │
                              │     └──────────┬───────────┘                      │
                              │                │                                  │
                              │         agent execution                           │
                              │          /        \                               │
                              │      success      failure                         │
                              │        /              \                           │
                              │       ▼                ▼                          │
                              │  ┌──────────┐    ┌──────────┐                     │
                              │  │completed │    │  failed   │────────────────┐    │
                              │  └──────────┘    └──────────┘                │    │
                              │                       │                      │    │
                              │              recovery pipeline starts        │    │
                              │              atomic: failed -> recovering     │    │
                              │                       │                      │    │
                              │                       ▼                      │    │
                              │              ┌──────────────────┐            │    │
                              │              │   recovering     │            │    │
                              │              └────────┬─────────┘            │    │
                              │                       │                      │    │
                              │              recovery outcome:               │    │
                              │              /        |         \            │    │
                              │           success   retry      exhausted     │    │
                              │            /         |             \         │    │
                              │           ▼          ▼              ▼        │    │
                              │     ┌─────────┐ ┌─────────┐  ┌────────────┐ │    │
                              │     │completed│ │ failed  │  │dispatch_   │ │    │
                              │     │(success)│ │(retry)  │  │failed     │ │    │
                              │     └─────────┘ └─────────┘  │(TERMINAL) │ │    │
                              │          │           │        └────────────┘ │    │
                              │          └───────────┘──────────────────────►│    │
                              │                                              │    │
                              │   daemon crash / graceful shutdown:           │    │
                              │   dispatched -> interrupted                   │    │
                              │   recovering -> failed (on restart)           │    │
                              │                       │                      │    │
                              │                       ▼                      │    │
                              │              ┌──────────────────┐            │    │
                              │              │  interrupted     │────────────┘    │
                              │              └──────────────────┘                 │
                              │                       │                          │
                              │              US-056: interrupted -> queued        │
                              │                       │                          │
                              └───────────────────────┴──────────────────────────┘

Terminal states (no further transitions):
  - completed: task successfully finished
  - dispatch_failed: all recovery exhausted, requires human intervention

Non-terminal failure states:
  - failed: eligible for recovery pipeline or next poll cycle retry
  - interrupted: will be re-queued on daemon restart (US-056)

Key transitions:
  - failed -> recovering: atomic UPDATE WHERE dispatch_status='failed' (prevents duplicate recovery)
  - recovering -> completed: recovery succeeded, agent produced valid result (calls handle_task_completion)
  - recovering -> failed: recovery attempt failed but retries remain, OR pipeline crashed
  - recovering -> dispatch_failed: all recovery tiers exhausted (TERMINAL)
  - dispatched -> interrupted: daemon shutdown/crash
  - recovering -> failed: daemon crash (reset on startup)
```

---

## Appendix G: Recovery Context Prompt Placement

When `agent_prompts.build_prompt()` receives a `RecoveryContext`, the recovery information is injected into the prompt as follows:

**Placement:** The recovery context is placed in a **USER message** (not SYSTEM), wrapped in XML tags for clear delineation. It appears AFTER the task description and BEFORE the skill-specific instructions.

**Format:**
```
<task>
{Original task description from tasks.description}
</task>

<recovery-context>
This is recovery attempt {N} of {max} for this task. Previous attempts failed.

## Attempt {N-1} Result
- Error: {error_code} -- {error_message}
- Agent Output (excerpt): {first 500 chars of previous raw output}
- Tool Calls Made: {count and summary of tools called}
- Diagnosis: {diagnostic_analysis, if available}

## Recovery Strategy
{strategy_description}

## Constraints
- Do NOT repeat the approach from attempt {N-1}: {description of failed approach}
- {Additional constraints from RecoveryContext.constraints}

## Previous Attempts Summary
{For each PreviousAttemptSummary: attempt N - strategy: X, error: Y, diagnostic: Z}

## Similar Past Fixes
{For each similar fix from failure_memory: "Previously, {resolution_summary}"}
</recovery-context>

<skills>
{Skill-specific instructions from skill YAML files}
</skills>
```

**Rationale for USER message placement:** The SYSTEM message contains the base SOP and agent identity. Recovery context is task-specific and varies per attempt -- it belongs in the USER message alongside the task description. XML tags prevent the agent from confusing recovery instructions with task content.
