from __future__ import annotations

import pytest

from deeptutor.agents.chat.tool_protocol_filter import ToolProtocolFilter


def _stream(parts: list[str]) -> str:
    filter_ = ToolProtocolFilter()
    return "".join(filter_.feed(part) for part in parts) + filter_.flush()


def test_complete_tool_block_is_removed() -> None:
    assert _stream([
        "before ",
        "<tool_call><function=mastery_grade>",
        "<parameter=answer>B</parameter>",
        "</function></tool_call>",
        " after",
    ]) == "before  after"


def test_parameter_payload_does_not_leak_across_chunks() -> None:
    assert _stream([
        "visible ",
        "<tool_",
        "call><func",
        "tion=mastery_grade><parameter=answer>",
        "B",
        "</para",
        "meter></function></tool_call>",
        " done",
    ]) == "visible  done"


def test_function_block_without_outer_tool_call_is_removed() -> None:
    assert _stream([
        "x",
        "<function=mastery_status>",
        "secret payload",
        "</function>",
        "y",
    ]) == "xy"


def test_standalone_parameter_block_is_removed() -> None:
    assert _stream(["a<parameter=answer>", "B", "</parameter>b"]) == "ab"


def test_unfinished_internal_tag_is_not_flushed() -> None:
    assert _stream(["safe", "<tool_ca"]) == "safe"


def test_ordinary_less_than_text_is_preserved() -> None:
    assert _stream(["For x < 5"]) == "For x < 5"


@pytest.mark.parametrize("split_at", range(1, 48))
def test_every_single_split_hides_answer_payload(split_at: int) -> None:
    raw = (
        "lead <tool_call><function=mastery_grade>"
        "<parameter=answer>B</parameter>"
        "</function></tool_call> tail"
    )
    result = _stream([raw[:split_at], raw[split_at:]])
    assert result == "lead  tail"
    assert "B" not in result
    assert "mastery_grade" not in result
