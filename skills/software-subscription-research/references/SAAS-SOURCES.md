# SaaS Research Sources - Detailed Methodology

Comprehensive guide for validating software subscription opportunities. Follow this systematically — no guessing.

---

## ⚠️ CRITICAL: MICRO-NICHE SEARCH CRITERIA (Updated 2026-02-09)

**WE ARE NOT BUILDING ENTERPRISE SOFTWARE. WE ARE BUILDING NICHE COMMUNITY SOFTWARE.**

### ❌ NEVER Search For:
- Established industries (veterinarians, property management, accounting, etc.)
- Markets with existing software solutions (QuickBooks integrations, CRM competitors)  
- Professional services that Fortune 500 companies would target
- Anything requiring compliance/licensing (HIPAA, financial compliance, legal compliance)
- Broad industry terms ("healthcare software", "real estate tools")

### ✅ ALWAYS Search For:
- **Weird job titles + "software"** that return NO useful results
- **Mobile/truck-based businesses** with manual processes  
- **1-10 person operations** that big companies ignore
- **Reddit r/sweatystartup complaints** about lack of software
- **Excel hell industries** using spreadsheets for everything

### 🎯 The Niche Test (MANDATORY):
If Google "[weird job] software" returns 3+ established competitors → **STOP, TOO MAINSTREAM**

### Example Searches That Work:
```
"grave cleaner scheduling software" → nothing = opportunity
"septic pumper route optimization" → manual = opportunity  
"bee removal invoicing system" → Excel hell = opportunity
"lockbox installer software" → paper-based = opportunity
```

**Use the methodology below ONLY AFTER identifying a qualifying micro-niche.**

---

## Data Trust Hierarchy

Not all data is equal. When conflicting signals exist, trust in this order:

| Trust Level | Source Type | Example |
|-------------|-------------|---------|
| **1 (Highest)** | Verified financial data | Baremetrics Open Startups, Stripe dashboards |
| **2** | Platform-visible metrics | G2 review counts, Product Hunt upvotes |
| **3** | Self-reported (established founder) | Indie Hackers MRR from known founders |
| **4** | Self-reported (unknown founder) | Random Twitter claims |
| **5 (Lowest)** | Estimates/proxies | SimilarWeb traffic, employee count guesses |

**Rule:** Never cite Level 4-5 data as primary validation. Use it only to supplement Level 1-3.

---

## Validation Thresholds

These are the minimum signals required before presenting a niche to Alan:

| Signal | Minimum Threshold | What It Proves |
|--------|-------------------|----------------|
| **Existing competitors** | ≥3 active products | Market exists |
| **Review count (G2/Capterra)** | ≥50 reviews across top 3 | Buyers exist and care |
| **MRR evidence** | ≥1 competitor at $5k+ MRR | Revenue is real |
| **Search volume** | ≥500/month for core keyword | Demand exists |
| **Community discussion** | ≥10 relevant threads | Pain is felt |

If ANY threshold isn't met → the idea needs more research or should be passed.

---

## Source-by-Source Methodology

### 1. G2 (Primary B2B Validation)

**URL:** g2.com  
**Apify Actor:** `vivid_astronaut/g2-capterra-scraper`  
**Cost:** $0.01/result

#### What to Extract
- Product name, URL, category
- Total review count
- Average rating
- Pricing tier indicators
- "Alternatives" list
- Negative review themes

#### Step-by-Step Process

1. **Search the category**
   ```
   g2.com/categories/[category-slug]
   ```

2. **Filter and sort**
   - Sort by "Most Reviews" first (establishes market leaders)
   - Note total products in category (market size indicator)

3. **Identify top 5 competitors**
   - Record: Name, review count, rating, pricing page URL
   - Threshold: If #1 has <50 reviews → weak market signal

4. **Deep dive on top 3**
   - Read 10 most recent negative reviews each
   - Extract: Feature complaints, pricing complaints, UX complaints
   - These are your differentiation opportunities

5. **Run Apify scraper for bulk data**
   ```
   Actor: vivid_astronaut/g2-capterra-scraper
   Input: { "url": "https://g2.com/products/[product]/reviews" }
   ```

6. **Document in competitor template**

#### Validation Checkboxes
- [ ] ≥3 products with ≥20 reviews each
- [ ] At least 1 product with ≥100 reviews (market leader exists)
- [ ] Negative reviews reveal addressable gaps
- [ ] Pricing visible or inferable

---

### 2. Capterra (B2B Validation + Pricing Intel)

**URL:** capterra.com  
**Apify Actor:** `vivid_astronaut/g2-capterra-scraper` (same actor)

#### What to Extract
- Pricing (more visible than G2)
- Feature comparison grids
- "Best for" categorization
- User company size distribution

#### Step-by-Step Process

