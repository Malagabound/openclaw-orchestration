#!/bin/bash
# Ralph Local - Self-Healing Supervisor
# Usage: ./agent-os/ralph-local.sh <spec-name> [max_iterations]
#
# This supervisor wraps ralph-core.sh and adds self-healing:
# - Detects failures via structured output
# - Spawns diagnosis agent to identify root cause
# - Applies targeted fixes
# - Retries automatically
# - Only notifies you after 3 failed fix attempts

set -e

# Allow nested Claude invocations when running inside Claude Code
unset CLAUDECODE 2>/dev/null || true

# =============================================================================
# CONFIGURATION
# =============================================================================

MAX_FIX_ATTEMPTS=3          # Max diagnosis+fix cycles per blocking story
DIAGNOSIS_TIMEOUT=300       # 5 minutes for diagnosis agent
FIX_TIMEOUT=600             # 10 minutes for fix agent
IVV_TIMEOUT=900             # 15 minutes for IVV audit agent
IVV_FIX_TIMEOUT=600         # 10 minutes for IVV fix agent
MAX_IVV_ITERATIONS=5        # Max IVV audit+fix cycles before escalating

# macOS doesn't have GNU timeout by default, so we detect and adapt
TIMEOUT_CMD=""
if command -v gtimeout &> /dev/null; then
  TIMEOUT_CMD="gtimeout"
elif command -v timeout &> /dev/null; then
  TIMEOUT_CMD="timeout"
fi

# Portable timeout function (works on macOS without coreutils)
run_with_timeout() {
  local timeout_seconds="$1"
  shift
  local command_to_run="$@"

  if [ -n "$TIMEOUT_CMD" ]; then
    $TIMEOUT_CMD --foreground --signal=TERM --kill-after=30s "${timeout_seconds}s" bash -c "$command_to_run"
    return $?
  else
    bash -c "$command_to_run" &
    local cmd_pid=$!
    local elapsed=0
    while [ $elapsed -lt $timeout_seconds ]; do
      if ! kill -0 $cmd_pid 2>/dev/null; then
        wait $cmd_pid
        return $?
      fi
      sleep 1
      elapsed=$((elapsed + 1))
    done
    echo "" >&2
    echo "Timeout: Process exceeded ${timeout_seconds}s limit" >&2
    kill -TERM $cmd_pid 2>/dev/null
    sleep 2
    kill -KILL $cmd_pid 2>/dev/null
    wait $cmd_pid 2>/dev/null
    return 124
  fi
}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# =============================================================================
# ARGUMENT HANDLING
# =============================================================================

if [ -z "$1" ]; then
  echo "Usage: ./agent-os/ralph-local.sh <spec-name> [max_iterations]"
  echo "Example: ./agent-os/ralph-local.sh 2026-01-16-review-notes-system 30"
  echo ""
  echo "This self-healing version:"
  echo "  - Works on your current branch (no worktree)"
  echo "  - Automatically diagnoses and fixes failures"
  echo "  - Only notifies you when it truly can't proceed"
  exit 1
fi

SPEC_NAME="$1"
MAX_ITERATIONS=${2:-30}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Normalize spec name: strip leading "agent-os/specs/" if present
SPEC_NAME="${SPEC_NAME#agent-os/specs/}"

SPEC_DIR="$PROJECT_ROOT/agent-os/specs/$SPEC_NAME"
FAILURE_FILE="$SPEC_DIR/ralph-failure.json"
FIX_LOG="$SPEC_DIR/ralph-fix-log.md"
PRD_FILE="$SPEC_DIR/prd.json"

# Validate spec exists before starting
if [ ! -d "$SPEC_DIR" ]; then
  echo -e "${RED}Error: Spec folder not found: $SPEC_DIR${NC}"
  exit 1
fi

if [ ! -f "$PRD_FILE" ]; then
  echo -e "${RED}Error: prd.json not found in spec folder${NC}"
  exit 1
fi

# Track fix attempts for current blocking story
CURRENT_BLOCKING_STORY=""
FIX_ATTEMPTS=0

# =============================================================================
# EMAIL NOTIFICATION
# =============================================================================

# Load Resend API key from .env
load_resend_key() {
  if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -E '^RESEND_API_KEY=' "$PROJECT_ROOT/.env" | xargs)
  fi
}

send_email() {
  local subject="$1"
  local html_body="$2"

  load_resend_key

  if [ -z "$RESEND_API_KEY" ]; then
    echo -e "${YELLOW}Warning: RESEND_API_KEY not found, skipping email notification${NC}"
    return 1
  fi

  curl -s -X POST 'https://api.resend.com/emails' \
    -H "Authorization: Bearer $RESEND_API_KEY" \
    -H 'Content-Type: application/json' \
    -d "{
      \"from\": \"Optimizer OS <noreply@optimizeos.ai>\",
      \"to\": [\"alan@roccoriley.com\"],
      \"subject\": \"$subject\",
      \"html\": \"$html_body\"
    }" > /dev/null 2>&1
}

