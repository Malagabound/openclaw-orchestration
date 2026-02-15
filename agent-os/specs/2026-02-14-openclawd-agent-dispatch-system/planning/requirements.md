# Spec Requirements: OpenClawd Agent Dispatch System

## Initial Description

OpenClawd has a well-documented multi-agent architecture (7 specialist agents: Rex, Pixel, Haven, Vault, Nora, Scout, Keeper + George as orchestrator) with an existing SQLite coordination dashboard for task tracking, agent check-ins, and contributions. However, **agents are currently conceptual roles** — nothing actually spawns them as separate processes. George "is" all agents within a single conversation.

This specification adds the missing execution layer: a **Python supervisor daemon** that monitors the coordination DB, matches tasks to agents, spawns parallel LLM API calls with agent-specific system prompts, and flows results back into the dashboard.

**Key design principle:** The system is **API-agnostic**. Users can plug in Anthropic, OpenAI, Google Gemini, Ollama, or any other LLM provider. The orchestration layer never knows or cares which model is behind it.

**Scope Clarification:** This is a **FULL IMPLEMENTATION** of all 6 phases described in the raw idea document. This is NOT an MVP — every feature, tool, provider, CLI command, health monitoring capability, self-healing tier, notification delivery method, and web dashboard is being built.

## Related Systems Identified

### Systems

