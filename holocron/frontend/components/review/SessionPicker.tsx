"use client";

import { useRouter } from "next/navigation";

const MODES = [
  { key: "quick5", label: "Quick 5", desc: "~5 min", cards: 10 },
  { key: "full", label: "Full", desc: "~10 min", cards: 20 },
  { key: "deep_dive", label: "Deep Dive", desc: "~20 min", cards: 30 },
] as const;

interface Props {
  dueCount: number;
}

export default function SessionPicker({ dueCount }: Props) {
  const router = useRouter();

  return (
    <div className="grid grid-cols-3 gap-3">
      {MODES.map((mode) => {
        const available = Math.min(mode.cards, dueCount);
        const disabled = dueCount === 0;
        return (
          <button
            key={mode.key}
            onClick={() => router.push(`/review?mode=${mode.key}`)}
            disabled={disabled}
            className="bg-surface border border-border rounded-xl p-4 text-center hover:border-amber hover:bg-surface-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            <div className="text-foreground font-medium">{mode.label}</div>
            <div className="text-muted text-sm mt-1">{mode.desc}</div>
            {!disabled && (
              <div className="text-amber text-xs mt-2">{available} cards</div>
            )}
          </button>
        );
      })}
    </div>
  );
}
