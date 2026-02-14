# Research Handoff Protocol - SYSTEMATIC & AUTOMATIC

**Date Established:** 2026-02-08
**Context:** Clear division of labor between specialists and Scout

## AUTOMATIC HANDOFF TRIGGERS

### Phase 1 → Phase 2 Handoff (AUTOMATIC)
**When:** Any opportunity scores ≥20/30 in Phase 1
**Who:** Specialist agent MUST spawn Scout immediately  
**No exceptions:** This is automatic, not optional

### Handoff Command Template:
```
sessions_spawn scout "Phase 2 deep validation for [OPPORTUNITY NAME]. 
Phase 1 score: [X/30]. 
Domain: [SaaS/Digital Product/Business Acquisition]
Details: [brief description]
Use [domain-specific-research] skill for methodology.
Report results back to [Agent Name] in [Telegram Group]."
```

## ROLE BOUNDARIES (IRONCLAD)

### Specialists Do (Phase 1):
✅ Initial discovery using domain expertise
✅ Basic competitive research within domain knowledge
✅ Phase 1 scoring (6 criteria)
✅ Simple market validation (demand signals)

### Specialists DON'T Do:
❌ Phase 2 deep validation
❌ Complex market sizing (TAM/SAM/SOM)
❌ Multi-platform research coordination
❌ Advanced competitive deep-dives

### Scout Does (Phase 2):
✅ Phase 2 deep validation (comprehensive)
✅ Market sizing analysis (extensive data collection)
✅ Cross-platform research (multiple tools/sources)
✅ Competitive deep-dives (technical analysis)
✅ Complex data collection (Apify actors, advanced scraping)
✅ Multi-step research workflows

### Scout DON'T Do:
❌ Initial opportunity discovery
❌ Domain-specific identification
❌ Phase 1 scoring (that's specialist expertise)

## GEORGE'S MONITORING REQUIREMENTS

**I must watch for:**
- Opportunities scoring ≥20/30 that DON'T get handed to Scout
- Phase 2 validations that aren't happening  
- Scout results that don't flow back to specialists
- Specialists doing Phase 2 work themselves (role violation)

**Monitoring Actions:**
- Daily check: Are handoffs happening for ≥20/30 scores?
- Intervention: If specialist doesn't hand off, I spawn Scout directly
- Follow-up: Ensure Scout results reach back to specialists
- Process fixes: Update systemPrompts if roles get confused

## EMBEDDED LOCATIONS

**This protocol must be embedded in:**
1. Specialist agent systemPrompts (Rex, Pixel, Vault)
2. Scout agent systemPrompt  
3. Research skills documentation
4. My orchestrator monitoring duties
5. HEARTBEAT.md oversight responsibilities

**Failure Points to Monitor:**
- Specialist does Phase 2 themselves instead of handing off
- Scout gets spawned for Phase 1 work (wrong direction)
- Results don't flow back to specialists
- Handoff doesn't happen despite ≥20/30 score
- Scout doesn't use appropriate domain-specific research skill