# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## Product Prospector (Opportunity Tracking)

**URL:** https://product-prospector.netlify.app
**Repo:** github.com/Malagabound/product-prospector
**Database:** Supabase (gtkehmsgiofaexftirgu.supabase.co)
**Credentials:** `~/.openclaw/credentials/supabase` (service key, DB password, pooler URL)

**This is where ALL product research goes.** When I find opportunities:
1. INSERT into `opportunity` table with scores
2. Log research sessions in `research_run` table
3. Track explored niches in `niche_explored` table

**Tables:**
- `opportunity` — Product ideas with scores (demand, competition, monetization, buildability, scalability, passion_fit)
- `niche_explored` — Record of all niches researched
- `research_run` — Log of scan sessions

**Status flow:** discovered → researching → validated → building → launched (or rejected)

**Scoring:** 6 criteria, each 1-5. Total /30. Threshold ≥20 for validation.

**API Access:**
```bash
curl "https://gtkehmsgiofaexftirgu.supabase.co/rest/v1/opportunity" \
  -H "apikey: $(cat ~/.openclaw/credentials/supabase | grep SERVICE_KEY | cut -d= -f2)" \
  -H "Authorization: Bearer $(cat ~/.openclaw/credentials/supabase | grep SERVICE_KEY | cut -d= -f2)"
```

## Task Tracking (Taskr)

**Dashboard:** https://taskr.one
**Project ID:** PR00000000MLA5HCQYMHXMGFBKI3
**Status:** Active — replaced George HQ Kanban (retired 2026-02-05)

**Task Lists:**
- Recurring Tasks — periodic checks (email, trends, follow-ups)
- Investment Opportunities — business acquisition research
- Rental & Realtor Business — QB, utilities, property management
- Awaiting Alan Decision — items needing his input

**Workflow:**
- Create tasks with `create_task` via mcporter
- Update status with `update_task` (open → wip → done)
- Alan can monitor progress in real-time from web/mobile

**Rule IDs for API calls:**
- `RU-SIMP-001` — for create_task
- `RU-PROC-001` — for update_task, get_task

## George HQ (RETIRED)

**URL:** https://george-hq.netlify.app
**Status:** Retired 2026-02-05, replaced by Taskr
**Repo:** https://github.com/Malagabound/george-hq

## Git Workflow

**Branches:**
- `dev` — George works here
- `prod` — Production, Alan controls

**Rules:**
- I push to `dev` only
- I create PRs for Alan to review
- I do NOT push to `prod` or merge to `prod`
- Alan reviews, tests, and decides when to deploy

## New Project Setup (Standard)

Every new app follows this setup:

1. **Create branches:**
   - `dev` branch (my working branch)
   - `prod` branch (production, auto-deploys)
   - Delete `main` branch
   - Set `prod` as default branch on GitHub

2. **Netlify setup:**
   - Create Netlify site linked to the repo
   - Create deploy key on Netlify, add to GitHub repo
   - Configure build settings with `prod` branch
   - Create build hook for `prod` branch

3. **GitHub webhook:**
   - Create webhook pointing to Netlify build hook
   - Trigger on `push` events
   - Result: pushes to `prod` auto-deploy to Netlify

**This is standard for ALL projects. Don't ask — just do it.**

## Validation Rule

**ALWAYS browser test before presenting anything to Alan.** 
- Run the dev server
- Open in browser
- Verify no errors
- Check it looks right
- THEN tell Alan it's ready

Alan should never see an error. If I can't validate it, it's not ready.

## GoHighLevel (The Autopilot AI)

**URL:** app.theautopilotai.com
**Login:** george@originutah.com
**Password:** G30rge!
**Purpose:** Handle support tickets for Alan's realtor SaaS clients
**Note:** Learn the platform, become proficient, handle incoming support

## QuickBooks Workflow

**Daily task:** Check for uncategorized transactions, assign classes (properties)
**When Alan forwards:** Utility bills → update spreadsheet + QB | PM income emails → update spreadsheet + QB
**Categorization rules:** See `memory/qb-categorization-rules.md` (build over time)
**If unsure:** Ask Alan once, then remember the answer forever

## Email Accounts (via Maton API)

