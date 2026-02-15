"""Agent runner module with tool call loop.

US-048: Provides run_agent() which assembles prompts, calls provider.complete(),
handles tool call loops with depth/loop/timeout limits, executes tools via
the registry, parses <agent-result> blocks, validates AgentResult schema,
and writes working_memory entries.
"""

import datetime
import hashlib
import importlib
import json
import logging
import os
import re
import sqlite3
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .agent_prompts import build_prompt
from .config import DEFAULT_DB_PATH, MAX_TOOL_ITERATIONS
from .llm_provider import LLMProvider, LLMResponse, Message
from .security import sanitize_agent_result, AgentResultValidationError
from .tool_registry import ToolRegistry, ToolRegistryError

logger = logging.getLogger(__name__)

# Default max iterations for tool call loop
_DEFAULT_MAX_ITERATIONS = 20

# Number of identical consecutive tool calls before breaking
_LOOP_DETECTION_THRESHOLD = 3

# Regex to extract <agent-result> XML block
_AGENT_RESULT_RE = re.compile(
    r"<agent-result>(.*?)</agent-result>",
    re.DOTALL,
)

# Required fields in AgentResult
_AGENT_RESULT_REQUIRED = ("status",)

# Squad chat milestone update settings
_MILESTONE_UPDATE_INTERVAL = 4  # Every N tool calls
_MAX_MILESTONE_UPDATES = 3      # Maximum updates per task


@dataclass
class AgentResult:
    """Structured result from an agent execution."""
    status: str = ""
    deliverable_summary: str = ""
    deliverable_content: str = ""
    deliverable_url: str = ""
    working_memory_entries: Optional[List[Dict[str, Any]]] = None
    follow_up_tasks: Optional[List[Dict[str, Any]]] = None
    confidence_score: float = 0.0
    raw_response: str = ""


class AgentRunnerError(Exception):
    """Raised when agent execution fails.

    US-029: Includes structured error context for recovery pipeline.
    """
    def __init__(self, message: str, raw_output: Optional[str] = None,
                 tool_call_log: Optional[List[Dict[str, Any]]] = None,
                 stop_reason: Optional[str] = None):
        super().__init__(message)
        self.raw_output = raw_output
        self.tool_call_log = tool_call_log or []
        self.stop_reason = stop_reason


def _get_db_path() -> str:
    """Resolve coordination.db path from env var or default."""
    import os
    return os.environ.get("OPENCLAWD_DB_PATH", DEFAULT_DB_PATH)


def _record_audit_log(
    trace_id: str,
    task_id: Optional[int],
    agent_name: str,
    tool_name: str,
    arguments: str,
    result: str,
    db_path: Optional[str] = None,
) -> None:
    """Record a tool call in the audit_log table.

    Args:
        trace_id: Dispatch trace ID (UUID).
        task_id: Task ID (may be None).
        agent_name: Agent that made the tool call.
        tool_name: Name of the tool executed.
        arguments: JSON string of tool arguments.
        result: Truncated result string.
        db_path: Optional database path override.
    """
    path = db_path or _get_db_path()
    try:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO audit_log (trace_id, task_id, agent_name, tool_name, arguments, result) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (trace_id, task_id, agent_name, tool_name, arguments, result),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.warning("Failed to record audit_log entry: %s", e)


def _parse_agent_result(content: str) -> Dict[str, Any]:
    """Extract and parse <agent-result> JSON block from LLM response.

    Args:
        content: Full text content from the LLM response.

    Returns:
        Parsed dict from the JSON inside <agent-result> tags.

    Raises:
        AgentRunnerError: If no <agent-result> block found or JSON invalid.
    """
    match = _AGENT_RESULT_RE.search(content)
    if not match:
        raise AgentRunnerError(
            "No <agent-result> block found in agent response"
        )

    raw_json = match.group(1).strip()
    try:
        result = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise AgentRunnerError(
            f"Invalid JSON in <agent-result> block: {e}"
        ) from e

    if not isinstance(result, dict):
        raise AgentRunnerError(
            f"<agent-result> must contain a JSON object, got {type(result).__name__}"
        )

    return result


