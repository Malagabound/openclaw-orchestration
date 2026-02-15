# User Stories Creation Process

You are creating prd.json with user stories from a given spec for Ralph autonomous execution.

## PHASE 1: Get and read the spec.md and/or requirements document(s)

You will need ONE OR BOTH of these files to inform your user stories:
- `agent-os/specs/[this-spec]/spec.md`
- `agent-os/specs/[this-spec]/planning/requirements.md`

IF you don't have ONE OR BOTH of those files in your current conversation context, then ask user to provide direction on where to find them by outputting the following request then wait for user's response:

```
I'll need a spec.md or requirements.md (or both) in order to create user stories.

Please direct me to where I can find those. If you haven't created them yet, you can run /shape-spec or /write-spec.
```

## PHASE 2: Create prd.json

Once you have `spec.md` AND/OR `requirements.md`, use the **spec-to-stories** subagent to convert the spec and requirements into properly sized, dependency-ordered user stories.

Provide the spec-to-stories agent:
- The spec name (folder name, e.g., `2026-01-11-my-feature`)
- It will read from `agent-os/specs/[spec-name]/spec.md`
- It will read from `agent-os/specs/[spec-name]/planning/requirements.md`

The spec-to-stories agent will create:
- `prd.json` - User stories for Ralph execution
- `progress.txt` - Initialized progress log

## PHASE 3: Inform user

Once the spec-to-stories agent has created `prd.json`, output the following:

```
Your user stories are ready!

✅ PRD created: `agent-os/specs/[this-spec]/prd.json`
✅ Progress log initialized: `agent-os/specs/[this-spec]/progress.txt`

**Stories Summary:**
[Include the stories summary table from spec-to-stories output]

NEXT STEPS:
1. Run spec-verifier to validate alignment (optional but recommended)
2. Run Ralph loop: `./agent-os/ralph-local.sh [spec-name]`
```
