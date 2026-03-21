"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/layout/AuthGuard";
import Header from "@/components/layout/Header";
import SessionPicker from "@/components/review/SessionPicker";
import { api } from "@/lib/api";
import type { ReviewCard, TopicResponse, InboxItemResponse } from "@/lib/types";
import Link from "next/link";

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning.";
  if (hour < 18) return "Good afternoon.";
  return "Good evening.";
}

function Dashboard() {
  const [dueCards, setDueCards] = useState<ReviewCard[]>([]);
  const [topics, setTopics] = useState<TopicResponse[]>([]);
  const [inboxCount, setInboxCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<ReviewCard[]>("/learning-units/due"),
      api.get<TopicResponse[]>("/topics"),
      api.get<InboxItemResponse[]>("/inbox"),
    ])
      .then(([cards, t, inbox]) => {
        setDueCards(cards);
        setTopics(t);
        setInboxCount(inbox.length);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <p className="text-muted animate-pulse">Loading...</p>;
  }

  const dueCount = dueCards.length;
  const estMinutes = Math.max(1, Math.round((dueCount * 30) / 60));

  // Group due cards by topic
  const topicDueCounts: Record<string, number> = {};
  for (const card of dueCards) {
    topicDueCounts[card.topic_name] = (topicDueCounts[card.topic_name] || 0) + 1;
  }

  return (
    <div className="space-y-8">
      {/* Greeting */}
      <div>
        <h1 className="text-2xl font-semibold">{getGreeting()}</h1>
        {dueCount > 0 ? (
          <p className="text-muted mt-1">
            {dueCount} items due today. Estimated time: ~{estMinutes} min
          </p>
        ) : (
          <p className="text-muted mt-1">You&apos;re all caught up. Enjoy your day.</p>
        )}
      </div>

      {/* Session Picker */}
      <SessionPicker dueCount={dueCount} />

      {/* Topic Breakdown */}
      {dueCount > 0 && (
        <div>
          <h2 className="text-sm text-muted uppercase tracking-wider mb-3">Topics today</h2>
          <div className="space-y-2">
            {Object.entries(topicDueCounts).map(([topic, count]) => (
              <div key={topic} className="flex items-center justify-between text-sm">
                <span className="text-foreground">{topic}</span>
                <span className="text-muted">{count} due</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Inbox */}
      {inboxCount > 0 && (
        <Link
          href="/inbox"
          className="block bg-surface border border-border rounded-xl p-4 hover:border-amber transition-colors"
        >
          <span className="text-muted text-sm">Inbox:</span>{" "}
          <span className="text-foreground">{inboxCount} cards awaiting review</span>
        </Link>
      )}

      {/* Quick Mastery Glance */}
      {topics.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm text-muted uppercase tracking-wider">Mastery</h2>
            <Link href="/mastery" className="text-sm text-amber hover:underline">
              View all
            </Link>
          </div>
          <div className="space-y-3">
            {topics.map((topic) => (
              <div key={topic.id}>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-foreground">{topic.name}</span>
                  <span className="text-muted">{topic.mastery_pct}%</span>
                </div>
                <div className="h-1.5 bg-surface rounded-full overflow-hidden">
                  <div
                    className="h-full bg-amber rounded-full transition-all duration-500"
                    style={{ width: `${topic.mastery_pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function HomePage() {
  return (
    <AuthGuard>
      <Header />
      <main className="flex-1 px-6 py-8 max-w-2xl mx-auto w-full">
        <Dashboard />
      </main>
    </AuthGuard>
  );
}
