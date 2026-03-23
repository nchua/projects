"use client";

import { useEffect, useCallback } from "react";
import type { DismissReason } from "@/lib/types";

interface DismissPopoverProps {
  onDismiss: (reason: DismissReason) => void;
  onCancel: () => void;
}

const OPTIONS: { key: string; reason: DismissReason; label: string }[] = [
  { key: "1", reason: "not_action_item", label: "Not an action item" },
  { key: "2", reason: "already_done", label: "Already done" },
  { key: "3", reason: "not_relevant", label: "Not relevant" },
];

export function DismissPopover({ onDismiss, onCancel }: DismissPopoverProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
        return;
      }
      const option = OPTIONS.find((o) => o.key === e.key);
      if (option) {
        e.preventDefault();
        onDismiss(option.reason);
      }
    },
    [onDismiss, onCancel],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className="absolute right-0 top-full mt-1 z-50 w-52 bg-surface-3 border border-surface-3 rounded-lg shadow-lg py-1 animate-in fade-in slide-in-from-top-1 duration-150">
      <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-text-dim font-semibold">
        Dismiss reason
      </div>
      {OPTIONS.map((option) => (
        <button
          key={option.reason}
          onClick={() => onDismiss(option.reason)}
          className="flex items-center gap-2 w-full px-3 py-2 text-xs text-text-secondary hover:bg-white/[0.05] transition-colors"
        >
          <kbd className="inline-flex items-center justify-center w-4 h-4 rounded bg-surface-2 text-[10px] text-text-muted font-mono">
            {option.key}
          </kbd>
          {option.label}
        </button>
      ))}
      <div className="px-3 py-1 text-[10px] text-text-dim border-t border-surface-2 mt-1">
        Esc to cancel
      </div>
    </div>
  );
}
