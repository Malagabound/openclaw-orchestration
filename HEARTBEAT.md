# HEARTBEAT.md

## Periodic Checks

Check `memory/heartbeat-state.json` for last check timestamps. Only run a check if enough time has passed.

### Multi-Agent Coordination (Every 15 minutes - PRIORITY)

**15-minute agent check-in system** (following SiteGPT model):

```python
# George coordination check
exec python3 orchestrator-dashboard/heartbeat_integration.py status
```

**What this does:**
- Monitors multi-agent system health
- Tracks task progress across specialist agents
- Reports coordination status and pending notifications
- Ensures no tasks fall through cracks

**Specialist agent check-ins** (happens automatically via their heartbeats):
- Rex (Research) - checks for new research/analysis tasks
- Pixel (Digital Products) - checks for product validation work
- Haven (Real Estate) - checks for property/investment tasks  
- Vault (Business Acquisition) - checks for deal analysis work
- Scout (Validation) - checks for quality control needs
- Keeper (Operations) - checks for maintenance/email tasks

**Agent coordination flow:**
1. Each specialist checks coordination dashboard every 15 minutes
2. Reviews new tasks in their domain + cross-domain opportunities
3. Adds contributions/insights if relevant to their expertise
4. Reports progress on assigned deliverables
5. Posts insights to squad chat if valuable for other agents

### 0. Activity Logging (continuous)
- Log completed tasks to `memory/activity-log.md`
- Include timestamp, category, and brief description

### 1. Process Observation Review (every 1-2 hours)
- Review `memory/process-observations.md`
- Add any new observations from recent work
- Note friction points, patterns, improvement ideas
- **For each focus group, ask:** "What could I do here that Alan hasn't thought of?"
- **If I identify an improvement I can build**: Build it, create PR on `dev`, log to activity-log.md
- Post suggestions to the relevant Telegram group - don't wait to be asked

### 2. Email Check (every 1 hour)
- Open Gmail for george@originutah.com
- Look for forwarded utility bills or property management emails from Alan
- If found: process them using the rental-utility-processor skill
- Update lastChecks.email timestamp

### 3. Taskr Sync (continuous)
- Track all work in Taskr (replaced George HQ Kanban)
- Update task status as work progresses (open → wip → done)
- Alan monitors via taskr.one dashboard — no manual check needed

### 4. Trend/Opportunity Scan (every 4-6 hours)
- Scan for micro-SaaS opportunities, competitor moves, trending pain points
- Sources: web search for Indie Hackers launches, Reddit pain points, X/Twitter trends
- Post findings to relevant Telegram group (Software Subscriptions or Digital Products)
- Only surface genuinely interesting opportunities (not noise)

### 5. Moltbook Check (every 4-6 hours, once claimed)
- Check Moltbook feed for interesting posts from other agents
- Look for: productivity tips, tool recommendations, workflow ideas
- Engage thoughtfully (not spam)
- Note useful learnings in `memory/moltbook-learnings.md`

## Daily Tasks

### Morning Briefing (7 AM MST via cron)
- Handled by cron job, not heartbeat
- Report: what I did, suggestions, tasks I could work on today
- Think independently - don't wait for assignments

### Self-Reflection Cycle (every 2-3 hours)
- Run `self-reflection check` — if ALERT, do a structured reflection
- Scan recent work for: mistakes, friction points, successful patterns
- Log insights via `self-reflection log <tag> <miss> <fix>`
- Run `reflect` if complex tasks or corrections happened since last check
- Check `.learnings/*.md` for pending items ready to promote
- Promote mature learnings → SOUL.md, AGENTS.md, TOOLS.md
- Check for cognitive gaps (self-evolving): did any task reveal unexpected weakness?
- Update `memory/heartbeat-state.json` with `lastReflection` timestamp

### Daily File Audit (once per day, afternoon)
Check `memory/heartbeat-state.json` for `lastAudit` timestamp. If >24h, run audit:

**Files to review:**
- `AGENTS.md` — workflow rules, delegation patterns
- `MEMORY.md` — long-term memories
- `TOOLS.md` — tool notes, gotchas
- `SOUL.md` — behavioral guidelines
- `IDENTITY.md` — persona details
- `USER.md` — info about Alan
- `HEARTBEAT.md` — this file
- `.learnings/*.md` — pending items to resolve or promote

**Look for:**
- Outdated information that's no longer true
- Conflicting rules across files
- Undocumented new workflows we've established
- Lessons from recent failures that should be promoted
- Stale learnings that were fixed but not marked resolved

**Output:** If changes needed, propose them to Alan. Don't auto-edit core files without approval (except memory/).

### Weekly Security Check (Sundays)
- Run `openclaw security audit`
- Review any warnings
- If `.learnings/ERRORS.md` has security-related entries, escalate

## Rules
- **ORCHESTRATOR ROLE:** I oversee systems, I don't do the work myself
- Run checks silently — don't message Alan unless there's something actionable  
- Late night (11pm-7am MST): process things silently, report in morning
- Update state file after each check
- **If work needs doing:** Spawn appropriate agent, don't do it myself
- **Always be thinking:** How can I advance Alan's goals (debt payoff + $20k passive income)?

## Oversight Responsibilities
- **Email processing** → Keeper handles this (check it's working)
- **Research pipelines** → Scout + specialists handle (check they're running)
- **Research handoffs** → Monitor Phase 1 scores ≥20/30 get handed to Scout automatically
- **Group agent activity** → Specialists post findings (monitor for gaps)
- **Cron job execution** → Background agents execute (verify completion)
- **System health** → Sentinel monitors (ensure alerts reach me)

## Research Handoff Monitoring (CRITICAL)
**Watch for handoff failures:**
- Opportunities scoring ≥20/30 that DON'T get handed to Scout
- Specialists doing Phase 2 work themselves (role violation)
- Scout results not flowing back to specialists
- Missing Phase 2 validations

**Intervention triggers:**
- If specialist doesn't hand off ≥20/30 score → I spawn Scout directly
- If specialist attempts Phase 2 → Redirect to proper handoff protocol
- If Scout doesn't report back → Follow up and ensure completion

---

*Updated: 2026-02-05 — Added daily file audit and weekly security check from Matthew Berman video recommendations.*
