#!/usr/bin/env python3
"""
Verify Telegram group setup and configuration.
Usage: python verify_setup.py --group-id "-1003xxxxxxxx"
"""

import json
import subprocess
import sys
import argparse

def get_current_config():
    """Get current OpenClaw configuration."""
    try:
        result = subprocess.run(['openclaw', 'gateway', 'config.get'], 
                              capture_output=True, text=True, check=True)
        return json.loads(result.stdout)['result']['config']
    except Exception as e:
        print(f"❌ Error getting current config: {e}")
        return None

def verify_group_setup(group_id):
    """Verify a group is properly configured."""
    print(f"🔍 Verifying setup for group {group_id}...")
    
    config = get_current_config()
    if not config:
        return False
    
    success = True
    
    # Check group registration
    groups = config.get('channels', {}).get('telegram', {}).get('groups', {})
    if group_id not in groups:
        print(f"❌ Group {group_id} not registered in channels.telegram.groups")
        success = False
    else:
        group_config = groups[group_id]
        print(f"✅ Group registered in configuration")
        
        # Check group settings
        if not group_config.get('requireMention') == False:
            print("❌ requireMention should be false")
            success = False
        else:
            print("✅ requireMention = false")
        
        if 'systemPrompt' not in group_config:
            print("❌ No systemPrompt configured")
            success = False
        else:
            prompt = group_config['systemPrompt']
            if len(prompt) < 50:
                print(f"⚠️  SystemPrompt seems short ({len(prompt)} chars)")
            else:
                print("✅ SystemPrompt configured")
    
    # Check agent binding
    bindings = config.get('bindings', [])
    group_bindings = [b for b in bindings if b.get('match', {}).get('peer', {}).get('id') == group_id]
    
    if not group_bindings:
        print(f"❌ No agent binding found for group {group_id}")
        success = False
    elif len(group_bindings) > 1:
        print(f"⚠️  Multiple bindings found for group {group_id}:")
        for binding in group_bindings:
            agent_id = binding.get('agentId', 'unknown')
            print(f"    - {agent_id}")
    else:
        binding = group_bindings[0]
        agent_id = binding.get('agentId', 'unknown')
        print(f"✅ Agent binding: {agent_id}")
        
        # Verify agent exists
        agents = config.get('agents', {}).get('list', [])
        agent_exists = any(a.get('id') == agent_id for a in agents)
        if not agent_exists:
            print(f"❌ Agent '{agent_id}' not found in agents.list")
            success = False
        else:
            print(f"✅ Agent '{agent_id}' exists")
    
    return success

def list_all_groups():
    """List all configured groups."""
    config = get_current_config()
    if not config:
        return
    
    groups = config.get('channels', {}).get('telegram', {}).get('groups', {})
    bindings = config.get('bindings', [])
    
    if not groups:
        print("No groups configured")
        return
    
    print(f"📋 Found {len(groups)} configured group(s):")
    
    for group_id, group_config in groups.items():
        # Find binding
        group_bindings = [b for b in bindings if b.get('match', {}).get('peer', {}).get('id') == group_id]
        
        if group_bindings:
            agent_id = group_bindings[0].get('agentId', 'unknown')
        else:
            agent_id = 'NO BINDING'
        
        require_mention = group_config.get('requireMention', True)
        has_prompt = 'systemPrompt' in group_config
        
        print(f"  {group_id}:")
        print(f"    Agent: {agent_id}")
        print(f"    Require mention: {require_mention}")
        print(f"    Has systemPrompt: {has_prompt}")

def main():
    parser = argparse.ArgumentParser(description='Verify Telegram group configuration')
    parser.add_argument('--group-id', help='Group ID to verify')
    parser.add_argument('--list', action='store_true', help='List all configured groups')
    
    args = parser.parse_args()
    
    if args.list:
        list_all_groups()
        return 0
    
    if not args.group_id:
        print("❌ --group-id is required (or use --list)")
        return 1
    
    success = verify_group_setup(args.group_id)
    
    if success:
        print(f"\n✅ Group {args.group_id} is properly configured")
        return 0
    else:
        print(f"\n❌ Group {args.group_id} has configuration issues")
        return 1

if __name__ == '__main__':
    sys.exit(main())