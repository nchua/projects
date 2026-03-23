"use client";

interface InsightsCardProps {
  insights: string | null;
}

/** Minimal bold-text renderer: wraps **text** in <strong>. */
function renderInsightLine(line: string, idx: number) {
  const parts = line.split(/(\*\*[^*]+\*\*)/g);
  return (
    <p key={idx} className="text-sm text-text-secondary leading-relaxed">
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={i} className="font-semibold text-text-primary">
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}

export function InsightsCard({ insights }: InsightsCardProps) {
  const lines = insights
    ? insights.split("\n").filter((l) => l.trim().length > 0)
    : [];

  return (
    <div className="bg-surface-2 border border-surface-3 rounded-[10px] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-surface-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">
          Insights
        </span>
      </div>

      {/* Content */}
      <div className="p-[18px] space-y-2">
        {lines.length === 0 && (
          <p className="text-sm text-text-dim">No insights available</p>
        )}
        {lines.map((line, idx) => renderInsightLine(line, idx))}
      </div>
    </div>
  );
}
