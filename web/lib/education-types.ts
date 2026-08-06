export type EducationStage =
  | "primary_lower"
  | "primary_upper"
  | "middle"
  | "high";

export type LearningModality =
  | "dialogue"
  | "animation"
  | "storybook"
  | "coding"
  | "quiz";

export interface StudentProfile {
  schema_version: 1;
  display_name: string;
  stage: EducationStage;
  grade: number;
  textbook_id: string;
  interests: string[];
  preferred_modalities: LearningModality[];
  learning_goal: string;
}

export interface EducationCourse {
  id: string;
  title_zh: string;
  title_en: string;
  summary_zh: string;
  summary_en?: string;
  knowledge_points: string[];
  recommended_actions: LearningModality[];
  // Catalog v2 fields (M4 §9.2). All optional for v1 backward compat.
  prerequisite_ids?: string[];
  estimated_minutes?: number;
  difficulty?: number;
  age_policy?: string;
  default_knowledge_point_id?: string;
  resource_ids?: string[];
  coding_task_ids?: string[];
  learning_objectives?: string[];
  common_misconceptions?: string[];
  safety_notes?: string;
  reference_sources?: string[];
}

export interface EducationTextbook {
  id: string;
  title_zh: string;
  title_en: string;
  stage: EducationStage;
  knowledge_base: string;
  default_course_id: string;
  courses: EducationCourse[];
}

export interface EducationCatalog {
  version: number;
  textbooks: EducationTextbook[];
}

export interface EducationLaunchContext {
  profile: StudentProfile;
  textbook: EducationTextbook;
  course: EducationCourse;
  mastery_path_id: string;
  knowledge_bases: string[];
  warnings: string[];
  mastery_seeded?: boolean;
  mastery_counts?: {
    total: number;
    modules: number;
  };
}

// --- M1: unified activity models -------------------------------------------

export type EducationActivity =
  | "lesson"
  | "quiz"
  | "animation"
  | "storybook"
  | "coding"
  | "resource";

export type ActivityEventType = "launched" | "completed" | "abandoned";

export type RecommendationReasonCode =
  | "pending_question"
  | "due_review"
  | "weak_point"
  | "next_new_point"
  | "preference_match"
  | "course_complete";

export interface LearningEvent {
  id: string;
  course_id: string;
  mastery_path_id: string;
  activity: EducationActivity;
  event_type: ActivityEventType;
  knowledge_point_id: string;
  score: number | null;
  duration_seconds: number | null;
  idempotency_key: string;
  created_at: number;
}

export interface RecommendationReason {
  code: RecommendationReasonCode;
  message_zh: string;
  evidence: Record<string, string | number>;
}

export interface EducationRecommendation {
  course_id: string;
  knowledge_point_id: string;
  knowledge_point_name: string;
  activity: EducationActivity;
  title: string;
  reasons: RecommendationReason[];
}

export interface ActivityCompletion {
  course_id: string;
  mastery_path_id: string;
  activity: EducationActivity;
  event_type: ActivityEventType;
  knowledge_point_id: string;
  score: number | null;
  duration_seconds: number | null;
  idempotency_key: string;
}
