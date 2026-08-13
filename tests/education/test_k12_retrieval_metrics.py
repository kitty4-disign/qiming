from scripts.evaluate_k12_tutor import evaluate_benchmarks, score_retrieval_cases


def test_benchmark_v2_source_contract_is_valid():
    result = evaluate_benchmarks()
    assert result["all_passed"] is True
    assert result["integrity_issues"] == []


def test_retrieval_metrics_detect_traceability_and_leakage():
    result = score_retrieval_cases(
        [
            {
                "question_id": "q1",
                "expected_kb": "kb-a",
                "observed_kb": "kb-a",
                "expected_sources": ["a.md"],
                "observed_sources": [{"source": "C:\\kb\\a.md", "chunk_id": "chunk-1"}],
            },
            {
                "question_id": "q2",
                "expected_kb": "kb-a",
                "observed_kb": "kb-a",
                "expected_sources": ["a.md"],
                "observed_sources": [{"source": "/kb/b.md"}],
            },
        ],
        known_sources={"a.md", "b.md"},
    )
    assert result["retrieval_hit_rate"] == 0.5
    assert result["source_traceability_rate"] == 0.5
    assert result["wrong_course_leakage_rate"] == 0.5
