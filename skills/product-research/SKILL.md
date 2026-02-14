---
name: product-research
description: Core framework for researching and validating product opportunities (digital products, software subscriptions, or any revenue-generating product). Provides shared scoring rubric, validation process, and proposal format. Use this as the foundation; see child skills for product-type-specific discovery sources.
---

# Product Research Framework

Universal process for discovering, validating, and proposing product opportunities. This is the parent skill — child skills (digital-product-research, software-subscription-research) provide product-type-specific discovery sources.

## ⚠️ WORKFLOW OWNERSHIP - IRONCLAD CEO RULE

| Phase | Who Decides | Alan's Involvement |
|-------|-------------|-------------------|
| Phase 1: Discovery | **Sub-agents** | NONE — Alan NEVER sees Phase 1 results |
| Phase 1 → Phase 2 | **AUTOMATIC** | NO permission needed if ≥20/30 |
| Phase 2: Deep Validation | **Sub-agents** | NONE — Alan NEVER sees Phase 2 in-progress |
| Phase 2 PASS → Phase 3 | **Present to Alan** | ONLY present opportunities that PASS Phase 2 |
| Phase 3: Paid Validation | **Alan** | Must approve before any money is spent |

**IRONCLAD CEO RULE:** Alan only sees opportunities that have PASSED both Phase 1 AND Phase 2 validation. Never present "should we move to Phase 2?" questions. Never show Phase 1/Phase 2 results unless they PASS. Alan is the CEO — only gets involved when validation is complete and an idea passes.

---

## The Golden Rule

