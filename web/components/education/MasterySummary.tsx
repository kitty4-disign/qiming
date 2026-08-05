"use client";

import { ArrowRight, CircleCheck, Clock3, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchMasteryMap, type MasteryMap } from "@/lib/learning-api";

interface MasteryCounts {
  mastered: number;
  learning: number;
  new: number;
  total: number;
}

interface MasterySummaryProps {
  pathId: string;
  masterySummary?: { total: number; mastered: number; learning: number; new: number } | null;
  nextKnowledgePoint?: string;
}

export function MasterySummary({
  pathId,
  masterySummary,
  nextKnowledgePoint,
}: MasterySummaryProps) {
  const { t } = useTranslation();
  const [result, setResult] = useState<{
    pathId: string;
    map: MasteryMap | null;
  } | null>(null);

  // Only fetch the mastery map if the dashboard didn't provide a summary.
  useEffect(() => {
    if (masterySummary) return;
    let active = true;
    fetchMasteryMap(pathId)
      .then((result) => {
        if (active) setResult({ pathId, map: result.map });
      })
      .catch(() => {
        if (active) setResult({ pathId, map: null });
      });
    return () => {
      active = false;
    };
  }, [pathId, masterySummary]);

  const loading = !masterySummary && result?.pathId !== pathId;
  const map = result?.pathId === pathId ? result.map : null;
  const counts: MasteryCounts = masterySummary
    ? {
        mastered: masterySummary.mastered,
        learning: masterySummary.learning,
        new: masterySummary.new,
        total: masterySummary.total,
      }
    : map?.counts ?? { mastered: 0, learning: 0, new: 0, total: 0 };
  const metrics = [
    { key: "Mastered", value: counts.mastered, icon: CircleCheck },
    { key: "Learning", value: counts.learning, icon: Clock3 },
    { key: "New", value: counts.new, icon: Sparkles },
  ];

  return (
    <section className="border-t border-[var(--border)] py-6" aria-labelledby="mastery-title">
      <h2 id="mastery-title" className="text-sm font-semibold text-[var(--foreground)]">
        {t("Learning Progress")}
      </h2>
      <div className="mt-3 grid grid-cols-3 divide-x divide-[var(--border)] border-y border-[var(--border)] py-4">
        {metrics.map(({ key, value, icon: Icon }) => (
          <div key={key} className="min-w-0 px-2 text-center sm:px-5">
            <Icon aria-hidden="true" className="mx-auto size-4 text-[var(--primary)]" />
            {loading ? (
              <div className="mx-auto mt-2 h-6 w-8 animate-pulse rounded bg-[var(--muted)]" />
            ) : (
              <p className="mt-1 text-xl font-semibold tabular-nums text-[var(--foreground)]">
                {value}
              </p>
            )}
            <p className="mt-0.5 truncate text-xs text-[var(--muted-foreground)]">
              {t(key)}
            </p>
          </div>
        ))}
      </div>
      {nextKnowledgePoint && (
        <div className="mt-3 flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
          <ArrowRight aria-hidden="true" className="size-3 shrink-0 text-[var(--primary)]" />
          <span>
            {t("Next")}: <span className="font-medium text-[var(--foreground)]">{nextKnowledgePoint}</span>
          </span>
        </div>
      )}
    </section>
  );
}