notify_human() {
  local title="$1"
  local message="$2"

  # Get failure context if available
  local story_info=""
  local failure_details=""
  if [ -f "$FAILURE_FILE" ]; then
    local story_id=$(jq -r '.story_id // "unknown"' "$FAILURE_FILE" 2>/dev/null)
    local story_title=$(jq -r '.story_title // "unknown"' "$FAILURE_FILE" 2>/dev/null)
    local failure_type=$(jq -r '.failure_type // "unknown"' "$FAILURE_FILE" 2>/dev/null)
    local reason=$(jq -r '.reason // "No reason provided"' "$FAILURE_FILE" 2>/dev/null)
    story_info="<p><strong>Story:</strong> $story_id - $story_title</p>"
    failure_details="<p><strong>Failure Type:</strong> $failure_type</p><p><strong>Reason:</strong> $reason</p>"
  fi

  # Send email
  local subject="🚨 Ralph Needs Help: $SPEC_NAME"
  local html_body="<h2>Ralph Supervisor - Human Intervention Required</h2><p><strong>Spec:</strong> $SPEC_NAME</p>$story_info<p><strong>Message:</strong> $message</p>$failure_details<p>Ralph attempted $MAX_FIX_ATTEMPTS automatic fixes but could not resolve the issue.</p><p>Check the fix log at: <code>agent-os/specs/$SPEC_NAME/ralph-fix-log.md</code></p>"

  send_email "$subject" "$html_body"

  # Terminal output
  echo ""
  echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${RED}║              HUMAN INTERVENTION REQUIRED                      ║${NC}"
  echo -e "${RED}╠═══════════════════════════════════════════════════════════════╣${NC}"
  echo -e "${RED}║${NC}  $message"
  echo -e "${RED}║${NC}"
  echo -e "${RED}║${NC}  Fix log: $FIX_LOG"
  echo -e "${RED}║${NC}  Failure details: $FAILURE_FILE"
  echo -e "${RED}║${NC}  📧 Email sent to alan@roccoriley.com"
  echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
}

notify_success() {
  local message="$1"

  # Send success email
  local subject="✅ Ralph Complete: $SPEC_NAME"
  local html_body="<h2>Ralph Supervisor - Success!</h2><p><strong>Spec:</strong> $SPEC_NAME</p><p>$message</p><p>All stories have been implemented successfully.</p>"

  send_email "$subject" "$html_body"

  echo -e "${GREEN}📧 Success notification sent to alan@roccoriley.com${NC}"
}

# =============================================================================
# DIAGNOSIS AGENT
# =============================================================================

run_diagnosis_agent() {
  local failure_file="$1"
  local output_file="$2"

  echo -e "${CYAN}▶ Running diagnosis agent...${NC}"

  # Read failure context
  local failure_type=$(jq -r '.failure_type' "$failure_file")
  local story_id=$(jq -r '.story_id' "$failure_file")
  local story_title=$(jq -r '.story_title' "$failure_file")
  local reason=$(jq -r '.reason' "$failure_file")

  # Get last Claude output if available (truncate to last 300 lines)
  local last_output=""
  if [ -f "$SPEC_DIR/ralph-last-output.txt" ]; then
    last_output=$(tail -300 "$SPEC_DIR/ralph-last-output.txt")
  fi

  # Get current story details from prd.json
  local story_details=$(jq --arg id "$story_id" '.userStories[] | select(.id == $id)' "$PRD_FILE" 2>/dev/null || echo "{}")

  # Get progress context
  local progress_tail=""
  if [ -f "$SPEC_DIR/progress.txt" ]; then
    progress_tail=$(tail -50 "$SPEC_DIR/progress.txt")
  fi

  # Build diagnosis prompt
  local prompt="You are the Ralph Diagnosis Agent. Ralph failed and you need to identify the root cause and recommend a fix.

FAILURE CONTEXT:
- Failure Type: $failure_type
- Story ID: $story_id
- Story Title: $story_title
- Reason: $reason

STORY DETAILS:
$story_details

RECENT PROGRESS LOG:
$progress_tail

LAST CLAUDE OUTPUT (truncated to last 300 lines):
$last_output

DIAGNOSIS CATEGORIES:
1. STORY_UNCLEAR - Acceptance criteria is ambiguous, missing details, or impossible to implement as written
2. STORY_TOO_LARGE - Story needs to be split into smaller pieces (taking too long, timing out)
3. CODE_BUG - Implementation has a bug that needs fixing (syntax error, logic error, missing import)
4. SPEC_CONFLICT - Story conflicts with existing code or makes assumptions that don't hold
5. MISSING_DEPENDENCY - Story depends on something not yet implemented (table, API, component)
6. INFRA_ISSUE - Browser connection, dev server, or tooling problem (not a code issue)

ANALYSIS STEPS:
1. Read the failure type and reason carefully
2. Look at the last Claude output for specific error messages
3. Check if the story description/criteria is clear and achievable
4. Determine the root cause category

OUTPUT FORMAT (you MUST use this exact XML format):
<diagnosis>
<category>CATEGORY_NAME</category>
<root_cause>Specific description of what went wrong - be precise</root_cause>
<fix_action>EDIT_STORY|EDIT_CODE|SPLIT_STORY|FIX_INFRA|EDIT_SPEC</fix_action>
<fix_details>Specific, actionable instructions for what to change. Include file paths and exact changes needed.</fix_details>
</diagnosis>

IMPORTANT: Your fix_details must be specific enough that another agent can execute the fix without guessing. Include:
- For EDIT_STORY: Which fields to change and what the new values should be
- For EDIT_CODE: Which file(s) to modify and what changes to make
- For SPLIT_STORY: How to break up the story (list the sub-stories)
- For FIX_INFRA: What commands to run or what to restart
- For EDIT_SPEC: What clarifications to add to spec.md"

  # Run diagnosis agent with timeout
  export prompt
  run_with_timeout ${DIAGNOSIS_TIMEOUT} 'echo "$prompt" | claude --print --dangerously-skip-permissions 2>&1' | tee "$output_file"
  return ${PIPESTATUS[0]}
}

