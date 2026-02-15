"""Anthropic provider adapter for the OpenClawd Agent Dispatch System.

Implements LLMProvider using the Anthropic Python SDK to call Claude models.
"""

import json
from typing import Any, Dict, List, Optional

from .llm_provider import (
    LLMProvider,
    LLMResponse,
    Message,
    ProviderCapabilities,
    TokenUsage,
)


# Model capability map: model prefix -> (max_context_tokens, max_output_tokens)
_MODEL_LIMITS: Dict[str, tuple] = {
    "claude-opus-4": (200000, 32000),
    "claude-sonnet-4": (200000, 64000),
    "claude-3-5-sonnet": (200000, 8192),
    "claude-3-5-haiku": (200000, 8192),
    "claude-3-opus": (200000, 4096),
    "claude-3-sonnet": (200000, 4096),
    "claude-3-haiku": (200000, 4096),
}

# Default limits for unknown Claude models
_DEFAULT_MAX_CONTEXT = 200000
_DEFAULT_MAX_OUTPUT = 8192


class AnthropicProvider(LLMProvider):
    """LLMProvider implementation for Anthropic Claude models."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._client = None  # Lazy init

    def _get_client(self) -> Any:
        """Lazily initialize and return the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ImportError(
                    "anthropic SDK is required for AnthropicProvider. "
                    "Install with: pip install anthropic"
                ) from exc

            kwargs: Dict[str, Any] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def _messages_to_anthropic_format(
        self, messages: List[Message]
    ) -> tuple:
        """Convert Message list to Anthropic API format.

        Returns:
            (system_prompt, anthropic_messages) tuple. System prompt is
            extracted from messages with role='system'. The rest are
            converted to Anthropic user/assistant message dicts.
        """
        system_prompt = ""
        anthropic_messages: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
                continue

            anthropic_msg: Dict[str, Any] = {
                "role": msg.role if msg.role in ("user", "assistant") else "user",
                "content": [],
            }

            # Add text content
            if msg.content:
                anthropic_msg["content"].append({
                    "type": "text",
                    "text": msg.content,
                })

            # Add tool use blocks (for assistant messages with tool calls)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    anthropic_msg["content"].append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "input": tc.get("input", {}),
                    })

            # Add tool results (for user messages responding to tool use)
            if msg.tool_results:
                for tr in msg.tool_results:
                    anthropic_msg["content"].append({
                        "type": "tool_result",
                        "tool_use_id": tr.get("tool_use_id", ""),
                        "content": tr.get("content", ""),
                    })

            # If content list is empty, use plain string
            if not anthropic_msg["content"]:
                anthropic_msg["content"] = msg.content or ""
            elif len(anthropic_msg["content"]) == 1 and anthropic_msg["content"][0].get("type") == "text":
                # Single text block can be simplified to a string
                anthropic_msg["content"] = anthropic_msg["content"][0]["text"]

            anthropic_messages.append(anthropic_msg)

        return system_prompt, anthropic_messages

    def _parse_response(self, response: Any) -> LLMResponse:
        """Convert Anthropic API response to LLMResponse."""
        content_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        usage = None
        if response.usage:
            usage = TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

        return LLMResponse(
            content="\n".join(content_parts),
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
            model=response.model,
            stop_reason=response.stop_reason or "",
        )

    def complete(self, messages: List[Message], **kwargs: Any) -> LLMResponse:
        """Send messages to Claude via anthropic.messages.create().

        Args:
            messages: Conversation history as Message objects.
            **kwargs: Additional params forwarded to messages.create()
                (e.g., temperature, max_tokens, tools).

        Returns:
            LLMResponse with content, tool_calls, usage, model, stop_reason.
        """
        client = self._get_client()
        system_prompt, anthropic_messages = self._messages_to_anthropic_format(messages)

        create_kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.pop("max_tokens", 4096),
        }

        if system_prompt:
            create_kwargs["system"] = system_prompt

        # Forward remaining kwargs (temperature, tools, etc.)
        create_kwargs.update(kwargs)

        response = client.messages.create(**create_kwargs)
        return self._parse_response(response)

    def validate_connection(self) -> bool:
        """Test API connectivity with a minimal messages.create() call."""
        try:
            client = self._get_client()
            response = client.messages.create(
                model=self._model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return response is not None and hasattr(response, "content")
        except Exception:
            return False

    def validate_tool_calling(self) -> bool:
        """Test tool calling with a canary tool call."""
        try:
            client = self._get_client()
            response = client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": "What is 2+2? Use the calculator tool."}],
                tools=[{
                    "name": "calculator",
                    "description": "Performs arithmetic calculations",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "Math expression to evaluate",
                            }
                        },
                        "required": ["expression"],
                    },
                }],
            )
            # Check if any content block is a tool_use
            for block in response.content:
                if block.type == "tool_use":
                    return True
            return False
        except Exception:
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for the configured Claude model."""
        max_context = _DEFAULT_MAX_CONTEXT
        max_output = _DEFAULT_MAX_OUTPUT

        for prefix, (ctx, out) in _MODEL_LIMITS.items():
            if self._model.startswith(prefix):
                max_context = ctx
                max_output = out
                break

        return ProviderCapabilities(
            supports_tool_calling=True,
            supports_streaming=True,
            supports_vision=True,
            max_context_tokens=max_context,
            max_output_tokens=max_output,
            tool_calling_reliability="high",
        )

    def count_tokens(self, messages: List[Message]) -> TokenUsage:
        """Count tokens using the Anthropic SDK's native token counter.

        Falls back to a character-based estimate if the SDK method is
        unavailable or fails.
        """
        try:
            client = self._get_client()
            _, anthropic_messages = self._messages_to_anthropic_format(messages)
            result = client.messages.count_tokens(
                model=self._model,
                messages=anthropic_messages,
            )
            return TokenUsage(input_tokens=result.input_tokens, output_tokens=0)
        except Exception:
            # Fallback: rough estimate of ~4 chars per token
            total_chars = sum(len(m.content) for m in messages)
            return TokenUsage(input_tokens=total_chars // 4, output_tokens=0)
