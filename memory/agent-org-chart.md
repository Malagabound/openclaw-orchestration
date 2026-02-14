# Agent Organizational Structure

*Designed 2026-02-07 | George = Orchestrator/Director*

---

## Architecture Overview

```
                        ┌─────────────┐
                        │   GEORGE    │
                        │ Orchestrator│
                        │  (DM/Main)  │
                        └──────┬──────┘
                               │
          ┌────────────┬───────┼───────┬────────────┐
          │            │       │       │            │
     ┌────┴────┐ ┌─────┴──┐ ┌─┴───┐ ┌─┴────┐ ┌────┴─────┐
     │  NORA   │ │  REX   │ │SCOUT│ │KEEPER│ │ SENTINEL │
     │Nth Degr.│ │Recurr. │ │Bkgnd│ │Bkgnd │ │  Bkgnd   │
     │ Group   │ │Revenue │ │Rsrch│ │Ops   │ │ Security │
     └─────────┘ └────────┘ └─────┘ └──────┘ └──────────┘
```

---

## 1. GEORGE — The Orchestrator

| Field | Value |
|-------|-------|
| **Type** | Orchestrator |
| **Where** | DM with Alan (main session) |
| **Trigger** | Always-on: heartbeats, DM messages, sub-agent reports |
| **Model** | claude-opus-4-6 (current) |

**Responsibilities:**
- Direct interface with Alan — all decisions flow through here
- Delegates heavy work to sub-agents via `sessions_spawn`
- Synthesizes reports from all agents into actionable summaries
- Manages MEMORY.md, daily logs, task tracking
- Handles ad-hoc requests, quick Q&A, conversational interaction

**Critical Rule:** George NEVER blocks on long-running tasks. Spawn a sub-agent, get back to Alan.

**Reports from sub-agents arrive via:**
- Sub-agent completion messages (automatic on spawn finish)
- Writing to `memory/agent-reports/` for async pickup during heartbeats
- Direct Telegram messages to relevant groups (agents with group access)

---

## 2. NORA — Nth Degree Analyst

| Field | Value |
|-------|-------|
| **Type** | Analyst |
| **Where** | Nth Degree group (`-1003801012047`) |
| **Trigger** | Group messages, on-demand from George, weekly cron |
| **Model** | claude-sonnet-4-20250514 (cost-efficient for routine work) |

**Responsibilities:**
- Monitor Nth Degree group for conversations needing action
- Track Optimize OS (seekingcertainty) development status
- Analyze support tickets from GoHighLevel / The Autopilot AI
- Summarize weekly progress on Alan's day-job SaaS
- Flag blockers or decisions needed → escalate to George

**Specific tasks:**
- Pull GitHub activity from `nthdegreecpas/seekingcertainty`
- Process GHL support tickets and draft responses
- Track client issues and patterns
- Weekly status report to George

**Implementation:**
```
# Cron: Weekly Nth Degree digest (Monday 8 AM)
openclaw cron add \
  --schedule "0 8 * * 1" \
  --label "nth-degree-weekly" \
  --channel telegram:-1003801012047 \
  --prompt "Review Optimize OS GitHub activity, open GHL tickets, and any unresolved items from this group. Post a concise weekly status update."
```

**Group behavior:** Responds to direct questions in the group. Stays silent on casual chat. Posts weekly digests unprompted.

---

## 3. REX — Recurring Revenue Analyst

| Field | Value |
|-------|-------|
| **Type** | Analyst |
| **Where** | Recurring Revenue group (`-1003843870702`) |
| **Trigger** | Group messages, research completions from Scout, daily cron |
| **Model** | claude-sonnet-4-20250514 |

**Responsibilities:**
- Curate and discuss passive income opportunities in the group
- Analyze product research results from Scout (scores, viability)
- Track progress on both tracks: digital products + micro-niche SaaS
- Post validated opportunities with recommendations
- Maintain running scoreboard of pipeline (discovered → validated → building → launched)

**Specific tasks:**
- When Scout completes research, Rex posts a summary to the group
- Tracks $20k/month goal progress
- Compares opportunities against each other
- Posts "This Week in Revenue" digest

