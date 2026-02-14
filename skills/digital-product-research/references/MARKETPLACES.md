# Digital Product Marketplace Research Guide

Systematic process for extracting data from each platform. Follow these steps exactly.

---

## 1. Gumroad

### Discovery URLs

| URL | What It Shows |
|-----|---------------|
| `gumroad.com/discover` | All categories, trending |
| `gumroad.com/discover?tags=templates` | Templates category |
| `gumroad.com/discover?tags=notion` | Notion templates |
| `gumroad.com/discover?tags=design` | Design assets |
| `gumroad.com/discover?tags=software` | Software/tools |
| `gumroad.com/discover?tags=education` | Courses/tutorials |

### Search Method

1. **Browse by category** at URLs above
2. **Search specific niches**: `gumroad.com/discover?query=[keyword]`
   - Example: `gumroad.com/discover?query=real+estate+template`
3. **Sort options**: Click "Popular" or "Newest" (no URL param, must click)

### Data Extraction (per product)

On each product page, capture:

| Field | Where to Find |
|-------|---------------|
| Product name | Page title |
| Price | Below title (look for crossed-out original if discounted) |
| Sales count | Below price — shows "[X] sales" (not always visible) |
| Rating | Star rating + review count |
| Creator | Profile link at top |
| Description | Main content area |
| What's included | Usually listed in description or bullet points |

### Creator Deep-Dive

Click creator profile to see:
- Total sales across all products
- Other products (portfolio patterns)
- Follower count

**Document creators with 1,000+ total sales** — they've validated the niche.

### Limitations

- Not all products show sales counts (creator setting)
- No price range filter
- Search algorithm favors established creators
- Can't sort by revenue

### Research Workflow

```
1. Pick category URL from table above
2. Scroll through first 50 products
3. Open products with visible sales > 50 in new tabs
4. For each: capture data in COMPETITOR-TEMPLATE.md format
5. Search 3-5 niche-specific keywords
6. Repeat data capture for promising results
7. Note top 3-5 creators in the space
```

---

## 2. Creative Market

### Discovery URLs

| URL | What It Shows |
|-----|---------------|
| `creativemarket.com/templates` | All templates |
| `creativemarket.com/templates/presentations` | Presentation templates |
| `creativemarket.com/templates/resumes` | Resume templates |
| `creativemarket.com/graphics` | Graphics & illustrations |
| `creativemarket.com/fonts` | Fonts |
| `creativemarket.com/themes` | Website themes |
| `creativemarket.com/photos` | Stock photos |

### Search Method

1. **Category browse**: Use URLs above
2. **Search bar**: `creativemarket.com/search?q=[keyword]`
3. **Filters available**:
   - Sort by: Best Sellers, Newest, Price
   - Price range: Free, Under $10, $10-$25, $25-$50, $50+
   - File type filters

### Sorting for Research

**Always sort by "Best Sellers"** — this surfaces proven demand.

URL pattern: `creativemarket.com/search?q=[keyword]&sort=best-sellers`

### Data Extraction (per product)

| Field | Where to Find |
|-------|---------------|
| Product name | Title |
| Price | Right sidebar |
| Sales count | Below title — "[X] Sales" |
| Rating | Stars + review count |
| Shop name | Link below title |
| What's included | "What's Included" section |
| File formats | Listed in details |
| Reviews | Bottom of page — read for complaints |

### Shop Analysis

Click shop name to see:
- Total shop sales
- All products
- Shop rating
- Member since (longevity = credibility)

**High-value signal**: Shops with 10,000+ total sales in a niche category.

### Research Workflow

```
1. Go to relevant category URL
2. Sort by Best Sellers
3. Scan first 100 results
4. Target: products with 500+ sales at $20+
5. Open top 10 in new tabs
6. Capture data for each
7. Read 5-10 negative reviews per product (find gaps)
8. Check shop profiles of top sellers
9. Search 3-5 niche keywords, repeat
```

---

## 3. Etsy (Digital Downloads)

### Discovery URLs

