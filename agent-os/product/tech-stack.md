# OptimizeOS Tech Stack

## Overview

OptimizeOS is built on a modern, TypeScript-first stack optimized for rapid development, type safety, and scalability. This document serves as the authoritative reference for all technology choices.

---

## Core Framework

### Next.js 14+
- **Version**: 14.x with App Router
- **Purpose**: Full-stack React framework
- **Key Features Used**:
  - App Router for file-based routing
  - Server Components for performance
  - API Routes for backend endpoints
  - Server Actions where appropriate
  - Middleware for auth and routing logic

**Why Next.js**: Industry-leading React framework with excellent developer experience, built-in optimization, and seamless full-stack capabilities.

---

## Database & Backend

### Supabase PostgreSQL
- **Purpose**: Primary database and backend services
- **Key Features Used**:
  - PostgreSQL database
  - Row Level Security (RLS) for multi-tenant data isolation
  - Real-time subscriptions (where needed)
  - Storage for file uploads
  - Edge Functions (if needed)

**Why Supabase**: Managed PostgreSQL with built-in auth, real-time, and storage. RLS provides robust multi-tenant security at the database level.

### Database Access Pattern
- **MCP Integration**: Supabase MCP for Claude Code operations
- **Project ID**: `aegfixqzothurtzmcile`
- **Client Library**: `@supabase/supabase-js`

---

## Authentication

### NextAuth.js (Auth.js)
- **Purpose**: Authentication and session management
- **Configuration**:
  - Credential-based authentication
  - JWT session strategy
  - Custom session callbacks for user/firm context
  - Role-based access control integration

**Why NextAuth**: Flexible, well-maintained auth solution with excellent Next.js integration and support for various providers.

---

## UI & Styling

### Tailwind CSS
- **Purpose**: Utility-first CSS framework
- **Configuration**:
  - Custom design tokens (colors, spacing, typography)
  - Dark mode support (class-based)
  - Responsive design utilities

### shadcn/ui
- **Purpose**: Component library
- **Key Characteristics**:
  - Copy-paste components (not npm dependency)
  - Built on Radix UI primitives
  - Fully customizable
  - Accessible by default
- **Location**: `src/components/ui/`

**Why shadcn/ui**: Provides high-quality, accessible components that we own and can customize. No vendor lock-in.

### Component Standards
- All UI elements use shadcn/ui components
- **Never** use native HTML inputs, buttons, selects
- Import from `@/components/ui/*`

---

## Type Safety & Validation

### TypeScript
- **Purpose**: Static type checking
- **Configuration**: Strict mode enabled
- **Coverage**: 100% TypeScript (no .js files in src/)

### Zod
- **Purpose**: Runtime validation and schema definition
- **Usage**:
  - API request/response validation
  - Form validation
  - Database query result validation
  - Type inference from schemas

**Why Zod**: TypeScript-first schema validation that provides both compile-time types and runtime validation.

---

## Development Tools

### Package Manager
- **npm**: Standard package manager

### Code Quality
- **ESLint**: Linting with Next.js recommended config
- **Prettier**: Code formatting (if configured)
- **TypeScript**: Type checking via `npm run typecheck`

### Testing
- **Playwright**: End-to-end and integration testing
- **Test Command**: `npm run test`

### Development Server
- **Command**: `npm run dev`
- **Port**: 3000 (default) or as configured

---

## Project Structure

```
/
├── src/
│   ├── app/              # Next.js App Router pages
│   ├── components/
│   │   ├── ui/           # shadcn/ui components
│   │   └── [feature]/    # Feature-specific components
│   ├── lib/              # Utilities, helpers, configurations
│   ├── hooks/            # Custom React hooks
│   ├── types/            # TypeScript type definitions
│   └── styles/           # Global styles
├── public/               # Static assets
├── docs/                 # Production documentation
├── scripts/              # Build and utility scripts
├── agent-os/             # AI agent configuration
│   └── product/          # Product documentation
└── .claude/              # Claude Code configuration
    └── docs/             # Development documentation
```

---

## Deployment

### Netlify
- **Purpose**: Hosting and deployment
- **Configuration**: `netlify.toml`
- **Branch Deploys**:
  - `prod` branch → Production
  - Feature branches → Preview deploys

---

## Key Dependencies

| Package | Purpose | Version Policy |
|---------|---------|----------------|
| `next` | Framework | Latest 14.x |
| `react` | UI Library | Latest 18.x |
| `@supabase/supabase-js` | Database client | Latest |
| `next-auth` | Authentication | Latest v4.x |
| `zod` | Validation | Latest |
| `tailwindcss` | Styling | Latest 3.x |
| `@radix-ui/*` | UI primitives | As needed by shadcn |

---

## Environment Variables

Required environment variables (see `.env.example` if available):

```bash
# Database
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Authentication
NEXTAUTH_URL=
NEXTAUTH_SECRET=

# Additional as needed
```

---

## Security Considerations

1. **Row Level Security**: All database tables use RLS for tenant isolation
2. **Authentication**: All API routes protected by NextAuth middleware
3. **Input Validation**: All inputs validated with Zod before processing
4. **Environment Variables**: Sensitive data never committed to repo

---

## Performance Considerations

1. **Server Components**: Default to Server Components for initial render
2. **Client Components**: Only for interactive elements
3. **Data Fetching**: Prefer server-side data fetching
4. **Caching**: Leverage Next.js built-in caching strategies

---

## Conventions

### Naming
- **Files**: kebab-case (`client-intake.tsx`)
- **Components**: PascalCase (`ClientIntake`)
- **Functions**: camelCase (`getClientById`)
- **Constants**: SCREAMING_SNAKE_CASE (`MAX_RETRY_COUNT`)

### Imports
- Use `@/` path alias for src imports
- Group imports: external → internal → relative

### Components
- One component per file (unless tightly coupled)
- Co-locate component-specific hooks and utilities
- Export components as named exports

---

## Future Tech Considerations

Reserved for future evaluation:

- **AI/ML**: OpenAI API, Anthropic Claude API for intelligent features
- **Payments**: Stripe for subscription billing
- **Email**: SendGrid, Resend, or Postmark for transactional email
- **Search**: Full-text search enhancement (Supabase or dedicated service)
- **Analytics**: Product analytics platform TBD
