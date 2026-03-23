"use client";

import { useEffect, useCallback } from "react";

interface ShortcutOverlayProps {
  onClose: () => void;
}

const SHORTCUTS: { section: string; items: { keys: string; description: string }[] }[] = [
  {
    section: "Global",
    items: [
      { keys: "?", description: "Toggle shortcut help" },
      { keys: "b", description: "Go to dashboard" },
      { keys: "s", description: "Go to settings" },
    ],
  },
  {
    section: "Non-Negotiables",
    items: [
      { keys: "j / k", description: "Navigate tasks" },
      { keys: "Space", description: "Complete focused task" },
    ],
  },
  {
    section: "Action Items",
    items: [
      { keys: "j / k", description: "Navigate items" },
      { keys: "a", description: "Acknowledge selected" },
      { keys: "d", description: "Dismiss selected" },
    ],
  },
  {
    section: "Dismiss Popover",
    items: [
      { keys: "1", description: "Not an action item" },
      { keys: "2", description: "Already done" },
      { keys: "3", description: "Not relevant" },
      { keys: "Esc", description: "Cancel" },
    ],
  },
];

export function ShortcutOverlay({ onClose }: ShortcutOverlayProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "?" || e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [onClose],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-surface-2 border border-surface-3 rounded-xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-text-primary">
            Keyboard shortcuts
          </h2>
          <button
            onClick={onClose}
            className="text-text-dim hover:text-text-tertiary text-sm transition-colors"
          >
            Esc
          </button>
        </div>

        <div className="grid grid-cols-2 gap-x-8 gap-y-5">
          {SHORTCUTS.map((section) => (
            <div key={section.section}>
              <h3 className="text-[10px] uppercase tracking-wider text-text-dim font-semibold mb-2">
                {section.section}
              </h3>
              <div className="space-y-1.5">
                {section.items.map((item) => (
                  <div
                    key={item.keys}
                    className="flex items-center justify-between gap-4"
                  >
                    <kbd className="text-[11px] font-mono px-1.5 py-0.5 bg-surface-3 rounded text-text-muted min-w-[40px] text-center">
                      {item.keys}
                    </kbd>
                    <span className="text-xs text-text-tertiary flex-1">
                      {item.description}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
