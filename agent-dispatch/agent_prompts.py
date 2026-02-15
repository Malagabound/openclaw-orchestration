"""Agent prompt assembly module.

Builds structured LLM message lists from base SOP, agent persona,
skill summaries, task description, and working memory entries.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .config import AGENT_SKILLS
from .llm_provider import Message, LLMProvider
from .security import wrap_cross_agent_data

logger = logging.getLogger(__name__)

# Directories relative to project root
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PROMPTS_DIR = os.path.join(_PROJECT_ROOT, "prompts")
_SKILLS_DIR = os.path.join(_PROJECT_ROOT, "skills")


def _read_file(path: str) -> Optional[str]:
    """Read a file and return its contents, or None if not found."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, PermissionError, OSError) as e:
        logger.warning("Could not read %s: %s", path, e)
        return None


def _load_dependency_chain(task_id: int, db_path: Optional[str] = None) -> List[int]:
    """Load the dependency chain for a task (tasks this task depends on).

    Args:
        task_id: The task ID to get dependencies for.
        db_path: Optional database path override.

    Returns:
        List of task IDs in the dependency chain (excluding task_id itself).
    """
    import sqlite3
    from .config import DEFAULT_DB_PATH

    path = db_path or os.environ.get("OPENCLAWD_DB_PATH", DEFAULT_DB_PATH)

    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row

        # Get all tasks this task depends on (direct dependencies only)
        # For deeper chains, could recursively traverse, but direct is sufficient for now
        rows = conn.execute(
            "SELECT depends_on_task_id FROM task_dependencies WHERE task_id = ?",
            (task_id,)
        ).fetchall()

        conn.close()

        return [row[0] for row in rows]
    except Exception as e:
        logger.warning("Failed to load dependency chain for task %s: %s", task_id, e)
        return []


