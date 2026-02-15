# Specification: OpenClawd Agent Dispatch System

## Goal

Add the missing execution layer to the OpenClawd multi-agent platform: a Python supervisor daemon that monitors the coordination database, matches tasks to specialist agents, spawns parallel LLM API calls with agent-specific system prompts via a provider-agnostic abstraction layer, and flows structured results back into the existing coordination dashboard. This is a full implementation across all 6 phases -- nothing is deferred or scoped to MVP.

## User Stories

- As the system operator (Alan), I want a persistent supervisor daemon that automatically dispatches pending tasks to the correct specialist agents (Rex, Pixel, Haven, Vault, Nora, Scout, Keeper) using any configured LLM provider, so that agents execute work in parallel without manual intervention.
- As a developer extending the platform, I want a provider-agnostic tool schema and adapter isolation layer, so that I can swap LLM providers, add agents, or update OpenClawd without breaking the dispatch system.
- As the system operator, I want health monitoring with automatic self-healing (fallback, format adaptation, graceful degradation), so that the system survives provider outages, API changes, and model deprecations without manual recovery.

---

## Specific Requirements

**Supervisor Daemon Core Loop**
- Implement a Python daemon (`agent_supervisor.py`) that polls `coordination.db` every 30 seconds for dispatchable tasks
- Claim tasks using lease-based atomic UPDATE to prevent double-dispatch across concurrent poll cycles
- Support configurable concurrent agent execution (`max_concurrent_agents`, default: 3)
- Implement retry logic with exponential backoff: immediate on first failure, 60s on second, 300s on third
- Implement graceful shutdown on SIGTERM/SIGINT: stop accepting new tasks, wait 60s for running agents, mark remaining as `interrupted`
- Implement SIGUSR1 (immediate poll) and SIGUSR2 (immediate health check) signal handlers
- Recover interrupted tasks on restart by re-queuing them (counting toward retry limit)
- Write PID file to `agent-dispatch/supervisor.pid` with stale-PID detection

**Dispatchable Task Query**
- Implement a single dispatchable-task query used by the supervisor poll loop. A task is dispatchable when ALL of the following conditions are met:
  1. `tasks.status` is `'open'` or `'in_progress'` (not `'completed'`, `'blocked'`, or `'review'`). Note: The `in_progress` status is included because tasks may be set to `in_progress` by external systems (e.g., the dashboard UI) or by `add_task_contribution()` side-effects; `dispatch_status` and `lease_until` (conditions 2-3) are the authoritative guards against double-dispatch.
  2. `dispatch_status` is NULL (never claimed) or `'queued'` (re-queued after failure/interruption)
  3. `lease_until` is NULL or `lease_until < CURRENT_TIMESTAMP` (no active lease, or lease expired)
  4. All rows in `task_dependencies` for this task's `task_id` reference `depends_on_task_id` values whose `tasks.status = 'completed'` (all dependencies satisfied); tasks with zero dependency rows pass this check
  5. No `dispatch_runs` row exists for this `task_id` with `next_retry_at > CURRENT_TIMESTAMP` (not in a retry backoff window)
  6. The global daily budget has not been exceeded (sum of `daily_usage.total_cost_usd` for today < `daily_budget_usd`)
  7. The agent's per-agent budget has not been exceeded (see Budget Model below)
- The query orders results by `tasks.priority DESC, tasks.created_at ASC` (highest priority first, oldest first within same priority)
- Pseudocode for the claim step: `UPDATE tasks SET dispatch_status = 'queued', lease_until = datetime('now', '+N seconds') WHERE id = ? AND (dispatch_status IS NULL OR dispatch_status IN ('queued', 'failed', 'interrupted')) AND (lease_until IS NULL OR lease_until < CURRENT_TIMESTAMP)`; if 0 rows affected, another supervisor won the race -- skip silently
- **Claim-to-dispatch state interplay:** The claim step sets `dispatch_status = 'queued'` and a non-NULL `lease_until`. Although condition 2 of the dispatchable query includes `dispatch_status = 'queued'` as dispatchable, condition 3 (`lease_until IS NULL OR lease_until < CURRENT_TIMESTAMP`) prevents a freshly claimed task from being re-claimed by a concurrent poll cycle, because the claim just set `lease_until` to a future timestamp. Once the agent process starts, the supervisor transitions `dispatch_status` from `'queued'` to `'dispatched'`, which removes it from the dispatchable set entirely. In summary: `queued` + active lease = "claimed, awaiting agent start" and is protected by the lease guard; `queued` + expired/NULL lease = "re-queued after failure" and is genuinely dispatchable.

**Lease Lifecycle**
- The lease duration for a task is determined as follows: (a) if `agent_lease_defaults[agent_name]` is set in config, use that value; (b) otherwise use the global `dispatch_lease_seconds` (default: 300 seconds). (c) The heartbeat extends the lease by the same duration every 2 minutes. (d) The hard cap is `agent_timeout_seconds` (default: 1800 seconds) -- even with continuous heartbeats, a task cannot hold a lease beyond this duration from its original dispatch time. These three values interact as a pipeline: initial lease gets the task started, heartbeats keep it alive during long execution, and the hard cap prevents infinite occupation.

