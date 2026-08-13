"""K12 / mastery multi-turn lifecycle regression tests.

These guard the turn-boundary teaching model:

* a K12 tutor turn ENDS at its ``ask_user`` card (the card is the turn's
  final artefact) instead of pausing the same agent loop and burning one
  shared round budget across every Q&A cycle — the old behaviour that
  forced a fake finish after ~4 exchanges and could leak raw
  ``<tool_call>`` protocol text to the user;
* the learner's answer starts a NEW turn (fresh round budget) that grades
  the persisted pending question with ``mastery_grade`` and continues;
* the mastery gate is untouched: no advancement below the threshold, no
  ``complete`` until every objective is mastered;
* ordinary chat ``ask_user`` pause/resume behaviour is unchanged.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.agents.chat.agent_loop import AgentLoop
from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.capabilities.mastery.tools import (
    MasteryAssessTool,
    MasteryGradeTool,
    MasteryQuizTool,
    MasteryStatusTool,
)
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.core.tool_protocol import ToolResult
from deeptutor.learning.models import (
    KnowledgePoint,
    KnowledgeType,
    LearningModule,
    PendingQuestion,
)
from deeptutor.learning.policy import is_mastered, next_objective
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import LearningStore

# ---------------------------------------------------------------------------
# helpers (mirror tests/agents/chat/test_agent_loop.py infra)
# ---------------------------------------------------------------------------


async def _collect_bus_events(bus: StreamBus) -> tuple[list[StreamEvent], asyncio.Task[Any]]:
    events: list[StreamEvent] = []

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)
    return events, consumer


def _llm_chunk(
    *,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> SimpleNamespace:
    delta_fields: dict[str, Any] = {"content": content}
    if tool_calls is not None:
        delta_fields["tool_calls"] = [
            SimpleNamespace(
                index=tc.get("index", i),
                id=tc.get("id"),
                function=SimpleNamespace(
                    name=tc.get("name"),
                    arguments=tc.get("arguments"),
                ),
            )
            for i, tc in enumerate(tool_calls)
        ]
    else:
        delta_fields["tool_calls"] = None
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(**delta_fields))])


async def _async_llm_stream(chunks: list[SimpleNamespace]):
    for chunk in chunks:
        yield chunk


class _ScriptedChatClient:
    def __init__(self, scripted: list[list[SimpleNamespace]]) -> None:
        self._script = list(scripted)
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []

        class _Completions:
            def __init__(self, parent: _ScriptedChatClient) -> None:
                self.parent = parent

            async def create(self, **kwargs):
                self.parent.call_count += 1
                self.parent.calls.append({**kwargs, "messages": list(kwargs.get("messages") or [])})
                if not self.parent._script:
                    raise RuntimeError("Scripted client exhausted")
                return _async_llm_stream(self.parent._script.pop(0))

        class _Chat:
            def __init__(self, parent: _ScriptedChatClient) -> None:
                self.completions = _Completions(parent)

        self.chat = _Chat(self)


class _MasteryRegistry:
    """Registry that executes the REAL mastery tools against a temp store."""

    def __init__(self, store_root: Path) -> None:
        self.store_root = store_root
        self.executed: list[dict[str, Any]] = []
        self._tools = {
            "mastery_status": MasteryStatusTool(),
            "mastery_quiz": MasteryQuizTool(),
            "mastery_grade": MasteryGradeTool(),
            "mastery_assess": MasteryAssessTool(),
        }

    def _service(self) -> LearningService:
        return LearningService(LearningStore(self.store_root / "learning"))

    def deferred_tools(self):
        return []

    def build_prompt_text(self, _enabled, **_kwargs):
        return "- `mastery_status` - read the path"

    def build_openai_schemas(self, enabled):
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": name,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                },
            }
            for name in enabled
        ]

    async def execute(self, name: str, **kwargs):
        self.executed.append({"name": name, "kwargs": dict(kwargs)})
        if name == "ask_user":
            payload = {
                "questions": [
                    {
                        "id": "q1",
                        "prompt": "Which option represents an image pixel?",
                        "options": [
                            {"label": "A", "description": "A number"},
                            {"label": "B", "description": "A matrix of numbers"},
                            {"label": "C", "description": "A string"},
                        ],
                    }
                ]
            }
            return ToolResult(
                content="Asked the user.",
                success=True,
                metadata={"ask_user": payload},
                pause_for_user=payload,
            )
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(content=f"unknown {name}", success=False)
        # Route through the real mastery engine with a temp store.
        import deeptutor.capabilities.mastery.tools as tools_mod

        original = tools_mod._new_service
        try:
            tools_mod._new_service = self._service
            return await tool.execute(**kwargs)
        finally:
            tools_mod._new_service = original


@pytest.fixture(autouse=True)
def _fake_llm_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(
            binding="openai",
            model="gpt-test",
            api_key="k",
            base_url="u",
            api_version=None,
            extra_headers={},
            reasoning_effort=None,
        ),
    )


async def _run(pipeline: AgenticChatPipeline, context: UnifiedContext):
    bus = StreamBus()
    events, consumer = await _collect_bus_events(bus)
    await pipeline.run(context, bus)
    await asyncio.sleep(0)
    await bus.close()
    await consumer
    return events


def _contents(events: list[StreamEvent]) -> list[str]:
    return [e.content for e in events if e.type == StreamEventType.CONTENT]


def _result(events: list[StreamEvent]) -> StreamEvent:
    return [e for e in events if e.type == StreamEventType.RESULT][-1]


def _progress_notices(events: list[StreamEvent]) -> list[str]:
    return [
        str(e.content)
        for e in events
        if e.type == StreamEventType.PROGRESS and e.content
    ]


def _all_streamed_text(events: list[StreamEvent]) -> str:
    return "\n".join(
        str(e.content or "")
        for e in events
        if e.type in (StreamEventType.CONTENT, StreamEventType.PROGRESS)
    )


def _make_context(
    message: str,
    *,
    mastery: bool = True,
    session_id: str = "s1",
    turn_id: str = "turn_1",
    min_rounds: int | None = 10,
) -> UnifiedContext:
    metadata: dict[str, Any] = {}
    if mastery:
        metadata["mastery_mode"] = True
        metadata["mastery_path_id"] = "k12_book_1"
        metadata["ask_user_turn_boundary"] = True
        if min_rounds is not None:
            metadata["_min_loop_rounds"] = min_rounds
    metadata["turn_id"] = turn_id
    return UnifiedContext(
        session_id=session_id,
        user_message=message,
        enabled_tools=[
            "mastery_status",
            "mastery_quiz",
            "mastery_grade",
            "mastery_assess",
            "ask_user",
        ],
        metadata=metadata,
    )


def _make_progress(store_root: Path, *, book_id: str = "k12_book_1") -> Any:
    """Build a small mastery path in a temp store: two knowledge points."""
    service = LearningService(LearningStore(store_root / "learning"))
    progress = service.get_or_create(book_id)
    module = LearningModule(
        id=f"{book_id}_m0",
        name="图像基础",
        order=0,
        knowledge_points=[
            KnowledgePoint(
                id=f"{book_id}_m0_kp0",
                name="数组表示图像",
                type=KnowledgeType.MEMORY,
                module_id=f"{book_id}_m0",
            ),
            KnowledgePoint(
                id=f"{book_id}_m0_kp1",
                name="最近质心分类",
                type=KnowledgeType.PROCEDURE,
                module_id=f"{book_id}_m0",
            ),
        ],
    )
    service.replace_modules(progress, [module])
    service.save(progress)  # replace_modules mutates in memory; persist it
    return service, progress


# ---------------------------------------------------------------------------
# TEST 7 / TEST 9 — protocol-leak protection + ordinary chat unchanged
# ---------------------------------------------------------------------------


class TestProtocolLeakProtection:
    def test_sanitizer_removes_tool_call_blocks(self) -> None:
        raw = (
            "<tool_call>\n"
            "<function=mastery_grade>\n"
            "<parameter=answer>B</parameter>\n"
            "</function>\n"
            "</tool_call>\n"
            "答案是 B。"
        )
        cleaned = AgentLoop._sanitize_user_facing_text(None, raw)
        assert "<tool_call" not in cleaned
        assert "<function" not in cleaned
        assert "<parameter" not in cleaned
        assert "答案是 B。" in cleaned

    def test_sanitizer_handles_bare_tags_and_empty_result(self) -> None:
        cleaned = AgentLoop._sanitize_user_facing_text(None, "<tool_call>\n</tool_call>")
        assert cleaned == ""
        assert AgentLoop._sanitize_user_facing_text(None, "") == ""
        assert AgentLoop._sanitize_user_facing_text(None, "plain answer") == "plain answer"

    @pytest.mark.asyncio
    async def test_finish_round_strips_leaked_protocol(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even a normal finish round must never surface tool protocol text."""
        client = _ScriptedChatClient(
            [
                [
                    _llm_chunk(
                        content=(
                            "<tool_call>\n<function=mastery_grade>\n"
                            "<parameter=answer>B</parameter>\n</function>\n</tool_call>\n"
                            "你答对了！"
                        )
                    )
                ]
            ]
        )
        pipeline = AgenticChatPipeline(language="zh")
        pipeline.registry = SimpleNamespace(
            deferred_tools=lambda: [],
            build_prompt_text=lambda *_a, **_k: "",
            build_openai_schemas=lambda _e: [],
        )
        monkeypatch.setattr(pipeline, "_compose_enabled_tools", lambda _context: [])
        monkeypatch.setattr(pipeline, "_build_openai_client", lambda: client)

        events = await _run(pipeline, _make_context("开始学习", mastery=True))

        result = _result(events)
        assert result.metadata["response"] == "你答对了！"
        assert "<tool_call" not in _all_streamed_text(events)

    @pytest.mark.asyncio
    async def test_k12_forced_finish_safe_pauses_without_protocol_leak(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """K12 mode + round budget exhausted while still requesting tools: the
        loop must SAFE-PAUSE (no fake completion) and never force the model to
        emit a tool-less finish that leaks <tool_call> text."""
        registry = _MasteryRegistry(tmp_path)
        client = _ScriptedChatClient(
            [
                # Round 1: always request a tool — the loop will exhaust its
                # budget and hit the forced-finish path.
                [
                    _llm_chunk(
                        tool_calls=[
                            {
                                "id": "call-1",
                                "name": "mastery_status",
                                "arguments": json.dumps({}),
                            }
                        ]
                    )
                ]
            ]
        )
        pipeline = AgenticChatPipeline(language="en")
        pipeline.registry = registry
        pipeline._max_rounds = 1
        monkeypatch.setattr(
            pipeline, "_compose_enabled_tools", lambda _context: ["mastery_status"]
        )
        monkeypatch.setattr(pipeline, "_build_openai_client", lambda: client)

        events = await _run(pipeline, _make_context("teach me", mastery=True, min_rounds=None))

        # Only the one scripted round ran — NO forced-finish LLM call with
        # tool_schemas=None that could fabricate a fake <tool_call> answer.
        assert client.call_count == 1
        result = _result(events)
        assert result.metadata["completed"] is False
        assert "<tool_call" not in _all_streamed_text(events)
        assert "<function" not in _all_streamed_text(events)

    @pytest.mark.asyncio
    async def test_non_k12_forced_finish_strips_protocol_text(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The legacy forced-finish path (non-K12) keeps working, and its
        answer is sanitised even if the model leaks protocol text."""
        registry = _MasteryRegistry(tmp_path)
        client = _ScriptedChatClient(
            [
                [
                    _llm_chunk(
                        tool_calls=[
                            {
                                "id": "call-1",
                                "name": "mastery_status",
                                "arguments": json.dumps({}),
                            }
                        ]
                    )
                ],
                # Forced finish (tools disabled) — the model still writes the
                # tool call it wanted to make as plain text.
                [
                    _llm_chunk(
                        content=(
                            "<tool_call>\n<function=mastery_status>\n</function>\n"
                            "</tool_call>\nBest effort answer."
                        )
                    )
                ],
            ]
        )
        pipeline = AgenticChatPipeline(language="en")
        pipeline.registry = registry
        pipeline._max_rounds = 1
        monkeypatch.setattr(
            pipeline, "_compose_enabled_tools", lambda _context: ["mastery_status"]
        )
        monkeypatch.setattr(pipeline, "_build_openai_client", lambda: client)

        context = UnifiedContext(
            session_id="s1",
            user_message="status?",
            enabled_tools=["mastery_status"],
            metadata={"turn_id": "turn_x"},
        )
        events = await _run(pipeline, context)

        assert client.call_count == 2
        result = _result(events)
        assert result.metadata["response"] == "Best effort answer."
        assert "<tool_call" not in _all_streamed_text(events)


# ---------------------------------------------------------------------------
# TEST 8 / TEST 9 — ordinary chat ask_user behaviour unchanged
# ---------------------------------------------------------------------------


class TestOrdinaryChatAskUserUnchanged:
    @pytest.mark.asyncio
    async def test_chat_ask_user_still_pauses_and_resumes_in_loop(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Without the K12 turn-boundary marker, ask_user keeps the in-loop
        pause/resume protocol: the waiter is consumed and the loop continues
        in the SAME turn."""
        registry = _MasteryRegistry(tmp_path)
        client = _ScriptedChatClient(
            [
                [
                    _llm_chunk(content="Let me check one thing."),
                    _llm_chunk(
                        tool_calls=[
                            {
                                "id": "call-1",
                                "name": "ask_user",
                                "arguments": json.dumps(
                                    {"questions": [{"id": "q1", "prompt": "Which topic?"}]}
                                ),
                            }
                        ]
                    ),
                ],
                [_llm_chunk(content="The answer.")],
            ]
        )
        pipeline = AgenticChatPipeline(language="en")
        pipeline.registry = registry
        monkeypatch.setattr(pipeline, "_compose_enabled_tools", lambda _context: ["ask_user"])
        monkeypatch.setattr(pipeline, "_build_openai_client", lambda: client)

        async def _waiter():
            return {"text": "Topic A"}

        context = UnifiedContext(
            session_id="s1",
            user_message="Quick question",
            enabled_tools=["ask_user"],
            metadata={"wait_for_user_reply": _waiter, "turn_id": "turn_1"},
        )
        events = await _run(pipeline, context)

        # Two rounds: narration + ask_user pause, then the resumed finish.
        assert client.call_count == 2
        assert _contents(events) == ["Let me check one thing.", "The answer."]
        result = _result(events)
        assert result.metadata["response"] == "The answer."
        assert result.metadata["completed"] is True


# ---------------------------------------------------------------------------
# TEST 4 — K12 turn boundary ends the turn at its question card
# ---------------------------------------------------------------------------


class TestK12TurnBoundary:
    @pytest.mark.asyncio
    async def test_ask_user_ends_turn_instead_of_waiting(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """In K12 mode the ask_user card is the turn's final artefact: the
        loop stops (no in-loop waiter resume), and even a present
        wait_for_user_reply waiter is NOT consumed."""
        registry = _MasteryRegistry(tmp_path)
        client = _ScriptedChatClient(
            [
                [
                    _llm_chunk(content="Here is the question."),
                    _llm_chunk(
                        tool_calls=[
                            {
                                "id": "call-1",
                                "name": "ask_user",
                                "arguments": json.dumps(
                                    {"questions": [{"id": "q1", "prompt": "Which option?"}]}
                                ),
                            }
                        ]
                    ),
                ],
                # No further scripted rounds: the turn must END here.
            ]
        )
        pipeline = AgenticChatPipeline(language="en")
        pipeline.registry = registry
        monkeypatch.setattr(pipeline, "_compose_enabled_tools", lambda _context: ["ask_user"])
        monkeypatch.setattr(pipeline, "_build_openai_client", lambda: client)

        waiter_called = False

        async def _waiter():
            nonlocal waiter_called
            waiter_called = True
            return {"text": "B"}

        context = UnifiedContext(
            session_id="s1",
            user_message="teach me",
            enabled_tools=["ask_user"],
            metadata={
                "mastery_mode": True,
                "mastery_path_id": "k12_book_1",
                "ask_user_turn_boundary": True,
                "wait_for_user_reply": _waiter,
                "turn_id": "turn_1",
            },
        )
        events = await _run(pipeline, context)

        assert client.call_count == 1
        assert waiter_called is False, "K12 turn boundary must not consume the waiter"
        # The narration text streams, then the card's question summary is the
        # turn's final content (mirrors the unresolved-pause fallback).
        assert _contents(events) == ["Here is the question.", "Which option represents an image pixel?"]
        result = _result(events)
        assert result.metadata["completed"] is False
        # The card's ask_user payload is in the tool_result metadata.
        card = [
            e
            for e in events
            if e.type == StreamEventType.TOOL_RESULT
            and str((e.metadata or {}).get("tool_metadata", {})).find("ask_user") != -1
        ]
        assert card


# ---------------------------------------------------------------------------
# engine-level lifecycle tests (real LearningService + temp store)
# ---------------------------------------------------------------------------


class TestMasteryEngineLifecycle:
    def _service(self, tmp_path: Path) -> LearningService:
        return LearningService(LearningStore(tmp_path / "learning"))

    def test_pending_question_persists_across_store_instances(
        self, tmp_path: Path
    ) -> None:
        """TEST 3 + TEST 10: a pending question survives a fresh service/store
        (page refresh / new request) — grading stays deterministic."""
        _, progress = _make_progress(tmp_path)
        first = self._service(tmp_path)
        pending = PendingQuestion(
            question_id="q-1",
            knowledge_point_id="k12_book_1_m0_kp0",
            module_id="k12_book_1_m0",
            prompt="255 在灰度图里表示更亮还是更暗？",
            question_type="choice",
            expected_answer="A",
            options=["A: 更亮", "B: 更暗"],
        )
        first.set_pending_question(progress, pending)

        # A brand-new service (new turn / after reload) sees the same pending.
        second = self._service(tmp_path)
        reloaded = second.get_or_create("k12_book_1")
        assert reloaded.pending_question is not None
        assert reloaded.pending_question.question_id == "q-1"
        assert reloaded.pending_question.expected_answer == "A"
        assert next_objective(reloaded).action == "answer_pending"

    @pytest.mark.asyncio
    async def test_grade_grades_against_pending_correctly(self, tmp_path: Path) -> None:
        """TEST 2: the learner's answer is graded by mastery_grade against the
        server-stored expected answer — right answer scores correct, wrong
        does not."""
        service, progress = _make_progress(tmp_path)
        service.set_pending_question(
            progress,
            PendingQuestion(
                question_id="q-2",
                knowledge_point_id="k12_book_1_m0_kp0",
                module_id="k12_book_1_m0",
                prompt="255 在灰度图里表示？",
                question_type="choice",
                expected_answer="A",
                options=["A: 更亮", "B: 更暗"],
            ),
        )
        grade = MasteryGradeTool()
        import deeptutor.capabilities.mastery.tools as tools_mod

        original = tools_mod._new_service
        tools_mod._new_service = lambda: self._service(tmp_path)
        try:
            right = await grade.execute(
                answer="A", _mastery_path_id="k12_book_1", _session_id="s1", _turn_id="t2"
            )
            # Re-register a fresh pending question: grading clears it.
            service.set_pending_question(
                service.get_or_create("k12_book_1"),
                PendingQuestion(
                    question_id="q-3",
                    knowledge_point_id="k12_book_1_m0_kp0",
                    module_id="k12_book_1_m0",
                    prompt="255 在灰度图里表示？",
                    question_type="choice",
                    expected_answer="A",
                    options=["A: 更亮", "B: 更暗"],
                ),
            )
            wrong = await grade.execute(
                answer="B", _mastery_path_id="k12_book_1", _session_id="s1", _turn_id="t3"
            )
        finally:
            tools_mod._new_service = original
        right_payload = json.loads(right.content)
        wrong_payload = json.loads(wrong.content)
        assert right_payload["is_correct"] is True
        assert wrong_payload["is_correct"] is False
        # Wrong answer must NOT have advanced the objective.
        assert wrong_payload["next"]["knowledge_point_id"] == "k12_book_1_m0_kp0"

    def test_gate_blocks_advance_until_threshold(self, tmp_path: Path) -> None:
        """TEST 5: a single correct answer (mastery 0.5 < 0.9) must NOT advance
        to the next knowledge point."""
        service, progress = _make_progress(tmp_path)
        kp = progress.modules[0].knowledge_points[0]
        assert not is_mastered(progress, kp)
        # One correct answer.
        service.grade_and_record(
            progress,
            question_id="q-a",
            knowledge_point_id=kp.id,
            module_id=kp.module_id,
            user_answer="A",
            expected_answer="A",
            question_type="choice",
        )
        assert not is_mastered(progress, kp)
        assert next_objective(progress).knowledge_point_id == kp.id

    def test_complete_only_when_every_objective_mastered(self, tmp_path: Path) -> None:
        """TEST 6: next_objective returns complete ONLY after every objective
        cleared its gate (quantitative ≥ 0.9, qualitative via assess)."""
        service, progress = _make_progress(tmp_path)
        kp0, kp1 = progress.modules[0].knowledge_points
        # kp0 (memory) needs ≥ 0.9: four correct answers give
        # (1.0+1.0+1.0+1.0)/4 = 1.0 with 4 attempts → cap 1.0.
        for i in range(4):
            service.grade_and_record(
                progress,
                question_id=f"q-{i}",
                knowledge_point_id=kp0.id,
                module_id=kp0.module_id,
                user_answer="A",
                expected_answer="A",
                question_type="choice",
            )
        assert is_mastered(progress, kp0)
        # kp1 not mastered yet → NOT complete.
        assert next_objective(progress).action != "complete"
        # kp1 (procedure) needs ≥ 0.9 as well.
        for i in range(4, 8):
            service.grade_and_record(
                progress,
                question_id=f"q-{i}",
                knowledge_point_id=kp1.id,
                module_id=kp1.module_id,
                user_answer="B",
                expected_answer="B",
                question_type="choice",
            )
        assert is_mastered(progress, kp1)
        step = next_objective(service.get_or_create("k12_book_1"))
        assert step.action == "complete"

    @pytest.mark.asyncio
    async def test_k12_ten_answer_cycles_without_budget_blowup(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """TEST 1 + TEST 4: ten full teach→answer cycles through the pipeline
        with the REAL mastery tools. Each cycle = two turns (question turn,
        answer turn); every turn gets a fresh round budget, so the default
        max_rounds can never terminate the lesson early. Progress survives
        across turns because the mastery path is persisted."""
        registry = _MasteryRegistry(tmp_path)
        # Seed the path.
        service, progress = _make_progress(tmp_path)
        kp = progress.modules[0].knowledge_points[0]

        def _status_call(text: str = "") -> list[SimpleNamespace]:
            return [
                _llm_chunk(content=text or None),
                _llm_chunk(
                    tool_calls=[
                        {
                            "id": f"call-{text or 's'}",
                            "name": "mastery_status",
                            "arguments": json.dumps({}),
                        }
                    ]
                ),
            ]

        cycles = 10
        for cycle in range(cycles):
            # --- Question turn: status -> quiz -> ask_user (ends turn) ---
            client = _ScriptedChatClient(
                [
                    _status_call("读取进度"),
                    [
                        _llm_chunk(
                            tool_calls=[
                                {
                                    "id": f"q-{cycle}",
                                    "name": "mastery_quiz",
                                    "arguments": json.dumps(
                                        {
                                            "knowledge_point_id": kp.id,
                                            "question": "255 表示更亮还是更暗？",
                                            "expected_answer": "A",
                                            "question_type": "choice",
                                            "options": ["A: 更亮", "B: 更暗"],
                                        }
                                    ),
                                }
                            ]
                        ),
                    ],
                    [
                        _llm_chunk(content="请回答：" + ("更亮" if cycle % 2 == 0 else "更暗")),
                        _llm_chunk(
                            tool_calls=[
                                {
                                    "id": f"ask-{cycle}",
                                    "name": "ask_user",
                                    "arguments": json.dumps(
                                        {
                                            "questions": [
                                                {
                                                    "id": "q1",
                                                    "prompt": "255 表示更亮还是更暗？",
                                                }
                                            ]
                                        }
                                    ),
                                }
                            ]
                        ),
                    ],
                ]
            )
            pipeline = AgenticChatPipeline(language="zh")
            pipeline.registry = registry
            monkeypatch.setattr(
                pipeline,
                "_compose_enabled_tools",
                lambda _context: [
                    "mastery_status",
                    "mastery_quiz",
                    "mastery_grade",
                    "ask_user",
                ],
            )
            monkeypatch.setattr(pipeline, "_build_openai_client", lambda: client)
            turn_events = await _run(
                pipeline,
                _make_context("继续学习", turn_id=f"turn_q_{cycle}"),
            )
            result = _result(turn_events)
            assert result.metadata["completed"] is False
            assert "<tool_call" not in _all_streamed_text(turn_events)

            # --- Answer turn: status -> grade -> finish text ---
            answer = "A" if cycle % 2 == 0 else "B"
            client2 = _ScriptedChatClient(
                [
                    _status_call("批改进度"),
                    [
                        _llm_chunk(
                            tool_calls=[
                                {
                                    "id": f"g-{cycle}",
                                    "name": "mastery_grade",
                                    "arguments": json.dumps({"answer": answer}),
                                }
                            ]
                        ),
                    ],
                    [_llm_chunk(content="这是反馈。")],
                ]
            )
            pipeline2 = AgenticChatPipeline(language="zh")
            pipeline2.registry = registry
            monkeypatch.setattr(
                pipeline2,
                "_compose_enabled_tools",
                lambda _context: ["mastery_status", "mastery_grade"],
            )
            monkeypatch.setattr(pipeline2, "_build_openai_client", lambda: client2)
            answer_events = await _run(
                pipeline2,
                _make_context(answer, turn_id=f"turn_a_{cycle}"),
            )
            result2 = _result(answer_events)
            assert result2.metadata["completed"] is True
            assert "<tool_call" not in _all_streamed_text(answer_events)
            assert "<function" not in _all_streamed_text(answer_events)

        # After 10 answer cycles: 10 graded attempts persisted, path continuous.
        final_progress = self._service(tmp_path).get_or_create("k12_book_1")
        attempts = [
            a
            for a in final_progress.quiz_attempts
            if a.knowledge_point_id == kp.id
        ]
        assert len(attempts) == cycles
        # Half correct -> recency-weighted mastery < gate; still on kp0.
        assert next_objective(final_progress).knowledge_point_id == kp.id
