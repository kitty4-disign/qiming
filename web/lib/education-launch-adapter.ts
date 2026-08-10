import type {
  EducationLaunchIntent,
  EducationStageLiteral,
  LearningModalityLiteral,
} from "./education-launch";
import type { EducationContext } from "./unified-ws";

export interface EducationComposerPreset {
  capability: "k12_tutor" | "deep_question" | "visualize";
  tools: string[];
  knowledgeBases: string[];
  config: Record<string, unknown>;
  educationContext: EducationContext;
  draft: string;
  topic: string;
}

export interface EducationStorybookPreset {
  kind: "storybook";
  topic: string;
  summary: string;
  knowledgePoints: string[];
  knowledgeBases: string[];
  stage: EducationStageLiteral;
  grade: number;
  courseId: string;
  knowledgePointId?: string;
  // Concrete constraints per stage (page count, per-page char budget).
  maxPages: number;
  maxCharsPerPage: number;
  intent: string;
}

// Stage-aware style_hint for visualize. Old code used a single hard-coded
// English hint; now the hint must vary by stage (M2 §7.2 C).
const ANIMATION_STYLE_HINT: Record<EducationStageLiteral, string> = {
  primary_lower:
    "K1-3: very large shapes, few labels, one change at a time, big play/pause buttons, no autoplay audio",
  primary_upper:
    "K4-6: large labeled diagrams, step-by-step causal flow, friendly colors, clear narration prompts",
  middle:
    "K7-9: data, features, steps and causal outcomes; allow simple parameters and small experiments",
  high:
    "K10-12: allow formulas, pseudocode, complexity analysis and parameter sweeps",
};

// Coding scaffolding strategy differs by stage (M2 §7.2 E).
const CODING_SCAFFOLD: Record<
  EducationStageLiteral,
  { strategy: string; firstTurn: string }
> = {
  primary_lower: {
    strategy: "block-style pseudocode with fill-in blanks",
    firstTurn:
      "先给我一个像积木一样的可运行伪代码框架，关键步骤留空让我填写，再让我说说我的思路。",
  },
  primary_upper: {
    strategy: "block-style pseudocode with simple Python helpers",
    firstTurn:
      "先给我一个可运行的简单代码框架，把关键变量留空让我填写，再让我试着运行一次。",
  },
  middle: {
    strategy: "partial Python code with TODO markers",
    firstTurn:
      "请给我一段带 TODO 标注的可运行 Python 框架，并写清楚每个 TODO 要解决的小目标，先不要给完整答案。",
  },
  high: {
    strategy: "task, tests and debugging hints",
    firstTurn:
      "请提供任务说明、一段带 TODO 的最小框架和一组可运行的测试，让我先尝试实现并跑通测试，先不要给最终答案。",
  },
};

// Quiz difficulty targets per stage. Difficulty still adapts to mastery later,
// but the initial band must depend on grade instead of being a fixed string.
const QUIZ_DIFFICULTY: Record<EducationStageLiteral, string> = {
  primary_lower: "认得图片、找出明显特征为主，避免抽象符号",
  primary_upper: "用具体例子和图像描述概念，少量计算",
  middle: "结合数据和小型计算，关注因果关系",
  high: "允许公式推导、参数分析和多步推理",
};

function k12Config(
  intent: EducationLaunchIntent,
  activityMode: "lesson" | "quiz" | "coding" = "lesson",
): Record<string, unknown> {
  const base: Record<string, unknown> = {
    course_id: intent.courseId,
    mastery_path_id: intent.masteryPathId,
    activity_mode: activityMode,
  };
  if (activityMode === "quiz") {
    return {
      ...base,
      // createdAt is unique for each dashboard launch and remains stable for
      // the full multi-turn quiz. The backend persists the counters in the
      // K12 capability config, so reload/follow-up turns keep the same run.
      quiz_run_id: String(intent.createdAt),
      quiz_question_count: 3,
      quiz_answered_count: 0,
      quiz_last_answered_turn_id: "",
    };
  }
  return base;
}

function stageLine(intent: EducationLaunchIntent): string {
  return `学段：${intent.stage}，年级：${intent.grade}`;
}

function reasonsLine(intent: EducationLaunchIntent): string {
  if (intent.recommendationReasons.length === 0) return "";
  const head = intent.recommendationReasons[0];
  return `推荐理由（${head.code}）：${head.message_zh}`;
}

function assembleLessonDraft(intent: EducationLaunchIntent): string {
  const lines = [
    `请带我开始今天的学习：${intent.topic}。`,
    stageLine(intent),
    "先诊断我已经知道什么，再只推进一个主要知识点。",
    "每轮结束只提一个清晰的问题。",
  ];
  const reason = reasonsLine(intent);
  if (reason) lines.push(reason);
  if (intent.knowledgeBases.length === 0) {
    lines.push("注意：教材库未就绪，回复需明确标注“基于通识回答，教材库未就绪”。");
  } else {
    lines.push("回复需要显示教材来源卡片或引用。");
  }
  return lines.join("\n");
}

