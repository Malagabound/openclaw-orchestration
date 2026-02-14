# Video Transcript: Use Clawdbot like a PRO (Advanced Use Cases)

**Source:** https://www.youtube.com/watch?v=3GrG-dOmrLU
**Author:** Matthew Berman
**Date Transcribed:** 2026-02-05

## Key Takeaways for Implementation

### 1. Telegram Groups with Topics
- Don't just DM - use Telegram groups with topic channels
- Each topic = separate conversation thread
- Benefits:
  - Parallel tasks without confusion
  - Saves context window (only loads that topic's history)
  - Better organization
- Setup: Create group → Add Claudebot → Make admin → Tell it to respond to every message (not just tagged)

### 2. Daily File Review/Audit
- Have Claudebot do daily audit of:
  - agents.md
  - memory.md
  - tools
  - soul
  - identity
  - user
  - heartbeat
- Look for: outdated info, conflicting rules, undocumented workflows, lessons from failures
- Propose changes → Human approves

### 3. Model Selection Strategy
- Primary: Sonnet 4.5 (workhorse, cheaper)
- Fallback chain: Gemini Flash → Opus → OpenRouter
- Use cases:
  - Basic: Haiku (fast, cheap)
  - Coding: Sonnet
  - Complex coding: Opus
  - Cron jobs: Local models or cheaper models
- Commands: `/model` to show/set, or just say "switch to [model]"

### 4. Skills vs Tools Architecture
- Skills = repeatable multi-step processes using tools
- Tools = actual code that accomplishes things
- Skills created through natural language
- Can delegate to other agents (cursor agent for complex coding)

### 5. Security Best Practices
- All API keys in .env file only
- Never include .env in git
- Run `openclaw security audit` regularly
- `openclaw security audit --fix` to auto-fix
- Use VPS (like Hostinger) for isolation
- **Clean vs Dirty Data concept:**
  - Anything from internet = dirty data
  - Prompt injection risk from emails, external content
  - Better models = less susceptible to injection
- Don't blindly trust ClawHub skills - scan first or write your own
- Plan mode for complex tasks - propose before executing

### 6. Cron Jobs for Scheduling
- One-off reminders: "in 1 hour, remind me..."
- Recurring: "every Sunday tell me which recycling..."
- Can handle complex schedules from images/documents

### 7. Real Use Cases from Video
1. **Video Research Pipeline:**
   - Drop link in Telegram
   - Claudebot researches via Brave API + checks Twitter via Grok
   - Creates Asana task automatically

2. **YouTube Analytics:**
   - Connected YouTube Data API + Analytics API
   - Ask for video performance → Posts to Telegram/Slack

3. **Meeting Prep:**
   - Morning cron job
   - Checks calendar for external meetings
   - Researches each person
   - Summarizes in Telegram

---

## Raw Transcript
(full text saved for reference - see original file)