- **orchestrator-dashboard/**: Existing coordination.db with tables for tasks, agent_activity, task_contributions, notifications, squad_chat, agent_checkins
  - Key files: `dashboard.py` (task CRUD, contributions, notifications), `agent_coordinator.py` (agent routing logic), `heartbeat_integration.py` (coordination summary)
  - Integration: Dispatch system extends this database with new tables and columns, imports existing modules ONLY via adapter layer

- **memory-db/**: Separate conversations.db with memory system for knowledge storage and conversation history
  - Key files: `auto_memory.py`, `memory_manager.py`, `openclaw_integration.py`
  - Integration: Separate database with clear contract. Task results in coordination.db can optionally be promoted to conversations.db for significant findings (Phase 6 integration)

- **skills/**: 46 existing skill directories including product-research, deep-research, microsaas-factory, reflect-learn, recursive-self-improvement, security-sentinel, self-evolving-skill
  - Integration: Agent prompts reference skills as knowledge context, but remain modular/separate systems

### Components

- **OrchestratorDashboard (dashboard.py)**: Task lifecycle management (create_task, complete_task, add_task_contribution, create_notification, log_agent_activity)
- **AgentCoordinator (agent_coordinator.py)**: Agent routing logic (`_determine_relevant_agents()`) - will be imported and reused via adapter
- **HeartbeatIntegration (heartbeat_integration.py)**: `george_coordination_summary()` for periodic status reports

### Key Architecture Decision

**All OpenClawd imports go through ONE file:** `openclawd_adapter.py`. No other dispatch system file imports from orchestrator-dashboard modules directly. This isolation layer protects against OpenClawd updates breaking the dispatch system.

## Requirements Discussion

### Scope Confirmation

**Q: What phases are in scope?**
**A:** ALL 6 phases from the original document. Full implementation including:
- Phase 1: Core Infrastructure
- Phase 2: Provider Adapters (Anthropic, OpenAI, Gemini, Ollama, Claude Code)
- Phase 3: Universal Tool Schema with working Python executors
- Phase 4: Agent Execution with structured prompts and result parsing
- Phase 5: Health & Self-Healing (all 5 tiers)
- Phase 6: Platform & Polish (daemon management, CLI surface, notifications, web dashboard, packaging)

**Q: Which LLM providers are being built?**
**A:** ALL providers mentioned in the spec:
- Anthropic (Claude) - primary provider, build first
- OpenAI (GPT-4o) - fallback provider, build second
- Google Gemini - full implementation
- Ollama (local models) - full implementation
- Claude Code CLI - passthrough mode implementation

Implementation order: Anthropic → OpenAI → Gemini → Ollama → Claude Code

**Q: Which tools need working executors?**
**A:** ALL tools mentioned in the spec need working Python executor implementations from the start:
- web_search (external API integration)
- file_read (local filesystem access)
- file_write (local filesystem write)
- database_query (SQLite query execution)
- database_write (SQLite write operations)
- shell_exec (subprocess with sandboxing)
- python_exec (subprocess Python execution)
- send_email (SMTP integration)

Each tool must have a complete executor with error handling, timeout management, and security sandboxing where applicable.

### Architecture & Integration Decisions

**Q: Where should agent-dispatch/ live in the project structure?**
**A:** At the root of openclaw-orchestration/ as a sibling to orchestrator-dashboard/ and memory-db/:
```
openclaw-orchestration/
├── orchestrator-dashboard/
├── memory-db/
├── agent-dispatch/          # NEW - dispatch system lives here
├── skills/
└── ...
```

The dispatch system references the existing coordination.db at:
`/openclaw-orchestration/orchestrator-dashboard/orchestrator-dashboard/coordination.db`

**Q: How do agent prompts relate to existing skills?**
**A:** Agent prompts and skills are **separate, modular systems**:
- Agent prompt files live in `agent-dispatch/prompts/*.md` (one per agent: rex.md, pixel.md, haven.md, vault.md, nora.md, scout.md, keeper.md)
- Skills live in `skills/` directories (existing 46+ skills)
- Agent prompts **reference** skills as knowledge context via the AGENT_SKILLS mapping in config.py
- The prompt builder reads skill SKILL.md descriptions and injects summaries into agent prompts
- Skills provide methodology/reference content; prompts provide agent persona/SOP/decision gates

**Q: Should we reuse existing agent definitions from agent_coordinator.py?**
**A:** YES - **import and reuse** via the adapter layer:
- The existing `agent_coordinator._determine_relevant_agents()` logic is the source of truth for agent routing
- The adapter exposes `determine_agents(task_content: str) -> list[str]` method
- Dispatch system calls adapter method to get agent assignments
- Do NOT create duplicate agent definitions in agent-dispatch/config.py
- Agent expertise, skill mappings, and routing rules come from agent_coordinator.py

**Q: Should we migrate to PostgreSQL (Supabase)?**
**A:** NO - **keep SQLite** for the dispatch system:
- The existing coordination.db is SQLite
- Prove the system works with SQLite first
- PostgreSQL migration is a separate future consideration
- All concurrency hardening (WAL mode, busy_timeout, lease-based dispatch) is designed for SQLite
- The spec explicitly designs around SQLite's constraints

### Self-Healing & Reliability Decisions

**Q: Should Tier 2 self-healing (runtime format adaptation) be enabled by default?**
**A:** YES - **enabled by default with comprehensive logging**:
- When tool calling format changes are detected, system automatically tries known format variations
- If a variation works, update the translator at runtime
- Create provider_incidents record with `auto_healed: true` and details of what changed
- Log the adaptation with full diagnostic context
- Create notification: "Provider format adapted automatically - [details]"
- Audit trail enables manual review without blocking automatic recovery

**Q: What should happen when OpenClawd compatibility check fails?**
**A:** **Tiered degradation with local queue buffer** - never refuse to start:

**Tier 1 (Additive Changes):**
- OpenClawd added new columns, tables, or methods
- Run normally with warning logged
- Dispatch continues, unknown fields ignored

**Tier 2 (Breaking Changes):**
- Method signatures changed, required columns missing, types incompatible
- Enter **queue-only mode**: accept new tasks via CLI, store them, but don't dispatch
- Auto-retry compatibility check every 5 minutes
- Create high-urgency notification: "OpenClawd compatibility issue detected. Dispatch paused."
- When compatibility restored, auto-resume dispatch from queue

**Tier 3 (Fundamental Breakage):**
- Database file missing, corrupted, or completely incompatible schema
- Enter queue-only mode with escalated alert
- Create urgent notification with diagnostic report
- Continue compatibility checks but don't auto-resume (require manual verification)

**Never** refuse to start - always maintain the queue buffer so no tasks are lost.

**Q: How should task-to-agent assignment work?**
**A:** **Always pre-assigned via orchestrator routing** - no unassigned tasks:
- Tasks are created with explicit agent assignment (via George or user CLI)
- For tasks without explicit assignment, supervisor calls `adapter.determine_agents(task_content)` before dispatch
- Dynamic routing happens at orchestration layer (via existing agent_coordinator logic)
- Supervisor never dispatches a task without knowing which agent(s) to invoke
- Manual decomposition via `openclawd pipeline create` for multi-agent pipelines

### Integration & Boundaries

**Q: How should the Python dispatch system integrate with the Next.js app?**
**A:** **Completely standalone for now** - shared database access only:
- Dispatch system is pure Python CLI/daemon
- Next.js app and Python dispatch both read/write coordination.db independently
- No HTTP API layer between them (no REST endpoints, no WebSocket)
- Both systems use SQLite's WAL mode for concurrent access
- Future Phase 6: Optional web dashboard via `openclawd serve` exposes status JSON

**Q: What should happen when provider SDK version is outdated?**
**A:** **Warn on untested, refuse on known-incompatible, never auto-upgrade**:
- `openclawd doctor` checks installed SDK versions against compatibility matrix
- Untested version (e.g., anthropic 0.30.0 when tested on 0.28.x): Warning logged, connection test required
- Known-incompatible version: Refuse to start, require manual upgrade with clear instructions
- Never run `pip install --upgrade` automatically (security risk, unexpected breaking changes)
- compatibility.yaml maintains version compatibility matrix per provider

### Data & Privacy Decisions

**Q: Should working memory be accessible across all tasks or scoped to dependencies?**
**A:** **Strictly scoped to task dependency chains** - no global cross-task access:
- working_memory entries are only visible to agents working on:
  - The same task (concurrent agents collaborating)
  - Downstream tasks in the dependency chain (Scout sees Rex's Phase 1 findings)
- Agents cannot query working memory from unrelated tasks
- No pattern mining across all Rex research tasks (that would be memory-db's responsibility)
- Security: Prevents information leakage between unrelated tasks/users

**Q: How should notification delivery failures be handled?**
**A:** **Retry with cascade, never block dispatch**:
- Attempt delivery via primary channel (webhook/email/desktop)
- Retry 3x with exponential backoff (1s → 5s → 30s)
- If all retries fail, cascade to next delivery channel (email fails → try desktop)
- If all channels exhausted, mark notification as failed in DB
- Log failure with full diagnostic context
- Continue dispatch operations - notification failure never blocks agent work
- `openclawd notifications retry` command for manual re-delivery

**Q: How granular should cost budget enforcement be?**
**A:** **Pause after current task completes, with per-agent sub-allocation support**:
- When daily budget exceeded, don't kill running agents mid-task
- Let current task complete, then pause dispatch
- Create urgent notification: "Daily budget of $X exceeded. Dispatch paused until [tomorrow]."
- Support per-agent budget allocation in config:
  ```yaml
  agent_budgets:
    rex: 20.00      # Research tasks are expensive
    scout: 15.00    # Validation is medium cost
    keeper: 5.00    # Maintenance is cheap
  ```
- If agent-specific budget exceeded, only that agent is paused
- Budget resets at midnight UTC (configurable timezone)

### Operational Decisions

**Q: How should lease timeouts work for long-running tasks?**
**A:** **Heartbeat-based auto-extension with per-agent defaults + hard cap**:
- Default lease: 5 minutes for most agents
- Agent runner sends heartbeat every 2 minutes while active
- Each heartbeat extends lease by another 5 minutes
- Per-agent configurable lease defaults:
  ```yaml
  agent_lease_defaults:
    rex: 1800      # 30 minutes for deep research
    keeper: 300    # 5 minutes for quick maintenance
  ```
- Hard cap from global `agent_timeout_seconds` (default: 1800 seconds / 30 minutes)
- Even with heartbeats, task cannot exceed hard cap
- Prevents infinite loops or hung agents

**Q: How should Ollama model detection work?**
**A:** **Validate via API, suggest alternatives, never auto-pull**:
- `openclawd doctor` calls Ollama API to list installed models
- If configured model not found, show error with available alternatives
- Never automatically run `ollama pull <model>` (large downloads, user should control)
- Provide clear instructions: "Model 'llama3.1' not found. Install with: ollama pull llama3.1"
- If Ollama server not running, provide clear diagnostic: "Ollama server unreachable at http://localhost:11434"

### Cleanup & Maintenance

**Q: Should the hardcoded /Users/blitz/ path in self-evolving-skill be fixed?**
**A:** **YES - fix as part of Phase 1 in this spec**:
- Search for all instances of `/Users/blitz/` in `skills/self-evolving-skill/` directory
- Replace with relative paths or environment variable expansion
- This is a quick cleanup task that improves system portability
- Document the fix in the requirements as a prerequisite for Phase 1

**Q: How should agent check-ins work with the dispatch system?**
**A:** **Orchestrator (supervisor) is responsible for all observability records**:
- Supervisor creates agent_checkins records when dispatching agents
- Supervisor updates check-ins during heartbeat renewals
- Agents return structured AgentResult only - no direct DB writes
- Agent runner doesn't import dashboard.py or create check-ins itself
- This maintains separation of concerns (agents focus on task work, supervisor handles coordination)

**Q: Should agents post to squad_chat during task execution?**
**A:** **YES - structured milestone updates, rate-limited to 2-3 per task**:
- Agents post milestone updates to squad_chat during long-running tasks
- Example milestones: "Phase 1 research started", "Competitor analysis complete (3/5)", "Final report generated"
- Rate limit: Maximum 2-3 squad_chat messages per task to avoid spam
- No blow-by-blow commentary - only significant progress markers
- Final deliverable goes to task_contributions (separate from squad_chat)

## Requirements Summary

### Functional Requirements

**Core Dispatch System:**
- Python supervisor daemon that polls coordination.db every 30 seconds for dispatchable tasks
- Lease-based task claiming with heartbeat renewal to prevent double-dispatch and enable crash recovery
- Concurrent agent execution (configurable max_concurrent_agents, default: 3)
- Retry logic with exponential backoff (immediate → 60s → 300s) for failed tasks
- Graceful shutdown with interrupted task recovery on restart
- Signal handlers for operational control (SIGTERM/SIGINT graceful shutdown, SIGUSR1 immediate poll, SIGUSR2 health check)

**Multi-Provider LLM Abstraction:**
- Abstract base class LLMProvider with complete(), validate_connection(), validate_tool_calling(), get_capabilities()
- Provider adapters for Anthropic, OpenAI, Gemini, Ollama, Claude Code (passthrough mode)
- Provider-agnostic message format with translation layer for each provider
- Provider registry factory that reads config and returns correct provider instance
- Per-agent model overrides (use cheaper models for simple agents)
- Global and per-agent fallback chains with capability requirements

**Universal Tool Schema (UTS):**
- Provider-agnostic YAML tool definitions with parameters, returns, execution metadata
- Translators for each provider (Anthropic tool_use, OpenAI function_calling, Gemini function_declarations, Ollama tools)
- Working Python executors for all tools: web_search, file_read, file_write, database_query, database_write, shell_exec, python_exec, send_email
- Tool execution layer with call loop (LLM → tool call → execute → result → LLM → repeat or final answer)
- Tool call safety controls: depth limits, loop detection, per-tool timeouts, permission model, idempotency tracking

**Agent Execution:**
- Per-agent system prompt assembly from template files (prompts/*.md)
- Base SOP injection (prompts/base_sop.md) shared across all agents
- Structured agent SOPs with numbered steps, decision gates, explicit outputs
- AgentResult schema validation before DB writes
- Working memory injection for dependent tasks
- Result parsing from <agent-result> blocks in LLM responses
- Output sanitization and SQL injection prevention

**Health Monitoring & Self-Healing:**
- Four canary tests per provider: basic_completion, tool_calling, tool_result_handling, structured_output
- Scheduled health checks every 6 hours (configurable)
- provider_health table with test results, latency tracking, error categorization
- Five-tier self-healing response:
  - Tier 1: Retry with backoff (transient errors)
  - Tier 2: Format adaptation (tool calling changes) - enabled by default with logging
  - Tier 3: Provider fallback (provider down or broken)
  - Tier 4: Graceful degradation (all providers down - pause dispatch, continue health checks)
  - Tier 5: Diagnostic report generation for novel failures
- provider_incidents table with auto-heal tracking and resolution timestamps

**Task Dependencies & Inter-Agent Communication:**
- task_dependencies table enabling sequential task execution (Scout depends on Rex completing first)
- Dependency failure cascading with notifications
- working_memory table for per-task structured findings (key-value pairs)
- Cross-agent data sharing scoped to task dependency chains only
- Squad chat integration with rate-limited milestone updates (2-3 per task)

**Cost Tracking & Budget Controls:**
- daily_usage table tracking tokens and estimated cost per provider/model
- User-configured pricing in openclawd.config.yaml (pricing updated per provider changes)
- Daily budget enforcement (pause dispatch when exceeded, don't kill mid-task)
- Per-agent budget sub-allocation support
- Alert threshold for proactive spending notifications
- Token counting per provider (SDK-based for Anthropic/OpenAI/Gemini, character estimate for Ollama)

**Data Retention & Cleanup:**
- Task archival after 90 days (moved to tasks_archive table)
- Health check aggregation into daily summaries after 30 days
- Database size monitoring with 500MB alert threshold
- Incremental vacuum for space reclamation without exclusive locks
- Configurable retention periods per data type

**Security:**
- API keys stored as environment variable names in config (never actual keys)
- Agent output sanitization (JSON validation, field length limits, SQL parameterization)
- Prompt injection defense with XML delimiters for cross-agent data
- Tool execution sandboxing (timeouts, memory limits, filesystem restrictions, network controls)
- Destructive tool audit log (permanent record, never cleaned up)
- Tool permission model (per-agent allowlists and denylists)

**Observability:**
- Structured JSON logging (one JSON object per line in supervisor.jsonl)
- Trace ID propagation through entire task lifecycle
- Log rotation with daily gzip compression
- Metrics derivation from existing data (dispatch_runs, daily_usage, provider_health)
- Consistent log fields: timestamp, level, component, trace_id, agent_name, task_id, message, extra

**CLI & User Experience:**
- Dual execution modes: openclawd daemon (persistent) and openclawd run (run-and-exit)
- Full command surface: status, dispatch, tasks, health, doctor, logs, config validate, demo, run, daemon, stop, kick
- Rich terminal output with tables, progress bars, color-coded status indicators
- --json flag on all commands for scripting
- Config validation with specific remediation steps
- Interactive setup wizard (openclawd init)

**Notification Delivery:**
- Webhook integration (Slack, Discord, custom endpoints)
- Email delivery via SMTP
- Desktop notifications (macOS osascript)
- Urgency-based routing (urgent → all channels, normal → webhook only)
- Retry with cascade (3 attempts per channel, fall back to next channel)
- Never block dispatch on notification failures

**Platform & Packaging:**
- macOS launchd service definition (com.openclaw.agent-supervisor.plist)
- Linux systemd service definition (openclawd-supervisor.service)
- PID file management for duplicate prevention
- Watchdog integration for automatic restart on hang
- pip installable package (openclawd-dispatch)
- Optional dependencies per provider ([anthropic], [openai], [gemini], [all])
- Config template auto-generation with comprehensive comments

**Web Dashboard:**
- Lightweight HTTP server (openclawd serve)
- Exposes status JSON for external tools (Grafana, custom dashboards)
- Real-time coordination visibility without CLI access

### Reusability Opportunities

**Existing Systems to Integrate:**
- agent_coordinator._determine_relevant_agents() for task routing (import via adapter)
- dashboard.py methods for task CRUD, contributions, notifications (import via adapter)
- heartbeat_integration.george_coordination_summary() for status reports (import via adapter)
- Existing 46+ skill directories as knowledge context for agent prompts

**Adapter Layer Pattern:**
- ONE file (openclawd_adapter.py) imports from OpenClawd modules
- All other dispatch code calls adapter methods, never imports directly
- Defensive wrapping with try/except and incompatibility reporting
- Compatibility checks on every startup with tiered degradation response

### Scope Boundaries

**In Scope (Everything from the Original Document):**
- All 6 implementation phases
- All 5 LLM providers (Anthropic, OpenAI, Gemini, Ollama, Claude Code)
- All tool executors with working implementations
- Complete health monitoring with all 5 self-healing tiers
- Full CLI command surface (14 commands)
- Notification delivery via all channels (webhook, email, desktop)
- Web dashboard HTTP endpoint
- Data retention and cleanup automation
- Security hardening (sandboxing, audit logs, prompt injection defense)
- Process management (daemon, signals, PID files, watchdog)
- Installation packaging (pip, setup wizard, config templates)
- Observability (structured logging, trace IDs, metrics)
- Cost tracking and budget enforcement
- Task dependencies and inter-agent communication
- Graceful shutdown and crash recovery
- OpenClawd compatibility monitoring and adaptation

**Explicitly Out of Scope (Deferred to Future):**
- Docker installation packaging
- OpenTelemetry exporter integration (logs are OTel-compatible, exporter is additive)
- Multi-turn agent conversations with accumulated history
- Agent-initiated task decomposition (manual decomposition via CLI is in scope)
- Usage reporting CLI (data captured in daily_usage, presentation layer deferred)
- Template pipeline YAML definitions (manual pipeline creation via CLI is in scope)
- `openclawd agent create` scaffolding CLI (manual 5-step process documented)
- Provider SDK version tracking in health monitor (compatibility matrix is in scope)
- PostgreSQL migration (SQLite is the target database)

### Technical Considerations

**Database Concurrency:**
- SQLite WAL mode enabled on all connections
- Busy timeout set to 5000ms on all connections
- Lease-based dispatch for idempotency and crash recovery
- Long-lived reader connection for supervisor poll loop
- Short-lived writer connections that close immediately after commit
- Transaction isolation level: DEFERRED with explicit BEGIN/COMMIT/ROLLBACK
- Network filesystem detection with WAL reliability warning

**Context Window Management:**
- Per-provider max_context_tokens exposed via get_capabilities()
- Token counting via provider SDKs (Anthropic, OpenAI, Gemini) or character estimates (Ollama)
- Context budget enforcement before dispatch (trim skills → summarize task → reject if still too large)
- Fallback context compatibility check (refuse fallback if task doesn't fit smaller context window)

**Provider Reliability:**
- Tool calling conformance testing with reliability rate tracking
- Automatic fallback to prompt-based tool mode if native tool calling drops below 80% success rate
- Provider health trends inform automatic fallback decisions
- Self-healing feedback loop for continuous improvement

**OpenClawd Update Survival:**
- Adapter layer isolates all OpenClawd imports
- Compatibility check validates schema + method signatures on startup
- Tiered degradation (run with warning → queue-only mode → escalated alert)
- Version compatibility matrix maintained in compatibility.yaml
- Idempotent schema migrations run on every startup

**Performance:**
- 30-second poll interval for task scanning
- Concurrent agent execution up to configurable limit
- Connection pooling via long-lived reader, short-lived writers
- Incremental vacuum instead of full VACUUM for space reclamation

**Security:**
- No API keys in config files (environment variables only)
- Agent output sanitization before DB writes
- Prompt injection defense with clear delimiters
- Tool sandboxing with memory/CPU/timeout limits
- Permanent audit log for destructive tool calls
- Tool permission model with explicit allow/deny lists

## Visual Assets

### Files Provided:
No visual files found in the visuals directory.

### Visual Assets Requested:
As this is a backend infrastructure system, visual assets would be architecture/flow diagrams rather than UI mockups. Suggested diagrams for documentation:
- System architecture diagram showing supervisor, agents, providers, and database interactions
- Dispatch state machine diagram (NULL → queued → dispatched → completed/failed/interrupted)
- Self-healing tier flowchart (5 tiers with decision points)
- Health check flow diagram (canary tests → regression detection → self-healing)
- Task dependency pipeline example (Rex Phase 1 → Scout Phase 2)

If created during implementation, place in:
`/Users/alanwalker/openclaw-orchestration/agent-os/specs/2026-02-14-openclawd-agent-dispatch-system/planning/visuals/`

## Implementation Phases (All In Scope)

### Phase 1: Core Infrastructure
- config.py — All constants, paths, timing, agent-skill mapping
- openclawd.config.yaml — User-facing config with provider, model, API key env vars, fallback chains
- dispatch_db.py — Schema migrations, dispatch queries, WAL mode, busy_timeout, connection strategy
- providers/base.py — LLMProvider abstract base class
- providers/registry.py — Provider factory
- openclawd_adapter.py — Isolation layer for OpenClawd imports
- compatibility_check.py — Schema + method signature validation
- ConfigValidator — Pre-dispatch validation
- Fix hardcoded /Users/blitz/ paths in skills/self-evolving-skill/

### Phase 2: Provider Adapters
- providers/anthropic_provider.py — Anthropic SDK integration with token counting
- providers/openai_provider.py — OpenAI SDK integration with token counting
- providers/gemini_provider.py — Google Gemini SDK integration
- providers/ollama_provider.py — Ollama local model integration with character-based token estimates
- providers/claude_code_provider.py — CLI subprocess passthrough mode

### Phase 3: Universal Tool Schema
- tools/schema.py — Tool definition dataclass, YAML loader, validator
- tools/translators/anthropic.py — UTS → Anthropic tool_use format
- tools/translators/openai.py — UTS → OpenAI function_calling format
- tools/translators/gemini.py — UTS → Gemini function_declarations format
- tools/translators/ollama.py — UTS → Ollama tools format
- tools/definitions/*.yaml — Tool YAML files for all tools
- tools/registry.py — Load and cache tool definitions
- Tool executors with security sandboxing for all tools

### Phase 4: Agent Execution
- agent_prompts.py — Structured message assembly (system + user, not text blob)
- prompts/*.md — Per-agent persona files (rex.md, pixel.md, haven.md, vault.md, nora.md, scout.md, keeper.md) + base_sop.md
- agent_runner.py — Calls provider.complete() with messages + translated tools, handles tool call loop, parses AgentResult, validates output schema, writes working_memory
- agent_supervisor.py — Main daemon: poll, dispatch, monitor, retry, signal handlers, PID file, interrupted task recovery
- cli.py — Manual dispatch interface and full CLI surface
- working_memory schema — Inter-agent communication with UNIQUE(task_id, agent_name, key)
- AgentResult schema validation layer
- Task decomposition CLI (openclawd pipeline create)
- Tool idempotency tracking
- Retry backoff with next_retry_at column
- Dependency failure cascading

### Phase 5: Health & Self-Healing
- health/canary_tests.py — 4 canary tests per provider
- health/health_db.py — provider_health and provider_incidents schema + queries
- health/health_monitor.py — Scheduled runner, regression detection, trend tracking
- health/self_healer.py — 5-tier recovery (retry → adapt → fallback → degrade → diagnose)
- health/diagnostic_report.py — Generate analysis for novel failures
- Data retention cleanup job — Runs during daily heartbeat
- Log rotation — Daily with gzip compression

### Phase 6: Platform & Polish
- scripts/com.openclaw.agent-supervisor.plist — macOS launchd service
- scripts/openclawd-supervisor.service — Linux systemd service
- Dual execution modes — openclawd run (run-and-exit) and openclawd daemon (persistent)
- Full CLI command surface — 14 commands with rich output formatting
- Structured logging — JSON-per-line in supervisor.jsonl
- Trace ID propagation — UUID per dispatch
- Installation packaging — pip install openclawd-dispatch with optional dependencies
- Config template generation — Auto-generate on first run
- Notification delivery — Webhook, email, desktop with retry and cascade
- Web dashboard — openclawd serve HTTP endpoint
- Tool testing CLI — openclawd tool test <tool_name>

## Verification Plan

**Unit Tests:**
- dispatch_db.py: Task claiming, double-dispatch prevention, lease expiry
- Provider adapters: Basic completion, tool call handling, capability reporting
- UTS translators: Tool definition translation correctness per provider
- Canary tests: Health check execution and result parsing

**Integration Tests:**
- End-to-end: Create task → supervisor dispatches → agent completes → results in DB
- Failover: Simulate primary provider failure → verify fallback activation → verify recovery
- Tool format change: Modify translator → verify self-healer detects and adapts
- Compatibility: Simulate OpenClawd schema change → verify tiered degradation

**Manual Tests:**
- CLI: openclawd dispatch --task-id N → verify end-to-end
- Daemon: Install launchd/systemd → verify lifecycle management
- Tool definitions: openclawd tool test <tool_name> → verify executor logic
- Config wizard: openclawd init → verify interactive setup

**Security Tests:**
- API key leakage: Verify keys never appear in logs, DB, or config files
- Prompt injection: Attempt cross-agent command injection via working_memory
- Tool sandboxing: Verify memory/CPU limits enforce, filesystem restrictions work
- SQL injection: Test malicious agent output doesn't corrupt DB

## Final Architecture Notes

**Project Structure:**
```
openclaw-orchestration/
├── orchestrator-dashboard/          # Existing
│   ├── dashboard.py
│   ├── agent_coordinator.py
│   └── heartbeat_integration.py
├── memory-db/                       # Existing
├── skills/                          # Existing (46+ skills)
├── agent-dispatch/                  # NEW - Full dispatch system
│   ├── __init__.py
│   ├── config.py
│   ├── openclawd.config.yaml
│   ├── openclawd_adapter.py
│   ├── compatibility_check.py
│   ├── dispatch_db.py
│   ├── agent_prompts.py
│   ├── agent_runner.py
│   ├── agent_supervisor.py
│   ├── cli.py
│   ├── providers/
│   │   ├── base.py
│   │   ├── anthropic_provider.py
│   │   ├── openai_provider.py
│   │   ├── gemini_provider.py
│   │   ├── ollama_provider.py
│   │   ├── claude_code_provider.py
│   │   └── registry.py
│   ├── tools/
│   │   ├── schema.py
│   │   ├── registry.py
│   │   ├── translators/
│   │   │   ├── anthropic.py
│   │   │   ├── openai.py
│   │   │   ├── gemini.py
│   │   │   └── ollama.py
│   │   └── definitions/
│   │       ├── web_search.yaml
│   │       ├── file_read.yaml
│   │       ├── database_query.yaml
│   │       └── ... (one per tool)
│   ├── health/
│   │   ├── canary_tests.py
│   │   ├── health_monitor.py
│   │   ├── health_db.py
│   │   ├── self_healer.py
│   │   └── diagnostic_report.py
│   ├── prompts/
│   │   ├── base_sop.md
│   │   ├── rex.md
│   │   ├── pixel.md
│   │   ├── haven.md
│   │   ├── vault.md
│   │   ├── nora.md
│   │   ├── scout.md
│   │   └── keeper.md
│   ├── output/
│   └── logs/
└── scripts/
    ├── com.openclaw.agent-supervisor.plist
    └── openclawd-supervisor.service
```

**Database Strategy:**
- Single SQLite database: coordination.db
- Dispatch system extends with new tables: dispatch_runs, task_dependencies, daily_usage, provider_health, provider_incidents, working_memory, audit_log
- Adds columns to existing tasks table: dispatch_status, lease_until
- WAL mode for concurrent access
- No PostgreSQL migration in this spec

**Integration Contract:**
- Dispatch system reads from: tasks, agent_activity, agent_checkins (via adapter)
- Dispatch system writes to: tasks (status updates), task_contributions (deliverables), notifications (alerts), squad_chat (milestones), agent_activity (logs), agent_checkins (heartbeats), plus all new tables
- Memory system (conversations.db) is separate - optional integration in Phase 6

**Success Criteria:**
- Supervisor daemon runs continuously without crashes for 7+ days
- All 5 providers successfully dispatch tasks and return results
- Health monitoring detects and recovers from simulated provider failures
- Task dependencies execute in correct order (Scout waits for Rex)
- Cost tracking accurately reflects provider usage within 5% margin
- CLI commands provide clear, actionable output
- OpenClawd compatibility survives simulated schema changes
- Tool executors complete successfully with security sandboxing enforced
- Notification delivery reaches all configured channels
- Web dashboard provides real-time coordination visibility

This comprehensive requirements document captures the full scope of the agent dispatch system implementation across all 6 phases.
