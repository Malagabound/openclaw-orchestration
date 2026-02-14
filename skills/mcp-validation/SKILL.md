---
name: mcp-validation
description: Validate MCP server opportunities for developer markets. Different from SaaS validation — focuses on developer pain points, technical feasibility, and the "what can AI do with this that's hard otherwise" test.
---

# MCP Server Validation

MCP-specific validation criteria, extending the core product-research workflow.

**Workflow:** See `skills/product-research/SKILL.md` for:
- Phase 1-2 ownership (George autonomous)
- Template locations (Phase 1 and Phase 2 Google Docs)
- Rejection tracking (Product Prospector database)
- Handoff to Alan (only for GO decisions)

**This skill adds MCP-specific questions** to apply before and during Phase 2 validation.

## The Core Questions

Before ANY validation work, answer these THREE questions:

### 1. Is MCP the right delivery mechanism?
> "Are target developers actually building AI agents that would use MCPs?"

If they're building traditional apps with UIs → MCP is wrong. They want an API or SDK.
If they're building AI-powered tools/agents → MCP makes sense.

**How to validate:**
- Search GitHub for AI agent projects in the vertical
- Check if target developers discuss Claude/GPT/Cursor in their communities
- Look for "AI-powered" products in the space

### 2. What's hard that this makes easy?
> "What can a developer's AI agent do with this MCP that it couldn't easily do otherwise?"

If the answer is "just call an existing API" → STOP. Don't validate.

### 3. Do the economics work?
> "What's the underlying data cost, and can we price profitably?"

MCP price points are typically $20-80/mo. If underlying data costs $50/mo, margins don't work.

**Calculate:**
- Underlying service costs (APIs, data feeds)
- Infrastructure costs (hosting, bandwidth)
- Target price point
- Gross margin (must be >50% for sustainability)

## MCP Value Criteria

### ✅ Worth Validating

| Criteria | Example |
|----------|---------|
| **Aggregates hard-to-access sources** | 5+ county property tax DBs → one API |
| **Embeds vertical business logic** | MLS data + cap rate + NOI + investment score |
| **Proprietary/scarce data** | Data that requires scraping or special access |
| **Multi-step workflow** | Pull data → analyze → format → return insight |
| **Known developer pain point** | "I spent 3 weeks integrating X" complaints |

### ❌ Don't Bother

| Criteria | Example |
|----------|---------|
| Thin API wrapper | "QuickBooks MCP" that just calls QB API |
| Easily available data | Weather, stock prices, public APIs |
| No unique logic | Just CRUD operations |
| No clear developer pain | Solution looking for problem |

## Phase 0: Is MCP the Right Delivery Mechanism?

**This comes BEFORE pain point validation.** If developers aren't building AI agents, MCP is the wrong product.

### Evidence That Developers Are Building AI Agents

| Evidence Type | Where to Find | Strong Signal |
|---------------|---------------|---------------|
| AI agent repos | GitHub search "[vertical] AI agent" | Active repos with stars |
| MCP discussions | r/mcp, dev Discords | Vertical-specific questions |
| AI tool mentions | Vertical subreddits/forums | "Using Claude/GPT for X" |
| PropTech/vertical AI startups | Crunchbase, Y Combinator | Funded companies in space |
| Job postings | LinkedIn, Indeed | "AI agent developer" + vertical |

### Red Flags (MCP May Be Wrong)

- No AI agent repos in the vertical
- Target developers don't discuss AI tools
- Existing solutions are all traditional web apps
- No MCP-related questions in vertical communities

### Validation Checklist

```markdown
## Is MCP Right for This Vertical?

- [ ] Found active AI agent projects in this vertical (links)
- [ ] Developers discuss AI tools in community forums (links)
- [ ] Existing AI-powered products exist (competitors)
- [ ] MCP questions/discussions in vertical (links)

**Verdict:** MCP is appropriate / MCP is wrong / Unclear - need more research
```

---

## Phase 1: Developer Pain Point Validation

**Different from consumer validation.** Developers won't fill out surveys. They complain in public.

### Where to Find Developer Pain Points

| Source | What to Look For |
|--------|------------------|
| **GitHub Issues** | "Why is this so hard?" / feature requests |
| **Stack Overflow** | Questions with many upvotes, no good answers |
| **Hacker News** | "Ask HN" threads, launch complaints |
| **Reddit** | r/programming, r/webdev, r/SaaS frustrations |
| **Twitter/X** | "[service] API sucks" / integration complaints |
| **Dev Discord/Slack** | Real-time pain point discussions |

### Pain Point Evidence Template

```markdown
## Pain Point: [Description]

### Evidence
- [ ] Stack Overflow questions (link, upvotes)
- [ ] GitHub issues (link, reactions)
- [ ] Reddit/HN threads (link, engagement)
- [ ] Twitter complaints (links)
- [ ] Personal experience / known pain

### Severity Assessment
- How much time does this pain cost developers?
- How often do developers encounter this?
- Are there workarounds? How painful are they?
```

## Phase 2: Technical Feasibility

### Data Access Assessment

| Question | Answer Required |
|----------|-----------------|
| Where does the underlying data come from? | API / Scraping / Aggregator |
| Do we need special agreements? | MLS contracts, enterprise APIs, etc. |
| Can we wrap an existing service? | SimplyRETS, RapidAPI, etc. |
| What's the data freshness requirement? | Real-time / hourly / daily |
| Rate limits or quotas? | May affect pricing model |

