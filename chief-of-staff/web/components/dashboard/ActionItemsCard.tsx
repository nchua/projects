"use client";

import { useEffect } from "react";
import { cn } from "@/lib/utils";
import { ConfidenceTag } from "@/components/shared/ConfidenceTag";
import { DismissPopover } from "@/components/shared/DismissPopover";
import { useActionItemTriage } from "@/hooks/useActionItemTriage";
import type { BriefingActionItem, ActionItemSource } from "@/lib/types";
import type { ActiveCard } from "@/hooks/useKeyboardShortcuts";

interface ActionItemsCardProps {
  items: BriefingActionItem[];
  isActive: boolean;
  onActivate: () => void;
  registerCard: (card: ActiveCard, handlers: { moveUp: () => void; moveDown: () => void; primary: () => void; secondary: () => void }) => void;
  unregisterCard: (card: ActiveCard) => void;
}

const SOURCE_ICONS: Record<ActionItemSource, string> = {
  gmail: "\u2709",
  github: "\u2B24",
  slack: "\u0023",
  notion: "\u25A1",
  discord: "\u25C6",
  granola: "\uD83C\uDF99",
  manual: "\u270E",
};

const PRIORITY_DOT_COLORS: Record<string, string> = {
  high: "bg-status-failed",
  medium: "bg-status-degraded",
  low: "bg-text-dim",
};

export function ActionItemsCard({
  items,
  isActive,
  onActivate,
  registerCard,
  unregisterCard,
}: ActionItemsCardProps) {
  const triage = useActionItemTriage(items);

  // Register keyboard handlers
  useEffect(() => {
    registerCard("action-items", {
      moveUp: triage.moveUp,
      moveDown: triage.moveDown,
      primary: triage.acknowledge,
      secondary: triage.openDismiss,
    });
    return () => unregisterCard("action-items");
  }, [registerCard, unregisterCard, triage.moveUp, triage.moveDown, triage.acknowledge, triage.openDismiss]);

  const allCaughtUp = triage.visibleItems.length === 0 && items.length > 0;

  return (
    <div
      className={cn(
        "bg-surface-2 border rounded-[10px] overflow-hidden transition-colors",
        isActive ? "border-accent" : "border-surface-3",
      )}
      onClick={onActivate}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-surface-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">
          Action Items
        </span>
        {triage.visibleItems.length > 0 && (
          <span className="text-xs text-text-dim">
            {triage.visibleItems.length} pending
          </span>
        )}
      </div>

      {/* Items */}
      <div className="p-[18px] space-y-1">
        {allCaughtUp && (
          <div className="flex items-center justify-center py-4 text-sm text-status-healthy">
            All caught up &#x2713;
          </div>
        )}
        {!allCaughtUp && triage.visibleItems.length === 0 && (
          <p className="text-sm text-text-dim">No action items</p>
        )}
        {triage.visibleItems.map((item, idx) => (
          <div
            key={item.id}
            className={cn(
              "relative flex items-center gap-3 px-2 py-1.5 rounded-md transition-colors",
              isActive && idx === triage.selectedIndex && "bg-accent-subtle border-l-2 border-l-accent",
              item.confidence_score !== null &&
                item.confidence_score < 0.6 &&
                "opacity-50",
            )}
          >
            {/* Source icon */}
            <span className="flex-shrink-0 w-4 text-center text-xs text-text-dim">
              {SOURCE_ICONS[item.source] ?? "\u2022"}
            </span>

            {/* Priority dot */}
            <span
              className={cn(
                "flex-shrink-0 w-1.5 h-1.5 rounded-full",
                PRIORITY_DOT_COLORS[item.priority] ?? "bg-text-dim",
              )}
            />

            {/* Title */}
            <span className="text-sm text-text-secondary flex-1 truncate">
              {item.title}
            </span>

            {/* Confidence tag */}
            <ConfidenceTag score={item.confidence_score} />

            {/* Dismiss popover */}
            {triage.showDismissPopover && idx === triage.selectedIndex && (
              <DismissPopover
                onDismiss={triage.dismiss}
                onCancel={triage.closeDismiss}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
