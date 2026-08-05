import type { EducationLaunchIntent } from "./education-launch";
import type {
  EducationCourse,
  EducationLaunchContext,
  EducationRecommendation,
  StudentProfile,
} from "./education-types";

export interface BuildLaunchIntentInput {
  action: EducationLaunchIntent["action"];
  course: EducationCourse;
  profile: StudentProfile;
  launchContext: EducationLaunchContext;
  knowledgePointId?: string;
  recommendation?: EducationRecommendation | null;
  createdAt?: number;
}

/**
 * Build a v2 EducationLaunchIntent from the dashboard state.
 *
 * Carries stage/grade/interests/preferredModalities/recommendationReasons so
 * downstream multimodal capabilities (k12_tutor / visualize / book) all see
 * the same learning context (M2 §7.1).
 */
export function buildEducationLaunchIntent(
  input: BuildLaunchIntentInput,
): EducationLaunchIntent {
  const { course, profile, launchContext, recommendation } = input;
  const reasons = recommendation?.reasons ?? [];
  // Prefer the explicit override; otherwise fall back to the recommendation's
  // knowledge point so the launched modality lands on the same KP the
  // dashboard recommended.
  const knowledgePointId =
    input.knowledgePointId ?? (recommendation?.knowledge_point_id || undefined);
  return {
    version: 2,
    action: input.action,
    courseId: course.id,
    textbookId: profile.textbook_id,
    masteryPathId: launchContext.mastery_path_id,
    knowledgePointId,
    knowledgeBases: launchContext.knowledge_bases,
    stage: profile.stage,
    grade: profile.grade,
    interests: profile.interests,
    preferredModalities: profile.preferred_modalities,
    recommendationReasons: reasons.map((reason) => ({
      code: reason.code,
      message_zh: reason.message_zh,
      evidence: reason.evidence,
    })),
    topic: course.title_zh,
    summary: course.summary_zh,
    knowledgePoints: course.knowledge_points,
    createdAt: input.createdAt ?? Date.now(),
  };
}