# =============================================================================
# FIX AGENTS
# =============================================================================

apply_fix() {
  local diagnosis_output="$1"

  # Extract diagnosis components using grep (more reliable than complex regex)
  local category=$(sed -n 's/.*<category>\(.*\)<\/category>.*/\1/p' "$diagnosis_output" | head -1)
  local root_cause=$(sed -n 's/.*<root_cause>\(.*\)<\/root_cause>.*/\1/p' "$diagnosis_output" | head -1)
  local fix_action=$(sed -n 's/.*<fix_action>\(.*\)<\/fix_action>.*/\1/p' "$diagnosis_output" | head -1)

  # Extract fix_details (may span multiple lines)
  local fix_details=$(sed -n '/<fix_details>/,/<\/fix_details>/p' "$diagnosis_output" | sed 's/<[^>]*>//g' | tr '\n' ' ')

  if [ -z "$fix_action" ]; then
    echo -e "${RED}Could not extract fix_action from diagnosis${NC}"
    return 1
  fi

  echo ""
  echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}║              APPLYING FIX                                     ║${NC}"
  echo -e "${CYAN}╠═══════════════════════════════════════════════════════════════╣${NC}"
  echo -e "${CYAN}║${NC}  Category: ${YELLOW}$category${NC}"
  echo -e "${CYAN}║${NC}  Action: ${YELLOW}$fix_action${NC}"
  echo -e "${CYAN}║${NC}  Root Cause: $root_cause"
  echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"

  # Log the fix attempt
  echo "" >> "$FIX_LOG"
  echo "## Fix Attempt $FIX_ATTEMPTS - $(date)" >> "$FIX_LOG"
  echo "- **Category:** $category" >> "$FIX_LOG"
  echo "- **Root Cause:** $root_cause" >> "$FIX_LOG"
  echo "- **Fix Action:** $fix_action" >> "$FIX_LOG"
  echo "- **Fix Details:** $fix_details" >> "$FIX_LOG"
  echo "" >> "$FIX_LOG"

  case "$fix_action" in
    EDIT_STORY)
      apply_story_edit "$fix_details"
      ;;
    EDIT_CODE)
      apply_code_fix "$fix_details"
      ;;
    SPLIT_STORY)
      apply_story_split "$fix_details"
      ;;
    FIX_INFRA)
      apply_infra_fix "$fix_details"
      ;;
    EDIT_SPEC)
      apply_spec_edit "$fix_details"
      ;;
    *)
      echo -e "${YELLOW}Unknown fix action: $fix_action - will retry Ralph anyway${NC}"
      return 0
      ;;
  esac
}

