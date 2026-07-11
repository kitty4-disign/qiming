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

import type { LearningModality } from "@/lib/education-types";

const MODALITIES: Array<{
  value: LearningModality;
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  { value: "dialogue", label: "Dialogue Learning", description: "Dialogue Learning description", icon: MessageCircle },
  { value: "animation", label: "Animation Learning", description: "Animation Learning description", icon: PlayCircle },
  { value: "storybook", label: "Storybook Learning", description: "Storybook Learning description", icon: BookOpen },
  { value: "coding", label: "Coding Learning", description: "Coding Learning description", icon: Code2 },
  { value: "quiz", label: "Quiz Learning", description: "Quiz Learning description", icon: ClipboardCheck },
];

interface ModalitySelectorProps {
  value: LearningModality[];
  onChange: (modalities: LearningModality[]) => void;
}

export function ModalitySelector({ value, onChange }: ModalitySelectorProps) {
  const { t } = useTranslation();
  const toggle = (modality: LearningModality) => {
    onChange(
      value.includes(modality)
        ? value.filter((item) => item !== modality)
        : [...value, modality],
    );
  };

  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium text-[var(--foreground)]">
        {t("Preferred Learning Modes")}
      </legend>
      <div className="divide-y divide-[var(--border)] border-y border-[var(--border)] sm:grid sm:grid-cols-2 sm:divide-y-0">
        {MODALITIES.map(({ value: modality, label, description, icon: Icon }) => (
          <label
            key={modality}
            className="flex min-w-0 cursor-pointer items-center gap-3 px-1 py-3 transition-colors hover:bg-[var(--muted)]/60 sm:border-b sm:border-[var(--border)] sm:px-3"
          >
            <input
              type="checkbox"
              checked={value.includes(modality)}
              onChange={() => toggle(modality)}
              className="size-4 shrink-0 accent-[var(--primary)]"
            />
            <Icon aria-hidden="true" className="size-4 shrink-0 text-[var(--primary)]" />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-[var(--foreground)]">
                {t(label)}
              </span>
              <span className="block text-xs text-[var(--muted-foreground)]">
                {t(description)}
              </span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
