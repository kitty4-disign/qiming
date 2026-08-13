from __future__ import annotations

import pytest
from fastapi import HTTPException

from deeptutor.api.routers import plugins_api


@pytest.mark.asyncio
async def test_direct_tool_execution_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPTUTOR_ENABLE_DIRECT_TOOL_EXECUTION", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await plugins_api.execute_tool(
            "exec",
            plugins_api.ToolExecuteRequest(params={"command": "echo unsafe"}),
        )

    assert exc_info.value.status_code == 403
    assert "disabled" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_direct_tool_stream_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPTUTOR_ENABLE_DIRECT_TOOL_EXECUTION", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await plugins_api.execute_tool_stream(
            "exec",
            plugins_api.ToolExecuteRequest(params={"command": "echo unsafe"}),
        )

    assert exc_info.value.status_code == 403


def test_direct_tool_execution_requires_explicit_truthy_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENABLE_DIRECT_TOOL_EXECUTION", "0")
    assert plugins_api._direct_tool_execution_enabled() is False

    monkeypatch.setenv("DEEPTUTOR_ENABLE_DIRECT_TOOL_EXECUTION", "1")
    assert plugins_api._direct_tool_execution_enabled() is True
