from __future__ import annotations

import json

from pydantic import ValidationError
import pytest

from deeptutor.api.routers.plugins_api import (
    CapabilityExecuteRequest,
    _execute_capability_stream,
)
from deeptutor.core.stream import StreamEvent, StreamEventType


def _sse_payload(chunk: str) -> dict:
    data_line = next(line for line in chunk.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


def test_plugin_capability_request_forbids_unknown_top_level_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CapabilityExecuteRequest.model_validate({"content": "start", "unexpected": True})


@pytest.mark.asyncio
async def test_plugin_k12_execution_validates_and_injects_education_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class FakeOrchestrator:
        def list_capabilities(self):
            return ["k12_tutor"]

        async def handle(self, context):
            captured["context"] = context
            yield StreamEvent(type=StreamEventType.DONE, source="k12_tutor")

    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    body = CapabilityExecuteRequest(
        content="start",
        config={
            "course_id": "image-recognition",
            "mastery_path_id": "edu_k12_ai_primary_upper_image_recognition",
        },
        education_context={
            "stage": "primary_upper",
            "grade": 5,
            "knowledge_point_id": "path_m0_kp0",
        },
    )

    chunks = [chunk async for chunk in _execute_capability_stream("k12_tutor", body)]

    assert _sse_payload(chunks[-1])["success"] is True
    assert captured["context"].config_overrides["course_id"] == "image-recognition"
    assert captured["context"].education_context.knowledge_point_id == "path_m0_kp0"


@pytest.mark.asyncio
async def test_plugin_k12_execution_rejects_teaching_fields_in_config() -> None:
    body = CapabilityExecuteRequest(
        content="start",
        config={
            "course_id": "image-recognition",
            "mastery_path_id": "edu_k12_ai_primary_upper_image_recognition",
            "stage": "primary_upper",
        },
    )

    chunks = [chunk async for chunk in _execute_capability_stream("k12_tutor", body)]

    assert "Extra inputs are not permitted" in _sse_payload(chunks[-1])["detail"]
