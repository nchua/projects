"use client";

import { cn } from "@/lib/utils";
import { format, isPast, parseISO } from "date-fns";
import type { BriefingCalendarEvent } from "@/lib/types";

interface CalendarCardProps {
  events: BriefingCalendarEvent[];
}

export function CalendarCard({ events }: CalendarCardProps) {
  return (
    <div className="bg-surface-2 border border-surface-3 rounded-[10px] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-surface-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">
          Calendar
        </span>
        {events.length > 0 && (
          <span className="text-xs text-text-dim">
            {events.length} event{events.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Events */}
      <div className="p-[18px] space-y-1">
        {events.length === 0 && (
          <p className="text-sm text-text-dim">No events today</p>
        )}
        {events.map((event, idx) => {
          const startDate = parseISO(event.start_time);
          const past = isPast(startDate);

          return (
            <div
              key={`${event.title}-${idx}`}
              className={cn(
                "flex items-start gap-3 px-2 py-1.5 rounded-md",
                past && "opacity-40",
              )}
            >
              {/* Time */}
              <span className="flex-shrink-0 text-xs font-mono text-text-muted w-[42px] pt-0.5">
                {format(startDate, "HH:mm")}
              </span>

              {/* Details */}
              <div className="flex-1 min-w-0">
                <div className="text-sm text-text-secondary truncate">
                  {event.title}
                </div>
                {event.location && (
                  <div className="text-xs text-text-dim truncate mt-0.5">
                    {event.location}
                  </div>
                )}
              </div>

              {/* Needs-prep indicator */}
              {event.needs_prep && (
                <span className="flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-status-degraded/15 text-status-degraded">
                  Prep
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
