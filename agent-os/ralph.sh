#!/bin/bash
# Ralph Wiggum for Claude Code - Autonomous AI agent loop
# Usage: ./agent-os/ralph.sh <spec-name> [max_iterations]
# Example: ./agent-os/ralph.sh 2026-01-11-my-feature 10

set -e

# =============================================================================
# PROGRESS MONITOR - Background process showing real-time status
# =============================================================================

MONITOR_PID=""
CLAUDE_START_TIME=""

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# =============================================================================
# TIMEOUT CONFIGURATION - Prevents indefinite agent hangs
# =============================================================================
CLAUDE_TIMEOUT_SECONDS=3600  # 60 minutes per Claude invocation
QA_TIMEOUT_SECONDS=600      # 10 minutes for QA verification
CHROME_PREFLIGHT_TIMEOUT=30 # 30 seconds for Chrome pre-flight check
PLAYWRIGHT_PREFLIGHT_TIMEOUT=30 # 30 seconds for Playwright pre-flight check
MAX_STORY_RETRIES=2         # Max retries per story after timeout

# =============================================================================
# CROSS-PLATFORM TIMEOUT - Works on both macOS and Linux
# =============================================================================
# macOS doesn't have GNU timeout by default, so we detect and adapt
TIMEOUT_CMD=""
if command -v gtimeout &> /dev/null; then
  # Homebrew coreutils installed (macOS with brew install coreutils)
  TIMEOUT_CMD="gtimeout"
elif command -v timeout &> /dev/null; then
  # Linux or GNU coreutils available
  TIMEOUT_CMD="timeout"
fi

# Fallback timeout function using background process (works on all Unix systems)
run_with_timeout() {
  local timeout_seconds="$1"
  shift
  local command_to_run="$@"

  if [ -n "$TIMEOUT_CMD" ]; then
    # Use GNU timeout if available
    $TIMEOUT_CMD --foreground --signal=TERM --kill-after=30s "${timeout_seconds}s" bash -c "$command_to_run"
    return $?
  else
    # Pure bash timeout fallback for macOS without coreutils
    # Run command in background, kill if it exceeds timeout
    bash -c "$command_to_run" &
    local cmd_pid=$!

    # Monitor process with timeout
    local elapsed=0
    while [ $elapsed -lt $timeout_seconds ]; do
      if ! kill -0 $cmd_pid 2>/dev/null; then
        # Process finished
        wait $cmd_pid
        return $?
      fi
      sleep 1
      elapsed=$((elapsed + 1))
    done

    # Timeout reached - kill the process
    echo "" >&2
    echo "Timeout: Process exceeded ${timeout_seconds}s limit" >&2
    kill -TERM $cmd_pid 2>/dev/null
    sleep 2
    kill -KILL $cmd_pid 2>/dev/null
    wait $cmd_pid 2>/dev/null
    return 124  # Standard timeout exit code
  fi
}

# =============================================================================
# PLAYWRIGHT PRIMARY & CHROME FALLBACK - Resilient QA verification
# =============================================================================
# Layer 1: Playwright pre-flight check before spawning expensive QA agent
#          (Playwright is PRIMARY - uses --isolated flag via MCP config)
# Layer 2: Chrome fallback when Playwright is unreachable

check_playwright_connection() {
  echo -e "${CYAN}▶ Playwright pre-flight check (${PLAYWRIGHT_PREFLIGHT_TIMEOUT}s timeout)...${NC}"
  local result
  result=$(echo "Call mcp__playwright__browser_snapshot. If it succeeds and returns page content, output exactly PLAYWRIGHT_OK. If it fails or errors, output exactly PLAYWRIGHT_FAIL. Output nothing else." | run_with_timeout ${PLAYWRIGHT_PREFLIGHT_TIMEOUT} 'claude --print --dangerously-skip-permissions 2>&1')
  local exit_code=$?

  if [ $exit_code -eq 124 ] || [ $exit_code -eq 137 ]; then
    echo -e "${YELLOW}  Playwright pre-flight timed out${NC}"
    return 1
  fi

  if echo "$result" | grep -q "PLAYWRIGHT_OK"; then
    echo -e "${GREEN}  ✓ Playwright is connected${NC}"
    return 0
  else
    echo -e "${YELLOW}  ✗ Playwright is not available${NC}"
    return 1
  fi
}

check_chrome_connection() {
  echo -e "${CYAN}▶ Chrome pre-flight check (${CHROME_PREFLIGHT_TIMEOUT}s timeout)...${NC}"
  local result
  result=$(echo "Call mcp__claude-in-chrome__tabs_context_mcp with createIfEmpty: true. If it succeeds and returns tab info, output exactly CHROME_OK. If it fails or errors, output exactly CHROME_FAIL. Output nothing else." | run_with_timeout ${CHROME_PREFLIGHT_TIMEOUT} 'claude --print --dangerously-skip-permissions --chrome 2>&1')
  local exit_code=$?

  if [ $exit_code -eq 124 ] || [ $exit_code -eq 137 ]; then
    echo -e "${YELLOW}  Chrome pre-flight timed out${NC}"
    return 1
  fi

  if echo "$result" | grep -q "CHROME_OK"; then
    echo -e "${GREEN}  ✓ Chrome is connected${NC}"
    return 0
  else
    echo -e "${YELLOW}  ✗ Chrome is not available${NC}"
    return 1
  fi
}

# Run QA using Playwright MCP tools (PRIMARY method with --isolated flag)
# Args: $1=working_dir, $2=output_file
# Expects QA_PLAYWRIGHT_PROMPT to be exported
run_qa_with_playwright() {
  local working_dir="$1"
  local output_file="$2"

  echo -e "${CYAN}▶ Starting QA Verifier with Playwright (timeout: $((QA_TIMEOUT_SECONDS/60)) min)...${NC}"
  echo -e "  ${YELLOW}Using Playwright MCP for browser testing (--isolated flag enabled)${NC}"

  (
    cd "$working_dir"
    echo "[QA:STARTED:$(date +%s):PLAYWRIGHT]"
    run_with_timeout ${QA_TIMEOUT_SECONDS} 'echo "$QA_PLAYWRIGHT_PROMPT" | claude --print --dangerously-skip-permissions 2>&1'
    echo "[QA:FINISHED:$(date +%s):PLAYWRIGHT]"
  ) | tee "$output_file"
  return ${PIPESTATUS[0]}
}

# Run QA using Chrome tools (FALLBACK when Playwright is unavailable)
# Args: $1=working_dir, $2=output_file
# Expects QA_PROMPT to be exported
run_qa_with_chrome() {
  local working_dir="$1"
  local output_file="$2"

  echo -e "${CYAN}▶ Starting QA Verifier with Chrome fallback (timeout: $((QA_TIMEOUT_SECONDS/60)) min)...${NC}"
  echo -e "  ${YELLOW}Playwright unavailable — falling back to Chrome${NC}"

  (
    cd "$working_dir"
    echo "[QA:STARTED:$(date +%s):CHROME]"
    run_with_timeout ${QA_TIMEOUT_SECONDS} 'echo "$QA_PROMPT" | claude --print --dangerously-skip-permissions --chrome 2>&1'
    echo "[QA:FINISHED:$(date +%s):CHROME]"
  ) | tee "$output_file"
  return ${PIPESTATUS[0]}
}

# Build a Playwright QA prompt (PRIMARY method)
build_playwright_qa_prompt() {
  local base_prompt="$1"
  cat <<PLAYWRIGHT_HEADER
You are the QA Verifier agent using Playwright for browser testing.
Use mcp__playwright__* tools for all browser automation.

PLAYWRIGHT TOOLS REFERENCE:
| Action         | Playwright Tool                                    |
|----------------|---------------------------------------------------|
| Navigate       | mcp__playwright__browser_navigate(url: "...")      |
| Read page      | mcp__playwright__browser_snapshot                  |
| Click          | mcp__playwright__browser_click(ref: "...")         |
| Type text      | mcp__playwright__browser_type(ref: "...", text: "...") |
| Fill form      | mcp__playwright__browser_fill_form(fields: [...])  |
| Screenshot     | mcp__playwright__browser_take_screenshot(type: "png") |
| Console logs   | mcp__playwright__browser_console_messages(level: "error") |
| Wait           | mcp__playwright__browser_wait_for(text: "...")     |

IMPORTANT: You must log in first. Check .claude/reference/test-credentials.md for credentials.

PLAYWRIGHT_HEADER

  echo "$base_prompt" | sed \
    -e 's/Use Claude in Chrome or Playwright to/Use Playwright to/g' \
    -e 's/Use Claude in Chrome/Use Playwright/g' \
    -e 's/mcp__claude-in-chrome__tabs_context_mcp/mcp__playwright__browser_snapshot/g' \
    -e 's/mcp__claude-in-chrome__tabs_create_mcp/mcp__playwright__browser_navigate/g' \
    -e 's/mcp__claude-in-chrome__navigate/mcp__playwright__browser_navigate/g' \
    -e 's/mcp__claude-in-chrome__read_page/mcp__playwright__browser_snapshot/g' \
    -e 's/mcp__claude-in-chrome__form_input/mcp__playwright__browser_fill_form/g' \
    -e 's/mcp__claude-in-chrome__computer/mcp__playwright__browser_click/g' \
    -e 's/mcp__claude-in-chrome__find/mcp__playwright__browser_snapshot/g' \
    -e 's/mcp__claude-in-chrome__read_console_messages/mcp__playwright__browser_console_messages/g'
}

