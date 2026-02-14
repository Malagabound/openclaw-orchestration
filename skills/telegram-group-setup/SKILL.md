---
name: telegram-group-setup
description: Automate OpenClaw Telegram group configuration for multi-agent systems. Use when Alan creates a new Telegram group and needs to bind a specialist agent to it. Handles group registration, agent binding, systemPrompt injection, and session cleanup.
---

# Telegram Group Setup

Automate the complete process of setting up new Telegram groups with specialist agents in OpenClaw.

## Quick Start

When Alan creates a new Telegram group:

1. **Get the group ID** - Send a message in the group, check OpenClaw logs for the group ID (starts with `-1003`)

2. **Use the gateway tool to configure** - Apply the configuration patch with agent binding and systemPrompt:
   ```bash
   gateway config.patch --raw '{"channels":{"telegram":{"groups":{"GROUP_ID":{"requireMention":false,"systemPrompt":"AGENT_PROMPT"}}}},"bindings":[{"agentId":"AGENT_ID","match":{"channel":"telegram","peer":{"kind":"group","id":"GROUP_ID"}}}]}'
   ```

3. **Test the setup** - Send a test message in the group to verify the correct agent responds.

## Supported Agents

See [references/agents.md](references/agents.md) for complete agent definitions and systemPrompt templates.

## Manual Process

If you need to understand or customize the process, see [references/manual-steps.md](references/manual-steps.md) for the complete step-by-step procedure.

## Troubleshooting

**Agent has wrong identity**: Clear existing sessions and restart:
```bash
scripts/cleanup_sessions.py --agent-id "agent_name"
```

**Group not responding**: Verify group registration and bindings:
```bash
scripts/verify_setup.py --group-id "-1003xxxxxxxxx"
```