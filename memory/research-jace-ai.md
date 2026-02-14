# Jace.AI Research Summary

**Date:** 2026-02-07
**Requested by:** Alan

---

## 1. What is Jace.AI?

Jace is a product by **Zeta Labs**, a London-based startup founded by former Meta engineers **Fryderyk Wiatrowski** and **Peter Albert** (Albert was on the core Llama 2 team). Founded August 2023.

**Important: Jace has pivoted.** It launched in mid-2024 as an **autonomous browser agent** (like a more ambitious version of what OpenClaw does with browser automation) but has since **pivoted to being an AI email assistant** — their current product at jace.ai is purely email-focused.

### Original Vision (2024): Autonomous Browser Agent
- An AI that controls a web browser like a human user
- Could book trips, pay invoices, set up job posts, manage recruitment pipelines
- Powered by their proprietary **AWA-1 (Autonomous Web Agent-1)** model
- Demo'd creating an entire company autonomously (math tutoring biz — found first client, made revenue in 2 weeks)

### Current Product (2025-2026): Email Assistant
- Connects to your Gmail/Outlook inbox
- Auto-drafts replies in your voice/style
- Categorizes and prioritizes emails
- Calendar scheduling integration
- "Onboards itself" by learning your writing style and company context
- Review-and-send workflow (human approves AI drafts)

---

## 2. How Does It Work?

### Original Architecture (Browser Agent)
- **Cognitive Architecture:** Multi-component system with separate planner, executor, and verifier
- **AWA-1 Model:** Fine-tuned open-source model using RLAIF (Reinforcement Learning from AI Feedback) + synthetic data
- **LLM Layer:** Standard LLM for chat/planning; AWA-1 for browser execution
- **Cloud Browser:** Tasks run in a cloud browser instance the user can watch
- **Anti-loop:** Reasoning/verification systems to prevent the agent from getting stuck in loops
- **Performance:** 89% task completion (AWA-1) vs 68% (GPT-4o) vs 25% (open-source GPT-4o agent)
- Could handle "hundreds of steps" per task

### Current Architecture (Email)
- Connects via OAuth to email providers
- Learns writing style from email history (1-3 years depending on plan)
- Auto-generates draft replies
- Custom instructions for tone/behavior tuning
- MCP integrations (Pro plan)

---

## 3. Pricing (Current Email Product)

| Plan | Price | Key Features |
|------|-------|--------------|
| **Plus** | $20/mo (annual) / $25/mo | 2 inboxes, 1yr email history, 10 drafts/day, 80 chat msgs/day |
| **Pro** | $40/mo (annual) / $50/mo | 8 inboxes, 3yr history, 30 drafts/day, 240 chat msgs/day, custom MCPs |
| **Enterprise** | Custom | White-glove setup, usage-based, dedicated AM |

- 7-day free trial on both plans
- 30-day money-back guarantee
- Overage capped at $50/mo (no surprise charges)
- Positions itself as replacing ~$93/mo in separate tools for $25/mo

---

## 4. Value Proposition

**Original (browser agent):** "A universal UI for everything — why learn to navigate different interfaces when AI can do it for you?" — Meta-aggregator for web interfaces.

**Current (email):** "Reclaim 90% of your email time" — save ~2 hours/day by having AI draft replies in your voice. Replace Superhuman + SaneBox + other email tools with one product.

Key selling points:
- Zero training required — learns your style automatically
- Review-first workflow (human stays in control)
- Consolidates multiple email productivity tools
- Custom instructions for fine-tuning behavior

---

## 5. Lessons for Alan & George

### What They Got Right (Worth Adopting)
1. **Review-first workflow** — AI drafts, human approves. George already does this with email via Maton, but could be more systematic.
2. **Style learning** — Jace analyzes your past emails to match your voice. George could study Alan's sent emails to better match his tone.
3. **Auto-categorization** — Inbox triage is huge. George already does some of this but could be more aggressive.
4. **Custom instructions** — Allowing the human to fine-tune AI behavior with specific rules. George has SOUL.md/AGENTS.md for this — already ahead.

### What George Already Does Better
- **Browser automation** — OpenClaw already has browser control. Jace *abandoned* this approach (likely too hard to make reliable at scale).
- **Multi-channel** — George works across Telegram, email, calendar, Drive, QuickBooks, etc. Jace is email-only.
- **Deep personalization** — SOUL.md, MEMORY.md, daily notes = far deeper context than Jace's style-matching.
- **Task execution** — George can actually *do* things (update spreadsheets, manage QB, research). Jace just drafts emails.

### Ideas to Steal
1. **Batch email processing** — Jace has a "batch process" workflow for email. George could adopt a daily "email sweep" where he processes all inbox items in one batch, categorizes, drafts replies, and presents a summary.
2. **Email thread summarization** — Summarize long threads into actionable bullets before Alan needs to read them.
3. **Follow-up tracking** — Flag emails where Alan is waiting for a reply and surface them proactively.
4. **Calendar-from-email** — Auto-detect scheduling requests in emails and propose calendar events.
5. **Overage cap model** — If George ever becomes a product, the "keep working + gentle overage cap" is a nice UX.

### The Pivot is Telling
Jace pivoted from browser automation to email because:
- Browser automation is **really hard** to make reliable at scale
- Email is a **narrower, more controllable** problem
- The market for "email assistant" is massive and proven
- George has an advantage here: he doesn't need to be a product at scale, he just needs to work for Alan. So the browser automation approach (which Jace abandoned) is still viable for a single-user setup.

---

## 6. Interesting Features & Patterns

- **MCP integrations** on Pro plan — they're embracing the MCP ecosystem for extensibility
- **Superwhisper integration** mentioned by a user — voice-to-email via dictation
- **Jace vs Lindy comparison** on their blog — positions as "inbox agent" (works on top of email) vs "prompt-driven assistant"
- **"Decision-ready drafts"** concept — not just drafting replies but providing context + risk flags + follow-up tracking
- **Weekly inbox cleanup routine** — structured 25-min Friday ritual they recommend

---

## 7. Company Details

- **Founded:** August 2023 (London)
- **Founders:** Fryderyk Wiatrowski, Peter Albert (both ex-Meta, Albert on Llama 2 core team)
- **Funding:** $2.9M pre-seed (June 2024), led by Daniel Gross (ex-YC AI head) & Nat Friedman (ex-GitHub CEO)
- **Notable angels:** Mati Staniszewski (ElevenLabs founder), Shawn Wang (swyx)
- **Website:** jace.ai (redirects from zetalabs.ai)
- **Twitter:** @ZetaLabsAI

---

## TL;DR

Jace started as an ambitious autonomous browser agent but pivoted to an AI email assistant. Their current product auto-drafts replies in your voice for $20-40/mo. The pivot validates that browser automation at scale is hard — but George already has this working for a single user via OpenClaw. The main takeaways for the Alan/George model: adopt batch email processing, follow-up tracking, and email thread summarization as systematic workflows. George is already more capable than Jace in almost every dimension — he just needs to be more structured about email specifically.
