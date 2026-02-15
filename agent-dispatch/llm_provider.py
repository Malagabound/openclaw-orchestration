"""LLMProvider abstract base class and supporting dataclasses.

Defines the provider-agnostic interface that all LLM provider adapters
(Anthropic, OpenAI, etc.) must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TokenUsage:
    """Token consumption for a single LLM call."""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Message:
    """A single message in an LLM conversation."""
    role: str = ""
    content: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_results: Optional[List[Dict[str, Any]]] = None


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[TokenUsage] = None
    model: str = ""
    stop_reason: str = ""


@dataclass
class ProviderCapabilities:
    """Capability flags and limits for a provider/model combination."""
    supports_tool_calling: bool = False
    supports_streaming: bool = False
    supports_vision: bool = False
    max_context_tokens: int = 0
    max_output_tokens: int = 0
    tool_calling_reliability: str = "low"  # "high", "medium", "low"


class LLMProvider(ABC):
    """Abstract base class for LLM provider adapters.

    All provider implementations (Anthropic, OpenAI, Google, Ollama, etc.)
    must subclass this and implement every abstract method.
    """

    @abstractmethod
    def complete(self, messages: List[Message], **kwargs: Any) -> LLMResponse:
        """Send messages to the LLM and return a response.

        Args:
            messages: Conversation history as a list of Message objects.
            **kwargs: Provider-specific options (temperature, max_tokens, tools, etc.).

        Returns:
            LLMResponse with content, tool_calls, usage, model, and stop_reason.
        """

    @abstractmethod
    def validate_connection(self) -> bool:
        """Test that the provider is reachable and the API key is valid.

        Returns:
            True if a test call succeeds, False otherwise.
        """

    @abstractmethod
    def validate_tool_calling(self) -> bool:
        """Test that tool/function calling works with this provider.

        Returns:
            True if a test tool call round-trip succeeds, False otherwise.
        """

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Return capability flags and limits for the configured model.

        Returns:
            ProviderCapabilities with support flags and token limits.
        """

    @abstractmethod
    def count_tokens(self, messages: List[Message]) -> TokenUsage:
        """Count the number of tokens in a list of messages.

        Args:
            messages: Messages to count tokens for.

        Returns:
            TokenUsage with input_tokens (and output_tokens=0 for estimates).
        """
