from deeptutor.agents.k12_tutor.capability import _turn_boundary_protocol


def test_quiz_launch_registers_only_question_one() -> None:
    text = _turn_boundary_protocol(
        "zh",
        "quiz",
        quiz_answered_count=0,
        quiz_question_count=3,
    )

    assert "ask_user 是当前 turn 的终点" in text
    assert "已提交 0/3 题" in text
    assert "注册第 1 题" in text
    assert "每次只允许注册一题" in text


def test_quiz_middle_turn_grades_then_advances_exactly_one_question() -> None:
    text = _turn_boundary_protocol(
        "zh",
        "quiz",
        quiz_answered_count=2,
        quiz_question_count=3,
    )

    assert "刚提交第 2/3 题" in text
    assert "先批改第 2 题" in text
    assert "注册第 3 题" in text
    assert "不得跳题、重复计数或一次展示多题" in text


def test_quiz_final_turn_forbids_fourth_question() -> None:
    text = _turn_boundary_protocol(
        "zh",
        "quiz",
        quiz_answered_count=3,
        quiz_question_count=3,
    )

    assert "已提交 3/3 题" in text
    assert "只负责批改第 3 题" in text
    assert "题数上限优先于课程是否 complete" in text
    assert "绝对禁止再次调用 mastery_quiz 或 ask_user" in text
    assert "禁止生成第 4 题/额外题" in text


def test_english_protocol_has_same_turn_boundary_contract() -> None:
    text = _turn_boundary_protocol("en", "lesson")

    assert "ask_user ENDS the current turn" in text
    assert "call mastery_grade first" in text
    assert "do not end with tool-less feedback" in text
    assert "Never require the learner to type 'continue'" in text


def test_english_final_quiz_stops_at_configured_limit() -> None:
    text = _turn_boundary_protocol(
        "en",
        "quiz",
        quiz_answered_count=3,
        quiz_question_count=3,
    )

    assert "3/3 answers submitted" in text
    assert "do NOT call mastery_quiz or ask_user again" in text
    assert "do NOT create an extra question" in text