1. **Search category**
   ```
   capterra.com/[category]/software
   ```

2. **Use filters strategically**
   - Filter by "Free Trial" → these compete on product quality
   - Filter by company size → find SMB-focused tools

3. **Extract pricing data**
   - Capterra often shows actual prices
   - Note: Starting price, per-user pricing, enterprise tiers
   - Build pricing landscape table

4. **Cross-reference with G2**
   - Same products should appear
   - If product is big on G2 but missing from Capterra → may be enterprise-only

#### Validation Checkboxes
- [ ] Pricing data extracted for top 5 competitors
- [ ] SMB-tier options exist (not all enterprise)
- [ ] Price points align with Alan's target ($29-199/month)

---

### 3. Product Hunt (Traction + Launch Validation)

**URL:** producthunt.com  
**Apify Actor:** `michael.g/product-hunt-scraper`  
**Cost:** ~$0.005/product

#### What to Extract
- Product name, tagline, URL
- Upvote count
- Comment count
- Launch date
- Categories/topics
- Maker info + links

#### Step-by-Step Process

1. **Search for category keywords**
   ```
   producthunt.com/search?q=[keyword]
   ```

2. **Filter by time**
   - Last 12 months = still relevant
   - Last 3 months = hot/emerging

3. **Identify high-signal launches**
   - ≥200 upvotes = strong interest
   - ≥50 comments = engaged audience
   - Low upvotes + high comments = polarizing (investigate why)

4. **Read comments for gold**
   - Feature requests
   - "I wish it did X"
   - Pricing objections
   - Competitor mentions

5. **Check if product is still active**
   - Visit website
   - Check last update/blog post
   - Abandoned product + high interest = opportunity

6. **Run Apify for category sweep**
   ```
   Actor: michael.g/product-hunt-scraper
   Input: { "date": "2025-12-01", "scrapeFeatured": false }
   ```
   Run for multiple dates across the year to find patterns.

#### Validation Checkboxes
- [ ] ≥3 related products launched in last 12 months
- [ ] At least 1 with ≥200 upvotes
- [ ] Comments reveal unmet needs
- [ ] Category is not oversaturated (≤20 similar launches)

---

### 4. Indie Hackers (Revenue Intel + Community)

**URL:** indiehackers.com  
**Apify Actor:** `jupri/indiehackers`

#### What to Extract
- Product name, URL, description
- Self-reported MRR
- Founder info + contact
- Categories
- Growth trajectory (if shared)

#### Step-by-Step Process

1. **Browse Products section**
   ```
   indiehackers.com/products
   ```
   Sort by: Revenue (high to low)

2. **Filter to target range**
   - $1k-10k MRR = replicable by us
   - $10k-50k MRR = proven demand, can we differentiate?
   - >$50k MRR = established, need strong angle

3. **Search discussions for niche**
   ```
   indiehackers.com/search?q=[niche]
   ```
   Look for:
   - "How I built" posts
   - "Revenue milestone" posts
   - "Struggling with" posts (pain points)

4. **Validate revenue claims**
   - Check if founder has OpenStartup dashboard
   - Cross-reference with their Twitter #buildinpublic
   - Look for Baremetrics/ChartMogul screenshots

5. **Extract founder contact**
   - For competitive intelligence later
   - NOT for copying — for understanding market

#### Trust Calibration
| Founder Type | Trust Level | Verify How |
|--------------|-------------|------------|
| Known IH regular, years of posts | High | History validates |
| New account, high MRR claim | Low | Demand external proof |
| Links to live dashboard | Highest | Verified data |

#### Validation Checkboxes
- [ ] ≥2 products in niche with verified revenue
- [ ] At least 1 at $5k+ MRR
- [ ] Community discussions exist (not dead niche)
- [ ] No "this market is dead" sentiment

---

### 5. Revenue Transparency Sources

These provide the highest-trust financial data.

#### Baremetrics Open Startups
**URL:** baremetrics.com/open-startups

- Real Stripe data, verified
- Search for products in target niche
- Extract: MRR, churn, LTV, ARPU

#### OpenStartup Movement
**Search:** "[product name] open startup" or "open startup [niche]"

- Founders publish live dashboards
- Often linked from IH profiles or Twitter bios

#### Twitter #buildinpublic
**Search:** `#buildinpublic [niche]` or `#buildinpublic MRR`

- Monthly revenue updates from founders
- Cross-reference with IH claims
- Look for growth trends, not just snapshots

#### Process
1. Search all three sources for products found in G2/IH
2. Record verified revenue data
3. Note churn rates (critical for subscription viability)
4. If churn >10% monthly → red flag for market

---

### 6. SaaSHub / AlternativeTo (Competitive Mapping)

**URLs:** saashub.com, alternativeto.net

