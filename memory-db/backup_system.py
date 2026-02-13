#!/usr/bin/env python3
"""
Memory Database Backup System
Following pattern from YouTube video - databases to Google Drive, code to GitHub
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

import shutil
import json
from datetime import datetime
from pathlib import Path
from typing import Dict

class MemoryBackup:
    def __init__(self):
        self.workspace_root = Path(__file__).parent.parent
        self.memory_db_dir = Path(__file__).parent
        self.backup_dir = self.workspace_root / "backups" / "memory-db"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
    def backup_database_files(self) -> str:
        """Backup database files with timestamp (like Google Drive pattern from video)."""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"memory_backup_{timestamp}"
        backup_path = self.backup_dir / backup_name
        backup_path.mkdir(exist_ok=True)
        
        # Files to backup
        db_files = [
            "conversations.db",
            "conversations.db-wal",
            "conversations.db-shm"
        ]
        
        backed_up_files = []
        
        for db_file in db_files:
            source_path = self.memory_db_dir / db_file
            if source_path.exists():
                dest_path = backup_path / db_file
                shutil.copy2(source_path, dest_path)
                backed_up_files.append(db_file)
        
        # Create backup manifest
        manifest = {
            "timestamp": datetime.now().isoformat(),
            "backup_name": backup_name,
            "files": backed_up_files,
            "size_mb": self._calculate_backup_size(backup_path)
        }
        
        manifest_path = backup_path / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        print(f"✅ Database backup created: {backup_path}")
        print(f"   Files: {', '.join(backed_up_files)}")
        print(f"   Size: {manifest['size_mb']:.2f} MB")
        
        return str(backup_path)
    
    def _calculate_backup_size(self, backup_path: Path) -> float:
        """Calculate total size of backup in MB."""
        total_size = 0
        for file_path in backup_path.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size / (1024 * 1024)
    
    def create_restore_instructions(self) -> str:
        """Create restore instructions document (like video user)."""
        
        instructions = """# Memory Database Restore Instructions

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
Created: {timestamp}
System: {system_info}
"""
        
        import platform
        restore_doc = instructions.format(
            timestamp=datetime.now().isoformat(),
            system_info=f"{platform.system()} {platform.release()}"
        )
        
        restore_file = self.backup_dir / "RESTORE_INSTRUCTIONS.md"
        with open(restore_file, 'w') as f:
            f.write(restore_doc)
        
        print(f"✅ Restore instructions created: {restore_file}")
        return str(restore_file)
    
    def git_backup_code(self) -> bool:
        """Backup code files to git (following video pattern)."""
        
        try:
            # Check if we're in a git repo
            git_status = os.system("cd .. && git status > /dev/null 2>&1")
            if git_status != 0:
                print("⚠️  Not in a git repository - code backup skipped")
                return False
            
            # Add memory-db files to git
            os.system("cd .. && git add memory-db/")
            
            # Commit with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_msg = f"Auto-backup: Memory database system - {timestamp}"
            
            commit_status = os.system(f'cd .. && git commit -m "{commit_msg}" > /dev/null 2>&1')
            
            if commit_status == 0:
                print("✅ Code backup committed to git")
                
                # Try to push (don't fail if remote not available)
                push_status = os.system("cd .. && git push > /dev/null 2>&1")
                if push_status == 0:
                    print("✅ Code backup pushed to remote")
                else:
                    print("⚠️  Code committed locally (push failed - no remote?)")
                    
                return True
            else:
                print("ℹ️  No code changes to backup")
                return True
                
        except Exception as e:
            print(f"❌ Git backup failed: {e}")
            return False
    
    def full_backup(self) -> Dict[str, str]:
        """Perform complete backup (database + code)."""
        
        print("🔄 Starting full memory system backup...")
        print("=" * 50)
        
        results = {}
        
        # 1. Backup database files
        results['database_backup'] = self.backup_database_files()
        
        # 2. Create restore instructions
        results['restore_instructions'] = self.create_restore_instructions()
        
        # 3. Git backup code
        results['git_backup'] = self.git_backup_code()
        
        # 4. Cleanup old backups (keep last 10)
        self._cleanup_old_backups()
        
        print("\n✅ Full backup complete!")
        print(f"   Database: {results['database_backup']}")
        print(f"   Instructions: {results['restore_instructions']}")
        print(f"   Git: {'✅' if results['git_backup'] else '❌'}")
        
        return results
    
    def _cleanup_old_backups(self, keep_count: int = 10):
        """Keep only the most recent backups."""
        
        backup_dirs = [d for d in self.backup_dir.iterdir() if d.is_dir() and d.name.startswith("memory_backup_")]
        backup_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        if len(backup_dirs) > keep_count:
            for old_backup in backup_dirs[keep_count:]:
                shutil.rmtree(old_backup)
                print(f"🗑️  Cleaned up old backup: {old_backup.name}")

def main():
    """Run backup from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Memory Database Backup System")
    parser.add_argument('--database-only', action='store_true', help='Backup only database files')
    parser.add_argument('--git-only', action='store_true', help='Backup only code to git')
    
    args = parser.parse_args()
    
    backup = MemoryBackup()
    
    if args.database_only:
        backup.backup_database_files()
        backup.create_restore_instructions()
    elif args.git_only:
        backup.git_backup_code()
    else:
        backup.full_backup()

if __name__ == "__main__":
    main()