apply_story_edit() {
  local fix_details="$1"

  echo -e "${CYAN}▶ Spawning story edit agent...${NC}"

  local prompt="You are the Ralph Fix Agent. Your job is to edit a story in prd.json based on the diagnosis.

PROJECT ROOT: $PROJECT_ROOT
SPEC FOLDER: $SPEC_DIR
PRD FILE: $PRD_FILE

FIX INSTRUCTIONS:
$fix_details

RULES:
1. Read the current prd.json first
2. Find the story that needs editing (check the fix instructions for the story ID)
3. Edit ONLY the specific fields mentioned in the fix instructions
4. Common edits: clarify description, update acceptanceCriteria, add implementation notes
5. Use the Edit tool to make precise changes to prd.json
6. Do NOT change story IDs or reorder stories
7. Do NOT mark stories as passes: true (that's Ralph's job)

After making the edit, output exactly:
<fix-result>SUCCESS</fix-result>

If you cannot make the edit, output:
<fix-result>FAILED</fix-result>
<fix-error>Reason why the fix failed</fix-error>"

  export prompt; local result=$(run_with_timeout ${FIX_TIMEOUT} 'echo "$prompt" | claude --print --dangerously-skip-permissions 2>&1')
  echo "$result"

  if echo "$result" | grep -q "<fix-result>SUCCESS</fix-result>"; then
    echo -e "${GREEN}✓ Story edit applied${NC}"
    echo "- **Result:** SUCCESS" >> "$FIX_LOG"
    return 0
  else
    echo -e "${YELLOW}Story edit may not have succeeded${NC}"
    echo "- **Result:** UNCERTAIN" >> "$FIX_LOG"
    return 0  # Continue anyway - Ralph will tell us if it worked
  fi
}

apply_code_fix() {
  local fix_details="$1"

  echo -e "${CYAN}▶ Spawning code fix agent...${NC}"

  local prompt="You are the Ralph Fix Agent. Your job is to fix a bug in the implementation.

PROJECT ROOT: $PROJECT_ROOT
SPEC FOLDER: $SPEC_DIR

FIX INSTRUCTIONS:
$fix_details

RULES:
1. Read the relevant files first to understand the current state
2. Make the MINIMUM change needed to fix the issue
3. After making changes, run: npm run typecheck
4. If typecheck fails, fix those errors too
5. Do NOT refactor or improve code beyond what's needed for the fix
6. Do NOT add new features

After making the fix, output exactly:
<fix-result>SUCCESS</fix-result>

If you cannot make the fix, output:
<fix-result>FAILED</fix-result>
<fix-error>Reason why the fix failed</fix-error>"

  export prompt; local result=$(run_with_timeout ${FIX_TIMEOUT} 'echo "$prompt" | claude --print --dangerously-skip-permissions 2>&1')
  echo "$result"

  if echo "$result" | grep -q "<fix-result>SUCCESS</fix-result>"; then
    echo -e "${GREEN}✓ Code fix applied${NC}"
    echo "- **Result:** SUCCESS" >> "$FIX_LOG"
    return 0
  else
    echo -e "${YELLOW}Code fix may not have succeeded${NC}"
    echo "- **Result:** UNCERTAIN" >> "$FIX_LOG"
    return 0
  fi
}

apply_story_split() {
  local fix_details="$1"

  echo -e "${CYAN}▶ Spawning story split agent...${NC}"

  local prompt="You are the Ralph Fix Agent. Your job is to split a large story into smaller stories.

PROJECT ROOT: $PROJECT_ROOT
SPEC FOLDER: $SPEC_DIR
PRD FILE: $PRD_FILE

FIX INSTRUCTIONS:
$fix_details

RULES:
1. Read the current prd.json first
2. Find the story that needs splitting
3. Create 2-3 smaller stories that together accomplish the original goal
4. For the original story: add a note in description that it was split, set passes: true
5. Insert new stories AFTER the original with IDs using letter suffixes (e.g., US-042a, US-042b)
6. Each new story must have: id, title, description, acceptanceCriteria, type, passes: false
7. Copy the qa_required field from the original story to new stories
8. Use the Edit tool to modify prd.json

After splitting, output exactly:
<fix-result>SUCCESS</fix-result>

If you cannot split the story, output:
<fix-result>FAILED</fix-result>
<fix-error>Reason why the split failed</fix-error>"

  export prompt; local result=$(run_with_timeout ${FIX_TIMEOUT} 'echo "$prompt" | claude --print --dangerously-skip-permissions 2>&1')
  echo "$result"

  if echo "$result" | grep -q "<fix-result>SUCCESS</fix-result>"; then
    echo -e "${GREEN}✓ Story split applied${NC}"
    echo "- **Result:** SUCCESS" >> "$FIX_LOG"
    return 0
  else
    echo -e "${YELLOW}Story split may not have succeeded${NC}"
    echo "- **Result:** UNCERTAIN" >> "$FIX_LOG"
    return 0
  fi
}

