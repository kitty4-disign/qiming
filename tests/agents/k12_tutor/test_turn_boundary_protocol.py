from deeptutor.agents.k12_tutor.capability import _turn_boundary_protocol


def test_quiz_protocol_grades_on_next_turn_and_keeps_teaching() -> None:
    text = _turn_boundary_protocol("zh", "quiz")

    assert "ask_user 是当前 turn 的终点" in text
    assert "必须先用 mastery_grade" in text
    assert "不能直接用无工具文本结束" in text
    assert "不得让学习者输入“继续”" in text
    assert "注册下一道题并 ask_user" in text


def test_english_protocol_has_same_turn_boundary_contract() -> None:
    text = _turn_boundary_protocol("en", "lesson")

    assert "ask_user ENDS the current turn" in text
    assert "call mastery_grade first" in text
    assert "do not end with tool-less feedback" in text
    assert "Never require the learner to type 'continue'" in text
