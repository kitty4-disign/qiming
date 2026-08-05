import test from "node:test";
import assert from "node:assert/strict";

import {
  consumeEducationLaunch,
  saveEducationLaunch,
  type KeyValueStorage,
} from "../lib/education-launch";

function memoryStorage(): KeyValueStorage {
  const values = new Map<string, string>();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => void values.set(key, value),
    removeItem: (key) => void values.delete(key),
  };
}

function v2Intent(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    version: 2,
    action: "lesson",
    courseId: "image-recognition",
    textbookId: "k12-ai-primary-upper",
    masteryPathId: "edu_k12_ai_primary_upper_image_recognition",
    knowledgeBases: ["k12-ai-primary-upper"],
    stage: "primary_upper",
    grade: 4,
    interests: ["绘画"],
    preferredModalities: ["dialogue", "quiz"],
    recommendationReasons: [
      { code: "next_new_point", message_zh: "推荐进入下一个新知识点", evidence: { index: "0" } },
    ],
    topic: "图像识别大冒险",
    summary: "从像素和特征出发",
    knowledgePoints: ["像素与数字图像", "图像特征"],
    createdAt: 1000,
    ...overrides,
  };
}

test("v2 launch intent is consumed exactly once", () => {
  const storage = memoryStorage();
  saveEducationLaunch(v2Intent() as never, storage);
  assert.equal(consumeEducationLaunch(storage, 2000)?.action, "lesson");
  assert.equal(consumeEducationLaunch(storage, 2000), null);
});

test("v2 launch intent expires after five minutes", () => {
  const storage = memoryStorage();
  saveEducationLaunch(
    v2Intent({ action: "quiz" }) as never,
    storage,
  );
  assert.equal(consumeEducationLaunch(storage, 301001), null);
});

test("v2 storybook launch keeps knowledge points and summary", () => {
  const storage = memoryStorage();
  saveEducationLaunch(
    v2Intent({ action: "storybook" }) as never,
    storage,
  );
  const intent = consumeEducationLaunch(storage, 2000);
  assert.equal(intent?.action, "storybook");
  assert.equal(intent?.summary, "从像素和特征出发");
  assert.deepEqual(intent?.knowledgePoints, ["像素与数字图像", "图像特征"]);
  assert.equal(intent?.stage, "primary_upper");
  assert.equal(intent?.grade, 4);
});

test("v1 intent is upgraded to v2 with safe defaults", () => {
  const storage = memoryStorage();
  storage.setItem(
    "deeptutor.education.launch.v1",
    JSON.stringify({
      version: 1,
      action: "lesson",
      courseId: "image-recognition",
      topic: "图像识别大冒险",
      masteryPathId: "edu_path",
      knowledgeBases: ["k12-ai-primary-upper"],
      createdAt: 1000,
    }),
  );
  const intent = consumeEducationLaunch(storage, 2000);
  assert.equal(intent?.version, 2);
  assert.equal(intent?.action, "lesson");
  assert.equal(intent?.stage, "primary_upper");
  assert.equal(intent?.grade, 4);
  assert.deepEqual(intent?.interests, []);
  assert.deepEqual(intent?.recommendationReasons, []);
});

test("tampered intent (bad stage) is rejected", () => {
  const storage = memoryStorage();
  storage.setItem(
    "deeptutor.education.launch.v2",
    JSON.stringify(v2Intent({ stage: "kindergarten" })),
  );
  assert.equal(consumeEducationLaunch(storage, 2000), null);
});

test("tampered intent (bad action) is rejected", () => {
  const storage = memoryStorage();
  storage.setItem(
    "deeptutor.education.launch.v2",
    JSON.stringify(v2Intent({ action: "watch_video" })),
  );
  assert.equal(consumeEducationLaunch(storage, 2000), null);
});

test("tampered intent (non-numeric grade) is rejected", () => {
  const storage = memoryStorage();
  storage.setItem(
    "deeptutor.education.launch.v2",
    JSON.stringify(v2Intent({ grade: "fourth" })),
  );
  assert.equal(consumeEducationLaunch(storage, 2000), null);
});