apply_infra_fix() {
  local fix_details="$1"

  echo -e "${CYAN}▶ Applying infrastructure fix...${NC}"

  # Handle common infra issues directly without spawning an agent
  local fixed=false

  # Port 3000 conflict
  if echo "$fix_details" | grep -qi "port\|3000"; then
    echo "  Killing processes on port 3000..."
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    sleep 2
    fixed=true
  fi

  # Dev server issues
  if echo "$fix_details" | grep -qi "dev server\|npm run dev"; then
    echo "  Restarting dev server..."
    pkill -f "next dev" 2>/dev/null || true
    sleep 2
    (cd "$PROJECT_ROOT" && npm run dev > /dev/null 2>&1 &)
    sleep 5
    fixed=true
  fi

  # Browser/Playwright issues
  if echo "$fix_details" | grep -qi "browser\|chrome\|playwright"; then
    echo "  Browser issue detected - will retry with fresh browser context"
    # Kill any stale browser processes
    pkill -f "chromium" 2>/dev/null || true
    pkill -f "playwright" 2>/dev/null || true
    sleep 2
    fixed=true
  fi

  if [ "$fixed" = true ]; then
    echo -e "${GREEN}✓ Infrastructure fix applied${NC}"
    echo "- **Result:** SUCCESS (direct fix)" >> "$FIX_LOG"
    return 0
  fi

  # For other infra issues, spawn an agent
  echo "  Spawning infra fix agent for: $fix_details"
  local prompt="You are the Ralph Fix Agent. Fix this infrastructure issue:

PROJECT ROOT: $PROJECT_ROOT

ISSUE:
$fix_details

Use Bash commands to fix the issue. Common fixes:
- Kill processes: lsof -ti:PORT | xargs kill -9
- Restart services: pkill -f PROCESS && sleep 2 && START_COMMAND
- Clear caches: rm -rf .next && npm run build

After fixing, output:
<fix-result>SUCCESS</fix-result>"

  export prompt; local result=$(run_with_timeout ${FIX_TIMEOUT} 'echo "$prompt" | claude --print --dangerously-skip-permissions 2>&1')
  echo "$result"

  echo "- **Result:** ATTEMPTED" >> "$FIX_LOG"
  return 0
}

apply_spec_edit() {
  local fix_details="$1"

  echo -e "${CYAN}▶ Spawning spec edit agent...${NC}"

  local prompt="You are the Ralph Fix Agent. Your job is to edit spec.md to clarify requirements.

PROJECT ROOT: $PROJECT_ROOT
SPEC FOLDER: $SPEC_DIR
SPEC FILE: $SPEC_DIR/spec.md

FIX INSTRUCTIONS:
$fix_details

RULES:
1. Read the current spec.md first
2. Add clarifying details where specified in the fix instructions
3. Do NOT remove existing content, only add or clarify
4. Be specific and technical in your additions
5. Use the Edit tool to make changes

After editing, output:
<fix-result>SUCCESS</fix-result>"

  export prompt; local result=$(run_with_timeout ${FIX_TIMEOUT} 'echo "$prompt" | claude --print --dangerously-skip-permissions 2>&1')
  echo "$result"

  if echo "$result" | grep -q "<fix-result>SUCCESS</fix-result>"; then
    echo -e "${GREEN}✓ Spec edit applied${NC}"
    echo "- **Result:** SUCCESS" >> "$FIX_LOG"
    return 0
  else
    echo -e "${YELLOW}Spec edit may not have succeeded${NC}"
    echo "- **Result:** UNCERTAIN" >> "$FIX_LOG"
    return 0
  fi
}

# =============================================================================
# IVV AUDIT AGENT - Independent Verification & Validation
# =============================================================================

run_ivv_agent() {
  local spec_file="$1"
  local output_file="$2"

  echo -e "${CYAN}▶ Running IVV audit agent...${NC}"

  local prompt="You are the Independent Verification & Validation (IVV) auditor, based on NASA IV&V, IEEE 1012, and DO-178C methodology.

Your job is to verify the implementation matches the spec. You are COMPLETELY INDEPENDENT.

SPEC FILE: $spec_file
PROJECT ROOT: $PROJECT_ROOT

METHODOLOGY:
1. Read the spec at $spec_file to understand ALL requirements
2. Build a Requirements Verification Traceability Matrix (RVTM) - list every testable requirement
3. For each requirement, verify the implementation by reading the actual code files
4. Run any available tests (pytest, npm test, etc.) to validate behavior
5. Check that each requirement is properly implemented

CRITICAL RULES:
- You are INDEPENDENT - do NOT read QA reports, progress files, implementation logs, or prd.json
- Verify by reading actual source code and running actual tests
- Be thorough - check every requirement in the spec
- A requirement is CERTIFIED only if you can point to specific code that implements it
- A requirement is NOT_CERTIFIED if implementation is missing, incomplete, or incorrect

OUTPUT FORMAT (MANDATORY):
For each requirement, output:

<requirement id=\"REQ-N\">
<description>What the spec requires</description>
<status>CERTIFIED|NOT_CERTIFIED</status>
<evidence>What you found in the code/tests</evidence>
<fix_needed>Description of what needs to be fixed (only if NOT_CERTIFIED)</fix_needed>
</requirement>

At the end, output EXACTLY one of:

<ivv-result>ALL_CERTIFIED</ivv-result>

or

<ivv-result>NOT_CERTIFIED</ivv-result>
<ivv-summary>
Concise list of what needs to be fixed, with specific file paths and required changes.
</ivv-summary>

IMPORTANT: Output ALL_CERTIFIED only if EVERY requirement passes. Even one failure means NOT_CERTIFIED."

  export prompt
  run_with_timeout ${IVV_TIMEOUT} 'echo "$prompt" | claude --print --dangerously-skip-permissions 2>&1' | tee "$output_file"
  return ${PIPESTATUS[0]}
}

