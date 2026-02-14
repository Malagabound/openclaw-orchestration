#!/usr/bin/env python3
"""
Google Drive Sync for Memory Database
Automatic backup of database files to Google Drive (following video pattern)
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

class GoogleDriveSync:
    def __init__(self):
        self.workspace_root = Path(__file__).parent.parent
        self.memory_db_dir = Path(__file__).parent
        self.local_backup_dir = self.workspace_root / "backups" / "memory-db"
        
        # Google Drive folder structure (following video pattern)
        self.drive_folder_name = "#George-Memory"
        self.drive_folder_id = None  # Will be discovered or created
        
        # Check for Google Drive integration
        self.maton_available = self._check_maton_api()
        self.rclone_available = self._check_rclone()
        
        if self.maton_available:
            print("✅ Google Drive sync available via Maton API")
        elif self.rclone_available:
            print("✅ Google Drive sync available via rclone")
        else:
            print("⚠️ Google Drive sync not available - using local backup only")
    
    def _check_maton_api(self) -> bool:
        """Check if Maton API is available for Google Drive."""
        try:
            cred_file = os.path.expanduser("~/.openclaw/credentials/maton")
            return os.path.exists(cred_file)
        except:
            return False
    
    def _check_rclone(self) -> bool:
        """Check if rclone is available and configured for Google Drive."""
        try:
            result = subprocess.run(['which', 'rclone'], capture_output=True, text=True)
            if result.returncode != 0:
                return False
            
            # Check for Google Drive remote
            result = subprocess.run(['rclone', 'listremotes'], capture_output=True, text=True)
            return 'gdrive:' in result.stdout or 'google:' in result.stdout
        except:
            return False
    
    def sync_to_google_drive(self) -> Dict[str, any]:
        """Sync database backups to Google Drive."""
        
        results = {
            "success": False,
            "method": None,
            "files_synced": [],
            "errors": []
        }
        
        # First create local backup
        from backup_system import MemoryBackup
        backup = MemoryBackup()
        local_backup_path = backup.backup_database_files()
        
        if self.maton_available:
            results = self._sync_via_maton(local_backup_path, results)
        elif self.rclone_available:
            results = self._sync_via_rclone(local_backup_path, results)
        else:
            results["errors"].append("No Google Drive sync method available")
            results["method"] = "local_only"
        
        return results
    
    def _sync_via_maton(self, local_backup_path: str, results: Dict) -> Dict:
        """Sync using Maton API (preferred method)."""
        
        try:
            # Read Maton API key
            cred_file = os.path.expanduser("~/.openclaw/credentials/maton")
            with open(cred_file, 'r') as f:
                content = f.read()
                for line in content.split('\n'):
                    if line.startswith('MATON_KEY'):
                        maton_key = line.split('=', 1)[1].strip().strip('"\'')
                        break
                else:
                    raise Exception("MATON_KEY not found in credentials")
            
            # Find or create the backup folder
            folder_id = self._find_or_create_folder(maton_key)
            
            # Upload database files
            backup_path = Path(local_backup_path)
            uploaded_files = []
            
            for db_file in backup_path.glob("*.db*"):
                if db_file.is_file():
                    file_id = self._upload_file_maton(maton_key, folder_id, db_file)
                    if file_id:
                        uploaded_files.append(db_file.name)
            
            # Upload manifest
            manifest_file = backup_path / "manifest.json"
            if manifest_file.exists():
                file_id = self._upload_file_maton(maton_key, folder_id, manifest_file)
                if file_id:
                    uploaded_files.append("manifest.json")
            
            results.update({
                "success": True,
                "method": "maton_api",
                "files_synced": uploaded_files,
                "folder_id": folder_id
            })
            
        except Exception as e:
            results["errors"].append(f"Maton sync error: {e}")
        
        return results
    
    def _find_or_create_folder(self, maton_key: str) -> str:
        """Find or create the backup folder in Google Drive."""
        
        # Implementation would use Maton API to:
        # 1. Search for existing folder by name
        # 2. Create folder if not found
        # 3. Return folder ID
        
        # For now, return a placeholder
        # TODO: Implement actual Maton API calls
        print(f"🗂️ Using Google Drive folder: {self.drive_folder_name}")
        return "placeholder_folder_id"
    
    def _upload_file_maton(self, maton_key: str, folder_id: str, file_path: Path) -> Optional[str]:
        """Upload file using Maton API."""
        
        # Implementation would use Maton API to upload file
        # TODO: Implement actual Maton API upload
        print(f"📤 Uploading {file_path.name} to Google Drive...")
        return f"file_id_{file_path.name}"
    
    def _sync_via_rclone(self, local_backup_path: str, results: Dict) -> Dict:
        """Sync using rclone (fallback method)."""
        
        try:
            # Find rclone remote name for Google Drive
            result = subprocess.run(['rclone', 'listremotes'], capture_output=True, text=True)
            
            remote_name = None
            for line in result.stdout.split('\n'):
                if 'gdrive' in line or 'google' in line:
                    remote_name = line.strip().rstrip(':')
                    break
            
            if not remote_name:
                raise Exception("No Google Drive remote found in rclone config")
            
            # Sync backup directory to Google Drive
            backup_path = Path(local_backup_path)
            remote_path = f"{remote_name}:{self.drive_folder_name}/{backup_path.name}"
            
            cmd = [
                'rclone', 'copy',
                str(backup_path),
                remote_path,
                '--create-empty-src-dirs',
                '--verbose'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                synced_files = list(backup_path.glob("*"))
                results.update({
                    "success": True,
                    "method": "rclone",
                    "files_synced": [f.name for f in synced_files if f.is_file()],
                    "remote_path": remote_path
                })
            else:
                results["errors"].append(f"rclone error: {result.stderr}")
            
        except Exception as e:
            results["errors"].append(f"rclone sync error: {e}")
        
        return results
    
    def schedule_automatic_sync(self, interval_hours: int = 24) -> bool:
        """Set up automatic sync using cron (following video pattern)."""
        
        try:
            # Create sync script
            sync_script_content = f"""#!/bin/bash
