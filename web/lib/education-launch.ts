const STORAGE_KEY = "deeptutor.education.launch.v2";
const LEGACY_STORAGE_KEY = "deeptutor.education.launch.v1";
const MAX_AGE_MS = 300_000;

export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export type EducationAction =
  | "lesson"
  | "quiz"
  | "animation"
  | "storybook"
  | "coding";

// Keep v1 type so legacy callers/tests compile. New code should prefer
// `EducationLaunchIntent` (v2).
export interface EducationLaunchIntentV1 {
  version: 1;
  action: EducationAction;
  courseId: string;
  topic: string;
  masteryPathId: string;
  knowledgeBases: string[];
  summary?: string;
  knowledgePoints?: string[];
  createdAt: number;
}

export interface EducationLaunchIntentV2 {
  version: 2;
  action: EducationAction;
  courseId: string;
  textbookId: string;
  masteryPathId: string;
  knowledgePointId?: string;
  knowledgeBases: string[];
  stage: EducationStageLiteral;
  grade: number;
  interests: string[];
  preferredModalities: LearningModalityLiteral[];
  recommendationReasons: RecommendationReasonLiteral[];
  topic: string;
  summary?: string;
  knowledgePoints?: string[];
  createdAt: number;
}

export type EducationStageLiteral =
  | "primary_lower"
  | "primary_upper"
  | "middle"
  | "high";

export type LearningModalityLiteral =
  | "dialogue"
  | "animation"
  | "storybook"
  | "coding"
  | "quiz";

export interface RecommendationReasonLiteral {
  code: string;
  message_zh: string;
  evidence: Record<string, string | number>;
}

/**
 * Unified launch intent. Always v2 internally; v1 inputs are upgraded.
 *
 * v1 fields remain a subset of v2, so legacy code reading `courseId`, `topic`,
 * `masteryPathId`, `knowledgeBases`, `summary`, `knowledgePoints`,
 * `action`, `createdAt` keeps working.
 */
export type EducationLaunchIntent = EducationLaunchIntentV2;

function browserStorage(): KeyValueStorage | null {
  return typeof window === "undefined" ? null : window.localStorage;
}

const ACTIONS: EducationAction[] = [
  "lesson",
  "quiz",
  "animation",
  "storybook",
  "coding",
];

const STAGES: EducationStageLiteral[] = [
  "primary_lower",
  "primary_upper",
  "middle",
  "high",
];

const MODALITIES: LearningModalityLiteral[] = [
  "dialogue",
  "animation",
  "storybook",
  "coding",
  "quiz",
];

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isReasonArray(value: unknown): value is RecommendationReasonLiteral[] {
  if (!Array.isArray(value)) return false;
  return value.every((item) => {
    if (typeof item !== "object" || item === null) return false;
    const reason = item as Record<string, unknown>;
    return (
      typeof reason.code === "string" &&
      typeof reason.message_zh === "string" &&
      (reason.evidence === undefined ||
        (typeof reason.evidence === "object" && reason.evidence !== null))
    );
  });
}

function isV1(value: unknown): value is EducationLaunchIntentV1 {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return (
    item.version === 1 &&
    typeof item.action === "string" &&
    ACTIONS.includes(item.action as EducationAction) &&
    typeof item.courseId === "string" &&
    typeof item.topic === "string" &&
    typeof item.masteryPathId === "string" &&
    Array.isArray(item.knowledgeBases) &&
    item.knowledgeBases.every((name) => typeof name === "string") &&
    (item.summary === undefined || typeof item.summary === "string") &&
    (item.knowledgePoints === undefined || isStringArray(item.knowledgePoints)) &&
    typeof item.createdAt === "number" &&
    Number.isFinite(item.createdAt)
  );
}

function isV2(value: unknown): value is EducationLaunchIntentV2 {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return (
    item.version === 2 &&
    typeof item.action === "string" &&
    ACTIONS.includes(item.action as EducationAction) &&
    typeof item.courseId === "string" &&
    typeof item.textbookId === "string" &&
    typeof item.masteryPathId === "string" &&
    (item.knowledgePointId === undefined ||
      typeof item.knowledgePointId === "string") &&
    Array.isArray(item.knowledgeBases) &&
    item.knowledgeBases.every((name) => typeof name === "string") &&
    typeof item.stage === "string" &&
    STAGES.includes(item.stage as EducationStageLiteral) &&
    typeof item.grade === "number" &&
    Number.isFinite(item.grade) &&
    isStringArray(item.interests) &&
    Array.isArray(item.preferredModalities) &&
    item.preferredModalities.every(
      (name) =>
        typeof name === "string" &&
        MODALITIES.includes(name as LearningModalityLiteral),
    ) &&
    isReasonArray(item.recommendationReasons) &&
    typeof item.topic === "string" &&
    (item.summary === undefined || typeof item.summary === "string") &&
    (item.knowledgePoints === undefined || isStringArray(item.knowledgePoints)) &&
    typeof item.createdAt === "number" &&
    Number.isFinite(item.createdAt)
  );
}

/** Upgrade a valid v1 intent to v2 with safe defaults for new fields. */
function upgradeV1(input: EducationLaunchIntentV1): EducationLaunchIntentV2 {
  return {
    version: 2,
    action: input.action,
    courseId: input.courseId,
    textbookId: "",
    masteryPathId: input.masteryPathId,
    knowledgePointId: undefined,
    knowledgeBases: input.knowledgeBases,
    stage: "primary_upper",
    grade: 4,
    interests: [],
    preferredModalities: [],
    recommendationReasons: [],
    topic: input.topic,
    summary: input.summary,
    knowledgePoints: input.knowledgePoints,
    createdAt: input.createdAt,
  };
}

/** Normalize arbitrary parsed JSON into a v2 intent, or null if it cannot be made safe. */
function normalize(
  value: unknown,
  now: number,
): EducationLaunchIntentV2 | null {
  if (isV2(value)) {
    return now - value.createdAt > MAX_AGE_MS ? null : value;
  }
  if (isV1(value)) {
    const upgraded = upgradeV1(value);
    return now - upgraded.createdAt > MAX_AGE_MS ? null : upgraded;
  }
  return null;
}

export function saveEducationLaunch(
  intent: EducationLaunchIntent,
  storage: KeyValueStorage | null = browserStorage(),
): void {
  if (!storage) throw new Error("Education launch storage is unavailable");
  storage.setItem(STORAGE_KEY, JSON.stringify(intent));
  // Clear any legacy v1 payload so a stale entry can't override the v2 one.
  storage.removeItem(LEGACY_STORAGE_KEY);
}

export function consumeEducationLaunch(
  storage: KeyValueStorage | null = browserStorage(),
  now = Date.now(),
): EducationLaunchIntent | null {
  if (!storage) return null;
  const raw = storage.getItem(STORAGE_KEY) ?? storage.getItem(LEGACY_STORAGE_KEY);
  if (raw === null) return null;
  storage.removeItem(STORAGE_KEY);
  storage.removeItem(LEGACY_STORAGE_KEY);
  try {
    const value: unknown = JSON.parse(raw);
    return normalize(value, now);
  } catch {
    return null;
  }
}

export function peekEducationLaunch(
  storage: KeyValueStorage | null = browserStorage(),
  now = Date.now(),
): EducationLaunchIntent | null {
  if (!storage) return null;
  const raw = storage.getItem(STORAGE_KEY) ?? storage.getItem(LEGACY_STORAGE_KEY);
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    return normalize(value, now);
  } catch {
    return null;
  }
}