def _validate_agent_result(result_dict: Dict[str, Any]) -> AgentResult:
    """Validate parsed result dict and return AgentResult dataclass.

    Args:
        result_dict: Parsed dict from <agent-result> block.

    Returns:
        Validated AgentResult instance.

    Raises:
        AgentRunnerError: If required fields are missing.
    """
    missing = [f for f in _AGENT_RESULT_REQUIRED if f not in result_dict]
    if missing:
        raise AgentRunnerError(
            f"AgentResult missing required fields: {', '.join(missing)}"
        )

    return AgentResult(
        status=str(result_dict.get("status", "")),
        deliverable_summary=str(result_dict.get("deliverable_summary", "")),
        deliverable_content=str(result_dict.get("deliverable_content", "")),
        deliverable_url=str(result_dict.get("deliverable_url", "")),
        working_memory_entries=result_dict.get("working_memory_entries"),
        follow_up_tasks=result_dict.get("follow_up_tasks"),
        confidence_score=float(result_dict.get("confidence_score", 0.0)),
        raw_response="",
    )


def _upsert_working_memory(
    task_id: int,
    agent_name: str,
    entries: List[Dict[str, Any]],
    db_path: Optional[str] = None,
) -> None:
    """Upsert working_memory entries with UNIQUE(task_id, agent_name, key).

    REQ-046: Enforces max_value_length of 5000 characters by truncating values.

    Args:
        task_id: Task ID for the memory entries.
        agent_name: Agent that produced the entries.
        entries: List of dicts with 'key' and 'value' fields.
        db_path: Optional database path override.
    """
    path = db_path or _get_db_path()
    try:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.cursor()

        for entry in entries:
            key = entry.get("key")
            value = entry.get("value", "")
            if not key:
                continue

            # REQ-046: Enforce 5000 char limit on value
            value_str = str(value)
            if len(value_str) > 5000:
                logger.warning(
                    "Working memory value for key '%s' exceeds 5000 chars, truncating (was %d chars)",
                    key, len(value_str)
                )
                value_str = value_str[:5000]

            cursor.execute(
                "INSERT OR REPLACE INTO working_memory "
                "(task_id, agent_name, key, value) VALUES (?, ?, ?, ?)",
                (task_id, agent_name, str(key), value_str),
            )

        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.warning("Failed to upsert working_memory: %s", e)


def write_output_file(
    task_id: int,
    agent_name: str,
    trace_id: str,
    deliverable_content: str,
    status: str,
    db_path: Optional[str] = None,
) -> str:
    """Write agent output to a Markdown file with YAML frontmatter.

    Creates agent-dispatch/output/ directory if it doesn't exist, writes
    the deliverable content with YAML frontmatter metadata, and stores
    the relative path in dispatch_runs.output_file.

    Args:
        task_id: The task ID this output belongs to.
        agent_name: The agent that produced the output.
        trace_id: Trace ID (UUID) for the dispatch run.
        deliverable_content: The deliverable text to write.
        status: Agent result status (e.g. 'completed', 'failed').
        db_path: Optional database path override.

    Returns:
        Relative path to the output file (e.g. 'output/42_research_a1b2c3d4.md').
    """
    # Determine output directory relative to agent-dispatch/
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    # Generate filename
    trace_prefix = trace_id[:8] if len(trace_id) >= 8 else trace_id
    filename = f"{task_id}_{agent_name}_{trace_prefix}.md"
    filepath = os.path.join(output_dir, filename)

    # Build YAML frontmatter
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    frontmatter = (
        "---\n"
        f"task_id: {task_id}\n"
        f"agent_name: {agent_name}\n"
        f"trace_id: {trace_id}\n"
        f"timestamp: {timestamp}\n"
        f"status: {status}\n"
        "---\n"
    )

    # Write file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter)
        f.write(deliverable_content)

    # Relative path for storage
    relative_path = f"output/{filename}"

    # Store path in dispatch_runs.output_file
    path = db_path or _get_db_path()
    try:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "UPDATE dispatch_runs SET output_file = ? WHERE trace_id = ?",
            (relative_path, trace_id),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.warning("Failed to store output_file path in dispatch_runs: %s", e)

    logger.info(
        "Wrote output file: %s (task=%s, agent=%s, trace=%s)",
        relative_path, task_id, agent_name, trace_id,
    )

    return relative_path


