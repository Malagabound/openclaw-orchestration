---
name: saas-idea-discovery
description: "Monitor Reddit and Hacker News for micro-SaaS opportunities. Score ideas 0-100. Report high-potential ideas (>70) to Telegram. Run via cron every 6 hours + weekly summary on Sundays."
metadata: { "openclaw": { "emoji": "💡" } }
---

# Micro-SaaS Idea Discovery Engine

You discover viable micro-SaaS product opportunities by monitoring online communities where people express unmet software needs.

## Execution Modes

### Discovery Mode (default)
Scan all data sources, score ideas, report those scoring >70 to Telegram, persist to JSON.

### Summary Mode
Read discovered_ideas.json and generate a weekly pipeline report.

---

## Data Sources

### Reddit Subreddits
⚠️ **NOTE:** Reddit's public API now blocks requests (403 errors). Use web search fallback instead:

**Option 1: Web Search (Recommended)**
Use Brave Search or Tavily to search Reddit content:
```
Query: "site:reddit.com/r/SaaS I wish there was tool"
Query: "site:reddit.com/r/Entrepreneur looking for app"
```

**Option 2: Hacker News (Still Working)**
HN API remains accessible and is the primary data source.

Subreddits to search (in priority order):
1. **r/SaaS** — direct SaaS discussions
2. **r/Entrepreneur** — business pain points
3. **r/SideProject** — indie maker needs
4. **r/webdev** — developer tool gaps
5. **r/smallbusiness** — SMB software needs

### Hacker News
Scan Ask HN posts:


---

## Search Patterns

Match posts containing these phrases (case-insensitive):
- "I wish there was"
- "why isn't there"
- "would pay for"
- "someone should build"
- "looking for a tool"
- "need a simple"
- "frustrated with"
- "paying too much for"
- "is there a tool"
- "any tool that"
- "alternative to"

---

## Scoring Rubric (0-100)

Use the scoring script for initial heuristics, then apply your judgment:


### Buildable in <1 Week? (0-20 points)
- 18-20: Single CRUD app, standard auth, one API integration max
- 10-17: Two features, maybe one complex integration
- 0-9: Needs ML, real-time, or multiple complex systems

### Clear Single Use Case? (0-20 points)
- 18-20: "Convert X to Y" or "Track X" — one sentence describes it
- 10-17: Two related features, slightly broader scope
- 0-9: Vague, platform-like, or multi-feature

### Existing Solutions Suck? (0-15 points)
- 12-15: People explicitly complain about current tools being bloated/expensive
- 6-11: Some alternatives exist but have gaps
- 0-5: Good solutions already exist

### People Actively Complaining? (0-15 points)
- 12-15: Post has 10+ upvotes AND 5+ comments agreeing
- 6-11: Some engagement (3-10 upvotes, few comments)
- 0-5: Low engagement or single person asking

### Monetizable at -50/mo? (0-15 points)
- 12-15: Business users, clear time savings, recurring need
- 6-11: Could charge but value prop is moderate
- 0-5: Likely free-tier only or one-time use

### No Major Competitor Moat? (0-15 points)
- 12-15: No dominant player, easy to differentiate
- 6-11: Competitors exist but are overpriced or over-featured
- 0-5: Big Tech or well-funded startup owns the space

---

## Deduplication

Before reporting, read  and skip if:
- Same URL already exists
- Title is >80% similar to an existing entry (fuzzy match)

---

## Telegram Report Format (for ideas >70)

Send this exact format:



---

## Weekly Summary Format (Sundays)



---

## Data Persistence

After each scan, update :


---

## Error Handling

- If a Reddit request returns 429: wait 60s, retry once, then skip that subreddit
- If HN API fails: log error, continue with Reddit results only
- If JSON file is corrupted: create a backup, start fresh
- Always report at least a "no new ideas found" message so the user knows the scan ran
