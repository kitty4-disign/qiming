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
