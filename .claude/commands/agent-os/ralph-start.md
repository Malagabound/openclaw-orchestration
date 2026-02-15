# Ralph Loop Starter

Generate the bash command to start the Ralph autonomous loop for a spec.

## Step 1: Find Available Specs

List all specs that have prd.json (ready for Ralph):

```bash
# Find specs with prd.json
for dir in agent-os/specs/*/; do
  if [ -f "${dir}prd.json" ]; then
    spec_name=$(basename "$dir")
    stories=$(jq '.userStories | length' "${dir}prd.json" 2>/dev/null || echo "?")
    remaining=$(jq '[.userStories[] | select(.passes != true)] | length' "${dir}prd.json" 2>/dev/null || echo "?")
    echo "  $spec_name ($remaining/$stories remaining)"
  fi
done
```

## Step 2: Determine Target Spec

**If argument provided:** Use it directly as the spec name.

**If no argument:**
- List available specs from Step 1
- Ask user which spec they want to run

## Step 3: Validate Spec

Before generating the command, verify:
1. Spec folder exists: `agent-os/specs/[spec-name]/`
2. prd.json exists in the folder
3. At least one story has `passes: false` or `passes: null`

If validation fails, explain what's missing.

## Step 4: Output the Command

Generate and display the bash command:

```
## Ralph Command

Paste into your terminal:

\`\`\`bash
./agent-os/ralph-local.sh [spec-name]
\`\`\`

**Spec:** [spec-name]
**Stories:** [X] total, [Y] remaining
**Branch:** [branchName from prd.json]

### With custom max iterations (default is 30):
\`\`\`bash
./agent-os/ralph-local.sh [spec-name] 50
\`\`\`

### What happens next

1. Ralph picks the highest priority story where `passes: false`
2. Implements that story in a fresh Claude instance
3. Runs typecheck + lint + QA verification
4. **If failures occur: diagnoses and self-heals automatically**
5. Repeats until all stories pass or requires human intervention

**Monitor progress:**
- `agent-os/specs/[spec-name]/progress.txt` - Implementation progress
- `agent-os/specs/[spec-name]/ralph-fix-log.md` - Self-healing attempts (if any)
```

## Example Output

If user runs `/ralph-start 2026-01-11-task-status`:

```
## Ralph Command

Paste into your terminal:

\`\`\`bash
./agent-os/ralph-local.sh 2026-01-11-task-status
\`\`\`

**Spec:** 2026-01-11-task-status
**Stories:** 5 total, 5 remaining
**Branch:** task-status

### With custom max iterations (default is 30):
\`\`\`bash
./agent-os/ralph-local.sh 2026-01-11-task-status 50
\`\`\`
```

## If No Specs Ready

If no specs have prd.json:

```
No specs are ready for Ralph execution.

To prepare a spec for Ralph:
1. Run `/plan` to create a new spec
2. Or run `/agent-os/create-stories [spec-name]` to generate prd.json for an existing spec

Available specs without prd.json:
- 2026-01-10-some-feature (has spec.md, needs prd.json)
- 2026-01-09-another-feature (has spec.md, needs prd.json)
```
