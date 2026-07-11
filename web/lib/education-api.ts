import { apiFetch, apiUrl } from "@/lib/api";
import type {
  EducationCatalog,
  EducationLaunchContext,
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