# Build a Chrome QA prompt (FALLBACK method)
build_chrome_qa_prompt() {
  local base_prompt="$1"
  cat <<CHROME_HEADER
You are the QA Verifier agent using Claude in Chrome for browser testing.
Playwright is NOT available. Use mcp__claude-in-chrome__* tools ONLY.

CHROME TOOLS REFERENCE:
| Action         | Chrome Tool                                        |
|----------------|---------------------------------------------------|
| Get context    | mcp__claude-in-chrome__tabs_context_mcp            |
| Create tab     | mcp__claude-in-chrome__tabs_create_mcp             |
| Navigate       | mcp__claude-in-chrome__navigate(url: "...")        |
| Read page      | mcp__claude-in-chrome__read_page                   |
| Fill form      | mcp__claude-in-chrome__form_input(ref: "...", value: "...") |
| Click          | mcp__claude-in-chrome__computer(action: "left_click", ref: "...") |
| Screenshot     | mcp__claude-in-chrome__computer(action: "screenshot") |
| Console logs   | mcp__claude-in-chrome__read_console_messages       |

NOTE: User is already authenticated in Chrome - no login needed.

CHROME_HEADER

  echo "$base_prompt"
}

# Unified QA runner: tries Playwright first (PRIMARY), falls back to Chrome
# Args: $1=working_dir, $2=qa_prompt, $3=output_file, $4=story_id (for logging)
# Returns: sets QA_OUTPUT_FILE_RESULT and QA_METHOD_USED
run_qa_resilient() {
  local working_dir="$1"
  local qa_prompt="$2"
  local output_file="$3"
  local story_id="$4"

  QA_METHOD_USED="playwright"

  # Layer 1: Playwright pre-flight check (PRIMARY - uses --isolated flag via MCP config)
  if check_playwright_connection; then
    local playwright_prompt
    playwright_prompt=$(build_playwright_qa_prompt "$qa_prompt")
    export QA_PLAYWRIGHT_PROMPT="$playwright_prompt"
    run_qa_with_playwright "$working_dir" "$output_file"
    local qa_exit=$?

    if [ $qa_exit -ne 124 ] && [ $qa_exit -ne 137 ]; then
      return $qa_exit
    fi

    echo -e "${YELLOW}  Playwright QA timed out — falling back to Chrome${NC}"
  fi

  # Layer 2: Chrome fallback
  QA_METHOD_USED="chrome"
  echo "" >> "$PROGRESS_FILE"
  echo "## QA FALLBACK - $story_id" >> "$PROGRESS_FILE"
  echo "- Playwright unavailable or timed out, using Chrome fallback" >> "$PROGRESS_FILE"
  echo "- Time: $(date)" >> "$PROGRESS_FILE"

  if check_chrome_connection; then
    local chrome_prompt
    chrome_prompt=$(build_chrome_qa_prompt "$qa_prompt")
    export QA_PROMPT="$chrome_prompt"
    run_qa_with_chrome "$working_dir" "$output_file"
    return $?
  else
    echo -e "${RED}  Both Playwright and Chrome unavailable — QA cannot proceed${NC}"
    echo "## QA UNAVAILABLE - $story_id" >> "$PROGRESS_FILE"
    echo "- Both Playwright and Chrome are unavailable" >> "$PROGRESS_FILE"
    echo "- Time: $(date)" >> "$PROGRESS_FILE"
    return 1
  fi
}

# Track retries per story (bash 3 compatible - uses temp file instead of associative array)
STORY_RETRIES_FILE=$(mktemp)

get_story_retries() {
  local story_id="$1"
  local count=$(grep "^${story_id}=" "$STORY_RETRIES_FILE" 2>/dev/null | cut -d= -f2)
  echo "${count:-0}"
}

set_story_retries() {
  local story_id="$1"
  local count="$2"
  # Remove existing entry and add new one
  grep -v "^${story_id}=" "$STORY_RETRIES_FILE" > "${STORY_RETRIES_FILE}.tmp" 2>/dev/null || true
  mv "${STORY_RETRIES_FILE}.tmp" "$STORY_RETRIES_FILE"
  echo "${story_id}=${count}" >> "$STORY_RETRIES_FILE"
}

