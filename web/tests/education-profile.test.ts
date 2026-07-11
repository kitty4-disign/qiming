import test from "node:test";
import assert from "node:assert/strict";

import { gradesForStage, textbooksForStage } from "../lib/education-profile";
import type { EducationCatalog } from "../lib/education-types";

const catalog: EducationCatalog = {
  version: 1,
  textbooks: [
    {
      id: "lower",
      title_zh: "低年级",
      title_en: "Lower",
      stage: "primary_lower",
      knowledge_base: "lower",
      default_course_id: "course-lower",
      courses: [],
    },
    {
      id: "middle",
      title_zh: "初中",
      title_en: "Middle",
      stage: "middle",
      knowledge_base: "middle",
      default_course_id: "course-middle",
      courses: [],
    },
  ],
};

test("gradesForStage returns the competition stage ranges", () => {
  assert.deepEqual(gradesForStage("primary_lower"), [1, 2, 3]);
  assert.deepEqual(gradesForStage("primary_upper"), [4, 5, 6]);
  assert.deepEqual(gradesForStage("middle"), [7, 8, 9]);
  assert.deepEqual(gradesForStage("high"), [10, 11, 12]);
});

test("textbooksForStage excludes textbooks from other stages", () => {
  assert.deepEqual(
    textbooksForStage(catalog, "middle").map((textbook) => textbook.id),
    ["middle"],
  );
  assert.deepEqual(textbooksForStage(catalog, "high"), []);
});
