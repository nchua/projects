"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { BriefingResponse } from "@/lib/types";

const PRIORITY_COLORS: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-amber-500",
  low: "bg-blue-400",
};

const SOURCE_LABELS: Record<string, string> = {
  gmail: "Gmail",
  github: "GitHub",
  slack: "Slack",
  granola: "Granola",
  manual: "Manual",
  notion: "Notion",
  discord: "Discord",
};

export default function TrayPopupPage() {
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.briefings
      .today()
      .then(setBriefing)
      .catch(() => setError(true));
  }, []);

  async function openDashboard() {
    const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    const main = await WebviewWindow.getByLabel("main");
    if (main) {
      await main.show();
      await main.setFocus();
    }
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full p-4">
        <p className="text-sm text-text-dim">
          Could not load briefing. Is the backend running?
        </p>
      </div>
    );
  }

  if (!briefing) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const actionItems = briefing.content?.action_items ?? [];
  const memoryContext = briefing.content?.memory_context ?? [];
  const topItems = actionItems.slice(0, 5);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 pt-3 pb-2 border-b border-surface-3/40">
        <div className="text-xs font-medium text-text-tertiary uppercase tracking-wider">
          Today&apos;s Priorities
        </div>
      </div>

      {/* Action items */}
      <div className="flex-1 overflow-y-auto px-1 py-1">
        {topItems.length === 0 ? (
          <div className="flex items-center justify-center h-32">
            <p className="text-sm text-text-dim">No action items today</p>
          </div>
        ) : (
          topItems.map((item) => (
            <button
              key={item.id}
              onClick={openDashboard}
              className="w-full text-left px-3 py-2 rounded-md hover:bg-surface-2 transition-colors group"
            >
              <div className="flex items-start gap-2">
                <div
                  className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${
                    PRIORITY_COLORS[item.priority] ?? "bg-gray-400"
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-text-secondary truncate group-hover:text-text-primary transition-colors">
                    {item.title}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[11px] text-text-dim">
                      {SOURCE_LABELS[item.source] ?? item.source}
                    </span>
                    {item.confidence_score != null && (
                      <span className="text-[11px] text-text-ghost">
                        {Math.round(item.confidence_score * 100)}%
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))
        )}

        {/* Memory context */}
        {memoryContext.length > 0 && (
          <div className="mt-2 px-3">
            <div className="text-[11px] font-medium text-text-ghost uppercase tracking-wider mb-1">
              Context
            </div>
            {memoryContext.slice(0, 3).map((fact) => (
              <div key={fact.id} className="text-xs text-text-dim py-0.5 truncate">
                {fact.fact_text}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-surface-3/40">
        <button
          onClick={openDashboard}
          className="w-full text-center text-[11px] text-text-ghost hover:text-text-tertiary transition-colors"
        >
          <kbd className="font-mono">&#8984;J</kbd> to search &middot; Click to
          open dashboard
        </button>
      </div>
    </div>
  );
}
