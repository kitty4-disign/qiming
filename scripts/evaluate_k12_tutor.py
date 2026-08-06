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

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

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
    # Parse "73 passed" or "2 failed, 71 passed" from pytest summary line.
    passed = 0
    failed = 0
    errors = 0
    for line in output.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            for token in line.split():
                if token.isdigit():
                    if "failed" in line:
                        failed = int(token)
                    elif "error" in line:
                        errors = int(token)
                    elif "passed" in line:
                        passed = int(token)
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

    per_stage: dict[str, dict] = {}
    for entry in benchmarks.get("benchmarks", []):
        stage = entry["stage"]
        questions = entry.get("questions", [])
        categories = {}
        for q in questions:
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
        "type": "manual_spot_check",
        "fixture_path": str(BENCHMARK_FIXTURE),
        "per_stage": per_stage,
        "expected_categories": sorted(expected_categories),
        "missing_categories_per_stage": missing,
        "note": "Benchmark questions are human-verified; this script checks fixture integrity and coverage, not answer quality.",
    }


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

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": "kitty4-disign/qiming",
        "branch": "feature/k12-competition-v2",
        "milestone": "M4",
        "sections": {
            "deterministic_tests": run_deterministic_tests(),
            "catalog_quality": check_catalog_quality(),
            "benchmark_coverage": evaluate_benchmarks(),
            "llm_judge": evaluate_llm_judge(),
            "manual_spot_check": {
                "type": "manual_spot_check",
                "status": "pending_human_review",
                "note": "Human reviewers must spot-check factual accuracy (>=95%), source traceability (100%), and stage blind-test differentiation.",
                "unverified": True,
            },
        },
        "quality_gates": {
            "stage_policy_deterministic": "100% required",
            "safety_redline": "100% required",
            "benchmark_retrieval_hit_rate": ">=90% required (not yet automated)",
            "manual_factual_accuracy": ">=95% required (pending human review)",
            "source_traceability": "100% required (not yet automated)",
            "stage_blind_test": "reviewer must identify stage from expression/difficulty (pending human review)",
        },
        "unverified_items": [
            "benchmark_retrieval_hit_rate (requires RAG index)",
            "manual_factual_accuracy (requires human spot-check)",
            "source_traceability (requires RAG index)",
            "stage_blind_test (requires human reviewers)",
        ],
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

    lines += [
        "",
        "## 4. LLM Judge（未运行）",
        "",
        f"- 状态: {report['sections']['llm_judge']['status']}",
        f"- 说明: {report['sections']['llm_judge']['reason']}",
        "",
        "## 5. 人工抽查（待完成）",
        "",
        f"- 状态: {report['sections']['manual_spot_check']['status']}",
        f"- 说明: {report['sections']['manual_spot_check']['note']}",
        "",
        "## 6. 质量门槛",
        "",
    ]
    for gate, requirement in report["quality_gates"].items():
        lines.append(f"- {gate}: {requirement}")

    lines += [
        "",
        "## 7. 未验证项",
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