| Email | Connection ID | Purpose |
|-------|---------------|---------|
| george@originutah.com | 26429363-7040-4bdc-b7b2-26a040d06a96 | George's inbox - forwarded tasks, research delivery |
| alan@originutah.com | 84a9a500-ccea-4a27-9bd8-38cb811904ad | Alan's main - utilities, newsletters, Jotform |
| alan@roccoriley.com | 5fbd0b9d-1f06-4b12-a791-657279ae14b2 | Alan's business - Optimize OS, Venmo |

**Priority:** Process george@ same-day. Monitor alan@ inboxes for actionable items.

### alan@originutah.com Rules

| Sender/Pattern | Action |
|----------------|--------|
| Jotform + "Pinnacle Chiropractic" | DELETE immediately |
| Make + "Encountered error in 3 Add to Custom Response Report" | ARCHIVE immediately (remove from inbox) |
| xpressbillpay / utility bills | Process → update spreadsheet → move to **WinHaw Rentals** folder |
| Dominion Energy / Enbridge Gas | Process → update spreadsheet → move to **WinHaw Rentals** folder |
| WordPress (any) | ARCHIVE immediately |
| Left Main Academy | ARCHIVE immediately |
| Mercury — transaction declined | ARCHIVE immediately |
| Mercury — card charged | ARCHIVE immediately |
| Optimize OS — error alerts | ARCHIVE immediately |

**WinHaw Rentals folder ID:** `Label_106`

**Utility processing workflow:**
1. Check alan@originutah.com for utility emails
2. Extract bill amount, property, due date
3. Update rental spreadsheet (property tab, correct month column)
4. Move email to WinHaw Rentals folder (remove from INBOX)
5. Mark as read

## Google Account (george@originutah.com)

**Credentials:** `~/.openclaw/credentials/google-george`
**Access:** Gmail, Drive, Sheets, Docs
**Purpose:** Receive forwarded emails from Alan, store research/deliverables

### Google Drive - My Folder
**Folder Name:** #George
**Folder ID:** `1zy6N6oDw5oY2VhEimYFmozIl6UsLvFUs`
**URL:** https://drive.google.com/drive/folders/1zy6N6oDw5oY2VhEimYFmozIl6UsLvFUs

**Subfolder Structure:**
| Subfolder | Purpose | Folder ID |
|-----------|---------|-----------|
| Research | Market research, API analysis, competitive analysis | `1dCe2iBrrp7CCD43yuuJ32E-t6zVGcZbn` |
| Digital Products | Product ideas, validation docs | `1EBmMS54K-O3JfSOjErWumOUMqph8SJWn` |
| Software Subscriptions | SaaS/MCP research, pricing analysis | `1JEmLPmL5EzkA-2ZNgetSgfD9lJJkAl8I` |
| Rental Business | QB reports, property docs | `1lqzxgfPpMlDHJhpyTLUed3pKL9-tqm-_` |

**Usage:** All deliverables for Alan go here. Always share the Google Doc link, never local file paths.

**⚠️ THIS IS MY EMAIL — LOG IN VIA BROWSER, NOT ZAPIER MCP**

### Creating Google Docs (via Maton API)

```bash
MATON_KEY="$(cat ~/.openclaw/credentials/maton | cut -d= -f2)"

# 1. Create doc
curl -X POST "https://gateway.maton.ai/google-docs/v1/documents" \
  -H "Authorization: Bearer $MATON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title": "Doc Title"}'

# 2. Add content (use documentId from step 1)
curl -X POST "https://gateway.maton.ai/google-docs/v1/documents/{docId}:batchUpdate" \
  -H "Authorization: Bearer $MATON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"requests": [{"insertText": {"location": {"index": 1}, "text": "Content here"}}]}'

# 3. Move to folder
curl -X PATCH "https://gateway.maton.ai/google-drive/drive/v3/files/{docId}?addParents={folderId}&removeParents=root" \
  -H "Authorization: Bearer $MATON_KEY"
```

**Result:** Share link like `https://docs.google.com/document/d/{docId}/edit`

**IMPORTANT:** After creating any doc via Maton, always share it with george@originutah.com:
```bash
curl -X POST "https://gateway.maton.ai/google-drive/drive/v3/files/{docId}/permissions" \
  -H "Authorization: Bearer $MATON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"role": "writer", "type": "user", "emailAddress": "george@originutah.com"}'
```

**⚠️ THIS IS MY EMAIL — LOG IN VIA BROWSER, NOT ZAPIER MCP**

