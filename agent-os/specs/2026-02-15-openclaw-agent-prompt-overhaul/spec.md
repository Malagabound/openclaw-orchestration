# Specification: OpenClaw Agent Prompt Overhaul

## Goal

Overhaul all OpenClaw agent prompts (create george.md, update 7 specialist prompts, update base_sop.md) and identity files to educate every agent about the new dispatch system, establish George as a pure coordinator with a reframed "Figure It Out" directive, and resolve contradictions between George's identity files and his orchestrator role.

## User Stories

- As Alan, I want George to intelligently delegate work to specialists without ever doing domain work himself, so that the right agent handles every request.
- As a specialist agent, I want to understand the dispatch system (leases, working memory, tool permissions, `<agent-result>` format) so that I operate correctly within the automated pipeline.
- As Alan, I want every agent to "Figure It Out" within their scope (George figures out coordination, specialists figure out execution) so that agents are resourceful and self-sufficient before escalating.

## Specific Requirements

**Create George Orchestrator Prompt (george.md)**
- Create `/Users/alanwalker/openclaw-orchestration/prompts/george.md` as a new file
- Implement a cardinal rule section: George NEVER does domain work (research, analysis, product creation, financial modeling, email drafting, code writing)
- Include a specialist agent directory table listing all 7 agents, their domains, and their activation status (Rex ACTIVE, Pixel ACTIVE, Scout ACTIVE, Keeper ACTIVE, Haven DEACTIVATED, Vault DEACTIVATED, Nora DEACTIVATED)
- Add a Delegation SOP: receive request from Alan, decompose into sub-tasks, create tasks via `create_task`, monitor via `get_dashboard_summary` or `get_coordination_summary`, deliver results back to Alan
- Add an Orchestrator "Figure It Out" directive: figure out WHO to route to, HOW to decompose tasks, HOW to unblock stuck agents -- but NEVER do the domain work yourself
- Describe George's coordination capabilities through the dispatch system: `create_task`, `complete_task`, `add_task_contribution`, `log_agent_activity`, `create_notification`, `squad_chat_post`, `get_dashboard_summary`, `agent_checkin`, `determine_agents`, `get_coordination_summary`. These are adapter methods on OpenClawdAdapter, available when George is used in direct chat sessions where the adapter is imported as a Python module. They are NOT universal tool-loop tools with YAML definitions. If George is ever dispatched through the supervisor daemon in the future, corresponding YAML tool definitions would need to be created in `tools/definitions/` to make these callable through the tool loop.
- Add an anti-patterns section listing things George must not do (e.g., "let me just quickly research this...", "I'll draft this email myself...", "let me analyze these financials...")
- Add a pre-action gate formatted as a bold decision box matching base_sop.md Decision Gate style: **"Decision Gate: Am I about to do domain work? If YES, delegate instead. If NO, proceed."**
- Define lightweight tasks George CAN do directly: system status checks, config updates, simple factual questions from memory, summarizing results from specialists
- Add multi-step request decomposition guidance: break complex requests into dependency chains of tasks assigned to different specialists
- Define Alan-facing response format: concise, include task IDs when delegating, report outcomes not process

**George's `<agent-result>` Format**
- George's work (delegation/coordination) produces different deliverables than specialist execution work. Define the following conventions for George's `<agent-result>` JSON:
  - `deliverable_content`: The delegation plan -- task IDs created, agents assigned to each, and the dependency chain between tasks
  - `confidence_score`: Routing confidence as a float 0.0-1.0 (1.0 = clear single-agent match, lower values when domain overlap makes routing ambiguous)
  - `working_memory` keys: Use a `delegation_plan` key containing task-to-agent mappings and dependency order
  - `follow_up_tasks`: Leave empty (George creates tasks directly via `create_task` during execution rather than declaring them as follow-ups in the result)

