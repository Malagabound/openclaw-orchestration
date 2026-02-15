"""UniversalTool schema and YAML loader for provider-agnostic tool definitions."""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ToolValidationError(Exception):
    """Raised when a tool definition is missing required fields or has invalid structure."""
    pass


@dataclass
class UniversalTool:
    """Provider-agnostic tool schema that can be converted to any LLM provider's tool format."""

    name: str
    description: str
    parameters: Dict[str, Any]
    returns: Dict[str, Any]
    execution: Dict[str, str]
    version: str = "1.0.0"
    idempotent: bool = False
    destructive: bool = False
    timeout_seconds: int = 300
    allowed_agents: Optional[List[str]] = None
    denied_agents: list = field(default_factory=list)  # Agents explicitly denied from using this tool
    test: Optional[Dict[str, Any]] = None


_REQUIRED_FIELDS = ("name", "description", "parameters", "returns", "execution")
_REQUIRED_EXECUTION_FIELDS = ("type", "module", "function")


def _validate_tool_data(data: Dict[str, Any]) -> None:
    """Validate that required fields are present and correctly structured."""
    missing = [f for f in _REQUIRED_FIELDS if f not in data or data[f] is None]
    if missing:
        raise ToolValidationError(f"Missing required fields: {', '.join(missing)}")

    execution = data["execution"]
    if not isinstance(execution, dict):
        raise ToolValidationError("'execution' must be a dict with keys: type, module, function")
    missing_exec = [f for f in _REQUIRED_EXECUTION_FIELDS if f not in execution]
    if missing_exec:
        raise ToolValidationError(
            f"'execution' missing required keys: {', '.join(missing_exec)}"
        )

    if not isinstance(data["parameters"], dict):
        raise ToolValidationError("'parameters' must be a dict with type schemas")

    if not isinstance(data["returns"], dict):
        raise ToolValidationError("'returns' must be a dict with type schemas")


def load_tool(yaml_path: str) -> UniversalTool:
    """Parse a YAML file and return a UniversalTool instance.

    Args:
        yaml_path: Path to the YAML tool definition file.

    Returns:
        UniversalTool instance populated from the YAML data.

    Raises:
        ToolValidationError: If required fields are missing or invalid.
        FileNotFoundError: If the YAML file does not exist.
    """
    if not os.path.isfile(yaml_path):
        raise FileNotFoundError(f"Tool definition not found: {yaml_path}")

    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required to load tool definitions: pip install pyyaml")

    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ToolValidationError(f"Tool definition must be a YAML mapping, got {type(data).__name__}")

    _validate_tool_data(data)

    return UniversalTool(
        name=data["name"],
        description=data["description"],
        parameters=data["parameters"],
        returns=data["returns"],
        execution=data["execution"],
        version=data.get("version", "1.0.0"),
        idempotent=bool(data.get("idempotent", False)),
        destructive=bool(data.get("destructive", False)),
        timeout_seconds=int(data.get("timeout_seconds", 300)),
        allowed_agents=data.get("allowed_agents"),
        denied_agents=data.get("denied_agents", []),
        test=data.get("test"),
    )
