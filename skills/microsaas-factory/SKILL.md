---
name: microsaas-factory
description: "Build and deploy micro-SaaS products from the ConvertFlow template. Clone, customize, build, and deploy to Vercel. Triggered via Telegram with 'build [name]' or from high-scoring ideas in saas-idea-discovery."
metadata: { "openclaw": { "emoji": "🏭" } }
---

# Micro-SaaS Factory

You build and deploy new micro-SaaS products by cloning the ConvertFlow template, customizing it for a new product, building it, and deploying to Vercel.

## Execution Modes

### Quick Build Mode (default)
Given a product name and description, generate the full product config, then build and deploy.

**Trigger:** User says "build [product-name]: [description]"
**Example:** "build markdown-magic: Convert Markdown to HTML and plain text"

### Build Mode
Given a complete product_config.json, skip config generation and go straight to build.

### Status Mode
List all built products from data/products.json.

**Trigger:** User says "factory status" or "list products"

---

## Build Pipeline

### Step 1: Generate Product Config
Using your intelligence, generate a complete product_config.json following the schema in templates/product_config.example.json. Include:
- Product name, slug, initials, API key prefix
- Hero section content (badge, title, subtitle)
- 4 feature cards with appropriate lucide-react icons
- Free and Pro plan limits and pricing features
- Tool directions, sample input/output, labels
- The core converter TypeScript code (pure functions, no external deps if possible)
- Database direction enum values

**Send config summary to user and wait for "go" to proceed.**

### Step 2: Clone Template
Run the clone script:
```bash
cd /home/node/.openclaw/workspace/skills/microsaas-factory
bash scripts/clone_template.sh [slug]
```

### Step 3: Customize Files
Run the customizer with the config:
```bash
cd /home/node/.openclaw/workspace/skills/microsaas-factory
node scripts/customize.js /home/milad/[slug] '[product_config_json]'
```

### Step 4: Build
```bash
cd /home/node/.openclaw/workspace/skills/microsaas-factory
bash scripts/build_and_fix.sh [slug]
```

If build fails, read the error output and:
1. Identify the failing file and error
2. Fix the TypeScript/import issue
3. Re-run the build (max 3 attempts)

### Step 5: Deploy (requires human approval)
**STOP and ask user:**
> Build successful for [product-name]. Ready to deploy.
> Reuse ConvertFlow API keys? (Clerk, Supabase, Stripe)
> Reply "deploy" to proceed, or provide new keys.

After approval:
```bash
cd /home/node/.openclaw/workspace/skills/microsaas-factory
bash scripts/deploy.sh [slug]
```

### Step 6: Report
Send to Telegram:
```
🏭 Product Deployed!

Name: [name]
URL: [vercel-url]
GitHub: [github-url]

Features:
- [feature 1]
- [feature 2]
- [feature 3]
- [feature 4]

Free: [free-limits]
Pro: $[price]/mo

Status: LIVE
```

Update data/products.json with the new product.

---

## Converter Code Generation Rules

When generating the TypeScript code for src/lib/converter.ts, follow these rules:

1. Export two named functions: `convertForward(input: string): string` and `convertBackward(input: string): string`
2. Export `detectFormat(input: string): "forward" | "backward" | "unknown"`
3. All functions must be pure — no side effects, no async, no external state
4. Handle errors by throwing Error with descriptive messages
5. Prefer zero external dependencies (use built-in string manipulation)
6. If an npm package is absolutely needed (e.g., `marked` for Markdown), include it in the config under `tool.npm_packages`
7. The code must be valid TypeScript that compiles without errors

Example structure:
```typescript
export function convertForward(input: string): string {
  // Convert from format A to format B
  if (!input.trim()) throw new Error("Input is empty");
  // ... conversion logic ...
  return result;
}

export function convertBackward(input: string): string {
  // Convert from format B to format A
  if (!input.trim()) throw new Error("Input is empty");
  // ... conversion logic ...
  return result;
}

export function detectFormat(input: string): "forward" | "backward" | "unknown" {
  // Detect whether input is format A or format B
  // ... detection logic ...
  return "unknown";
}
```

---

## File Modification Reference

The customize.js script modifies these files in the cloned template:

| File | What Changes |
|------|-------------|
| package.json | name field |
| src/lib/utils.ts | APP_NAME default, API key prefix, PLANS constants |
| src/lib/converter.ts | Replaced entirely with generated code |
| src/app/page.tsx | Hero title, subtitle, badge, feature cards |
| src/app/pricing/page.tsx | Plan features, prices, descriptions |
| src/components/landing/hero-converter.tsx | Sample data, labels, directions |
| src/components/ui/navbar.tsx | Logo initials |
| src/app/api/v1/convert/route.ts | Import names, direction handling |
| src/lib/supabase.ts | DbConversion direction type |
| supabase/schema.sql | Direction CHECK constraint |
| .env.local.example | APP_NAME default |

---

## Error Handling

- If clone fails: report error, do not proceed
- If customize fails: report which file failed, attempt to fix
- If build fails: capture errors, attempt auto-fix up to 3 times, then report failure
- If deploy fails: report error, preserve the built project for manual deploy
- Always update products.json with status ("building", "built", "deployed", "failed")

---

## Safety Rules

1. NEVER delete the source template at /home/milad/micro-saas-template/
2. NEVER deploy without explicit user approval
3. NEVER use real payment credentials — always use Stripe test keys
4. ALWAYS wait for "go" or "deploy" confirmation before proceeding
5. ALWAYS report estimated token cost before large operations
