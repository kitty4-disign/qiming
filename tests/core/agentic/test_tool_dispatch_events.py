"""Event-payload and protocol safety for the parallel tool dispatcher.

Regressions covered here include server-injected private kwargs leaking into
stream events, parallel tool batches exceeding the execution cap, and raw
exception strings escaping into tool/UI payloads.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from deeptutor.core.agentic.tool_dispatch import MAX_PARALLEL_TOOL_CALLS, dispatch_tool_calls
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.core.tool_protocol import ToolResult
from deeptutor.services.sandbox import Mount


class _Registry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, name: str, **kwargs: Any) -> ToolResult:
        self.calls.append((name, kwargs))
        return ToolResult(content="ok", success=True)


class _FailingRegistry:
    async def execute(self, name: str, **kwargs: Any) -> ToolResult:
        raise RuntimeError("SECRET_INTERNAL_PATH=/srv/private/credential.txt")


def _augment(tool_name: str, tool_args: dict[str, Any], _ctx: UnifiedContext) -> dict[str, Any]:
    # Mirrors the chat pipeline: server-side plumbing rides on private keys.
    return {
        **tool_args,
        "_sandbox_user_id": "u1",
        "_sandbox_workdir": "/tmp/x",
        "_sandbox_mounts": (Mount(host_path="/tmp/x", sandbox_path="/tmp/x", read_only=False),),
    }


@pytest.mark.asyncio
async def test_tool_call_event_args_exclude_private_kwargs() -> None:
    bus = StreamBus()
    events: list[StreamEvent] = []

    import asyncio

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)

    await dispatch_tool_calls(
        tool_calls=[{"id": "c1", "name": "exec", "arguments": json.dumps({"command": "true"})}],
        context=UnifiedContext(session_id="s1", user_message="hi"),
        stream=bus,
        source="chat",
        stage="responding",
        iteration_index=0,
        registry=_Registry(),
        kwarg_augmenter=_augment,
    )
    await bus.close()
    await consumer

    tool_calls = [e for e in events if e.type == StreamEventType.TOOL_CALL]
    assert tool_calls, "tool_call event must be emitted"
    args = tool_calls[0].metadata.get("args") or {}
    assert set(args.keys()) == {"command"}
    # The whole event must survive strict JSON serialization — this is what
    # the WS push and the turn-event store both rely on.
    json.dumps(tool_calls[0].to_dict())


@pytest.mark.asyncio
async def test_overflow_tool_calls_keep_one_to_one_tool_message_pairing() -> None:
    bus = StreamBus()
    registry = _Registry()
    total = MAX_PARALLEL_TOOL_CALLS + 3
    tool_calls = [
        {
            "id": f"c{i}",
            "name": "noop",
            "arguments": json.dumps({"index": i}),
        }
        for i in range(total)
    ]

    outcome = await dispatch_tool_calls(
        tool_calls=tool_calls,
        context=UnifiedContext(session_id="s1", user_message="hi"),
        stream=bus,
        source="chat",
        stage="responding",
        iteration_index=0,
        registry=registry,
        too_many_tool_calls_message="too many",
    )

    assert len(registry.calls) == MAX_PARALLEL_TOOL_CALLS
    assert len(outcome.tool_messages) == total
    assert [m["tool_call_id"] for m in outcome.tool_messages] == [f"c{i}" for i in range(total)]
    overflow = outcome.tool_messages[MAX_PARALLEL_TOOL_CALLS:]
    assert all("skipped" in m["content"] for m in overflow)


@pytest.mark.asyncio
async def test_tool_exception_details_are_not_exposed_to_model_or_ui() -> None:
    bus = StreamBus()
    events: list[StreamEvent] = []

    import asyncio

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)

    outcome = await dispatch_tool_calls(
        tool_calls=[{"id": "c1", "name": "boom", "arguments": "{}"}],
        context=UnifiedContext(session_id="s1", user_message="hi"),
        stream=bus,
        source="chat",
        stage="responding",
        iteration_index=0,
        registry=_FailingRegistry(),
        unknown_error_message_factory=lambda name: f"{name} failed safely",
        retrieve_meta_factory=lambda *_args: {"query": "x"},
    )
    await bus.close()
    await consumer

    assert outcome.tool_messages[0]["content"] == "boom failed safely"
    assert outcome.tool_metadata_by_id["c1"] == {"error_type": "RuntimeError"}
    serialized = json.dumps([e.to_dict() for e in events])
    assert "SECRET_INTERNAL_PATH" not in serialized
    assert "/srv/private" not in serialized
