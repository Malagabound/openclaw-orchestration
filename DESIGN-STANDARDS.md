# Design Standards

All projects follow these standards. No exceptions.

---

## Color System

### Base Palette
- **Neutral base:** Slate/gray tones (slate-50 through slate-900)
- **Background:** White or slate-50 for cards, slate-100 for page backgrounds
- **Text:** slate-800 for body, slate-600 for secondary, slate-400 for muted

### Accent Colors
- **One primary accent per project** — used sparingly for CTAs and key actions
- **Semantic colors (muted):**
  - Success: emerald-50/emerald-700 (not bright green)
  - Warning: amber-50/amber-700
  - Error: red-50/red-700
  - Info: blue-50/blue-700

### Contrast
- Minimum WCAG AA compliance (4.5:1 for normal text)
- High contrast between text and backgrounds

---

## Typography

### Font
- **Primary:** Inter (clean, modern, excellent readability)
- **Fallback:** system-ui, sans-serif

### Scale (limited)
- **Heading 1:** 2rem (32px) — semibold
- **Heading 2:** 1.5rem (24px) — semibold
- **Heading 3:** 1.25rem (20px) — semibold
- **Body:** 1rem (16px) — regular
- **Small:** 0.875rem (14px) — regular
- **Tiny:** 0.75rem (12px) — for labels/badges only

### Line Height
- Headings: 1.2
- Body: 1.5

---

## Components

### Component Library
- **Shadcn/ui** — our standard component library
- Built on Radix UI (accessible primitives)
- Works with Tailwind CSS
- Customize to match our color system

### Buttons
- **Primary:** Solid background (slate-800), white text
- **Secondary:** White background, slate border, slate text
- **Destructive:** Red-50 background, red-700 text (muted, not alarming)
- **Rounded:** rounded-md (not fully rounded, not square)
- **Padding:** px-4 py-2

### Cards
- White background
- Subtle border (slate-200)
- Subtle shadow (shadow-sm)
- Rounded corners (rounded-lg)
- Generous padding (p-6)

### Form Inputs
- White background
- slate-300 border
- slate-400 focus ring
- Clear labels above inputs
- Error messages below in red-600

---

## Layout

### Spacing
- Use consistent spacing scale (Tailwind default: 4, 6, 8, 12, 16, 24)
- Generous white space between sections
- Don't cram elements together

### Containers
- Max-width containers (max-w-7xl for full layouts)
- Horizontal padding on edges (px-4 md:px-6 lg:px-8)

### Grid
- CSS Grid or Flexbox
- Card-based organization for dashboards
- Clear visual hierarchy

### Responsive
- **Mobile-first** — design for mobile, enhance for desktop
- Breakpoints: sm (640px), md (768px), lg (1024px), xl (1280px)
- Stack elements vertically on mobile

---

## Interactions

### Hover States
- Subtle opacity change (hover:opacity-80) or
- Background color shift (hover:bg-slate-100)
- Never jarring or flashy

### Transitions
- Duration: 150-200ms
- Timing: ease-in-out
- Apply to color, background-color, opacity

### Focus States
- Clear focus rings for accessibility
- ring-2 ring-slate-400 ring-offset-2

### Loading States
- Spinner for quick loads
- Skeleton screens for longer loads
- Never leave users guessing

---

## Icons

- **Lucide React** — our standard icon library (works with Shadcn)
- Consistent stroke width
- Appropriate sizing (16px for inline, 20px for buttons, 24px for standalone)

---

## Dark Mode

- Support dark mode when practical
- Use slate-900 for dark backgrounds
- Invert the color relationships
- Don't force it if it doesn't add value

---

## What to Avoid

- ❌ Bright pastel colors (Easter egg syndrome)
- ❌ Multiple accent colors competing
- ❌ Heavy drop shadows
- ❌ Overly rounded corners (pill buttons except where appropriate)
- ❌ Cluttered layouts with no breathing room
- ❌ Inconsistent spacing
- ❌ Tiny click targets on mobile
- ❌ Low contrast text

---

## Quick Reference

```
Font:        Inter
Colors:      Slate-based neutrals + one accent
Components:  Shadcn/ui
Icons:       Lucide React
Corners:     rounded-md / rounded-lg
Shadows:     shadow-sm (subtle)
Transitions: 150ms ease-in-out
```

---

*Last updated: 2026-02-03*
