# Regulated/Compliance Filter Implementation - 2026-02-10

## Problem
I repeatedly suggested regulated/compliance industry opportunities to Alan despite his clear corrections:
1. **Rex suggested** "AI-powered code review for regulated industries" 
2. **Pixel suggested** "AI prompt chains for content creators"  
3. **I suggested** "regulatory compliance spaces - trucking, medical waste, lab animal care"

Alan had to correct me MULTIPLE TIMES about avoiding:
- Regulated/compliance industries
- Prompt engineering (saturated 2022-era market)

## Root Cause
Filter gates in skills were missing comprehensive regulated/compliance keyword blocking. The restrictions existed in MEMORY.md but weren't prominently placed in the active skill workflows.

## Fix Implemented

### 1. Updated Core Skills
Added **🚨 REGULATED/COMPLIANCE INDUSTRIES - AUTO-REJECT** section to:
- ✅ `skills/product-research/SKILL.md` (parent framework)
- ✅ `skills/software-subscription-research/SKILL.md` (SaaS research)  
- ✅ `skills/digital-product-research/SKILL.md` (digital products)

### 2. Updated Specialist Criteria
Added same auto-reject filter to ALL specialist scoring criteria:
- ✅ `skills/product-research/references/rex-saas-criteria.md`
- ✅ `skills/product-research/references/pixel-digital-criteria.md`
- ✅ `skills/product-research/references/vault-acquisition-criteria.md`

### 3. Updated Core Memory Files
Enhanced existing restrictions in:
- ✅ `MEMORY.md` - Made regulated/compliance section more prominent
- ✅ `SOUL.md` - Added to "What to AVOID" with 🚨 prominence

### 4. Comprehensive Keyword List
**Auto-reject if ANY of these appear:**
- regulated, compliance, regulatory, government, EPA, FDA, OSHA, HIPAA, SOX, PCI
- medical, healthcare, pharmaceutical, finance, banking, legal, insurance
- trucking regulations, medical waste, lab animal care, environmental compliance
- prompt engineering, AI prompts, prompt chains (saturated market)

### 5. Process Change
**IF ANY RED FLAG KEYWORD APPEARS → STOP IMMEDIATELY. DO NOT RESEARCH. DO NOT SCORE. MOVE ON.**

## Verification Needed
- [ ] Test that specialists now reject opportunities containing these keywords
- [ ] Verify filter gates are applied BEFORE any scoring begins
- [ ] Confirm all sub-agents have access to updated criteria files

## Never Again
This pattern of repeatedly ignoring Alan's corrections about the same topic MUST NOT happen again. The fix is now embedded in:
- Every skill workflow (product-research, software-subscription-research, digital-product-research)
- Every specialist criteria file (Rex, Pixel, Vault)
- My core behavioral files (SOUL.md, MEMORY.md)

**Rule: When Alan corrects the same mistake multiple times, it becomes an IRONCLAD behavioral change, not just a suggestion.**