# K12 教学评估报告

生成时间: 2026-08-09T08:51:39.537230+00:00
仓库: kitty4-disign/qiming @ feature/k12-competition-v2
里程碑: FP1-FP6

## 1. 确定性自动化测试

- 工具: pytest
- 通过: 120
- 失败: 0
- 错误: 0
- 退出码: 0

## 2. Catalog 质量检查

- Catalog 版本: 2
- 教材数: 4
- 课程数: 8
- 问题数: 0
- 全部通过: True

## 3. 基准问题覆盖率

- Fixture 路径: D:\ai\DeepTutor\tests\education\fixtures\k12_benchmark.yaml
- 预期类别: age_expression, factual_accuracy, misconception_correction, out_of_scope_degradation, safety_ethics
- primary_lower: 5 题, 类别: {'factual_accuracy': 1, 'age_expression': 1, 'misconception_correction': 1, 'safety_ethics': 1, 'out_of_scope_degradation': 1}
- primary_upper: 5 题, 类别: {'factual_accuracy': 1, 'age_expression': 1, 'misconception_correction': 1, 'safety_ethics': 1, 'out_of_scope_degradation': 1}
- middle: 5 题, 类别: {'factual_accuracy': 1, 'age_expression': 1, 'misconception_correction': 1, 'safety_ethics': 1, 'out_of_scope_degradation': 1}
- high: 5 题, 类别: {'factual_accuracy': 1, 'age_expression': 1, 'misconception_correction': 1, 'safety_ethics': 1, 'out_of_scope_degradation': 1}

## 4. RAG 来源追溯

- 状态: completed
- Provider: llamaindex
- 可评估题目: 16
- 已完成题目: 16
- Retrieval hit rate: 100.0%
- Source traceability rate: 100.0%
- Wrong-course leakage rate: 0.0%

## 5. LLM Judge（未运行）

- 状态: not_run
- 说明: LLM judge is optional. If used, record model name, prompt, and raw output. Never present LLM judge scores as objective fact.

## 6. 人工抽查（待完成）

- 状态: pending_human_review
- 说明: Human reviewers must spot-check factual accuracy (>=95%) and stage blind-test differentiation.

## 7. 质量门槛

- stage_policy_deterministic: 100% required
- safety_redline: 100% required
- benchmark_retrieval_hit_rate: >=90% required (automated when indexes are ready)
- manual_factual_accuracy: >=95% required (pending human review)
- source_traceability: 100% required (automated when indexes are ready)
- wrong_course_leakage: 0% required
- stage_blind_test: reviewer must identify stage from expression/difficulty (pending human review)

## 8. 未验证项

- manual_factual_accuracy (requires human spot-check)
- stage_blind_test (requires human reviewers)

---

**注意**: LLM judge 评分不作为客观事实。所有 LLM 评分必须附带模型名称、提示词和原始输出。未验证项不构成上线依据。