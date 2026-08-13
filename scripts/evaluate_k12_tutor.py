"""K12 tutor evaluation script (M4 §9.3).

Outputs reports/k12-evaluation.json and a Markdown summary that clearly
distinguishes:
  - deterministic automated test results (from pytest)
  - LLM judge results (if used; clearly marked as subjective)
  - manual spot-check results (clearly marked as human, not automated)
  - unverified items

LLM judge scores are NEVER written as objective fact — only as observed LLM
judgements with model name and prompt recorded.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"
BENCHMARK_FIXTURE = ROOT / "tests" / "education" / "fixtures" / "k12_benchmark.yaml"


def run_deterministic_tests() -> dict:
    """Run the deterministic automated test suite and capture pass/fail counts."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/education/", "tests/capabilities/test_k12_guidance.py", "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    def count(label: str) -> int:
        matches = re.findall(rf"(\d+)\s+{label}", output)
        return int(matches[-1]) if matches else 0

    passed = count("passed")
    failed = count("failed")
    errors = count("errors?")
    return {
        "type": "deterministic_automated",
        "tool": "pytest",
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "exit_code": result.returncode,
        "raw_summary": output.strip().splitlines()[-1] if output.strip() else "",
    }


def load_benchmarks() -> dict:
    """Load the K12 benchmark questions fixture."""
    if not BENCHMARK_FIXTURE.exists():
        return {"error": "benchmark fixture not found", "path": str(BENCHMARK_FIXTURE)}
    raw = yaml.safe_load(BENCHMARK_FIXTURE.read_text(encoding="utf-8"))
    return raw


def evaluate_benchmarks() -> dict:
    """Evaluate benchmark coverage — counts, not LLM judging.

    The benchmark questions are human-verified. This script does NOT use an LLM
    judge to score the tutor's answers — it only verifies that the fixture is
    well-formed and reports the coverage matrix.
    """
    benchmarks = load_benchmarks()
    if "error" in benchmarks:
        return benchmarks

    if benchmarks.get("version") != 2:
        return {"error": "benchmark fixture must use version 2"}
    per_stage: dict[str, dict] = {}
    question_ids: set[str] = set()
    integrity_issues: list[str] = []
    for entry in benchmarks.get("benchmarks", []):
        stage = entry["stage"]
        questions = entry.get("questions", [])
        categories = {}
        for q in questions:
            if q.get("id") in question_ids:
                integrity_issues.append(f"duplicate question id: {q.get('id')}")
            question_ids.add(str(q.get("id") or ""))
            if "retrieval_required" not in q or "expected_sources" not in q:
                integrity_issues.append(f"{q.get('id')}: missing retrieval source contract")
            if q.get("retrieval_required") and not q.get("expected_sources"):
                integrity_issues.append(f"{q.get('id')}: retrieval requires expected_sources")
            cat = q["category"]
            categories[cat] = categories.get(cat, 0) + 1
        per_stage[stage] = {
            "total_questions": len(questions),
            "categories": categories,
            "course_id": entry["course_id"],
        }

    expected_categories = {
        "factual_accuracy",
        "age_expression",
        "misconception_correction",
        "safety_ethics",
        "out_of_scope_degradation",
    }

    missing = {}
    for stage, info in per_stage.items():
        missing_cats = expected_categories - set(info["categories"].keys())
        if missing_cats:
            missing[stage] = list(missing_cats)

    return {
        "type": "deterministic_automated",
        "fixture_path": str(BENCHMARK_FIXTURE),
        "per_stage": per_stage,
        "expected_categories": sorted(expected_categories),
        "missing_categories_per_stage": missing,
        "integrity_issues": integrity_issues,
        "all_passed": not missing and not integrity_issues,
        "note": "Benchmark questions are human-verified; this script checks fixture integrity and coverage, not answer quality.",
    }


def _source_name(source: dict) -> str:
    for key in ("source", "file_path", "filename", "file_name", "title"):
        value = str(source.get(key) or "").replace("\\", "/").strip()
        if value:
            return value.rsplit("/", 1)[-1].lower()
    return ""


def score_retrieval_cases(cases: list[dict], *, known_sources: set[str]) -> dict:
    """Mechanically score retrieval provenance without an LLM judge."""
    hits = 0
    leaked = 0
    traceable_rows = 0
    source_rows = 0
    fully_traceable = 0
    details = []
    for case in cases:
        expected = {str(item).lower() for item in case["expected_sources"]}
        observed = [item for item in case.get("observed_sources", []) if isinstance(item, dict)]
        names = [_source_name(item) for item in observed]
        hit = any(name in expected for name in names)
        traces = [
            bool(name) and bool(item.get("chunk_id") or item.get("id") or item.get("page"))
            for name, item in zip(names, observed)
        ]
        leak = case.get("observed_kb") != case.get("expected_kb") or any(
            not name or name not in known_sources or name not in expected for name in names
        )
        hits += int(hit)
        leaked += int(leak)
        source_rows += len(observed)
        traceable_rows += sum(traces)
        fully_traceable += int(bool(observed) and all(traces))
        details.append({**case, "hit": hit, "fully_traceable": bool(observed) and all(traces), "leak": leak})
    total = len(cases)
    return {
        "status": "completed",
        "eligible_cases": total,
        "completed_cases": total,
        "retrieval_hit_rate": hits / total if total else 0.0,
        "source_traceability_rate": traceable_rows / source_rows if source_rows else 0.0,
        "fully_traceable_case_rate": fully_traceable / total if total else 0.0,
        "wrong_course_leakage_rate": leaked / total if total else 0.0,
        "cases": details,
    }


