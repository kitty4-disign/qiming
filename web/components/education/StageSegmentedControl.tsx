"use client";

import type { EducationStage } from "@/lib/education-types";
import { useTranslation } from "react-i18next";

const STAGES: Array<{ value: EducationStage; label: string; grades: string }> = [
  { value: "primary_lower", label: "Primary Lower", grades: "1-3" },
  { value: "primary_upper", label: "Primary Upper", grades: "4-6" },
  { value: "middle", label: "Middle School", grades: "7-9" },
  { value: "high", label: "High School", grades: "10-12" },
];

interface StageSegmentedControlProps {
  value: EducationStage;
  onChange: (stage: EducationStage) => void;
}

export function StageSegmentedControl({
  value,
  onChange,
}: StageSegmentedControlProps) {
  const { t } = useTranslation();
  return (
    <fieldset className="min-w-0">
      <legend className="mb-2 text-sm font-medium text-[var(--foreground)]">
        {t("Education Stage")}
      </legend>
      <div className="grid grid-cols-2 gap-1 rounded-lg border border-[var(--border)] bg-[var(--muted)] p-1 sm:grid-cols-4">
        {STAGES.map((stage) => {
          const selected = stage.value === value;
          return (
            <button
              key={stage.value}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(stage.value)}
              className={`min-w-0 rounded-md px-2 py-2 text-left transition-colors active:scale-[0.98] ${
                selected
                  ? "bg-[var(--card)] text-[var(--foreground)] shadow-sm"
                  : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              }`}
            >
              <span className="block text-xs font-semibold sm:text-center">
                {t(stage.label)}
              </span>
              <span className="mt-0.5 block text-[10px] sm:text-center">
                {t("Grades range", { range: stage.grades })}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