start_progress_monitor() {
  local worktree="$1"
  local prd_file="$2"

  CLAUDE_START_TIME=$(date +%s)

  (
    local spinner=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local spin_idx=0

    while true; do
      # Calculate elapsed time
      local now=$(date +%s)
      local elapsed=$((now - CLAUDE_START_TIME))
      local mins=$((elapsed / 60))
      local secs=$((elapsed % 60))
      local time_str=$(printf "%02d:%02d" $mins $secs)

      # Get current spinner character
      local spin_char="${spinner[$spin_idx]}"
      spin_idx=$(( (spin_idx + 1) % ${#spinner[@]} ))

      # Get current story being worked on
      local current_story=""
      if [ -f "$prd_file" ]; then
        current_story=$(jq -r '[.userStories[] | select(.passes == false)][0].title // "Unknown"' "$prd_file" 2>/dev/null | head -c 50)
      fi

      # Print status line (overwrite previous)
      printf "\r${CYAN}${spin_char}${NC} ${BOLD}Claude working${NC} [${time_str}] │ Story: ${GREEN}%.45s${NC}...    " "$current_story"

      sleep 0.5
    done
  ) &
  MONITOR_PID=$!
}

stop_progress_monitor() {
  if [ -n "$MONITOR_PID" ]; then
    kill $MONITOR_PID 2>/dev/null || true
    wait $MONITOR_PID 2>/dev/null || true
    MONITOR_PID=""
    echo "" # New line after spinner
  fi
}

# Cleanup monitor and temp files on script exit
cleanup_all() {
  stop_progress_monitor
  [ -n "$CLAUDE_OUTPUT_FILE" ] && rm -f "$CLAUDE_OUTPUT_FILE" 2>/dev/null
  [ -n "$STORY_RETRIES_FILE" ] && rm -f "$STORY_RETRIES_FILE" 2>/dev/null
}
trap cleanup_all EXIT INT TERM

# =============================================================================
# ARGUMENT VALIDATION
# =============================================================================

# Validate arguments
if [ -z "$1" ]; then
  echo "Usage: ./agent-os/ralph.sh <spec-name> [max_iterations]"
  echo "Example: ./agent-os/ralph.sh 2026-01-11-my-feature 10"
  exit 1
fi

SPEC_NAME="$1"
MAX_ITERATIONS=${2:-10}

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SPEC_DIR="$SCRIPT_DIR/specs/$SPEC_NAME"
PRD_FILE="$SPEC_DIR/prd.json"
PROGRESS_FILE="$SPEC_DIR/progress.txt"
PROMPT_FILE="$SCRIPT_DIR/prompt.md"

# Worktree configuration
WORKTREES_DIR="$PROJECT_ROOT/.trees"
WORKTREE_PATH="$WORKTREES_DIR/$SPEC_NAME"

# Worktree-relative paths (for validation after Claude runs in worktree)
WORKTREE_PRD_FILE="$WORKTREE_PATH/agent-os/specs/$SPEC_NAME/prd.json"

# Temp file for capturing Claude output
CLAUDE_OUTPUT_FILE=$(mktemp)

# Validate spec folder exists
if [ ! -d "$SPEC_DIR" ]; then
  echo "Error: Spec folder not found: $SPEC_DIR"
  echo ""
  echo "Available specs (including nested):"
  find "$SCRIPT_DIR/specs" -name "prd.json" -type f 2>/dev/null | while read prd_file; do
    spec_path=$(dirname "$prd_file" | sed "s|^$SCRIPT_DIR/specs/||")
    remaining=$(jq '[.userStories[] | select(.passes == false)] | length' "$prd_file" 2>/dev/null || echo "?")
    total=$(jq '.userStories | length' "$prd_file" 2>/dev/null || echo "?")
    echo "  $spec_path ($remaining/$total remaining)"
  done
  echo ""
  echo "Tip: For nested specs, use the full path:"
  echo "  ./agent-os/ralph.sh project-name/phase-2a"
  exit 1
fi

# Validate prd.json exists
if [ ! -f "$PRD_FILE" ]; then
  echo "Error: prd.json not found in spec folder: $PRD_FILE"
  echo "Run spec-to-stories agent first to generate prd.json"
  exit 1
fi

# Validate prompt.md exists
if [ ! -f "$PROMPT_FILE" ]; then
  echo "Error: prompt.md not found: $PROMPT_FILE"
  exit 1
fi

# Get branch name from prd.json
BRANCH_NAME=$(jq -r '.branchName // empty' "$PRD_FILE")
if [ -z "$BRANCH_NAME" ]; then
  echo "Error: No branchName found in prd.json"
  exit 1
fi

# =============================================================================
# WORKTREE FUNCTIONS - Creates isolated working directory for this Ralph instance
# =============================================================================

setup_worktree() {
  echo ""
  echo "Setting up isolated worktree for $SPEC_NAME..."

  # Create worktrees directory if needed
  mkdir -p "$WORKTREES_DIR"

  # Check if worktree already exists
  if [ -d "$WORKTREE_PATH" ]; then
    echo "  Worktree already exists at $WORKTREE_PATH"
    WORKTREE_BRANCH=$(git -C "$WORKTREE_PATH" branch --show-current 2>/dev/null || echo "")

    # Check for any work in the worktree (committed or uncommitted)
    UNCOMMITTED=$(cd "$WORKTREE_PATH" && git status --porcelain 2>/dev/null)
    COMMITS_AHEAD=$(cd "$WORKTREE_PATH" && git rev-list --count HEAD ^origin/$WORKTREE_BRANCH 2>/dev/null || echo "0")

    if [ "$WORKTREE_BRANCH" != "$BRANCH_NAME" ]; then
      # Branch mismatch - but we should preserve any existing work
      if [ -n "$UNCOMMITTED" ] || [ "$COMMITS_AHEAD" -gt 0 ]; then
        # There's work here - keep using this worktree, just warn about branch name
        echo -e "  ${YELLOW}Note: Worktree is on branch '$WORKTREE_BRANCH' (prd.json says '$BRANCH_NAME')${NC}"
        echo -e "  ${YELLOW}Continuing with existing worktree to preserve work.${NC}"
        # Update BRANCH_NAME to match actual worktree branch for consistency
        BRANCH_NAME="$WORKTREE_BRANCH"
        return 0
      else
        # No work to preserve - safe to recreate on correct branch
        echo "  Worktree on different branch '$WORKTREE_BRANCH' with no uncommitted work."
        echo "  Recreating on branch '$BRANCH_NAME'..."
        git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || rm -rf "$WORKTREE_PATH"
        git worktree prune 2>/dev/null || true
      fi
    else
      echo "  Worktree ready on branch: $BRANCH_NAME"
      return 0
    fi
  fi

  # Ensure branch exists (create from current HEAD if not)
  if ! git show-ref --verify --quiet "refs/heads/$BRANCH_NAME"; then
    echo "  Creating branch: $BRANCH_NAME"
    git branch "$BRANCH_NAME"
  fi

  # Create the worktree
  echo "  Creating worktree at: $WORKTREE_PATH"
  git worktree add "$WORKTREE_PATH" "$BRANCH_NAME"

  # Copy environment files
  echo "  Copying environment files..."
  for env_file in .env .env.local .env.production .env.netlify; do
    if [ -f "$PROJECT_ROOT/$env_file" ]; then
      cp "$PROJECT_ROOT/$env_file" "$WORKTREE_PATH/$env_file"
      echo "    Copied $env_file"
    fi
  done

  # Copy service account files
  for sa_file in "$PROJECT_ROOT"/*-service-account-key.json "$PROJECT_ROOT"/*.serviceaccount.json; do
    if [ -f "$sa_file" ]; then
      cp "$sa_file" "$WORKTREE_PATH/"
      echo "    Copied $(basename "$sa_file")"
    fi
  done

  # Symlink node_modules for speed
  if [ -d "$PROJECT_ROOT/node_modules" ]; then
    echo "  Symlinking node_modules..."
    ln -sf "$PROJECT_ROOT/node_modules" "$WORKTREE_PATH/node_modules"
  else
    echo "  Warning: node_modules not found in main project"
    echo "  Running npm ci in worktree..."
    (cd "$WORKTREE_PATH" && npm ci)
  fi

  echo "  Worktree setup complete!"
}

cleanup_worktree() {
  echo ""
  echo "Cleaning up worktree..."
  if [ -d "$WORKTREE_PATH" ]; then
    # Remove symlinked node_modules first
    [ -L "$WORKTREE_PATH/node_modules" ] && rm "$WORKTREE_PATH/node_modules"
    # Remove the worktree
    git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || {
      echo "  Warning: Could not cleanly remove worktree, forcing removal..."
      rm -rf "$WORKTREE_PATH"
      git worktree prune
    }
    echo "  Worktree removed: $WORKTREE_PATH"
  fi
}

# Optional: Uncomment to auto-cleanup on exit
# trap cleanup_worktree EXIT

# =============================================================================
# COMPONENT VALIDATION - Server-side enforcement of component requirements
# =============================================================================

validate_component_usage() {
  local story_id="$1"
  local prd_file="$2"
  local worktree="$3"

  # Get changed .tsx files
  local changed_tsx=$(cd "$worktree" && git status --porcelain 2>/dev/null | grep -E '\.tsx$' | awk '{print $2}')

  if [ -z "$changed_tsx" ]; then
    return 0  # No frontend changes to validate
  fi

  # Extract story description and criteria
  local story_description=$(jq -r --arg id "$story_id" '.userStories[] | select(.id == $id) | .description // ""' "$prd_file")
  local story_criteria=$(jq -r --arg id "$story_id" '.userStories[] | select(.id == $id) | .acceptanceCriteria // [] | .[]' "$prd_file")

  # Build list of required components from description + criteria
  local required_components=""

  # Components we check for (add more as needed)
  local component_list="CRUDTable EntityForm ChecklistSystem StatusBadge Modal ConfirmDialog EmptyState LoadingState UniversalEmailPreview Progress Tabs"

  # Check for "Use ComponentName" in description (from Implementation section)
  for component in $component_list; do
    if echo "$story_description" | grep -qi "Use $component"; then
      required_components="$required_components $component"
    fi
  done

  # Check for "Uses ComponentName" in acceptance criteria
  while IFS= read -r criterion; do
    for component in $component_list; do
      if echo "$criterion" | grep -qi "Uses $component"; then
        required_components="$required_components $component"
      fi
    done
  done <<< "$story_criteria"

  # Deduplicate
  required_components=$(echo "$required_components" | tr ' ' '\n' | sort -u | grep -v '^$' | tr '\n' ' ')

  if [ -z "$(echo "$required_components" | tr -d ' ')" ]; then
    return 0  # No component requirements found
  fi

  echo -e "${BLUE}── Component Validation ──${NC}"
  echo -e "  Required components:${YELLOW}$required_components${NC}"
  echo -e "  Changed tsx files: $(echo "$changed_tsx" | tr '\n' ' ')"

  # Validate each component is imported in at least one changed file
  local failures=""
  for component in $required_components; do
    local found=false
    for file in $changed_tsx; do
      if (cd "$worktree" && grep -q "import.*$component" "$file" 2>/dev/null); then
        found=true
        break
      fi
    done
    if [ "$found" = false ]; then
      failures="$failures $component"
    fi
  done

  if [ -n "$(echo "$failures" | tr -d ' ')" ]; then
    echo ""
    echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║              COMPONENT VALIDATION FAILED                      ║${NC}"
    echo -e "${RED}╠═══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${RED}║${NC}  Story $story_id requires components that were not imported:"
    echo -e "${RED}║${NC}"
    echo -e "${RED}║${NC}  Missing:${YELLOW}$failures${NC}"
    echo -e "${RED}║${NC}"
    echo -e "${RED}║${NC}  The story description or acceptance criteria specified these"
    echo -e "${RED}║${NC}  components, but they were not found in the changed .tsx files."
    echo -e "${RED}║${NC}"
    echo -e "${RED}║${NC}  Check that you:"
    echo -e "${RED}║${NC}  - Used the components from componentContext"
    echo -e "${RED}║${NC}  - Did NOT build custom implementations"
    echo -e "${RED}║${NC}  - Properly imported the components"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
    return 1
  fi

  echo -e "  ${GREEN}✓ All required components found in imports${NC}"
  return 0
}

# =============================================================================
# SETUP WORKTREE
# =============================================================================

setup_worktree

# CRITICAL: Copy spec files from main repo to worktree
# The worktree branch may have stale/different spec files, but we need the CURRENT ones
echo ""
echo -e "${BLUE}Syncing spec files to worktree...${NC}"
WORKTREE_SPEC_DIR="$WORKTREE_PATH/agent-os/specs/$SPEC_NAME"
mkdir -p "$WORKTREE_SPEC_DIR"

# Copy prd.json and progress.txt from main repo to worktree
cp "$SPEC_DIR/prd.json" "$WORKTREE_SPEC_DIR/prd.json"
echo -e "  Copied prd.json to worktree"
if [ -f "$SPEC_DIR/progress.txt" ]; then
  cp "$SPEC_DIR/progress.txt" "$WORKTREE_SPEC_DIR/progress.txt"
  echo -e "  Copied progress.txt to worktree"
fi
if [ -f "$SPEC_DIR/spec.md" ]; then
  cp "$SPEC_DIR/spec.md" "$WORKTREE_SPEC_DIR/spec.md"
  echo -e "  Copied spec.md to worktree"
fi

# Now switch to worktree paths for ALL validation
# Claude runs in the worktree and edits files THERE, so we must validate THERE
echo ""
echo -e "${BLUE}Using worktree's spec files for validation...${NC}"
PRD_FILE="$WORKTREE_SPEC_DIR/prd.json"
PROGRESS_FILE="$WORKTREE_SPEC_DIR/progress.txt"
echo -e "  PRD:      ${GREEN}$PRD_FILE${NC}"
echo -e "  Progress: ${GREEN}$PROGRESS_FILE${NC}"

# Verify the file is valid
if ! jq -e '.userStories' "$PRD_FILE" > /dev/null 2>&1; then
  echo -e "  ${RED}ERROR: prd.json missing userStories field${NC}"
  echo -e "  ${RED}File content:${NC}"
  head -20 "$PRD_FILE"
  exit 1
fi

# Function to sync spec files back to main repo (preserves progress)
sync_spec_to_main() {
  if [ -f "$PRD_FILE" ]; then
    cp "$PRD_FILE" "$SPEC_DIR/prd.json"
  fi
  if [ -f "$PROGRESS_FILE" ]; then
    cp "$PROGRESS_FILE" "$SPEC_DIR/progress.txt"
  fi
}

# Initialize progress file if it doesn't exist
if [ ! -f "$PROGRESS_FILE" ]; then
  DESCRIPTION=$(jq -r '.description // "No description"' "$PRD_FILE")
  cat > "$PROGRESS_FILE" << EOF
# Ralph Progress Log

**Feature:** $DESCRIPTION
**Branch:** $BRANCH_NAME
**Worktree:** $WORKTREE_PATH
**Started:** $(date)

---

## Codebase Patterns

(Add reusable patterns discovered during implementation here)

---

EOF
fi

# =============================================================================
# QA-PASSED HELPERS - Track stories needing QA verification
# =============================================================================
# A story is "fully done" when:
#   - passes == true AND (qa_passed == true OR qa_required == false)
# Stories with qa_required: false (pure backend/schema) don't need QA verification.
# If qa_required field is missing, defaults to true (safe default - run QA).

# Count stories that still need work (implementation OR QA verification)
count_remaining() {
  local prd_file="$1"
  # NOTE: Use .qa_required != false (NOT .qa_required // true) because jq's //
  # operator treats both null AND false as falsey, which breaks explicit false values
  jq '[.userStories[] | select(
    .passes == false or
    (.passes == true and (.qa_passed // false) == false and .qa_required != false)
  )] | length' "$prd_file"
}

# Count stories that still need IMPLEMENTATION (passes == false only)
count_needing_implementation() {
  local prd_file="$1"
  jq '[.userStories[] | select(.passes == false)] | length' "$prd_file"
}

# Get next story needing QA only (priority over new implementation)
get_next_qa_only_id() {
  local prd_file="$1"
  # NOTE: Use .qa_required != false (NOT .qa_required // true) because jq's //
  # operator treats both null AND false as falsey, which breaks explicit false values
  jq -r '[.userStories[] | select(
    .passes == true and (.qa_passed // false) == false and .qa_required != false
  )][0].id // ""' "$prd_file"
}


# Display startup info
echo ""
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}           ${BOLD}Ralph Wiggum for Claude Code${NC}                       ${CYAN}║${NC}"
echo -e "${CYAN}╠═══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  Spec:           ${YELLOW}$SPEC_NAME${NC}"
echo -e "${CYAN}║${NC}  Branch:         $BRANCH_NAME"
echo -e "${CYAN}║${NC}  Worktree:       $WORKTREE_PATH"
echo -e "${CYAN}║${NC}  Max Iterations: $MAX_ITERATIONS"
echo -e "${CYAN}║${NC}  PRD:            $PRD_FILE"
echo -e "${CYAN}║${NC}  Progress:       $PROGRESS_FILE"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Count remaining stories (includes those needing QA re-verification)
REMAINING=$(count_remaining "$PRD_FILE")
TOTAL=$(jq '.userStories | length' "$PRD_FILE")
COMPLETED=$((TOTAL - REMAINING))
echo -e "${BOLD}Stories:${NC} ${GREEN}$COMPLETED${NC}/${TOTAL} complete, ${YELLOW}$REMAINING${NC} remaining"
echo ""

# Track consecutive iterations with no progress (stuck detection)
NO_PROGRESS_COUNT=0
MAX_NO_PROGRESS=3  # Abort after 3 consecutive iterations with no progress

# =============================================================================
# STORY TYPE INFERENCE - Used for display labels only (NOT for QA gating)
# QA verification is controlled by the qa_required field in prd.json.
# This function provides human-readable type labels for iteration summaries.
# =============================================================================

infer_story_type() {
  local story_id="$1"
  # Extract the numeric part (e.g., "US-045" -> 45)
  local num=$(echo "$story_id" | sed 's/US-0*//' | sed 's/^0*//')

  if [[ -z "$num" ]] || ! [[ "$num" =~ ^[0-9]+$ ]]; then
    echo "Unknown"
    return
  fi

  if (( num >= 1 && num <= 20 )); then
    echo "Schema"
  elif (( num >= 21 && num <= 40 )); then
    echo "API"
  elif (( num >= 41 && num <= 60 )); then
    echo "UI Component"
  elif (( num >= 61 && num <= 80 )); then
    echo "Page Integration"
  elif (( num >= 81 && num <= 100 )); then
    echo "Polish"
  else
    echo "Unknown"
  fi
}

# =============================================================================
# ITERATION SUMMARY FUNCTION - Displays status at end of each iteration
# =============================================================================

print_iteration_summary() {
  local iteration="$1"
  local story_id="$2"
  local story_title="$3"
  local completed="$4"
  local total="$5"
  local impl_status="$6"
  local component_status="$7"
  local qa_status="$8"

  echo ""
  echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}║${NC}              ${BOLD}ITERATION $iteration SUMMARY${NC}                          ${CYAN}║${NC}"
  echo -e "${CYAN}╠═══════════════════════════════════════════════════════════════╣${NC}"
  printf "${CYAN}║${NC}  Story: [%s] %.40s\n" "$story_id" "$story_title"

  # Implementation status
  case "$impl_status" in
    passed)  echo -e "${CYAN}║${NC}  Implementation:       ${GREEN}✓ PASSED${NC}" ;;
    qa_only) echo -e "${CYAN}║${NC}  Implementation:       ${CYAN}○ SKIPPED${NC} (QA-only re-run)" ;;
    *)       echo -e "${CYAN}║${NC}  Implementation:       ${YELLOW}○ NO PROGRESS${NC}" ;;
  esac

  # Component validation status
  case "$component_status" in
    passed) echo -e "${CYAN}║${NC}  Component Validation: ${GREEN}✓ PASSED${NC}" ;;
    failed) echo -e "${CYAN}║${NC}  Component Validation: ${RED}✗ FAILED${NC}" ;;
    *)      echo -e "${CYAN}║${NC}  Component Validation: ${CYAN}○ N/A${NC}" ;;
  esac

  # QA status
  case "$qa_status" in
    passed)       echo -e "${CYAN}║${NC}  QA Browser Testing:   ${GREEN}✓ PASSED${NC}" ;;
    failed)       echo -e "${CYAN}║${NC}  QA Browser Testing:   ${RED}✗ FAILED${NC}" ;;
    skipped)      echo -e "${CYAN}║${NC}  QA Browser Testing:   ${CYAN}○ SKIPPED${NC} (non-UI story)" ;;
    not_required) echo -e "${CYAN}║${NC}  QA Browser Testing:   ${CYAN}○ N/A${NC}" ;;
  esac

  echo -e "${CYAN}╠═══════════════════════════════════════════════════════════════╣${NC}"
  echo -e "${CYAN}║${NC}  Overall: ${GREEN}$completed${NC}/${BOLD}$total${NC} stories complete"
  echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
}

