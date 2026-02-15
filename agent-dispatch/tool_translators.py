"""Provider-specific tool format translators.

Converts UniversalTool definitions to provider-specific tool schemas
for use with each LLM provider's tool/function calling API.
"""

from typing import Any, Dict, List

from .universal_tool import UniversalTool


def translate_to_anthropic(tool: UniversalTool) -> Dict[str, Any]:
    """Convert a UniversalTool to Anthropic's tool_use schema format.

    Args:
        tool: A UniversalTool instance to convert.

    Returns:
        Dict with name, description, and input_schema fields matching
        Anthropic's tool_use format.
    """
    parameters = tool.parameters
    properties = {}
    required: List[str] = []

    for param_name, param_def in parameters.items():
        if isinstance(param_def, dict):
            prop = dict(param_def)
            if prop.pop("required", False):
                required.append(param_name)
            properties[param_name] = prop
        else:
            properties[param_name] = {"type": "string", "description": str(param_def)}

    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }

    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": input_schema,
    }


def translate_to_openai(tool: UniversalTool) -> Dict[str, Any]:
    """Convert a UniversalTool to OpenAI's function calling schema format.

    Args:
        tool: A UniversalTool instance to convert.

    Returns:
        Dict with type='function' and function={name, description, parameters}
        matching OpenAI's function calling format.
    """
    parameters = tool.parameters
    properties = {}
    required: List[str] = []

    for param_name, param_def in parameters.items():
        if isinstance(param_def, dict):
            prop = dict(param_def)
            if prop.pop("required", False):
                required.append(param_name)
            properties[param_name] = prop
        else:
            properties[param_name] = {"type": "string", "description": str(param_def)}

    params_schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": params_schema,
        },
    }


def translate_to_gemini(tool: UniversalTool) -> Dict[str, Any]:
    """Convert a UniversalTool to Gemini's function_declarations schema format.

    Args:
        tool: A UniversalTool instance to convert.

    Returns:
        Dict with name, description, and parameters fields matching
        Gemini's function_declarations format.
    """
    parameters = tool.parameters
    properties = {}
    required: List[str] = []

    for param_name, param_def in parameters.items():
        if isinstance(param_def, dict):
            prop = dict(param_def)
            if prop.pop("required", False):
                required.append(param_name)
            properties[param_name] = prop
        else:
            properties[param_name] = {"type": "string", "description": str(param_def)}

    params_schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        params_schema["required"] = required

    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": params_schema,
    }


def translate_to_ollama(tool: UniversalTool) -> Dict[str, Any]:
    """Convert a UniversalTool to Ollama's tools schema format.

    Ollama uses the same function calling format as OpenAI:
    {"type": "function", "function": {name, description, parameters}}.

    Args:
        tool: A UniversalTool instance to convert.

    Returns:
        Dict with type='function' and function={name, description, parameters}
        matching Ollama's tools format.
    """
    parameters = tool.parameters
    properties = {}
    required: List[str] = []

    for param_name, param_def in parameters.items():
        if isinstance(param_def, dict):
            prop = dict(param_def)
            if prop.pop("required", False):
                required.append(param_name)
            properties[param_name] = prop
        else:
            properties[param_name] = {"type": "string", "description": str(param_def)}

    params_schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": params_schema,
        },
    }
