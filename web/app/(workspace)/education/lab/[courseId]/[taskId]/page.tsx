"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { CodingLab } from "@/components/education/CodingLab";
import { educationErrorKey, getLaunchContext } from "@/lib/education-api";

export default function CodingLabPage({
  params,
}: {
  params: { courseId: string; taskId: string };
}) {
  const { t } = useTranslation();
  const [masteryPathId, setMasteryPathId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getLaunchContext(params.courseId)
      .then((ctx) => {
        if (cancelled) return;
        setMasteryPathId(ctx.mastery_path_id);
      })
      .catch((reason) => {
        if (!cancelled) setError(t(educationErrorKey(reason)));
      });
    return () => {
      cancelled = true;
    };
  }, [params.courseId]);

  if (error) {
    return (
      <main className="mx-auto w-full max-w-4xl px-4 py-6">
        <p role="alert" className="text-sm text-red-600 dark:text-red-300">
          {error}
        </p>
      </main>
    );
  }

  if (!masteryPathId) {
    return (
      <main className="mx-auto w-full max-w-4xl px-4 py-6">
        <p className="text-sm text-[var(--muted-foreground)]">{t("Loading")}</p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-6">
      <CodingLab
        taskId={params.taskId}
        courseId={params.courseId}
        masteryPathId={masteryPathId}
      />
    </main>
  );
}
