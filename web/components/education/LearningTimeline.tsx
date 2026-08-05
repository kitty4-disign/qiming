"use client";

import {
  BookOpen,
  ClipboardCheck,
  Code2,
  MessageCircle,
  PlayCircle,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import type { LearningEvent } from "@/lib/education-types";

const ACTIVITY_ICONS: Record<string, LucideIcon> = {
  lesson: MessageCircle,
  quiz: ClipboardCheck,
  animation: PlayCircle,
  storybook: BookOpen,
  coding: Code2,
  resource: BookOpen,
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  launched: "Started",
  completed: "Completed",
  abandoned: "Left",
};

function formatRelativeTime(timestamp: number, locale: string): string {
  const now = Date.now();
  const diff = now / 1000 - timestamp;
  if (diff < 60) return locale.startsWith("zh") ? "刚刚" : "just now";
  if (diff < 3600) {
    const minutes = Math.floor(diff / 60);
    return locale.startsWith("zh") ? `${minutes} 分钟前` : `${minutes}m ago`;
  }
  if (diff < 86400) {
    const hours = Math.floor(diff / 3600);
    return locale.startsWith("zh") ? `${hours} 小时前` : `${hours}h ago`;
  }
  const days = Math.floor(diff / 86400);
  return locale.startsWith("zh") ? `${days} 天前` : `${days}d ago`;
}

interface LearningTimelineProps {
  events: LearningEvent[];
}

export function LearningTimeline({ events }: LearningTimelineProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  if (events.length === 0) {
    return (
      <section
        className="border-t border-[var(--border)] py-6"
        aria-labelledby="timeline-title"
      >
        <h2
          id="timeline-title"
          className="text-sm font-semibold text-[var(--foreground)]"
        >
          {t("Recent Activity")}
        </h2>
        <p className="mt-3 text-xs text-[var(--muted-foreground)]">
          {t("No learning activity yet")}
        </p>
      </section>
    );
  }

  return (
    <section
      className="border-t border-[var(--border)] py-6"
      aria-labelledby="timeline-title"
    >
      <h2
        id="timeline-title"
        className="text-sm font-semibold text-[var(--foreground)]"
      >
        {t("Recent Activity")}
      </h2>
      <ol className="mt-3 space-y-2">
        {events.slice(0, 8).map((event) => {
          const Icon = ACTIVITY_ICONS[event.activity] ?? MessageCircle;
          const typeLabel = EVENT_TYPE_LABELS[event.event_type] ?? event.event_type;
          return (
            <li
              key={event.id}
              className="flex items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--card)] px-3 py-2"
            >
              <Icon
                aria-hidden="true"
                className="size-3.5 shrink-0 text-[var(--primary)]"
              />
              <span className="min-w-0 flex-1 text-xs text-[var(--foreground)]">
                {t(typeLabel)} {t(event.activity)}
                {event.score !== null && (
                  <span className="ml-1 text-[var(--muted-foreground)]">
                    ({Math.round(event.score * 100)}%)
                  </span>
                )}
              </span>
              <time className="shrink-0 text-[10px] text-[var(--muted-foreground)]">
                {formatRelativeTime(event.created_at, locale)}
              </time>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
