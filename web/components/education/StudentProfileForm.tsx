"use client";

import { Save } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import { ModalitySelector } from "@/components/education/ModalitySelector";
import { StageSegmentedControl } from "@/components/education/StageSegmentedControl";
import { saveEducationProfile } from "@/lib/education-api";
import { gradesForStage, textbooksForStage } from "@/lib/education-profile";
import type {
  EducationCatalog,
  EducationStage,
  LearningModality,
  StudentProfile,
} from "@/lib/education-types";

interface StudentProfileFormProps {
  catalog: EducationCatalog;
  initialProfile: StudentProfile | null;
  onSaved: (profile: StudentProfile) => void;
}

const fieldClass =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2.5 text-sm text-[var(--foreground)] outline-none transition-colors placeholder:text-[var(--muted-foreground)] focus:border-[var(--primary)] focus:ring-2 focus:ring-[var(--primary)]/15";

function normalizeInterests(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[,，]/)
        .map((item) => item.trim().slice(0, 30))
        .filter(Boolean),
    ),
  ).slice(0, 5);
}

export function StudentProfileForm({
  catalog,
  initialProfile,
  onSaved,
}: StudentProfileFormProps) {
  const initialStage: EducationStage =
    initialProfile?.stage ?? catalog.textbooks[0]?.stage ?? "primary_lower";
  const initialTextbooks = textbooksForStage(catalog, initialStage);
  const [displayName, setDisplayName] = useState(initialProfile?.display_name ?? "同学");
  const [stage, setStage] = useState<EducationStage>(initialStage);
  const [grade, setGrade] = useState(
    initialProfile?.grade ?? gradesForStage(initialStage)[0],
  );
  const [textbookId, setTextbookId] = useState(
    initialProfile?.textbook_id ?? initialTextbooks[0]?.id ?? "",
  );
  const [interests, setInterests] = useState(initialProfile?.interests.join("，") ?? "");
  const [modalities, setModalities] = useState<LearningModality[]>(
    initialProfile?.preferred_modalities ?? ["dialogue", "quiz"],
  );
  const [learningGoal, setLearningGoal] = useState(initialProfile?.learning_goal ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const grades = useMemo(() => gradesForStage(stage), [stage]);
  const textbooks = useMemo(() => textbooksForStage(catalog, stage), [catalog, stage]);

  const changeStage = (nextStage: EducationStage) => {
    const nextTextbooks = textbooksForStage(catalog, nextStage);
    setStage(nextStage);
    setGrade(gradesForStage(nextStage)[0]);
    setTextbookId(nextTextbooks[0]?.id ?? "");
    setFieldErrors({});
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    if (!displayName.trim()) nextErrors.displayName = "请输入学生称呼";
    if (!textbookId) nextErrors.textbook = "当前学段没有可选教材";
    if (modalities.length === 0) nextErrors.modalities = "请至少选择一种学习方式";
    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setSaving(true);
    setError("");
    try {
      const saved = await saveEducationProfile({
        schema_version: 1,
        display_name: displayName.trim(),
        stage,
        grade,
        textbook_id: textbookId,
        interests: normalizeInterests(interests),
        preferred_modalities: modalities,
        learning_goal: learningGoal.trim(),
      });
      onSaved(saved);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="w-full min-w-0 space-y-6" noValidate>
      <div>
        <label htmlFor="education-display-name" className="mb-2 block text-sm font-medium">
          学生称呼
        </label>
        <input
          id="education-display-name"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          maxLength={30}
          aria-describedby={fieldErrors.displayName ? "display-name-error" : undefined}
          className={fieldClass}
          placeholder="例如：小航"
        />
        {fieldErrors.displayName && (
          <p id="display-name-error" className="mt-1.5 text-xs text-red-600">
            {fieldErrors.displayName}
          </p>
        )}
      </div>

      <StageSegmentedControl value={stage} onChange={changeStage} />

      <div className="grid min-w-0 gap-4 sm:grid-cols-2">
        <div className="min-w-0">
          <label htmlFor="education-grade" className="mb-2 block text-sm font-medium">
            年级
          </label>
          <select
            id="education-grade"
            value={grade}
            onChange={(event) => setGrade(Number(event.target.value))}
            className={fieldClass}
          >
            {grades.map((item) => (
              <option key={item} value={item}>
                {item} 年级
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-0">
          <label htmlFor="education-textbook" className="mb-2 block text-sm font-medium">
            教材
          </label>
          <select
            id="education-textbook"
            value={textbookId}
            onChange={(event) => setTextbookId(event.target.value)}
            aria-describedby={fieldErrors.textbook ? "textbook-error" : undefined}
            className={fieldClass}
          >
            {textbooks.map((textbook) => (
              <option key={textbook.id} value={textbook.id}>
                {textbook.title_zh}
              </option>
            ))}
          </select>
          {fieldErrors.textbook && (
            <p id="textbook-error" className="mt-1.5 text-xs text-red-600">
              {fieldErrors.textbook}
            </p>
          )}
        </div>
      </div>

      <div>
        <label htmlFor="education-interests" className="mb-2 block text-sm font-medium">
          兴趣方向
        </label>
        <input
          id="education-interests"
          value={interests}
          onChange={(event) => setInterests(event.target.value)}
          className={fieldClass}
          placeholder="机器人，绘画，足球"
        />
        <p className="mt-1.5 text-xs text-[var(--muted-foreground)]">
          用逗号分隔，最多保留五项
        </p>
      </div>

      <div aria-describedby={fieldErrors.modalities ? "modalities-error" : undefined}>
        <ModalitySelector value={modalities} onChange={setModalities} />
        {fieldErrors.modalities && (
          <p id="modalities-error" className="mt-1.5 text-xs text-red-600">
            {fieldErrors.modalities}
          </p>
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <label htmlFor="education-goal" className="text-sm font-medium">
            学习目标
          </label>
          <span className="text-xs tabular-nums text-[var(--muted-foreground)]">
            {learningGoal.length}/200
          </span>
        </div>
        <textarea
          id="education-goal"
          value={learningGoal}
          onChange={(event) => setLearningGoal(event.target.value)}
          maxLength={200}
          rows={4}
          className={`${fieldClass} resize-y`}
          placeholder="这次最想理解什么？"
        />
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        >
          {error}
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={saving}
          className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-semibold text-[var(--primary-foreground)] transition-transform hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Save aria-hidden="true" className={`size-4 ${saving ? "animate-pulse" : ""}`} />
          {saving ? "正在保存" : "保存学习画像"}
        </button>
      </div>
    </form>
  );
}
