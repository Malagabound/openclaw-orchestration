# Requirements: OpenClaw Agent Prompt Overhaul

## Summary

Overhaul all OpenClaw agent prompts to integrate dispatch system awareness, establish George as a pure coordinator, add "Figure It Out" directives, and resolve identity contradictions across AGENTS.md, MEMORY.md, and SOUL.md.

## Acceptance Criteria

### George Orchestrator Prompt (george.md)
- [ ] `prompts/george.md` exists and is loadable by `build_prompt("george", ...)`
- [ ] George's prompt contains a cardinal rule prohibiting domain work
- [ ] George's prompt lists only adapter methods that actually exist on OpenClawdAdapter: `create_task`, `complete_task`, `add_task_contribution`, `log_agent_activity`, `create_notification`, `squad_chat_post`, `get_dashboard_summary`, `agent_checkin`, `determine_agents`, `get_coordination_summary`
- [ ] George's prompt includes a pre-action decision gate in base_sop.md Decision Gate format
- [ ] George's prompt includes a specialist directory with activation statuses

### Dispatch System Awareness (All 7 Specialist Prompts)
- [ ] Each of rex.md, pixel.md, haven.md, vault.md, nora.md, scout.md, keeper.md contains a "Dispatch System Awareness" section
- [ ] Lease lifecycle documented with specific values: 300s initial, 120s heartbeat, 1800s hard timeout
- [ ] Working memory protocol documented: 5000 char limit, UNIQUE upsert, dependency-scoped reads
- [ ] Health monitoring and self-healing awareness mentioned (5-tier model, automatic fallback)
- [ ] Sections are inserted after Quality Standards and before Routing Keywords

### Figure It Out Directive
- [ ] Each specialist prompt contains a "Figure It Out" section
- [ ] base_sop.md Step 3 Decision Gate updated: "retry once" replaced with "try 3+ approaches"
- [ ] The Figure It Out section in base_sop.md is placed between Step 2 and Step 3
- [ ] george.md contains an orchestrator-scoped Figure It Out (coordination, not domain work)

### Cross-Agent Handoff Protocol
- [ ] Each specialist prompt contains a "Cross-Agent Handoff" section
- [ ] Scout validation trigger uses < 0.5 confidence pattern (matching Rex's existing threshold)
- [ ] The relationship between confidence_score (0.0-1.0), Rex's < 0.5 threshold, and SOUL.md's 20/30 rubric is documented

### Base SOP Updates
- [ ] Dispatch System Context preamble added before Step 1
- [ ] Orchestrator conditional path explicitly states george.md replaces Step 3
- [ ] Tool permission awareness note present in Step 3
- [ ] Context budget awareness note present
- [ ] `<agent-result>` programmatic parsing note present in Step 5

### Config Updates
- [ ] AGENT_SKILLS keys renamed from functional names to persona names (research -> rex, product -> pixel, comms -> nora, ops -> keeper, meta -> scout)
- [ ] `"george": []` entry added to AGENT_SKILLS
- [ ] Supervisor daemon and any code referencing old key names audited and updated

### Identity File Consolidation
- [ ] AGENTS.md "Be the Orchestrator" and "Figure It Out Directive" sections replaced with cross-reference to george.md
- [ ] MEMORY.md "BUILD THE PRODUCT" line replaced with delegation-oriented language
- [ ] SOUL.md "Operating Model: Orchestrator-First" section (lines 123-160) replaced with cross-reference to george.md

### Idempotency
- [ ] Running the prompt updates a second time does not create duplicate sections