### Key Templates
| Template | Purpose | URL |
|----------|---------|-----|
| Phase 1 Discovery | Initial discovery report, scoring, proceed/pass decision | https://docs.google.com/document/d/17Gk2zWrRmKoonJ-RtSyhgxwwJwC1yW6TbYjSuQRLqG8/edit |
| Phase 2 Validation | Deep validation report for products scoring ≥20/30 | https://docs.google.com/document/d/1jXUeUi4i718oKTzB9gHolBDP0IrFCIt8paDnQgMoqes/edit |

**⚠️ THIS IS MY EMAIL — LOG IN VIA BROWSER, NOT ZAPIER MCP**

**Periodic checks:** During heartbeats, check inbox for:
- Forwarded utility bills → process with rental-utility-processor skill
- Property management emails → process with rental-income-processor skill

## Apify (Web Scraping)

**Console:** https://console.apify.com
**API Token:** `~/.openclaw/credentials/apify-token`
**Plan:** Free tier ($5/month credits)

### Digital Product Research Actors
| Actor | Purpose | Cost |
|-------|---------|------|
| `muhammetakkurtt/gumroad-scraper` | Gumroad product data | ~$0.002/product |
| `epctex/etsy-scraper` | Etsy digital products | ~$0.01/result |

### SaaS Research Actors
| Actor | Purpose | Cost |
|-------|---------|------|
| `vivid_astronaut/g2-capterra-scraper` | G2 + Capterra reviews/products | $0.01/result |
| `michael.g/product-hunt-scraper` | Product Hunt launches + team data | ~$0.005/product |
| `jupri/indiehackers` | Indie Hackers products + revenue data | Pay per usage |

**Usage:** Bulk marketplace data extraction for product research.
**Methodology:** See `skills/software-subscription-research/references/SAAS-SOURCES.md`

## Digital Product Validation Tools

### Gumroad Research
| Tool | Purpose | Cost |
|------|---------|------|
| **Gumroad Discover** | Browse top-selling products | Free |
| **GumTrends** | 250k+ products database, revenue estimates, mixed review analysis | $49 one-time |
| **Marketsy.ai Gumroad Trends** | Trending product tracking | Free |

### Etsy Research
| Tool | Purpose | Cost |
|------|---------|------|
| **eRank** | Keyword research, trend tracking, competition | Free-$9.99/mo |
| **EverBee** | Revenue estimates, competitor tracking | $29/mo |
| **Marmalead** | Search volume, engagement scores | $19/mo |
| **Alura** | Product research, listing optimization | $19/mo |

### Demand Signals
| Tool | Purpose | Cost |
|------|---------|------|
| **Google Trends** | Search interest over time | Free |
| **Pinterest Trends** | Printable/template demand | Free |
| **AnswerThePublic** | Questions people ask | Free-$99/mo |

**Methodology:** See `skills/digital-product-research/references/VALIDATION-METHODS.md`

---

## Sequence (Financial Router)

**URL:** https://app.getsequence.io
**API:** https://api.getsequence.io
**Credentials:** `~/.openclaw/credentials/sequence`

**What it does:** Alan's financial automation platform - routes money between accounts, handles rent collection, automates transfers.

**Connected Accounts:**
- WINHAW CHECKING (Winridge Hawthorne Checking) - rental property
- WINHAW SAVINGS (Winridge Hawthorne Savings) - rental property
- Personal accounts, income sources, pods

**API Capabilities:**
- ✅ `/accounts` - Get all accounts + balances
- ❌ Transaction history (not exposed, need Remote API)

