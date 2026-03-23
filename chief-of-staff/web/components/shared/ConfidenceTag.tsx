"use client";

import { cn } from "@/lib/utils";

interface ConfidenceTagProps {
  score: number | null;
  className?: string;
}

function getConfidenceColor(score: number): string {
  if (score > 0.8) return "bg-status-healthy/15 text-status-healthy";
  if (score >= 0.6) return "bg-status-degraded/15 text-status-degraded";
  return "bg-status-failed/15 text-status-failed";
}

export function ConfidenceTag({ score, className }: ConfidenceTagProps) {
  if (score === null || score === undefined) return null;

  return (
    <span
      className={cn(
        "inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded-full",
        getConfidenceColor(score),
        className,
      )}
    >
      {Math.round(score * 100)}%
    </span>
  );
}