# Main loop
for i in $(seq 1 $MAX_ITERATIONS); do
  # Reset iteration tracking variables
  ITERATION_IMPL_STATUS="pending"
  ITERATION_COMPONENT_STATUS="not_checked"
  ITERATION_QA_STATUS="not_required"
  ITERATION_QA_EVIDENCE=""

  # Check if all stories are complete before starting iteration
  REMAINING=$(count_remaining "$PRD_FILE")
  if [ "$REMAINING" -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ All stories complete! Nothing to do.${NC}"
    # Promote learnings to codebase-wide patterns
    echo "Promoting learnings to codebase-wide patterns..."
    "$PROJECT_ROOT/.claude/scripts/promote-learnings.sh" "$SPEC_NAME" || true
    exit 0
  fi

  # Store remaining count BEFORE Claude runs (for progress tracking)
  REMAINING_BEFORE=$REMAINING
  REMAINING_BEFORE_IMPL=$(count_needing_implementation "$PRD_FILE")

  # Check if a story needs QA-only (already implemented but not QA-verified)
  QA_ONLY_ID=$(get_next_qa_only_id "$PRD_FILE")
  if [ -n "$QA_ONLY_ID" ]; then
    MODE="qa_only"
    CURRENT_STORY_ID="$QA_ONLY_ID"
    CURRENT_STORY=$(jq -r --arg id "$QA_ONLY_ID" '.userStories[] | select(.id == $id) | .title // "Unknown"' "$PRD_FILE")
  else
    MODE="implement"
    # Get current story title and ID for display
    CURRENT_STORY=$(jq -r '[.userStories[] | select(.passes == false)][0].title // "Unknown"' "$PRD_FILE")
    CURRENT_STORY_ID=$(jq -r '[.userStories[] | select(.passes == false)][0].id // "?"' "$PRD_FILE")
  fi

  COMPLETED_COUNT=$((TOTAL - REMAINING))
  STORY_NUMBER=$((COMPLETED_COUNT + 1))

  echo ""
  echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "  ${CYAN}Iteration $i of $MAX_ITERATIONS${NC} │ ${GREEN}Story $STORY_NUMBER of $TOTAL${NC}"
  if [ "$MODE" = "qa_only" ]; then
    echo -e "  ${CYAN}Mode:${NC} QA-only re-run (story already implemented)"
  fi
  echo -e "  ${YELLOW}Target:${NC} [$CURRENT_STORY_ID] $CURRENT_STORY"
  echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
  echo ""

  # If QA-only mode, skip implementation and jump to QA verification
  if [ "$MODE" = "qa_only" ]; then
    echo -e "${CYAN}Story already implemented — running QA verification only...${NC}"
    ITERATION_IMPL_STATUS="qa_only"
    JUST_COMPLETED_ID="$CURRENT_STORY_ID"
    JUST_COMPLETED_TYPE=$(infer_story_type "$JUST_COMPLETED_ID")
    JUST_COMPLETED_TITLE="$CURRENT_STORY"
  else

  # Create the prompt with spec folder context, worktree info, and explicit story target
  # COMMIT_MODE: true tells Claude to commit after each story (ralph.sh uses isolated worktrees)
  FULL_PROMPT="SPEC_FOLDER: $SPEC_NAME
WORKTREE_PATH: $WORKTREE_PATH
TARGET_STORY_ID: $CURRENT_STORY_ID
COMMIT_MODE: true

$(cat "$PROMPT_FILE")"

  # Start progress monitor
  echo -e "${BLUE}▶ Starting Claude (timeout: $((CLAUDE_TIMEOUT_SECONDS/60)) min)...${NC}"
  start_progress_monitor "$WORKTREE_PATH" "$PRD_FILE"

  # Run claude INSIDE THE WORKTREE - isolated from main directory WITH TIMEOUT
  # Exit codes: 124 = timeout, 137 = killed after grace period
  CLAUDE_EXIT_CODE=0
  (
    cd "$WORKTREE_PATH"
    # Export the prompt for the inner bash to access
    export FULL_PROMPT
    run_with_timeout ${CLAUDE_TIMEOUT_SECONDS} 'echo "$FULL_PROMPT" | claude --print --dangerously-skip-permissions --chrome 2>&1'
  ) | tee "$CLAUDE_OUTPUT_FILE"
  CLAUDE_EXIT_CODE=${PIPESTATUS[0]}

  # Stop progress monitor
  stop_progress_monitor

  # =============================================================================
  # TIMEOUT DETECTION - Handle Claude timeout gracefully
  # =============================================================================
  if [ $CLAUDE_EXIT_CODE -eq 124 ] || [ $CLAUDE_EXIT_CODE -eq 137 ]; then
    echo ""
    echo -e "${YELLOW}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║              TIMEOUT: Claude exceeded time limit              ║${NC}"
    echo -e "${YELLOW}╠═══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${YELLOW}║${NC}  Story: [$CURRENT_STORY_ID] $CURRENT_STORY"
    echo -e "${YELLOW}║${NC}  Time limit: $((CLAUDE_TIMEOUT_SECONDS/60)) minutes"
    echo -e "${YELLOW}╚═══════════════════════════════════════════════════════════════╝${NC}"

    # Check if story completed despite timeout (maybe it finished right before timeout)
    STORY_STATUS=$(jq -r --arg id "$CURRENT_STORY_ID" \
      '.userStories[] | select(.id == $id) | .passes' "$PRD_FILE")

    if [ "$STORY_STATUS" != "true" ]; then
      # Story did not complete - track retries
      RETRIES=$(get_story_retries "$CURRENT_STORY_ID")
      RETRIES=$((RETRIES + 1))
      set_story_retries "$CURRENT_STORY_ID" "$RETRIES"

      echo ""
      echo -e "${YELLOW}  Retry count for $CURRENT_STORY_ID: $RETRIES/$MAX_STORY_RETRIES${NC}"

      if [ $RETRIES -ge $MAX_STORY_RETRIES ]; then
        echo ""
        echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║              STORY BLOCKED - Max retries exceeded             ║${NC}"
        echo -e "${RED}╠═══════════════════════════════════════════════════════════════╣${NC}"
        echo -e "${RED}║${NC}  Story: [$CURRENT_STORY_ID] $CURRENT_STORY"
        echo -e "${RED}║${NC}  Timed out $MAX_STORY_RETRIES times without completing"
        echo -e "${RED}║${NC}"
        echo -e "${RED}║${NC}  This story may need:"
        echo -e "${RED}║${NC}  - Breaking into smaller stories"
        echo -e "${RED}║${NC}  - Manual investigation"
        echo -e "${RED}║${NC}  - Clearer acceptance criteria"
        echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"

        # Log to progress file
        echo "" >> "$PROGRESS_FILE"
        echo "## BLOCKED - $CURRENT_STORY_ID" >> "$PROGRESS_FILE"
        echo "- Story: $CURRENT_STORY" >> "$PROGRESS_FILE"
        echo "- Reason: Timed out $MAX_STORY_RETRIES times" >> "$PROGRESS_FILE"
        echo "- Time: $(date)" >> "$PROGRESS_FILE"
        echo "---" >> "$PROGRESS_FILE"

        sync_spec_to_main  # Preserve any partial progress
        rm -f "$CLAUDE_OUTPUT_FILE"
        exit 1
      else
        echo -e "${YELLOW}  Will retry in next iteration...${NC}"
        # Log timeout to progress file
        echo "" >> "$PROGRESS_FILE"
        echo "## TIMEOUT - $CURRENT_STORY_ID (attempt $RETRIES)" >> "$PROGRESS_FILE"
        echo "- Story: $CURRENT_STORY" >> "$PROGRESS_FILE"
        echo "- Time: $(date)" >> "$PROGRESS_FILE"
        echo "---" >> "$PROGRESS_FILE"
      fi
    else
      echo -e "${GREEN}  Story completed despite timeout - continuing...${NC}"
    fi
  fi

  # Calculate iteration duration
  if [ -n "$CLAUDE_START_TIME" ]; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - CLAUDE_START_TIME))
    DUR_MINS=$((DURATION / 60))
    DUR_SECS=$((DURATION % 60))
    echo -e "${GREEN}✓ Claude finished${NC} (took ${DUR_MINS}m ${DUR_SECS}s)"
  fi

  # Show summary of changes
  echo ""
  echo -e "${BLUE}── Changes this iteration ──${NC}"
  if [ -d "$WORKTREE_PATH" ]; then
    CHANGES=$(cd "$WORKTREE_PATH" && git status --porcelain 2>/dev/null)
    if [ -n "$CHANGES" ]; then
      echo "$CHANGES" | head -10
      TOTAL_CHANGES=$(echo "$CHANGES" | wc -l | tr -d ' ')
      if [ "$TOTAL_CHANGES" -gt 10 ]; then
        echo "  ... and $((TOTAL_CHANGES - 10)) more files"
      fi
    else
      echo "  (no file changes)"
    fi
  fi
  echo ""

  fi  # End of MODE check (qa_only skips implementation, implement runs Claude)

  # =============================================================================
  # QA-ONLY MODE - Skip progress tracking and go straight to QA verification
  # =============================================================================
  if [ "$MODE" = "qa_only" ]; then
    NEEDS_BROWSER_VERIFICATION=true

    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║              QA VERIFICATION - Browser Testing                ║${NC}"
    echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${BLUE}║${NC}  Story: [$JUST_COMPLETED_ID] $JUST_COMPLETED_TITLE"
    echo -e "${BLUE}║${NC}  Type: $JUST_COMPLETED_TYPE (QA-only re-run)"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Dev server on worktree port
    DEV_SERVER_PORT=5174
    echo -e "${CYAN}▶ Starting dev server in worktree on port $DEV_SERVER_PORT...${NC}"
    if ! curl -s "http://localhost:$DEV_SERVER_PORT" > /dev/null 2>&1; then
      (cd "$WORKTREE_PATH" && npm run dev -- --port $DEV_SERVER_PORT > /dev/null 2>&1 &)
      DEV_SERVER_READY=false
      for attempt in $(seq 1 30); do
        if curl -s "http://localhost:$DEV_SERVER_PORT" > /dev/null 2>&1; then
          DEV_SERVER_READY=true
          echo -e "${GREEN}✓ Dev server ready${NC}"
          break
        fi
        sleep 1
      done
      if [ "$DEV_SERVER_READY" = false ]; then
        echo -e "${RED}✗ Dev server failed to start. QA FAIL.${NC}"
        jq --arg id "$JUST_COMPLETED_ID" \
          '(.userStories[] | select(.id == $id)) |= (.passes = false | .qa_passed = false)' \
          "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"
        ITERATION_QA_STATUS="failed"
        pkill -f "npm.*--port.*$DEV_SERVER_PORT" 2>/dev/null || true
        lsof -ti:$DEV_SERVER_PORT | xargs kill -9 2>/dev/null || true
        FINAL_COMPLETED=$(count_remaining "$PRD_FILE")
        FINAL_COMPLETED=$((TOTAL - FINAL_COMPLETED))
        print_iteration_summary "$i" "$CURRENT_STORY_ID" "$CURRENT_STORY" "$FINAL_COMPLETED" "$TOTAL" "$ITERATION_IMPL_STATUS" "$ITERATION_COMPONENT_STATUS" "$ITERATION_QA_STATUS"
        sync_spec_to_main
        continue
      fi
    else
      echo -e "${GREEN}✓ Dev server already running${NC}"
    fi

    SCREENSHOTS_DIR="$WORKTREE_PATH/agent-os/specs/$SPEC_NAME/screenshots"
    mkdir -p "$SCREENSHOTS_DIR"
    STORY_ACCEPTANCE=$(jq -r --arg id "$JUST_COMPLETED_ID" '.userStories[] | select(.id == $id) | .acceptanceCriteria // []' "$PRD_FILE")
    STORY_DESCRIPTION=$(jq -r --arg id "$JUST_COMPLETED_ID" '.userStories[] | select(.id == $id) | .description // ""' "$PRD_FILE")

    QA_PROMPT="You are the QA Verifier agent. Your job is to verify that a story was implemented correctly by testing it in the browser.

