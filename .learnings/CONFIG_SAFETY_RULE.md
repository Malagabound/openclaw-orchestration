# CONFIG SAFETY RULE - MANDATORY

**Date Established:** 2026-02-08
**Context:** I broke OpenClaw config causing complete failure

## IRONCLAD RULE: Config Documentation Required

**BEFORE making ANY OpenClaw config change:**

1. **Read OpenClaw docs first** - Check `/opt/homebrew/lib/node_modules/openclaw/docs/` 
2. **Verify syntax and structure** - Ensure the change follows documented patterns
3. **Understand the impact** - Know what systems will be affected
4. **Test incrementally** - Make one change at a time, not batch changes
5. **Have rollback plan** - Know how to undo if something breaks

## What I Broke (2026-02-08):
- Added bad config changes that caused complete OpenClaw failure
- Made assumptions about config structure without consulting docs
- Tried to enable agent-to-agent messaging incorrectly
- Modified spawn permissions improperly

## Alan's Rule:
> "You MUST verify how the change should work against openclaw docs before you can make a change"

## NEVER AGAIN:
- No config changes without documentation verification
- No assumptions about OpenClaw configuration structure
- No batch config modifications without testing each change

This rule is now permanently embedded and non-negotiable.