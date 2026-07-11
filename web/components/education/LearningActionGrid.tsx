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
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { getLaunchContext } from "@/lib/education-api";
import {
  saveEducationLaunch,
  type EducationAction,
} from "@/lib/education-launch";
import type { EducationCourse, EducationLaunchContext } from "@/lib/education-types";

interface LearningActionGridProps {
  course: EducationCourse;
  launchContext: EducationLaunchContext | null;
}

const ACTIONS: Array<{
  action: EducationAction;
  label: string;
  description: string;
  route: "/home" | "/book";
  icon: LucideIcon;
}> = [
  {
    action: "lesson",
    label: "Start Lesson",
    description: "Start Lesson description",
    route: "/home",
    icon: MessageCircle,
  },
  {
    action: "quiz",
    label: "Fun Quiz",
    description: "Fun Quiz description",
    route: "/home",
    icon: ClipboardCheck,
  },
  {
    action: "animation",
    label: "Animation Explanation",
    description: "Animation Explanation description",
    route: "/home",
    icon: PlayCircle,
  },
  {
    action: "storybook",
    label: "Interactive Storybook",
    description: "Interactive Storybook description",
    route: "/book",
    icon: BookOpen,
  },
  {
    action: "coding",
    label: "Coding Practice",
    description: "Coding Practice description",
    route: "/home",
    icon: Code2,
  },
];

export function LearningActionGrid({ course, launchContext }: LearningActionGridProps) {
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const [pending, setPending] = useState<EducationAction | null>(null);
  const [error, setError] = useState("");
  const topic = i18n.language.startsWith("zh") ? course.title_zh : course.title_en;

  const launch = useCallback(
    async (action: (typeof ACTIONS)[number]) => {
      setPending(action.action);
      setError("");
      try {
        const context = launchContext ?? (await getLaunchContext(course.id));
        saveEducationLaunch({
          version: 1,
          action: action.action,
          courseId: course.id,
          topic,
          masteryPathId: context.mastery_path_id,
          knowledgeBases: context.knowledge_bases,
          createdAt: Date.now(),
        });
        if (action.action === "storybook" && navigator.clipboard) {
          const prompt = `请为“${topic}”生成适合当前学段的互动绘本，包含知识讲解、一个互动问题和安全提示。`;
          await navigator.clipboard.writeText(prompt).catch(() => undefined);
        }
        router.push(action.route);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : t("Launch failed"));
        setPending(null);
      }
    },
    [course.id, launchContext, router, t, topic],
  );

  return (
    <section className="border-t border-[var(--border)] py-6" aria-labelledby="actions-title">
      <h2 id="actions-title" className="text-sm font-semibold text-[var(--foreground)]">
        {t("Choose a learning activity")}
      </h2>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {ACTIONS.map((action) => (
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
