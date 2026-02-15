"""Tool registry that loads and caches UniversalTool definitions from YAML files."""

import os
from typing import Dict, List

from .universal_tool import UniversalTool, ToolValidationError, load_tool


class ToolRegistryError(Exception):
    """Raised when a tool cannot be found or loaded from the registry."""
    pass


class ToolRegistry:
    """Registry that loads and caches tool definitions from tools/definitions/ YAML files.

    Tools are loaded lazily on first access via get_tool() and cached in memory.
    """

    def __init__(self, definitions_dir: str = None):
        """Initialize the tool registry.

        Args:
            definitions_dir: Path to the directory containing tool YAML files.
                Defaults to tools/definitions/ relative to the project root.
        """
        if definitions_dir is None:
            # Default: project_root/tools/definitions/
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            definitions_dir = os.path.join(project_root, "tools", "definitions")
        self._definitions_dir = definitions_dir
        self._cache: Dict[str, UniversalTool] = {}

    def get_tool(self, name: str) -> UniversalTool:
        """Load a tool by name, returning cached version if available.

        Args:
            name: The tool name, corresponding to {name}.yaml in the definitions dir.

        Returns:
            The loaded UniversalTool instance.

        Raises:
            ToolRegistryError: If the tool file is missing or invalid.
        """
        if name in self._cache:
            return self._cache[name]

        yaml_path = os.path.join(self._definitions_dir, f"{name}.yaml")
        if not os.path.isfile(yaml_path):
            raise ToolRegistryError(
                f"Tool '{name}' not found: expected file at {yaml_path}"
            )

        try:
            tool = load_tool(yaml_path)
        except (ToolValidationError, ImportError) as e:
            raise ToolRegistryError(f"Failed to load tool '{name}': {e}") from e

        self._cache[name] = tool
        return tool

    def list_tools(self) -> List[str]:
        """Return a sorted list of all available tool names from the definitions directory.

        Scans the definitions directory for .yaml files and returns their basenames
        (without extension) as tool names.

        Returns:
            Sorted list of tool name strings.
        """
        if not os.path.isdir(self._definitions_dir):
            return []

        names = []
        for filename in os.listdir(self._definitions_dir):
            if filename.endswith(".yaml"):
                names.append(filename[:-5])  # Strip .yaml extension
        return sorted(names)
