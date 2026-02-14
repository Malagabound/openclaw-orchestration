# TECH-STACK.md - Standard Technology Stack

Reference this document for ALL new development. This is the baseline—deviate only with explicit approval.

---

## Core Framework

| Layer | Technology | Version | Notes |
|-------|------------|---------|-------|
| **Framework** | Next.js | 16.x | App Router, Server Components |
| **Language** | TypeScript | 5.x | Strict mode |
| **Runtime** | Node.js | 20.x | LTS |
| **Package Manager** | npm | - | Use `--legacy-peer-deps` for installs |

---

## Database & Backend

| Layer | Technology | Notes |
|-------|------------|-------|
| **Database** | PostgreSQL | Via Supabase |
| **Backend-as-a-Service** | Supabase | Auth, DB, Storage, Realtime, RLS |
| **ORM/Client** | Supabase JS Client | NOT Prisma, NOT Drizzle |

---

## UI & Styling

| Layer | Technology | Notes |
|-------|------------|-------|
| **Styling** | Tailwind CSS | With CSS variables for theming |
| **Component Library** | shadcn/ui | Copy-paste components, NOT npm package |
| **Icons** | Lucide React | Consistent icon set |
| **Animations** | Framer Motion | For complex animations |
| **Font** | Inter | Via `next/font` |

### UI Component Packages
- `@radix-ui/*` — Primitives (via shadcn)
- `@dnd-kit/*` — Drag and drop
- `recharts` — Charts and graphs
- `@schedule-x/react` — Calendar views (if needed)
- `@tiptap/*` — Rich text editor (if needed)

---

## State & Data Fetching

| Layer | Technology | Notes |
|-------|------------|-------|
| **Server State** | TanStack React Query | Caching, refetching, mutations |
| **Client State** | Zustand | Simple stores when needed |
| **Forms** | React Hook Form + Zod | Validation via resolver |

**⚠️ DO NOT USE:** SWR (redundant with TanStack Query)

---

## Async & Background Jobs

**This is critical. Read carefully.**

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **Upstash QStash** | Job queue, scheduling, retries | ANY async work that must complete reliably |
| **Upstash Redis** | Caching, rate limiting, sessions | Fast ephemeral state, pub/sub |
| **Next.js API Routes** | Worker endpoints | Receive jobs from QStash |

### The Pattern That Works

```
User Action → API Route → QueueService.enqueue*() → QStash
                                                      ↓
                                            POST /api/workers/{job-type}
                                                      ↓
                                            Worker does work (with maxDuration)
                                                      ↓
                                            Returns 200 (success) or 500 (retry)
```

### Worker Route Template

```typescript
// src/app/api/workers/{job-name}/route.ts
import { NextRequest } from 'next/server';
import { verifyQStashSignature } from '@/lib/queue/verify-signature';

export const dynamic = 'force-dynamic';
export const maxDuration = 120; // Set based on job complexity (60-600)

export async function POST(request: NextRequest) {
  // 1. Verify QStash signature
  const { isValid, body, error } = await verifyQStashSignature(request);
  if (!isValid) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    // 2. Do the work (AWAIT everything)
    const result = await doTheWork(body);

    // 3. Return success
    return Response.json({ success: true, result });

  } catch (error) {
    // 4. Return 500 so QStash retries
    console.error('Worker failed:', error);
    return Response.json({ error: error.message }, { status: 500 });
  }
}
```

### Critical Rules

1. **AWAIT everything** — No fire-and-forget promises in API routes
2. **Set `maxDuration`** — Based on expected job time (default 10s is too short)
3. **Return 500 on failure** — QStash will retry automatically
4. **Verify signatures** — Always validate QStash requests
5. **Idempotent workers** — Jobs may run more than once (retries)

### ⚠️ DO NOT USE

- **Netlify Background Functions** — Had reliability issues (jobs not completing)
- **Netlify Async Workloads** — Same issues
- **Fire-and-forget in routes** — `Promise.all(...).then(...)` without await = risky

---

## Infrastructure & Hosting

| Layer | Technology | Notes |
|-------|------------|-------|
| **Hosting** | Netlify | Auto-deploy from `prod` branch |
| **CDN/Edge** | Netlify Edge | Automatic |
| **Email** | Resend | Transactional emails |
| **Error Tracking** | Sentry | With source maps |
| **Analytics** | — | TBD per project |

### Netlify Configuration

```toml
# netlify.toml
[build]
command = "npm run build"
publish = ".next"

[build.environment]
NODE_VERSION = "20"
NPM_FLAGS = "--legacy-peer-deps"
```

---

## AI Integration (Optional)

| Tool | Purpose | Notes |
|------|---------|-------|
| **Anthropic SDK** | Claude API calls | For AI features |
| **Vercel AI SDK** | Streaming, tools | If building chat/agent UI |

Only include if the project has AI features.

---

## Testing

| Layer | Technology | Notes |
|-------|------------|-------|
| **E2E Testing** | Playwright | Primary test framework |
| **Unit Testing** | Vitest | For utility functions |
| **Component Testing** | Testing Library | With Vitest |

### Playwright Setup

```bash
# Run with MCP for agent control
npx @anthropic/playwright-mcp@latest --isolated
```

---

## Authentication

| Pattern | Implementation |
|---------|----------------|
| **Auth Provider** | Supabase Auth |
| **Session Handling** | Via Supabase client |
| **Protected Routes** | Middleware + RLS |

