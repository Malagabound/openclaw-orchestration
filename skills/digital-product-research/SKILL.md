---
name: digital-product-research
description: Research and validate digital product ideas (templates, courses, ebooks, tools, assets) for one-time sales. Use when discovering new product opportunities, validating ideas, analyzing competitors, or preparing product proposals for Alan.
---

# Digital Product Research

Extension of `product-research` skill for one-time sale digital products.

**First:** Read `skills/product-research/SKILL.md` for:
- **Workflow ownership** (Phase 1-2 = George autonomous, Phase 3 = Alan approval)
- **Template locations** (Phase 1 and Phase 2 Google Doc templates)
- **Rejection tracking** (Product Prospector database)
- **Scoring rubric** (6 criteria, thresholds)

This skill provides digital-product-specific discovery sources.

## What Counts as a Digital Product

One-time purchase OR usage-based items:
- Templates (Notion, spreadsheets, presentations, design)
- Courses and educational content
- Ebooks and guides
- Design assets (icons, fonts, graphics, mockups)
- Code snippets and starter kits
- Printables and planners
- Audio/video assets
- **API products** (scrapers, data APIs, utility APIs)
- **Browser extensions** (Chrome, Firefox)
- **Platform plugins** (Figma, Shopify, WordPress)

**NOT:** Full SaaS applications (see `software-subscription-research`)

## ⚠️ CRITICAL: REGULATED/COMPLIANCE INDUSTRY FILTER (Updated 2026-02-10)

**🚨 IMMEDIATE RED FLAG KEYWORDS - AUTO-REJECT:**
- **regulated, compliance, regulatory, government, EPA, FDA, OSHA, HIPAA, SOX, PCI**
- **medical, healthcare, pharmaceutical, finance, banking, legal, insurance**
- **trucking regulations, medical waste, lab animal care, environmental compliance**
- **prompt engineering, AI prompts, prompt chains** (saturated 2022-era market)

**IF ANY OF THESE APPEAR → STOP IMMEDIATELY. DO NOT RESEARCH. DO NOT SCORE. MOVE ON.**

## Phase 1: Discovery Sources

### Primary Marketplaces

| Marketplace | URL | Best For | Key Data |
|-------------|-----|----------|----------|
| Gumroad | gumroad.com/discover | All digital products | Sales counts visible |
| Creative Market | creativemarket.com | Design assets, templates | Sales + reviews |
| Etsy | etsy.com (digital filter) | Printables, templates | Sales counts |
| Envato/ThemeForest | themeforest.net | Code, themes, templates | Exact sales |
| AppSumo | appsumo.com | Tools, courses | Reviews, "bought today" |
| Notion Template Gallery | notion.so/templates | Notion templates | Popularity sorting |

**See `references/MARKETPLACES.md` for detailed research methods per platform.**

### API & Code Marketplaces

| Marketplace | URL | Best For | Revenue Model |
|-------------|-----|----------|---------------|
| Apify Store | apify.com/store | Scrapers, automation | Pay-per-use or rental |
| RapidAPI | rapidapi.com | Data APIs, utilities | 20% commission |
| APILayer | apilayer.com | Curated APIs | 15% commission |
| CodeCanyon | codecanyon.net | Scripts, plugins | One-time sales |
| Chrome Web Store | chrome.google.com/webstore | Browser extensions | Free/freemium |

**See `references/API-MARKETPLACES.md` for detailed research methods.**

### Secondary Sources

| Source | What to Look For |
|--------|------------------|
| Product Hunt | Launched products with traction; maker activity |
| Gumroad Creator Profiles | Top sellers' full portfolios |
| Udemy/Skillshare | Course topics with high enrollment |
| Amazon Kindle | Ebook categories and bestseller ranks |

### Pain Point Mining

Use universal methods from parent skill, plus:
- Search "[profession] + template" on Reddit
- Search "[tool name] + template/starter" (e.g., "Notion template", "Figma starter kit")
- Browse r/Entrepreneur, r/SideProject for "I made $X selling [product]" posts

## Revenue Model Notes

**One-time sales math:**
```
Monthly Revenue = Price × Monthly Units Sold
```

**Typical ranges:**
- Low end: $15-29 (templates, simple assets)
- Mid range: $29-79 (comprehensive templates, courses)
- Premium: $79-199 (course bundles, premium assets)

**Volume expectations:**
- New product, no audience: 5-20 sales/month
- Established, good reviews: 50-200 sales/month
- Top sellers: 500+ sales/month

## Digital Product-Specific Scoring Notes

When using the universal rubric (`product-research/references/SCORING-RUBRIC.md`):

**Build Effort:** Digital products are usually faster to build than SaaS. A "3" here might be 1-2 weeks (vs 2-4 weeks for equivalent SaaS).

**Revenue Potential:** One-time sales cap out lower than subscriptions. A "5" is >$3k/month — ambitious but achievable for top performers.

**Maintenance:** Usually minimal. Factor this into Build Effort favorably.

## Phase 2: Validation

**For digital products, use the specific validation process in:**
`references/VALIDATION-METHODS.md`

Key steps:
1. **Marketplace Mining** — Use GumTrends/eRank to find products with high sales + mixed reviews
2. **Demand Signals** — Google Trends, Pinterest Trends, community activity
3. **Pre-Sell Test** — Gumroad pre-order or waitlist landing page
4. **Threshold:** 3+ pre-orders OR 50+ waitlist signups = validated

## Reference Files

**Shared (in `product-research/references/`):**
- `SCORING-RUBRIC.md` — Universal scoring criteria
- `COMPETITOR-TEMPLATE.md` — Standard competitor analysis
- `PROPOSAL-TEMPLATE.md` — Proposal format for Alan
- `NICHES-EXPLORED.md` — Log of all researched niches

**Digital-product specific:**
- `references/VALIDATION-METHODS.md` — Phase 2 validation process for digital products
- `references/MARKETPLACES.md` — Traditional digital product platforms (Gumroad, Etsy, etc.)
- `references/API-MARKETPLACES.md` — API, scraper, and code marketplaces (Apify, RapidAPI, etc.)
