"use client";

import { cn } from "@/lib/utils";

interface StreakBadgeProps {
  count: number;
  className?: string;
}

export function StreakBadge({ count, className }: StreakBadgeProps) {
  if (count <= 0) return null;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded bg-surface-3 text-text-tertiary",
        className,
      )}
    >
      <span aria-hidden>🔥</span>
      {count}
    </span>
  );
}
