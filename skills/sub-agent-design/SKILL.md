---
name: sub-agent-design
description: Design and implement specialized sub-agents with persistent domain expertise. Use when creating agent teams, defining agent specializations, or enhancing agent knowledge retention. Covers systemPrompt engineering, domain expertise embedding, and multi-agent coordination.
---

# Sub-Agent Design

Create specialized agents with persistent domain knowledge and clear responsibilities within a multi-agent system.

## Design Principles

### 1. Persistent Knowledge First
**Domain expertise MUST be persistent** - stored where agents can't "forget" it:
- **Core expertise** → systemPrompt (always loaded, never compacted)
- **Deep knowledge** → reference files the agent is instructed to check
- **Tools/workflows** → explicitly listed in systemPrompt with usage instructions

### 2. Clear Specialization
Each agent should own a distinct domain with:
- **Specific metrics and KPIs** they understand
- **Industry terminology** they use fluently  
- **Decision frameworks** for their domain
- **Tool proficiency** for domain-specific tasks

### 3. Identity Reinforcement
Agents must know who they are and who they're NOT:
- Explicit identity declaration
- Clear distinction from other agents
- Role boundaries and responsibilities
- Personality traits that support their function

## Agent Design Process

### Step 1: Define Domain Scope
- What specific knowledge area does this agent own?
- What business goals are they responsible for?
- What metrics/KPIs should they track?
- What tools do they need to be proficient with?

### Step 2: Create Core Knowledge
Build the essential domain expertise into systemPrompt:
- Key concepts and terminology
- Important metrics and frameworks
- Common decision patterns
- Tool usage instructions

### Step 3: Design Reference Knowledge
Create detailed reference files for deep expertise:
- Comprehensive domain guides
- Best practices and methodologies  
- Industry-specific data and insights
- Tool documentation and workflows

### Step 4: Implement and Test
- Deploy with enhanced systemPrompt
- Test domain knowledge retention
- Verify tool usage proficiency
- Validate decision-making quality

## SystemPrompt Template

```
You are [Name] [emoji], the [domain specialist role].

DOMAIN EXPERTISE:
- [Key concept 1]: [definition/importance]
- [Key concept 2]: [definition/importance]
- [Key concept 3]: [definition/importance]

KEY METRICS: [specific metrics they should track]
DECISION FRAMEWORK: [how they evaluate opportunities/problems]
TOOLS: [specific skills/APIs they should use]

PERSONALITY: [traits that support their function]

MISSION: You work for Alan, [specific goal related to their domain]. 

IDENTITY: You are NOT George — George is the main orchestrator agent. You are [Name], a specialist focused on [domain area].

KNOWLEDGE: When you need deep domain knowledge, check references/[domain]-knowledge.md for comprehensive guidance.
```

See [references/domain-examples.md](references/domain-examples.md) for complete domain expertise examples.

## Multi-Agent Coordination

### Agent Hierarchy
- **George** - Orchestrator, handles Alan directly
- **Specialists** - Domain experts bound to Telegram groups
- **Background** - Automated workers (Scout, Keeper, Sentinel)

### Communication Patterns
- Specialists post findings to their Telegram groups
- Cross-domain collaboration happens via George
- Background agents work silently, report issues only

### Knowledge Sharing
- Common frameworks stored in shared references
- Domain-specific knowledge stays with specialists
- George maintains overview of all domains

## Enhancement Workflow

When upgrading existing agents:

1. **Audit current systemPrompt** - What domain knowledge is missing?
2. **Research domain expertise** - What should they know?
3. **Design knowledge architecture** - Core vs. reference knowledge
4. **Update systemPrompt** - Embed core expertise
5. **Create reference files** - Deep domain knowledge
6. **Test and validate** - Verify knowledge retention