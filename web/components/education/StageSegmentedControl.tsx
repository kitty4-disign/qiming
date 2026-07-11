"use client";

import type { EducationStage } from "@/lib/education-types";

const STAGES: Array<{ value: EducationStage; label: string; grades: string }> = [
  { value: "primary_lower", label: "小学低年级", grades: "1-3 年级" },
  { value: "primary_upper", label: "小学高年级", grades: "4-6 年级" },
  { value: "middle", label: "初中", grades: "7-9 年级" },
  { value: "high", label: "高中", grades: "10-12 年级" },
];

interface StageSegmentedControlProps {
  value: EducationStage;
  onChange: (stage: EducationStage) => void;
}

export function StageSegmentedControl({
  value,
  onChange,
}: StageSegmentedControlProps) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-2 text-sm font-medium text-[var(--foreground)]">
        学段
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
                {stage.label}
              </span>
              <span className="mt-0.5 block text-[10px] sm:text-center">
                {stage.grades}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
