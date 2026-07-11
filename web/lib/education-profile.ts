import type {
  EducationCatalog,
  EducationStage,
  EducationTextbook,
} from "./education-types";

const STAGE_GRADES: Record<EducationStage, readonly number[]> = {
  primary_lower: [1, 2, 3],
  primary_upper: [4, 5, 6],
  middle: [7, 8, 9],
  high: [10, 11, 12],
};

export function gradesForStage(stage: EducationStage): number[] {
  return [...STAGE_GRADES[stage]];
}

export function textbooksForStage(
  catalog: EducationCatalog,
  stage: EducationStage,
): EducationTextbook[] {
  return catalog.textbooks.filter((textbook) => textbook.stage === stage);
}