#### Purpose
Map the full competitive landscape from a known product.

#### Step-by-Step Process

1. **Start with known product in niche**
   ```
   alternativeto.net/software/[product-name]
   ```

2. **Extract all alternatives listed**
   - Record names + user vote counts
   - Note which are "liked" most

3. **Categorize competitors**
   | Tier | Characteristics |
   |------|-----------------|
   | Enterprise | High price, complex, sales-led |
   | Mid-market | $100-500/mo, some support |
   | SMB | $20-100/mo, self-serve |
   | Freemium | Free tier + paid upgrade |

4. **Identify gap**
   - All enterprise? → SMB opportunity
   - All complex? → Simpler tool opportunity
   - All old/dated? → Modern UX opportunity

5. **Cross-reference with G2 data**
   - Products on AlternativeTo but not G2 → may be small/new
   - Products on G2 but not AlternativeTo → may be enterprise-only

---

### 7. Community Pain Point Mining

#### Reddit
**Subreddits:**
- r/SaaS, r/microsaas, r/startups
- r/[industry] (niche-specific)
- r/Entrepreneur, r/smallbusiness

**Search queries:**
```
site:reddit.com "[niche] software frustrated"
site:reddit.com "[niche] tool wish"
site:reddit.com "[niche] alternative to"
site:reddit.com "I'd pay for [niche]"
```

**What to extract:**
- Specific pain points (quote them)
- Mentioned competitors
- Upvote count on complaint posts (validates pain)
- Any "I built this" responses (competitors to research)

#### Twitter/X
**Search queries:**
```
"[tool name] sucks"
"[tool name] alternative"
"[niche] software frustrating"
"why isn't there a [niche]"
```

#### Hacker News
**Search:** hn.algolia.com
```
"Ask HN: [niche] tool"
"Show HN: [niche]"
```

**Why HN matters:**
- Technical audience = good signal for dev tools
- Honest feedback in comments
- Launch posts show traction

---

### 8. Traffic & Traction Estimation

Use when revenue data isn't available. **Trust Level: 5 (lowest)**

#### SimilarWeb (similarweb.com)
- Free tier gives basic traffic estimates
- Note: Can be wildly inaccurate for small sites
- Useful for: Relative comparison between competitors

#### BuiltWith (builtwith.com)
- Shows technology adoption
- Useful for: "How many sites use [tool]?" 
- Growing tech usage = growing market

#### Proxy Signals
| Signal | Where to Find | What It Indicates |
|--------|---------------|-------------------|
| Chrome extension users | Chrome Web Store | Active user base |
| GitHub stars | GitHub | Developer interest |
| Job postings | LinkedIn, Indeed | Company is growing |
| Social followers | Twitter, LinkedIn | Audience size |
| Blog publish frequency | Company blog | Active development |

---

## Full Validation Flow

For every niche, execute in this order:

### Phase 1: Quick Scan (30 min)
1. [ ] G2 category search — ≥3 competitors with reviews?
2. [ ] Product Hunt search — any recent launches?
3. [ ] Reddit search — active discussions?
4. [ ] If NO to any → STOP, move on

### Phase 2: Deep Dive (2-3 hours)
5. [ ] Run Apify G2/Capterra scraper on top 5
6. [ ] Extract pricing from all competitors
7. [ ] Read 30+ negative reviews, categorize themes
8. [ ] Search Indie Hackers for revenue data
9. [ ] Map full competitive landscape via AlternativeTo
10. [ ] Mine Reddit/Twitter for specific pain quotes

### Phase 3: Synthesis
11. [ ] Fill out competitor template for top 5
12. [ ] Calculate market size estimate
13. [ ] Identify differentiation angle
14. [ ] Score against universal rubric
15. [ ] If score ≥24 → prepare proposal

---

## Apify Integration Summary

| Source | Actor | Cost | When to Use |
|--------|-------|------|-------------|
| G2/Capterra | `vivid_astronaut/g2-capterra-scraper` | $0.01/result | Deep competitor analysis |
| Product Hunt | `michael.g/product-hunt-scraper` | ~$0.005/product | Category trend analysis |
| Indie Hackers | `jupri/indiehackers` | Pay per usage | Revenue intelligence |

**Budget awareness:** Free tier = $5/month. Use scrapers for bulk analysis, not casual browsing.

**When to scrape vs manual:**
- Manual: Initial exploration, reading reviews/comments
- Scrape: Bulk data extraction, building competitor databases

---

## Output Requirements

Every niche research must produce:

1. **Competitor table** (from COMPETITOR-TEMPLATE.md)
2. **Pain point list** with sources/quotes
3. **Revenue evidence** with trust level noted
4. **Market size estimate** with methodology
5. **Differentiation hypothesis**

If any of these are missing → research is incomplete.
