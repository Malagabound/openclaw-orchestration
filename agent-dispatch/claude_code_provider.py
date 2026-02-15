"""Claude Code CLI provider adapter for the OpenClawd Agent Dispatch System.

Implements LLMProvider by spawning a 'claude' subprocess with raw text
passthrough. No tool calling support. No structured result parsing.
"""

import shutil
import subprocess
from typing import Any, List, Optional

from .llm_provider import (
    LLMProvider,
    LLMResponse,
    Message,
    ProviderCapabilities,
    TokenUsage,
)


class ClaudeCodeProvider(LLMProvider):
    """LLMProvider implementation that spawns Claude Code CLI as a subprocess.

    This provider is a fallback for complex tasks where direct API access
    is unavailable. It sends prompts via stdin and captures stdout as raw text.
    No tool calling or structured output support.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        # Resolve the CLI command once
        self._cli_command = self._find_cli_command()

    @staticmethod
    def _find_cli_command() -> str:
        """Find the claude CLI command on the system PATH."""
        for cmd in ("claude",):
            if shutil.which(cmd):
                return cmd
        return "claude"

    def complete(self, messages: List[Message], **kwargs: Any) -> LLMResponse:
        """Send prompt to Claude Code CLI via subprocess stdin, capture stdout.

        Concatenates all message contents into a single prompt string,
        sends it to the CLI process via stdin, and returns raw stdout
        as the response content.

        Args:
            messages: Conversation history as Message objects.
            **kwargs: Ignored (CLI does not support extra params).

        Returns:
            LLMResponse with raw stdout as content, no tool_calls.
        """
        prompt = "\n\n".join(
            m.content for m in messages if m.content
        )

        cmd = [self._cli_command, "-p", prompt, "--output-format", "text"]

        if self._model:
            cmd.extend(["--model", self._model])

        timeout = kwargs.get("timeout", 1800)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            content = result.stdout or ""
            stop_reason = "end_turn" if result.returncode == 0 else "error"

            if result.returncode != 0 and result.stderr:
                content = content or result.stderr

        except subprocess.TimeoutExpired:
            content = "Error: Claude Code CLI timed out"
            stop_reason = "timeout"
        except FileNotFoundError:
            content = "Error: claude command not found"
            stop_reason = "error"
        except Exception as exc:
            content = f"Error: {exc}"
            stop_reason = "error"

        # Estimate token usage from character count
        input_chars = sum(len(m.content) for m in messages if m.content)
        output_chars = len(content)

        return LLMResponse(
            content=content,
            tool_calls=None,
            usage=TokenUsage(
                input_tokens=input_chars // 4,
                output_tokens=output_chars // 4,
            ),
            model=self._model or "claude-code-cli",
            stop_reason=stop_reason,
        )

    def validate_connection(self) -> bool:
        """Check if the 'claude' CLI command exists on the system PATH."""
        return shutil.which(self._cli_command) is not None

    def validate_tool_calling(self) -> bool:
        """Claude Code CLI does not support tool calling."""
        return False

    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for Claude Code CLI (no tool calling)."""
        return ProviderCapabilities(
            supports_tool_calling=False,
            supports_streaming=False,
            supports_vision=False,
            max_context_tokens=200000,
            max_output_tokens=32000,
            tool_calling_reliability="medium",
        )

    def count_tokens(self, messages: List[Message]) -> TokenUsage:
        """Estimate tokens using character-based heuristic (chars / 4)."""
        total_chars = sum(len(m.content) for m in messages if m.content)
        return TokenUsage(input_tokens=total_chars // 4, output_tokens=0)
