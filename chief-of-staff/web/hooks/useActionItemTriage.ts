"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api";
import type { DismissReason, BriefingActionItem } from "@/lib/types";
import { useSWRConfig } from "swr";

interface UseActionItemTriageReturn {
  selectedIndex: number;
  showDismissPopover: boolean;
  /** Items remaining after dismiss/acknowledge */
  visibleItems: BriefingActionItem[];
  moveUp: () => void;
  moveDown: () => void;
  openDismiss: () => void;
  closeDismiss: () => void;
  dismiss: (reason: DismissReason) => Promise<void>;
  acknowledge: () => Promise<void>;
}

export function useActionItemTriage(
  items: BriefingActionItem[],
): UseActionItemTriageReturn {
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showDismissPopover, setShowDismissPopover] = useState(false);
  const { mutate } = useSWRConfig();

  const visibleItems = items.filter((item) => !dismissedIds.has(item.id));

  const clampIndex = useCallback(
    (idx: number) => Math.max(0, Math.min(idx, visibleItems.length - 1)),
    [visibleItems.length],
  );

  const moveUp = useCallback(() => {
    setSelectedIndex((prev) => clampIndex(prev - 1));
  }, [clampIndex]);

  const moveDown = useCallback(() => {
    setSelectedIndex((prev) => clampIndex(prev + 1));
  }, [clampIndex]);

  const openDismiss = useCallback(() => {
    if (visibleItems.length > 0) {
      setShowDismissPopover(true);
    }
  }, [visibleItems.length]);

  const closeDismiss = useCallback(() => {
    setShowDismissPopover(false);
  }, []);

  const dismiss = useCallback(
    async (reason: DismissReason) => {
      const item = visibleItems[selectedIndex];
      if (!item) return;

      setDismissedIds((prev) => new Set(prev).add(item.id));
      setShowDismissPopover(false);

      // Clamp index after removing
      const newLength = visibleItems.length - 1;
      if (selectedIndex >= newLength && newLength > 0) {
        setSelectedIndex(newLength - 1);
      }

      try {
        await api.actionItems.dismiss(item.id, reason);
        void mutate("/briefings/today");
      } catch {
        // Revert on failure
        setDismissedIds((prev) => {
          const next = new Set(prev);
          next.delete(item.id);
          return next;
        });
      }
    },
    [visibleItems, selectedIndex, mutate],
  );

  const acknowledge = useCallback(async () => {
    const item = visibleItems[selectedIndex];
    if (!item) return;

    setDismissedIds((prev) => new Set(prev).add(item.id));

    const newLength = visibleItems.length - 1;
    if (selectedIndex >= newLength && newLength > 0) {
      setSelectedIndex(newLength - 1);
    }

    try {
      await api.actionItems.acknowledge(item.id);
      void mutate("/briefings/today");
    } catch {
      setDismissedIds((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
  }, [visibleItems, selectedIndex, mutate]);

  return {
    selectedIndex,
    showDismissPopover,
    visibleItems,
    moveUp,
    moveDown,
    openDismiss,
    closeDismiss,
    dismiss,
    acknowledge,
  };
}
