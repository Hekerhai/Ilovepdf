"""Tool registry. Tools register with the ``@register`` decorator, so adding a tool never edits this file."""

from collections.abc import Iterable

from app.domain.errors import NotFound
from app.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        if tool.id in self._tools:
            raise ValueError(f"Duplicate tool id: {tool.id}")
        self._tools[tool.id] = tool

    def get(self, tool_id: str) -> Tool:
        try:
            return self._tools[tool_id]
        except KeyError:
            raise NotFound(f"Unknown tool '{tool_id}'") from None

    def all(self) -> Iterable[Tool]:
        return self._tools.values()

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._tools


_default = ToolRegistry()


def register(cls: type[Tool]) -> type[Tool]:
    _default.add(cls())
    return cls


def default_registry() -> ToolRegistry:
    # Importing the modules runs their @register decorators.
    from app.tools import (  # noqa: F401
        convert_from,
        convert_to,
        edit,
        intelligence,
        optimize,
        organize,
        security,
    )

    return _default