def _load_working_memory_with_dependencies(
    task_id: int,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Load working memory scoped to task and its dependency chain.

    Args:
        task_id: The current task ID.
        db_path: Optional database path override.

    Returns:
        List of working memory entry dicts with key, value, agent_name.
    """
    import sqlite3
    from .config import DEFAULT_DB_PATH

    path = db_path or os.environ.get("OPENCLAWD_DB_PATH", DEFAULT_DB_PATH)

    # Get dependency chain
    dependency_ids = _load_dependency_chain(task_id, db_path)
    all_task_ids = [task_id] + dependency_ids

    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row

        # Build WHERE clause with placeholders
        placeholders = ",".join("?" * len(all_task_ids))
        query = f"""
            SELECT key, value, agent_name
            FROM working_memory
            WHERE task_id IN ({placeholders})
            ORDER BY task_id, id
        """

        rows = conn.execute(query, all_task_ids).fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning(
            "Failed to load working memory for task %s and dependencies: %s",
            task_id, e
        )
        return []


def enforce_context_budget(
    messages: List[Message],
    provider: LLMProvider,
    max_tokens: int,
    skill_parts: List[str],
    task_description: str,
) -> List[Message]:
    """Enforce context budget by trimming prompt parts if needed.

    Strategy:
    1. Count total tokens in current messages
    2. If over budget:
       a. First, remove skill summaries
       b. If still over, truncate task description
       c. If still over after all trimming, raise error

    Args:
        messages: Current message list to check.
        provider: LLMProvider instance for token counting.
        max_tokens: Maximum context tokens allowed.
        skill_parts: List of skill summary strings (for removal if needed).
        task_description: Task description (for truncation if needed).

    Returns:
        Trimmed message list that fits within budget.

    Raises:
        ValueError: If prompt cannot be trimmed to fit budget.
    """
    # Try counting tokens with provider method, fallback to char/4 estimate
    try:
        usage = provider.count_tokens(messages)
        current_tokens = usage.input_tokens
    except Exception as e:
        logger.warning("Token counting failed, using char/4 estimate: %s", e)
        # Estimate: ~4 chars per token
        total_chars = sum(len(m.content or "") for m in messages)
        current_tokens = total_chars // 4

    logger.debug(
        "Context budget check: %d tokens (max: %d)",
        current_tokens, max_tokens
    )

    if current_tokens <= max_tokens:
        return messages  # Within budget, no changes needed

    logger.info(
        "Context budget exceeded (%d > %d), trimming prompt",
        current_tokens, max_tokens
    )

    # Strategy 1: Remove skill summaries
    if skill_parts:
        logger.info("Removing %d skill summaries to reduce context", len(skill_parts))
        # Rebuild system message without skills
        system_msg = messages[0]
        system_content = system_msg.content or ""

        # Remove skill sections
        for skill_part in skill_parts:
            system_content = system_content.replace(skill_part, "")

        # Clean up extra separators
        system_content = system_content.replace("\n\n---\n\n\n\n---\n\n", "\n\n---\n\n")

        messages[0] = Message(role="system", content=system_content)

        # Re-check token count
        try:
            usage = provider.count_tokens(messages)
            current_tokens = usage.input_tokens
        except Exception:
            total_chars = sum(len(m.content or "") for m in messages)
            current_tokens = total_chars // 4

        if current_tokens <= max_tokens:
            logger.info("Context within budget after removing skills")
            return messages

    # Strategy 2: Truncate task description
    user_msg = messages[1]
    user_content = user_msg.content or ""

    # Find task description section (after "# Task:" and metadata)
    lines = user_content.split("\n")
    truncate_target = max_tokens - current_tokens + (len(task_description) // 4)

    if truncate_target > 500:
        # Keep at least 500 chars
        truncated_desc = task_description[:truncate_target] + "\n\n[... description truncated to fit context budget ...]"
        new_user_content = user_content.replace(task_description, truncated_desc)
        messages[1] = Message(role=user_msg.role, content=new_user_content)

        # Re-check
        try:
            usage = provider.count_tokens(messages)
            current_tokens = usage.input_tokens
        except Exception:
            total_chars = sum(len(m.content or "") for m in messages)
            current_tokens = total_chars // 4

        if current_tokens <= max_tokens:
            logger.info("Context within budget after truncating description")
            return messages

    # If we're still over budget, raise error
    logger.error(
        "Cannot trim prompt to fit context budget: %d tokens > %d max",
        current_tokens, max_tokens
    )
    raise ValueError(
        f"Prompt exceeds context budget ({current_tokens} > {max_tokens}) "
        f"and cannot be trimmed further"
    )


def build_prompt(
    agent_name: str,
    task_dict: Dict[str, Any],
    working_memory_entries: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
    provider: Optional[LLMProvider] = None,
) -> List[Message]:
    """Assemble structured messages for an agent LLM call.

    Reads base SOP, agent persona, skill summaries, and injects
    working memory with XML delimiters. Enforces context budget if provider given.

    Args:
        agent_name: Agent identifier (e.g., "research", "product").
        task_dict: Task row as a dictionary with title, description, etc.
        working_memory_entries: List of dicts with key/value from working_memory table.
            If None or empty, will auto-load working memory scoped to task dependencies.
        config: Optional config dict (reserved for future use).
        provider: Optional LLMProvider for context budget enforcement.

    Returns:
        List of Message objects: [system_message, user_message].
    """
    system_parts: List[str] = []

    # 1. Base SOP
    base_sop = _read_file(os.path.join(_PROMPTS_DIR, "base_sop.md"))
    if base_sop:
        system_parts.append(base_sop)

    # 2. Agent persona
    persona = _read_file(os.path.join(_PROMPTS_DIR, f"{agent_name}.md"))
    if persona:
        system_parts.append(persona)

    # 3. Skill summaries (keep references for budget enforcement)
    skill_parts: List[str] = []
    skill_dirs = AGENT_SKILLS.get(agent_name, [])
    for skill_name in skill_dirs:
        skill_md_path = os.path.join(_SKILLS_DIR, skill_name, "SKILL.md")
        skill_content = _read_file(skill_md_path)
        if skill_content:
            skill_part = f"## Skill: {skill_name}\n{skill_content}"
            skill_parts.append(skill_part)
            system_parts.append(skill_part)

    system_content = "\n\n---\n\n".join(system_parts) if system_parts else ""

    # 4. Load working memory with dependency scoping if not provided
    task_id = task_dict.get("id")
    if not working_memory_entries and task_id:
        working_memory_entries = _load_working_memory_with_dependencies(task_id)
        logger.debug(
            "Loaded %d working memory entries for task %s (with dependencies)",
            len(working_memory_entries), task_id
        )

    # 5. User message: task description + working memory
    user_parts: List[str] = []

    # Task description
    task_title = task_dict.get("title", "Untitled Task")
    task_description = task_dict.get("description", "")
    task_domain = task_dict.get("domain", "")
    task_priority = task_dict.get("priority", "")

    user_parts.append(f"# Task: {task_title}")
    if task_domain:
        user_parts.append(f"**Domain:** {task_domain}")
    if task_priority:
        user_parts.append(f"**Priority:** {task_priority}")
    if task_description:
        user_parts.append(f"\n{task_description}")

    # Working memory with XML delimiters
    if working_memory_entries:
        user_parts.append("\n## Working Memory")
        for entry in working_memory_entries:
            key = entry.get("key", "unknown")
            value = entry.get("value", "")
            source = entry.get("agent_name", "unknown")
            wrapped = wrap_cross_agent_data(
                f"{key}: {value}", source_agent=source
            )
            user_parts.append(wrapped)

    user_content = "\n".join(user_parts)

    messages = [
        Message(role="system", content=system_content),
        Message(role="user", content=user_content),
    ]

    # 6. Enforce context budget if provider is given
    if provider is not None:
        capabilities = provider.get_capabilities()
        max_tokens = capabilities.max_context_tokens

        if max_tokens > 0:
            messages = enforce_context_budget(
                messages=messages,
                provider=provider,
                max_tokens=max_tokens,
                skill_parts=skill_parts,
                task_description=task_description,
            )

    return messages
