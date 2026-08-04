const STORAGE_KEY = "deeptutor.education.launch.v1";
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

export interface EducationLaunchIntent {
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

function browserStorage(): KeyValueStorage | null {
  return typeof window === "undefined" ? null : window.localStorage;
}

function isLaunchIntent(value: unknown): value is EducationLaunchIntent {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  const actions: EducationAction[] = [
    "lesson",
    "quiz",
    "animation",
    "storybook",
    "coding",
  ];
  return (
    item.version === 1 &&
    typeof item.action === "string" &&
    actions.includes(item.action as EducationAction) &&
    typeof item.courseId === "string" &&
    typeof item.topic === "string" &&
    typeof item.masteryPathId === "string" &&
    Array.isArray(item.knowledgeBases) &&
    item.knowledgeBases.every((name) => typeof name === "string") &&
    (item.summary === undefined || typeof item.summary === "string") &&
    (item.knowledgePoints === undefined ||
      (Array.isArray(item.knowledgePoints) &&
        item.knowledgePoints.every((point) => typeof point === "string"))) &&
    typeof item.createdAt === "number" &&
    Number.isFinite(item.createdAt)
  );
}

export function saveEducationLaunch(
  intent: EducationLaunchIntent,
  storage: KeyValueStorage | null = browserStorage(),
): void {
  if (!storage) throw new Error("Education launch storage is unavailable");
  storage.setItem(STORAGE_KEY, JSON.stringify(intent));
}

export function consumeEducationLaunch(
  storage: KeyValueStorage | null = browserStorage(),
  now = Date.now(),
): EducationLaunchIntent | null {
  if (!storage) return null;
  const raw = storage.getItem(STORAGE_KEY);
  if (raw === null) return null;
  storage.removeItem(STORAGE_KEY);
  try {
    const value: unknown = JSON.parse(raw);
    if (!isLaunchIntent(value) || now - value.createdAt > MAX_AGE_MS) return null;
    return value;
  } catch {
    return null;
  }
}

export function peekEducationLaunch(
  storage: KeyValueStorage | null = browserStorage(),
  now = Date.now(),
): EducationLaunchIntent | null {
  if (!storage) return null;
  const raw = storage.getItem(STORAGE_KEY);
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isLaunchIntent(value) || now - value.createdAt > MAX_AGE_MS) return null;
    return value;
  } catch {
    return null;
  }
}
