# Spec Writing Process

You are creating a comprehensive specification for a new feature.

## PHASE 1: Write Initial Spec

Use the **spec-writer** subagent to create the specification document for this spec:

Provide the spec-writer with:
- The spec folder path (find the current one or the most recent in `agent-os/specs/*/`)
- The requirements from `planning/requirements.md`
- Any visual assets in `planning/visuals/`

The spec-writer will create `spec.md` inside the spec folder.

## PHASE 2: Spec Critic Review Loop (MANDATORY)

After the spec-writer creates `spec.md`, you MUST run the spec-critic review loop. The spec does NOT advance until the critic approves it with zero issues.

### Loop Process:

**2a. Send to spec-critic:**

Use the **spec-critic** subagent to review the spec:

Provide the spec-critic with:
- The spec folder path
- Instruction: "Review `spec.md` for blindspots, ambiguities, and missing explanations."

**2b. Check the result:**

Parse the spec-critic's output for the `<spec-review>` tags:

- If `<status>APPROVED</status>` → The spec passed. Exit the loop, proceed to Phase 3.
- If `<status>CHANGES_REQUIRED</status>` → The spec needs work. Continue to step 2c.

**2c. PM addresses ALL feedback:**

Use the **spec-writer** subagent again to address the critic's feedback:

Provide the spec-writer with:
- The spec folder path
- The FULL list of issues from the spec-critic's output
- Instruction: "The spec-critic found the following issues. You MUST address ALL of them — no issue is too minor to skip. Update `spec.md` to resolve every issue listed."

**2d. Loop back to 2a.**

Send the updated spec back to the spec-critic. Repeat until the critic returns `APPROVED` with zero issues.

### Rules:
- **ALL issues must be addressed.** Do not skip "minor" or "non-blocking" issues. The PM must fix everything.
- **Do not approve the spec yourself.** Only the spec-critic agent can approve it.
- **Track iterations.** Log each round in `progress.txt` with the issue count.
- **No infinite loops.** If the loop has iterated 5+ times, stop and present the remaining issues to the user for manual resolution.

## PHASE 3: Ready for CEO Review

Once the spec-critic returns `APPROVED`, output the following:

```
Your spec.md is ready for CEO review!

✅ Spec document created: `[spec-path]`
✅ Spec critic review: APPROVED (passed after [N] iteration(s))

The spec has been reviewed for blindspots, ambiguities, and missing explanations.
No remaining issues found.

NEXT STEP 👉 CEO reviews and approves the spec, then run `/create-tasks` to generate user stories.
```
