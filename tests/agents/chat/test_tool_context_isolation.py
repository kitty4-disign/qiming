from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.runtime.registry.tool_registry import ToolRegistry


class _FakePathService:
    def __init__(self, user_root: Path) -> None:
        self.user_root = user_root

    def get_user_root(self) -> Path:
        return self.user_root


class _CapturingWebSearchTool(BaseTool):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_search",
            description="test web search",
            parameters=[ToolParameter(name="query", type="string")],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        self.calls.append(dict(kwargs))
        return ToolResult(content="ok")


@pytest.mark.asyncio
async def test_web_search_rejects_output_dir_outside_current_user_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Undeclared model kwargs must not become arbitrary filesystem writes."""
    from deeptutor.services import path_service as path_service_module

    user_root = tmp_path / "user-a"
    user_root.mkdir()
    monkeypatch.setattr(
        path_service_module,
        "get_path_service",
        lambda: _FakePathService(user_root),
    )

    tool = _CapturingWebSearchTool()
    registry = ToolRegistry()
    registry.register(tool)

    await registry.execute(
        "web_search",
        query="safe query",
        output_dir=str(tmp_path / "user-b" / "attacker-controlled"),
    )

    assert tool.calls == [{"query": "safe query"}]


@pytest.mark.asyncio
async def test_web_search_preserves_server_output_dir_inside_current_user_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server-injected per-turn artifact paths remain functional."""
    from deeptutor.services import path_service as path_service_module

    user_root = tmp_path / "user-a"
    safe_output_dir = user_root / "workspace" / "chat" / "turn-1" / "web_search"
    user_root.mkdir()
    monkeypatch.setattr(
        path_service_module,
        "get_path_service",
        lambda: _FakePathService(user_root),
    )

    tool = _CapturingWebSearchTool()
    registry = ToolRegistry()
    registry.register(tool)

    await registry.execute(
        "web_search",
        query="safe query",
        output_dir=str(safe_output_dir),
    )

    assert tool.calls == [
        {
            "query": "safe query",
            "output_dir": str(safe_output_dir.resolve()),
        }
    ]