---

## File Structure

```
src/
├── app/                    # Next.js App Router
│   ├── api/               # API routes
│   │   └── workers/       # QStash worker endpoints
│   ├── (authenticated)/   # Protected routes
│   └── (public)/          # Public routes
├── components/            # React components
│   ├── ui/               # shadcn components
│   └── [feature]/        # Feature-specific
├── lib/                   # Utilities
│   ├── supabase/         # Supabase clients
│   ├── queue/            # QStash client & utilities
│   └── services/         # Business logic
├── hooks/                 # Custom React hooks
├── types/                 # TypeScript types
└── contexts/              # React contexts
```

---

## Environment Variables

Required for all projects:

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# QStash
QSTASH_TOKEN=
QSTASH_CURRENT_SIGNING_KEY=
QSTASH_NEXT_SIGNING_KEY=

# Upstash Redis
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=

# App
NEXT_PUBLIC_APP_URL=
```

---

## Naming Conventions

### Database

#### Tables
| Rule | Example |
|------|---------|
| Main tables = singular | `user`, `skill`, `client` |
| Related tables = prefix_descriptor | `user_role`, `skill_type`, `client_setting` |
| Junction tables = primary_entity_secondary | `user_skill`, `client_firm` |
| All lowercase, snake_case | `client_company`, `tax_return` |

**Junction table rule:** Primary entity first (the entity that "owns" the relationship). When unclear, use alphabetical. When a business term exists (`enrollment`, `assignment`), prefer that.

#### Columns
| Rule | Example |
|------|---------|
| All snake_case | `first_name`, `created_at` |
| Foreign keys = full table name + `_id` | `user_id`, `client_company_id` |
| Booleans = `is_` prefix | `is_active`, `is_deleted` |

#### Required Columns (Every Table)
```sql
id              uuid primary key default gen_random_uuid(),
created_at      timestamptz default now(),
updated_at      timestamptz default now(),
is_active       boolean default true,
is_deleted      boolean default false,
deleted_at      timestamptz  -- nullable, set when is_deleted = true
```

#### Indexes & Constraints (PostgreSQL Standard)
Format: `{table}_{column(s)}_{suffix}`

| Suffix | Use | Example |
|--------|-----|---------|
| `pkey` | Primary key | `user_pkey` |
| `key` | Unique constraint | `user_email_key` |
| `idx` | Regular index | `user_created_at_idx` |
| `fkey` | Foreign key | `user_firm_id_fkey` |
| `check` | Check constraint | `user_age_check` |

**Modifiers:**
- Composite index: columns in order → `user_firm_id_role_id_idx`
- Partial index: add `_partial` → `user_email_idx_partial`
- Index with INCLUDE: add `_includes` → `user_name_idx_includes`

#### Soft Deletes
**No hard deletes.** Always soft delete:
```sql
UPDATE user SET is_deleted = true, deleted_at = now() WHERE id = '...';
```

Query active records:
```sql
SELECT * FROM user WHERE is_deleted = false;
-- or
SELECT * FROM user WHERE is_active = true AND is_deleted = false;
```

### Code

#### Files

| Type | Convention | Example |
|------|------------|---------|
| Components | PascalCase | `UserProfile.tsx`, `LoginPage.tsx` |
| Hooks | camelCase with `use` prefix | `useAuth.ts`, `useBreadcrumb.ts` |
| Utilities/Services | kebab-case | `format-date.ts`, `qstash-client.ts` |
| Types | kebab-case | `database.types.ts`, `approval-workflow.ts` |
| API routes | kebab-case folders | `/api/data-imports/route.ts` |
| Constants | kebab-case | `constants.ts`, `config.ts` |

#### Variables & Functions

| Type | Convention | Example |
|------|------------|---------|
| Variables | camelCase | `userName`, `isLoading` |
| Functions | camelCase | `fetchUserData`, `formatDate` |
| Boolean variables | `is`/`has`/`should` prefix | `isActive`, `hasPermission`, `shouldRefetch` |
| Event handlers | `handle` or `on` prefix | `handleSubmit`, `onButtonClick` |
| Constants | UPPER_SNAKE_CASE | `API_URL`, `MAX_RETRY_COUNT` |

#### Components & Hooks

| Type | Convention | Example |
|------|------------|---------|
| Components | PascalCase | `UserCard`, `DashboardPage` |
| Custom hooks | camelCase with `use` prefix | `useAuth`, `useLocalStorage` |
| HOCs | camelCase with `with` prefix | `withAuth`, `withTheme` |
| Context providers | PascalCase with `Provider` suffix | `ThemeProvider`, `AuthProvider` |

#### Types & Interfaces

| Type | Convention | Example |
|------|------------|---------|
| Types | PascalCase | `User`, `ClientCompany` |
| Interfaces | PascalCase (no `I` prefix) | `UserProps`, `ApiResponse` |
| Props types | PascalCase with `Props` suffix | `UserCardProps`, `ButtonProps` |
| Enums | PascalCase name, UPPER_SNAKE_CASE values | `enum Status { ACTIVE, PENDING }` |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-03 | QStash over Netlify Async | Netlify async had reliability issues |
| 2026-02-03 | TanStack Query only (no SWR) | Avoid redundant data fetching libs |
| 2026-02-03 | Supabase client (no ORM) | Direct access, RLS support |

---

*Last updated: 2026-02-03*
