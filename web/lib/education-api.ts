import { apiFetch, apiUrl } from "@/lib/api";
import type {
  ActivityCompletion,
  EducationCatalog,
  EducationLaunchContext,
  EducationRecommendation,
  LearningEvent,
  LearningEpisode,
  StudentProfile,
  TeachingDecision,
} from "@/lib/education-types";

export class EducationApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, status: number) {
    super(code);
    this.name = "EducationApiError";
    this.code = code;
    this.status = status;
  }
}

function errorCode(data: unknown, status: number): string {
  if (typeof data !== "object" || data === null || !("detail" in data)) {
    return `http_${status}`;
  }
  const detail = (data as { detail: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) return "validation_error";
  return `http_${status}`;
}

const EDUCATION_ERROR_KEYS: Record<string, string> = {
  education_profile_required: "Education profile required",
  course_not_found: "Course not found",
  knowledge_point_not_in_course: "Knowledge point not in course",
  mastery_path_mismatch: "Learning path mismatch",
  episode_mismatch: "Learning episode mismatch",
  knowledge_point_not_in_episode: "Knowledge point not in learning episode",
  episode_not_found: "Learning episode not found",
  episode_not_active: "Learning episode is no longer active",
  task_not_found: "Coding task not found",
  task_course_mismatch: "Coding task course mismatch",
  source_too_long: "Code source too long",
  forbidden_import: "Forbidden import",
  unsupported_language: "Unsupported code language",
  language_not_allowed: "Code language not allowed",
  sandbox_unavailable: "Sandbox unavailable",
  validation_error: "Education validation failed",
};

/** Convert education API codes into UI translation keys without exposing raw protocol text. */
export function educationErrorKey(reason: unknown): string {
  const code = reason instanceof EducationApiError
    ? reason.code.split(":", 1)[0]
    : "";
  return EDUCATION_ERROR_KEYS[code] ??
    (reason instanceof TypeError
      ? "Unable to connect to education service"
      : "Education request failed");
}

async function expectJson<T>(response: Response): Promise<T> {
  const data = (await response.json().catch(() => ({}))) as unknown;
  if (!response.ok) {
    throw new EducationApiError(errorCode(data, response.status), response.status);
  }
  return data as T;
}

export async function getEducationProfile(): Promise<StudentProfile | null> {
  const response = await apiFetch(apiUrl("/api/v1/education/profile"));
  const data = await expectJson<{ profile: StudentProfile | null }>(response);
  return data.profile;
}

export async function saveEducationProfile(
  profile: StudentProfile,
): Promise<StudentProfile> {
  const response = await apiFetch(apiUrl("/api/v1/education/profile"), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  const data = await expectJson<{ profile: StudentProfile }>(response);
  return data.profile;
}

export async function getEducationCatalog(): Promise<EducationCatalog> {
  const response = await apiFetch(apiUrl("/api/v1/education/catalog"));
  return expectJson<EducationCatalog>(response);
}

export async function getLaunchContext(
  courseId: string,
): Promise<EducationLaunchContext> {
  const response = await apiFetch(
    apiUrl(`/api/v1/education/launch-context/${encodeURIComponent(courseId)}`),
  );
  return expectJson<EducationLaunchContext>(response);
}

export interface EducationDashboard {
  profile: StudentProfile;
  course: EducationLaunchContext["course"];
  mastery_path_id: string;
  mastery_summary: {
    total: number;
    mastered: number;
    learning: number;
    new: number;
  };
  recommendation: EducationRecommendation;
  activity_summary: {
    total_events: number;
    completed_count: number;
    quiz_completed: number;
    quiz_correct: number;
    last_event_at: number;
  };
  recent_events: LearningEvent[];
  active_episode: LearningEpisode | null;
  learning_evidence: LearningEpisode | null;
  teaching_decision: TeachingDecision;
}

export async function getEducationDashboard(
  courseId: string,
): Promise<EducationDashboard> {
  const response = await apiFetch(
    apiUrl(`/api/v1/education/dashboard/${encodeURIComponent(courseId)}`),
  );
  return expectJson<EducationDashboard>(response);
}

export async function recordEducationEvent(
  completion: ActivityCompletion,
): Promise<LearningEvent> {
  const response = await apiFetch(apiUrl("/api/v1/education/events"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(completion),
  });
  const data = await expectJson<{ event: LearningEvent }>(response);
  return data.event;
}

// ── Coding lab (M3) ────────────────────────────────────────────────────────

export interface CodingTestCase {
  name: string;
  stdin: string;
  expected_stdout: string;
  is_hidden?: boolean;
}

export interface CodingTask {
  id: string;
  course_id: string;
  stage: string;
  title: string;
  instructions: string;
  starter_code: string;
  allowed_languages: string[];
  visible_tests: CodingTestCase[];
  hint_count: number;
}

export interface TestCaseResult {
  name: string;
  passed: boolean;
  stdout: string;
  expected: string;
}

export interface CodeRunResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  timed_out: boolean;
  language: string;
  visible_results: TestCaseResult[];
  hidden_passed: number;
  hidden_total: number;
  all_visible_passed: boolean;
  all_hidden_passed: boolean;
}

export async function getCodingTasks(
  courseId?: string,
): Promise<CodingTask[]> {
  const query = courseId ? `?course_id=${encodeURIComponent(courseId)}` : "";
  const response = await apiFetch(
    apiUrl(`/api/v1/education/coding-tasks${query}`),
  );
  const data = await expectJson<{ tasks: CodingTask[] }>(response);
  return data.tasks;
}

export async function getCodingTask(taskId: string): Promise<CodingTask> {
  const response = await apiFetch(
    apiUrl(`/api/v1/education/coding-tasks/${encodeURIComponent(taskId)}`),
  );
  return expectJson<CodingTask>(response);
}

export async function runStudentCode(
  request: {
    course_id: string;
    task_id: string;
    language: string;
    source_code: string;
    stdin?: string;
  },
): Promise<CodeRunResult> {
  const response = await apiFetch(apiUrl("/api/v1/education/code/run"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const data = await expectJson<{ result: CodeRunResult }>(response);
  return data.result;
}

export async function getCodingHint(
  taskId: string,
  attempt: number,
): Promise<string> {
  const response = await apiFetch(
    apiUrl(
      `/api/v1/education/coding-tasks/${encodeURIComponent(taskId)}/hint?attempt=${attempt}`,
    ),
  );
  const data = await expectJson<{ hint: string }>(response);
  return data.hint;
}

// ── Gamification (M3 §8.2) ──────────────────────────────────────────────────

export interface GamificationSummary {
  xp_total: number;
  level: number;
  xp_into_level: number;
  xp_for_next_level: number;
  current_streak_days: number;
  badges: string[];
  next_badge_progress: Record<string, string | number>;
}

export async function getGamification(
  courseId: string,
): Promise<GamificationSummary> {
  const response = await apiFetch(
    apiUrl(`/api/v1/education/gamification/${encodeURIComponent(courseId)}`),
  );
  const data = await expectJson<{ gamification: GamificationSummary }>(response);
  return data.gamification;
}