**Task Completion Sequence**
- When an agent returns a successful `AgentResult` (status = "completed"), the supervisor executes the following steps in order. Steps are split into multiple transaction/connection boundaries because the adapter methods (`add_task_contribution()`, `create_notification()`, `complete_task()`) each open their own `sqlite3.connect()` calls internally and CANNOT participate in the dispatch system's transaction:
  1. Validate the `AgentResult` against the schema (status, deliverable_summary, deliverable_content, etc.). If validation fails, mark the dispatch run as failed and count toward retry limit.
  2. **Block A (single dispatch-system transaction on the dispatch system's own connection):** Execute steps 2a-2d within a single SQLite transaction:
     - 2a. Set `dispatch_status = 'completed'` and `lease_until = NULL` on the `tasks` row.
     - 2b. If `AgentResult.working_memory_entries` is non-empty, upsert each entry into the `working_memory` table.
     - 2c. Update the `dispatch_runs` row: set `status = 'completed'`, `completed_at = CURRENT_TIMESTAMP`, record `tokens_used` and `cost_estimate`.
     - 2d. Write cost data to `daily_usage` table.
  3. **Step 3 (adapter call, separate connection):** Call `adapter.add_task_contribution(task_id, agent_name, 'deliverable', deliverable_content)` to record the deliverable. This opens its own `sqlite3.connect()` and has a side-effect: it sets `tasks.status = 'in_progress'` if the current status is `'open'`.
  4. **Step 4 (adapter call, separate connection):** Call `adapter.complete_task(task_id, agent_name, deliverable_url)` which opens its own `sqlite3.connect()` and sets `tasks.status = 'completed'` and `updated_at = CURRENT_TIMESTAMP`. Note: `complete_task()` internally calls `create_notification(task_id, "Task completed by {agent_name}", "normal")` and `log_agent_activity()`. The dispatch system does NOT send its own explicit completion notification -- it relies on the notification produced by `complete_task()`'s internal side-effect to avoid duplicate notifications (see Gotcha on `complete_task()` internal side-effects below).
- **Failure recovery across boundaries:** Because the completion sequence spans four independent connection boundaries (Block A, Step 3, Step 4), there are multiple points of partial failure:
  - **Block A fails:** No state has been committed. The dispatch run is marked as failed and counts toward retry limit. The task remains dispatchable for re-attempt on next cycle.
  - **Block A commits, Step 3 (`add_task_contribution`) fails:** `dispatch_status = 'completed'` is set, but no contribution is recorded and `tasks.status` remains `'open'`. The task will NOT be re-dispatched (excluded by `dispatch_status = 'completed'`). The supervisor logs a critical error. The recovery sweep (see below) detects tasks where `dispatch_status = 'completed'` but `tasks.status != 'completed'` and retries from Step 3 onward.
  - **Block A and Step 3 commit, Step 4 (`complete_task`) fails:** `dispatch_status = 'completed'` and the contribution is recorded, but `tasks.status` is `'in_progress'` (set by `add_task_contribution()` side-effect) rather than `'completed'`. Same recovery sweep handles this case -- it retries Step 4 specifically.
  - **Recovery sweep:** On each poll cycle, the supervisor runs a recovery query for tasks where `dispatch_status = 'completed'` but `tasks.status != 'completed'`. For each such task, it checks the last successful dispatch run to determine which step failed and retries from that point. If recovery fails 3 times, create an urgent notification for manual intervention.
- If Block A fails at any step, log the error with full context, mark the dispatch run as failed, and count toward retry limit. The `dispatch_status` remains as-is so the supervisor can re-attempt on next cycle.

**LLM Provider Abstraction Layer**
- Define abstract base class `LLMProvider` with methods: `complete()`, `validate_connection()`, `validate_tool_calling()`, `get_capabilities()`, `count_tokens()`
- Implement provider adapters in build order: Anthropic, OpenAI, Gemini, Ollama, Claude Code CLI
- Implement provider-agnostic `Message` dataclass (role, content, tool_calls, tool_results) with per-provider translation
- Implement provider registry factory that reads `openclawd.config.yaml` and returns the correct provider instance
- Implement per-agent model overrides via `agent_models` config section
- Implement global and per-agent fallback chains with capability requirements (tool_calling, min_context_tokens)
- Implement context budget enforcement: trim skills, summarize task, reject if still too large

**Universal Tool Schema (UTS)**
- Define provider-agnostic YAML tool definition format with fields: name, description, version, parameters, returns, execution
- Implement translators for each provider format: Anthropic `tool_use`, OpenAI `function_calling`, Gemini `function_declarations`, Ollama `tools`
- Implement working Python executors for all 8 tools: `web_search`, `file_read`, `file_write`, `database_query`, `database_write`, `shell_exec`, `python_exec`, `send_email`
- Implement tool call loop: LLM returns tool_call, runner executes tool, sends result back to LLM, repeats until final answer or depth limit
- Implement tool safety controls: depth limit (default 20), identical-call loop detection, per-tool timeouts, per-agent allowlist/denylist
- Implement tool idempotency tracking: tools declare `idempotent` flag; runner adjusts retry behavior for side-effecting tools
- Implement conformance-based fallback: if native tool calling reliability drops below 80% over a rolling window of the last 20 tool-calling health checks, switch to prompt-based tool mode. A "failure" is any canary `tool_calling` or `tool_result_handling` test that returns `passed = FALSE`. Recovery: when 2 consecutive health check runs each produce a `passed = TRUE` result for both the `tool_calling` and `tool_result_handling` canary tests, switch back to native tool mode. The rolling 20-check window is not used for recovery detection -- only the most recent 2 health check runs are examined.

**`web_search` Tool Executor**
- Implement the `web_search` executor with the following search API priority: (1) SerpAPI if `SERPAPI_KEY` env var is set, (2) Brave Search API if `BRAVE_SEARCH_API_KEY` env var is set, (3) DuckDuckGo HTML scraping as a zero-config fallback (no API key required)
- If no search API key is configured, the executor uses the DuckDuckGo fallback automatically with a logged warning
- No additional API keys are required beyond what the user chooses to configure; the tool degrades gracefully to the free tier

**Agent Execution Pipeline**
- Implement prompt assembly (`agent_prompts.py`): base SOP + agent persona + skill summaries + task description + working memory from dependencies
- Create 7 agent persona files (`prompts/*.md`: rex, pixel, haven, vault, nora, scout, keeper) plus `base_sop.md`
- Implement structured SOPs with numbered steps, decision gates, explicit outputs, and machine-parseable status prefixes
- Implement `agent_runner.py`: call `provider.complete()`, handle tool call loop, parse `<agent-result>` blocks, validate against `AgentResult` schema
- Implement `AgentResult` schema validation (status, deliverable_summary, deliverable_content, working_memory_entries, follow_up_tasks, confidence_score) before any DB write
- Implement working memory writes during agent execution with UNIQUE(task_id, agent_name, key) upsert semantics
- Implement squad_chat milestone updates during long-running tasks (rate-limited to 2-3 per task)

**Health Monitoring and Self-Healing**
- Implement 4 canary tests per provider: basic_completion, tool_calling, tool_result_handling, structured_output
- Run health checks every 6 hours (configurable) on primary and fallback providers
- Implement regression detection: compare against last successful run for failures, 3x latency increase, 2+ consecutive failures, novel error categories
- Implement 5-tier self-healing: (1) retry with backoff, (2) runtime format adaptation with logging (enabled by default), (3) provider fallback, (4) graceful degradation with accelerated 5-min health checks, (5) diagnostic report generation
- Store all health data in `provider_health` and `provider_incidents` tables
- Integrate OpenClawd compatibility as a health check (provider='openclawd')

**Task Dependencies and Inter-Agent Communication**
- Implement `task_dependencies` table with `dependency_type` ('completion', 'contribution')
- Block dispatch of tasks whose dependencies are not all in 'completed' status
- Implement dependency failure cascading: when a task permanently fails, propagate `dispatch_failed` to all direct dependents with notification
- Implement `working_memory` table: per-task structured key-value store with max_value_length 5000 chars
- Scope working memory access strictly to task dependency chains (same task or downstream dependencies only)
- Inject working memory from upstream tasks into downstream agent prompts with XML delimiters for prompt injection defense

**OpenClawd Adapter and Compatibility**
- Implement `openclawd_adapter.py` as the ONLY file that imports from `orchestrator-dashboard/` modules
- Wrap all adapter methods in try/except with `OpenClawdIncompatibleError` reporting
- Implement startup compatibility check: validate expected tables, columns, method signatures via `inspect.signature()`
- Implement tiered degradation on compatibility failure: Tier 1 (additive changes) run with warning, Tier 2 (breaking changes) enter queue-only mode with 5-min auto-retry, Tier 3 (fundamental breakage) queue-only with escalated alert requiring manual verification
- Implement versioned compatibility matrix in `compatibility.yaml`
- Run idempotent schema migrations on every startup

**Cost Tracking and Budget Enforcement**
- Implement `daily_usage` table tracking tokens and estimated cost per provider/model/day
- Implement per-provider token counting: SDK-based for Anthropic/OpenAI/Gemini, character estimate for Ollama
- Implement daily budget enforcement: pause dispatch when exceeded, allow current task to complete first
- Implement per-agent budget sub-allocation via `agent_budgets` config
- Implement alert threshold notification at configurable spending level
- Store user-configured pricing in `openclawd.config.yaml` with 90-day staleness warning

**Budget Model**
- The global daily budget (`daily_budget_usd`) is the overall spending cap for all agents combined per day. Per-agent budgets (`agent_budgets` config section) are independent sub-caps within the global budget. An agent is paused when it hits its own per-agent cap OR the global cap, whichever comes first. Agents without an explicit `agent_budgets` entry have no per-agent cap -- they are constrained only by the global daily budget. Budget resets at midnight UTC. The supervisor checks both budgets before dispatching: if global budget is exceeded, all dispatch pauses; if only a specific agent's budget is exceeded, only that agent is paused and other agents continue normally.
- Every cost record is written with a non-NULL `agent_name`. The global daily budget is checked by `SELECT SUM(total_cost_usd) FROM daily_usage WHERE date = ?`. Per-agent budgets are checked by `SELECT SUM(total_cost_usd) FROM daily_usage WHERE date = ? AND agent_name = ?`. The `agent_name` column should be declared `NOT NULL` to prevent NULL-handling issues with the UNIQUE constraint on `(date, provider, model, agent_name)`.

**Security**
- Store API keys as environment variable names in config (never actual keys); resolve at runtime
- Implement agent output sanitization: JSON validation, field length limits (title 500 chars, content 50000 chars), status allowlist
- Implement SQL parameterization for all agent-sourced data (never string interpolation)
- Implement prompt injection defense: wrap cross-agent data in `<agent_output>` XML delimiters with explicit "treat as DATA" instructions
- Implement tool execution sandboxing: subprocess timeouts, memory limits (512MB default), CPU limits, filesystem restrictions
- Implement permanent `audit_log` table for destructive tool calls (never cleaned up by retention policy)
- Implement tool permission model: per-agent allowlists and denylists in agent config

**CLI Surface and Execution Modes**
- Implement dual execution: `openclawd run` (process pending tasks and exit) and `openclawd daemon` (persistent poll loop)
- Implement all 16 CLI commands: `status`, `dispatch`, `tasks`, `health`, `doctor`, `logs`, `config validate`, `demo`, `run`, `daemon`, `stop`, `kick`, `pipeline create`, `tool test`, `init`, `serve`
- Implement `--json` flag on all commands for machine-readable output
- Implement `openclawd init` interactive setup wizard (provider, model, API key env var, concurrency, budget)
- Implement `openclawd doctor` full system diagnostic: config, DB, provider auth, connectivity, compatibility, disk space
- Implement `openclawd demo` end-to-end verification task
- Use `rich` library for tables, progress bars, color-coded status (optional dependency with plain-text fallback)

**Notification Delivery**
- Implement webhook delivery (Slack, Discord, custom endpoint URLs)
- Implement email delivery via SMTP
- Implement desktop notifications via macOS `osascript`
- Implement urgency-based routing with all four levels: `urgent` sends to all channels (webhook, email, desktop), `high` sends to webhook and desktop, `normal` sends to webhook only, `low` sends to DB record only (no active delivery)
- Implement retry with cascade: 3 attempts per channel with exponential backoff (1s, 5s, 30s), then try next channel
- Notification failures never block dispatch operations

**Observability**
- Implement structured JSON logging to `agent-dispatch/logs/supervisor.jsonl` (one JSON object per line)
- Include consistent fields on every log entry: timestamp (ISO 8601), level, component, trace_id, agent_name, task_id, message, extra
- Generate UUID v4 trace_id per dispatch; propagate through entire task lifecycle
- Implement daily log rotation with gzip compression and configurable retention (default 30 days)

**Data Retention and Cleanup**
- Archive completed tasks older than 90 days to `tasks_archive` table, using `updated_at` as the timestamp proxy for completion age (since `complete_task()` sets `updated_at = CURRENT_TIMESTAMP` upon completion, this is the closest available approximation to a completion timestamp)
- Aggregate health checks older than 30 days into `health_daily_summary`, delete raw records
- Delete agent activity logs, dispatch runs, and working memory older than 90 days
- Retain provider incidents for 180 days
- Monitor database file size with 500MB alert threshold (configurable)
- Use `PRAGMA incremental_vacuum` (requires `auto_vacuum=INCREMENTAL` set at DB creation); fall back to full `VACUUM` only when zero active dispatches
- Before running archival DELETE on `tasks`, delete or nullify related `audit_log` rows first (see `audit_log` schema note on `ON DELETE SET NULL`). The archival DELETE also cascades through `dispatch_runs`, `task_dependencies`, `working_memory`, and `task_contributions` via their `ON DELETE CASCADE` foreign keys. Additionally, the existing `agent_activity`, `notifications`, and `squad_chat` tables have `ON DELETE SET NULL` foreign keys to `tasks(id)` — when archived tasks are deleted, these rows retain their data but have their `task_id`/`related_task_id` set to NULL. This is expected and harmless.
- Archival SQL (run within a single transaction per batch):

```sql
-- Step 1: Copy completed tasks older than 90 days into the archive table.
-- The column list must be explicit because tasks_archive has the extra archived_at column
-- which receives its DEFAULT CURRENT_TIMESTAMP value automatically.
-- OR IGNORE ensures idempotency: if re-run after partial failure, duplicate INSERTs are silently skipped.
INSERT OR IGNORE INTO tasks_archive (
    id, title, description, status, priority, domain, assigned_agent,
    created_by, created_at, updated_at, due_date, deliverable_type,
    deliverable_url, estimated_effort, business_impact,
    dispatch_status, lease_until
)
SELECT
    id, title, description, status, priority, domain, assigned_agent,
    created_by, created_at, updated_at, due_date, deliverable_type,
    deliverable_url, estimated_effort, business_impact,
    dispatch_status, lease_until
FROM tasks
WHERE status = 'completed'
  AND updated_at < datetime('now', '-90 days');

-- Step 2: Delete the archived rows from the live tasks table.
-- audit_log.task_id will be SET NULL automatically via ON DELETE SET NULL.
-- dispatch_runs, task_dependencies, working_memory, task_contributions
-- will cascade-delete via ON DELETE CASCADE.
DELETE FROM tasks
WHERE status = 'completed'
  AND updated_at < datetime('now', '-90 days')
  AND id IN (SELECT id FROM tasks_archive);
```

Note: The `AND id IN (SELECT id FROM tasks_archive)` guard in the DELETE ensures only rows that were successfully inserted into the archive are removed. Output files under `agent-dispatch/output/` for archived task IDs are deleted in the same retention cleanup job (filesystem operation, outside the transaction).

**Output Directory and Files**
- Agent deliverables are written to `agent-dispatch/output/` as individual files
- Naming convention: `{task_id}_{agent_name}_{trace_id[:8]}.md` (e.g., `42_rex_a1b2c3d4.md`)
- File format: Markdown with YAML frontmatter containing task_id, agent_name, trace_id, timestamp, status
- The `dispatch_runs.output_file` column stores the relative path from the `agent-dispatch/` directory (e.g., `output/42_rex_a1b2c3d4.md`)
- Retention: output files for archived tasks (older than 90 days) are deleted during the same retention cleanup job that archives tasks
- The `output/` directory is created on first use if it does not exist

**Web Dashboard**
- Implement `openclawd serve` lightweight HTTP endpoint exposing `openclawd status --json` output
- Default port: 8377, bind to `127.0.0.1` (localhost only, no external access)
- No authentication for v1 (localhost binding provides sufficient security for single-user operation)
- Endpoint path: `GET /status` returns the same JSON as `openclawd status --json`
- Runs as a separate process from the daemon (not embedded); can be started independently via `openclawd serve` while the daemon runs in the background
- Provide real-time coordination visibility for external tools (Grafana, custom dashboards)

**Hardcoded Path Verification**
- Verify no hardcoded user-specific paths remain in `skills/self-evolving-skill/`. If any are found, replace with relative paths or `$HOME` expansion. Do not assign engineering effort to fix something that may not need fixing.

**Platform and Packaging**
- Create macOS launchd plist (`scripts/com.openclaw.agent-supervisor.plist`)
- Create Linux systemd service (`scripts/openclawd-supervisor.service`)
- Implement watchdog: supervisor writes heartbeat timestamp to `supervisor.heartbeat` each poll cycle; service manager restarts if stale >5 min
- Package as `pip install openclawd-dispatch` with optional dependency groups: `[anthropic]`, `[openai]`, `[gemini]`, `[all]`
- Core dependencies: `pyyaml`, `requests` only
- Auto-generate commented config template on first run if no config file exists

---

## Visual Design

No visual mockups are provided. This is a backend infrastructure system. The following architectural diagrams should be created during implementation and placed in `planning/visuals/`:
- System architecture diagram (supervisor, agents, providers, database interactions)
- Dispatch state machine (NULL, queued, dispatched, completed, failed, interrupted, dispatch_failed)
- Self-healing tier flowchart (5 tiers with decision points)
- Task dependency pipeline example (Rex Phase 1 then Scout Phase 2)

---

## Systems to Integrate

### OrchestratorDashboard (dashboard.py)

**Key Files**: `/Users/alanwalker/openclaw-orchestration/orchestrator-dashboard/dashboard.py`

**Integration Points**:
- `create_task(title, description, domain, priority=3, assigned_agent=None, deliverable_type="report", estimated_effort=5, business_impact=3) -> int`
- `complete_task(task_id, agent_name, deliverable_url=None) -> bool`
- `add_task_contribution(task_id, agent_name, contribution_type, content) -> bool`
- `log_agent_activity(agent_name, task_id, activity_type, message) -> None`
- `create_notification(task_id, message, urgency="normal") -> None`
- `squad_chat_post(agent_name, message, related_task_id=None) -> None`
- `get_dashboard_summary() -> Dict`
- `agent_checkin(agent_name) -> Dict`

**Recommended Patterns**:
- Import ONLY through `openclawd_adapter.py` -- no direct imports from any other dispatch module
- Wrap every call in try/except catching `TypeError` (signature changes) and `sqlite3.Error` (schema changes)
- The dashboard creates its own DB connections with `timeout=10.0` but does NOT use WAL mode -- the dispatch system must set WAL on its own connections
- Every adapter method (`add_task_contribution()`, `create_notification()`, `complete_task()`) opens its own `sqlite3.connect()` call internally. These calls CANNOT participate in the dispatch system's SQLite transactions. The Task Completion Sequence is designed around this constraint with explicit transaction boundaries.

**Gotchas**:
- `OrchestratorDashboard.__init__` takes `db_path` defaulting to `"orchestrator-dashboard/coordination.db"` (relative path) -- must resolve to the correct absolute path from the dispatch system's working directory
- The `tasks` table has a CHECK constraint on `status` limited to `('open', 'in_progress', 'review', 'completed', 'blocked')` -- the dispatch system adds `dispatch_status` as a SEPARATE column, not modifying the existing `status` column
- `log_agent_activity` silently swallows `sqlite3.Error` -- the adapter should add its own error detection around this
- `add_task_contribution()` has a side effect: it sets `tasks.status = 'in_progress'` if the current status is `'open'`. In the dispatch flow this is expected and benign since `complete_task()` will overwrite it to `'completed'` immediately after (in Step 4 of the Task Completion Sequence). However, if Step 4 fails after Step 3 commits, the task will be left with `status = 'in_progress'` and `dispatch_status = 'completed'` -- this is handled by the recovery sweep described in the Task Completion Sequence.
- **`complete_task()` internal side-effects produce notifications and activity logs:** `complete_task()` internally calls `create_notification(task_id, "Task completed by {agent_name}", "normal")` and `log_agent_activity(agent_name, task_id, "completion", ...)`. The dispatch system does NOT send its own explicit completion notification -- it relies entirely on `complete_task()`'s internal notification to avoid duplicates. If the dispatch system needs a notification with custom urgency or message content for a specific completion scenario (e.g., urgency escalation), it must either: (a) call its own `create_notification()` AND accept the duplicate from `complete_task()`, or (b) create a wrapper that suppresses the internal notification. For the standard completion path, neither is needed -- the internal notification suffices.

### AgentCoordinator (agent_coordinator.py)

**Key Files**: `/Users/alanwalker/openclaw-orchestration/orchestrator-dashboard/agent_coordinator.py`

**Integration Points**:
- `_determine_relevant_agents(task_content: str) -> List[str]` -- keyword-based agent selection using inline keyword lists (e.g., 'research', 'analyze', 'market' -> rex). This method scans the combined title+description text for keyword matches and returns a deduplicated list of agent names. It does NOT use the `agent_expertise` mapping.
- `_can_agent_contribute(agent_name: str, task: Dict) -> bool` -- domain-expertise matching using the `agent_expertise` dict (lines 60-68). This is a separate mechanism from `_determine_relevant_agents` and checks whether an agent's expertise domains include the task's domain field, with additional cross-domain heuristics (Scout validates everything, Rex matches 'research' in title, etc.).
- `agent_expertise` mapping (lines 60-68, inside `_can_agent_contribute`): rex (research, market_analysis, competitive_analysis, customer_research), pixel (digital_products, product_validation, marketplace_strategy, product_creation), haven (real_estate, property_analysis, investment_analysis, market_research), vault (business_acquisition, deal_analysis, roi_assessment, due_diligence), nora (operations, day_job, financial_management, task_management), scout (validation, quality_control, fact_checking, cross_domain_review), keeper (maintenance, email_management, automation, system_health)

**Recommended Patterns**:
- Adapter exposes `determine_agents(task_content: str) -> list[str]` which internally calls `coordinator._determine_relevant_agents()` for keyword-based routing
- Do NOT duplicate the keyword lists or agent_expertise mapping in dispatch config -- use the coordinator as the single source of truth
- The `_can_agent_contribute()` method is useful for cross-domain task validation but is NOT the same as agent routing

**Gotchas**:
- `AgentCoordinator.__init__()` takes NO parameters and internally creates `OrchestratorDashboard()` with its default relative path. The adapter must handle this by either: (a) setting the working directory to the `orchestrator-dashboard/` directory before constructing the coordinator, or (b) constructing `OrchestratorDashboard(db_path=absolute_path)` separately and then monkey-patching `coordinator.dashboard` with the correctly-configured instance. Option (b) is recommended for explicitness.
- `_determine_relevant_agents` is a private method (underscore prefix) -- it could be renamed or refactored in future OpenClawd updates; the adapter must handle this gracefully
- The method uses keyword matching only (no ML/embedding) -- results are deterministic based on content keywords

### HeartbeatIntegration (heartbeat_integration.py)

**Key Files**: `/Users/alanwalker/openclaw-orchestration/orchestrator-dashboard/heartbeat_integration.py`

**Integration Points**:
- `george_coordination_summary() -> str` -- generates status summary for periodic heartbeat reports

**Recommended Patterns**:
- Adapter exposes `get_coordination_summary() -> str` wrapping this function
- Call during the supervisor's periodic heartbeat cycle

**Gotchas**:
- This function instantiates its own `AgentCoordinator` internally -- there is no way to inject a DB path
- The function returns emoji-rich strings intended for display -- the dispatch system should treat this as opaque text

### Existing Coordination Database Schema

**Key Files**: `/Users/alanwalker/openclaw-orchestration/orchestrator-dashboard/orchestrator-dashboard/coordination.db`

**Integration Points**:
- Dispatch system extends this database with new tables and columns (does NOT create a separate DB)
- New tables: `dispatch_runs`, `task_dependencies`, `daily_usage`, `provider_health`, `provider_incidents`, `working_memory`, `audit_log`, `tasks_archive`, `health_daily_summary`
- New columns on `tasks`: `dispatch_status`, `lease_until`

**Recommended Patterns**:
- All schema migrations are idempotent (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN` wrapped in try/except)
- Migrations run on every supervisor startup
- Enable WAL mode and busy_timeout=5000 on every connection
- Set `PRAGMA foreign_keys = ON` on every dispatch-system connection (SQLite does not enable foreign key enforcement by default; it must be set per-connection). Note: the existing dashboard.py already sets this pragma in `init_database()` but only on the connection used during initialization.
- Long-lived reader connection (autocommit) for polls, short-lived writer connections (DEFERRED isolation) for claims/updates

**Gotchas**:
- The DB path contains a doubled directory: `orchestrator-dashboard/orchestrator-dashboard/coordination.db` -- verify this is the actual runtime path
- The existing schema does NOT use WAL mode or busy_timeout -- these must be set per-connection
- NEVER modify or drop existing OpenClawd tables or columns
- Network filesystem detection: check if DB is on NFS/SMB and warn about WAL unreliability

### Skills Directory

**Key Files**: `/Users/alanwalker/openclaw-orchestration/skills/` (44 skill directories)

**Integration Points**:
- Agent prompts reference skills as knowledge context via `AGENT_SKILLS` mapping in `config.py`
- Prompt builder reads `SKILL.md` description from each assigned skill directory and injects a summary into the agent prompt
- Skills provide methodology/reference content; they are NOT callable tools

**Recommended Patterns**:
- Skills are read-only from the dispatch system's perspective
- Inject only the description/summary from `SKILL.md` (not the full content) to stay within context budgets
- Support incremental adoption of `owner_agents` frontmatter in SKILL.md headers

**Gotchas**:
- Verify no hardcoded user-specific paths remain in `skills/self-evolving-skill/` at implementation time; fix any found instances
- Some skill directories may lack a `SKILL.md` file -- handle missing files gracefully
- The skills directory is a sibling of `orchestrator-dashboard/`, not inside `agent-dispatch/`

### Memory System (conversations.db)

**Key Files**: `/Users/alanwalker/openclaw-orchestration/memory-db/`

**Integration Points**:
- Phase 6 optional integration: promote significant task findings from `coordination.db` to `conversations.db`
- Separate database with separate ownership -- dispatch system does NOT read or write to `conversations.db` until Phase 6

**Recommended Patterns**:
- Treat as a strictly separate system with a one-way data flow (coordination.db -> conversations.db)
- Integration goes through `auto_memory.py` module, not direct DB writes

**Gotchas**:
- This is a separate SQLite database file -- do not confuse connection paths
- The memory system has its own schema and migration logic

---

## Components to Reuse (Existing)

**OrchestratorDashboard** (`orchestrator-dashboard/dashboard.py`)
- How used: Adapter wraps `create_task()`, `complete_task()`, `add_task_contribution()`, `log_agent_activity()`, `create_notification()`, `squad_chat_post()` for all task lifecycle operations

**AgentCoordinator._determine_relevant_agents()** (`orchestrator-dashboard/agent_coordinator.py`)
- How used: Adapter exposes `determine_agents()` for keyword-based routing of tasks to the correct specialist agents when no explicit assignment is provided

**AgentCoordinator._can_agent_contribute()** (`orchestrator-dashboard/agent_coordinator.py`)
- How used: Adapter can expose `can_agent_contribute()` for domain-expertise validation of whether an agent should work on a given task, as a secondary check after routing

**george_coordination_summary()** (`orchestrator-dashboard/heartbeat_integration.py`)
- How used: Adapter exposes `get_coordination_summary()` for periodic status reports in the supervisor heartbeat cycle

**Existing `tasks` table schema** (`coordination.db`)
- How used: Dispatch system extends with `dispatch_status` and `lease_until` columns; reads/writes task records through both the adapter (for OpenClawd methods) and direct SQL (for dispatch-specific queries)

**Existing `skills/` directory** (44 skill directories)
- How used: Prompt builder reads `SKILL.md` files to inject knowledge context summaries into agent system prompts

---

## New Components to Build

### Module: agent-dispatch/ (All New)

This is an entirely new Python module. Every file listed below is new. There are no existing `agent-dispatch/` components to reuse.

All Python package directories include standard `__init__.py` files (omitted from the table for brevity).

| Component | Purpose | File Path |
|-----------|---------|-----------|
| config.py | Constants, paths, timing, agent-skill mapping, config loader | `agent-dispatch/config.py` |
| openclawd.config.yaml | User-facing YAML config (provider, model, API key env vars, fallback chains, budgets) | `agent-dispatch/openclawd.config.yaml` |
| openclawd_adapter.py | ONLY file importing from OpenClawd modules; isolation layer with defensive wrapping | `agent-dispatch/openclawd_adapter.py` |
| compatibility_check.py | Startup schema + method signature validation with tiered degradation | `agent-dispatch/compatibility_check.py` |
| compatibility.yaml | Version compatibility matrix (compatible, untested, incompatible versions) | `agent-dispatch/compatibility.yaml` |
| dispatch_db.py | Schema migrations, dispatch queries, WAL/busy_timeout, connection strategy | `agent-dispatch/dispatch_db.py` |
| agent_prompts.py | Per-agent structured message assembly (system + user + working memory + skills) | `agent-dispatch/agent_prompts.py` |
| agent_runner.py | LLM provider call, tool call loop, result parsing, AgentResult validation | `agent-dispatch/agent_runner.py` |
| agent_supervisor.py | Main daemon: poll loop, dispatch, monitor, retry, signals, PID file, recovery | `agent-dispatch/agent_supervisor.py` |
| cli.py | Full CLI surface (16 commands), entry point, output formatting | `agent-dispatch/cli.py` |
| providers/base.py | LLMProvider ABC + Message/LLMResponse/ProviderCapabilities dataclasses | `agent-dispatch/providers/base.py` |
| providers/registry.py | Provider factory: config dict to provider instance | `agent-dispatch/providers/registry.py` |
| providers/anthropic_provider.py | Anthropic Claude SDK adapter with token counting | `agent-dispatch/providers/anthropic_provider.py` |
| providers/openai_provider.py | OpenAI GPT SDK adapter with token counting | `agent-dispatch/providers/openai_provider.py` |
| providers/gemini_provider.py | Google Gemini SDK adapter with token counting | `agent-dispatch/providers/gemini_provider.py` |
| providers/ollama_provider.py | Ollama local model adapter with character-based token estimate | `agent-dispatch/providers/ollama_provider.py` |
| providers/claude_code_provider.py | Claude Code CLI subprocess passthrough (bypasses UTS and result parsing) | `agent-dispatch/providers/claude_code_provider.py` |
| tools/schema.py | Tool definition dataclass, YAML loader, validator | `agent-dispatch/tools/schema.py` |
| tools/registry.py | Load and cache tool definitions from YAML files | `agent-dispatch/tools/registry.py` |
| tools/translators/anthropic.py | UTS to Anthropic tool_use format | `agent-dispatch/tools/translators/anthropic.py` |
| tools/translators/openai.py | UTS to OpenAI function_calling format | `agent-dispatch/tools/translators/openai.py` |
| tools/translators/gemini.py | UTS to Gemini function_declarations format | `agent-dispatch/tools/translators/gemini.py` |
| tools/translators/ollama.py | UTS to Ollama tools format | `agent-dispatch/tools/translators/ollama.py` |
| tools/definitions/*.yaml | 8 YAML tool definition files (web_search, file_read, file_write, database_query, database_write, shell_exec, python_exec, send_email) | `agent-dispatch/tools/definitions/` |
| tools/executors/*.py | 8 Python executor modules (one per tool) with sandboxing | `agent-dispatch/tools/executors/` |
| health/canary_tests.py | 4 canary tests per provider | `agent-dispatch/health/canary_tests.py` |
| health/health_monitor.py | Scheduled runner, regression detection, trend tracking | `agent-dispatch/health/health_monitor.py` |
| health/health_db.py | provider_health and provider_incidents schema + queries | `agent-dispatch/health/health_db.py` |
| health/self_healer.py | 5-tier recovery logic | `agent-dispatch/health/self_healer.py` |
| health/diagnostic_report.py | Novel failure analysis and report generation | `agent-dispatch/health/diagnostic_report.py` |
| prompts/base_sop.md | Shared SOP injected into all agent prompts | `agent-dispatch/prompts/base_sop.md` |
| prompts/rex.md | Rex (research) agent persona, expertise, SOP, allowed tools | `agent-dispatch/prompts/rex.md` |
| prompts/pixel.md | Pixel (digital products) agent persona | `agent-dispatch/prompts/pixel.md` |
| prompts/haven.md | Haven (real estate) agent persona | `agent-dispatch/prompts/haven.md` |
| prompts/vault.md | Vault (business acquisition) agent persona | `agent-dispatch/prompts/vault.md` |
| prompts/nora.md | Nora (operations) agent persona | `agent-dispatch/prompts/nora.md` |
| prompts/scout.md | Scout (validation) agent persona | `agent-dispatch/prompts/scout.md` |
| prompts/keeper.md | Keeper (maintenance) agent persona | `agent-dispatch/prompts/keeper.md` |
| scripts/com.openclaw.agent-supervisor.plist | macOS launchd service definition | `scripts/com.openclaw.agent-supervisor.plist` |
| scripts/openclawd-supervisor.service | Linux systemd service definition | `scripts/openclawd-supervisor.service` |

---

## Existing Code to Leverage

**OrchestratorDashboard task CRUD methods**
- `create_task()`, `complete_task()`, `add_task_contribution()` provide the full task lifecycle without reimplementation
- The adapter wraps these 1:1 with defensive error handling
- Avoids duplicating any SQL for task creation, completion, or contribution tracking

**AgentCoordinator agent routing logic**
- `_determine_relevant_agents()` contains keyword-based routing rules that scan task content for domain keywords and return matching agent names
- `_can_agent_contribute()` contains domain-expertise matching via the `agent_expertise` dict -- a separate mechanism used for task-agent compatibility checking
- Reuse both methods as complementary routing tools via the adapter
- Eliminates the need to maintain a parallel routing system in agent-dispatch

**Dashboard notification and squad_chat infrastructure**
- `create_notification()` and `squad_chat_post()` handle DB writes for notifications and team chat
- The dispatch system uses these for milestone updates, alerts, and urgency-based notifications
- Notification delivery (webhook, email, desktop) is new -- but notification storage reuses the existing table and methods

**Existing coordination.db schema**
- 6 existing tables (tasks, agent_activity, task_contributions, notifications, squad_chat, agent_checkins) with established schema and indexes
- The dispatch system adds new tables alongside these, never modifying existing table definitions
- Existing indexes on tasks(status), tasks(domain), tasks(priority), agent_activity(agent_name), agent_activity(timestamp) benefit dispatch queries

**Existing launchd plist pattern**
- `scripts/com.openclaw.dailygit.plist` provides a working pattern for macOS launchd service configuration in this project
- Use the same directory and naming convention for the supervisor plist

---

## Database Schema (New Tables and Columns)

### New column on existing `tasks` table: `dispatch_status`

```sql
ALTER TABLE tasks ADD COLUMN dispatch_status TEXT
    CHECK(dispatch_status IN ('queued', 'dispatched', 'completed', 'failed', 'interrupted', 'dispatch_failed'));
```

NULL is the initial state for all existing tasks. SQLite CHECK constraints permit NULL values by design, so the CHECK constraint correctly allows the NULL -> queued transition without needing to list NULL explicitly.

Valid state transitions:
- `NULL` -> `queued` (supervisor claims task)
- `queued` -> `dispatched` (agent process started)
- `dispatched` -> `completed` (agent finished successfully)
- `dispatched` -> `failed` (agent errored, retries remaining)
- `dispatched` -> `interrupted` (graceful shutdown during execution)
- `dispatched` -> `dispatch_failed` (max retries exceeded)
- `failed` -> `queued` (retry: re-queue)
- `interrupted` -> `queued` (restart recovery: re-queue)

### New column on existing `tasks` table: `lease_until`

```sql
ALTER TABLE tasks ADD COLUMN lease_until DATETIME DEFAULT NULL;
```

Used for lease-based dispatch. Supervisor extends lease via heartbeat every 2 minutes. Expired leases (lease_until < now) make tasks re-dispatchable.

### Composite index on `tasks` for the dispatchable task query

```sql
CREATE INDEX IF NOT EXISTS idx_tasks_dispatch ON tasks(dispatch_status, lease_until);
```

This index accelerates the dispatchable task query, which is the most performance-critical query in the system (runs every 30 seconds). It covers conditions 2 and 3 of the dispatchable task query (dispatch_status and lease_until filtering).

### `dispatch_runs` table

```sql
CREATE TABLE IF NOT EXISTS dispatch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'timeout')),
    attempt INTEGER NOT NULL DEFAULT 1,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    output_file TEXT,
    error_summary TEXT,
    tokens_used INTEGER DEFAULT 0,
    cost_estimate REAL DEFAULT 0.0,
    trace_id TEXT NOT NULL,
    tool_calls_count INTEGER DEFAULT 0,
    next_retry_at DATETIME,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_dispatch_runs_task ON dispatch_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_runs_trace ON dispatch_runs(trace_id);
