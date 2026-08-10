"use client";

import {
  BookOpen,
  ClipboardCheck,
  Code2,
  MessageCircle,
  PlayCircle,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { educationErrorKey, getLaunchContext } from "@/lib/education-api";
import { buildEducationLaunchIntent } from "@/lib/education-launch-builder";
import {
  saveEducationLaunch,
  type EducationAction,
} from "@/lib/education-launch";
import type {
  EducationCourse,
  EducationLaunchContext,
  LearningModality,
  StudentProfile,
} from "@/lib/education-types";

interface LearningActionGridProps {
  course: EducationCourse;
  profile: StudentProfile;
  launchContext: EducationLaunchContext | null;
}

const ACTIONS: Array<{
  action: EducationAction;
  modality: LearningModality;
  label: string;
  description: string;
  route: "/home" | "/book";
  icon: LucideIcon;
}> = [
  {
    action: "lesson",
    modality: "dialogue",
    label: "Start Lesson",
    description: "Start Lesson description",
    route: "/home",
    icon: MessageCircle,
  },
  {
    action: "quiz",
    modality: "quiz",
    label: "Fun Quiz",
    description: "Fun Quiz description",
    route: "/home",
    icon: ClipboardCheck,
  },
  {
    action: "animation",
    modality: "animation",
    label: "Animation Explanation",
    description: "Animation Explanation description",
    route: "/home",
    icon: PlayCircle,
  },
  {
    action: "storybook",
    modality: "storybook",
    label: "Interactive Storybook",
    description: "Interactive Storybook description",
    route: "/book",
    icon: BookOpen,
  },
  {
    action: "coding",
    modality: "coding",
    label: "Coding Practice",
    description: "Coding Practice description",
    route: "/home",
    icon: Code2,
  },
];

export function LearningActionGrid({ course, profile, launchContext }: LearningActionGridProps) {
  const router = useRouter();
  const { t } = useTranslation();
  const [pending, setPending] = useState<EducationAction | null>(null);
  const [error, setError] = useState("");

  const visibleActions = useMemo(() => {
    const recommended = new Set(course.recommended_actions);
    const filtered = ACTIONS.filter((action) => recommended.has(action.modality));
    return filtered.length > 0 ? filtered : ACTIONS.filter((action) => action.action === "lesson");
  }, [course.recommended_actions]);

  const launch = useCallback(
    async (action: (typeof ACTIONS)[number]) => {
      setPending(action.action);
      setError("");
      try {
        const context = launchContext ?? (await getLaunchContext(course.id));
        saveEducationLaunch(
          buildEducationLaunchIntent({
            action: action.action,
            course,
            profile,
            launchContext: context,
          }),
        );
        router.push(action.route);
      } catch (reason) {
        setError(t(educationErrorKey(reason)));
        setPending(null);
      }
    },
    [course, profile, launchContext, router, t],
  );

  return (
    <section className="border-t border-[var(--border)] py-6" aria-labelledby="actions-title">
      <h2 id="actions-title" className="text-sm font-semibold text-[var(--foreground)]">
        {t("Choose a learning activity")}
      </h2>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {visibleActions.map((action) => (
          <article
            key={action.action}
            className="flex min-w-0 items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--card)] p-3"
          >
            <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-[var(--muted)] text-[var(--primary)]">
              <action.icon aria-hidden="true" className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold text-[var(--foreground)]">
                {t(action.label)}
              </h3>
              <p className="mt-0.5 text-xs leading-5 text-[var(--muted-foreground)]">
                {t(action.description)}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void launch(action)}
              disabled={pending !== null}
              className="shrink-0 rounded-md bg-[var(--primary)] px-3 py-2 text-xs font-semibold text-[var(--primary-foreground)] transition-transform hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pending === action.action ? t("Opening") : t("Open")}
            </button>
          </article>
        ))}
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-300">
          {error}
        </p>
      )}
    </section>
  );
}