apply_ivv_fixes() {
  local ivv_output_file="$1"

  echo -e "${CYAN}▶ Spawning IVV fix agent...${NC}"

  # Extract the NOT_CERTIFIED requirements and summary
  local not_certified=$(grep -B 3 -A 10 "NOT_CERTIFIED" "$ivv_output_file")
  local summary=$(sed -n '/<ivv-summary>/,/<\/ivv-summary>/p' "$ivv_output_file" | sed 's/<[^>]*>//g')

  local prompt="You are the IVV Fix Agent. The IVV auditor found issues that must be fixed for the project to pass certification.

PROJECT ROOT: $PROJECT_ROOT
SPEC FILE: $SPEC_DIR/spec.md

IVV FINDINGS (NOT_CERTIFIED requirements):
$not_certified

IVV SUMMARY OF REQUIRED FIXES:
$summary

YOUR TASK:
1. Read the spec to understand what was expected
2. Read the relevant implementation files
3. Make the MINIMUM changes needed to satisfy each NOT_CERTIFIED requirement
4. Run tests after making changes to verify your fixes (pytest, npm test, etc.)
5. Do NOT refactor or improve code beyond what's needed for certification

RULES:
- Fix ONLY the issues identified by IVV - nothing more
- Do NOT add features, refactor, or make improvements
- Do NOT modify the spec or prd.json
- Run available tests after fixes to confirm they pass

After making fixes, output exactly:
<fix-result>SUCCESS</fix-result>
<fix-summary>Brief description of what was fixed</fix-summary>

If you cannot fix all issues, output:
<fix-result>PARTIAL</fix-result>
<fix-summary>What was fixed and what could not be fixed</fix-summary>"

  export prompt
  local result=$(run_with_timeout ${IVV_FIX_TIMEOUT} 'echo "$prompt" | claude --print --dangerously-skip-permissions 2>&1')
  echo "$result"

  if echo "$result" | grep -q "<fix-result>SUCCESS</fix-result>"; then
    local fix_summary=$(echo "$result" | sed -n '/<fix-summary>/,/<\/fix-summary>/p' | sed 's/<[^>]*>//g' | tr '\n' ' ')
    echo -e "${GREEN}✓ IVV fixes applied successfully${NC}"
    echo "- **IVV Fix Result:** SUCCESS" >> "$FIX_LOG"
    echo "- **Fix Summary:** $fix_summary" >> "$FIX_LOG"
    return 0
  elif echo "$result" | grep -q "<fix-result>PARTIAL</fix-result>"; then
    local fix_summary=$(echo "$result" | sed -n '/<fix-summary>/,/<\/fix-summary>/p' | sed 's/<[^>]*>//g' | tr '\n' ' ')
    echo -e "${YELLOW}⚠ IVV fixes partially applied${NC}"
    echo "- **IVV Fix Result:** PARTIAL" >> "$FIX_LOG"
    echo "- **Fix Summary:** $fix_summary" >> "$FIX_LOG"
    return 0
  else
    echo -e "${RED}IVV fix agent did not produce clear result${NC}"
    echo "- **IVV Fix Result:** UNCERTAIN" >> "$FIX_LOG"
    return 1
  fi
}

# =============================================================================
# MAIN SUPERVISOR LOOP
# =============================================================================

echo ""
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}         ${BOLD}Ralph Local - Self-Healing Supervisor${NC}                 ${CYAN}║${NC}"
echo -e "${CYAN}╠═══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  Spec: ${YELLOW}$SPEC_NAME${NC}"
echo -e "${CYAN}║${NC}  Max iterations per run: $MAX_ITERATIONS"
echo -e "${CYAN}║${NC}  Max fix attempts per story: $MAX_FIX_ATTEMPTS"
echo -e "${CYAN}║${NC}  ${GREEN}Self-healing enabled${NC} - will diagnose and fix failures"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Initialize fix log if it doesn't exist
if [ ! -f "$FIX_LOG" ]; then
  cat > "$FIX_LOG" << EOF
# Ralph Fix Log - $SPEC_NAME

This log tracks diagnosis and fix attempts by the supervisor.

---

EOF
fi