```

The `next_retry_at` column lives on `dispatch_runs` (not on `tasks`) because retry timing is per-attempt. When a dispatch run fails and retries are remaining, the supervisor sets `next_retry_at` on the failed run's row to `datetime('now', '+N seconds')` based on the backoff schedule (immediate, +60s, +300s). The dispatchable task query checks: `NOT EXISTS (SELECT 1 FROM dispatch_runs WHERE dispatch_runs.task_id = tasks.id AND dispatch_runs.next_retry_at > CURRENT_TIMESTAMP)` to skip tasks still in a backoff window.

### `task_dependencies` table

```sql
CREATE TABLE IF NOT EXISTS task_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    depends_on_task_id INTEGER NOT NULL,
    dependency_type TEXT DEFAULT 'completion'
        CHECK(dependency_type IN ('completion', 'contribution')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    UNIQUE(task_id, depends_on_task_id)
);
```

### `working_memory` table

```sql
CREATE TABLE IF NOT EXISTS working_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    UNIQUE(task_id, agent_name, key)
);
```

### `daily_usage` table

```sql
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
);
```

The `agent_name` column is declared `NOT NULL` because every cost record is always written with an explicit agent name. The global daily budget is checked by `SELECT SUM(total_cost_usd) FROM daily_usage WHERE date = ?`. Per-agent budgets are checked by `SELECT SUM(total_cost_usd) FROM daily_usage WHERE date = ? AND agent_name = ?`. Declaring `NOT NULL` avoids NULL-handling ambiguity in the UNIQUE constraint.

### `provider_health` table

```sql
CREATE TABLE IF NOT EXISTS provider_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    test_name TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    latency_ms INTEGER,
    error_message TEXT,
    error_category TEXT,
    raw_response TEXT,
    tested_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_provider_health_tested ON provider_health(tested_at);
