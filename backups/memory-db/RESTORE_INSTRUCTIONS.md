# Memory Database Restore Instructions

## Quick Restore
1. Stop OpenClaw if running: `openclaw gateway stop`
2. Navigate to workspace: `cd ~/.openclaw/workspace`
3. Backup current memory-db: `mv memory-db memory-db.backup`
4. Copy backup files: `cp -r backups/memory-db/memory_backup_YYYYMMDD_HHMMSS memory-db`
5. Rename database files:
   - `mv conversations.db.backup conversations.db` (if needed)
6. Start OpenClaw: `openclaw gateway start`
7. Test: `cd memory-db && python3 memory_cli.py stats`

## Verify Restore
```bash
cd memory-db
python3 test_memory.py
python3 memory_cli.py stats
```

## If Restore Fails
1. Stop OpenClaw
2. Remove corrupted memory-db: `rm -rf memory-db`
3. Reinitialize: `mkdir memory-db`
4. Copy schema: `cp memory-db-backup/schema.sql memory-db/`
5. Initialize: `cd memory-db && python3 memory_manager.py`
6. Import from daily memory files if needed

## Database Schema Recreation
```bash
cd memory-db
sqlite3 conversations.db < schema.sql
```

## Testing
- `memory_cli.py stats` - Should show conversation counts
- `memory_cli.py search --query "test"` - Should return results
- `auto_memory.py` - Should run without errors

---
Created: 2026-02-13T16:17:45.030987
System: Darwin 25.2.0
