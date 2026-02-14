#!/bin/bash

# Daily Git Commit Script for OpenClaw Orchestration
# Runs daily via cron to commit workspace changes

WORKSPACE_DIR="/Users/macmini/.openclaw/workspace"
LOG_FILE="$WORKSPACE_DIR/scripts/git-commit.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

cd "$WORKSPACE_DIR" || exit 1

# Log start
echo "[$DATE] Starting daily git commit..." >> "$LOG_FILE"

# Check if there are changes
if git diff --quiet && git diff --staged --quiet; then
    echo "[$DATE] No changes to commit" >> "$LOG_FILE"
    exit 0
fi

# Stage all changes
git add -A

# Create commit message with date and summary of changes
CHANGED_FILES=$(git diff --staged --name-only | wc -l | tr -d ' ')
COMMIT_MSG="Daily update: $DATE

- Modified $CHANGED_FILES files
- Orchestrator system updates
- Memory database updates  
- Agent coordination updates"

# Commit changes
if git commit -m "$COMMIT_MSG"; then
    echo "[$DATE] Successfully committed changes" >> "$LOG_FILE"
    
    # Push to GitHub
    if git push origin main; then
        echo "[$DATE] Successfully pushed to GitHub" >> "$LOG_FILE"
    else
        echo "[$DATE] ERROR: Failed to push to GitHub" >> "$LOG_FILE"
    fi
else
    echo "[$DATE] ERROR: Failed to commit changes" >> "$LOG_FILE"
fi

echo "[$DATE] Daily git commit completed" >> "$LOG_FILE"