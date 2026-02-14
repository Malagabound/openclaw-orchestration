# Regulated Industry Filter Test

## Test Scenarios

These should ALL be AUTO-REJECTED by updated filters:

### Test 1: Medical Compliance
**Opportunity:** "Practice management software for healthcare providers with HIPAA compliance features"
**Expected Result:** STOP IMMEDIATELY - contains "healthcare" and "HIPAA" 
**Rejection Reason:** Regulated industry (healthcare + HIPAA compliance)

### Test 2: Financial Services
**Opportunity:** "Banking transaction monitoring with regulatory compliance reporting"
**Expected Result:** STOP IMMEDIATELY - contains "banking," "regulatory," and "compliance"
**Rejection Reason:** Regulated industry (finance/banking + regulatory compliance)

### Test 3: Environmental Compliance
**Opportunity:** "Environmental compliance tracking for trucking companies with EPA integration"
**Expected Result:** STOP IMMEDIATELY - contains "compliance," "trucking," and "EPA"
**Rejection Reason:** Regulated industry (environmental compliance + trucking regulations)

### Test 4: Prompt Engineering (Saturated)
**Opportunity:** "AI prompt chains for content creators to optimize ChatGPT workflows"
**Expected Result:** STOP IMMEDIATELY - contains "AI prompt chains" and "prompt"
**Rejection Reason:** Saturated 2022-era market

## Verification Process

1. **Skills Check:** All product research skills now have 🚨 AUTO-REJECT sections
2. **Criteria Check:** Rex, Pixel, and Vault criteria files updated  
3. **Memory Check:** SOUL.md and MEMORY.md prominently display the restrictions
4. **Keyword Check:** Comprehensive blocklist implemented

## Expected Behavior

When ANY red flag keyword appears:
1. **STOP IMMEDIATELY**
2. **DO NOT RESEARCH** 
3. **DO NOT SCORE**
4. **MOVE ON** to next opportunity

No exceptions. No "but this one might be different" reasoning.

---

**Files Updated:**
- ✅ skills/product-research/SKILL.md  
- ✅ skills/software-subscription-research/SKILL.md
- ✅ skills/digital-product-research/SKILL.md
- ✅ skills/product-research/references/rex-saas-criteria.md
- ✅ skills/product-research/references/pixel-digital-criteria.md  
- ✅ skills/product-research/references/vault-acquisition-criteria.md
- ✅ SOUL.md
- ✅ MEMORY.md
- ✅ .learnings/LEARNINGS.md

**This pattern WILL NOT repeat.**