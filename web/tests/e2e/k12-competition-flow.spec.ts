import { expect, test, type Page } from "@playwright/test";

const catalog = {
  version: 1,
  textbooks: [
    {
      id: "k12-ai-primary-lower",
      title_zh: "AI启蒙小课堂",
      title_en: "AI First Steps",
      stage: "primary_lower",
      knowledge_base: "k12-ai-primary-lower",
      default_course_id: "smart-friends",
      courses: [
        {
          id: "smart-friends",
          title_zh: "聪明机器朋友",
          title_en: "Smart Machine Friends",
          summary_zh: "用生活故事认识指令、模式和人工智能安全。",
          knowledge_points: ["指令与顺序", "寻找相同模式"],
          recommended_actions: ["dialogue", "storybook", "quiz"],
        },
      ],
    },
    {
      id: "k12-ai-primary-upper",
      title_zh: "AI探索与创造",
      title_en: "Explore and Create with AI",
      stage: "primary_upper",
      knowledge_base: "k12-ai-primary-upper",
      default_course_id: "image-recognition",
      courses: [
        {
          id: "image-recognition",
          title_zh: "图像识别大冒险",
          title_en: "Image Recognition Adventure",
          summary_zh: "从像素和特征出发，理解机器如何学习区分图片。",
          knowledge_points: ["像素与数字图像", "图像特征", "训练集与测试集"],
          recommended_actions: ["dialogue", "animation", "storybook", "quiz"],
        },
      ],
    },
  ],
};

async function stubApis(page: Page) {
  let profile: Record<string, unknown> | null = null;
  await page.addInitScript(() => {
    window.localStorage.setItem("deeptutor-language", "zh");
  });
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
  await page.route("**/api/v1/knowledge/list", (route) =>
    route.fulfill({ json: { knowledge_bases: [] } }),
  );
  await page.route("**/api/v1/settings", (route) =>
    route.fulfill({ json: { catalog: { llm: [] } } }),
  );
  await page.route("**/api/v1/education/catalog", (route) => route.fulfill({ json: catalog }));
  await page.route("**/api/v1/education/profile", async (route) => {
    if (route.request().method() === "PUT") {
      profile = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ json: { profile } });
      return;
    }
    await route.fulfill({ json: { profile } });
  });
  await page.route("**/api/v1/education/launch-context/*", (route) =>
    route.fulfill({
      json: {
        profile,
        textbook: catalog.textbooks[1],
        course: catalog.textbooks[1].courses[0],
        mastery_path_id: "edu_k12_ai_primary_upper_image_recognition",
        knowledge_bases: [],
        warnings: ["knowledge_base_not_ready:k12-ai-primary-upper"],
      },
    }),
  );
  await page.route("**/api/v1/learning/progress/*/map", (route) =>
    route.fulfill({
      json: {
        book_id: "edu_k12_ai_primary_upper_image_recognition",
        next: {},
        map: {
          counts: { mastered: 0, learning: 1, new: 3, total: 4 },
          due_reviews: 0,
          complete: false,
          modules: [],
        },
      },
    }),
  );
}

test("K12 competition flow reuses tutor, quiz, and responsive workspace", async ({ page }) => {
  await stubApis(page);
  await page.goto("/education");

  await page.getByRole("button", { name: /小学高年级/ }).click();
  await page.getByLabel("年级").selectOption("5");
  await expect(page.getByLabel("教材")).toHaveValue("k12-ai-primary-upper");
  await page.getByRole("button", { name: "保存学习画像" }).click();

  await expect(page.getByRole("heading", { name: "图像识别大冒险" })).toBeVisible();
  const lesson = page.getByRole("article").filter({ hasText: "开始课堂" });
  await lesson.getByRole("button", { name: "打开" }).click();

  await expect(page).toHaveURL(/\/home/);
  await expect(page.getByRole("button", { name: /K12 学习导师/ })).toBeVisible();
  const composer = page.locator("textarea");
  await expect(composer).toHaveValue(/图像识别大冒险/);
  await page.waitForTimeout(150);
  await expect(composer).toHaveValue(/图像识别大冒险/);

  await page.goto("/education");
  const quiz = page.getByRole("article").filter({ hasText: "趣味测验" });
  await quiz.getByRole("button", { name: "打开" }).click();

  await expect(page).toHaveURL(/\/home/);
  await expect(page.getByRole("button", { name: /测验/ })).toBeVisible();
  await expect(page.getByLabel("数量")).toHaveValue("3");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/education");
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
