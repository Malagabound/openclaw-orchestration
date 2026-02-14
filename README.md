# OpenClaw Orchestration System

Multi-agent orchestrator system for OpenClaw with research workflow automation.

## Architecture

**Core Principle:** Alan talks only to George (orchestrator), all specialist agents work in background.

### Specialist Agents

- **Rex** (Research & Market Analysis) - Market research, competitive analysis, trend monitoring
- **Pixel** (Digital Products) - Product validation, creation, marketplace strategy  
- **Haven** (Real Estate & Investments) - Property analysis, investment opportunities
- **Vault** (Business Acquisition) - Deal analysis, acquisition research
- **Nora** (Operations & Day Job) - QuickBooks, email processing, operational tasks
- **Scout** (Quality & Validation) - Phase 2 validation, quality control
- **Keeper** (Maintenance & Automation) - System health, backups, cron jobs

### Key Components

- **Multi-Agent Orchestrator** (`orchestrator-dashboard/`) - Task coordination system
- **Memory Database** (`memory-db/`) - Hybrid SQLite + vector storage for conversations
- **Research Workflows** - Automated market research and opportunity identification
- **Custom Skills** (`skills/`) - Specialized agent capabilities

### Workflow System

1. **Second Brain** - Research storage and organization with NextJS interface
2. **Morning Brief** - Daily 7AM intelligence briefing via Telegram
3. **Research Factory** - Multi-agent research pipeline 
4. **Market Research Engine** - Automated opportunity identification
5. **Goal-Driven Tasks** - Autonomous task generation advancing business goals
6. **Smart Model Routing** - Cost-optimized AI model usage

## Business Focus

**Primary Goal:** $300k debt elimination + $20k/month passive income

**Research Focus:** 
- 70% Digital Products (debt payoff) - AI tools, OpenClaw templates, developer resources
- 30% SaaS (passive income) - Micro-SaaS for AI/automation space
- **Exclude:** Real estate, crypto, business acquisition (paused)

## Technical Stack

- **Backend:** Python (agent coordination), SQLite (task management), OpenAI embeddings
- **Frontend:** NextJS (Second Brain interface)  
- **Integration:** OpenClaw heartbeat system, Telegram messaging
- **Hosting:** Local development, Netlify for web interfaces

## Repository Structure

```
/orchestrator-dashboard/     # Agent coordination system
/memory-db/                 # Memory database system  
/skills/                    # Custom skills
/RESEARCH_WORKFLOW_SYSTEM.md # Workflow planning document
/ORCHESTRATOR_IMPROVEMENTS.md # Implementation roadmap
/AGENTS.md, SOUL.md, etc.   # Agent configuration files
```

## Status

**Phase 1 Complete:** Multi-agent orchestrator with 7 specialist agents, memory database, coordination dashboard

**Phase 2 In Progress:** Research workflow automation, Second Brain interface, morning briefing system

---

*This system transforms OpenClaw from single-agent assistant to sophisticated multi-agent business intelligence and automation platform.*