DEV SERVER URL: http://localhost:$DEV_SERVER_PORT

STORY TO VERIFY:
- ID: $JUST_COMPLETED_ID
- Title: $JUST_COMPLETED_TITLE
- Type: $JUST_COMPLETED_TYPE
- Description: $STORY_DESCRIPTION

ACCEPTANCE CRITERIA:
$STORY_ACCEPTANCE

MANDATORY VERIFICATION STEPS:
1. Use Claude in Chrome or Playwright to navigate to http://localhost:$DEV_SERVER_PORT
2. Navigate to the page related to this story
3. Take a screenshot and save it to: $SCREENSHOTS_DIR/${JUST_COMPLETED_ID}.png
4. Verify each acceptance criterion works as expected
5. If testing forms: submit data and verify it persists
6. If testing edit mode: verify fields pre-populate with saved values

OUTPUT FORMAT (MANDATORY):
If verification PASSES, output exactly:
<qa-result>PASS</qa-result>
<qa-evidence>Brief description of what was verified</qa-evidence>

If verification FAILS, output exactly:
<qa-result>FAIL</qa-result>
<qa-failure-reason>Specific description of what failed</qa-failure-reason>

IMPORTANT: You MUST output one of the above formats. If you cannot verify, output FAIL with reason."

    QA_OUTPUT_FILE=$(mktemp)

    # Use resilient QA runner (Chrome with Playwright fallback)
    run_qa_resilient "$WORKTREE_PATH" "$QA_PROMPT" "$QA_OUTPUT_FILE" "$JUST_COMPLETED_ID"
    QA_EXIT_CODE=$?

    if [ "$QA_METHOD_USED" = "playwright" ]; then
      echo -e "${CYAN}  QA ran via Playwright fallback (Chrome unavailable)${NC}"
    fi

    if [ $QA_EXIT_CODE -eq 124 ] || [ $QA_EXIT_CODE -eq 137 ]; then
      echo -e "${RED}QA Verifier timed out (both Chrome and Playwright).${NC}"
      jq --arg id "$JUST_COMPLETED_ID" \
        '(.userStories[] | select(.id == $id)) |= (.passes = false | .qa_passed = false)' \
        "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"
      ITERATION_QA_STATUS="failed"
      rm -f "$QA_OUTPUT_FILE"
    elif grep -q "<qa-result>PASS</qa-result>" "$QA_OUTPUT_FILE" 2>/dev/null; then
      echo -e "${GREEN}QA PASSED — setting qa_passed: true${NC}"
      if [ "$QA_METHOD_USED" = "playwright" ]; then
        echo -e "${CYAN}  (verified via Playwright fallback)${NC}"
      fi
      jq --arg id "$JUST_COMPLETED_ID" \
        '(.userStories[] | select(.id == $id) | .qa_passed) = true' \
        "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"
      ITERATION_QA_STATUS="passed"
      NO_PROGRESS_COUNT=0  # QA passing IS progress
      rm -f "$QA_OUTPUT_FILE"
    elif grep -q "<qa-result>FAIL</qa-result>" "$QA_OUTPUT_FILE" 2>/dev/null; then
      FAILURE_REASON=$(grep -A 20 "<qa-failure-reason>" "$QA_OUTPUT_FILE" | grep -B 20 "</qa-failure-reason>" | sed 's/<[^>]*>//g' | head -5)
      echo -e "${RED}QA FAILED: $FAILURE_REASON${NC}"
      jq --arg id "$JUST_COMPLETED_ID" \
        '(.userStories[] | select(.id == $id)) |= (.passes = false | .qa_passed = false)' \
        "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"
      ITERATION_QA_STATUS="failed"
      rm -f "$QA_OUTPUT_FILE"
    else
      echo -e "${RED}QA ambiguous — defaulting to FAIL${NC}"
      jq --arg id "$JUST_COMPLETED_ID" \
        '(.userStories[] | select(.id == $id)) |= (.passes = false | .qa_passed = false)' \
        "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"
      ITERATION_QA_STATUS="failed"
      rm -f "$QA_OUTPUT_FILE"
    fi

    # Kill dev server
    echo -e "${CYAN}Stopping dev server...${NC}"
    pkill -f "npm.*--port.*$DEV_SERVER_PORT" 2>/dev/null || true
    lsof -ti:$DEV_SERVER_PORT | xargs kill -9 2>/dev/null || true

    FINAL_COMPLETED=$(count_remaining "$PRD_FILE")
    FINAL_COMPLETED=$((TOTAL - FINAL_COMPLETED))
    print_iteration_summary "$i" "$CURRENT_STORY_ID" "$CURRENT_STORY" "$FINAL_COMPLETED" "$TOTAL" "$ITERATION_IMPL_STATUS" "$ITERATION_COMPONENT_STATUS" "$ITERATION_QA_STATUS"
    sync_spec_to_main

    echo -e "${YELLOW}Iteration $i complete.${NC} Pausing 3 seconds before next iteration..."
    sleep 3
    continue
  fi

  # =============================================================================
  # IMPLEMENTATION MODE - Progress tracking and QA
  # =============================================================================

  # Progress tracking: Check if any stories were marked complete this iteration
  # Use implementation-only count to detect progress (UI stories stay in count_remaining
  # until QA passes, but implementation progress should still be recognized)
  REMAINING_AFTER_IMPL=$(count_needing_implementation "$PRD_FILE")
  REMAINING_AFTER=$(count_remaining "$PRD_FILE")
  COMPLETED_THIS_ITERATION=$((REMAINING_BEFORE_IMPL - REMAINING_AFTER_IMPL))

  # ==========================================================================
  # COMPONENT VALIDATION - Validate required components were used
  # ==========================================================================
  if [ "$COMPLETED_THIS_ITERATION" -gt 0 ]; then
    # Get the story that was just completed (the one we targeted this iteration)
    COMPLETED_STORY_ID="$CURRENT_STORY_ID"

    if ! validate_component_usage "$COMPLETED_STORY_ID" "$PRD_FILE" "$WORKTREE_PATH"; then
      echo ""
      echo -e "${YELLOW}Rolling back: Setting passes: false for $COMPLETED_STORY_ID${NC}"

      # Rollback the story: set both passes and qa_passed to false
      jq --arg id "$COMPLETED_STORY_ID" \
        '(.userStories[] | select(.id == $id)) |= (.passes = false | .qa_passed = false)' \
        "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"

      # Adjust counts
      REMAINING_AFTER=$((REMAINING_AFTER + 1))
      COMPLETED_THIS_ITERATION=$((COMPLETED_THIS_ITERATION - 1))
      NO_PROGRESS_COUNT=$((NO_PROGRESS_COUNT + 1))
      ITERATION_COMPONENT_STATUS="failed"
      ITERATION_IMPL_STATUS="pending"  # Rollback means no real progress

      echo -e "${YELLOW}Story will be re-attempted next iteration with proper components...${NC}"
    else
      ITERATION_COMPONENT_STATUS="passed"
    fi
  fi

  # Calculate total progress
  TOTAL_COMPLETED=$((TOTAL - REMAINING_AFTER))

  echo -e "${BLUE}── Progress ──${NC}"
  echo -e "  Overall: ${GREEN}$TOTAL_COMPLETED${NC} of ${BOLD}$TOTAL${NC} stories complete"
  echo -e "  This iteration: ${CYAN}+$COMPLETED_THIS_ITERATION${NC}"

  if [ "$COMPLETED_THIS_ITERATION" -le 0 ]; then
    NO_PROGRESS_COUNT=$((NO_PROGRESS_COUNT + 1))
    echo ""
    echo -e "${YELLOW}⚠ WARNING: No progress this iteration ($NO_PROGRESS_COUNT/$MAX_NO_PROGRESS before abort)${NC}"

    if [ "$NO_PROGRESS_COUNT" -ge "$MAX_NO_PROGRESS" ]; then
      echo ""
      echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
      echo -e "${RED}║                    STUCK LOOP DETECTED                        ║${NC}"
      echo -e "${RED}╠═══════════════════════════════════════════════════════════════╣${NC}"
      echo -e "${RED}║${NC}  $MAX_NO_PROGRESS consecutive iterations with no progress!"
      echo -e "${RED}║${NC}  Claude is not marking stories complete in prd.json."
      echo -e "${RED}║${NC}"
      echo -e "${RED}║${NC}  Stories remaining: $REMAINING_AFTER of $TOTAL"
      echo -e "${RED}║${NC}"
      echo -e "${RED}║${NC}  Check if:"
      echo -e "${RED}║${NC}  - Stories are actually being implemented"
      echo -e "${RED}║${NC}  - prd.json is being updated with passes: true"
      echo -e "${RED}║${NC}  - Claude is following prompt.md instructions"
      echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
      sync_spec_to_main  # Preserve any partial progress
      rm -f "$CLAUDE_OUTPUT_FILE"
      exit 1
    fi
  else
    NO_PROGRESS_COUNT=0  # Reset counter on progress
    ITERATION_IMPL_STATUS="passed"
    echo -e "${GREEN}✓ Progress made!${NC}"

    # =============================================================================
    # QA VERIFICATION - Spawn qa-verifier for UI stories
    # =============================================================================

    # Get the story that was just completed
    JUST_COMPLETED_ID="$CURRENT_STORY_ID"
    JUST_COMPLETED_TYPE=$(infer_story_type "$JUST_COMPLETED_ID")
    JUST_COMPLETED_TITLE=$(jq -r --arg id "$JUST_COMPLETED_ID" '.userStories[] | select(.id == $id) | .title // "Unknown"' "$PRD_FILE")

    # Check if this story requires browser verification via qa_required field
    # Defaults to true if field is missing (safe default - run QA)
    # NOTE: Use explicit conditional (NOT .qa_required // true) because jq's //
    # operator treats both null AND false as falsey, which breaks explicit false values
    QA_REQUIRED=$(jq -r --arg id "$JUST_COMPLETED_ID" \
      '.userStories[] | select(.id == $id) | if .qa_required == false then false else true end' "$PRD_FILE")
    if [ "$QA_REQUIRED" = "true" ]; then
      NEEDS_BROWSER_VERIFICATION=true
    else
      NEEDS_BROWSER_VERIFICATION=false
    fi

    if [ "$NEEDS_BROWSER_VERIFICATION" = true ]; then
      echo ""
      echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
      echo -e "${BLUE}║              QA VERIFICATION - Browser Testing                ║${NC}"
      echo -e "${BLUE}╠═══════════════════════════════════════════════════════════════╣${NC}"
      echo -e "${BLUE}║${NC}  Story: [$JUST_COMPLETED_ID] $JUST_COMPLETED_TITLE"
      echo -e "${BLUE}║${NC}  Type: $JUST_COMPLETED_TYPE (requires browser verification)"
      echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
      echo ""

      # Start dev server in worktree on port 5174 (to avoid conflict with main project)
      DEV_SERVER_PORT=5174
      DEV_SERVER_STARTED=false

      echo -e "${CYAN}▶ Starting dev server in worktree on port $DEV_SERVER_PORT...${NC}"
      (cd "$WORKTREE_PATH" && npm run dev -- --port $DEV_SERVER_PORT > /dev/null 2>&1 &)
      DEV_SERVER_STARTED=true

      # Wait for dev server to be ready (max 30 seconds)
      DEV_SERVER_READY=false
      for attempt in $(seq 1 30); do
        if curl -s "http://localhost:$DEV_SERVER_PORT" > /dev/null 2>&1; then
          DEV_SERVER_READY=true
          echo -e "${GREEN}✓ Dev server ready${NC}"
          break
        fi
        sleep 1
      done

      if [ "$DEV_SERVER_READY" = false ]; then
        echo -e "${RED}✗ Dev server failed to start. Marking QA as FAIL.${NC}"
        # Revert story: set both passes and qa_passed to false
        jq --arg id "$JUST_COMPLETED_ID" \
          '(.userStories[] | select(.id == $id)) |= (.passes = false | .qa_passed = false)' \
          "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"

        # Log failure
        echo "" >> "$PROGRESS_FILE"
        echo "## QA FAILURE - $JUST_COMPLETED_ID" >> "$PROGRESS_FILE"
        echo "- Story: $JUST_COMPLETED_TITLE" >> "$PROGRESS_FILE"
        echo "- Failure: Dev server failed to start" >> "$PROGRESS_FILE"
        echo "---" >> "$PROGRESS_FILE"

        REMAINING_AFTER=$((REMAINING_AFTER + 1))
        COMPLETED_THIS_ITERATION=$((COMPLETED_THIS_ITERATION - 1))
        NO_PROGRESS_COUNT=$((NO_PROGRESS_COUNT + 1))
        ITERATION_QA_STATUS="failed"
        ITERATION_IMPL_STATUS="pending"  # Rollback means no real progress
      else
        # Create screenshots directory in worktree spec folder
        SCREENSHOTS_DIR="$WORKTREE_PATH/agent-os/specs/$SPEC_NAME/screenshots"
        mkdir -p "$SCREENSHOTS_DIR"

        # Get story acceptance criteria
        STORY_ACCEPTANCE=$(jq -r --arg id "$JUST_COMPLETED_ID" '.userStories[] | select(.id == $id) | .acceptanceCriteria // []' "$PRD_FILE")
        STORY_DESCRIPTION=$(jq -r --arg id "$JUST_COMPLETED_ID" '.userStories[] | select(.id == $id) | .description // ""' "$PRD_FILE")

        # Create QA prompt
        QA_PROMPT="You are the QA Verifier agent. Your job is to verify that a story was implemented correctly by testing it in the browser.

