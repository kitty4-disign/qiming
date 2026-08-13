from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.context import UnifiedContext


class _FakePathService:
    def __init__(self, task_dir: Path) -> None:
        self.task_dir = task_dir

    def get_task_workspace(self, _capability: str, _workspace_key: str) -> Path:
        return self.task_dir


def test_web_search_output_dir_is_server_controlled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model-supplied extra kwargs must not redirect search artifacts."""
    from deeptutor.services import path_service as path_service_module

    task_dir = tmp_path / "task"
    pipeline = AgenticChatPipeline.__new__(AgenticChatPipeline)
    monkeypatch.setattr(
        AgenticChatPipeline,
        "_workspace_key",
        lambda _self, _context: "workspace-1",
    )
    monkeypatch.setattr(
        AgenticChatPipeline,
        "_active_loop_capabilities",
        lambda _self, _context: (),
    )
    monkeypatch.setattr(
        path_service_module,
        "get_path_service",
        lambda: _FakePathService(task_dir),
    )

    caller_args = {
        "query": "safe query",
        "output_dir": str(tmp_path / "attacker-controlled"),
    }
    result = pipeline._augment_tool_kwargs(
        "web_search",
        caller_args,
        UnifiedContext(user_message="fallback query"),
    )

    assert result["output_dir"] == str(task_dir / "web_search")
    assert result["query"] == "safe query"
    assert caller_args["output_dir"] != result["output_dir"]
