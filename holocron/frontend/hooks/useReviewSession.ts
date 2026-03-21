"use client";

import { useState, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import type { ReviewCard, Rating, ReviewResponse } from "@/lib/types";

type SessionMode = "quick5" | "full" | "deep_dive";
type SessionState = "idle" | "loading" | "reviewing" | "revealed" | "submitting" | "completed";

const MODE_LIMITS: Record<SessionMode, number> = {
  quick5: 10,
  full: 20,
  deep_dive: 30,
};

interface TopicStats {
  recalled: number;
  struggled: number;
  forgot: number;
}

interface SessionResult {
  totalReviewed: number;
  recalled: number;
  struggled: number;
  forgot: number;
  durationSeconds: number;
  topicStats: Record<string, TopicStats>;
  strongestTopic: string | null;
  weakestTopic: string | null;
}

export function useReviewSession(mode: SessionMode) {
  const [state, setState] = useState<SessionState>("idle");
  const [cards, setCards] = useState<ReviewCard[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [result, setResult] = useState<SessionResult | null>(null);

  // Timing refs (don't trigger re-renders)
  const cardShownAt = useRef<number>(0);
  const revealedAt = useRef<number>(0);
  const sessionStartedAt = useRef<number>(0);

  // Per-topic stats tracking
  const topicStatsRef = useRef<Record<string, TopicStats>>({});

  const currentCard = cards[currentIndex] ?? null;

  const start = useCallback(async () => {
    setState("loading");
    try {
      const limit = MODE_LIMITS[mode];
      const due = await api.get<ReviewCard[]>(`/learning-units/due?limit=${limit}`);
      if (due.length === 0) {
        setResult({
          totalReviewed: 0,
          recalled: 0,
          struggled: 0,
          forgot: 0,
          durationSeconds: 0,
          topicStats: {},
          strongestTopic: null,
          weakestTopic: null,
        });
        setState("completed");
        return;
      }
      setCards(due);
      setCurrentIndex(0);
      topicStatsRef.current = {};
      sessionStartedAt.current = Date.now();
      cardShownAt.current = Date.now();
      setState("reviewing");
    } catch {
      setState("idle");
    }
  }, [mode]);

  const reveal = useCallback(() => {
    if (state !== "reviewing") return;
    revealedAt.current = Date.now();
    setState("revealed");
  }, [state]);

  const rate = useCallback(
    async (rating: Rating) => {
      if (state !== "revealed" || !currentCard) return;
      setState("submitting");

      const timeToReveal = revealedAt.current - cardShownAt.current;
      const timeReading = Date.now() - revealedAt.current;

      // Track per-topic stats
      const topic = currentCard.topic_name;
      if (!topicStatsRef.current[topic]) {
        topicStatsRef.current[topic] = { recalled: 0, struggled: 0, forgot: 0 };
      }
      if (rating === "got_it" || rating === "easy") {
        topicStatsRef.current[topic].recalled++;
      } else if (rating === "struggled") {
        topicStatsRef.current[topic].struggled++;
      } else {
        topicStatsRef.current[topic].forgot++;
      }

      try {
        await api.post<ReviewResponse>("/reviews", {
          learning_unit_id: currentCard.id,
          rating,
          time_to_reveal_ms: timeToReveal,
          time_reading_ms: timeReading,
        });
      } catch {
        // Continue even if submission fails — don't break the session
      }

      const nextIndex = currentIndex + 1;
      if (nextIndex >= cards.length) {
        // Session complete
        const stats = topicStatsRef.current;
        const totalRecalled = Object.values(stats).reduce((s, t) => s + t.recalled, 0);
        const totalStruggled = Object.values(stats).reduce((s, t) => s + t.struggled, 0);
        const totalForgot = Object.values(stats).reduce((s, t) => s + t.forgot, 0);

        // Find strongest/weakest by recall rate
        let strongest: string | null = null;
        let weakest: string | null = null;
        let bestRate = -1;
        let worstRate = 2;
        for (const [t, s] of Object.entries(stats)) {
          const total = s.recalled + s.struggled + s.forgot;
          const recallRate = total > 0 ? s.recalled / total : 0;
          if (recallRate > bestRate) {
            bestRate = recallRate;
            strongest = t;
          }
          if (recallRate < worstRate) {
            worstRate = recallRate;
            weakest = t;
          }
        }

        setResult({
          totalReviewed: cards.length,
          recalled: totalRecalled,
          struggled: totalStruggled,
          forgot: totalForgot,
          durationSeconds: Math.round((Date.now() - sessionStartedAt.current) / 1000),
          topicStats: stats,
          strongestTopic: strongest,
          weakestTopic: weakest,
        });
        setState("completed");
      } else {
        setCurrentIndex(nextIndex);
        cardShownAt.current = Date.now();
        setState("reviewing");
      }
    },
    [state, currentCard, currentIndex, cards.length],
  );

  return {
    state,
    currentCard,
    currentIndex,
    totalCards: cards.length,
    result,
    start,
    reveal,
    rate,
  };
}