**Add Dispatch System Awareness to All Specialist Prompts**
- Add a "Dispatch System Awareness" section to each of: research.md, product.md, haven.md, vault.md, comms.md, meta.md, ops.md
- Explain that tasks arrive via the supervisor daemon polling coordination.db; the agent does not choose tasks
- Explain the lease lifecycle: task is claimed with an initial 300-second (5-minute) lease, heartbeat extends it every 2 minutes, hard timeout at 1800 seconds
- Explain working memory protocol: reads are scoped to the task's dependency chain, values have a 5000 character limit, keys upsert with UNIQUE(task_id, agent_name, key)
- Explain tool permissions: tools have allowed_agents and denied_agents lists; denied takes precedence; if an agent calls a tool it lacks permission for, the call returns an access-denied error
- Explain context budget: if the assembled prompt exceeds the provider's context window, skill summaries are trimmed first, then the task description is truncated
- Explain squad chat milestones: during long tasks (every 4 tool calls, max 3 updates), post progress to squad_chat so other agents and George have visibility
- Explain health monitoring and self-healing: the dispatch system runs provider canary tests on a configurable interval (default 6 hours), stores results in provider_health, and uses a 5-tier self-healing model (rate-limit backoff, format variation, fallback provider, graceful degradation, escalation); agents do not interact with this system directly but should be aware that provider failures may trigger automatic fallback to a different model/provider mid-pipeline

**Add Specialist "Figure It Out" Directive to All Specialist Prompts**
- Add a "Figure It Out" section to each specialist prompt
- Core message: "Figure out HOW to do the work. When tools fail or approaches don't work, try 3+ alternatives before declaring failure. Don't go back to George asking for instructions."
- Include the mandate: before setting status to `failed`, the agent MUST have tried at least 3 different approaches and documented why each failed
- Preserve each agent's existing domain expertise, SOP steps, tool lists, and working memory keys -- the new sections are additive
- Update the existing retry-once Decision Gates in Keeper's Step 3 (line 70: "IF maintenance operation fails, THEN retry once; if fails again, set status to `failed` and alert") and Nora's Step 3 (line 71: "IF tool execution fails, THEN retry once; if fails again, set status to `failed`") to align with the 3+ approach policy. Replace the "retry once; if fails again" pattern with "try at least 3 different approaches before setting status to `failed`" in both cases.

**Add Cross-Agent Handoff Protocol**
- Add a "Cross-Agent Handoff" section to each specialist prompt
- Define Phase 1 to Phase 2 Scout validation triggers: when a specialist produces a deliverable in a research or analysis domain, create a follow-up task for Scout validation (see "Scout validation confidence threshold" note below for when to trigger)
- Define escalation to George: when an agent is blocked on something outside its domain, it should set status to `blocked` and describe the cross-domain need in the deliverable_summary so George can route it
- Define working memory as the inter-agent data bus: store key findings using descriptive keys so downstream agents can reference them without needing direct communication

**Scout Validation Confidence Threshold Clarification**
- Three separate threshold systems exist and serve different purposes; the spec must document the relationship:
  - **base_sop.md confidence_score (0.0-1.0)**: A self-assessed quality metric included in every `<agent-result>` JSON payload. This is a continuous float used for result reporting.
  - **Rex's internal routing threshold (< 0.5)**: When Rex's own confidence on key findings drops below 0.5, Rex flags those findings for Scout review (already in research.md Step 3 Decision Gate). This is Rex's self-assessment trigger.
  - **SOUL.md scoring (20/30 or 30/30)**: A structured rubric score used in the Phase 1 to Phase 2 validation pipeline (CEO Validation Rule). Phase 1 results scoring >= 20/30 automatically proceed to Phase 2 Scout validation.
- The Cross-Agent Handoff section should use Rex's existing < 0.5 pattern as the model: each specialist triggers Scout validation when the specialist's own confidence on a deliverable drops below 0.5, indicating uncertain results that need external validation. This is separate from the Phase 1/Phase 2 pipeline which uses the 20/30 rubric score.

