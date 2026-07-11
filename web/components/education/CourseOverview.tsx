"use client";

import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { EducationCourse } from "@/lib/education-types";

interface CourseOverviewProps {
  course: EducationCourse;
}

export function CourseOverview({ course }: CourseOverviewProps) {
  const { t, i18n } = useTranslation();
  const isChinese = i18n.language.startsWith("zh");

  return (
    <section className="border-t border-[var(--border)] py-6" aria-labelledby="course-title">
      <p className="mb-2 text-xs font-semibold uppercase text-[var(--muted-foreground)]">
        {t("Today's Course")}
      </p>
      <div className="grid gap-5 md:grid-cols-[minmax(0,1.35fr)_minmax(240px,0.65fr)]">
        <div className="min-w-0">
          <h2 id="course-title" className="text-xl font-semibold text-[var(--foreground)]">
            {isChinese ? course.title_zh : course.title_en}
          </h2>
          <p className="mt-2 max-w-[65ch] text-sm leading-6 text-[var(--muted-foreground)]">
            {course.summary_zh}
          </p>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-[var(--foreground)]">
            {t("Knowledge Map")}
          </h3>
          <ul className="mt-2 space-y-2">
            {course.knowledge_points.map((point) => (
              <li key={point} className="flex items-start gap-2 text-sm text-[var(--foreground)]">
                <Check aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-[var(--primary)]" />
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
