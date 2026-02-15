"""Ollama provider adapter for the OpenClawd Agent Dispatch System.

Implements LLMProvider using the Ollama HTTP API to call local models.
Uses only stdlib (urllib) — no external SDK required.
"""

import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from .llm_provider import (
    LLMProvider,
    LLMResponse,
    Message,
    ProviderCapabilities,
    TokenUsage,
)


# Default Ollama API base URL
_DEFAULT_BASE_URL = "http://localhost:11434"

# Model capability map: model prefix -> (max_context_tokens, max_output_tokens)
_MODEL_LIMITS: Dict[str, tuple] = {
    "llama3": (128000, 4096),
    "llama2": (4096, 4096),
    "mistral": (32768, 4096),
    "mixtral": (32768, 4096),
    "codellama": (16384, 4096),
    "gemma": (8192, 4096),
    "phi": (4096, 4096),
    "qwen": (32768, 4096),
    "deepseek": (32768, 4096),
}

_DEFAULT_MAX_CONTEXT = 4096
_DEFAULT_MAX_OUTPUT = 4096


class OllamaProvider(LLMProvider):
    """LLMProvider implementation for local Ollama models via HTTP API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key  # Unused but matches provider interface
        self._model = model
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")

    def _post(self, endpoint: str, payload: Dict[str, Any], timeout: int = 300) -> Dict[str, Any]:
        """Make a POST request to the Ollama API.

        Args:
            endpoint: API endpoint path (e.g., "/api/chat").
            payload: JSON-serializable request body.
            timeout: Request timeout in seconds.

        Returns:
            Parsed JSON response dict.

        Raises:
            ConnectionError: If the Ollama server is unreachable.
            RuntimeError: If the API returns an error.
        """
        url = f"{self._base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ConnectionError(
                f"Cannot reach Ollama server at {self._base_url}: {exc}"
            ) from exc

    def _messages_to_ollama_format(
        self, messages: List[Message]
    ) -> List[Dict[str, Any]]:
        """Convert Message list to Ollama /api/chat format.

        Ollama expects messages as: [{"role": "...", "content": "..."}]
        System messages use role "system".
        """
        ollama_messages: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.role
            if role not in ("system", "user", "assistant"):
                role = "user"

            ollama_msg: Dict[str, Any] = {
                "role": role,
                "content": msg.content or "",
            }
            ollama_messages.append(ollama_msg)

        return ollama_messages

    def complete(self, messages: List[Message], **kwargs: Any) -> LLMResponse:
        """Send messages to Ollama via /api/chat.

        Args:
            messages: Conversation history as Message objects.
            **kwargs: Additional params (e.g., temperature, num_predict).

        Returns:
            LLMResponse with content, usage, model, stop_reason.
        """
        ollama_messages = self._messages_to_ollama_format(messages)

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": False,
        }

        # Map common kwargs to Ollama options
        options: Dict[str, Any] = {}
        if "temperature" in kwargs:
            options["temperature"] = kwargs.pop("temperature")
        if "max_tokens" in kwargs:
            options["num_predict"] = kwargs.pop("max_tokens")
        if options:
            payload["options"] = options

        try:
            response = self._post("/api/chat", payload)
        except (ConnectionError, RuntimeError) as exc:
            return LLMResponse(
                content=f"Ollama API error: {exc}",
                tool_calls=None,
                usage=None,
                model=self._model,
                stop_reason="error",
            )

        # Parse response
        message = response.get("message", {})
        content = message.get("content", "")

        # Extract token usage if available
        usage = None
        if "prompt_eval_count" in response or "eval_count" in response:
            usage = TokenUsage(
                input_tokens=response.get("prompt_eval_count", 0),
                output_tokens=response.get("eval_count", 0),
            )

        # Determine stop reason
        stop_reason = "stop"
        if response.get("done_reason"):
            stop_reason = response["done_reason"]
        elif not response.get("done", True):
            stop_reason = "length"

        return LLMResponse(
            content=content,
            tool_calls=None,
            usage=usage,
            model=response.get("model", self._model),
            stop_reason=stop_reason,
        )

    def validate_connection(self) -> bool:
        """Check if the Ollama server is running by hitting the API."""
        try:
            url = f"{self._base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def validate_tool_calling(self) -> bool:
        """Ollama tool calling support varies by model; return False by default."""
        return False

    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for the configured Ollama model."""
        max_context = _DEFAULT_MAX_CONTEXT
        max_output = _DEFAULT_MAX_OUTPUT

        for prefix, (ctx, out) in _MODEL_LIMITS.items():
            if self._model.startswith(prefix):
                max_context = ctx
                max_output = out
                break

        return ProviderCapabilities(
            supports_tool_calling=False,
            supports_streaming=True,
            supports_vision=False,
            max_context_tokens=max_context,
            max_output_tokens=max_output,
            tool_calling_reliability="low",
        )

    def count_tokens(self, messages: List[Message]) -> TokenUsage:
        """Estimate tokens as total characters / 4."""
        total_chars = sum(len(m.content) for m in messages)
        return TokenUsage(input_tokens=total_chars // 4, output_tokens=0)