```

### `provider_incidents` table

```sql
CREATE TABLE IF NOT EXISTS provider_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    incident_type TEXT NOT NULL,
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    auto_healed BOOLEAN DEFAULT FALSE,
    healing_action TEXT,
    diagnostic_report TEXT,
    notified_user BOOLEAN DEFAULT FALSE
);
```

### `audit_log` table (permanent, never cleaned up)

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    task_id INTEGER,
    agent_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    result TEXT,
    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_log_trace ON audit_log(trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_task ON audit_log(task_id);
```

The `task_id` column is declared as nullable (`INTEGER` without `NOT NULL`) with `ON DELETE SET NULL`. This is required because: (1) the `audit_log` table is permanent and never cleaned up by the retention policy, but (2) the archival process DELETEs old completed tasks from the `tasks` table. Without `ON DELETE SET NULL`, the archival DELETE would fail with a foreign key constraint violation for any archived task that has audit_log entries. With `ON DELETE SET NULL`, the audit_log rows are preserved with `task_id = NULL` after the referenced task is archived, maintaining the audit trail while allowing task cleanup. The dispatch system MUST set `PRAGMA foreign_keys = ON` on every connection for this constraint to be enforced (see Existing Coordination Database Schema gotchas).

### `tasks_archive` table

The `tasks_archive` table must be defined with an explicit schema rather than using `CREATE TABLE AS SELECT * FROM tasks WHERE 0`, because the latter approach does not copy CHECK constraints, DEFAULT values, or any columns added by `ALTER TABLE` migrations. The archive table schema must be created AFTER all `ALTER TABLE` migrations on the `tasks` table have run, so that it includes `dispatch_status` and `lease_until`.

