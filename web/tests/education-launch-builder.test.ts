import test from "node:test";
import assert from "node:assert/strict";

import { buildEducationLaunchIntent } from "../lib/education-launch-builder";
import type { EducationLaunchIntent } from "../lib/education-launch";
import type {
  EducationCourse,
  EducationLaunchContext,
  EducationRecommendation,
  StudentProfile,
} from "../lib/education-types";

function baseProfile(): StudentProfile {
  return {
    schema_version: 1,
    display_name: "小明",
    stage: "primary_upper",
    grade: 5,
    textbook_id: "k12-ai-primary-upper",
    interests: ["绘画", "机器人"],
    preferred_modalities: ["dialogue", "quiz"],
    learning_goal: "了解 AI 如何看图",
  };
}

function baseCourse(): EducationCourse {
  return {
    id: "image-recognition",
    title_zh: "图像识别大冒险",
    title_en: "Image Recognition Adventure",
    summary_zh: "从像素和特征出发",
    knowledge_points: ["像素与数字图像", "图像特征"],
    recommended_actions: ["dialogue", "quiz", "animation"],
  };
}

function baseContext(): EducationLaunchContext {
  return {
    profile: baseProfile(),
    textbook: {
      id: "k12-ai-primary-upper",
      title_zh: "小学高年级 AI 通识",
      title_en: "Primary Upper AI",
      stage: "primary_upper",
      knowledge_base: "k12-ai-primary-upper",
      default_course_id: "image-recognition",
      courses: [baseCourse()],
    },
    course: baseCourse(),
    mastery_path_id: "edu_k12_ai_primary_upper_image_recognition",
    knowledge_bases: ["k12-ai-primary-upper"],
    warnings: [],
  };
}

function baseRecommendation(): EducationRecommendation {
  return {
    course_id: "image-recognition",
    knowledge_point_id: "kp_features",
    knowledge_point_name: "图像特征",
    activity: "quiz",
    title: "做一道关于图像特征的题",
    reasons: [
      {
        code: "weak_point",
        message_zh: "最近答错过一次，建议先巩固",
        evidence: { attempts: 1 },
      },
    ],
  };
}

test("buildEducationLaunchIntent produces v2 intent carrying profile+reasons", () => {
  const intent = buildEducationLaunchIntent({
    action: "quiz",
    course: baseCourse(),
    profile: baseProfile(),
    launchContext: baseContext(),
    recommendation: baseRecommendation(),
    createdAt: 42,
  });
  assert.equal(intent.version, 2);
  assert.equal(intent.action, "quiz");
  assert.equal(intent.courseId, "image-recognition");
  assert.equal(intent.textbookId, "k12-ai-primary-upper");
  assert.equal(intent.masteryPathId, "edu_k12_ai_primary_upper_image_recognition");
  assert.equal(intent.knowledgePointId, "kp_features");
  assert.equal(intent.stage, "primary_upper");
  assert.equal(intent.grade, 5);
  assert.deepEqual(intent.interests, ["绘画", "机器人"]);
  assert.deepEqual(intent.preferredModalities, ["dialogue", "quiz"]);
  assert.equal(intent.recommendationReasons.length, 1);
  assert.equal(intent.recommendationReasons[0].code, "weak_point");
  assert.equal(intent.createdAt, 42);
});

test("buildEducationLaunchIntent tolerates missing recommendation", () => {
  const intent = buildEducationLaunchIntent({
    action: "lesson",
    course: baseCourse(),
    profile: baseProfile(),
    launchContext: baseContext(),
  });
  assert.equal(intent.action, "lesson");
  assert.equal(intent.knowledgePointId, undefined);
  assert.deepEqual(intent.recommendationReasons, []);
});

test("buildEducationLaunchIntent overrides knowledgePointId when provided", () => {
  const intent = buildEducationLaunchIntent({
    action: "animation",
    course: baseCourse(),
    profile: baseProfile(),
    launchContext: baseContext(),
    knowledgePointId: "kp_pixels",
  });
  assert.equal(intent.knowledgePointId, "kp_pixels");
});