def evaluate_retrieval() -> dict:
    """Run real K12 retrieval when every index is ready; otherwise report blocked."""
    from deeptutor.education.knowledge_bootstrap import (
        K12_KB_SOURCE_STEMS,
        expected_k12_targets,
        kb_base_dir,
    )
    from deeptutor.services.rag.factory import DEFAULT_PROVIDER
    from deeptutor.services.rag.index_probe import has_ready_provider_index
    from deeptutor.tools.rag_tool import rag_search

    fixture = load_benchmarks()
    targets = expected_k12_targets(ROOT)
    base_dir = kb_base_dir(ROOT)
    unavailable = [
        target.name
        for target in targets
        if not has_ready_provider_index(base_dir / target.name, DEFAULT_PROVIDER)
    ]
    eligible = [
        (entry, question)
        for entry in fixture.get("benchmarks", [])
        for question in entry.get("questions", [])
        if question.get("retrieval_required")
    ]
    if unavailable:
        return {
            "type": "rag_automated",
            "status": "blocked",
            "reason": "K12 provider indexes are not ready",
            "provider": DEFAULT_PROVIDER,
            "eligible_cases": len(eligible),
            "completed_cases": 0,
            "unavailable_knowledge_bases": unavailable,
        }

    async def run_cases() -> list[dict]:
        cases = []
        for entry, question in eligible:
            result = await rag_search(
                query=question["question_zh"],
                kb_name=entry["knowledge_base"],
                kb_base_dir=str(base_dir),
                provider=DEFAULT_PROVIDER,
                top_k=5,
            )
            cases.append(
                {
                    "question_id": question["id"],
                    "expected_kb": entry["knowledge_base"],
                    "observed_kb": entry["knowledge_base"],
                    "expected_sources": question["expected_sources"],
                    "observed_sources": result.get("sources") or [],
                }
            )
        return cases

    known = {f"{stem}.md".lower() for stem in K12_KB_SOURCE_STEMS.values()}
    scored = score_retrieval_cases(asyncio.run(run_cases()), known_sources=known)
    return {"type": "rag_automated", "provider": DEFAULT_PROVIDER, **scored}


def check_catalog_quality() -> dict:
    """Verify catalog v2 fields are present and well-formed."""
    from deeptutor.education.catalog import load_catalog

    catalog = load_catalog()
    issues = []
    for textbook in catalog.textbooks:
        for course in textbook.courses:
            if not course.learning_objectives:
                issues.append(f"{course.id}: missing learning_objectives")
            if not course.common_misconceptions:
                issues.append(f"{course.id}: missing common_misconceptions")
            if not course.safety_notes:
                issues.append(f"{course.id}: missing safety_notes")
            if not course.reference_sources:
                issues.append(f"{course.id}: missing reference_sources")
            if not course.age_policy:
                issues.append(f"{course.id}: missing age_policy")
    return {
        "type": "deterministic_automated",
        "catalog_version": catalog.version,
        "textbook_count": len(catalog.textbooks),
        "course_count": sum(len(t.courses) for t in catalog.textbooks),
        "issues": issues,
        "all_passed": len(issues) == 0,
    }


def evaluate_llm_judge() -> dict:
    """LLM judge placeholder — clearly marked as NOT run automatically.

    Per M4 §9.3, LLM judge scores must not be written as objective fact. If
    used, the model name, prompt, and raw output must be recorded alongside the
    score so reviewers can see the subjectivity.
    """
    return {
        "type": "llm_judge",
        "status": "not_run",
        "reason": "LLM judge is optional. If used, record model name, prompt, and raw output. Never present LLM judge scores as objective fact.",
        "unverified": True,
    }