```sql
CREATE TABLE IF NOT EXISTS tasks_archive (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT,
    priority INTEGER,
    domain TEXT NOT NULL,
    assigned_agent TEXT,
    created_by TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    due_date DATETIME,
    deliverable_type TEXT,
    deliverable_url TEXT,
    estimated_effort INTEGER,
    business_impact INTEGER,
    dispatch_status TEXT,
    lease_until DATETIME,
    archived_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### `health_daily_summary` table

```sql
CREATE TABLE IF NOT EXISTS health_daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tests_run INTEGER DEFAULT 0,
    tests_passed INTEGER DEFAULT 0,
    avg_latency_ms REAL DEFAULT 0.0,
    UNIQUE(date, provider, model)
);
```

---

## Configuration Schema (openclawd.config.yaml)

```yaml
# Primary LLM Provider
provider: anthropic                          # anthropic | openai | gemini | ollama | claude_code
model: claude-sonnet-4-5-20250514
api_key_env: ANTHROPIC_API_KEY               # Env var name (never actual key)

# Per-agent model overrides
agent_models:
  keeper: claude-haiku-4-5-20251001
  rex: claude-sonnet-4-5-20250514

# Global fallback provider
fallback:
  provider: openai
  model: gpt-4o
  api_key_env: OPENAI_API_KEY

