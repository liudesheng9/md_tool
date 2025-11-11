from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from .base import MDTool


@dataclass(frozen=True)
class ToolSpec:
    """Metadata describing a tool available to the CLI."""

    name: str
    tool: MDTool
    category: str = "default"


class ToolRegistry:
    """Simple in-memory registry for MDTool implementations."""

    def __init__(self) -> None:
        self._specs: List[ToolSpec] = []

    def register(self, tool: MDTool, *, category: str = "default") -> ToolSpec:
        # Avoid duplicate registration when modules are re-imported
        for spec in self._specs:
            if spec.tool is tool or spec.name == tool.name:
                return spec
        spec = ToolSpec(name=tool.name, tool=tool, category=category)
        self._specs.append(spec)
        return spec

    def iter(self, *, category: Optional[str] = None) -> Iterable[ToolSpec]:
        if category is None:
            return tuple(self._specs)
        return tuple(spec for spec in self._specs if spec.category == category)


registry = ToolRegistry()


def register_tool(tool: MDTool, *, category: str = "default") -> ToolSpec:
    """Register a tool implementation with the global registry."""

    return registry.register(tool, category=category)


def iter_tool_specs(*, category: Optional[str] = None) -> Iterable[ToolSpec]:
    """Yield registered tool metadata."""

    return registry.iter(category=category)

