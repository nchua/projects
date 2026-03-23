"use client";

import type { BriefingMemoryFact } from "@/lib/types";

interface MemoryContextCardProps {
  facts: BriefingMemoryFact[];
}

const TYPE_LABELS: Record<string, string> = {
  commitment: "Commitment",
  deadline: "Deadline",
  decision: "Decision",
  context: "Context",
  follow_up: "Follow-up",
};

const TYPE_COLORS: Record<string, string> = {
  commitment: "text-blue-400",
  deadline: "text-orange-400",
  decision: "text-emerald-400",
  context: "text-text-tertiary",
  follow_up: "text-violet-400",
};

export function MemoryContextCard({ facts }: MemoryContextCardProps) {
  return (
    <div className="bg-surface-2 border border-surface-3 rounded-[10px] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-surface-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">
          Context
        </span>
        {facts.length > 0 && (
          <span className="text-[10px] text-text-ghost">
            {facts.length} fact{facts.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="p-[18px] space-y-2.5">
        {facts.length === 0 && (
          <p className="text-sm text-text-dim">
            No context yet — facts will appear as messages are processed
          </p>
        )}
        {facts.map((fact) => (
          <div key={fact.id} className="flex items-start gap-2.5">
            <span
              className={`text-[10px] font-medium uppercase tracking-wider mt-0.5 min-w-[70px] ${
                TYPE_COLORS[fact.fact_type] ?? "text-text-tertiary"
              }`}
            >
              {TYPE_LABELS[fact.fact_type] ?? fact.fact_type}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-text-secondary leading-snug">
                {fact.fact_text}
              </p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] text-text-ghost">
                  from {fact.source}
                </span>
                {fact.valid_until && (
                  <span className="text-[10px] text-orange-400/70">
                    expires{" "}
                    {new Date(fact.valid_until).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                )}
                {fact.people && fact.people.length > 0 && (
                  <span className="text-[10px] text-text-ghost">
                    {fact.people.join(", ")}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
