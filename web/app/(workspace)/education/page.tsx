"use client";

import { RotateCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { EducationDashboard } from "@/components/education/EducationDashboard";
import { StudentProfileForm } from "@/components/education/StudentProfileForm";
import {
  educationErrorKey,
  getEducationCatalog,
  getEducationProfile,
} from "@/lib/education-api";
import type { EducationCatalog, StudentProfile } from "@/lib/education-types";

export default function EducationPage() {
  const { t } = useTranslation();
  const [catalog, setCatalog] = useState<EducationCatalog | null>(null);
  const [profile, setProfile] = useState<StudentProfile | null | undefined>(undefined);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    void Promise.all([getEducationProfile(), getEducationCatalog()])
      .then(([nextProfile, nextCatalog]) => {
        setProfile(nextProfile);
        setCatalog(nextCatalog);
      })
      .catch((reason) => {
        setError(t(educationErrorKey(reason)));
      });
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const retry = () => {
    setError("");
    setProfile(undefined);
    setCatalog(null);
    load();
  };

  if (profile === undefined || catalog === null) {
    return (
      <main className="mx-auto h-full w-full max-w-6xl overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">
        {error ? (
          <div role="alert" className="border-y border-red-300 py-5 text-sm text-red-700">
            <p>{error}</p>
            <button
              type="button"
              onClick={retry}
              className="mt-3 inline-flex items-center gap-2 rounded-md border border-[var(--border)] px-3 py-2 font-medium text-[var(--foreground)]"
            >
              <RotateCw aria-hidden="true" className="size-4" />
              {t("Try again")}
            </button>
          </div>
        ) : (
          <div aria-label={t("Loading AI Classroom")} className="space-y-5">
            <div className="h-7 w-44 animate-pulse rounded bg-[var(--muted)]" />
            <div className="h-16 animate-pulse rounded bg-[var(--muted)]" />
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="h-28 animate-pulse rounded bg-[var(--muted)]" />
              <div className="h-28 animate-pulse rounded bg-[var(--muted)]" />
            </div>
          </div>
        )}
      </main>
    );
  }

  return (
    <main className="mx-auto h-full w-full max-w-6xl overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">
      {profile === null ? (
        <div className="mx-auto max-w-3xl">
          <header className="mb-6 border-b border-[var(--border)] pb-5">
            <p className="text-sm font-medium text-[var(--primary)]">{t("AI Classroom")}</p>
            <h1 className="mt-1 text-2xl font-semibold text-[var(--foreground)]">
              {t("Student Profile")}
            </h1>
            <p className="mt-2 text-sm text-[var(--muted-foreground)]">
              {t("Student Profile introduction")}
            </p>
          </header>
          <StudentProfileForm catalog={catalog} initialProfile={null} onSaved={setProfile} />
        </div>
      ) : (
        <EducationDashboard catalog={catalog} profile={profile} />
      )}
    </main>
  );
}
