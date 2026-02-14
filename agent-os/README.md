# Agent OS - Autonomous Development Workflow

Agent OS is a structured workflow for planning and implementing development work using specialized AI agents.

## Quick Start

### Planning Phase

```bash
# Start the planning workflow
/plan
```

This invokes the sequential planning agents:
1. `spec-initializer` → Creates spec folder
2. `spec-shaper` → Gathers requirements via Q&A
3. `spec-writer` → Creates spec.md
4. `spec-to-stories` → Creates prd.json with user stories
5. `spec-verifier` → Validates alignment

### Implementation Phase

Choose your execution model based on the number of stories:

| Stories | Recommended Model | Command |
|---------|------------------|---------|
| < 10 | In-Context Orchestration | `/ralph-orchestrate <spec-name>` |
| 10+ | External Script | `./agent-os/ralph-local.sh <spec-name>` |

---

## Execution Models

### Model A: External Script (`ralph-local.sh`)

**Best for:** Long story lists (10+), background execution, overnight runs

**How it works:**
- Bash script spawns separate Claude Code instances
- Each story gets fresh context (no context limits)
- QA verification via separate Claude for UI stories
- Commits only at the end

**Usage:**
```bash
./agent-os/ralph-local.sh <spec-name> [max_iterations]

# Example
./agent-os/ralph-local.sh 2026-01-16-review-notes-system 30
```

**Features:**
- ✅ Works on current branch (no worktree)
- ✅ Commits only at the end
- ✅ QA verification for UI stories
- ✅ Progress monitoring with spinner
- ✅ Stuck detection (aborts after 3 no-progress iterations)
- ✅ Promotes learnings to patterns.md on completion

---

### Model B: In-Context Orchestration (`/ralph-orchestrate`)

**Best for:** Shorter lists (<10), real-time visibility, ability to intervene

**How it works:**
- You stay in current Claude Code conversation
- Claude acts as orchestrator
- Spawns `implementer` sub-agents via Task tool
- Spawns `qa-verifier` sub-agents for UI stories
- You can intervene between any story

**Usage:**
```
/ralph-orchestrate <spec-name>

# Example
/ralph-orchestrate 2026-01-16-review-notes-system
```

**Features:**
- ✅ Real-time progress in conversation
- ✅ Can pause/intervene between stories
- ✅ Sub-agents share parent context
- ✅ QA verification for UI stories
- ⚠️ Limited by conversation context window

---

## Comparison

| Aspect | ralph-local.sh | /ralph-orchestrate |
|--------|----------------|-------------------|
| Execution location | External terminal | In conversation |
| Claude instances | Fresh per story | Sub-agents |
| Context | Isolated | Shared with parent |
| User intervention | Kill script | Between any story |
| Visibility | Terminal output | Real-time in chat |
| Context limits | None | Conversation window |
| Best for | 10+ stories | < 10 stories |

---

## QA Verification

Both models automatically run QA verification for UI stories:

**Story types requiring QA:**
- `UI Component`
- `Page Integration`
- `UI`
- `Page`
- `Frontend`

**Story types skipping QA:**
- `Schema`
- `Types`
- `Server Action`
- `Email`

The QA verifier:
1. Uses Claude in Chrome for browser testing
2. Navigates to the relevant page
3. Tests acceptance criteria
4. Returns PASS or FAIL
5. On FAIL: reverts `passes: false`, logs failure, retries

---

## Directory Structure

```
agent-os/
├── specs/                    # All spec folders
│   └── YYYY-MM-DD-spec-name/
│       ├── planning/
│       │   ├── raw-idea.md
│       │   ├── requirements.md
│       │   └── visuals/
│       ├── spec.md           # Technical specification
│       ├── prd.json          # User stories for Ralph
│       ├── progress.txt      # Implementation progress
│       └── verification/
│           └── spec-verification.md
├── ralph.sh                  # Original Ralph (uses worktrees)
├── ralph-local.sh            # Ralph Local (current branch, commit at end)
├── prompt.md                 # Implementer prompt template
└── README.md                 # This file
```

---

## Workflow Commands

| Command | Description |
|---------|-------------|
| `/plan` | Start full planning workflow |
| `/ralph-orchestrate <spec>` | In-context implementation |
| `./agent-os/ralph-local.sh <spec>` | External script implementation |
| `/agent-os/shape-spec` | Just gather requirements |
| `/agent-os/write-spec` | Just write specification |
| `/agent-os/create-stories` | Just create prd.json |

---

## Troubleshooting

### Stories not progressing

Both models detect "stuck" scenarios:
- ralph-local.sh: Aborts after 3 iterations with no progress
- /ralph-orchestrate: Asks for user guidance after 3 retries

### QA verification keeps failing

1. Check if dev server is running
2. Check for console errors in browser
3. Verify test credentials are correct
4. Review the failure reason in progress.txt

### Context window limits (in-context only)

If conversation gets too long:
1. Progress is saved to progress.txt
2. Start new conversation
3. Run `/ralph-orchestrate <spec>` again
4. Will resume from last completed story