# Per-agent fallback chains (overrides global fallback)
agent_fallbacks:
  rex:
    requires: { tool_calling: true, min_context_tokens: 50000 }
    fallback_chain:
      - { provider: openai, model: gpt-4o, api_key_env: OPENAI_API_KEY }

# Per-agent budget allocation (USD per day)
agent_budgets:
  rex: 20.00
  scout: 15.00
  keeper: 5.00

# Per-agent lease defaults (seconds)
agent_lease_defaults:
  rex: 1800
  keeper: 300

# Concurrency
max_concurrent_agents: 3
agent_timeout_seconds: 1800                  # Hard cap even with heartbeat extension
dispatch_lease_seconds: 300                  # Default lease duration

# Cost controls
max_tokens_per_task: 100000
daily_budget_usd: 50.00
alert_threshold_usd: 25.00

# Health checks
health_check_interval_hours: 6
auto_fallback_on_failure: true

# Token-to-dollar pricing (user-maintained)
pricing:
  anthropic:
    claude-sonnet-4-5-20250514:
      input_per_1m_tokens: 3.00
      output_per_1m_tokens: 15.00
  openai:
    gpt-4o:
      input_per_1m_tokens: 2.50
      output_per_1m_tokens: 10.00
pricing_updated_at: "2026-02-14"             # Warn if older than 90 days

