import type { EducationLaunchIntent } from "./education-launch";

export interface EducationComposerPreset {
  capability: "k12_tutor" | "deep_question" | "visualize";
  tools: string[];
  knowledgeBases: string[];
  config: Record<string, unknown>;
  draft: string;
}

function k12Config(intent: EducationLaunchIntent): Record<string, unknown> {
  return {
    course_id: intent.courseId,
    mastery_path_id: intent.masteryPathId,
  };
}

export function buildEducationComposerPreset(
  intent: EducationLaunchIntent,
): EducationComposerPreset {
  if (intent.action === "lesson") {
    return {
      capability: "k12_tutor",
      tools: [],
      knowledgeBases: intent.knowledgeBases,
      config: k12Config(intent),
      draft: `请带我开始今天的学习：${intent.topic}。先了解我已经知道什么，再一步步讲解。`,
    };
  }
  if (intent.action === "quiz") {
    return {
      capability: "deep_question",
      tools: [],
      knowledgeBases: intent.knowledgeBases,
      config: {
        mode: "custom",
        num_questions: 3,
        difficulty: "auto",
        question_types: ["choice", "concept"],
        per_type_counts: {},
        paper_path: "",
        max_questions: 10,
        topic: intent.topic,
      },
      draft: `请围绕“${intent.topic}”生成三道适合当前学习阶段的趣味测验。`,
    };
  }
  if (intent.action === "animation") {
    return {
      capability: "visualize",
      tools: [],
      knowledgeBases: intent.knowledgeBases,
      config: {
        render_mode: "html",
        quality: "medium",
        style_hint: "K12 interactive explanation with labeled steps and no autoplay audio",
      },
      draft: `请为“${intent.topic}”制作分步骤、带清晰标注的互动动画讲解。`,
    };
  }
  if (intent.action === "coding") {
    return {
      capability: "k12_tutor",
      tools: ["code_execution"],
      knowledgeBases: intent.knowledgeBases,
      config: k12Config(intent),
      draft: `围绕“${intent.topic}”设计一次编程实践。先给我一个可运行的代码框架，再引导我逐步完成。`,
    };
  }
  throw new Error("storybook launches through the book workspace");
}