**Usage:**
```bash
curl -s 'https://api.getsequence.io/accounts' \
  -H 'x-sequence-access-token: Bearer $(cat ~/.openclaw/credentials/sequence | grep API_KEY | cut -d= -f2)' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

## MCP Servers

### Zapier (zapier)
- **URL:** https://mcp.zapier.com/api/v1/connect
- **Current integrations:**
  - Gmail (create drafts)
- **Add more:** `mcporter call zapier.add_tools()`

## GitHub Accounts

**Personal/Passive Income (default):**
- Account: Malagabound
- Auth: PAT stored in `~/.openclaw/credentials/github-personal`
- Projects: product-prospector, second-brain, george-hq, etc.

**Nth Degree CPAs (work):**
- Account: nthdegreecpas
- Auth: PAT stored in `~/.openclaw/credentials/nth-degree-github`
- Use for: Alan's day job SaaS work (seekingcertainty)

### Optimize OS
- **Repo:** `nthdegreecpas/seekingcertainty`
- **What it is:** Alan's SaaS project at Nth Degree CPAs
- **Note:** "Optimize OS" = "seekingcertainty" — same thing

## Rental Property Tracking (Alan's Properties)

**Spreadsheet:** `11HXbgyvNV2GRsslRxeA9kyxx91Vhv1Lx7LY_8siR0xQ`
**Access:** Via Zapier MCP (alan@originutah.com connection)

**Properties (each has its own tab):**
- Clinton
- 287 N Center
- 217 Reed Ave
- 521-523 N 600 W
- 150 E Garden Ave
- 4936 S La Brea
- 7085 W Cimmarron
- 948 22nd St

**Summary tabs:** Net, Lease, Mortgages, Cash on Cash

**Workflow:**
1. Alan forwards utility bills → I update utility cells for that property/month
2. Alan forwards property management emails → I update rent/income for that property/month
3. QuickBooks transactions → Assign to correct property using class function

## Hard-Won Lessons

### 2026-02-03: Google Docs Disaster
**Mistake:** Used `append_text_to_document` without specifying a target doc. It grabbed a random customer document and I sent the link to Alan without checking it first.

**Rule:** ALWAYS verify outputs before sharing. Open the link yourself. Check it looks right. Then send it.

**Rule:** Test unfamiliar tools on dummy data first, not real deliverables.

---

## Browser Access

**Use `profile="openclaw"`** for browser operations — this is the managed browser that requires no extension.

**DO NOT use `profile="chrome"`** — that requires manually clicking the Chrome extension on a tab.

```bash
openclaw browser --browser-profile openclaw status
```

Config set: `browser.defaultProfile: "openclaw"`

---

## ClawHub (Skill Marketplace)

**URL:** https://clawhub.ai
**CLI:** `clawhub` (installed globally)

**Search for skills:**
```bash
clawhub search "query"
```

**Install a skill:**
```bash
clawhub install <slug>
```

**List installed skills:**
```bash
clawhub list
```

**Installed skills (as of 2026-02-05):**
security-sentinel, quickbooks, gmail, deep-research, firecrawl-search, gumroad-admin, twitter, supabase, postgres, calendar, obsidian, self-improving-agent, reflect-learn, tavily-search, youtube-transcript

---

## Research Delivery Process

When completing research tasks:

1. **Create Google Doc** via Zapier MCP with full findings
2. **Send Telegram summary:**
   - TL;DR (2-3 sentences)
   - Key findings (bullets)
   - My recommendation
   - Link to full doc
3. **Move Kanban task** to Review (not Done yet)
4. **Wait for Alan's feedback** before moving to Done

**Research Doc Structure:**
- Executive Summary
- Key Findings
- Options (with pros/cons if applicable)
- Recommendation + Reasoning
- Sources/References

## Tavily Search (AI-Optimized Web Search)

**API Key:** `~/.openclaw/credentials/tavily`
**Skill:** `tavily-search`
**Status:** ✅ Active (configured 2026-02-09)

**Usage:**
```bash
node skills/tavily-search/scripts/search.mjs "query"
node skills/tavily-search/scripts/search.mjs "query" -n 10
node skills/tavily-search/scripts/search.mjs "query" --deep
node skills/tavily-search/scripts/search.mjs "query" --topic news
```

**Purpose:** AI-optimized web search that returns clean, relevant content specifically designed for AI agents. Better than traditional search for research tasks.

**Configuration:** Added to OpenClaw gateway config under `skills.entries.tavily-search` with `TAVILY_API_KEY` environment variable.

## Firecrawl (Advanced Web Scraping)

**API Key:** `~/.openclaw/credentials/firecrawl`
**Skill:** `firecrawl-search`
**Status:** ✅ Active (configured 2026-02-09)

**Usage:**
```bash
# Web search via Firecrawl
python3 skills/firecrawl-search/scripts/search.py "query"

# Scrape specific URLs (handles JS-heavy sites)
python3 skills/firecrawl-search/scripts/scrape.py "https://example.com"

# Crawl entire websites
python3 skills/firecrawl-search/scripts/crawl.py "https://example.com"
```

**Purpose:** Advanced web scraping and crawling service. Handles JavaScript-heavy pages, dynamic content, and rate limiting. Ideal for competitor analysis and deep data extraction.

**Configuration:** Added to OpenClaw gateway config under `skills.entries.firecrawl-search` with `FIRECRAWL_API_KEY` environment variable.

---

Add whatever helps you do your job. This is your cheat sheet.