# Notifications
notifications:
  webhook_url: ""
  email:
    smtp_host: ""
    smtp_port: 587
    from: ""
    to: ""
  desktop: true
  delivery_rules:
    urgent: [webhook, email, desktop]
    high: [webhook, desktop]
    normal: [webhook]
    low: []

# Data retention
retention:
  tasks_days: 90
  activity_days: 90
  health_checks_days: 30
  incidents_days: 180
  max_db_size_mb: 500

# Logging
log_retention_days: 30
max_log_file_mb: 100

# Tool safety
max_tool_iterations: 20
min_tool_interval_seconds: 1
```

Config resolution order (first match wins):
1. `--config` CLI flag
2. `OPENCLAWD_CONFIG` environment variable
3. `./openclawd.config.yaml` (current working directory)
4. `agent-dispatch/openclawd.config.yaml` (project directory)
5. `~/.openclawd/openclawd.config.yaml` (user home directory)

---

## Key Data Models

### Message (Provider-Agnostic)

```
Message:
    role: str           # "system", "user", "assistant", "tool_result"
    content: str
    tool_calls: list    # Outbound tool calls (from LLM)
    tool_results: list  # Inbound tool results (to LLM)
```

### LLMResponse

```
LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    usage: TokenUsage       # input_tokens, output_tokens
    model: str
    stop_reason: str        # "end_turn", "tool_use", "max_tokens"
```

### ProviderCapabilities

```
ProviderCapabilities:
    supports_tool_calling: bool
    supports_streaming: bool
    supports_vision: bool
    max_context_tokens: int
    max_output_tokens: int
    tool_calling_reliability: str   # "high", "medium", "low"
```

### AgentResult (parsed from LLM output)

```
AgentResult:
    status: str                     # "completed", "blocked", "needs_input", "failed"
    deliverable_summary: str        # One-line summary
    deliverable_content: str        # Full deliverable text
    deliverable_url: str | None
    working_memory_entries: list | None   # Key-value pairs to store
    follow_up_tasks: list | None         # Suggested next tasks
    confidence_score: float | None       # 0.0-1.0
```

Result handling by status:
- `completed` -> validate, execute Block A (dispatch_status + working_memory + dispatch_run + daily_usage), then Step 3 (add_task_contribution), then Step 4 (complete_task() which internally creates the completion notification and logs agent activity) -- see Task Completion Sequence above
- `blocked` -> set task blocked, create high-urgency notification
- `needs_input` -> create high-urgency notification for user
- `failed` -> log, retry up to 3x, then urgent notification
- provider_failure -> trigger self-healer before marking as failed

### UniversalTool (YAML definition)

```
UniversalTool:
    name: str
    description: str
    version: str
    parameters: dict            # Typed parameter definitions with required/optional
    returns: dict               # Return type specification
    execution:
        type: str               # "python"
        module: str             # e.g., "tools.executors.web_search"
        function: str           # e.g., "execute"
    idempotent: bool            # Default true for reads, false for writes
    destructive: bool           # Triggers audit log + permission check
    timeout_seconds: int        # Per-tool timeout (default 30)
    allowed_agents: list | None # If set, only these agents can call this tool
    test: dict | None           # Sample inputs and expected output shapes