function assembleQuizDraft(intent: EducationLaunchIntent): string {
  const difficulty = QUIZ_DIFFICULTY[intent.stage];
  const kp = intent.knowledgePointId ? `知识点：${intent.knowledgePointId}。` : "";
  return [
    `请围绕“${intent.topic}”开始一轮 3 题趣味测验。`,
    stageLine(intent),
    kp,
    `难度定位：${difficulty}`,
    "先读我的掌握度，再出第 1 题让我回答；每次只展示一题。",
    "每次提交后先判分和反馈，再进入下一题；第 3 题反馈后给出本轮总结并结束，不出第 4 题。",
    "不要提前把标准答案发到浏览器；提交后再显示正误、错误位置、原因和下一步。",
  ].join("\n");
}

function assembleAnimationDraft(intent: EducationLaunchIntent): string {
  return [
    `请为“${intent.topic}”制作分步骤、带清晰标注的互动动画讲解。`,
    stageLine(intent),
    `风格指引：${ANIMATION_STYLE_HINT[intent.stage]}`,
    "动画中至少有一个可点击问题，能通过 dt:visualize-prompt 回到对话。",
    "页面必须有“我看懂了/还没懂”反馈按钮，但点击不能直接判定掌握。",
  ].join("\n");
}

function assembleCodingDraft(intent: EducationLaunchIntent): string {
  const scaffold = CODING_SCAFFOLD[intent.stage];
  return [
    `围绕“${intent.topic}”设计一次编程实践。`,
    stageLine(intent),
    `脚手架策略：${scaffold.strategy}`,
    scaffold.firstTurn,
    "代码运行结果由 Sandbox 返回，不能由模型编造。",
  ].join("\n");
}

export function buildEducationComposerPreset(
  intent: EducationLaunchIntent,
): EducationComposerPreset {
  const base = {
    educationContext: {
      stage: intent.stage,
      grade: intent.grade,
      ...(intent.knowledgePointId
        ? { knowledge_point_id: intent.knowledgePointId }
        : {}),
    },
    topic: intent.topic,
  };
  if (intent.action === "lesson") {
    return {
      ...base,
      capability: "k12_tutor",
      tools: [],
      knowledgeBases: intent.knowledgeBases,
      config: k12Config(intent, "lesson"),
      draft: assembleLessonDraft(intent),
    };
  }
  if (intent.action === "quiz") {
    return {
      ...base,
      capability: "k12_tutor",
      tools: [],
      knowledgeBases: intent.knowledgeBases,
      config: k12Config(intent, "quiz"),
      draft: assembleQuizDraft(intent),
    };
  }
  if (intent.action === "animation") {
    return {
      ...base,
      capability: "visualize",
      tools: [],
      knowledgeBases: intent.knowledgeBases,
      config: {
        render_mode: "html",
        quality: "medium",
        style_hint: ANIMATION_STYLE_HINT[intent.stage],
      },
      draft: assembleAnimationDraft(intent),
    };
  }
  if (intent.action === "coding") {
    return {
      ...base,
      capability: "k12_tutor",
      tools: ["code_execution"],
      knowledgeBases: intent.knowledgeBases,
      config: k12Config(intent, "coding"),
      draft: assembleCodingDraft(intent),
    };
  }
  throw new Error("storybook launches through the book workspace");
}

// Storybook stage constraints (M2 §7.2 D): primary_lower flagship 6-8 pages,
// <=80 zh chars per page; older stages relax these.
const STORYBOOK_CONSTRAINTS: Record<
  EducationStageLiteral,
  { maxPages: number; maxCharsPerPage: number }
> = {
  primary_lower: { maxPages: 8, maxCharsPerPage: 80 },
  primary_upper: { maxPages: 12, maxCharsPerPage: 120 },
  middle: { maxPages: 16, maxCharsPerPage: 160 },
  high: { maxPages: 20, maxCharsPerPage: 220 },
};

export function buildEducationStorybookPreset(
  intent: EducationLaunchIntent,
): EducationStorybookPreset {
  if (intent.action !== "storybook") {
    throw new Error("storybook preset requires a storybook launch intent");
  }
  const knowledgePoints = intent.knowledgePoints ?? [];
  const pointsText = knowledgePoints.length
    ? knowledgePoints.map((point, index) => `${index + 1}. ${point}`).join("\n")
    : "围绕课程核心概念展开";
  const summary = intent.summary || intent.topic;
  const constraints = STORYBOOK_CONSTRAINTS[intent.stage];
  const safetyLine =
    "结尾必须包含“今天学会了什么”和安全与伦理提示（不收集个人信息、不模仿危险行为）。";
  const questionLine = "至少两页包含可回答的小问题。";
  const failureLine = "生成失败时保留输入内容并允许重试，不要回到空白页。";
  const intentText = [
    `请为 K12 课程“${intent.topic}”生成一本适合当前学段的互动绘本。`,
    stageLine(intent),
    `课程概要：${summary}`,
    `篇幅限制：不超过 ${constraints.maxPages} 页，每页不超过约 ${constraints.maxCharsPerPage} 个中文字符。`,
    "绘本需要包含：",
    "- 生活化故事主线",
    "- 分步骤知识讲解",
    questionLine,
    safetyLine,
    failureLine,
    "核心知识点：",
    pointsText,
  ].join("\n");

  return {
    kind: "storybook",
    topic: intent.topic,
    summary,
    knowledgePoints,
    knowledgeBases: intent.knowledgeBases,
    stage: intent.stage,
    grade: intent.grade,
    courseId: intent.courseId,
    knowledgePointId: intent.knowledgePointId,
    maxPages: constraints.maxPages,
    maxCharsPerPage: constraints.maxCharsPerPage,
    intent: intentText,
  };
}