**Update Base SOP (base_sop.md)**
- Add a "Dispatch System Context" preamble section before Step 1 explaining how tasks arrive (supervisor daemon claims from coordination.db, agent receives task via prompt assembly)
- Add a conditional path at the top of the preamble: "If you are an orchestrator agent (e.g., George), skip Step 3 (Execute Work) and follow your persona's Delegation SOP instead. george.md contains the replacement for Step 3: task decomposition and delegation. Steps 1, 2, 4, and 5 still apply."
- Add a shared "Figure It Out" directive between Step 2 (Analyze Requirements) and Step 3 (Execute Work)
- Update Step 3's Decision Gate to be consistent with the "Figure It Out" directive: replace "IF a tool call fails, THEN retry once. If it fails again, set status to `failed` with the error summary." with "IF a tool call fails, THEN try at least 3 different approaches (alternative tools, different parameters, workaround strategies) before setting status to `failed`. Document each attempt and why it failed."
- Reinforce the `<agent-result>` output format in Step 5 with a note that the dispatch system parses this block programmatically -- malformed JSON will cause the dispatch run to fall back to raw response
- Add working memory protocol details: mention the 5000 char value limit, UNIQUE key behavior, and dependency-scoped reads
- Add a tool permission awareness note in Step 3: if a tool call returns an access-denied error, do not retry the same tool -- instead report the permission gap as a blocker
- Add context budget awareness note: if the prompt feels truncated (missing skill details or shortened task description), the agent should proceed with available information rather than requesting re-dispatch

**Section Insertion Order for Specialist Prompts**
- Insert the three new sections in this order: (1) Dispatch System Awareness, (2) Figure It Out, (3) Cross-Agent Handoff
- Insert them after the "Quality Standards" section and before the "Routing Keywords" section in each specialist prompt

**Update Identity Files**
- Update `AGENTS.md`: replace the full "Be the Orchestrator" section and the "Figure It Out Directive" section (lines 32-70, from the `## Be the Orchestrator` header through the end of "Figure It Out Directive" content) with a brief cross-reference to `prompts/george.md` as the single source of truth for orchestrator behavior and the Figure It Out directive. The replacement text should be: **"## Orchestrator Role & Figure It Out Directive\n\nSee `prompts/george.md` for the complete orchestrator prompt, delegation SOP, and Figure It Out directive. George coordinates specialists; he does not do domain work."**
- Update `MEMORY.md`: replace the line "George: Research niches, present options, define strategy, handle customers/sales/marketing, BUILD THE PRODUCT (vibe coding)" (line 95) with: **"George: Coordinate specialist agents, decompose tasks, route work to Rex/Pixel/Scout/Keeper, monitor progress, deliver results to Alan. George delegates ALL domain work -- research, product creation, email, operations -- to the appropriate specialist."**
- Update `SOUL.md`: replace the full "Operating Model: Orchestrator-First" section (lines 123-160, from "## Operating Model: Orchestrator-First" through the end of the "Operating Rules" subsections) with a brief cross-reference: **"## Operating Model: Orchestrator-First\n\nSee `prompts/george.md` for the complete orchestrator prompt, delegation SOP, operating rules, and dispatch-aware coordination protocol. The principle remains: I am the conductor, not the musician."**

