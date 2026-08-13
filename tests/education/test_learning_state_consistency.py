from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.learning.models import (
    KnowledgePoint,
    KnowledgeType,
    LearningModule,
    LearningProgress,
    PendingQuestion,
    QuizAttempt,
)
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import ConcurrentLearningUpdateError, LearningStore


def _module(*, kp_name: str = "new concept") -> LearningModule:
    return LearningModule(
        id="m0",
        name="Module 0",
        order=0,
        knowledge_points=[
            KnowledgePoint(
                id="path_m0_kp0",
                name=kp_name,
                type=KnowledgeType.CONCEPT,
                module_id="m0",
            )
        ],
    )


def _appended_module() -> LearningModule:
    return LearningModule(
        id="m1",
        name="Module 1",
        order=1,
        knowledge_points=[
            KnowledgePoint(
                id="path_m1_kp0",
                name="brand new topic",
                type=KnowledgeType.PROCEDURE,
                module_id="m1",
            )
        ],
    )


def test_replace_modules_clears_history_even_when_positional_kp_id_is_reused(
    tmp_path: Path,
) -> None:
    progress = LearningProgress(book_id="path")
    progress.modules = [_module(kp_name="old concept")]
    progress.mastery_levels["path_m0_kp0"] = 1.0
    progress.qualitative_mastery["path_m0_kp0"] = True
    progress.quiz_attempts.append(
        QuizAttempt(
            question_id="old-q",
            knowledge_point_id="path_m0_kp0",
            module_id="m0",
            is_correct=True,
            user_answer="old answer",
        )
    )
    progress.pending_question = PendingQuestion(
        question_id="old-pending",
        knowledge_point_id="path_m0_kp0",
        module_id="m0",
        expected_answer="old expected",
    )

    LearningService(store=LearningStore(root=tmp_path / "learning")).replace_modules(
        progress,
        [_module(kp_name="completely different concept")],
    )

    assert progress.mastery_levels == {}
    assert progress.qualitative_mastery == {}
    assert progress.quiz_attempts == []
    assert progress.pending_question is None
    assert progress.knowledge_types == {"path_m0_kp0": KnowledgeType.CONCEPT}


def test_append_style_rebuild_preserves_history_for_unchanged_kp(tmp_path: Path) -> None:
    service = LearningService(LearningStore(root=tmp_path / "learning"))
    progress = LearningProgress(book_id="path")
    unchanged = _module(kp_name="same concept")
    progress.modules = [unchanged]
    progress.mastery_levels["path_m0_kp0"] = 0.8
    progress.qualitative_mastery["path_m0_kp0"] = True
    progress.quiz_attempts.append(
        QuizAttempt(
            question_id="q-old",
            knowledge_point_id="path_m0_kp0",
            module_id="m0",
            is_correct=True,
            user_answer="A",
        )
    )

    service.replace_modules(progress, [unchanged, _appended_module()])

    assert progress.mastery_levels == {"path_m0_kp0": 0.8}
    assert progress.qualitative_mastery == {"path_m0_kp0": True}
    assert [attempt.question_id for attempt in progress.quiz_attempts] == ["q-old"]
    assert progress.knowledge_types == {
        "path_m0_kp0": KnowledgeType.CONCEPT,
        "path_m1_kp0": KnowledgeType.PROCEDURE,
    }


def test_second_distinct_pending_question_is_rejected(tmp_path: Path) -> None:
    service = LearningService(LearningStore(root=tmp_path / "learning"))
    progress = service.get_or_create("path")
    service.set_pending_question(
        progress,
        PendingQuestion(
            question_id="q1",
            knowledge_point_id="kp1",
            expected_answer="a1",
        ),
    )

    with pytest.raises(ValueError, match="already pending"):
        service.set_pending_question(
            progress,
            PendingQuestion(
                question_id="q2",
                knowledge_point_id="kp2",
                expected_answer="a2",
            ),
        )

    restored = service.get_or_create("path")
    assert restored.pending_question is not None
    assert restored.pending_question.question_id == "q1"


def test_grade_persists_attempt_and_pending_clear_in_one_write(tmp_path: Path) -> None:
    service = LearningService(LearningStore(root=tmp_path / "learning"))
    progress = service.get_or_create("path")
    service.set_pending_question(
        progress,
        PendingQuestion(
            question_id="q1",
            knowledge_point_id="kp1",
            module_id="m1",
            expected_answer="A",
        ),
    )

    assert service.grade_and_record(
        progress,
        question_id="q1",
        knowledge_point_id="kp1",
        module_id="m1",
        user_answer="A",
        expected_answer="A",
    ) is True

    restored = service.get_or_create("path")
    assert restored.pending_question is None
    assert len(restored.quiz_attempts) == 1
    assert restored.quiz_attempts[0].question_id == "q1"

    version_after_grade = progress.version
    service.clear_pending_question(progress)
    assert progress.version == version_after_grade


def test_stale_progress_save_fails_closed_instead_of_last_save_wins(tmp_path: Path) -> None:
    store = LearningStore(root=tmp_path / "learning")
    original = LearningProgress(book_id="path")
    store.save(original)

    first = store.load("path")
    stale = store.load("path")
    assert first is not None and stale is not None

    first.mastery_levels["kp-a"] = 1.0
    store.save(first)

    stale.mastery_levels["kp-b"] = 1.0
    with pytest.raises(ConcurrentLearningUpdateError):
        store.save(stale)

    restored = store.load("path")
    assert restored is not None
    assert restored.mastery_levels == {"kp-a": 1.0}