**Implementation:**
```
# Cron: Revenue pipeline update (Wednesday + Saturday 9 AM)
openclaw cron add \
  --schedule "0 9 * * 3,6" \
  --label "revenue-pipeline" \
  --channel telegram:-1003843870702 \
  --prompt "Query the Product Prospector database for current pipeline status. Summarize opportunities by status (discovered/researching/validated/building). Post update to this group."
```

**Group behavior:** Active participant. Posts research findings, asks Alan for input on go/no-go decisions, tracks revenue milestones.

---

## 4. SCOUT — Research Tasker (Background)

| Field | Value |
|-------|-------|
| **Type** | Tasker |
| **Where** | Background (no group — reports to George + Rex) |
| **Trigger** | Cron (existing schedules), on-demand spawn from George |
| **Model** | claude-sonnet-4-20250514 |

**Responsibilities:**
- Execute all product/market research scans
- Run Apify actors for Gumroad, Etsy, G2, Product Hunt data
- Score opportunities using the 6-criteria system (≥20/30 threshold)
- Write results to Product Prospector database
- Create Google Docs for Phase 1/Phase 2 validation reports

**Absorbs these existing crons:**
- Product research scan (8 AM daily)
- Business acquisition scan (Mon/Thu 9 AM)

**Workflow:**
1. **Phase 1 Discovery:** Scout runs research scan → writes to Supabase
2. **Phase 2 Handoff:** When specialists find ≥20/30 opportunities → auto-spawn Scout for deep validation
3. **Scout Validation:** Scout completes Phase 2 research → validates quality before presenting to Alan
4. **Results Flow:** Scout writes validated findings to relevant specialist groups
5. **George Oversight:** George monitors handoffs and ensures Scout validation occurs

**Implementation:**
```
# Already running — just formalize the identity:
# Product scan cron → add label "scout-product-scan"
# Acquisition cron → add label "scout-acquisition-scan"

# On-demand (George spawns when Alan asks for specific research):
# sessions_spawn with task description, Scout handles end-to-end
```

---

## 5. KEEPER — Operations Tasker (Background)

| Field | Value |
|-------|-------|
| **Type** | Tasker |
| **Where** | Background (no group — reports to George) |
| **Trigger** | Cron (existing schedules), email-triggered, on-demand |
| **Model** | claude-sonnet-4-20250514 |

**Responsibilities:**
- Process emails across all 3 accounts (george@, alan@originutah, alan@roccoriley)
- Handle QuickBooks transaction categorization
- Process utility bills → update spreadsheet → move emails
- Process property management income → update spreadsheet
- Maintain rental property financial records

**Absorbs these existing crons:**
- Email agent (30-min cron)
- QB check (2 PM daily)

**Specific rules:**
- Jotform + "Pinnacle Chiropractic" → DELETE
- Make + error reports → ARCHIVE
- Utility bills → process → WinHaw Rentals folder
- QB uncategorized → assign property classes

**Workflow:**
1. Keeper processes emails/QB on schedule
2. Anything needing Alan's decision → writes to `memory/agent-reports/keeper-{date}.md` + flags for George
3. Routine completions → silent (logged to daily memory only)
4. Urgent items → George relays to Alan immediately

**Implementation:**
```
# Already running — formalize:
# Email cron (30 min) → label "keeper-email"
# QB cron (2 PM) → label "keeper-qb"

# Add: utility bill processor auto-trigger
# When keeper-email finds utility bill → spawns utility processing sub-task
```

---

## 6. SENTINEL — Guardian (Background)

| Field | Value |
|-------|-------|
| **Type** | Guardian |
| **Where** | Background (no group — alerts George on issues) |
| **Trigger** | Heartbeat checks, daily cron |
| **Model** | claude-haiku (lightweight, frequent checks) |

**Responsibilities:**
- Monitor system health (OpenClaw gateway, cron jobs running)
- Audit credential files exist and aren't expired
- Watch for unusual email patterns (phishing, account alerts)
- Verify backup processes
- Check that other agents completed their scheduled tasks
- Monitor Supabase/Netlify service status

**Specific checks:**
- Are all cron jobs still registered and firing?
- Any failed sub-agent tasks in the last 24h?
- Credential files present in `~/.openclaw/credentials/`?
- Any security-related emails (password reset, login alerts)?
- Disk space / system resources OK?

