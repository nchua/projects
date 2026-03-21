"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import AuthGuard from "@/components/layout/AuthGuard";
import Header from "@/components/layout/Header";
import ReviewCardComponent from "@/components/review/ReviewCard";
import RatingButtons from "@/components/review/RatingButtons";
import ProgressBar from "@/components/review/ProgressBar";
import SessionSummary from "@/components/review/SessionSummary";
import { useReviewSession } from "@/hooks/useReviewSession";
import { api } from "@/lib/api";
import type { InboxItemResponse } from "@/lib/types";

type SessionMode = "quick5" | "full" | "deep_dive";

function ReviewSession() {
  const searchParams = useSearchParams();
  const mode = (searchParams.get("mode") as SessionMode) || "full";
  const { state, currentCard, currentIndex, totalCards, result, start, reveal, rate } =
    useReviewSession(mode);
  const [inboxCount, setInboxCount] = useState(0);

  useEffect(() => {
    start();
  }, [start]);

  useEffect(() => {
    if (state === "completed") {
      api.get<InboxItemResponse[]>("/inbox").then((items) => setInboxCount(items.length)).catch(() => {});
    }
  }, [state]);

  // Space bar to reveal
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.code === "Space" && state === "reviewing") {
        e.preventDefault();
        reveal();
      }
    },
    [state, reveal],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Loading
  if (state === "loading") {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <p className="text-muted animate-pulse">Loading cards...</p>
      </div>
    );
  }

  // Completed
  if (state === "completed" && result) {
    return <SessionSummary result={result} inboxCount={inboxCount} />;
  }

  // Reviewing
  if (!currentCard) return null;

  return (
    <div className="space-y-6">
      <ProgressBar current={currentIndex} total={totalCards} />

      <ReviewCardComponent card={currentCard} revealed={state === "revealed" || state === "submitting"} />

      {state === "reviewing" && (
        <button
          onClick={reveal}
          className="w-full bg-surface border border-border rounded-xl py-3 text-foreground font-medium hover:border-amber transition-colors"
        >
          Show Answer
          <span className="text-xs text-muted ml-2">space</span>
        </button>
      )}

      {(state === "revealed" || state === "submitting") && (
        <div className="animate-reveal">
          <RatingButtons onRate={rate} disabled={state === "submitting"} />
        </div>
      )}
    </div>
  );
}

export default function ReviewPage() {
  return (
    <AuthGuard>
      <Header />
      <main className="flex-1 px-6 py-8 max-w-2xl mx-auto w-full">
        <Suspense fallback={<p className="text-muted animate-pulse">Loading...</p>}>
          <ReviewSession />
        </Suspense>
      </main>
    </AuthGuard>
  );
}