**Never bring an idea to Alan without empirical validation.** Every proposal must include:
- Proof of demand (sales data, search volume, community requests)
- Competitor analysis (who's selling what, at what price, with what reviews)
- Clear differentiation angle (why ours wins)
- Revenue projection grounded in real numbers

---

## Phase 1: Discovery (George Autonomous)

**MANDATORY:** For every opportunity discovered, complete the Phase 1 Discovery Report.

### Template Document
https://docs.google.com/document/d/17Gk2zWrRmKoonJ-RtSyhgxwwJwC1yW6TbYjSuQRLqG8/edit

### Process
1. Copy the template
2. Rename to: "Phase 1 - [Product Name] - [Date]"
3. Move to appropriate subfolder (#George/Software Subscriptions or #George/Digital Products)
4. Fill out ALL sections completely
5. Calculate the 6-criteria score

### Phase 1 Decision (Specialist Makes This Call)

| Score | Decision | Action |
|-------|----------|--------|
| ≥ 20/30 | **PROCEED** | AUTOMATICALLY spawn Scout for Phase 2 validation |
| < 20/30 | **PASS** | Log in Product Prospector as `rejected`, move on |

**HANDOFF PROTOCOL (AUTOMATIC):**
When opportunity scores ≥20/30, specialist MUST spawn Scout:
```
sessions_spawn scout "Phase 2 deep validation for [OPPORTUNITY]. 
Phase 1 score: [X/30]. 
Use [domain-specific-research] skill for methodology."
```

**Alan does NOT need to see Phase 1 results.** This is specialist's filter.

### Discovery Sources

Discovery sources vary by product type. See child skills:
- **Digital products**: `digital-product-research`
- **Software subscriptions**: `software-subscription-research`
- **Business acquisitions**: `business-acquisition-research`

---

## ⚠️ CRITICAL: MICRO-NICHE FILTER GATES (Updated 2026-02-10)

**BEFORE doing ANY research, apply these gates in order:**

### 0. REGULATED/COMPLIANCE INDUSTRY GATE (IRONCLAD)
**🚨 IMMEDIATE RED FLAG KEYWORDS - AUTO-REJECT:**
- **regulated, compliance, regulatory, government, EPA, FDA, OSHA, HIPAA, SOX, PCI**
- **medical, healthcare, pharmaceutical, finance, banking, legal, insurance**
- **trucking regulations, medical waste, lab animal care, environmental compliance**
- **prompt engineering, AI prompts, prompt chains** (saturated 2022-era market)

**IF ANY OF THESE APPEAR → STOP IMMEDIATELY. DO NOT RESEARCH. DO NOT SCORE. MOVE ON.**

### 1. Niche Test (MOST IMPORTANT)
- **Google "[weird job/service] software"** 
- **If 3+ established competitors appear → STOP, TOO MAINSTREAM**
- **If Fortune 500 would build this → STOP, WRONG DIRECTION**
- **If it's an established industry (veterinarians, property management, accounting) → STOP**

### 2. Weirdness Test
- **Is this a weird job most people don't know exists?** (grave cleaners, septic pumpers, bee removal)
- **Do they have trucks but no software?** (mobile services with manual processes)
- **Are they 1-10 person operations?** (too small for big companies to care)
- **If NO to any → reconsider if it's niche enough**

### 3. Standard Gates
- **Is there existing demand?** (Reddit complaints OR search volume > 100/mo OR community requests)
- **Can Alan build it?** (Within dev skills, no specialized expertise required)
- **Is the audience B2B or prosumer?** (They have money and will pay)
- **Is it evergreen or trend-dependent?** (Prefer evergreen)
- **Is it in a "hard no" category?** (Check MEMORY.md)

### 4. Final Gate: Portfolio Thinking
- **Could this realistically hit $1-5k MRR?** (Part of portfolio approach, not one big winner)
- **Is support burden low?** (Simple workflows, not complex enterprise needs)

**If ANY gate fails → move on. Don't waste time on deep research.**

---

## Phase 2: Deep Validation (George Autonomous, NO MONEY SPENT)

**MANDATORY:** For any product scoring ≥20/30 in Phase 1, complete the Phase 2 Validation Report.

### Template Document
https://docs.google.com/document/d/1jXUeUi4i718oKTzB9gHolBDP0IrFCIt8paDnQgMoqes/edit

### Process
1. Copy the template
2. Rename to: "Phase 2 - [Product Name] - [Date]"
3. Move to appropriate subfolder
4. Fill out ALL six sections completely:
   - Competitor Deep-Dive (use native Google Docs tables)
   - Gap Analysis
   - Differentiation Thesis
   - Market Sizing (TAM/SAM/SOM)
   - Build Cost Estimate (use native Google Docs tables)
   - Go/No-Go Recommendation

### Phase 2 Decision (Scout Makes This Call)

| Final Score | Decision | Action |
|-------------|----------|--------|
| ≥ 24/30 + GO | **PRESENT TO ALAN** | Scout validates, then shares Phase 2 doc for approval |
| 20-23 | **CONDITIONAL** | Scout reviews and makes final call |
| < 20 | **NO-GO** | Log in Product Prospector as `rejected`, move on |

**Scout Verification Required:** All Phase 2 results must pass Scout validation before reaching Alan.

---

## Phase 2 → Phase 3 Handoff (REQUIRES ALAN'S APPROVAL)

When George has a GO decision from Phase 2:

1. Post summary to relevant Telegram group (Software Subscriptions or Digital Products)
2. Include:
   - Product name and type
   - Final score (X/30)
   - Key differentiation thesis
   - Link to Phase 2 Google Doc
3. Wait for Alan's response

**Alan decides:**
- ✅ **APPROVED** → Proceed to Phase 3
- ❌ **DECLINED** → Log in Product Prospector as `rejected` with Alan's reason
- 🔄 **PIVOT** → George adjusts approach based on feedback

---

## Phase 3: Transactional Validation (REQUIRES ALAN'S APPROVAL)

Only for products that Alan has explicitly approved:

1. Build landing page / smoke test
2. Run ads ($50-100 budget)
3. Collect pre-orders or waitlist signups
4. Go/no-go based on conversion data

**George does NOT start Phase 3 without Alan's explicit approval.**

---

## Rejection Tracking (CRITICAL)

All rejected ideas must be logged to prevent re-researching the same things.

### Product Prospector Database
**URL:** https://product-prospector.netlify.app
**Database:** Supabase (gtkehmsgiofaexftirgu.supabase.co)

### Status Flow
```
discovered → researching → validated → building → launched
                ↓
             rejected (with reason)
```

### When to Log as Rejected

| Rejection Point | Status | Reason to Log |
|-----------------|--------|---------------|
| Phase 1: Score < 20 | `rejected` | "Phase 1: Score X/30 - [brief reason]" |
| Phase 2: Score < 20 or NO-GO | `rejected` | "Phase 2: Score X/30 - [brief reason]" |
| Alan declines at handoff | `rejected` | "Alan declined: [his reason]" |

### Before Starting ANY Research

**Check Product Prospector first** to see if the niche/product was already researched and rejected.

---

## Scoring Rubric

Score each idea 1-5 on six criteria:

| Criterion | Weight | What It Measures |
|-----------|--------|------------------|
| Demand | 1x | Proof that people want this |
| Competition | 1x | Market saturation and beatable competitors |
| Monetization | 1x | Realistic income ceiling |
| Buildability | 1x | Time/complexity to launch |
| Scalability | 1x | Low maintenance, automation potential |
| Passion Fit | 1x | Alignment with Alan's background |

### Thresholds

| Total | Meaning |
|-------|---------|
| ≥ 24/30 | Strong GO → Present to Alan |
| 20-23/30 | Conditional → George decides |
| < 20/30 | PASS → Log as rejected |

---

## Reference Files

- `references/rex-saas-criteria.md` — **Rex's SaaS scoring criteria (CRYSTAL CLEAR)**
- `references/pixel-digital-criteria.md` — **Pixel's digital product criteria (CRYSTAL CLEAR)**
- `references/vault-acquisition-criteria.md` — **Vault's business acquisition criteria (CRYSTAL CLEAR)**
- `references/SCORING-RUBRIC.md` — Detailed scoring criteria
- `references/COMPETITOR-TEMPLATE.md` — Standard competitor analysis format
- `references/PROPOSAL-TEMPLATE.md` — Proposal format for Alan
- `references/NICHES-EXPLORED.md` — Legacy log (now use Product Prospector)

---

## Key Principles

1. **Data over intuition** — If you can't find numbers, the idea isn't validated
2. **Competitors are good** — They prove demand; zero competitors = no market
3. **Price signals quality** — Don't race to bottom
4. **Time kills deals** — Validate quickly, build quickly
5. **Alan's time is precious** — Only surface GO decisions from Phase 2
6. **Track rejections** — Never research the same thing twice
