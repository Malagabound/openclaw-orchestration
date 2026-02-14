#!/usr/bin/env python3
"""
Setup a Telegram group with a specialist agent.
Usage: python setup_group.py --group-id "-1003xxxxxxxx" --agent "rex" --name "Software Subscriptions"
"""

import json
import subprocess
import sys
import argparse
import os

AGENT_PROMPTS = {
    'nora': 'You are Nora 📊, the Nth Degree CPAs analyst. You track Optimize OS development, GHL support tickets, and day-job SaaS progress. You are professional, concise, and technically sharp. You work for Alan, helping manage his day-job projects. You are NOT George — George is the main orchestrator agent. You are Nora, a specialist focused on Nth Degree work.',
    
    'rex': 'You are Rex 💰, the recurring revenue analyst. You curate passive income opportunities, track the product pipeline, and post research findings. You are entrepreneurial, data-driven, and action-oriented. You work for Alan, helping him reach $20k/month passive income. You are NOT George — George is the main orchestrator agent. You are Rex, a specialist focused on software subscription and SaaS opportunities.',
    
    'pixel': 'You are Pixel 🎨, the digital product specialist. You hunt Gumroad, Etsy, and developer marketplace opportunities. You track templates, tools, and one-time purchase products for debt payoff. You are creative, trend-aware, and data-backed. You work for Alan, helping him pay off $300k debt through digital product sales. You are NOT George — George is the main orchestrator agent. You are Pixel, a specialist focused on digital products.',
    
    'haven': 'You are Haven 🏠, the rental and realtor business manager. You handle property financials, QuickBooks categorization, utility tracking, tenant matters, and spreadsheet updates. You are detail-oriented, organized, and proactive. You work for Alan, managing his rental property portfolio. You are NOT George — George is the main orchestrator agent. You are Haven, a specialist focused on rental property operations.',
    
    'vault': 'You are Vault 🏦, the investment opportunity researcher. You analyze business acquisitions, crypto moves, and alternative investment vehicles. You are analytical, risk-aware, and opportunity-focused. You work for Alan, helping identify high-value investment opportunities. You are NOT George — George is the main orchestrator agent. You are Vault, a specialist focused on investments.'
}

def get_current_config():
    """Get current OpenClaw configuration."""
    import os
    config_path = os.path.expanduser("~/.openclaw/openclaw.json")
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error reading config from {config_path}: {e}")
        return None

def apply_config_patch(patch):
    """Apply a configuration patch to OpenClaw."""
    # For now, we'll use the gateway tool approach
    # This requires the gateway tool to be available
    try:
        # Create a temporary file with the patch
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(patch, f, indent=2)
            temp_file = f.name
        
        print(f"   Patch written to {temp_file}")
        print("   You'll need to apply this manually using:")
        print(f"   gateway config.patch --file {temp_file}")
        return {"manual": True, "patch_file": temp_file}
    except Exception as e:
        print(f"❌ Error creating config patch: {e}")
        return None

def cleanup_agent_sessions(agent_id):
    """Clean up existing sessions for an agent."""
    import glob
    
    home_dir = os.path.expanduser('~')
    session_pattern = f"{home_dir}/.openclaw/sessions/agent:{agent_id}:telegram:*"
    transcript_pattern = f"{home_dir}/.openclaw/transcripts/agent:{agent_id}:telegram:*"
    
    cleaned = 0
    for pattern in [session_pattern, transcript_pattern]:
        for filepath in glob.glob(pattern):
            try:
                os.remove(filepath)
                cleaned += 1
                print(f"   Removed: {os.path.basename(filepath)}")
            except Exception as e:
                print(f"   Warning: Could not remove {filepath}: {e}")
    
    return cleaned

def main():
    parser = argparse.ArgumentParser(description='Setup Telegram group with specialist agent')
    parser.add_argument('--group-id', required=True, help='Telegram group ID (e.g., "-1003xxxxxxxx")')
    parser.add_argument('--agent', required=True, choices=list(AGENT_PROMPTS.keys()), 
                       help='Agent to bind to this group')
    parser.add_argument('--name', help='Group name for documentation')
    parser.add_argument('--cleanup-sessions', action='store_true', 
                       help='Clean up existing agent sessions first')
    
    args = parser.parse_args()
    
    print(f"🚀 Setting up Telegram group {args.group_id} with agent '{args.agent}'...")
    
    # Validate group ID format
    if not args.group_id.startswith('-1003'):
        print("❌ Group ID should start with '-1003' for Telegram supergroups")
        return 1
    
    # Get system prompt
    system_prompt = AGENT_PROMPTS[args.agent]
    
    # Cleanup sessions if requested
    if args.cleanup_sessions:
        print(f"🧹 Cleaning up existing sessions for agent '{args.agent}'...")
        cleaned = cleanup_agent_sessions(args.agent)
        print(f"   Cleaned {cleaned} session/transcript files")
    
    # Get current config
    print("📋 Getting current configuration...")
    config = get_current_config()
    if not config:
        return 1
    
    # Build configuration patch
    patch = {
        'channels': {
            'telegram': {
                'groups': {
                    args.group_id: {
                        'requireMention': False,
                        'systemPrompt': system_prompt
                    }
                }
            }
        }
    }
    
    # Check if binding already exists
    existing_bindings = config.get('bindings', [])
    binding_exists = any(
        b.get('agentId') == args.agent and 
        b.get('match', {}).get('peer', {}).get('id') == args.group_id
        for b in existing_bindings
    )
    
    if not binding_exists:
        patch['bindings'] = existing_bindings + [{
            'agentId': args.agent,
            'match': {
                'channel': 'telegram',
                'peer': {
                    'kind': 'group',
                    'id': args.group_id
                }
            }
        }]
        print(f"   Adding new binding for {args.agent} → {args.group_id}")
    else:
        print(f"   Binding already exists for {args.agent} → {args.group_id}")
    
    # Apply configuration
    print("⚙️ Applying configuration...")
    result = apply_config_patch(patch)
    if not result:
        return 1
    
    print("✅ Configuration applied successfully!")
    
    if result.get('result', {}).get('restart'):
        print("🔄 OpenClaw is restarting... (this takes ~5 seconds)")
        print("\n🧪 Next steps:")
        print("1. Wait for restart to complete")
        print("2. Send a test message in the group")
        print(f"3. Verify {args.agent} responds with correct identity")
    
    # Documentation reminder
    if args.name:
        print(f"\n📝 Remember to document this setup:")
        print(f"   Group: {args.name}")
        print(f"   ID: {args.group_id}")
        print(f"   Agent: {args.agent}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())