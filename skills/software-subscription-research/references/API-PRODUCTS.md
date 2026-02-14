# API Products & Developer Tools Research

Methodology for discovering and validating API-as-a-service, marketplace actors, and developer tool opportunities.

---

## Why This Category?

**Traditional micro-SaaS:** User-facing app → marketing to end users → high competition
**API products:** Developer-facing service → developers find you → often less crowded

**Advantages:**
- Lower marketing cost (developers search for solutions)
- Platform distribution (Apify, RapidAPI handle discovery)
- Specific technical problems = willingness to pay
- Recurring usage-based revenue
- Less design/UX burden (it's an API)

---

## Product Types in This Category

| Type | Example | Revenue Model |
|------|---------|---------------|
| **API service** | Data enrichment, geocoding, NLP | Per-call or subscription |
| **Apify actors** | Web scrapers, automation tools | Pay-per-result via Apify |
| **Platform plugins** | Shopify apps, WordPress plugins | Monthly subscription |
| **Developer tools** | SDKs, CLI tools, libraries | Freemium + paid tiers |
| **Data feeds** | Market data, lead lists, enrichment | Subscription access |
| **Infrastructure** | Logging, monitoring, queues | Usage-based |

---

## Discovery Sources

### 1. Apify Store

**URL:** apify.com/store  
**Why:** See what scrapers/actors exist, what's missing, what's popular

#### Research Method

1. **Browse by category**
   - Note top actors by usage (user count visible)
   - Identify gaps: "Why isn't there an actor for X?"

2. **Check actor quality**
   - Low ratings + high demand = opportunity to build better
   - Old/unmaintained actors = opportunity to replace

3. **Read actor issues/requests**
   - Each actor has an Issues tab
   - Feature requests = unmet demand

4. **Analyze pricing**
   - Most charge per result ($0.001 - $0.05)
   - High-value data can charge more

5. **Identify underserved niches**
   - Search for "[industry] scraper" — does it exist?
   - If manual research is painful, an actor would help

#### Validation Signals
| Signal | Good | Great |
|--------|------|-------|
| Actor users | 100+ | 1,000+ |
| Monthly active | 10+ | 100+ |
| Reviews | Any positive | 4.5+ rating |
| Requests in Issues | People asking for features | Repeated same request |

---

### 2. RapidAPI

**URL:** rapidapi.com  
**Why:** Largest API marketplace — see what developers actually pay for

#### Research Method

1. **Browse categories**
   ```
   rapidapi.com/categories
   ```
   - Data, Finance, AI/ML, Location, Sports, etc.

2. **Sort by popularity**
   - "Most Popular" shows proven demand
   - Note APIs with 1M+ calls

3. **Check pricing models**
   - Free tier + paid = standard
   - Note price per call for paid tiers

4. **Read reviews/discussions**
   - What's missing from popular APIs?
   - What complaints exist?

5. **Find gaps**
   - Search for specific data needs
   - "No results" = potential opportunity

#### Validation Signals
| Signal | Threshold |
|--------|-----------|
| API popularity rank | Top 100 in category |
| Endpoints | Serving real needs (not toy APIs) |
| Pricing | $0.001+ per call (people pay) |
| Reviews | Active discussion |

---

### 3. AWS / Azure / GCP Marketplaces

**URLs:**
- aws.amazon.com/marketplace
- azuremarketplace.microsoft.com
- cloud.google.com/marketplace

**Why:** Enterprise-grade APIs with serious budgets

#### Research Method

1. **Browse SaaS/API categories**
2. **Note pricing (often $100s-$1000s/month)**
3. **Identify SMB gaps**
   - Enterprise-priced API doing simple thing?
   - Could we offer SMB version at $29/month?

4. **Check reviews for complaints**

---

### 4. Product Hunt (APIs Category)

**URL:** producthunt.com/topics/apis  
**Apify Actor:** `michael.g/product-hunt-scraper`

#### Research Method

1. **Filter to API/developer tools**
2. **Look for high upvotes + launch patterns**
3. **Read comments for "I wish it did X"**
4. **Check if tools are still active**

---

### 5. Developer Community Mining

#### GitHub
**What to search:**
```
github.com/topics/[niche]
github.com/search?q=[niche]+api
```

**Signals:**
- Repos with many stars but no hosted service = opportunity
- "Awesome-[topic]" lists show what tools exist
- Issues requesting features = unmet needs

#### Stack Overflow
**What to search:**
```
site:stackoverflow.com "[niche] api" OR "[niche] service"
```

**Look for:**
- Questions with no good answers
- Deprecated tools being asked about
- "Is there a service that does X?"

#### Hacker News
**Search:** hn.algolia.com
```
"Ask HN: API for [niche]"
"looking for [niche] service"
```

#### Dev.to / Hashnode
- Developer blogs often mention tool gaps
- Search for "[niche] tools I use"

---

### 6. Existing Platform Analysis

#### Platforms with Plugin/App Ecosystems

| Platform | Marketplace | Opportunity Type |
|----------|-------------|------------------|
| Shopify | apps.shopify.com | E-commerce tools |
| WordPress | wordpress.org/plugins | Site tools |
| Zapier | zapier.com/apps | Integration |
| Slack | slack.com/apps | Team tools |
| Notion | notion.so/integrations | Productivity |
| Airtable | airtable.com/marketplace | Data tools |
| Chrome | chrome.google.com/webstore | Browser extensions |
| VS Code | marketplace.visualstudio.com | Dev tools |

#### Research Method

1. **Browse marketplace for niche category**
2. **Sort by installs/reviews**
3. **Find gaps:**
   - Highly-rated but abandoned plugins
   - Feature requests in reviews
   - Categories with few options

4. **Analyze pricing:**
   - What do top apps charge?
   - Is there room for mid-tier?

---

## Validation Thresholds (API Products)

Different from traditional SaaS:

| Signal | Minimum | What It Proves |
|--------|---------|----------------|
| **Similar APIs exist** | ≥1 paid API in space | Developers pay for this |
| **Usage on existing** | ≥1,000 calls/month | Real demand |
| **Developer discussion** | ≥5 threads on topic | Pain exists |
| **No dominant player** | No API with >80% market | Room for us |
| **Build feasibility** | Can we access/generate this data? | We can actually deliver |

---

## API-Specific Considerations

### Revenue Models

| Model | Best For | Example |
|-------|----------|---------|
| **Per-call** | Variable usage, low per-request value | $0.001/call |
| **Tiered subscription** | Predictable usage | $29/mo for 10k calls |
| **Freemium** | Land & expand | 1k free, then paid |
| **Pay-per-result** | Scrapers, enrichment | $0.01/successful result |

**Recommendation:** Tiered subscription for predictable MRR, but offer pay-as-you-go for flexibility.

### Technical Moat

Unlike SaaS where UX is the moat, API products need:
- **Data access** — Can you get data others can't?
- **Speed/reliability** — Is yours faster/more stable?
- **Accuracy** — Is your output higher quality?
- **Documentation** — Is it easier to integrate?
- **Support** — Do you actually help developers?

### Platform Dependency Risk

| Platform | Risk Level | Why |
|----------|------------|-----|
| Apify | Medium | They take 20-30% but handle distribution |
| RapidAPI | Medium | Same — rev share but discoverability |
| Shopify | High | Can change rules anytime |
| Direct API | Low | You own everything |

**Strategy:** Start on platform for distribution, build direct customers over time.

---

## Research Flow for API Products

### Phase 1: Opportunity Scan (1 hour)
1. [ ] Browse Apify Store for niche — anything similar?
2. [ ] Search RapidAPI — paid APIs in this space?
3. [ ] Search GitHub — OSS tools that could be hosted?
4. [ ] Search Stack Overflow — developers asking for this?

### Phase 2: Validation (2-3 hours)
5. [ ] Analyze top 3 existing APIs/actors
6. [ ] Document pricing models
7. [ ] Read reviews/issues for gaps
8. [ ] Assess technical feasibility
9. [ ] Estimate build time

### Phase 3: Proposal
10. [ ] Fill out competitor template
11. [ ] Define differentiation
12. [ ] Score against rubric (same universal rubric)
13. [ ] If ≥24 → propose to Alan

---

## Output Requirements

Same as traditional SaaS, plus:
- Platform strategy (Apify vs RapidAPI vs direct)
- Technical feasibility assessment
- Data source identification
- Revenue model recommendation
