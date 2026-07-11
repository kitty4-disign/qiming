import test from "node:test";
import assert from "node:assert/strict";

import { buildEducationComposerPreset } from "../lib/education-launch-adapter";
import type {
  EducationAction,
  EducationLaunchIntent,
} from "../lib/education-launch";

function primaryUpperIntent(action: EducationAction): EducationLaunchIntent {
  return {
    version: 1,
    action,
    courseId: "image-recognition",
    topic: "图像识别大冒险",
    masteryPathId: "edu_k12_ai_primary_upper_image_recognition",
    knowledgeBases: ["k12-ai-primary-upper"],
    createdAt: 1000,
  };
}

test("lesson launches K12 mastery tutor", () => {
  const preset = buildEducationComposerPreset(primaryUpperIntent("lesson"));
  assert.equal(preset.capability, "k12_tutor");
  assert.deepEqual(preset.config, {
    course_id: "image-recognition",
    mastery_path_id: "edu_k12_ai_primary_upper_image_recognition",
  });
  assert.match(preset.draft, /开始今天的学习/);
});

test("quiz reuses deep_question with age-neutral auto difficulty", () => {
  const preset = buildEducationComposerPreset(primaryUpperIntent("quiz"));
  assert.equal(preset.capability, "deep_question");
  assert.equal(preset.config.num_questions, 3);
  assert.equal(preset.config.difficulty, "auto");
  assert.deepEqual(preset.config.question_types, ["choice", "concept"]);
});

test("animation reuses visualize", () => {
  const preset = buildEducationComposerPreset(primaryUpperIntent("animation"));
  assert.equal(preset.capability, "visualize");
  assert.equal(preset.config.render_mode, "html");
});

test("coding keeps K12 tutor and enables only code execution", () => {
  const preset = buildEducationComposerPreset(primaryUpperIntent("coding"));
  assert.equal(preset.capability, "k12_tutor");
  assert.deepEqual(preset.tools, ["code_execution"]);
  assert.match(preset.draft, /先给我一个可运行的代码框架/);
});
