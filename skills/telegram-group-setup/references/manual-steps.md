# Manual Setup Process

Complete step-by-step process for setting up Telegram groups manually.

## Prerequisites

- Alan has created the Telegram group
- @GeorgeAlanBot has been added to the group
- You know which specialist agent should handle this group

## Step 1: Get Group ID

The group ID is required for configuration. Two methods:

### Method A: Monitor OpenClaw Logs
1. Send any message in the new group
2. Check OpenClaw logs for the group ID (negative number like `-1003xxxxxxxxx`)

### Method B: Use Telegram Bot API
```bash
curl "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates" | jq '.result[-1].message.chat.id'
```

## Step 2: Clear Existing Sessions (If Reconfiguring)

If this agent was previously bound to another group, clear stale sessions:

```bash
# Remove session files
rm -f ~/.openclaw/sessions/agent:${AGENT_ID}:telegram:*

# Remove transcript files  
rm -f ~/.openclaw/transcripts/agent:${AGENT_ID}:telegram:*
```

## Step 3: Update OpenClaw Configuration

Use `gateway config.patch` to update the configuration:

```json
{
  "channels": {
    "telegram": {
      "groups": {
        "GROUP_ID": {
          "requireMention": false,
          "systemPrompt": "SYSTEM_PROMPT_TEXT"
        }
      }
    }
  },
  "bindings": [
    {
      "agentId": "AGENT_ID", 
      "match": {
        "channel": "telegram",
        "peer": {
          "kind": "group", 
          "id": "GROUP_ID"
        }
      }
    }
  ]
}
```

### Configuration Fields

**GROUP_ID**: The Telegram group ID (negative number like `-1003xxxxxxxxx`)

**AGENT_ID**: The specialist agent ID (`nora`, `rex`, `pixel`, `haven`, `vault`)

**requireMention**: Set to `false` so agent responds to all messages in the group

**systemPrompt**: The agent's identity prompt (see agents.md for templates)

## Step 4: Apply Configuration

The config patch triggers an automatic restart:

```bash
openclaw gateway config.patch --raw '{"channels": {...}}'
```

Wait for the restart to complete (~5 seconds).

## Step 5: Verify Setup

1. **Send test message** in the group
2. **Verify correct agent responds** with appropriate personality
3. **Check agent knows its identity** (not confused with George)

## Step 6: Update Documentation

Add the new group to your tracking:

- **TOOLS.md** - Add group ID to Telegram section
- **MEMORY.md** - Note the new group purpose and agent assignment

## Common Issues

### Agent Responds as George
**Problem**: Agent reads George's SOUL.md instead of its systemPrompt
**Solution**: Clear sessions and restart gateway

### Agent Doesn't Respond  
**Problem**: Group not properly registered or binding missing
**Solution**: Verify group ID and binding configuration

### Multiple Agents Respond
**Problem**: Group bound to multiple agents 
**Solution**: Check bindings array for duplicates

### Wrong Agent Personality
**Problem**: systemPrompt not specific enough or agent reading wrong context
**Solution**: Update systemPrompt to be more explicit about agent identity

## Configuration Template

Here's a complete configuration template:

```json
{
  "channels": {
    "telegram": {
      "groups": {
        "-1003xxxxxxxxx": {
          "requireMention": false,
          "groupPolicy": "open", 
          "systemPrompt": "You are [Agent Name] [emoji], the [role]. [description]. You work for Alan, helping [goal]. You are NOT George — George is the main orchestrator agent. You are [Agent Name], a specialist focused on [focus area]."
        }
      }
    }
  },
  "bindings": [
    {
      "agentId": "agent_id",
      "match": {
        "channel": "telegram",
        "peer": {
          "kind": "group",
          "id": "-1003xxxxxxxxx" 
        }
      }
    }
  ]
}
```

Replace placeholders with actual values from the agents.md reference.