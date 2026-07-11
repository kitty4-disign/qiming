from deeptutor.agents.k12_tutor.guidance import render_k12_guidance
from deeptutor.education.models import EducationStage, StudentProfile


def make_profile(stage, grade):
    return StudentProfile(
        display_name="小航",
        stage=stage,
        grade=grade,
        textbook_id=f"k12-ai-{stage.value.replace('_', '-')}",
        interests=["机器人"],
        preferred_modalities=["dialogue", "quiz"],
        learning_goal="理解人工智能如何学习",
    )


def test_primary_lower_guidance_requires_short_concrete_turns():
    text = render_k12_guidance(make_profile(EducationStage.PRIMARY_LOWER, 2), language="zh")
    assert "每次最多解释一个概念" in text
    assert "避免公式" in text
    assert "机器人" in text


def test_high_school_guidance_requires_code_and_tradeoffs():
    text = render_k12_guidance(make_profile(EducationStage.HIGH, 11), language="zh")
    assert "算法复杂度" in text
    assert "可运行的 Python" in text
    assert "局限" in text