### Build Complexity

| Level | Time | Characteristics |
|-------|------|-----------------|
| **Easy** | 1-2 weeks | Single data source, simple logic |
| **Medium** | 2-4 weeks | Multiple sources OR complex logic |
| **Hard** | 4-8 weeks | Multiple sources AND complex logic AND auth |

### The "Wrap vs Build" Decision

**Prefer wrapping existing services when possible:**

| Wrap Existing Service | Build from Scratch |
|----------------------|-------------------|
| Faster to market | Full control |
| Lower maintenance | Higher margins |
| Proven data quality | Unique differentiator |
| Less liability | Competitive moat |

**Example:** MLS data
- ❌ Don't build MLS integrations (requires contracts with 900+ MLSs)
- ✅ Wrap SimplyRETS/Realtyna + add analysis logic

## Phase 3: Market Validation

### Developer Willingness to Pay

| Signal | Strength |
|--------|----------|
| Existing paid solutions exist | Strong — market is proven |
| Developers say "I'd pay for this" | Medium — talk is cheap |
| Developers currently pay for workarounds | Strong — proven demand |
| Open source alternatives exist | Weak — price sensitivity |

### Pricing Research

**MCP typical price points:**
- Free tier: 5-20 requests/day
- Basic: $15-30/mo
- Pro: $40-80/mo
- Business: $100-200/mo

**Check competitors:**
- What do similar APIs charge?
- What's the cost of the developer's time to build this themselves?

### Cost & Margin Analysis (CRITICAL)

**You MUST calculate this before proceeding:**

```markdown
## Cost Analysis

### Underlying Data Costs
| Service | Cost | Usage Model |
|---------|------|-------------|
| [Data source 1] | $X/mo or $X/call | |
| [Data source 2] | $X/mo or $X/call | |
| [Infrastructure] | $X/mo | |

### Per-Customer Cost Estimate
- Avg calls/customer/month: X
- Data cost per call: $X
- Monthly data cost per customer: $X

### Pricing & Margin
- Target price: $X/mo
- Cost per customer: $X/mo
- Gross margin: X%

### Margin Thresholds
- >70% margin: Excellent
- 50-70% margin: Good
- 30-50% margin: Risky (scaling problems)
- <30% margin: DON'T BUILD
```

**Common MCP cost traps:**
- Underlying APIs with per-call pricing eat margins at scale
- Data providers with minimum monthly fees hurt low-volume months
- Enterprise APIs often require annual commitments

### Developer Persona

Who exactly would use this?

| Persona | Characteristics | Price Sensitivity |
|---------|-----------------|-------------------|
| Indie hacker | Solo, budget-conscious | High — wants free/cheap |
| Startup dev | Small team, moving fast | Medium — values time > money |
| Agency dev | Client work, expense it | Low — bills to client |
| Enterprise | Procurement process | Low — but slow sales cycle |

**Best target for MCP:** Startup devs and agency devs.

## Phase 4: Competitive Analysis

### Existing MCP Servers

Check these registries:
- [ ] [Smithery](https://smithery.ai)
- [ ] [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)
- [ ] [mcpmarket.com](https://mcpmarket.com)
- [ ] [glama.ai/mcp](https://glama.ai/mcp)
- [ ] [Composio](https://composio.dev)

### If Competitors Exist

| Situation | Action |
|-----------|--------|
| No competitors | Validate demand exists first |
| 1-2 competitors | Good — market proven, room to differentiate |
| 3+ competitors | Need strong differentiation |
| Enterprise player | Avoid unless targeting different segment |

### Differentiation Options

- **Vertical focus** — generic QB vs QB for RE investors
- **Better DX** — cleaner API, better docs
- **Bundled logic** — data + analysis in one call
- **Price** — undercut if you can (careful with margins)
- **Speed** — faster response times

## Validation Scorecard

| Checkpoint | Weight | Score (1-5) |
|------------|--------|-------------|
| **MCP is right delivery mechanism** | 15% | |
| Developer pain point evidence | 20% | |
| "Hard to do otherwise" test passes | 15% | |
| Technical feasibility | 10% | |
| Willingness to pay signals | 15% | |
| **Cost/margin analysis (>50% margin)** | 15% | |
| Competitive positioning | 10% | |
| **TOTAL** | 100% | /5.0 |

**Thresholds:**
- ≥ 4.0: Strong GO
- 3.5-3.9: Conditional GO (address weak areas)
- 3.0-3.4: More research needed
- < 3.0: NO-GO

## Output: MCP Validation Report

```markdown
# MCP Validation: [Name]

## The Pitch (1 sentence)
[What it does and why developers need it]

## The Core Value Test
> What can a developer's AI agent do with this that's hard otherwise?
[Answer]

## Pain Point Evidence
[Links and quotes from developer complaints]

## Technical Approach
- Data source(s):
- Wrap vs build:
- Complexity: Easy/Medium/Hard
- Time to MVP:

## Market Signals
- Existing solutions:
- Pricing benchmarks:
- Target persona:

## Competitive Position
[How we differentiate]

## Validation Score: X.X/5.0
[Breakdown by checkpoint]

## Recommendation: GO / NO-GO / NEEDS MORE RESEARCH
[Reasoning]
```

---

*Created: 2026-02-05*