**Rename Prompt Files to Match Functional Config Keys (Revised Approach)**
- Instead of renaming AGENT_SKILLS keys (which would break the self-healing system's naming convention and require a DB migration), rename the prompt *files* to match the existing functional config keys:
  - `prompts/research.md` -> `prompts/research.md`
  - `prompts/product.md` -> `prompts/product.md`
  - `prompts/comms.md` -> `prompts/comms.md`
  - `prompts/ops.md` -> `prompts/ops.md`
  - `prompts/meta.md` -> `prompts/meta.md`
  - `prompts/haven.md` -- stays as-is (new AGENT_SKILLS entry added)
  - `prompts/vault.md` -- stays as-is (new AGENT_SKILLS entry added)
- This eliminates all conflicts with the self-healing system: no DB migration needed, existing tasks with `assigned_agent='research'` still work, recovery code uses dynamic lookups so file renames are invisible to it.

**Add New AGENT_SKILLS Entries (config.py)**
- Add `"haven": []` -- real estate agent, no dedicated MCP skills yet
- Add `"vault": []` -- business acquisition agent, no dedicated MCP skills yet
- Add `"george": []` -- orchestrator, coordination only (empty skills list to avoid consuming context budget)
- AGENT_SKILLS keys remain functional names (`research`, `product`, `comms`, `ops`, `meta`). No existing keys are renamed.

**Add New Entries to openclawd.config.yaml**
- Add `haven`, `vault`, `george` entries to `agent_models`, `agent_fallbacks`, `agent_budgets`, and `agent_lease_defaults` sections.
- No existing keys are renamed in the YAML config.

**Prompt Update Idempotency**
- All prompt file updates described in this spec should be idempotent. If the target sections (Dispatch System Awareness, Figure It Out, Cross-Agent Handoff) already exist in a prompt file, update them in place rather than appending duplicates. Check for the section header before inserting.

## Visual Design

No visual mockups provided for this specification.

## Systems to Integrate

### Dispatch System Prompt Assembly

**Key Files**: `/Users/alanwalker/openclaw-orchestration/agent-dispatch/agent_prompts.py`

**Integration Points**:
- `build_prompt()` loads `prompts/{agent_name}.md` as the persona file -- creating `prompts/george.md` automatically makes it available when `agent_name="george"`
- `build_prompt()` loads skill summaries from `AGENT_SKILLS[agent_name]` -- adding "george" to AGENT_SKILLS enables George's prompt assembly
- `agent_name` parameter must match a key in AGENT_SKILLS for skill loading, AND must match a filename stem in `prompts/` for persona loading

**Recommended Patterns**:
- Follow the exact naming convention: `prompts/{agent_name}.md` where agent_name matches the key in AGENT_SKILLS
- The persona file is concatenated after base_sop.md and before skill summaries in the system message

**Gotchas**:
- If George has skills listed in AGENT_SKILLS, those SKILL.md files will be injected into his prompt, consuming context budget -- keep his skills list empty
- After the file rename, AGENT_SKILLS keys (`research`, `product`, etc.) now match the prompt filenames (`research.md`, `product.md`, etc.) -- `build_prompt()` can correctly load persona files.

### Dispatch System Config

**Key Files**: `/Users/alanwalker/openclaw-orchestration/agent-dispatch/config.py`

**Integration Points**:
- `AGENT_SKILLS` dict (line 29-92) maps agent names to skill directory lists
- Agent names used here must match the persona filename stem (e.g., "george" maps to `prompts/george.md`)

**Recommended Patterns**:
- Use lowercase single-word agent names that match prompt filenames: `research`, `product`, `comms`, `ops`, `meta`, `george`

**Gotchas**:
- AGENT_SKILLS keys are unchanged (still functional names). No code audit needed for key references.

### Dispatch Config Template (openclawd.config.yaml)

**Key Files**: `/Users/alanwalker/openclaw-orchestration/agent-dispatch/openclawd.config.yaml`

**Integration Points**:
- `agent_models`, `agent_fallbacks`, `agent_budgets`, and `agent_lease_defaults` all map agent name keys to per-agent configuration values
- Keys use functional names (`research`, `product`, etc.) matching AGENT_SKILLS keys. New agents (haven, vault, george) need entries added.

**Recommended Patterns**:
- Keep YAML keys in sync with AGENT_SKILLS keys in `config.py` at all times
- When adding a new agent, add entries to all four per-agent sections (models, fallbacks, budgets, lease defaults) to avoid falling back to global defaults unexpectedly

**Gotchas**:
- Users with existing config copies only need to add haven, vault, george entries -- no key renames required.

### Agent Supervisor Daemon

**Key Files**: `/Users/alanwalker/openclaw-orchestration/agent-dispatch/agent_supervisor.py`, `/Users/alanwalker/openclaw-orchestration/agent-dispatch/cli.py`

**Integration Points**:
- `agent_supervisor.py` and `cli.py` use functional agent names (`research`, etc.) for default agent assignments. These remain correct since AGENT_SKILLS keys are unchanged.

**Recommended Patterns**:
- Use functional key names (`research`, `product`, `comms`, etc.) in any code that sets or defaults `assigned_agent` values

**Gotchas**:
- If the supervisor daemon defaults to an agent name that does not exist as an AGENT_SKILLS key, `build_prompt()` will fail to load the persona file and skill summaries.

### Agent Runner Tool Loop

**Key Files**: `/Users/alanwalker/openclaw-orchestration/agent-dispatch/agent_runner.py`

**Integration Points**:
- `run_agent()` accepts `agent_name` parameter that must match AGENT_SKILLS key
- `_check_tool_permission()` enforces allowed_agents/denied_agents from YAML tool definitions
- `_post_milestone_update()` posts to squad_chat every 4 tool calls (max 3 per task)
- `_upsert_working_memory()` enforces 5000 char limit on values

**Recommended Patterns**:
- George's coordination tools (create_task, complete_task, etc.) are adapter methods on OpenClawdAdapter, not registered universal tools. The prompt should describe these as capabilities available through the dispatch system rather than as tool-call-loop tools unless YAML definitions are created for them.

**Gotchas**:
- George's tools are currently adapter methods, not registered universal tools -- the prompt should describe these as capabilities available through the dispatch system

### Working Memory System

**Key Files**: `/Users/alanwalker/openclaw-orchestration/agent-dispatch/agent_prompts.py` (lines 67-111), `/Users/alanwalker/openclaw-orchestration/agent-dispatch/agent_runner.py` (lines 174-221)

**Integration Points**:
- `_load_working_memory_with_dependencies()` scopes reads to the task and its dependency chain via task_dependencies table
- `_upsert_working_memory()` uses INSERT OR REPLACE with UNIQUE(task_id, agent_name, key)
- Working memory entries are injected into the user message with XML delimiters via `wrap_cross_agent_data()`

**Recommended Patterns**:
- Each agent prompt should list recommended working memory key names (already done in existing prompts like research.md, product.md, etc.)
- Key naming should be descriptive and consistent across agents for cross-referencing

**Gotchas**:
- Values exceeding 5000 characters are silently truncated -- agents should be aware of this limit when storing large outputs

### Health Monitoring and Self-Healing System

**Key Files**: `/Users/alanwalker/openclaw-orchestration/agent-dispatch/health/health_monitor.py`, `/Users/alanwalker/openclaw-orchestration/agent-dispatch/health/self_healer.py`

**Integration Points**:
- Health monitor runs canary tests on a configurable interval (default 6 hours) and stores pass/fail in `provider_health` table
- Self-healer implements 5-tier recovery: (1) rate-limit backoff, (2) format variation, (3) fallback provider switch, (4) graceful degradation with accelerated checks, (5) diagnostic escalation
- Conformance tracking monitors tool_calling pass rates over a rolling 20-check window, switching to prompt-based mode if reliability drops below 80%

**Recommended Patterns**:
- Agents do not interact with health monitoring directly. The Dispatch System Awareness section should explain that provider failures may trigger automatic fallback, which means the agent might be served by a different model than expected.

**Gotchas**:
- If the agent experiences unexpected tool format issues, it may be because the system has switched to a fallback provider with different capabilities. The agent should proceed with available tools rather than failing outright.

### OpenClawd Adapter (George's Coordination Tools)

**Key Files**: `/Users/alanwalker/openclaw-orchestration/agent-dispatch/openclawd_adapter.py`

**Integration Points**:
- The adapter exposes these methods (and ONLY these): `create_task`, `complete_task`, `add_task_contribution`, `log_agent_activity`, `create_notification`, `squad_chat_post`, `get_dashboard_summary`, `agent_checkin`, `determine_agents`, `get_coordination_summary`
- Methods `get_task_status` and `get_task_contributions` do NOT exist on the adapter

**Recommended Patterns**:
- George's prompt should reference only the methods listed above. For monitoring task status, George should use `get_dashboard_summary` or `get_coordination_summary` rather than nonexistent per-task status methods.
- George's prompt is designed for direct chat sessions where the adapter is available as a Python import, not for automated supervisor dispatch through the tool loop. Describe these as "coordination capabilities through the dispatch system" rather than as tool-call-loop tools. If George is ever dispatched through the supervisor daemon in the future, corresponding YAML tool definitions would need to be created in `tools/definitions/` to make these capabilities callable through the universal tool loop.

**Gotchas**:
- These are adapter methods, not universal tools registered in the tool loop. George cannot call them via the standard tool_call mechanism unless corresponding YAML definitions are created in `tools/definitions/`. Creating those YAML definitions is out of scope for this spec.

## Components to Reuse (Existing)

**base_sop.md** (`/Users/alanwalker/openclaw-orchestration/prompts/base_sop.md`)
- How used: Updated in place with new sections; remains the shared foundation for all agents

**Agent persona prompts** (`/Users/alanwalker/openclaw-orchestration/prompts/{research,product,haven,vault,comms,meta,ops}.md`)
- How used: Each is updated in place with 3 new additive sections (Dispatch System Awareness, Figure It Out, Cross-Agent Handoff)

**AGENT_SKILLS mapping** (`/Users/alanwalker/openclaw-orchestration/agent-dispatch/config.py`)
- How used: Add new entries for haven, vault, george with empty skills lists. Existing keys unchanged.

**Dispatch config template** (`/Users/alanwalker/openclaw-orchestration/agent-dispatch/openclawd.config.yaml`)
- How used: Add haven, vault, george entries to all four per-agent sections (agent_models, agent_fallbacks, agent_budgets, agent_lease_defaults). Existing keys unchanged.

**Identity files** (`/Users/alanwalker/openclaw-orchestration/{AGENTS.md,MEMORY.md,SOUL.md}`)
- How used: Targeted text replacements to consolidate orchestrator identity into george.md; replaced sections become brief cross-references

## New Components to Build

### Shared Components (Multi-Module Use)

None. This feature creates/updates markdown prompt files and a Python config dict. No shared UI or code components are needed.

### Module-Specific Components

| Component | Purpose | File Path |
|-----------|---------|-----------|
| george.md | George orchestrator persona prompt | `/Users/alanwalker/openclaw-orchestration/prompts/george.md` |

## Existing Code to Leverage

**Agent prompt assembly pipeline (`agent_prompts.py`)**
- The `build_prompt()` function already handles persona file loading, skill injection, working memory scoping, and context budget enforcement
- Creating `george.md` and adding "george" to AGENT_SKILLS is all that's needed for George to work within the dispatch pipeline
- No changes to `agent_prompts.py` logic are required -- prompt files now match AGENT_SKILLS keys

**Existing specialist prompt structure**
- All 7 specialist prompts follow an identical structure: Identity block, Expertise list, Domains list, Allowed Tools list, SOP Workflow with numbered steps and decision gates, Quality Standards, Routing Keywords
- New sections (Dispatch Awareness, Figure It Out, Cross-Agent Handoff) should be inserted consistently in all 7 files, after the Quality Standards section and before Routing Keywords, in the order: (1) Dispatch System Awareness, (2) Figure It Out, (3) Cross-Agent Handoff

**Base SOP step structure**
- The base_sop.md already uses STATUS prefixes, decision gates, and the `<agent-result>` format
- New sections should follow the same structural conventions (headers, bold decision gates, bold status labels)

**SOUL.md orchestrator rules**
- SOUL.md already contains an "Operating Model: Orchestrator-First" section with rules like "I COORDINATE, I DON'T EXECUTE"
- george.md should expand on these rules with dispatch-specific detail; the SOUL.md section will be replaced with a cross-reference to george.md

**AGENTS.md specialist directory**
- AGENTS.md already contains the specialist agent architecture table with names, domains, and activation status
- george.md should include a self-contained copy of the specialist directory for dispatch context (since george.md is assembled into the prompt independently)

## Out of Scope

- Creating new YAML tool definitions for George's coordination tools (create_task, complete_task, etc.) -- these are adapter methods, not universal tools
- Modifying `agent_runner.py` or `dispatch_db.py` dispatch logic -- the dispatch system code is stable and does not need logic changes for this prompt overhaul (only docstring updates in `agent_runner.py` and `dispatch_db.py` are in scope)
- Building a george-specific dispatch workflow or routing logic in the supervisor daemon
- Changing how the supervisor daemon selects which agent to dispatch -- that is a task assignment concern, not a prompt concern
- Creating new tools or executors for any agent
- Modifying the `<agent-result>` JSON schema or adding new fields
- Changing the YAML tool definition format or adding new tool YAML files
- Updating the orchestrator-dashboard UI or coordination.db schema
- Implementing inter-agent direct messaging or real-time communication beyond squad_chat
- Automating the Phase 1 to Phase 2 handoff in code -- the prompt update tells agents to create follow-up tasks for Scout, but the automation logic is not in scope
- Creating YAML tool definitions for George's adapter methods -- George's tools remain adapter-level capabilities described in his prompt, not registered in the universal tool loop