**Implementation:**
```
# Cron: Daily security audit (6 AM, before morning briefing)
openclaw cron add \
  --schedule "0 6 * * *" \
  --label "sentinel-audit" \
  --prompt "Run daily security and health audit. Check: 1) All cron jobs registered 2) Credential files exist 3) Recent agent task completions 4) System resources. Write report to memory/agent-reports/sentinel-{date}.md. Only alert George if issues found."
```

---

## Communication Flow

```
Alan ←→ George (DM)           # All human interaction
           │
           ├→ spawns Scout     # "Research X for me"
           ├→ spawns Keeper    # "Process that bill"  
           ├→ reads reports    # Heartbeat pickups from memory/agent-reports/
           │
Nth Degree Group ←→ Nora      # Autonomous in group, escalates to George
Recurring Rev Group ←→ Rex    # Autonomous in group, fed by Scout
                               
Sentinel → George              # Alerts only (never talks to Alan directly)
Scout → Rex                    # Research results flow to Rex for group posting
Scout → George                 # High-priority findings go direct
Keeper → George                # Decisions needed, urgent items
```

**Inter-agent communication method:** File-based via `memory/agent-reports/`
- Each agent writes `{agent}-{date}.md` 
- George reads during heartbeats
- Urgent items: agent includes `URGENT:` prefix → George relays immediately

---

## Morning Briefing (7 AM) — George Synthesizes

The existing 7 AM morning briefing becomes George's daily synthesis:

1. Read `memory/agent-reports/sentinel-{date}.md` (overnight security)
2. Read `memory/agent-reports/keeper-{date}.md` (email/QB summary)  
3. Read `memory/agent-reports/scout-{date}.md` (research findings)
4. Check Nora's last Nth Degree update
5. Check Rex's revenue pipeline status
6. Compile into Alan's morning briefing

---

## Implementation Plan

### Phase 1: Formalize Existing ✅ DONE (2026-02-08)
- [x] Document current cron jobs as agent roles (this file)
- [x] Create `memory/agent-reports/` directory
- [x] Relabel existing crons with agent names (scout-*, keeper-*)
- [x] Add Sentinel daily audit cron (6 AM daily, id: 263d3c36)

### Phase 2: All Agents ✅ DONE (2026-02-08)
- [x] Nora → Nth Degree group (Opus)
- [x] Rex → Software Subscriptions group (Opus)
- [x] Pixel → Digital Products group (Opus)
- [x] Haven → Rental/Realtor Biz group (Opus)
- [x] Vault → Investment Research group (Opus)
- [x] Scout → Background research (Opus)
- [x] Keeper → Background operations (Opus)
- [x] Sentinel → Background security (Sonnet)
- [x] All agents respond to all group messages (no mention-only gating)
- [ ] Configure Rex to receive Scout output

### Phase 3: Optimize (Week 3+)
- [ ] Tune models per agent (Haiku for Sentinel, Sonnet for others)
- [ ] Add inter-agent file protocol (`URGENT:` prefix handling)
- [ ] Build dashboards in George HQ... wait, that's retired. Taskr integration.
- [ ] Monitor token costs per agent, optimize

### Cost Considerations
| Agent | Model | Frequency | Est. Monthly Cost |
|-------|-------|-----------|-------------------|
| George | Opus | Always-on | Highest (main session) |
| Nora | Sonnet | Weekly + group msgs | Low |
| Rex | Sonnet | 2x/week + group msgs | Low |
| Scout | Sonnet | Daily + on-demand | Medium |
| Keeper | Sonnet | 48x/day (email) + QB | Medium |
| Sentinel | Haiku | Daily | Minimal |

---

## Future Expansion

**Potential new agents as needs arise:**
- **CLERK** (Assistant) — Dedicated to GoHighLevel support ticket handling
- **TRACKER** (Analyst) — Dedicated debt payoff progress + financial modeling  
- **BUILDER** (Tasker) — Code generation and deployment for new products
- **SOCIAL** (Assistant) — Twitter/social media management if Alan wants presence

**New Telegram groups would get:**
- Their own agent personality suited to the group's purpose
- Connection back to George for cross-group coordination

---

*This is a living document. Update as agents come online and roles evolve.*