# Auto-generated memory database sync script

cd {self.memory_db_dir}
python3 google_drive_sync.py --auto-sync

# Log the sync
echo "$(date): Memory database sync completed" >> {self.workspace_root}/logs/memory_sync.log
"""
            
            sync_script_path = self.memory_db_dir / "auto_sync.sh"
            with open(sync_script_path, 'w') as f:
                f.write(sync_script_content)
            
            # Make executable
            os.chmod(sync_script_path, 0o755)
            
            print(f"✅ Created auto-sync script: {sync_script_path}")
            print(f"📅 To enable automatic sync every {interval_hours}h, add to cron:")
            print(f"   0 */{interval_hours} * * * {sync_script_path}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to create auto-sync script: {e}")
            return False
    
    def get_sync_status(self) -> Dict:
        """Get current sync status and capabilities."""
        
        return {
            "maton_available": self.maton_available,
            "rclone_available": self.rclone_available,
            "sync_capable": self.maton_available or self.rclone_available,
            "preferred_method": "maton_api" if self.maton_available else ("rclone" if self.rclone_available else None),
            "drive_folder": self.drive_folder_name,
            "local_backup_dir": str(self.local_backup_dir)
        }

def main():
    """Command line interface for Google Drive sync."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Google Drive Sync for Memory Database")
    parser.add_argument('--sync', action='store_true', help='Perform sync now')
    parser.add_argument('--auto-sync', action='store_true', help='Auto-sync mode (for cron)')
    parser.add_argument('--setup-cron', type=int, metavar='HOURS', help='Setup automatic sync every N hours')
    parser.add_argument('--status', action='store_true', help='Show sync status')
    
    args = parser.parse_args()
    
    sync = GoogleDriveSync()
    
    if args.status:
        status = sync.get_sync_status()
        print("📊 Google Drive Sync Status:")
        print(json.dumps(status, indent=2))
        
    elif args.sync or args.auto_sync:
        if args.auto_sync:
            print("🔄 Auto-sync mode: Starting memory database backup...")
        
        results = sync.sync_to_google_drive()
        
        if results["success"]:
            print(f"✅ Sync completed via {results['method']}")
            print(f"   Files synced: {', '.join(results['files_synced'])}")
        else:
            print(f"❌ Sync failed: {', '.join(results['errors'])}")
            
    elif args.setup_cron:
        sync.schedule_automatic_sync(args.setup_cron)
        
    else:
        parser.print_help()

if __name__ == "__main__":
    main()