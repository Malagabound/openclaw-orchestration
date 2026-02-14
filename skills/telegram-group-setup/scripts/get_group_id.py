#!/usr/bin/env python3
"""
Get Telegram group ID from recent bot messages.
Usage: python get_group_id.py
"""

import json
import subprocess
import sys
import os

def get_bot_token():
    """Get bot token from OpenClaw config."""
    try:
        result = subprocess.run(['openclaw', 'gateway', 'config.get'], 
                              capture_output=True, text=True, check=True)
        config = json.loads(result.stdout)['result']['config']
        return config['channels']['telegram']['botToken']
    except Exception as e:
        print(f"Error getting bot token: {e}")
        return None

def get_recent_groups(bot_token):
    """Get recent group interactions from Telegram API."""
    import urllib.request
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            
        groups = {}
        for update in data.get('result', []):
            if 'message' in update:
                chat = update['message']['chat']
                if chat['type'] in ['group', 'supergroup']:
                    group_id = str(chat['id'])
                    group_name = chat.get('title', 'Unknown Group')
                    groups[group_id] = group_name
                    
        return groups
    except Exception as e:
        print(f"Error fetching updates: {e}")
        return {}

def main():
    print("🔍 Finding Telegram group IDs...")
    
    bot_token = get_bot_token()
    if not bot_token:
        print("❌ Could not get bot token from OpenClaw config")
        return 1
    
    groups = get_recent_groups(bot_token)
    
    if not groups:
        print("❌ No groups found in recent messages")
        print("\nTips:")
        print("1. Make sure @GeorgeAlanBot was added to the group") 
        print("2. Send a test message in the group")
        print("3. Run this script again")
        return 1
    
    print(f"\n📋 Found {len(groups)} group(s):")
    for group_id, name in groups.items():
        print(f"   {group_id} - {name}")
    
    if len(groups) == 1:
        group_id = list(groups.keys())[0]
        group_name = groups[group_id]
        print(f"\n✅ Single group detected: {group_id}")
        print(f"\nNext step:")
        print(f"   scripts/setup_group.py --group-id \"{group_id}\" --agent \"<agent_name>\" --name \"{group_name}\"")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())