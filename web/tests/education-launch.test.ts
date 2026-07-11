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

test("launch intent is consumed exactly once", () => {
  const storage = memoryStorage();
  saveEducationLaunch(
    {
      version: 1,
      action: "lesson",
      courseId: "image-recognition",
      topic: "图像识别大冒险",
      masteryPathId: "edu_k12_ai_primary_upper_image_recognition",
      knowledgeBases: ["k12-ai-primary-upper"],
      createdAt: 1000,
    },
    storage,
  );
  assert.equal(consumeEducationLaunch(storage, 2000)?.action, "lesson");
  assert.equal(consumeEducationLaunch(storage, 2000), null);
});

test("launch intent expires after five minutes", () => {
  const storage = memoryStorage();
  saveEducationLaunch(
    {
      version: 1,
      action: "quiz",
      courseId: "image-recognition",
      topic: "图像识别大冒险",
      masteryPathId: "edu_path",
      knowledgeBases: [],
      createdAt: 1000,
    },
    storage,
  );
  assert.equal(consumeEducationLaunch(storage, 301001), null);
});
