#!/usr/bin/env python3
"""
Clean up OpenClaw agent sessions and transcripts.
Usage: python cleanup_sessions.py --agent-id "rex"
"""

import os
import glob
import argparse
import sys

def cleanup_sessions(agent_id):
    """Remove all session and transcript files for an agent."""
    home_dir = os.path.expanduser('~')
    
    patterns = [
        f"{home_dir}/.openclaw/sessions/agent:{agent_id}:*",
        f"{home_dir}/.openclaw/transcripts/agent:{agent_id}:*"
    ]
    
    total_cleaned = 0
    
    for pattern in patterns:
        files = glob.glob(pattern)
        for filepath in files:
            try:
                os.remove(filepath)
                total_cleaned += 1
                print(f"   Removed: {os.path.basename(filepath)}")
            except Exception as e:
                print(f"   Warning: Could not remove {filepath}: {e}")
    
    return total_cleaned

def list_agent_sessions():
    """List all active agent sessions."""
    home_dir = os.path.expanduser('~')
    session_dir = f"{home_dir}/.openclaw/sessions"
    
    if not os.path.exists(session_dir):
        print("No session directory found")
        return
    
    sessions = glob.glob(f"{session_dir}/agent:*")
    if not sessions:
        print("No agent sessions found")
        return
    
    agents = {}
    for session_path in sessions:
        filename = os.path.basename(session_path)
        if filename.startswith('agent:'):
            parts = filename.split(':')
            if len(parts) >= 2:
                agent_id = parts[1]
                if agent_id not in agents:
                    agents[agent_id] = []
                agents[agent_id].append(filename)
    
    print("Active agent sessions:")
    for agent_id, sessions in agents.items():
        print(f"  {agent_id}: {len(sessions)} session(s)")
        for session in sessions:
            print(f"    {session}")

def main():
    parser = argparse.ArgumentParser(description='Clean up OpenClaw agent sessions')
    parser.add_argument('--agent-id', help='Agent ID to clean up (e.g., "rex", "nora")')
    parser.add_argument('--list', action='store_true', help='List all agent sessions')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without actually deleting')
    
    args = parser.parse_args()
    
    if args.list:
        list_agent_sessions()
        return 0
    
    if not args.agent_id:
        print("❌ --agent-id is required (or use --list to see available agents)")
        return 1
    
    print(f"🧹 Cleaning up sessions for agent '{args.agent_id}'...")
    
    if args.dry_run:
        home_dir = os.path.expanduser('~')
        patterns = [
            f"{home_dir}/.openclaw/sessions/agent:{args.agent_id}:*",
            f"{home_dir}/.openclaw/transcripts/agent:{args.agent_id}:*"
        ]
        
        total = 0
        for pattern in patterns:
            files = glob.glob(pattern)
            for filepath in files:
                total += 1
                print(f"   Would remove: {os.path.basename(filepath)}")
        
        print(f"\nDry run complete. {total} files would be removed.")
        print("Run without --dry-run to actually delete the files.")
        return 0
    
    cleaned = cleanup_sessions(args.agent_id)
    
    if cleaned == 0:
        print(f"   No sessions found for agent '{args.agent_id}'")
    else:
        print(f"✅ Cleaned {cleaned} session/transcript files")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())