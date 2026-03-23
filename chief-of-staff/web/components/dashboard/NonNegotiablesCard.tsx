"use client";

import { useState, useCallback, useEffect } from "react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { StreakBadge } from "@/components/shared/StreakBadge";
import type { TodayRecurringTask } from "@/lib/types";
import type { ActiveCard } from "@/hooks/useKeyboardShortcuts";
import { useSWRConfig } from "swr";

interface NonNegotiablesCardProps {
  tasks: TodayRecurringTask[];
  isActive: boolean;
  onActivate: () => void;
  registerCard: (card: ActiveCard, handlers: { moveUp: () => void; moveDown: () => void; primary: () => void }) => void;
  unregisterCard: (card: ActiveCard) => void;
}

export function NonNegotiablesCard({
  tasks,
  isActive,
  onActivate,
  registerCard,
  unregisterCard,
}: NonNegotiablesCardProps) {
  const { mutate } = useSWRConfig();
  const [focusedIndex, setFocusedIndex] = useState(0);
  const [completingIds, setCompletingIds] = useState<Set<string>>(new Set());

  const completedCount = tasks.filter((t) => t.completed_today).length;
  const totalCount = tasks.length;
  const progressPct = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  const clamp = useCallback(
    (idx: number) => Math.max(0, Math.min(idx, tasks.length - 1)),
    [tasks.length],
  );

  const completeTask = useCallback(
    async (taskId: string) => {
      if (completingIds.has(taskId)) return;
      const task = tasks.find((t) => t.id === taskId);
      if (!task || task.completed_today) return;

      setCompletingIds((prev) => new Set(prev).add(taskId));

      try {
        await api.recurringTasks.complete(taskId);
        void mutate("/tasks/today");
      } catch {
        // silent failure — state will reconcile on next fetch
      } finally {
        setCompletingIds((prev) => {
          const next = new Set(prev);
          next.delete(taskId);
          return next;
        });
      }
    },
    [tasks, completingIds, mutate],
  );

  // Register keyboard handlers
  useEffect(() => {
    registerCard("non-negotiables", {
      moveUp: () => setFocusedIndex((prev) => clamp(prev - 1)),
      moveDown: () => setFocusedIndex((prev) => clamp(prev + 1)),
      primary: () => {
        const task = tasks[focusedIndex];
        if (task && !task.completed_today) {
          void completeTask(task.id);
        }
      },
    });
    return () => unregisterCard("non-negotiables");
  }, [registerCard, unregisterCard, clamp, tasks, focusedIndex, completeTask]);

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
          Non-Negotiables
        </span>
        <span className="text-xs text-text-dim">
          {completedCount}/{totalCount}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-[2px] bg-surface-3">
        <div
          className="h-full bg-accent transition-all duration-300"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {/* Tasks */}
      <div className="p-[18px] space-y-1">
        {tasks.length === 0 && (
          <p className="text-sm text-text-dim">No tasks for today</p>
        )}
        {tasks.map((task, idx) => (
          <div
            key={task.id}
            className={cn(
              "flex items-center gap-3 px-2 py-1.5 rounded-md transition-colors",
              isActive && idx === focusedIndex && "bg-accent-subtle",
              task.completed_today && "opacity-50",
            )}
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                void completeTask(task.id);
              }}
              disabled={task.completed_today || completingIds.has(task.id)}
              className={cn(
                "flex-shrink-0 w-4 h-4 rounded border transition-colors flex items-center justify-center",
                task.completed_today
                  ? "bg-accent border-accent"
                  : "border-text-dim hover:border-accent",
              )}
            >
              {task.completed_today && (
                <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                  <path
                    d="M1 4L3.5 6.5L9 1"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="text-text-primary"
                  />
                </svg>
              )}
            </button>
            <span
              className={cn(
                "text-sm flex-1",
                task.completed_today
                  ? "line-through text-text-dim"
                  : "text-text-secondary",
              )}
            >
              {task.title}
            </span>
            <StreakBadge count={task.streak_count} />
          </div>
        ))}
      </div>
    </div>
  );
}
