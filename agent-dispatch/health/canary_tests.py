"""Canary tests for provider health monitoring.

Four canary tests that validate LLM provider capabilities:
  1. test_basic_completion - simple prompt/response
  2. test_tool_calling - tool use request
  3. test_tool_result_handling - tool result continuation
  4. test_structured_output - JSON response validation

Each test returns a dict with:
  - passed (bool)
  - latency_ms (float)
  - error_message (str or None)
  - error_category (str or None)
  - raw_response (str or None)
"""

import json
import time
from typing import Any, Dict, Optional

from ..llm_provider import LLMProvider, Message


# Timeout for each canary test in seconds.
CANARY_TIMEOUT_SECONDS: int = 30


def _make_result(
    passed: bool,
    latency_ms: float,
    error_message: Optional[str] = None,
    error_category: Optional[str] = None,
    raw_response: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a standardized canary test result dict."""
    return {
        "passed": passed,
        "latency_ms": latency_ms,
        "error_message": error_message,
        "error_category": error_category,
        "raw_response": raw_response,
    }


def _classify_error(exc: Exception) -> str:
    """Classify an exception into an error category string."""
    name = type(exc).__name__
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "rate" in msg and "limit" in msg:
        return "rate_limit"
    if "auth" in msg or "key" in msg or "401" in msg or "403" in msg:
        return "auth"
    if "connect" in msg or "network" in msg or "dns" in msg:
        return "network"
    if "500" in msg or "502" in msg or "503" in msg or "504" in msg:
        return "server_error"
    return name


def test_basic_completion(provider: LLMProvider) -> Dict[str, Any]:
    """Call provider.complete() with a simple prompt and validate response.

    Sends a trivial prompt and checks that the response contains
    non-empty content.

    Args:
        provider: An instantiated LLMProvider.

    Returns:
        Canary result dict.
    """
    messages = [Message(role="user", content="Reply with the word 'ok'.")]
    start = time.monotonic()
    try:
        response = provider.complete(messages, max_tokens=64, timeout=CANARY_TIMEOUT_SECONDS)
        latency_ms = (time.monotonic() - start) * 1000.0
        raw = response.content
        if raw and len(raw.strip()) > 0:
            return _make_result(passed=True, latency_ms=latency_ms, raw_response=raw)
        return _make_result(
            passed=False,
            latency_ms=latency_ms,
            error_message="Empty response content",
            error_category="empty_response",
            raw_response=raw,
        )
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000.0
        return _make_result(
            passed=False,
            latency_ms=latency_ms,
            error_message=str(exc),
            error_category=_classify_error(exc),
        )


_CANARY_TOOL = {
    "name": "get_weather",
    "description": "Get weather for a city.",
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name"},
        },
        "required": ["city"],
    },
}


def test_tool_calling(provider: LLMProvider) -> Dict[str, Any]:
    """Call provider with tool definitions and validate tool_call in response.

    Sends a prompt that should trigger the provider to emit a tool call,
    then checks that the response contains at least one tool_call entry.

    Args:
        provider: An instantiated LLMProvider.

    Returns:
        Canary result dict.
    """
    messages = [
        Message(role="user", content="What is the weather in Tokyo?"),
    ]
    start = time.monotonic()
    try:
        response = provider.complete(
            messages,
            tools=[_CANARY_TOOL],
            max_tokens=256,
            timeout=CANARY_TIMEOUT_SECONDS,
        )
        latency_ms = (time.monotonic() - start) * 1000.0
        raw = response.content or ""
        tool_calls = response.tool_calls

        if tool_calls and len(tool_calls) > 0:
            return _make_result(
                passed=True,
                latency_ms=latency_ms,
                raw_response=json.dumps(tool_calls, default=str),
            )
        return _make_result(
            passed=False,
            latency_ms=latency_ms,
            error_message="No tool_calls in response",
            error_category="missing_tool_call",
            raw_response=raw,
        )
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000.0
        return _make_result(
            passed=False,
            latency_ms=latency_ms,
            error_message=str(exc),
            error_category=_classify_error(exc),
        )


def test_tool_result_handling(provider: LLMProvider) -> Dict[str, Any]:
    """Send a tool result back to the provider and validate continuation.

    Simulates a full tool-use round trip: user asks question, assistant
    requests tool, user supplies tool result, assistant produces final
    answer.  Validates that the final response has non-empty content.

    Args:
        provider: An instantiated LLMProvider.

    Returns:
        Canary result dict.
    """
    messages = [
        Message(role="user", content="What is the weather in Tokyo?"),
        Message(
            role="assistant",
            content="",
            tool_calls=[{
                "id": "canary_tool_1",
                "name": "get_weather",
                "input": {"city": "Tokyo"},
            }],
        ),
        Message(
            role="user",
            content="",
            tool_results=[{
                "tool_use_id": "canary_tool_1",
                "content": '{"temperature": "22C", "conditions": "sunny"}',
            }],
        ),
    ]
    start = time.monotonic()
    try:
        response = provider.complete(messages, max_tokens=256, timeout=CANARY_TIMEOUT_SECONDS)
        latency_ms = (time.monotonic() - start) * 1000.0
        raw = response.content
        if raw and len(raw.strip()) > 0:
            return _make_result(passed=True, latency_ms=latency_ms, raw_response=raw)
        return _make_result(
            passed=False,
            latency_ms=latency_ms,
            error_message="Empty response after tool result",
            error_category="empty_response",
            raw_response=raw,
        )
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000.0
        return _make_result(
            passed=False,
            latency_ms=latency_ms,
            error_message=str(exc),
            error_category=_classify_error(exc),
        )


def test_structured_output(provider: LLMProvider) -> Dict[str, Any]:
    """Request a JSON response and validate it is parseable.

    Asks the provider to respond with a JSON object and verifies that
    the returned content can be parsed by json.loads().

    Args:
        provider: An instantiated LLMProvider.

    Returns:
        Canary result dict.
    """
    messages = [
        Message(
            role="user",
            content=(
                "Respond with ONLY a valid JSON object (no markdown, no explanation). "
                'Example: {"status": "ok", "value": 42}'
            ),
        ),
    ]
    start = time.monotonic()
    try:
        response = provider.complete(messages, max_tokens=128, timeout=CANARY_TIMEOUT_SECONDS)
        latency_ms = (time.monotonic() - start) * 1000.0
        raw = response.content or ""
        # Strip potential markdown fences
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (the fences)
            inner = "\n".join(lines[1:-1] if len(lines) > 2 else lines[1:])
            cleaned = inner.strip()

        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as parse_exc:
            return _make_result(
                passed=False,
                latency_ms=latency_ms,
                error_message=f"Response is not valid JSON: {parse_exc}",
                error_category="invalid_json",
                raw_response=raw,
            )

        if isinstance(parsed, dict):
            return _make_result(passed=True, latency_ms=latency_ms, raw_response=raw)
        return _make_result(
            passed=False,
            latency_ms=latency_ms,
            error_message=f"Response is JSON but not an object (got {type(parsed).__name__})",
            error_category="invalid_json",
            raw_response=raw,
        )
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000.0
        return _make_result(
            passed=False,
            latency_ms=latency_ms,
            error_message=str(exc),
            error_category=_classify_error(exc),
        )


# All canary tests in execution order.
ALL_CANARY_TESTS = [
    ("basic_completion", test_basic_completion),
    ("tool_calling", test_tool_calling),
    ("tool_result_handling", test_tool_result_handling),
    ("structured_output", test_structured_output),
]
