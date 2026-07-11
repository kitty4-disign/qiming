"use client";

import {
  BookOpen,
  ClipboardCheck,
  Code2,
  MessageCircle,
  PlayCircle,
  type LucideIcon,
} from "lucide-react";

import type { LearningModality } from "@/lib/education-types";

const MODALITIES: Array<{
  value: LearningModality;
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  { value: "dialogue", label: "对话讲解", description: "边问边学", icon: MessageCircle },
  { value: "animation", label: "动画演示", description: "看见过程", icon: PlayCircle },
  { value: "storybook", label: "故事绘本", description: "用故事理解", icon: BookOpen },
  { value: "coding", label: "编程实践", description: "动手运行", icon: Code2 },
  { value: "quiz", label: "随堂测验", description: "及时检查", icon: ClipboardCheck },
];

interface ModalitySelectorProps {
  value: LearningModality[];
  onChange: (modalities: LearningModality[]) => void;
}

export function ModalitySelector({ value, onChange }: ModalitySelectorProps) {
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
        喜欢的学习方式
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
                {label}
              </span>
              <span className="block text-xs text-[var(--muted-foreground)]">
                {description}
              </span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
