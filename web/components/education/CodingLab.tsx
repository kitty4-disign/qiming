"use client";

import { CheckCircle2, Lightbulb, Loader2, Play, Terminal, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  getCodingHint,
  getCodingTask,
  runStudentCode,
  type CodeRunResult,
  type CodingTask,
} from "@/lib/education-api";
import { recordEducationEvent } from "@/lib/education-api";

interface CodingLabProps {
  taskId: string;
  courseId: string;
  masteryPathId: string;
}

export function CodingLab({ taskId, courseId, masteryPathId }: CodingLabProps) {
  const { t } = useTranslation();
  const [task, setTask] = useState<CodingTask | null>(null);
  const [source, setSource] = useState("");
  const [stdin, setStdin] = useState("");
  const [result, setResult] = useState<CodeRunResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [hintAttempt, setHintAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getCodingTask(taskId)
      .then((data) => {
        if (cancelled) return;
        setTask(data);
        setSource(data.starter_code);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  const run = useCallback(async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await runStudentCode({
        course_id: courseId,
        task_id: taskId,
        language: "python",
        source_code: source,
        stdin,
      });
      setResult(res);
      // If all tests pass, record a completion event (learning evidence only,
      // does not change mastery — M2/M3 contract).
      if (res.all_visible_passed && res.all_hidden_passed) {
        await recordEducationEvent({
          course_id: courseId,
          mastery_path_id: masteryPathId,
          activity: "coding",
          event_type: "completed",
          knowledge_point_id: "",
          score: 1.0,
          duration_seconds: null,
          idempotency_key: `coding-${taskId}-${Date.now()}`,
        });
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [courseId, masteryPathId, source, stdin, taskId]);

  const requestHint = useCallback(async () => {
    setError("");
    try {
      const text = await getCodingHint(taskId, hintAttempt);
      setHint(text);
      setHintAttempt((n) => n + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [hintAttempt, taskId]);

  if (error && !task) {
    return (
      <div className="p-6">
        <p role="alert" className="text-sm text-red-600 dark:text-red-300">
          {error}
        </p>
      </div>
    );
  }

  if (!task) {
    return (
      <div className="p-6">
        <Loader2 aria-hidden="true" className="size-4 animate-spin" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-lg font-semibold text-[var(--foreground)]">{task.title}</h1>
        <p className="mt-2 whitespace-pre-wrap text-sm text-[var(--muted-foreground)]">
          {task.instructions}
        </p>
      </header>

      <section aria-labelledby="editor-title">
        <h2 id="editor-title" className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-[var(--foreground)]">
          <Terminal aria-hidden="true" className="size-4" />
          {t("Code Editor")}
        </h2>
        <textarea
          value={source}
          onChange={(event) => setSource(event.target.value)}
          spellCheck={false}
          aria-label={t("Source code")}
          className="min-h-[280px] w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 font-mono text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
        />
        <div className="mt-2 flex items-center gap-3">
          <button
            type="button"
            onClick={() => void run()}
            disabled={loading || !source.trim()}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--primary)] px-4 py-2 text-xs font-semibold text-[var(--primary-foreground)] transition-transform hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <Loader2 aria-hidden="true" className="size-3.5 animate-spin" />
            ) : (
              <Play aria-hidden="true" className="size-3.5" />
            )}
            {loading ? t("Running") : t("Run")}
          </button>
          <span className="text-xs text-[var(--muted-foreground)]">{task.allowed_languages.join(", ")}</span>
        </div>
      </section>

      <section aria-labelledby="stdin-title">
        <h2 id="stdin-title" className="mb-2 text-sm font-semibold text-[var(--foreground)]">
          {t("Standard Input (optional)")}
        </h2>
        <textarea
          value={stdin}
          onChange={(event) => setStdin(event.target.value)}
          spellCheck={false}
          aria-label={t("Standard input")}
          className="min-h-[80px] w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 font-mono text-xs text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
        />
      </section>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-300">
          {error}
        </p>
      )}

      {result && (
        <section aria-labelledby="result-title">
          <h2 id="result-title" className="mb-2 text-sm font-semibold text-[var(--foreground)]">
            {t("Result")}
          </h2>
          {result.timed_out && (
            <p className="mb-2 rounded bg-yellow-50 p-2 text-xs text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200">
              {t("Your program timed out. Check for infinite loops.")}
            </p>
          )}
          <pre className="max-h-[200px] overflow-auto rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 font-mono text-xs text-[var(--foreground)]">
            <span className="text-[var(--muted-foreground)]">stdout:</span>
            {"\n"}
            {result.stdout || t("(empty)")}
            {"\n\n"}
            {result.stderr && (
              <>
                <span className="text-red-600 dark:text-red-300">stderr:</span>
                {"\n"}
                {result.stderr}
              </>
            )}
          </pre>

          <div className="mt-3 space-y-2">
            <h3 className="text-xs font-semibold text-[var(--foreground)]">{t("Visible Tests")}</h3>
            {result.visible_results.map((test) => (
              <div
                key={test.name}
                className="flex items-start gap-2 rounded border border-[var(--border)] p-2"
              >
                {test.passed ? (
                  <CheckCircle2 aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-green-600" />
                ) : (
                  <XCircle aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-red-600" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-[var(--foreground)]">{test.name}</p>
                  {!test.passed && (
                    <pre className="mt-1 whitespace-pre-wrap font-mono text-[10px] text-[var(--muted-foreground)]">
                      {t("got")}: {test.stdout || t("(empty)")}
                      {"\n"}
                      {t("expected")}: {test.expected}
                    </pre>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 rounded-lg border border-[var(--border)] p-3">
            <p className="text-xs text-[var(--muted-foreground)]">
              {t("Hidden Tests")}: {result.hidden_passed} / {result.hidden_total}
            </p>
            {result.all_visible_passed && result.all_hidden_passed && (
              <p className="mt-1 text-xs font-medium text-green-600 dark:text-green-300">
                {t("All tests passed! Completion recorded.")}
              </p>
            )}
          </div>
        </section>
      )}

      <section aria-labelledby="hint-title">
        <h2 id="hint-title" className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-[var(--foreground)]">
          <Lightbulb aria-hidden="true" className="size-4 text-[var(--primary)]" />
          {t("Hint")}
        </h2>
        <button
          type="button"
          onClick={() => void requestHint()}
          disabled={hintAttempt >= task.hint_count}
          className="rounded-md border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--foreground)] transition-transform hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {hintAttempt >= task.hint_count ? t("No more hints") : t("Get a hint")}
        </button>
        {hint && (
          <p className="mt-2 rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 text-xs text-[var(--muted-foreground)]">
            {hint}
          </p>
        )}
      </section>
    </div>
  );
}
