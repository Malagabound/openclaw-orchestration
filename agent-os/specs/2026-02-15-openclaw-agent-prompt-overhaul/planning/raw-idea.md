# Raw Idea: OpenClaw Agent Prompt Overhaul

Overhaul all OpenClaw agent prompts (George + 7 specialists) to:

1. CREATE a dedicated george.md orchestrator prompt that makes George a pure coordinator/delegator with a reframed "Figure It Out" skill focused on coordination (figuring out WHO to route to, HOW to decompose tasks, HOW to unblock things) rather than doing domain work himself.

2. UPDATE all specialist agent prompts (rex.md, pixel.md, haven.md, vault.md, nora.md, scout.md, keeper.md) to educate them about the new openclawd-agent-dispatch-system infrastructure:
   - How the dispatch system works (supervisor daemon polls coordination.db, claims tasks via leases)
   - The <agent-result> XML output format they MUST produce
   - Working memory protocol (dependency-scoped reads, 5000 char value limit, UNIQUE key upserts)
   - Tool registry and universal tool schema (allowed_agents, denied_agents, idempotency)
   - Context budget enforcement (skills may be trimmed if prompt exceeds provider limits)
   - Squad chat milestone updates during long tasks
   - Health monitoring and self-healing awareness

3. ADD a "Figure It Out" directive to every specialist agent (currently missing from all of them) — when tools fail or approaches don't work, try alternatives before declaring failure.

4. ADD cross-agent handoff protocols — Phase 1→2 Scout validation triggers, escalation to George, cross-domain coordination via working memory.

5. UPDATE base_sop.md to incorporate dispatch system awareness and the shared "Figure It Out" directive.

6. RESOLVE contradictions in George's identity files (AGENTS.md "Figure It Out" and MEMORY.md "BUILD THE PRODUCT" conflicting with orchestrator role).

7. ADD George to the dispatch config (AGENT_SKILLS in config.py) and restrict his tools to coordination-only.

8. CONSOLIDATE George's identity — make george.md the single source of truth, cross-reference from AGENTS.md/SOUL.md instead of duplicating orchestrator rules across 5 files.