# Main supervisor loop
while true; do
  # Clear previous failure file before each run
  rm -f "$FAILURE_FILE"

  echo ""
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "  ${BOLD}Running Ralph Core...${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
  echo ""

  # Run ralph-core.sh (the actual implementation loop)
  set +e
  "$SCRIPT_DIR/ralph-core.sh" "$SPEC_NAME" "$MAX_ITERATIONS"
  EXIT_CODE=$?
  set -e

  # Check exit code
  if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║       ALL STORIES COMPLETE — Starting IVV Audit              ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # =========================================================================
    # IVV LOOP - Independent Verification & Validation
    # Only after IVV certifies 100% is the project truly done.
    # =========================================================================
    SPEC_FILE="$SPEC_DIR/spec.md"

    if [ ! -f "$SPEC_FILE" ]; then
      echo -e "${YELLOW}No spec.md found — skipping IVV audit${NC}"
      notify_success "All stories complete for $SPEC_NAME! (IVV skipped - no spec.md)"
      exit 0
    fi

    echo "" >> "$FIX_LOG"
    echo "---" >> "$FIX_LOG"
    echo "" >> "$FIX_LOG"
    echo "# IVV Audit Phase" >> "$FIX_LOG"
    echo "" >> "$FIX_LOG"

    IVV_ITERATION=0
    IVV_CERTIFIED=false

    while [ $IVV_ITERATION -lt $MAX_IVV_ITERATIONS ]; do
      IVV_ITERATION=$((IVV_ITERATION + 1))

      echo ""
      echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
      echo -e "  ${BOLD}IVV Audit — Iteration $IVV_ITERATION of $MAX_IVV_ITERATIONS${NC}"
      echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
      echo ""

      echo "" >> "$FIX_LOG"
      echo "## IVV Iteration $IVV_ITERATION - $(date)" >> "$FIX_LOG"
      echo "" >> "$FIX_LOG"

      IVV_OUTPUT=$(mktemp)

      if ! run_ivv_agent "$SPEC_FILE" "$IVV_OUTPUT"; then
        echo -e "${RED}IVV agent failed or timed out${NC}"
        echo "- **IVV Status:** Agent failed/timed out" >> "$FIX_LOG"
        rm -f "$IVV_OUTPUT"
        if [ $IVV_ITERATION -ge $MAX_IVV_ITERATIONS ]; then
          break
        fi
        sleep 5
        continue
      fi

      # Check IVV result
      if grep -q "<ivv-result>ALL_CERTIFIED</ivv-result>" "$IVV_OUTPUT" 2>/dev/null; then
        echo ""
        echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║              IVV AUDIT: 100% CERTIFIED                       ║${NC}"
        echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
        echo "- **IVV Status:** ALL CERTIFIED ✓" >> "$FIX_LOG"
        IVV_CERTIFIED=true
        rm -f "$IVV_OUTPUT"
        break
      fi

      # IVV found issues — apply fixes
      echo ""
      echo -e "${YELLOW}IVV found issues — applying fixes (iteration $IVV_ITERATION)...${NC}"
      echo "- **IVV Status:** NOT CERTIFIED — applying fixes" >> "$FIX_LOG"

      if ! apply_ivv_fixes "$IVV_OUTPUT"; then
        echo -e "${RED}IVV fix agent failed${NC}"
        echo "- **Fix Status:** FAILED" >> "$FIX_LOG"
      fi

      rm -f "$IVV_OUTPUT"

      echo ""
      echo -e "${GREEN}Fixes applied. Re-running IVV audit in 5 seconds...${NC}"
      sleep 5
    done

    if [ "$IVV_CERTIFIED" = true ]; then
      echo ""
      echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
      echo -e "${GREEN}║          PROJECT COMPLETE — IVV CERTIFIED                    ║${NC}"
      echo -e "${GREEN}╠═══════════════════════════════════════════════════════════════╣${NC}"
      echo -e "${GREEN}║${NC}  All stories implemented, QA verified, and IVV certified."
      echo -e "${GREEN}║${NC}"
      echo -e "${GREEN}║${NC}  ${BOLD}Ready to commit.${NC} Review changes with: git status"
      echo -e "${GREEN}║${NC}  Commit when ready with: git add -A && git commit"
      echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"

      notify_success "All stories complete AND IVV certified for $SPEC_NAME!"
      exit 0
    else
      echo ""
      echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
      echo -e "${RED}║       IVV AUDIT FAILED — Max iterations reached              ║${NC}"
      echo -e "${RED}╠═══════════════════════════════════════════════════════════════╣${NC}"
      echo -e "${RED}║${NC}  IVV could not certify after $MAX_IVV_ITERATIONS iterations."
      echo -e "${RED}║${NC}  Check the fix log for details."
      echo -e "${RED}║${NC}"
      echo -e "${RED}║${NC}  Fix log: $FIX_LOG"
      echo -e "${RED}║${NC}  📧 Email sent to alan@roccoriley.com"
      echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"

      echo "" >> "$FIX_LOG"
      echo "## IVV BLOCKED — Max Iterations Reached" >> "$FIX_LOG"
      echo "- IVV could not certify after $MAX_IVV_ITERATIONS iterations" >> "$FIX_LOG"
      echo "- Human intervention required" >> "$FIX_LOG"

      notify_human "Ralph Supervisor" "IVV audit could not certify $SPEC_NAME after $MAX_IVV_ITERATIONS iterations"
      exit 1
    fi
  fi

  # Ralph failed - check if we have failure details
  if [ ! -f "$FAILURE_FILE" ]; then
    echo ""
    echo -e "${RED}Ralph failed (exit code $EXIT_CODE) but no failure file found.${NC}"
    echo -e "${RED}This might be a validation error or unexpected crash.${NC}"
    notify_human "Ralph Supervisor" "Ralph failed without failure details (exit $EXIT_CODE)"
    exit 1
  fi

  # Read failure details
  FAILURE_TYPE=$(jq -r '.failure_type' "$FAILURE_FILE")
  BLOCKING_STORY=$(jq -r '.story_id' "$FAILURE_FILE")
  FAILURE_REASON=$(jq -r '.reason' "$FAILURE_FILE")

  echo ""
  echo -e "${YELLOW}╔═══════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${YELLOW}║              RALPH FAILED - ATTEMPTING SELF-HEAL              ║${NC}"
  echo -e "${YELLOW}╠═══════════════════════════════════════════════════════════════╣${NC}"
  echo -e "${YELLOW}║${NC}  Failure Type: ${RED}$FAILURE_TYPE${NC}"
  echo -e "${YELLOW}║${NC}  Blocking Story: $BLOCKING_STORY"
  echo -e "${YELLOW}║${NC}  Reason: $FAILURE_REASON"
  echo -e "${YELLOW}╚═══════════════════════════════════════════════════════════════╝${NC}"

  # Track fix attempts per story
  if [ "$BLOCKING_STORY" != "$CURRENT_BLOCKING_STORY" ]; then
    # New blocking story - reset counter
    CURRENT_BLOCKING_STORY="$BLOCKING_STORY"
    FIX_ATTEMPTS=0
    echo "" >> "$FIX_LOG"
    echo "---" >> "$FIX_LOG"
    echo "" >> "$FIX_LOG"
    echo "# Blocking Story: $BLOCKING_STORY" >> "$FIX_LOG"
    echo "" >> "$FIX_LOG"
  fi

  FIX_ATTEMPTS=$((FIX_ATTEMPTS + 1))

  echo ""
  echo -e "${CYAN}Fix attempt $FIX_ATTEMPTS of $MAX_FIX_ATTEMPTS for story $BLOCKING_STORY${NC}"

  if [ $FIX_ATTEMPTS -gt $MAX_FIX_ATTEMPTS ]; then
    echo ""
    echo -e "${RED}Max fix attempts ($MAX_FIX_ATTEMPTS) reached for story $BLOCKING_STORY${NC}"
    echo "" >> "$FIX_LOG"
    echo "## BLOCKED - Max Attempts Reached" >> "$FIX_LOG"
    echo "- Story $BLOCKING_STORY could not be fixed after $MAX_FIX_ATTEMPTS attempts" >> "$FIX_LOG"
    echo "- Human intervention required" >> "$FIX_LOG"
    echo "" >> "$FIX_LOG"

    notify_human "Ralph Supervisor" "Story $BLOCKING_STORY blocked after $MAX_FIX_ATTEMPTS fix attempts"
    exit 1
  fi

  # Run diagnosis
  DIAGNOSIS_OUTPUT=$(mktemp)
  echo ""
  if ! run_diagnosis_agent "$FAILURE_FILE" "$DIAGNOSIS_OUTPUT"; then
    echo -e "${RED}Diagnosis agent failed or timed out${NC}"
    echo "## Diagnosis Failed" >> "$FIX_LOG"
    echo "- Diagnosis agent timed out or crashed" >> "$FIX_LOG"
    rm -f "$DIAGNOSIS_OUTPUT"
    echo -e "${YELLOW}Will retry Ralph directly...${NC}"
    sleep 3
    continue
  fi

  # Check if diagnosis produced valid output
  if ! grep -q "<diagnosis>" "$DIAGNOSIS_OUTPUT"; then
    echo -e "${RED}Diagnosis agent did not produce valid output${NC}"
    echo "## Diagnosis Invalid" >> "$FIX_LOG"
    echo "- Diagnosis agent output did not contain expected XML format" >> "$FIX_LOG"
    rm -f "$DIAGNOSIS_OUTPUT"
    echo -e "${YELLOW}Will retry Ralph directly...${NC}"
    sleep 3
    continue
  fi

  # Apply the fix
  echo ""
  if ! apply_fix "$DIAGNOSIS_OUTPUT"; then
    echo -e "${YELLOW}Fix application had issues${NC}"
  fi

  rm -f "$DIAGNOSIS_OUTPUT"

  echo ""
  echo -e "${GREEN}Fix attempt complete. Restarting Ralph in 5 seconds...${NC}"
  sleep 5

done
