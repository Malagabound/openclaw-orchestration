"""OpenAI provider adapter for the OpenClawd Agent Dispatch System.

Implements LLMProvider using the OpenAI Python SDK to call GPT models.
Uses tiktoken for accurate token counting when available.
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
    "gpt-4o": (128000, 16384),
    "gpt-4-turbo": (128000, 4096),
    "gpt-4-": (8192, 8192),
    "gpt-4": (8192, 8192),
    "gpt-3.5-turbo": (16385, 4096),
    "o1": (200000, 100000),
    "o3": (200000, 100000),
}

# Default limits for unknown models
_DEFAULT_MAX_CONTEXT = 128000
_DEFAULT_MAX_OUTPUT = 4096


class OpenAIProvider(LLMProvider):
    """LLMProvider implementation for OpenAI GPT models."""

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
        """Lazily initialize and return the OpenAI client."""
        if self._client is None:
            try:
                import openai
            except ImportError as exc:
                raise ImportError(
                    "openai SDK is required for OpenAIProvider. "
                    "Install with: pip install openai"
                ) from exc

            kwargs: Dict[str, Any] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def _messages_to_openai_format(
        self, messages: List[Message]
    ) -> List[Dict[str, Any]]:
        """Convert Message list to OpenAI chat completion format.

        Maps Message roles to OpenAI roles (system, user, assistant, tool).
        Converts tool_calls and tool_results to OpenAI's expected structure.
        """
        openai_messages: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                openai_messages.append({
                    "role": "system",
                    "content": msg.content,
                })
                continue

            # Assistant message with tool calls
            if msg.role == "assistant" and msg.tool_calls:
                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [],
                }
                for tc in msg.tool_calls:
                    assistant_msg["tool_calls"].append({
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("input", {})),
                        },
                    })
                openai_messages.append(assistant_msg)
                continue

            # Tool result messages
            if msg.tool_results:
                for tr in msg.tool_results:
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": tr.get("tool_use_id", ""),
                        "content": tr.get("content", ""),
                    })
                continue

            # Regular user or assistant message
            role = msg.role if msg.role in ("user", "assistant") else "user"
            openai_messages.append({
                "role": role,
                "content": msg.content or "",
            })

        return openai_messages

    def _parse_response(self, response: Any) -> LLMResponse:
        """Convert OpenAI chat completion response to LLMResponse."""
        choice = response.choices[0] if response.choices else None
        if choice is None:
            return LLMResponse(content="", model=response.model or self._model, stop_reason="")

        message = choice.message
        content = message.content or ""

        tool_calls = None
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                arguments = {}
                if tc.function and tc.function.arguments:
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, TypeError):
                        arguments = {"raw": tc.function.arguments}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name if tc.function else "",
                    "input": arguments,
                })

        usage = None
        if response.usage:
            usage = TokenUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )

        stop_reason = choice.finish_reason or ""

        return LLMResponse(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
            model=response.model or self._model,
            stop_reason=stop_reason,
        )

    def complete(self, messages: List[Message], **kwargs: Any) -> LLMResponse:
        """Send messages to GPT via openai.chat.completions.create().

        Args:
            messages: Conversation history as Message objects.
            **kwargs: Additional params forwarded to chat.completions.create()
                (e.g., temperature, max_tokens, tools).

        Returns:
            LLMResponse with content, tool_calls, usage, model, stop_reason.
        """
        client = self._get_client()
        openai_messages = self._messages_to_openai_format(messages)

        create_kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": openai_messages,
        }

        # Handle max_tokens (OpenAI uses max_tokens or max_completion_tokens)
        max_tokens = kwargs.pop("max_tokens", None)
        if max_tokens is not None:
            create_kwargs["max_tokens"] = max_tokens

        # Convert tools from Anthropic format to OpenAI function format if needed
        tools = kwargs.pop("tools", None)
        if tools:
            openai_tools = []
            for tool in tools:
                if "function" in tool:
                    openai_tools.append(tool)
                else:
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("input_schema", {}),
                        },
                    })
            create_kwargs["tools"] = openai_tools

        # Forward remaining kwargs (temperature, etc.)
        create_kwargs.update(kwargs)

        response = client.chat.completions.create(**create_kwargs)
        return self._parse_response(response)

    def validate_connection(self) -> bool:
        """Test API connectivity with a minimal chat.completions.create() call."""
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return response is not None and hasattr(response, "choices")
        except Exception:
            return False

    def validate_tool_calling(self) -> bool:
        """Test tool calling with a canary function call."""
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": "What is 2+2? Use the calculator tool."}],
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "description": "Performs arithmetic calculations",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "expression": {
                                    "type": "string",
                                    "description": "Math expression to evaluate",
                                }
                            },
                            "required": ["expression"],
                        },
                    },
                }],
            )
            choice = response.choices[0] if response.choices else None
            if choice and choice.message and choice.message.tool_calls:
                return True
            return False
        except Exception:
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for the configured GPT model."""
        max_context = _DEFAULT_MAX_CONTEXT
        max_output = _DEFAULT_MAX_OUTPUT

        # Check longest prefixes first to match gpt-4o before gpt-4
        for prefix in sorted(_MODEL_LIMITS.keys(), key=len, reverse=True):
            if self._model.startswith(prefix):
                max_context, max_output = _MODEL_LIMITS[prefix]
                break

        return ProviderCapabilities(
            supports_tool_calling=True,
            supports_streaming=True,
            supports_vision=self._model.startswith(("gpt-4o", "gpt-4-turbo")),
            max_context_tokens=max_context,
            max_output_tokens=max_output,
            tool_calling_reliability="high",
        )

    def count_tokens(self, messages: List[Message]) -> TokenUsage:
        """Count tokens using tiktoken for accurate token counting.

        Falls back to a character-based estimate if tiktoken is not installed.
        """
        try:
            import tiktoken
            encoding = tiktoken.encoding_for_model(self._model)
        except (ImportError, KeyError):
            # Fallback: rough estimate of ~4 chars per token
            total_chars = sum(len(m.content) for m in messages)
            return TokenUsage(input_tokens=total_chars // 4, output_tokens=0)

        # Count tokens per message following OpenAI's token counting guide
        num_tokens = 0
        for msg in messages:
            # Every message has overhead tokens for role/formatting
            num_tokens += 4  # <|im_start|>{role}\n ... <|im_end|>\n
            num_tokens += len(encoding.encode(msg.content))
            if msg.role:
                num_tokens += len(encoding.encode(msg.role))
        num_tokens += 2  # priming tokens for assistant reply
        return TokenUsage(input_tokens=num_tokens, output_tokens=0)
