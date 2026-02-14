# Spec Template

Use this template for every feature, project, or product before building.

---

# [Feature/Project Name]

**Status:** Draft | In Review | Approved | Building | Complete  
**Author:** George  
**Created:** YYYY-MM-DD  
**Last Updated:** YYYY-MM-DD  

---

## 1. Problem Statement

**What problem are we solving?**

[Clear, concise description of the problem. Why does this need to exist? What pain point are we addressing?]

**Who has this problem?**

[Target user/customer description]

---

## 2. Goals & Success Metrics

**Primary Goal:**
- [What does success look like?]

**How We'll Measure Success:**
- [ ] Metric 1
- [ ] Metric 2

**Non-Goals (Explicitly Out of Scope):**
- [What we are NOT trying to solve with this]

---

## 3. User Stories

Format: "As a [user type], I want to [action] so that [benefit]"

| # | User Story | Priority |
|---|------------|----------|
| 1 | As a [user], I want to [action] so that [benefit] | Must Have |
| 2 | As a [user], I want to [action] so that [benefit] | Should Have |
| 3 | As a [user], I want to [action] so that [benefit] | Nice to Have |

**Priority Key:**
- **Must Have:** Core functionality, required for launch
- **Should Have:** Important but not blocking
- **Nice to Have:** Future enhancement, not in initial scope

---

## 4. Functional Requirements

**Core Features:**

1. **[Feature Name]**
   - Description: [What it does]
   - Inputs: [What user provides]
   - Outputs: [What user gets]
   - Validation: [Any rules/constraints]

2. **[Feature Name]**
   - Description:
   - Inputs:
   - Outputs:
   - Validation:

---

## 5. UI/UX Description

**Key Screens/Views:**

### Screen 1: [Name]
- **Purpose:** [What user accomplishes here]
- **Layout:** [Description of layout — header, main content, sidebar, etc.]
- **Key Elements:**
  - [Element 1]
  - [Element 2]
- **User Flow:** [How user gets here, what they do, where they go next]

### Screen 2: [Name]
- **Purpose:**
- **Layout:**
- **Key Elements:**
- **User Flow:**

**Design Notes:**
- Follow DESIGN-STANDARDS.md
- [Any specific design considerations]

---

## 6. Data Model

**Entities:**

### [Entity Name]
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | uuid | Yes | Primary key |
| created_at | timestamp | Yes | Creation time |
| [field] | [type] | [Yes/No] | [description] |

### [Entity Name]
| Field | Type | Required | Description |
|-------|------|----------|-------------|

**Relationships:**
- [Entity A] has many [Entity B]
- [Entity B] belongs to [Entity A]

---

## 7. Technical Considerations

**Stack:**
- Frontend: Next.js + Tailwind + Shadcn/ui
- Backend: [Supabase / API / etc.]
- Hosting: Netlify

**Integrations:**
- [Any external services/APIs]

**Security:**
- [Authentication requirements]
- [Data privacy considerations]

**Performance:**
- [Any specific performance requirements]

---

## 8. Acceptance Criteria

**Definition of Done:**

- [ ] All "Must Have" user stories implemented
- [ ] Follows DESIGN-STANDARDS.md
- [ ] Works on mobile and desktop
- [ ] No console errors
- [ ] Browser tested by George before presenting
- [ ] Alan has previewed on localhost
- [ ] Alan has approved for production

---

## 9. Out of Scope

**What we are NOT building:**
- [Feature/capability explicitly excluded]
- [Feature/capability explicitly excluded]

**Future Considerations:**
- [Things we might add later but not now]

---

## 10. Open Questions

| Question | Answer | Status |
|----------|--------|--------|
| [Question for Alan] | [Answer] | Open/Resolved |

---

## Approval

- [ ] **Alan reviewed and approved scope** — Date: ___________

---

*Spec approved. Ready to build.*
