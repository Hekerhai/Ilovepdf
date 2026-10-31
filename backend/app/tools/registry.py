"""Tool registry. Tools register with the ``@register`` decorator, so adding a tool never edits this file."""

from collections.abc import Iterable

from app.domain.errors import NotFound
from app.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._order: dict[str, int] = {}

    def add(self, tool: Tool) -> None:
        if tool.id in self._tools:
            raise ValueError(f"Duplicate tool id: {tool.id}")
        self._tools[tool.id] = tool
        self._order[tool.id] = len(self._order)

    def get(self, tool_id: str) -> Tool:
        try:
            return self._tools[tool_id]
        except KeyError:
            raise NotFound(f"Unknown tool '{tool_id}'") from None

    def all(self) -> Iterable[Tool]:
        # Stable order (module order below, then definition order) whatever order modules were imported in.
        def key(tool: Tool) -> tuple[int, int]:
            module = type(tool).__module__.rsplit(".", 1)[-1]
            rank = MODULE_ORDER.index(module) if module in MODULE_ORDER else len(MODULE_ORDER)
            return rank, self._order[tool.id]

        return sorted(self._tools.values(), key=key)

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._tools


MODULE_ORDER = ["organize", "optimize", "accessibility", "convert_to", "convert_from", "edit", "editor", "security",
                "signatures", "intelligence"]  # fmt: skip

_default = ToolRegistry()


def register(cls: type[Tool]) -> type[Tool]:
    _default.add(cls())
    return cls


def default_registry() -> ToolRegistry:
    # Importing the modules runs their @register decorators.
    from app.tools import (  # noqa: F401
        accessibility,
        convert_from,
        convert_to,
        edit,
        editor,
        intelligence,
        optimize,
        organize,
        security,
        signatures,
    )

    return _default
