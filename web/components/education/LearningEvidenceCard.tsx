"use client";

import { ArrowRight, BookOpen, CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { LearningEpisode, TeachingDecision } from "@/lib/education-types";

interface LearningEvidenceCardProps {
  evidence: LearningEpisode | null;
  decision: TeachingDecision | null;
  loading: boolean;
  textbookTitle?: string;
  courseTitle?: string;
}

const ACTIVITY_LABEL_KEYS: Record<string, string> = {
  lesson: "lesson",
  quiz: "Quiz",
  animation: "Animation",
  storybook: "storybook",
  coding: "coding",
  resource: "resource",
};

const HINT_LABEL_KEYS: Record<string, string> = {
  high: "High",
  medium_high: "Medium-high",
  medium: "Medium",
  low: "Low",
};

export function LearningEvidenceCard({
  evidence,
  decision,
  loading,
  textbookTitle,
  courseTitle,
}: LearningEvidenceCardProps) {
  const { t } = useTranslation();
  const activityLabel = (activity: string) =>
    t(ACTIVITY_LABEL_KEYS[activity] ?? "Activity");

  return (
    <section className="border-t border-[var(--border)] py-6" aria-labelledby="learning-evidence-title">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--primary)]">
            {t("Learning Evidence")}
          </p>
          <h2 id="learning-evidence-title" className="mt-1 text-lg font-semibold text-[var(--foreground)]">
            {evidence?.knowledge_point_name || t("This learning session")}
          </h2>
        </div>
        {evidence?.raw_gain != null && (
          <span className="shrink-0 rounded-full bg-emerald-500/10 px-3 py-1 text-sm font-semibold tabular-nums text-emerald-700 dark:text-emerald-300">
            +{Math.round(evidence.raw_gain)}
          </span>
        )}
      </div>

      {loading ? (
        <div className="mt-4 h-28 animate-pulse rounded-xl bg-[var(--muted)]" />
      ) : evidence ? (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--muted)]/35 p-4">
            <div>
              <p className="text-xs text-[var(--muted-foreground)]">{t("Before learning")}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--foreground)]">
                {Math.round(evidence.pre_score)}%
              </p>
            </div>
            <ArrowRight aria-hidden="true" className="size-5 text-[var(--primary)]" />
            <div className="text-right">
              <p className="text-xs text-[var(--muted-foreground)]">{t("After learning")}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--foreground)]">
                {Math.round(evidence.post_score ?? evidence.pre_score)}%
              </p>
            </div>
          </div>

          {evidence.resolved_misconceptions.map((item) => (
            <p key={item} className="flex gap-2 text-sm text-[var(--foreground)]">
              <CheckCircle2 aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-emerald-600" />
              <span><span className="font-medium">{t("Corrected misconception")}:</span> {item}</span>
            </p>
          ))}

          <div className="grid gap-3 text-sm sm:grid-cols-2">
            <div className="rounded-lg border border-[var(--border)] p-3">
              <p className="text-xs text-[var(--muted-foreground)]">{t("Learning activities")}</p>
              <p className="mt-1 break-words text-[var(--foreground)]">
                {evidence.activities_used.map(activityLabel).join(" → ") || "-"}
              </p>
            </div>
            <div className="rounded-lg border border-[var(--border)] p-3">
              <p className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
                <BookOpen aria-hidden="true" className="size-3.5" /> {t("Textbook sources")}
              </p>
              {evidence.source_ids.length > 0 && (textbookTitle || courseTitle) ? (
                <div className="mt-1 text-[var(--foreground)]">
                  {textbookTitle && <p>《{textbookTitle}》</p>}
                  {courseTitle && <p>{courseTitle}</p>}
                </div>
              ) : (
                <p className="mt-1 text-[var(--foreground)]">{t("No textbook source recorded")}</p>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-dashed border-[var(--border)] p-4 text-sm text-[var(--muted-foreground)]">
          <p>{t("Complete a pre-test and post-test to generate learning evidence")}</p>
          {decision && (
            <p className="mt-2 text-xs">
              {t("Teaching Policy")}: {activityLabel(decision.activity)} · {t("Difficulty")} {decision.difficulty} · {t("Hint Level")} {t(HINT_LABEL_KEYS[decision.hint_level] ?? "Medium")}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