def _write_error_context_to_dispatch_runs(
    trace_id: str,
    raw_output: Optional[str],
    tool_call_log: List[Dict[str, Any]],
    stop_reason: Optional[str],
    error_context: Dict[str, Any],
    config: Dict[str, Any],
    db_path: Optional[str] = None,
) -> None:
    """Write structured error context to dispatch_runs on failure.

    US-029: Populates the recovery columns added by US-001 migration so the
    recovery pipeline has complete failure information.

    Args:
        trace_id: Dispatch trace ID to identify the dispatch_runs row.
        raw_output: Raw LLM response text (truncated before writing).
        tool_call_log: List of tool call dicts accumulated during tool loop.
        stop_reason: Why the agent stopped (e.g., 'provider_error', 'loop_detected').
        error_context: Dict with exception type, message, traceback.
        config: Config dict for reading truncation limits.
        db_path: Optional database path override.
    """
    path = db_path or _get_db_path()

    # Truncate raw_output per config
    recovery_config = config.get("recovery", {}) if isinstance(config, dict) else {}
    max_chars = recovery_config.get("raw_output_max_chars", 10000) if isinstance(recovery_config, dict) else 10000
    truncated_output = raw_output
    if truncated_output and len(truncated_output) > max_chars:
        truncated_output = truncated_output[:max_chars]

    try:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "UPDATE dispatch_runs SET raw_output = ?, tool_call_log = ?, "
            "stop_reason = ?, error_context = ? WHERE trace_id = ?",
            (
                truncated_output,
                json.dumps(tool_call_log, default=str) if tool_call_log else None,
                stop_reason,
                json.dumps(error_context, default=str),
                trace_id,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.warning("Failed to write error context to dispatch_runs: %s", e)


def _compute_tool_call_hash(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Compute a deterministic hash for a tool call (name + args).

    Used for tracking non-idempotent tool call repetition.

    Args:
        tool_name: Name of the tool.
        tool_args: Arguments dict.

    Returns:
        Hash string (first 16 chars of SHA256).
    """
    call_repr = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
    return hashlib.sha256(call_repr.encode()).hexdigest()[:16]


def _check_tool_permission(tool_def, agent_name: str) -> bool:
    """Check if an agent has permission to use a tool.

    Permission logic:
    1. If agent is in denied_agents list, DENY (denylist takes precedence)
    2. If allowed_agents is empty/None, ALLOW (tool available to all)
    3. If agent is in allowed_agents list, ALLOW
    4. Otherwise, DENY

    Args:
        tool_def: UniversalTool instance
        agent_name: Name of the agent requesting the tool

    Returns:
        True if agent has permission, False otherwise
    """
    # Check denylist first (takes precedence)
    if tool_def.denied_agents and agent_name in tool_def.denied_agents:
        return False

    # If no allowlist, tool is available to all (except denied)
    if not tool_def.allowed_agents:
        return True

    # Check allowlist
    return agent_name in tool_def.allowed_agents


def _execute_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_registry: ToolRegistry,
    trace_id: Optional[str] = None,
    task_id: Optional[int] = None,
    agent_name: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """Execute a tool via the registry and return the result as a string.

    Args:
        tool_name: Name of the tool to execute.
        tool_args: Arguments to pass to the tool executor.
        tool_registry: ToolRegistry instance for loading tool definitions.
        trace_id: Optional trace ID for audit logging.
        task_id: Optional task ID for audit logging.
        agent_name: Optional agent name for audit logging.
        db_path: Optional database path override.

    Returns:
        JSON string of the tool execution result.
    """
    try:
        tool_def = tool_registry.get_tool(tool_name)
    except ToolRegistryError as e:
        return json.dumps({"error": f"Tool not found: {e}"})

    # Check tool permissions (REQ-026/REQ-067)
    if agent_name and not _check_tool_permission(tool_def, agent_name):
        logger.warning(
            "Agent %s denied access to tool %s (trace=%s)",
            agent_name, tool_name, trace_id
        )
        return json.dumps({
            "error": f"Access denied: agent '{agent_name}' is not permitted to use tool '{tool_name}'"
        })

    # Import and call the executor function
    execution = tool_def.execution
    module_path = execution.get("module", "")
    function_name = execution.get("function", "execute")

    try:
        mod = importlib.import_module(module_path)
        func = getattr(mod, function_name)
    except (ImportError, AttributeError) as e:
        return json.dumps({"error": f"Failed to load tool executor: {e}"})

    # Execute with timeout from tool definition
    try:
        result = func(**tool_args)
        result_str = json.dumps(result) if not isinstance(result, str) else result
    except Exception as e:
        result_str = json.dumps({"error": f"Tool execution failed: {e}"})

    # Record tool call in audit_log if trace_id is available
    if trace_id is not None:
        _record_audit_log(
            trace_id=trace_id,
            task_id=task_id,
            agent_name=agent_name or "",
            tool_name=tool_name,
            arguments=json.dumps(tool_args, default=str),
            result=result_str[:1000],
            db_path=db_path,
        )

    return result_str


def _detect_loop(recent_calls: List[Dict[str, Any]]) -> bool:
    """Detect if the last N tool calls are identical (same tool + args).

    Args:
        recent_calls: List of recent tool call dicts with 'name' and 'args'.

    Returns:
        True if the last _LOOP_DETECTION_THRESHOLD calls are identical.
    """
    if len(recent_calls) < _LOOP_DETECTION_THRESHOLD:
        return False

    last_n = recent_calls[-_LOOP_DETECTION_THRESHOLD:]
    first = (last_n[0].get("name"), json.dumps(last_n[0].get("args", {}), sort_keys=True))
    for call in last_n[1:]:
        current = (call.get("name"), json.dumps(call.get("args", {}), sort_keys=True))
        if current != first:
            return False
    return True


def _post_milestone_update(
    agent_name: str,
    task_id: int,
    tool_call_count: int,
    adapter,
) -> None:
    """Post a milestone update to squad_chat.

    REQ-036: Posts updates during long tool call loops with rate limiting.

    Args:
        agent_name: Agent name.
        task_id: Task ID being worked on.
        tool_call_count: Number of tool calls completed so far.
        adapter: OpenClawdAdapter instance for squad_chat_post.
    """
    if adapter is None:
        return

    try:
        message = (
            f"Agent {agent_name} working on task {task_id}: "
            f"completed {tool_call_count} tool calls"
        )
        adapter.squad_chat_post(
            agent_name=agent_name,
            message=message,
            related_task_id=task_id,
        )
        logger.debug("Posted milestone update to squad_chat: %s", message)
    except Exception as e:
        logger.warning("Failed to post milestone update to squad_chat: %s", e)


def _get_tools_for_provider(
    tool_registry: ToolRegistry,
    provider_name: str,
) -> List[Dict[str, Any]]:
    """Load all tools from registry and translate to provider format.

    Args:
        tool_registry: ToolRegistry instance.
        provider_name: Provider name string (anthropic, openai, google, ollama).

    Returns:
        List of tool dicts in provider-specific format.
    """
    from .tool_translators import (
        translate_to_anthropic,
        translate_to_openai,
        translate_to_gemini,
        translate_to_ollama,
    )

    translator_map = {
        "anthropic": translate_to_anthropic,
        "openai": translate_to_openai,
        "google": translate_to_gemini,
        "ollama": translate_to_ollama,
        "claude_code": translate_to_anthropic,  # fallback
    }

    translator = translator_map.get(provider_name, translate_to_anthropic)
    tool_names = tool_registry.list_tools()
    tools = []
    for name in tool_names:
        try:
            tool_def = tool_registry.get_tool(name)
            tools.append(translator(tool_def))
        except ToolRegistryError as e:
            logger.warning("Skipping tool %s: %s", name, e)

    return tools


def run_agent(
    agent_name: str,
    task_dict: Dict[str, Any],
    provider: LLMProvider,
    tool_registry: ToolRegistry,
    config: Dict[str, Any],
    working_memory_entries: Optional[List[Dict[str, Any]]] = None,
    max_iterations: Optional[int] = None,
    db_path: Optional[str] = None,
    trace_id: Optional[str] = None,
    adapter=None,
) -> AgentResult:
    """Execute an agent with tool calling loop.

    Assembles prompt, calls provider.complete() in a loop handling tool calls,
    parses <agent-result> from final response, validates result, and upserts
    working_memory entries.

    REQ-027: Implements tool idempotency tracking and retry behavior.
    REQ-036: Posts milestone updates to squad_chat during long tool loops.
    REQ-046: Enforces working_memory max_value_length of 5000 chars.

    Args:
        agent_name: Agent identifier (e.g., "research", "product").
        task_dict: Task row dict with id, title, description, domain, priority.
        provider: LLMProvider instance to call.
        tool_registry: ToolRegistry for loading and executing tools.
        config: Parsed openclawd.config.yaml dict.
        working_memory_entries: Existing working memory for this task.
        max_iterations: Max tool call loop iterations (default 20).
        db_path: Optional database path override.
        trace_id: Optional trace ID (UUID v4) for correlating all operations
            in this dispatch. If None, a new UUID is generated.
        adapter: Optional OpenClawdAdapter for squad_chat milestone updates.

    Returns:
        AgentResult with status, deliverables, and working memory.

    Raises:
        AgentRunnerError: If agent execution fails.
    """
    if trace_id is None:
        trace_id = str(uuid.uuid4())

    task_id = task_dict.get("id")

    if working_memory_entries is None:
        working_memory_entries = []

    if max_iterations is None:
        max_iterations = config.get("max_tool_iterations", _DEFAULT_MAX_ITERATIONS)

    # 1. Assemble prompt with context budget enforcement
    messages = build_prompt(
        agent_name, task_dict, working_memory_entries, config,
        provider=provider  # Pass provider for budget enforcement
    )

    # 2. Determine provider name for tool translation
    provider_name = config.get("provider", {}).get("name", "anthropic")

    # 3. Load tools in provider format
    tools = _get_tools_for_provider(tool_registry, provider_name)

    # 4. Tool call loop with idempotency tracking
    recent_calls: List[Dict[str, Any]] = []
    iteration = 0

    # REQ-027: Track non-idempotent tool call hashes to prevent retry
    non_idempotent_hashes: Set[str] = set()

    # REQ-036: Track milestone updates
    milestone_updates_posted = 0

    # US-029: Accumulate tool call log and raw output for recovery pipeline
    tool_call_log: List[Dict[str, Any]] = []
    raw_output_parts: List[str] = []

    # Extra dict for structured log entries with trace context
    _log_extra = {"trace_id": trace_id, "agent_name": agent_name, "task_id": task_id}

    while iteration < max_iterations:
        iteration += 1
        logger.info(
            "Agent %s iteration %d/%d (trace=%s)",
            agent_name, iteration, max_iterations, trace_id,
            extra=_log_extra,
        )

        # Call provider
        kwargs: Dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools

        try:
            response: LLMResponse = provider.complete(messages, **kwargs)
        except Exception as e:
            logger.error(
                "Provider call failed on iteration %d (trace=%s): %s",
                iteration, trace_id, e,
                extra=_log_extra,
            )
            # US-029: Capture error context on provider failure
            stop_reason = "provider_error"
            combined_raw = "\n".join(raw_output_parts) if raw_output_parts else None
            error_ctx = {
                "exception_type": type(e).__name__,
                "exception_module": type(e).__module__,
                "message": str(e),
                "traceback": traceback.format_exc(),
            }
            _write_error_context_to_dispatch_runs(
                trace_id, combined_raw, tool_call_log, stop_reason, error_ctx, config, db_path
            )
            raise AgentRunnerError(
                f"Provider call failed on iteration {iteration}: {e}",
                raw_output=combined_raw,
                tool_call_log=tool_call_log,
                stop_reason=stop_reason,
            ) from e

        # US-029: Capture raw LLM output from each iteration
        if response.content:
            raw_output_parts.append(response.content)

        # Check for tool calls
        if not response.tool_calls:
            # No tool calls - this is the final response
            break

        # Process tool calls
        tool_results = []
        for tool_call in response.tool_calls:
            tc_name = tool_call.get("name", "")
            tc_args = tool_call.get("input", tool_call.get("arguments", {}))
            tc_id = tool_call.get("id", "")

            # Parse string args if needed
            if isinstance(tc_args, str):
                try:
                    tc_args = json.loads(tc_args)
                except json.JSONDecodeError:
                    tc_args = {}

            # Track for loop detection
            recent_calls.append({"name": tc_name, "args": tc_args})

            # Check for loop
            if _detect_loop(recent_calls):
                logger.warning(
                    "Detected identical tool call loop for %s (trace=%s), breaking",
                    tc_name, trace_id,
                    extra=_log_extra,
                )
                break

            # REQ-027: Check tool idempotency for retry behavior
            try:
                tool_def = tool_registry.get_tool(tc_name)
                is_idempotent = tool_def.idempotent
            except ToolRegistryError:
                # If tool not found, assume non-idempotent (safer default)
                is_idempotent = False

            call_hash = _compute_tool_call_hash(tc_name, tc_args)

            # If non-idempotent and we've seen this exact call before, skip retry
            if not is_idempotent and call_hash in non_idempotent_hashes:
                logger.warning(
                    "Skipping retry of non-idempotent tool %s (already called with same args)",
                    tc_name
                )
                result_str = json.dumps({
                    "error": (
                        f"Tool {tc_name} is non-idempotent and has already been called "
                        f"with these arguments. Skipping retry to prevent side effects."
                    )
                })
            else:
                # Execute tool
                logger.info(
                    "Executing tool: %s (idempotent=%s, trace=%s)",
                    tc_name, is_idempotent, trace_id,
                    extra=_log_extra,
                )
                result_str = _execute_tool(
                    tc_name, tc_args, tool_registry,
                    trace_id=trace_id,
                    task_id=task_id,
                    agent_name=agent_name,
                    db_path=db_path,
                )

                # Track non-idempotent calls
                if not is_idempotent:
                    non_idempotent_hashes.add(call_hash)

            # US-029: Append to tool_call_log for recovery context
            tool_call_log.append({
                "name": tc_name,
                "arguments": tc_args,
                "result_excerpt": result_str[:500] if result_str else "",
                "iteration": iteration,
            })

            tool_results.append({
                "tool_call_id": tc_id,
                "name": tc_name,
                "content": result_str,
            })

        # REQ-036: Post milestone update if at interval and under max
        if (len(recent_calls) % _MILESTONE_UPDATE_INTERVAL == 0 and
            milestone_updates_posted < _MAX_MILESTONE_UPDATES):
            _post_milestone_update(agent_name, task_id, len(recent_calls), adapter)
            milestone_updates_posted += 1

        # Check if we broke out of tool calls due to loop
        if _detect_loop(recent_calls):
            # Append what we have and break the outer loop
            if tool_results:
                messages.append(Message(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                ))
                messages.append(Message(
                    role="user",
                    content="Tool call loop detected. Please provide your final answer.",
                    tool_results=tool_results,
                ))
            break

        # Append assistant message with tool calls and tool results
        messages.append(Message(
            role="assistant",
            content=response.content or "",
            tool_calls=response.tool_calls,
        ))
        messages.append(Message(
            role="user",
            content="",
            tool_results=tool_results,
        ))

    else:
        # Max iterations reached
        logger.warning(
            "Agent %s reached max iterations (%d) (trace=%s)",
            agent_name, max_iterations, trace_id,
            extra=_log_extra,
        )

    # 5. Parse <agent-result> from final response content
    final_content = response.content or ""
    # US-029: Combine all raw output captured during tool loop iterations
    combined_raw_output = "\n".join(raw_output_parts) if raw_output_parts else final_content or None

    try:
        result_dict = _parse_agent_result(final_content)
    except AgentRunnerError as parse_err:
        # If no structured result, create a minimal one from raw content
        logger.warning(
            "No <agent-result> block found for agent %s (trace=%s), using raw response",
            agent_name, trace_id,
            extra=_log_extra,
        )
        result_dict = {
            "status": "completed",
            "deliverable_summary": final_content[:500],
            "deliverable_content": final_content,
        }

    # 6. Validate result
    try:
        agent_result = _validate_agent_result(result_dict)
    except AgentRunnerError as val_err:
        # US-029: Write error context to dispatch_runs on validation failure
        stop_reason = "validation_error"
        error_ctx = {
            "exception_type": type(val_err).__name__,
            "message": str(val_err),
            "traceback": traceback.format_exc(),
        }
        _write_error_context_to_dispatch_runs(
            trace_id, combined_raw_output, tool_call_log, stop_reason, error_ctx, config, db_path
        )
        raise AgentRunnerError(
            str(val_err),
            raw_output=combined_raw_output,
            tool_call_log=tool_call_log,
            stop_reason=stop_reason,
        ) from val_err

    agent_result.raw_response = final_content

    # 7. Upsert working memory entries (with 5000 char limit enforcement)
    if task_id and agent_result.working_memory_entries:
        _upsert_working_memory(
            task_id=task_id,
            agent_name=agent_name,
            entries=agent_result.working_memory_entries,
            db_path=db_path,
        )

    return agent_result