| URL | What It Shows |
|-----|---------------|
| `etsy.com/search?q=digital+download&explicit=1` | All digital |
| `etsy.com/search?q=notion+template&explicit=1` | Notion templates |
| `etsy.com/search?q=canva+template&explicit=1` | Canva templates |
| `etsy.com/search?q=spreadsheet+template&explicit=1` | Spreadsheets |
| `etsy.com/search?q=planner+printable&explicit=1` | Planners |
| `etsy.com/search?q=resume+template&explicit=1` | Resumes |
| `etsy.com/search?q=budget+template&explicit=1` | Budget tools |

### Search Method

1. **Search**: `etsy.com/search?q=[keyword]`
2. **Add digital filter**: Click "Digital downloads" in left sidebar, or add `&is_digital=true` to URL
3. **Sort options**: Relevancy, Lowest Price, Highest Price, Most Recent
   - Note: No "Best Seller" sort — Etsy buries this

### Finding Best Sellers

Etsy hides sales data in search. To find top performers:

1. Search your keyword
2. Look for "Bestseller" badge on listings
3. Look for "Star Seller" badge on shops
4. Click into products, check sales count on product page

### Data Extraction (per product)

| Field | Where to Find |
|-------|---------------|
| Product name | Title |
| Price | Right side |
| Sales count | Below title — "[X] sales" |
| Reviews | Star rating + count |
| Shop name | Below title |
| What's included | Description + "Digital download" section |
| File formats | Listed in description |

### Shop Analysis

Click shop to see:
- Total shop sales
- Total reviews
- Shop creation date
- All listings
- "Star Seller" status

### Research Workflow

```
1. Search niche keyword + "template" or "digital"
2. Filter to Digital downloads
3. Scan first 50 results for Bestseller badges
4. Open products with 1,000+ sales
5. Capture data for top 10
6. Read negative reviews (1-2 star) for gaps
7. Check shop profiles — note shops with 5,000+ sales
8. Search related keywords, repeat
```

---

## 4. Envato (ThemeForest / CodeCanyon / GraphicRiver)

### Discovery URLs

| URL | What It Shows |
|-----|---------------|
| `themeforest.net/popular_items` | Top selling themes |
| `themeforest.net/category/wordpress` | WordPress themes |
| `themeforest.net/category/site-templates` | HTML templates |
| `codecanyon.net/popular_items` | Top selling code |
| `codecanyon.net/category/javascript` | JS scripts/plugins |
| `graphicriver.net/popular_items` | Top selling graphics |

### Search Method

1. **Category browse**: Use sidebar navigation
2. **Search**: Search bar at top
3. **Sort by**: Best Sellers, Newest, Best Rated, Price

### Data Extraction (per product)

Envato shows the BEST data of any marketplace:

| Field | Where to Find |
|-------|---------------|
| Product name | Title |
| Price | Right sidebar |
| **Exact sales count** | Right sidebar — always visible |
| Rating | Stars + review count |
| Author | Profile link |
| Last updated | Right sidebar (important for themes) |
| Comments | Bottom — feature requests and complaints |

### Author Analysis

Click author profile:
- Total portfolio sales
- All items
- Author rating
- Member since

### Research Workflow

```
1. Go to popular_items for relevant marketplace
2. Browse top 50 best sellers in target category
3. Note products with 1,000+ sales
4. Calculate revenue: Sales × Price
5. Read comments section for:
   - Feature requests (gaps)
   - Complaints (opportunities)
   - Support issues (their weakness)
6. Check author portfolios of top sellers
7. Search niche keywords, sort by Best Sellers
8. Document top 5 competitors with full data
```

---

## 5. AppSumo

### Discovery URLs

| URL | What It Shows |
|-----|---------------|
| `appsumo.com/browse/` | All current deals |
| `appsumo.com/browse/?category=productivity` | Productivity tools |
| `appsumo.com/browse/?category=marketing` | Marketing tools |
| `appsumo.com/browse/?category=design` | Design tools |
| `appsumo.com/browse/?ordering=-review_count` | Sort by reviews |

### Search Method

1. **Browse**: Use category filters in sidebar
2. **Search**: Search bar for keywords
3. **Sort**: By review count or recency

### Data Extraction (per product)

| Field | Where to Find |
|-------|---------------|
| Product name | Title |
| Price | Deal price (usually lifetime) |
| Original value | Crossed out price |
| Review count | On card and product page |
| Rating | Stars |
| "Bought today" | Sometimes shown |
| Features | Detailed on product page |
| Questions | Q&A section — gold for understanding objections |

