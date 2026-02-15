"""Google Gemini provider adapter for the OpenClawd Agent Dispatch System.

Implements LLMProvider using the Google Generative AI Python SDK to call
Gemini models.
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
    "gemini-2.0-flash": (1048576, 8192),
    "gemini-2.0-pro": (2097152, 8192),
    "gemini-1.5-pro": (2097152, 8192),
    "gemini-1.5-flash": (1048576, 8192),
    "gemini-1.0-pro": (32760, 8192),
}

_DEFAULT_MAX_CONTEXT = 1048576
_DEFAULT_MAX_OUTPUT = 8192


class GoogleProvider(LLMProvider):
    """LLMProvider implementation for Google Gemini models."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._genai = None  # Lazy init of the module
        self._gen_model = None  # Lazy init of the GenerativeModel

    def _get_genai(self) -> Any:
        """Lazily import and configure the google.generativeai module."""
        if self._genai is None:
            try:
                import google.generativeai as genai
            except ImportError as exc:
                raise ImportError(
                    "google-generativeai SDK is required for GoogleProvider. "
                    "Install with: pip install google-generativeai"
                ) from exc

            genai.configure(api_key=self._api_key)
            self._genai = genai
        return self._genai

    def _get_model(self) -> Any:
        """Lazily initialize and return the GenerativeModel instance."""
        if self._gen_model is None:
            genai = self._get_genai()
            self._gen_model = genai.GenerativeModel(self._model)
        return self._gen_model

    def _messages_to_gemini_format(
        self, messages: List[Message]
    ) -> tuple:
        """Convert Message list to Gemini API format.

        Returns:
            (system_instruction, gemini_contents) tuple. System instruction is
            extracted from messages with role='system'. The rest are converted
            to Gemini content dicts with role 'user' or 'model'.
        """
        system_instruction = None
        contents: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
                continue

            # Gemini uses 'model' instead of 'assistant'
            role = "model" if msg.role == "assistant" else "user"
            parts: List[Dict[str, Any]] = []

            if msg.content:
                parts.append({"text": msg.content})

            # Tool calls from assistant become function_call parts
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    parts.append({
                        "function_call": {
                            "name": tc.get("name", ""),
                            "args": tc.get("input", {}),
                        }
                    })

            # Tool results become function_response parts
            if msg.tool_results:
                for tr in msg.tool_results:
                    parts.append({
                        "function_response": {
                            "name": tr.get("name", ""),
                            "response": {"result": tr.get("content", "")},
                        }
                    })

            if parts:
                contents.append({"role": role, "parts": parts})

        return system_instruction, contents

    def _parse_response(self, response: Any) -> LLMResponse:
        """Convert Gemini API response to LLMResponse."""
        content_parts = []
        tool_calls = []

        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    content_parts.append(part.text)
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append({
                        "name": fc.name,
                        "input": dict(fc.args) if fc.args else {},
                    })

        # Extract usage metadata
        usage = None
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            usage = TokenUsage(
                input_tokens=getattr(um, "prompt_token_count", 0) or 0,
                output_tokens=getattr(um, "candidates_token_count", 0) or 0,
            )

        # Determine stop reason
        stop_reason = ""
        if candidate:
            finish_reason = getattr(candidate, "finish_reason", None)
            if finish_reason is not None:
                stop_reason = str(finish_reason)

        return LLMResponse(
            content="\n".join(content_parts),
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
            model=self._model,
            stop_reason=stop_reason,
        )

    def complete(self, messages: List[Message], **kwargs: Any) -> LLMResponse:
        """Send messages to Gemini via google.generativeai.generate_content().

        Args:
            messages: Conversation history as Message objects.
            **kwargs: Additional params forwarded to generate_content()
                (e.g., generation_config, tools).

        Returns:
            LLMResponse with content, tool_calls, usage, model, stop_reason.
        """
        genai = self._get_genai()
        system_instruction, contents = self._messages_to_gemini_format(messages)

        # Create model with system instruction if present
        model_kwargs: Dict[str, Any] = {}
        if system_instruction:
            model_kwargs["system_instruction"] = system_instruction

        model = genai.GenerativeModel(self._model, **model_kwargs)

        # Build generation config from kwargs
        generate_kwargs: Dict[str, Any] = {}
        if "tools" in kwargs:
            generate_kwargs["tools"] = kwargs.pop("tools")
        if "generation_config" in kwargs:
            generate_kwargs["generation_config"] = kwargs.pop("generation_config")
        elif any(k in kwargs for k in ("temperature", "max_tokens", "top_p", "top_k")):
            gen_config: Dict[str, Any] = {}
            if "temperature" in kwargs:
                gen_config["temperature"] = kwargs.pop("temperature")
            if "max_tokens" in kwargs:
                gen_config["max_output_tokens"] = kwargs.pop("max_tokens")
            if "top_p" in kwargs:
                gen_config["top_p"] = kwargs.pop("top_p")
            if "top_k" in kwargs:
                gen_config["top_k"] = kwargs.pop("top_k")
            generate_kwargs["generation_config"] = gen_config

        response = model.generate_content(contents, **generate_kwargs)
        return self._parse_response(response)

    def validate_connection(self) -> bool:
        """Test API connectivity with a minimal generate_content() call."""
        try:
            genai = self._get_genai()
            model = genai.GenerativeModel(self._model)
            response = model.generate_content("ping")
            return response is not None and hasattr(response, "candidates")
        except Exception:
            return False

    def validate_tool_calling(self) -> bool:
        """Test tool calling with a canary function call."""
        try:
            genai = self._get_genai()
            model = genai.GenerativeModel(self._model)

            calculator_tool = {
                "function_declarations": [{
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
                }]
            }

            response = model.generate_content(
                "What is 2+2? Use the calculator tool.",
                tools=[calculator_tool],
            )

            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            return True
            return False
        except Exception:
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for the configured Gemini model."""
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
            tool_calling_reliability="medium",
        )

    def count_tokens(self, messages: List[Message]) -> TokenUsage:
        """Count tokens using the Gemini SDK's native token counter.

        Falls back to a character-based estimate if the SDK method is
        unavailable or fails.
        """
        try:
            model = self._get_model()
            _, contents = self._messages_to_gemini_format(messages)
            result = model.count_tokens(contents)
            return TokenUsage(input_tokens=result.total_tokens, output_tokens=0)
        except Exception:
            total_chars = sum(len(m.content) for m in messages)
            return TokenUsage(input_tokens=total_chars // 4, output_tokens=0)