```

---

## Implementation Phases

### Phase 1: Core Infrastructure
1. `config.py` -- constants, paths, timing, AGENT_SKILLS mapping, config loader with resolution order
2. `openclawd.config.yaml` -- user-facing config template with comprehensive comments
3. `openclawd_adapter.py` -- isolation layer wrapping all OpenClawd imports with defensive try/except; construct `OrchestratorDashboard(db_path=absolute_path)` and monkey-patch onto coordinator instance
4. `compatibility_check.py` -- schema validation (sqlite_master queries) + method signature validation (inspect.signature) + version matrix
5. `compatibility.yaml` -- version compatibility matrix
6. `dispatch_db.py` -- idempotent schema migrations for all new tables/columns (archive table created AFTER ALTER TABLE migrations), WAL mode, busy_timeout=5000, `PRAGMA foreign_keys = ON` on every connection, connection strategy (long-lived reader, short-lived writers), composite index on `tasks(dispatch_status, lease_until)`
7. `providers/base.py` -- LLMProvider ABC with complete(), validate_connection(), validate_tool_calling(), get_capabilities(), count_tokens()
8. `providers/registry.py` -- factory reading config, resolving API keys from environment variables
9. Security foundations: output sanitization layer, prompt injection defense delimiters, SQL parameterization enforcement
10. `ConfigValidator` -- pre-dispatch validation (env vars, SDK imports, DB access, config ranges)
11. Network filesystem detection for coordination.db WAL reliability warning
12. Verify no hardcoded user-specific paths remain in `skills/self-evolving-skill/`; fix any found instances

### Phase 2: Provider Adapters
1. `providers/anthropic_provider.py` -- Anthropic SDK with native token counting
2. `providers/openai_provider.py` -- OpenAI SDK with tiktoken-based token counting
3. `providers/claude_code_provider.py` -- CLI subprocess passthrough (no UTS, no result parsing, raw text output)
4. `providers/gemini_provider.py` -- Google Gemini SDK with SDK token counting
5. `providers/ollama_provider.py` -- Ollama HTTP API with character-based token estimates
6. Per-provider `count_tokens()` implementations

### Phase 3: Universal Tool Schema
1. `tools/schema.py` -- UniversalTool dataclass, YAML loader, parameter validator
2. `tools/translators/anthropic.py` -- UTS to Anthropic tool_use format
3. `tools/translators/openai.py` -- UTS to OpenAI function_calling format
4. `tools/translators/gemini.py` -- UTS to Gemini function_declarations format
5. `tools/translators/ollama.py` -- UTS to Ollama tools format
6. `tools/definitions/*.yaml` -- 8 tool YAML definitions
7. `tools/registry.py` -- load and cache tool definitions
8. `tools/executors/*.py` -- 8 Python executor implementations with sandboxing (subprocess timeouts, memory limits, filesystem restrictions); `web_search` uses SerpAPI > Brave Search > DuckDuckGo fallback chain

### Phase 4: Agent Execution
1. `agent_prompts.py` -- structured message assembly: base_sop + persona + skill summaries + task + working memory (with XML delimiters)
2. `prompts/base_sop.md` + 7 agent persona files -- structured SOPs with decision gates
3. `agent_runner.py` -- provider.complete() call, tool call loop with depth/loop/timeout limits, result parsing from `<agent-result>` blocks, AgentResult validation, working_memory writes
4. `agent_supervisor.py` -- main daemon with poll loop, dispatchable task query, lease-based claiming, concurrent dispatch, retry backoff, signal handlers, PID file, interrupted task recovery, heartbeat file, recovery sweep for partially-completed tasks (dispatch_status='completed' but tasks.status!='completed')
5. `cli.py` -- initial commands: dispatch, run, daemon, stop, kick, status, tasks, doctor
6. `working_memory` integration -- prompt builder queries and injects dependency chain memories
7. Task decomposition CLI: `openclawd pipeline create`
8. Tool idempotency tracking and retry adjustment
9. Dependency failure cascading with notifications
10. Task completion sequence implementation (validate -> Block A [dispatch_status + working_memory + dispatch_run + daily_usage] -> Step 3 [add_task_contribution] -> Step 4 [complete_task() with internal notification] with multi-boundary failure recovery)

### Phase 5: Health and Self-Healing
1. `health/canary_tests.py` -- 4 tests per provider (basic_completion, tool_calling, tool_result_handling, structured_output)
2. `health/health_db.py` -- provider_health + provider_incidents schema and queries
3. `health/health_monitor.py` -- scheduled runner (every 6 hours), regression detection (failure vs last run, latency 3x increase, consecutive failures, novel categories), conformance tracking (rolling 20-check window for tool-calling reliability; recovery uses most recent 2 consecutive passes only)
4. `health/self_healer.py` -- 5-tier recovery: retry with backoff, format adaptation with runtime translator update, provider fallback with notification, graceful degradation with accelerated 5-min checks, diagnostic report
5. `health/diagnostic_report.py` -- generate detailed analysis for novel/persistent failures
6. Data retention cleanup job (runs in daily heartbeat): archive tasks using explicit INSERT INTO tasks_archive / DELETE FROM tasks SQL (using `updated_at` as completion timestamp proxy; audit_log rows have task_id SET NULL via ON DELETE SET NULL), aggregate health, delete old activity/dispatch_runs, delete output files for archived tasks, check DB size, incremental vacuum
7. Log rotation with daily gzip compression

### Phase 6: Platform and Polish
1. `scripts/com.openclaw.agent-supervisor.plist` -- macOS launchd with WatchPaths for heartbeat monitoring
2. `scripts/openclawd-supervisor.service` -- Linux systemd with WatchdogSec=300
3. Dual execution modes: `openclawd run` (single pass + exit) and `openclawd daemon` (persistent loop)
4. Full CLI command surface: `health`, `logs`, `config validate`, `demo`, `init`, `pipeline create`, `tool test`, `serve`
5. Output formatting: `rich` library integration with tables, progress bars, color status; `--json` flag on all commands
6. Structured JSON logging to `supervisor.jsonl` with consistent field set
7. Trace ID propagation: UUID v4 per dispatch, stored in dispatch_runs, passed through all stages
8. Installation packaging: `pyproject.toml` with `openclawd` console_scripts entry point, optional dependency groups
9. Config template auto-generation on first run
10. `openclawd init` interactive setup wizard
11. Notification delivery: webhook (HTTP POST), email (SMTP), desktop (osascript) with urgency routing (urgent/high/normal/low) and retry cascade
12. `openclawd serve` -- lightweight HTTP server on port 8377 bound to 127.0.0.1, separate process, GET /status endpoint, no auth for v1
13. `openclawd tool test <tool_name>` -- run tool test blocks from YAML definitions
14. Optional Phase 6 memory integration: promote significant findings to conversations.db via auto_memory.py

---

## Error Handling Strategy

### Dispatch Errors
- Task claim race condition: atomic UPDATE with WHERE clause on dispatch_status + lease_until; if 0 rows affected, another supervisor won the race -- skip silently
- Agent crash during execution: lease expires after configured duration; supervisor detects expired lease on next poll, re-queues task counting toward retry limit
- Max retries exceeded: mark task `dispatch_failed`, cascade failure to dependent tasks, create urgent notification

### Provider Errors
- Rate limit (429): Tier 1 self-healing -- retry with exponential backoff (1s, 5s, 30s)
- Auth failure (401/403): Tier 3 -- switch to fallback provider, create urgent notification
- Server error (5xx): Tier 1 -- retry with backoff; if persistent (2+ consecutive), escalate to Tier 3
- Model deprecated: Tier 5 -- generate diagnostic report with clear instructions to update config
- Tool format change: Tier 2 -- try known format variations, update translator at runtime if one works

### Database Errors
- `database is locked`: busy_timeout=5000 handles most cases; if still locked after 5s, log error and retry on next poll cycle
- Connection corruption: detect via PRAGMA integrity_check in health monitor; alert and refuse dispatch if corruption detected
- Schema mismatch: compatibility check detects on startup; enter tiered degradation mode

### Agent Output Errors
- Malformed JSON in `<agent-result>`: log the raw output, mark task as failed with parse error details, count toward retry limit
- Missing required fields: log validation error, mark failed
- Status value not in allowlist: reject, mark failed
- Content exceeds length limits: truncate with warning logged (not a failure)

### Notification Errors
- Webhook delivery failure: retry 3x (1s, 5s, 30s); on exhaustion, cascade to next channel
- SMTP failure: retry 3x; on exhaustion, cascade to desktop notification
- All channels exhausted: mark notification as failed in DB, log full diagnostic context, continue dispatch operations

---

## Out of Scope

- Docker installation packaging (deferred to future)
- OpenTelemetry exporter integration (logs are OTel-compatible; exporter is additive future work)
- Multi-turn agent conversations with accumulated history (single-turn is sufficient for initial implementation)
- Agent-initiated task decomposition (manual decomposition via `openclawd pipeline create` is in scope; automatic `follow_up_tasks` creation is not)
- Usage reporting CLI (`openclawd report`) -- data captured in `daily_usage`, presentation layer deferred
- Template pipeline YAML definitions in `agent-dispatch/pipelines/` -- manual pipeline creation is in scope
- `openclawd agent create` scaffolding CLI -- manual 5-step agent creation process documented instead
- Provider SDK version tracking in health monitor (compatibility matrix is in scope, but not automatic SDK version detection)
- PostgreSQL migration -- SQLite with WAL mode is the target database
- HTTP API layer between dispatch system and Next.js app (shared DB access only, no REST/WebSocket endpoints)
- `notifications retry` CLI command -- manual retry is deferred; notification failures are handled automatically by the retry cascade (3 attempts per channel with exponential backoff, then cascade to next channel) as described in the Notification Delivery section