### Research Workflow

```
1. Browse relevant category
2. Sort by review count (most reviews = most buyers)
3. Focus on products with 100+ reviews
4. Read product pages for:
   - Feature lists (what's expected in the space)
   - Q&A section (buyer concerns)
   - Reviews (what people love/hate)
5. Note pricing patterns (even though LTD, indicates value)
6. Check if similar products keep appearing (category has legs)
```

### Limitation

AppSumo is mostly SaaS/tools, not pure digital products. Use for:
- Understanding tool categories
- Feature expectations
- Price anchoring
- Identifying tool niches that might also want templates/assets

---

## 6. Product Hunt

### Discovery URLs

| URL | What It Shows |
|-----|---------------|
| `producthunt.com/topics/productivity` | Productivity products |
| `producthunt.com/topics/design-tools` | Design tools |
| `producthunt.com/topics/developer-tools` | Dev tools |
| `producthunt.com/topics/notion` | Notion ecosystem |
| `producthunt.com/search?q=[keyword]` | Search results |

### Search Method

1. **Topics**: Browse by topic (URLs above)
2. **Search**: `producthunt.com/search?q=[keyword]`
3. **Time filter**: Today, This Week, This Month, This Year

### Data Extraction (per product)

| Field | Where to Find |
|-------|---------------|
| Product name | Title |
| Tagline | One-liner description |
| Upvotes | On card and product page |
| Comments | Engagement level |
| Launch date | Listed on page |
| Maker | Profile linked |
| Links | Website, social, etc. |

### Research Workflow

```
1. Search niche keyword
2. Filter to "This Year" or "All Time"
3. Look for products with 200+ upvotes
4. Read comments for:
   - Feature requests
   - "I wish it did X"
   - Competitor mentions
5. Check if maker is still active (dead products = opportunity)
6. Visit actual product site — is it still maintained?
7. Note any pricing or traction signals
```

---

## 7. Notion Template Gallery

### Discovery URL

`notion.so/templates`

### Browse Method

1. **Categories**: Left sidebar (Personal, Work, School, etc.)
2. **Subcategories**: Expand each category
3. **Featured**: Notion's curated picks

### Limitations

- No sales data visible
- Mix of free and paid (unclear which)
- No sorting by popularity (just "Popular" section)

### Research Workflow

```
1. Browse relevant category
2. Note template names and what they offer
3. Cross-reference with Gumroad:
   - Search same template type on Gumroad
   - Compare features and pricing
4. Identify gaps:
   - What's on Notion Gallery that's NOT on Gumroad?
   - What paid Gumroad templates fill gaps in free gallery?
5. Use gallery for inspiration, Gumroad for validation
```

---

## Cross-Platform Research Process

For any niche you're exploring:

### Step 1: Quick Scan (30 min)
```
- Gumroad: Search keyword, sort Popular, note top 5
- Creative Market: Search keyword, sort Best Sellers, note top 5
- Etsy: Search keyword + digital, find Bestsellers, note top 5
```

### Step 2: Deep Dive (1-2 hours)
```
- Pick top 3 competitors from scan
- Fill out COMPETITOR-TEMPLATE.md for each
- Read 10+ reviews per competitor
- Document complaints and gaps
```

### Step 3: Revenue Validation (30 min)
```
- Calculate competitor revenue: Sales × Price
- Estimate monthly sales (if product age known)
- Document in proposal
```

### Step 4: Cross-Reference (30 min)
```
- Same product selling on multiple platforms = strong signal
- Same creator on multiple platforms = they've validated the niche
- Consistent pricing across platforms = market rate established
```

---

## Data Capture Template

For each product researched:

```markdown
## [Product Name]

**Platform:** [Gumroad/Creative Market/Etsy/etc.]
**URL:** [link]
**Price:** $[X]
**Sales:** [X] (or "not visible")
**Rating:** [X] stars ([X] reviews)
**Creator/Shop:** [name] ([total shop sales])

**What's Included:**
- [Item 1]
- [Item 2]

**Key Reviews (Negative):**
- "[Quote about what's missing]"
- "[Quote about frustration]"

**Gap/Opportunity:**
- [What we could do better]
```
