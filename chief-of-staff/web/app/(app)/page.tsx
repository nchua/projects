"use client";

import useSWR from "swr";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { format } from "date-fns";
import { NonNegotiablesCard } from "@/components/dashboard/NonNegotiablesCard";
import { ActionItemsCard } from "@/components/dashboard/ActionItemsCard";
import { CalendarCard } from "@/components/dashboard/CalendarCard";
import { InsightsCard } from "@/components/dashboard/InsightsCard";
import { MemoryContextCard } from "@/components/dashboard/MemoryContextCard";
import { ShortcutOverlay } from "@/components/shared/ShortcutOverlay";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import type { BriefingResponse, TodayTasksResponse } from "@/lib/types";

function SkeletonCard({ title }: { title: string }) {
  return (
    <div className="bg-surface-2 border border-surface-3 rounded-[10px] overflow-hidden animate-pulse">
      <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-surface-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">
          {title}
        </span>
      </div>
      <div className="p-[18px] space-y-3">
        <div className="h-3 bg-surface-3 rounded w-3/4" />
        <div className="h-3 bg-surface-3 rounded w-1/2" />
        <div className="h-3 bg-surface-3 rounded w-2/3" />
      </div>
    </div>
  );
}

function ErrorCard({ title, message }: { title: string; message: string }) {
  return (
    <div className="bg-surface-2 border border-red-500/20 rounded-[10px] overflow-hidden">
      <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-surface-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">
          {title}
        </span>
      </div>
      <div className="p-[18px]">
        <p className="text-xs text-red-400">{message}</p>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const now = new Date();
  const greeting =
    now.getHours() < 12
      ? "Good morning"
      : now.getHours() < 17
        ? "Good afternoon"
        : "Good evening";

  const {
    showOverlay,
    closeOverlay,
    activeCard,
    setActiveCard,
    registerCard,
    unregisterCard,
  } = useKeyboardShortcuts();

  const { data: briefing, isLoading: briefingLoading, error: briefingError } =
    useSWR<BriefingResponse>("/briefings/today", () => api.briefings.today(), {
      refreshInterval: 120_000,
    });

  const { data: todayTasks, isLoading: tasksLoading, error: tasksError } =
    useSWR<TodayTasksResponse>("/tasks/today", () => api.tasks.today(), {
      refreshInterval: 30_000,
    });

  const briefingContent = briefing?.content ?? null;
  const generatingBriefing = briefing && !briefing.content;

  // "Morning complete" check:
  // All non-negotiable recurring tasks are completed AND no pending action items
  const recurringTasks = todayTasks?.recurring_tasks ?? [];
  const actionItems = briefingContent?.action_items ?? [];
  const allTasksCompleted =
    recurringTasks.length > 0 &&
    recurringTasks.every((t) => t.completed_today);
  const noActionItems = actionItems.length === 0;
  const morningComplete =
    !tasksLoading &&
    !briefingLoading &&
    allTasksCompleted &&
    noActionItems;

  return (
    <div>
      {/* Header */}
      <div className="px-8 pt-7">
        <h1 className="text-[22px] font-semibold text-text-primary">
          {greeting}
          <span className="font-normal text-text-muted ml-2 text-base">
            {format(now, "EEEE, MMMM d")}
          </span>
        </h1>
        {user && (
          <p className="mt-1 text-xs text-text-dim">
            {user.email}
            <span className="ml-3 text-text-ghost">
              Press <kbd className="font-mono px-1 py-0.5 bg-surface-3 rounded text-[10px]">?</kbd> for shortcuts
            </span>
          </p>
        )}
      </div>

      {/* Morning complete banner */}
      {morningComplete && (
        <div className="mx-8 mt-4 px-4 py-3 bg-status-healthy/8 border border-status-healthy/20 rounded-lg text-sm text-status-healthy flex items-center gap-2">
          <span>&#10003;</span>
          All done for today. Nice work.
        </div>
      )}

      {/* Generating banner */}
      {generatingBriefing && (
        <div className="mx-8 mt-4 px-4 py-3 bg-accent-subtle border border-accent/20 rounded-lg text-sm text-accent flex items-center gap-2">
          <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-accent/30 border-t-accent rounded-full" />
          Generating your briefing...
        </div>
      )}

      {/* Dashboard grid */}
      <div className="grid grid-cols-2 gap-5 p-8 pt-6 max-w-[1400px]">
        {/* Non-Negotiables */}
        {tasksLoading ? (
          <SkeletonCard title="Non-Negotiables" />
        ) : tasksError ? (
          <ErrorCard title="Non-Negotiables" message="Failed to load tasks." />
        ) : (
          <NonNegotiablesCard
            tasks={recurringTasks}
            isActive={activeCard === "non-negotiables"}
            onActivate={() => setActiveCard("non-negotiables")}
            registerCard={registerCard}
            unregisterCard={unregisterCard}
          />
        )}

        {/* Action Items */}
        {briefingLoading ? (
          <SkeletonCard title="Action Items" />
        ) : briefingError ? (
          <ErrorCard title="Action Items" message="Failed to load briefing." />
        ) : (
          <ActionItemsCard
            items={actionItems}
            isActive={activeCard === "action-items"}
            onActivate={() => setActiveCard("action-items")}
            registerCard={registerCard}
            unregisterCard={unregisterCard}
          />
        )}

        {/* Calendar */}
        {briefingLoading ? (
          <SkeletonCard title="Calendar" />
        ) : briefingError ? (
          <ErrorCard title="Calendar" message="Failed to load calendar." />
        ) : (
          <CalendarCard events={briefingContent?.calendar_events ?? []} />
        )}

        {/* Insights */}
        {briefingLoading ? (
          <SkeletonCard title="Insights" />
        ) : briefingError ? (
          <ErrorCard title="Insights" message="Failed to load insights." />
        ) : (
          <InsightsCard insights={briefingContent?.ai_insights ?? null} />
        )}

        {/* Memory Context */}
        {briefingLoading ? (
          <SkeletonCard title="Context" />
        ) : briefingError ? (
          <ErrorCard title="Context" message="Failed to load context." />
        ) : (
          <MemoryContextCard facts={briefingContent?.memory_context ?? []} />
        )}
      </div>

      {/* Shortcut overlay */}
      {showOverlay && <ShortcutOverlay onClose={closeOverlay} />}
    </div>
  );
}
