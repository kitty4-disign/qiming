import test from "node:test";
import assert from "node:assert/strict";

import {
  buildEducationComposerPreset,
  buildEducationStorybookPreset,
} from "../lib/education-launch-adapter";
import type { EducationLaunchIntent } from "../lib/education-launch";

const STAGES = ["primary_lower", "primary_upper", "middle", "high"] as const;
type Stage = (typeof STAGES)[number];

function stageIntent(
  action: EducationLaunchIntent["action"],
  stage: Stage,
  overrides: Partial<EducationLaunchIntent> = {},
): EducationLaunchIntent {
  return {
    version: 2,
    action,
    courseId: "image-recognition",
    textbookId: `k12-ai-${stage}`,
    masteryPathId: `edu_k12_ai_${stage}_image_recognition`,
    knowledgeBases: [`k12-ai-${stage}`],
    stage,
    grade: stage === "primary_lower" ? 2 : stage === "primary_upper" ? 5 : stage === "middle" ? 8 : 11,
    interests: [],
    preferredModalities: [],
    recommendationReasons: [],
    topic: "什么是训练数据",
    summary: "理解机器从数据中学习",
    knowledgePoints: ["数据示例", "标签", "训练集与测试集"],
    createdAt: 1000,
    ...overrides,
  };
}

test("lesson launches K12 mastery tutor", () => {
  const preset = buildEducationComposerPreset(stageIntent("lesson", "primary_upper"));
  assert.equal(preset.capability, "k12_tutor");
  assert.deepEqual(preset.config, {
    course_id: "image-recognition",
    mastery_path_id: "edu_k12_ai_primary_upper_image_recognition",
    activity_mode: "lesson",
    stage: "primary_upper",
    grade: 5,
    knowledge_point_id: "",
  });
  assert.match(preset.draft, /开始今天的学习/);
  assert.match(preset.draft, /学段：primary_upper/);
});

test("quiz routes to K12 tutor with activity_mode=quiz", () => {
  const preset = buildEducationComposerPreset(stageIntent("quiz", "middle"));
  assert.equal(preset.capability, "k12_tutor");
  assert.equal(preset.config.activity_mode, "quiz");
  assert.equal(preset.config.stage, "middle");
  assert.match(preset.draft, /趣味测验/);
  assert.match(preset.draft, /难度定位/);
});

test("animation reuses visualize with stage-aware style_hint", () => {
  const preset = buildEducationComposerPreset(stageIntent("animation", "high"));
  assert.equal(preset.capability, "visualize");
  assert.equal(preset.config.render_mode, "html");
  assert.match(preset.config.style_hint as string, /formulas|pseudocode/);
});

test("four stages produce four distinct animation style_hints", () => {
  const hints = STAGES.map(
    (stage) =>
      buildEducationComposerPreset(stageIntent("animation", stage)).config
        .style_hint as string,
  );
  assert.equal(new Set(hints).size, 4, "each stage must have a distinct style_hint");
  assert.match(hints[0], /K1-3/);
  assert.match(hints[1], /K4-6/);
  assert.match(hints[2], /K7-9/);
  assert.match(hints[3], /K10-12/);
});

test("four stages produce four distinct quiz difficulty bands", () => {
  const drafts = STAGES.map(
    (stage) =>
      buildEducationComposerPreset(stageIntent("quiz", stage)).draft,
  );
  // All four drafts contain the stage-specific difficulty line and they differ.
  assert.equal(new Set(drafts).size, 4);
  assert.match(drafts[0], /认得图片/);
  assert.match(drafts[3], /公式推导/);
});

test("coding keeps K12 tutor and enables only code execution", () => {
  const preset = buildEducationComposerPreset(stageIntent("coding", "high"));
  assert.equal(preset.capability, "k12_tutor");
  assert.equal(preset.config.activity_mode, "coding");
  assert.deepEqual(preset.tools, ["code_execution"]);
  assert.match(preset.draft, /可运行/);
});

test("coding scaffold differs by stage", () => {
  const drafts = STAGES.map(
    (stage) => buildEducationComposerPreset(stageIntent("coding", stage)).draft,
  );
  assert.equal(new Set(drafts).size, 4);
  assert.match(drafts[0], /积木/);
  assert.match(drafts[2], /TODO/);
  assert.match(drafts[3], /测试/);
});

test("animation preset carries stage/grade/course/knowledge_point_id", () => {
  const preset = buildEducationComposerPreset(
    stageIntent("animation", "primary_upper", { knowledgePointId: "kp_pixels" }),
  );
  assert.equal(preset.stage, "primary_upper");
  assert.equal(preset.grade, 5);
  assert.equal(preset.courseId, "image-recognition");
  assert.equal(preset.knowledgePointId, "kp_pixels");
  assert.equal(preset.config.knowledge_point_id, "kp_pixels");
});

test("lesson draft mentions KB unreadiness when no knowledge bases", () => {
  const preset = buildEducationComposerPreset(
    stageIntent("lesson", "primary_upper", { knowledgeBases: [] }),
  );
  assert.match(preset.draft, /教材库未就绪/);
});

test("lesson draft includes recommendation reason when provided", () => {
  const preset = buildEducationComposerPreset(
    stageIntent("lesson", "primary_upper", {
      recommendationReasons: [
        {
          code: "weak_point",
          message_zh: "最近答错过一次，建议先巩固",
          evidence: { attempts: 1 },
        },
      ],
    }),
  );
  assert.match(preset.draft, /推荐理由（weak_point）/);
});

test("storybook builds book workspace intent with stage constraints", () => {
  const preset = buildEducationStorybookPreset(stageIntent("storybook", "primary_lower"));
  assert.equal(preset.kind, "storybook");
  assert.equal(preset.stage, "primary_lower");
  assert.equal(preset.maxPages, 8);
  assert.equal(preset.maxCharsPerPage, 80);
  assert.match(preset.intent, /不超过 8 页/);
  assert.match(preset.intent, /不超过约 80 个中文字符/);
  assert.match(preset.intent, /至少两页包含可回答的小问题/);
  assert.match(preset.intent, /安全与伦理提示/);
});

test("storybook constraints relax for older stages", () => {
  const high = buildEducationStorybookPreset(stageIntent("storybook", "high"));
  assert.ok(high.maxPages > 8);
  assert.ok(high.maxCharsPerPage > 80);
});

test("storybook preset carries courseId and knowledgePointId", () => {
  const preset = buildEducationStorybookPreset(
    stageIntent("storybook", "primary_upper", { knowledgePointId: "kp_features" }),
  );
  assert.equal(preset.courseId, "image-recognition");
  assert.equal(preset.knowledgePointId, "kp_features");
});
