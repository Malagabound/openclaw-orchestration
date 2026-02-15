"""Provider registry factory for the OpenClawd Agent Dispatch System.

Reads openclawd.config.yaml and returns the correct LLMProvider instance
with API keys resolved from environment variables.
"""

import importlib
import os
from typing import Any, Dict, List, Optional

from .llm_provider import LLMProvider


# Maps provider name strings to (module_name, class_name) tuples.
# Module names are relative to the agent-dispatch package.
_PROVIDER_MAP: Dict[str, tuple] = {
    "anthropic": (".anthropic_provider", "AnthropicProvider"),
    "openai": (".openai_provider", "OpenAIProvider"),
    "google": (".google_provider", "GoogleProvider"),
    "ollama": (".ollama_provider", "OllamaProvider"),
    "claude_code": (".claude_code_provider", "ClaudeCodeProvider"),
}


class ProviderRegistryError(Exception):
    """Raised when provider instantiation fails."""
    pass


def get_provider(
    config_dict: Dict[str, Any],
    agent_name: Optional[str] = None,
) -> LLMProvider:
    """Read provider/model from config and return an instantiated LLMProvider.

    Args:
        config_dict: Parsed openclawd.config.yaml as a dict. Must contain
            a ``provider`` section with ``name``, ``api_key_env``, and ``model``.
        agent_name: Optional agent name (e.g. "research", "comms"). When
            provided, checks ``agent_models`` for a per-agent model override.

    Returns:
        An instantiated LLMProvider subclass ready for use.

    Raises:
        ProviderRegistryError: If the config is missing required fields,
            the API key env var is not set, or the provider module cannot
            be imported.
    """
    # ── Extract provider section ────────────────────────────────────
    provider_section = config_dict.get("provider")
    if not provider_section or not isinstance(provider_section, dict):
        raise ProviderRegistryError(
            "Config missing required 'provider' section with name, api_key_env, and model"
        )

    provider_name = provider_section.get("name")
    if not provider_name:
        raise ProviderRegistryError("Config 'provider.name' is required")

    api_key_env = provider_section.get("api_key_env")
    if not api_key_env:
        raise ProviderRegistryError("Config 'provider.api_key_env' is required")

    model = provider_section.get("model")
    if not model:
        raise ProviderRegistryError("Config 'provider.model' is required")

    base_url = provider_section.get("base_url")

    # ── Per-agent model override ────────────────────────────────────
    if agent_name:
        agent_models = config_dict.get("agent_models", {})
        if isinstance(agent_models, dict) and agent_name in agent_models:
            model = agent_models[agent_name]

    # ── Resolve API key from environment ────────────────────────────
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ProviderRegistryError(
            f"Environment variable '{api_key_env}' is not set or empty. "
            f"Set it to your {provider_name} API key."
        )

    # ── Import and instantiate provider class ───────────────────────
    provider_name_lower = provider_name.lower()

    if provider_name_lower in _PROVIDER_MAP:
        module_path, class_name = _PROVIDER_MAP[provider_name_lower]
    else:
        raise ProviderRegistryError(
            f"Unknown provider '{provider_name}'. "
            f"Supported providers: {', '.join(sorted(_PROVIDER_MAP.keys()))}"
        )

    try:
        module = importlib.import_module(module_path, package="agent-dispatch")
    except ImportError as exc:
        raise ProviderRegistryError(
            f"Cannot import provider module '{module_path}' for provider "
            f"'{provider_name}': {exc}. Ensure the provider adapter is installed."
        ) from exc

    provider_class = getattr(module, class_name, None)
    if provider_class is None:
        raise ProviderRegistryError(
            f"Module '{module_path}' does not contain class '{class_name}'"
        )

    # ── Build kwargs for provider constructor ───────────────────────
    kwargs: Dict[str, Any] = {
        "api_key": api_key,
        "model": model,
    }
    if base_url:
        kwargs["base_url"] = base_url

    try:
        instance = provider_class(**kwargs)
    except TypeError as exc:
        raise ProviderRegistryError(
            f"Failed to instantiate {class_name} with kwargs "
            f"{list(kwargs.keys())}: {exc}"
        ) from exc

    if not isinstance(instance, LLMProvider):
        raise ProviderRegistryError(
            f"{class_name} does not implement LLMProvider interface"
        )

    return instance


def get_provider_with_fallback(
    config_dict: Dict[str, Any],
    agent_name: Optional[str] = None,
    require_tool_calling: bool = False,
    min_context_tokens: int = 0,
) -> LLMProvider:
    """Get provider with fallback chain, filtering by capability requirements.

    This function attempts to instantiate the primary provider. If that fails
    or doesn't meet capability requirements, it tries each fallback provider
    in the configured fallback chain, applying capability filters.

    Args:
        config_dict: Parsed openclawd.config.yaml as a dict.
        agent_name: Optional agent name for per-agent model overrides.
        require_tool_calling: If True, skip providers that don't support
            reliable tool calling (validate_tool_calling() returns False or
            tool_calling_reliability is "low").
        min_context_tokens: Minimum required context window size. Skip
            providers with max_context_tokens less than this value.

    Returns:
        An instantiated LLMProvider that meets the capability requirements.

    Raises:
        ProviderRegistryError: If no suitable provider can be instantiated
            or meets the capability requirements.
    """
    # Build list of providers to try: primary + fallbacks
    providers_to_try: List[str] = []

    # Add primary provider
    provider_section = config_dict.get("provider", {})
    primary_provider = provider_section.get("name")
    if primary_provider:
        providers_to_try.append(primary_provider)

    # Add fallback providers from config
    fallback_chain = config_dict.get("fallback_chain", [])
    if isinstance(fallback_chain, list):
        providers_to_try.extend(fallback_chain)

    last_error: Optional[Exception] = None

    for provider_name in providers_to_try:
        try:
            # Temporarily override provider name in config
            modified_config = config_dict.copy()
            modified_provider_section = provider_section.copy()
            modified_provider_section["name"] = provider_name

            # Resolve provider-specific settings if configured
            if "fallback_providers" in config_dict:
                fallback_providers = config_dict["fallback_providers"]
                if isinstance(fallback_providers, dict) and provider_name in fallback_providers:
                    provider_config = fallback_providers[provider_name]
                    if isinstance(provider_config, dict):
                        # Override api_key_env, base_url, model if specified
                        if "api_key_env" in provider_config:
                            modified_provider_section["api_key_env"] = provider_config["api_key_env"]
                        if "base_url" in provider_config:
                            modified_provider_section["base_url"] = provider_config["base_url"]
                        if "model" in provider_config:
                            modified_provider_section["model"] = provider_config["model"]

            modified_config["provider"] = modified_provider_section

            # Try to instantiate provider
            provider = get_provider(modified_config, agent_name)

            # Check capability requirements
            caps = provider.get_capabilities()

            # Filter by tool calling requirement
            if require_tool_calling:
                if caps.tool_calling_reliability == "low" or not provider.validate_tool_calling():
                    continue

            # Filter by context window requirement
            if min_context_tokens > 0:
                if caps.max_context_tokens < min_context_tokens:
                    continue

            # Provider meets requirements
            return provider

        except Exception as exc:
            last_error = exc
            continue

    # No suitable provider found
    error_msg = "No suitable provider found"
    if require_tool_calling:
        error_msg += " with reliable tool calling"
    if min_context_tokens > 0:
        error_msg += f" and min context tokens >= {min_context_tokens}"

    if last_error:
        raise ProviderRegistryError(f"{error_msg}. Last error: {last_error}") from last_error
    else:
        raise ProviderRegistryError(error_msg)