DEV SERVER URL: http://localhost:$DEV_SERVER_PORT

STORY TO VERIFY:
- ID: $JUST_COMPLETED_ID
- Title: $JUST_COMPLETED_TITLE
- Type: $JUST_COMPLETED_TYPE
- Description: $STORY_DESCRIPTION

ACCEPTANCE CRITERIA:
$STORY_ACCEPTANCE

MANDATORY VERIFICATION STEPS:
1. Use Claude in Chrome or Playwright to navigate to http://localhost:$DEV_SERVER_PORT
2. Navigate to the page related to this story
3. Take a screenshot and save it to: $SCREENSHOTS_DIR/${JUST_COMPLETED_ID}.png
4. Verify each acceptance criterion works as expected
5. If testing forms: submit data and verify it persists
6. If testing edit mode: verify fields pre-populate with saved values

OUTPUT FORMAT (MANDATORY):
If verification PASSES, output exactly:
<qa-result>PASS</qa-result>
<qa-evidence>Brief description of what was verified</qa-evidence>

If verification FAILS, output exactly:
<qa-result>FAIL</qa-result>
<qa-failure-reason>Specific description of what failed</qa-failure-reason>

IMPORTANT: You MUST output one of the above formats. If you cannot verify, output FAIL with reason."

        # Run QA verifier with resilient Chrome/Playwright fallback
        QA_OUTPUT_FILE=$(mktemp)

        run_qa_resilient "$WORKTREE_PATH" "$QA_PROMPT" "$QA_OUTPUT_FILE" "$JUST_COMPLETED_ID"
        QA_EXIT_CODE=$?

        if [ "$QA_METHOD_USED" = "playwright" ]; then
          echo -e "${CYAN}  QA ran via Playwright fallback (Chrome unavailable)${NC}"
        fi

        # Handle QA timeout (both Chrome and Playwright failed)
        if [ $QA_EXIT_CODE -eq 124 ] || [ $QA_EXIT_CODE -eq 137 ]; then
          echo ""
          echo -e "${RED}QA Verifier timed out (both Chrome and Playwright).${NC}"
          # Log and continue
          echo "" >> "$PROGRESS_FILE"
          echo "## QA TIMEOUT - $JUST_COMPLETED_ID" >> "$PROGRESS_FILE"
          echo "- Both Chrome and Playwright QA timed out (${QA_TIMEOUT_SECONDS}s each)" >> "$PROGRESS_FILE"
          echo "- Time: $(date)" >> "$PROGRESS_FILE"
          echo "---" >> "$PROGRESS_FILE"

          # Revert story: set both passes and qa_passed to false
          jq --arg id "$JUST_COMPLETED_ID" \
            '(.userStories[] | select(.id == $id)) |= (.passes = false | .qa_passed = false)' \
            "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"

          REMAINING_AFTER=$((REMAINING_AFTER + 1))
          COMPLETED_THIS_ITERATION=$((COMPLETED_THIS_ITERATION - 1))
          NO_PROGRESS_COUNT=$((NO_PROGRESS_COUNT + 1))
          ITERATION_QA_STATUS="failed"
          ITERATION_IMPL_STATUS="pending"

          rm -f "$QA_OUTPUT_FILE"
          # Kill dev server before continuing
          echo -e "${CYAN}Stopping dev server...${NC}"
          pkill -f "npm.*--port.*$DEV_SERVER_PORT" 2>/dev/null || true
          lsof -ti:$DEV_SERVER_PORT | xargs kill -9 2>/dev/null || true

          # Print summary and continue to next iteration
          FINAL_COMPLETED=$((TOTAL - REMAINING_AFTER))
          print_iteration_summary "$i" "$CURRENT_STORY_ID" "$CURRENT_STORY" "$FINAL_COMPLETED" "$TOTAL" "$ITERATION_IMPL_STATUS" "$ITERATION_COMPONENT_STATUS" "$ITERATION_QA_STATUS"
          sync_spec_to_main
          continue
        fi

        # Check QA result
        if grep -q "<qa-result>PASS</qa-result>" "$QA_OUTPUT_FILE" 2>/dev/null; then
          # Extract evidence
          QA_EVIDENCE=$(grep -A 5 "<qa-evidence>" "$QA_OUTPUT_FILE" | sed 's/<[^>]*>//g' | tr '\n' ' ' | head -c 100)
          ITERATION_QA_EVIDENCE="$QA_EVIDENCE"

          echo ""
          echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
          echo -e "${GREEN}║              QA VERIFICATION PASSED                           ║${NC}"
          echo -e "${GREEN}╠═══════════════════════════════════════════════════════════════╣${NC}"
          echo -e "${GREEN}║${NC}  Story: [$JUST_COMPLETED_ID] $JUST_COMPLETED_TITLE"
          if [ "$QA_METHOD_USED" = "playwright" ]; then
            echo -e "${GREEN}║${NC}  Method: ${CYAN}Playwright fallback${NC} (Chrome unavailable)"
          fi
          if [ -n "$QA_EVIDENCE" ]; then
            echo -e "${GREEN}║${NC}  Evidence: ${QA_EVIDENCE:0:60}"
          fi
          if [ -f "$SCREENSHOTS_DIR/${JUST_COMPLETED_ID}.png" ]; then
            echo -e "${GREEN}║${NC}  Screenshot: ${GREEN}✓${NC} saved"
          else
            echo -e "${GREEN}║${NC}  Screenshot: ${YELLOW}⚠${NC} not saved (non-blocking)"
          fi
          echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"

          # Set qa_passed: true
          jq --arg id "$JUST_COMPLETED_ID" \
            '(.userStories[] | select(.id == $id) | .qa_passed) = true' \
            "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"

          ITERATION_QA_STATUS="passed"
          NO_PROGRESS_COUNT=0  # QA passing IS progress
          rm -f "$QA_OUTPUT_FILE"
          > "$CLAUDE_OUTPUT_FILE"  # Clear to prevent stale COMPLETE signal

        elif grep -q "<qa-result>FAIL</qa-result>" "$QA_OUTPUT_FILE" 2>/dev/null; then
          echo ""
          echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
          echo -e "${RED}║              QA VERIFICATION FAILED                           ║${NC}"
          echo -e "${RED}╠═══════════════════════════════════════════════════════════════╣${NC}"

          FAILURE_REASON=$(grep -A 20 "<qa-failure-reason>" "$QA_OUTPUT_FILE" | grep -B 20 "</qa-failure-reason>" | sed 's/<[^>]*>//g' | head -5)
          echo -e "${RED}║${NC}  Reason: $FAILURE_REASON"
          echo -e "${RED}║${NC}  Reverting story to passes: false"
          echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"

          # Revert story: set both passes and qa_passed to false
          jq --arg id "$JUST_COMPLETED_ID" \
            '(.userStories[] | select(.id == $id)) |= (.passes = false | .qa_passed = false)' \
            "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"

          # Log failure
          echo "" >> "$PROGRESS_FILE"
          echo "## QA FAILURE - $JUST_COMPLETED_ID" >> "$PROGRESS_FILE"
          echo "- Story: $JUST_COMPLETED_TITLE" >> "$PROGRESS_FILE"
          echo "- Failure: $FAILURE_REASON" >> "$PROGRESS_FILE"
          echo "---" >> "$PROGRESS_FILE"

          REMAINING_AFTER=$((REMAINING_AFTER + 1))
          COMPLETED_THIS_ITERATION=$((COMPLETED_THIS_ITERATION - 1))
          NO_PROGRESS_COUNT=$((NO_PROGRESS_COUNT + 1))
          ITERATION_QA_STATUS="failed"
          ITERATION_IMPL_STATUS="pending"  # Rollback means no real progress
          rm -f "$QA_OUTPUT_FILE"
          echo ""
          echo -e "${YELLOW}Story will be re-attempted next iteration...${NC}"

        else
          # CRITICAL: Default to FAIL, not PASS
          echo ""
          echo -e "${RED}✗ QA Verifier did not output a clear result. Assuming FAIL.${NC}"

          # Revert story: set both passes and qa_passed to false
          jq --arg id "$JUST_COMPLETED_ID" \
            '(.userStories[] | select(.id == $id)) |= (.passes = false | .qa_passed = false)' \
            "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"

          echo "" >> "$PROGRESS_FILE"
          echo "## QA UNCLEAR - $JUST_COMPLETED_ID" >> "$PROGRESS_FILE"
          echo "- Story: $JUST_COMPLETED_TITLE" >> "$PROGRESS_FILE"
          echo "- QA Verifier output was ambiguous, defaulting to FAIL" >> "$PROGRESS_FILE"
          echo "---" >> "$PROGRESS_FILE"

          REMAINING_AFTER=$((REMAINING_AFTER + 1))
          COMPLETED_THIS_ITERATION=$((COMPLETED_THIS_ITERATION - 1))
          NO_PROGRESS_COUNT=$((NO_PROGRESS_COUNT + 1))
          ITERATION_QA_STATUS="failed"
          ITERATION_IMPL_STATUS="pending"  # Rollback means no real progress
          rm -f "$QA_OUTPUT_FILE"
          echo ""
          echo -e "${YELLOW}Story will be re-attempted next iteration...${NC}"
        fi
      fi

      # Kill dev server
      echo -e "${CYAN}Stopping dev server...${NC}"
      pkill -f "npm.*--port.*$DEV_SERVER_PORT" 2>/dev/null || true
      # Also kill any node processes on that port
      lsof -ti:$DEV_SERVER_PORT | xargs kill -9 2>/dev/null || true
    else
      # QA not required for non-UI story types
      echo ""
      echo -e "${BLUE}── QA Verification ──${NC}"
      echo -e "  ${CYAN}Skipped${NC} (story type: $JUST_COMPLETED_TYPE - no browser verification required)"
      ITERATION_QA_STATUS="skipped"
    fi

    sync_spec_to_main  # Sync progress back to main repo
  fi

  # =============================================================================
  # ITERATION SUMMARY - Display end-of-iteration status
  # =============================================================================
  FINAL_COMPLETED=$((TOTAL - REMAINING_AFTER))
  print_iteration_summary "$i" "$CURRENT_STORY_ID" "$CURRENT_STORY" "$FINAL_COMPLETED" "$TOTAL" "$ITERATION_IMPL_STATUS" "$ITERATION_COMPONENT_STATUS" "$ITERATION_QA_STATUS"

  echo ""

  # Check for completion signal
  if grep -q "<promise>COMPLETE</promise>" "$CLAUDE_OUTPUT_FILE" 2>/dev/null; then
    echo ""
    echo -e "${BLUE}══ Validating completion claim... ══${NC}"

    # SERVER-SIDE VALIDATION: Don't trust Claude, verify prd.json
    VALIDATED_REMAINING=$(count_remaining "$PRD_FILE")
    VALIDATED_TOTAL=$(jq '.userStories | length' "$PRD_FILE")
    VALIDATED_COMPLETE=$((VALIDATED_TOTAL - VALIDATED_REMAINING))

    if [ "$VALIDATED_REMAINING" -gt 0 ]; then
      echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
      echo -e "${RED}║              COMPLETION CLAIM REJECTED                        ║${NC}"
      echo -e "${RED}╠═══════════════════════════════════════════════════════════════╣${NC}"
      echo -e "${RED}║${NC}  Claude claimed COMPLETE but prd.json validation failed!"
      echo -e "${RED}║${NC}"
      echo -e "${RED}║${NC}  Stories complete (passes: true):  ${GREEN}$VALIDATED_COMPLETE${NC}"
      echo -e "${RED}║${NC}  Stories remaining (passes: false): ${YELLOW}$VALIDATED_REMAINING${NC}"
      echo -e "${RED}║${NC}  Total stories: $VALIDATED_TOTAL"
      echo -e "${RED}║${NC}"
      echo -e "${RED}║${NC}  Claude must update prd.json to mark stories complete!"
      echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
      echo ""
      echo -e "${YELLOW}Ignoring false completion claim. Continuing to next iteration...${NC}"
      sleep 3
      continue  # Don't exit! Force another iteration
    fi

    # VERIFIED - actually complete
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              COMPLETION VALIDATED                             ║${NC}"
    echo -e "${GREEN}╠═══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  All $VALIDATED_TOTAL stories verified: passes: true in prd.json"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    # Sync final state back to main repo
    sync_spec_to_main
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                    Ralph completed all tasks!                 ║${NC}"
    echo -e "${GREEN}╠═══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  Completed at iteration $i of $MAX_ITERATIONS"
    echo -e "${GREEN}║${NC}  Check progress.txt for implementation details"
    echo -e "${GREEN}║${NC}  Worktree: $WORKTREE_PATH"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    # Promote learnings to codebase-wide patterns
    echo ""
    echo "Promoting learnings to codebase-wide patterns..."
    "$PROJECT_ROOT/.claude/scripts/promote-learnings.sh" "$SPEC_NAME" || true
    rm -f "$CLAUDE_OUTPUT_FILE"
    exit 0
  fi

  echo -e "${YELLOW}Iteration $i complete.${NC} Pausing 3 seconds before next iteration..."
  sleep 3
done

# Cleanup temp file
rm -f "$CLAUDE_OUTPUT_FILE"

# Sync any progress back to main repo before exiting
sync_spec_to_main

echo ""
echo -e "${YELLOW}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║              Ralph reached max iterations                     ║${NC}"
echo -e "${YELLOW}╠═══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${YELLOW}║${NC}  Max iterations: $MAX_ITERATIONS"
echo -e "${YELLOW}║${NC}  Check $PROGRESS_FILE for status"
echo -e "${YELLOW}║${NC}  Worktree preserved: $WORKTREE_PATH"
echo -e "${YELLOW}║${NC}  Run again to continue: ./agent-os/ralph.sh $SPEC_NAME"
echo -e "${YELLOW}╚═══════════════════════════════════════════════════════════════╝${NC}"
exit 1
