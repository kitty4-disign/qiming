"use client";

import { Pencil } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { CourseOverview } from "@/components/education/CourseOverview";
import { LearningActionGrid } from "@/components/education/LearningActionGrid";
import { LearningEvidenceCard } from "@/components/education/LearningEvidenceCard";
import { LearningTimeline } from "@/components/education/LearningTimeline";
import { MasterySummary } from "@/components/education/MasterySummary";
import { RecommendedNextStep } from "@/components/education/RecommendedNextStep";
import { StudentProfileForm } from "@/components/education/StudentProfileForm";
import { getEducationDashboard, getLaunchContext } from "@/lib/education-api";
import type {
  EducationCatalog,
  EducationLaunchContext,
  StudentProfile,
} from "@/lib/education-types";

interface EducationDashboardProps {
  catalog: EducationCatalog;
  profile: StudentProfile;
}

export function EducationDashboard({ catalog, profile }: EducationDashboardProps) {
  const { t, i18n } = useTranslation();
  const [currentProfile, setCurrentProfile] = useState(profile);
  const [editing, setEditing] = useState(false);
  const textbook = useMemo(
    () => catalog.textbooks.find((item) => item.id === currentProfile.textbook_id),
    [catalog, currentProfile.textbook_id],
  );
  const [courseId, setCourseId] = useState(textbook?.default_course_id ?? "");
  const [launchResult, setLaunchResult] = useState<{
    courseId: string;
    context: EducationLaunchContext | null;
  } | null>(null);
  const [dashboardData, setDashboardData] = useState<{
    courseId: string;
    data: Awaited<ReturnType<typeof getEducationDashboard>> | null;
  } | null>(null);
  const [dashboardError, setDashboardError] = useState(false);

  const fetchDashboard = useCallback((id: string) => {
    let active = true;
    getEducationDashboard(id)
      .then((data) => {
        if (active) {
          setDashboardData({ courseId: id, data });
          setDashboardError(false);
        }
      })
      .catch(() => {
        if (active) {
          setDashboardData({ courseId: id, data: null });
          setDashboardError(true);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!courseId) return;
    let active = true;
    getLaunchContext(courseId)
      .then((context) => {
        if (active) setLaunchResult({ courseId, context });
      })
      .catch(() => {
        if (active) setLaunchResult({ courseId, context: null });
      });
    const cleanup = fetchDashboard(courseId);
    return () => {
      active = false;
      cleanup();
    };
  }, [courseId, fetchDashboard]);

  if (!textbook) return null;
  const course = textbook.courses.find((item) => item.id === courseId) ?? textbook.courses[0];
  if (!course) return null;
  const launchContext = launchResult?.courseId === courseId ? launchResult.context : null;
  const isChinese = i18n.language.startsWith("zh");
  const pathId = launchContext?.mastery_path_id ?? "";
  const kbWarning = launchContext?.warnings.some((warning) =>
    warning.startsWith("knowledge_base_not_ready:"),
  );
  const dashboard = dashboardData?.courseId === courseId ? dashboardData.data : null;
  const recommendation = dashboard?.recommendation ?? null;
  const recentEvents = dashboard?.recent_events ?? [];
  const masterySummary = dashboard?.mastery_summary ?? null;
  const learningEvidence = dashboard?.learning_evidence ?? null;
  const teachingDecision = dashboard?.teaching_decision ?? null;
  const dashboardLoading = dashboardData?.courseId !== courseId;

  return (
    <div className="min-w-0">
      <header className="flex flex-col gap-3 pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm text-[var(--muted-foreground)]">
            {t("Student greeting", { name: currentProfile.display_name })}
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-[var(--foreground)]">
            {t("AI Classroom")}
          </h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            {t("Grade label", { grade: currentProfile.grade })} · {isChinese ? textbook.title_zh : textbook.title_en}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setEditing((value) => !value)}
          title={t("Edit Profile")}
          aria-label={t("Edit Profile")}
          className="inline-flex size-9 items-center justify-center self-start rounded-lg border border-[var(--border)] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)] active:scale-[0.98] sm:self-auto"
        >
          <Pencil aria-hidden="true" className="size-4" />
        </button>
      </header>

      {editing ? (
        <section className="border-t border-[var(--border)] py-6" aria-label={t("Student Profile")}>
          <StudentProfileForm
            catalog={catalog}
            initialProfile={currentProfile}
            onSaved={(saved) => {
              const savedTextbook = catalog.textbooks.find(
                (item) => item.id === saved.textbook_id,
              );
              setCurrentProfile(saved);
              setCourseId(savedTextbook?.default_course_id ?? "");
              setEditing(false);
            }}
          />
        </section>
      ) : (
        <>
          {textbook.courses.length > 1 && (
            <div className="flex gap-1 overflow-x-auto border-t border-[var(--border)] py-4">
              {textbook.courses.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={item.id === course.id}
                  onClick={() => setCourseId(item.id)}
                  className={`shrink-0 rounded-md px-3 py-2 text-sm transition-colors ${
                    item.id === course.id
                      ? "bg-[var(--foreground)] text-[var(--background)]"
                      : "bg-[var(--muted)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {isChinese ? item.title_zh : item.title_en}
                </button>
              ))}
            </div>
          )}
          {kbWarning && (
            <div
              role="status"
              className="border-y border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
            >
              {t("Textbook knowledge base is not ready")}
            </div>
          )}
          <CourseOverview course={course} />
          {pathId ? (
            <MasterySummary
              pathId={pathId}
              masterySummary={masterySummary}
              nextKnowledgePoint={recommendation?.knowledge_point_name}
            />
          ) : (
            <section className="border-t border-[var(--border)] py-6">
              <div className="h-16 animate-pulse rounded bg-[var(--muted)]" />
            </section>
          )}
          {recommendation && (
            <RecommendedNextStep
              recommendation={recommendation}
              course={course}
              profile={currentProfile}
              launchContext={launchContext}
              onLaunched={() => fetchDashboard(courseId)}
            />
          )}
          {dashboardError && (
            <div
              role="alert"
              className="border-t border-[var(--border)] py-4 text-sm text-[var(--muted-foreground)]"
            >
              {t("Failed to load recommendation")}
              <button
                type="button"
                onClick={() => fetchDashboard(courseId)}
                className="ml-2 underline text-[var(--primary)]"
              >
                {t("Retry")}
              </button>
            </div>
          )}
          <LearningActionGrid course={course} profile={currentProfile} launchContext={launchContext} />
          <LearningEvidenceCard
            evidence={learningEvidence}
            decision={teachingDecision}
            loading={dashboardLoading}
            textbookTitle={isChinese ? textbook.title_zh : textbook.title_en}
            courseTitle={isChinese ? course.title_zh : course.title_en}
          />
          <LearningTimeline events={recentEvents} />
        </>
      )}
    </div>
  );
}
