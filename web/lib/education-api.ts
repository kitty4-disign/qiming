import { apiFetch, apiUrl } from "@/lib/api";
import type {
  ActivityCompletion,
  EducationCatalog,
  EducationLaunchContext,
  EducationRecommendation,
  LearningEvent,
  StudentProfile,
} from "@/lib/education-types";

async function expectJson<T>(response: Response): Promise<T> {
  const data = (await response.json().catch(() => ({}))) as unknown;
  if (!response.ok) {
    const detail =
      typeof data === "object" && data !== null && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : `Request failed: ${response.status}`;
    throw new Error(detail);
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