def main() -> int:
    REPORTS_DIR.mkdir(exist_ok=True)
    retrieval = evaluate_retrieval()
    unverified_items = [
        "manual_factual_accuracy (requires human spot-check)",
        "stage_blind_test (requires human reviewers)",
    ]
    if retrieval.get("status") != "completed":
        unverified_items.extend(
            [
                "benchmark_retrieval_hit_rate (K12 indexes are not ready)",
                "source_traceability_rate (K12 indexes are not ready)",
                "wrong_course_leakage_rate (K12 indexes are not ready)",
            ]
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": "kitty4-disign/qiming",
        "branch": "feature/k12-competition-v2",
        "milestone": "FP1-FP6",
        "sections": {
            "deterministic_tests": run_deterministic_tests(),
            "catalog_quality": check_catalog_quality(),
            "benchmark_coverage": evaluate_benchmarks(),
            "rag_retrieval": retrieval,
            "llm_judge": evaluate_llm_judge(),
            "manual_spot_check": {
                "type": "manual_spot_check",
                "status": "pending_human_review",
                "note": "Human reviewers must spot-check factual accuracy (>=95%) and stage blind-test differentiation.",
                "unverified": True,
            },
        },
        "quality_gates": {
            "stage_policy_deterministic": "100% required",
            "safety_redline": "100% required",
            "benchmark_retrieval_hit_rate": ">=90% required (automated when indexes are ready)",
            "manual_factual_accuracy": ">=95% required (pending human review)",
            "source_traceability": "100% required (automated when indexes are ready)",
            "wrong_course_leakage": "0% required",
            "stage_blind_test": "reviewer must identify stage from expression/difficulty (pending human review)",
        },
        "unverified_items": unverified_items,
    }

    json_path = REPORTS_DIR / "k12-evaluation.json"
    md_path = REPORTS_DIR / "k12-evaluation.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Markdown summary
    lines = [
        "# K12 教学评估报告",
        "",
        f"生成时间: {report['generated_at']}",
        f"仓库: {report['repository']} @ {report['branch']}",
        f"里程碑: {report['milestone']}",
        "",
        "## 1. 确定性自动化测试",
        "",
        f"- 工具: {report['sections']['deterministic_tests']['tool']}",
        f"- 通过: {report['sections']['deterministic_tests']['passed']}",
        f"- 失败: {report['sections']['deterministic_tests']['failed']}",
        f"- 错误: {report['sections']['deterministic_tests']['errors']}",
        f"- 退出码: {report['sections']['deterministic_tests']['exit_code']}",
        "",
        "## 2. Catalog 质量检查",
        "",
        f"- Catalog 版本: {report['sections']['catalog_quality']['catalog_version']}",
        f"- 教材数: {report['sections']['catalog_quality']['textbook_count']}",
        f"- 课程数: {report['sections']['catalog_quality']['course_count']}",
        f"- 问题数: {len(report['sections']['catalog_quality']['issues'])}",
        f"- 全部通过: {report['sections']['catalog_quality']['all_passed']}",
    ]
    if report["sections"]["catalog_quality"]["issues"]:
        lines.append("")
        lines.append("### 问题清单")
        for issue in report["sections"]["catalog_quality"]["issues"]:
            lines.append(f"- {issue}")

    lines += [
        "",
        "## 3. 基准问题覆盖率",
        "",
        f"- Fixture 路径: {report['sections']['benchmark_coverage'].get('fixture_path', 'N/A')}",
        f"- 预期类别: {', '.join(report['sections']['benchmark_coverage'].get('expected_categories', []))}",
    ]
    for stage, info in report["sections"]["benchmark_coverage"].get("per_stage", {}).items():
        lines.append(f"- {stage}: {info['total_questions']} 题, 类别: {dict(info['categories'])}")
    missing = report["sections"]["benchmark_coverage"].get("missing_categories_per_stage", {})
    if missing:
        lines.append("")
        lines.append("### 缺失类别")
        for stage, cats in missing.items():
            lines.append(f"- {stage}: {', '.join(cats)}")

    rag = report["sections"]["rag_retrieval"]
    lines += [
        "",
        "## 4. RAG 来源追溯",
        "",
        f"- 状态: {rag.get('status')}",
        f"- Provider: {rag.get('provider', 'N/A')}",
        f"- 可评估题目: {rag.get('eligible_cases', 0)}",
        f"- 已完成题目: {rag.get('completed_cases', 0)}",
    ]
    if rag.get("status") == "completed":
        lines.extend(
            [
                f"- Retrieval hit rate: {rag.get('retrieval_hit_rate', 0):.1%}",
                f"- Source traceability rate: {rag.get('source_traceability_rate', 0):.1%}",
                f"- Wrong-course leakage rate: {rag.get('wrong_course_leakage_rate', 0):.1%}",
            ]
        )
    else:
        lines.append(f"- 阻塞原因: {rag.get('reason', 'unknown')}")

    lines += [
        "",
        "## 5. LLM Judge（未运行）",
        "",
        f"- 状态: {report['sections']['llm_judge']['status']}",
        f"- 说明: {report['sections']['llm_judge']['reason']}",
        "",
        "## 6. 人工抽查（待完成）",
        "",
        f"- 状态: {report['sections']['manual_spot_check']['status']}",
        f"- 说明: {report['sections']['manual_spot_check']['note']}",
        "",
        "## 7. 质量门槛",
        "",
    ]
    for gate, requirement in report["quality_gates"].items():
        lines.append(f"- {gate}: {requirement}")

    lines += [
        "",
        "## 8. 未验证项",
        "",
    ]
    for item in report["unverified_items"]:
        lines.append(f"- {item}")

    lines += [
        "",
        "---",
        "",
        "**注意**: LLM judge 评分不作为客观事实。所有 LLM 评分必须附带模型名称、提示词和原始输出。未验证项不构成上线依据。",
    ]

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Report written to: {json_path}")
    print(f"Markdown summary written to: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
