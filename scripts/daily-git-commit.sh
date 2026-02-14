#!/bin/bash

# Daily Git Commit Script for OpenClaw Orchestration
# Runs daily via cron to commit workspace changes
# TWO-WAY SYNC: Handles changes from both local and remote

WORKSPACE_DIR="/Users/macmini/.openclaw/workspace"
LOG_FILE="$WORKSPACE_DIR/scripts/git-commit.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

cd "$WORKSPACE_DIR" || exit 1

# Log start
echo "[$DATE] Starting daily git sync (two-way)..." >> "$LOG_FILE"

# Step 1: Pull any remote changes first
echo "[$DATE] Pulling remote changes..." >> "$LOG_FILE"
if git pull origin main; then
    echo "[$DATE] Successfully pulled remote changes" >> "$LOG_FILE"
else
    echo "[$DATE] WARNING: Pull failed or conflicts detected" >> "$LOG_FILE"
    
    # Check if we have merge conflicts
    if git diff --name-only --diff-filter=U | grep -q .; then
        echo "[$DATE] MERGE CONFLICTS DETECTED - Manual intervention required" >> "$LOG_FILE"
        echo "[$DATE] Conflicted files:" >> "$LOG_FILE"
        git diff --name-only --diff-filter=U >> "$LOG_FILE"
        
        # Send notification about conflicts (could expand this later)
        echo "[$DATE] Aborting sync due to conflicts" >> "$LOG_FILE"
        exit 1
    fi
fi

# Step 2: Check if there are local changes to commit
if git diff --quiet && git diff --staged --quiet; then
    echo "[$DATE] No local changes to commit" >> "$LOG_FILE"
    echo "[$DATE] Sync completed (remote changes only)" >> "$LOG_FILE"
    exit 0
fi

# Step 3: Stage all local changes
echo "[$DATE] Staging local changes..." >> "$LOG_FILE"
git add -A

# Step 4: Create commit message with date and summary of changes
CHANGED_FILES=$(git diff --staged --name-only | wc -l | tr -d ' ')
COMMIT_MSG="Daily update: $DATE

- Modified $CHANGED_FILES files
- Orchestrator system updates
- Memory database updates  
- Agent coordination updates

Auto-sync from workspace"

# Step 5: Commit local changes
if git commit -m "$COMMIT_MSG"; then
    echo "[$DATE] Successfully committed local changes" >> "$LOG_FILE"
    
    # Step 6: Push everything back to GitHub
    if git push origin main; then
        echo "[$DATE] Successfully pushed to GitHub" >> "$LOG_FILE"
        echo "[$DATE] TWO-WAY SYNC COMPLETED SUCCESSFULLY" >> "$LOG_FILE"
    else
        echo "[$DATE] ERROR: Failed to push to GitHub - possible new remote changes" >> "$LOG_FILE"
        echo "[$DATE] Will retry on next sync cycle" >> "$LOG_FILE"
    fi
else
    echo "[$DATE] ERROR: Failed to commit local changes" >> "$LOG_FILE"
fi

echo "[$DATE] Daily git sync completed" >> "$LOG_FILE"