# SaaS Technical Considerations

Checklist for evaluating technical feasibility and ongoing burden.

## Pre-Build Assessment

### Infrastructure Needs

| Aspect | Questions |
|--------|-----------|
| **Hosting** | Static site? Server-side? Serverless? |
| **Database** | What data? How much? Growth rate? |
| **File storage** | User uploads? Media? Volume? |
| **Background jobs** | Queues? Scheduled tasks? |
| **Real-time** | WebSockets? Polling? |

**Our preference:** Serverless/edge where possible (Netlify, Vercel, Cloudflare Workers). Minimize ops burden.

### Third-Party Dependencies

| Risk Level | Characteristics |
|------------|-----------------|
| Low | Public APIs, stable providers, fallbacks exist |
| Medium | Required integrations, reasonable SLAs |
| High | Single provider dependency, rate limits, expensive |

**Document dependencies and fallback plans.**

### Security Requirements

| If handling... | You need... |
|----------------|-------------|
| User accounts | Auth system, password security |
| Payment info | PCI compliance (use Stripe/Paddle) |
| Personal data | GDPR considerations |
| Business data | Encryption, access controls |
| Health data | HIPAA (avoid unless necessary) |

**Default:** Use established auth (Clerk, Auth0, Supabase Auth) and payment (Stripe) providers.

---

## Complexity Assessment

### Build Complexity Score

| Score | Description | Example |
|-------|-------------|---------|
| 1 | Weekend project | Landing page with waitlist |
| 2 | 1-2 weeks | Simple CRUD app, basic dashboard |
| 3 | 2-4 weeks | Multi-user app, integrations |
| 4 | 1-2 months | Complex logic, multiple integrations |
| 5 | 2+ months | Enterprise features, scaling concerns |

**Our target:** 1-3 (ship fast, iterate)

### Ongoing Maintenance Score

| Score | Description | Burden |
|-------|-------------|--------|
| 1 | Set and forget | Minimal updates needed |
| 2 | Monthly check-ins | Dependency updates, minor fixes |
| 3 | Weekly attention | Bug fixes, feature requests |
| 4 | Daily ops | Support tickets, monitoring |
| 5 | Full-time job | Complex infra, constant issues |

**Our target:** 1-2 (Alan has a day job)

---

## Technical Red Flags

🚩 **Avoid or carefully consider:**

- Real-time sync requirements (complex, expensive)
- Mobile app needed (doubles effort, app store friction)
- ML/AI as core feature (model maintenance, compute costs)
- Marketplace/two-sided (chicken-and-egg problem)
- Heavy compliance (HIPAA, SOC2, PCI beyond Stripe)
- On-premise deployment requested (support nightmare)
- Complex integrations with unreliable third parties

---

## Technical Green Flags

✅ **Prefer these characteristics:**

- Static or serverless architecture
- Single database, simple schema
- Uses commodity services (auth, payments, email)
- API-driven (clean separation)
- Progressive enhancement possible
- Can launch with feature subset
- Clear scaling path if needed

---

## Our Tech Stack Preferences

*(Reference TECH-STACK.md in workspace root for full details)*

**Frontend:**
- React/Next.js or vanilla for simple
- Tailwind + shadcn/ui

**Backend:**
- Serverless functions
- Supabase for DB + Auth when needed
- Netlify/Vercel for hosting

**Payments:**
- Stripe (always)
- LemonSqueezy alternative for digital goods

**Avoid:**
- Heavy server infrastructure
- Complex deployment pipelines
- Technologies we'd need to learn

---

## Pre-Proposal Technical Check

Before scoring Build Effort, answer:

1. [ ] Can we build MVP in <2 weeks?
2. [ ] Do we understand all required tech?
3. [ ] Are dependencies reliable and affordable?
4. [ ] Is ongoing maintenance minimal?
5. [ ] No technical red flags present?

**If any NO:** Adjust Build Effort score or reconsider the opportunity.
