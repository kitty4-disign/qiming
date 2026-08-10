"use client";

import {
  BookOpen,
  ClipboardCheck,
  Code2,
  Lightbulb,
  MessageCircle,
  PlayCircle,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { educationErrorKey, getLaunchContext } from "@/lib/education-api";
import { buildEducationLaunchIntent } from "@/lib/education-launch-builder";
import { saveEducationLaunch } from "@/lib/education-launch";
import type {
  EducationActivity,
  EducationCourse,
  EducationLaunchContext,
  EducationRecommendation,
  StudentProfile,
} from "@/lib/education-types";

const ACTIVITY_META: Record<
  EducationActivity,
  { icon: LucideIcon; action: "lesson" | "quiz" | "animation" | "storybook" | "coding" | null; route: "/home" | "/book" }
> = {
  lesson: { icon: MessageCircle, action: "lesson", route: "/home" },
  quiz: { icon: ClipboardCheck, action: "quiz", route: "/home" },
  animation: { icon: PlayCircle, action: "animation", route: "/home" },
  storybook: { icon: BookOpen, action: "storybook", route: "/book" },
  coding: { icon: Code2, action: "coding", route: "/home" },
  resource: { icon: BookOpen, action: null, route: "/home" },
};

interface RecommendedNextStepProps {
  recommendation: EducationRecommendation;
  course: EducationCourse;
  profile: StudentProfile;
  launchContext: EducationLaunchContext | null;
  onLaunched?: () => void;
}

export function RecommendedNextStep({
  recommendation,
  course,
  profile,
  launchContext,
  onLaunched,
}: RecommendedNextStepProps) {
  const { t } = useTranslation();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  const meta = ACTIVITY_META[recommendation.activity] ?? ACTIVITY_META.lesson;
  const Icon = meta.icon;
  const kpName = recommendation.knowledge_point_name || recommendation.knowledge_point_id;

  const launch = async () => {
    if (!meta.action) return;
    setPending(true);
    setError("");
    try {
      const context = launchContext ?? (await getLaunchContext(course.id));
      saveEducationLaunch(
        buildEducationLaunchIntent({
          action: meta.action,
          course,
          profile,
          launchContext: context,
          knowledgePointId: recommendation.knowledge_point_id || undefined,
          recommendation,
        }),
      );
      onLaunched?.();
      router.push(meta.route);
    } catch (reason) {
      setError(t(educationErrorKey(reason)));
      setPending(false);
    }
  };

  return (
    <section
      className="border-t border-[var(--border)] py-6"
      aria-labelledby="recommendation-title"
    >
      <h2
        id="recommendation-title"
        className="flex items-center gap-1.5 text-sm font-semibold text-[var(--foreground)]"
      >
        <Lightbulb aria-hidden="true" className="size-4 text-[var(--primary)]" />
        {t("Recommended Next Step")}
      </h2>
      <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--card)] p-4">
        <div className="flex items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-[var(--muted)] text-[var(--primary)]">
            <Icon aria-hidden="true" className="size-4" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-[var(--foreground)]">
              {recommendation.title}
            </h3>
            {kpName && (
              <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">
                {t("Knowledge Point")}: {kpName}
              </p>
            )}
            {recommendation.reasons.length > 0 && (
              <ul className="mt-2 space-y-1">
                {recommendation.reasons.map((reason, index) => (
                  <li
                    key={`${reason.code}-${index}`}
                    className="text-xs leading-5 text-[var(--muted-foreground)]"
                  >
                    <span className="font-medium text-[var(--foreground)]">
                      {reason.message_zh}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {meta.action && (
            <button
              type="button"
              onClick={() => void launch()}
              disabled={pending}
              className="shrink-0 rounded-md bg-[var(--primary)] px-3 py-2 text-xs font-semibold text-[var(--primary-foreground)] transition-transform hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pending ? t("Opening") : t("Start")}
            </button>
          )}
        </div>
        {error && (
          <p role="alert" className="mt-2 text-xs text-red-600 dark:text-red-300">
            {error}
            <button
              type="button"
              onClick={() => void launch()}
              className="ml-2 underline"
            >
              {t("Retry")}
            </button>
          </p>
        )}
      </div>
    </section>
  );
}
