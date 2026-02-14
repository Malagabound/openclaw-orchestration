# Product Validation Skill — SPEC (Draft for Review)

**Purpose:** Rigorous validation of product opportunities AFTER they pass initial discovery/scoring (≥20/30).

**Goal:** Determine if an opportunity is worth building — not just "interesting" but "people will pay for this."

---

## Context: Two-Stage Process

| Stage | Skill | Output |
|-------|-------|--------|
| 1. Discovery | `product-research`, `digital-product-research`, `software-subscription-research` | Scored opportunities (≥20/30 threshold) |
| 2. Validation | **This skill** | GO/NO-GO decision with evidence |

---

## Validation Framework (Adapted from Jungle Scout + Indie Hackers)

### 6 Validation Checkpoints

Each checkpoint scored 1-5. Must score ≥24/30 to proceed to build.

#### 1. Pain Evidence (1-5)
**Question:** Is the pain REAL and actively discussed?

**How to validate:**
- Find 10+ organic complaints (Reddit, Twitter, G2 reviews, forums)
- Look for phrases like "I wish...", "frustrated with...", "hate that..."
- Check if people are actively searching for solutions

**Scoring:**
- 5 = 20+ complaints found, clear pattern, emotional language
- 4 = 10-20 complaints, consistent theme
- 3 = 5-10 complaints, some variation in pain description
- 2 = <5 complaints, vague pain
- 1 = No organic pain evidence found

---

#### 2. Search Demand (1-5)
**Question:** Are people actively looking for solutions?

**How to validate:**
- Google Keyword Planner / Ubersuggest for search volume
- Reddit search frequency
- Google Trends (stable or growing?)

**Scoring:**
- 5 = 5,000+ monthly searches for core terms, growing trend
- 4 = 1,000-5,000 monthly searches, stable trend
- 3 = 500-1,000 monthly searches
- 2 = 100-500 monthly searches
- 1 = <100 monthly searches

---

#### 3. Competition Landscape (1-5)
**Question:** What exists? Where are the gaps?

**How to validate:**
- Map ALL competitors (direct + indirect)
- Document pricing, features, reviews, funding
- Identify gaps in current solutions

**Scoring:**
- 5 = Clear gap, competitors have <500 reviews avg, no VC-backed players
- 4 = Gap exists, moderate competition, can differentiate on price/UX/niche
- 3 = Crowded but fragmented, no dominant player
- 2 = Established players with good reviews, hard to differentiate
- 1 = Red ocean, VC-backed incumbents, strong network effects

---

#### 4. Market Size (1-5)
**Question:** Is there a path to $20k MRR?

**How to validate:**
- Estimate TAM (total addressable market)
- Calculate realistic SAM (serviceable addressable market)
- Model: At $X/mo, need Y customers for $20k MRR

**Scoring:**
- 5 = Clear path: <500 customers needed at realistic price point
- 4 = Achievable: 500-1,000 customers needed
- 3 = Challenging: 1,000-2,500 customers needed
- 2 = Difficult: 2,500-5,000 customers needed
- 1 = Unrealistic: >5,000 customers needed or pricing won't support

---

#### 5. Willingness to Pay (1-5)
**Question:** Is there EVIDENCE people pay for solutions in this space?

**How to validate:**
- Competitor pricing (do they have paying customers?)
- G2/Capterra reviews mentioning "worth the price" or "too expensive"
- Reddit/forum discussions about paying for tools
- Existing marketplace sales (Gumroad, AppSumo, etc.)

**Scoring:**
- 5 = Competitors have $1M+ ARR or thousands of paying customers
- 4 = Multiple competitors with paid plans, positive pricing reviews
- 3 = Some paid solutions exist, unclear revenue
- 2 = Mostly free alternatives, few paid options
- 1 = Everything is free, no evidence of willingness to pay

---

#### 6. Differentiation Angle (1-5)
**Question:** Can we OWN a specific angle?

**How to validate:**
- Identify unique positioning (niche, UX, price, integration, speed)
- Test if differentiation resonates (Reddit comments, interviews)
- Ensure differentiation is defensible

**Scoring:**
- 5 = Clear, defensible USP that competitors can't easily copy
- 4 = Strong positioning, would require effort for competitors to match
- 3 = Good angle but not unique, execution-dependent
- 2 = Weak differentiation, easily copied
- 1 = No clear differentiation

---

## Validation Process

### Phase A: Desk Research (2-4 hours)
1. **Pain Evidence** — Search Reddit, Twitter, G2, forums for complaints
2. **Search Demand** — Run keyword research tools
3. **Competition Landscape** — Map all competitors, create comparison table
4. **Market Size** — Estimate TAM/SAM/SOM
5. **Willingness to Pay** — Document competitor pricing and revenue evidence

### Phase B: Outreach (Optional, for high-potential ideas)
6. **Landing Page Test** — Simple page with email signup
7. **Community Posts** — Describe the problem, gauge interest
8. **Direct Outreach** — Message 5-10 potential users with questions

### Phase C: Decision
- Score all 6 checkpoints
- **≥24/30** → Proceed to build (with spec)
- **20-23/30** → Consider but research more
- **<20/30** → Reject, document learnings

---

## Output Format

For each validated opportunity:

```markdown
## [Opportunity Name] — Validation Report

**Discovery Score:** X/30
**Validation Score:** X/30
**Decision:** GO / NO-GO / NEEDS MORE RESEARCH

### Checkpoint Scores
| Checkpoint | Score | Evidence |
|------------|-------|----------|
| Pain Evidence | X/5 | [summary] |
| Search Demand | X/5 | [keywords + volumes] |
| Competition | X/5 | [key competitors] |
| Market Size | X/5 | [TAM/SAM calculation] |
| Willingness to Pay | X/5 | [pricing evidence] |
| Differentiation | X/5 | [proposed USP] |

### Key Findings
- [insight 1]
- [insight 2]

### Risks
- [risk 1]
- [risk 2]

### Recommendation
[GO: Here's why we should build this]
[NO-GO: Here's why we should pass]
```

---

## Integration with Product Prospector

- Validated opportunities update status in Supabase: `discovered` → `validated` or `rejected`
- Validation reports stored as markdown in `research/validations/`
- Dashboard shows validation progress

---

## Questions for Alan

1. **Threshold:** Is ≥24/30 the right bar for "proceed to build"?
2. **Outreach:** Do you want me to do landing page tests, or just desk research?
3. **Time budget:** How many hours per validation is acceptable?
4. **Priority:** Which of the 3 software subscriptions should I validate first?
   - Feedback-to-Roadmap Tool (24/30 discovery)
   - AI Prompt Library (24/30 discovery)  
   - AI API Cost Tracker (23/30 discovery)

---

*Draft v1 — Feb 5, 2026*
