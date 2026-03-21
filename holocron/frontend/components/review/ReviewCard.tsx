"use client";

import type { ReviewCard as ReviewCardType } from "@/lib/types";

interface Props {
  card: ReviewCardType;
  revealed: boolean;
}

/** Parse cloze front_content: replace {{blank}} with underline spans */
function renderCloze(text: string, answers: string[], revealed: boolean) {
  const parts = text.split(/\{\{blank\}\}/g);
  const result: React.ReactNode[] = [];

  for (let i = 0; i < parts.length; i++) {
    result.push(<span key={`t-${i}`}>{parts[i]}</span>);
    if (i < parts.length - 1) {
      if (revealed && answers[i]) {
        result.push(
          <span key={`a-${i}`} className="text-amber font-medium underline decoration-amber/50 underline-offset-2">
            {answers[i]}
          </span>,
        );
      } else {
        result.push(
          <span key={`b-${i}`} className="inline-block min-w-[80px] border-b-2 border-muted mx-1">
            &nbsp;
          </span>,
        );
      }
    }
  }
  return result;
}

export default function ReviewCard({ card, revealed }: Props) {
  const isCloze = card.type === "cloze";
  const clozeAnswers = isCloze ? card.back_content.split("; ") : [];

  return (
    <div className="bg-surface border border-border rounded-2xl p-8 min-h-[280px] flex flex-col">
      {/* Topic label */}
      <div className="text-xs text-amber uppercase tracking-wider mb-6">
        {card.type === "cloze" ? "FILL IN" : "RECALL"} &middot; {card.topic_name}
      </div>

      {/* Front content */}
      <div className="flex-1 flex items-center">
        <p className="text-lg leading-relaxed">
          {isCloze
            ? renderCloze(card.front_content, clozeAnswers, revealed)
            : card.front_content}
        </p>
      </div>

      {/* Back content (revealed) */}
      {revealed && !isCloze && (
        <div className="mt-6 pt-6 border-t border-border animate-reveal">
          <p className="text-foreground/90 leading-relaxed">{card.back_content}</p>
        </div>
      )}

      {/* Source */}
      {card.source_name && (
        <div className="mt-4 text-xs text-muted">
          Source: {card.source_name}
        </div>
      )}
    </div>
  );
}
