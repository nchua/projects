"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/layout/AuthGuard";
import Header from "@/components/layout/Header";
import { api } from "@/lib/api";
import type { TopicResponse } from "@/lib/types";

function masteryColor(pct: number): string {
  if (pct >= 80) return "bg-emerald-500";
  if (pct >= 50) return "bg-amber";
  if (pct >= 20) return "bg-yellow-500";
  return "bg-red-500";
}

function MasteryContent() {
  const [topics, setTopics] = useState<TopicResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<TopicResponse[]>("/topics")
      .then(setTopics)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <p className="text-muted animate-pulse">Loading...</p>;
  }

  if (topics.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-muted">No topics yet. Run /holocron-refresh to get started.</p>
      </div>
    );
  }

  const totalConcepts = topics.reduce((s, t) => s + t.concept_count, 0);
  const avgMastery = topics.length > 0
    ? Math.round(topics.reduce((s, t) => s + t.mastery_pct, 0) / topics.length)
    : 0;

  return (
    <div className="space-y-8">
      {/* Aggregate stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-surface border border-border rounded-xl p-4 text-center">
          <div className="text-2xl font-semibold text-foreground">{topics.length}</div>
          <div className="text-xs text-muted mt-1">Topics</div>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 text-center">
          <div className="text-2xl font-semibold text-foreground">{totalConcepts}</div>
          <div className="text-xs text-muted mt-1">Concepts</div>
        </div>
        <div className="bg-surface border border-border rounded-xl p-4 text-center">
          <div className="text-2xl font-semibold text-amber">{avgMastery}%</div>
          <div className="text-xs text-muted mt-1">Avg mastery</div>
        </div>
      </div>

      {/* Topic bars */}
      <div className="space-y-5">
        {topics.map((topic) => (
          <div key={topic.id} className="bg-surface border border-border rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="font-medium text-foreground">{topic.name}</h3>
                {topic.description && (
                  <p className="text-xs text-muted mt-0.5">{topic.description}</p>
                )}
              </div>
              <span className="text-lg font-semibold text-foreground">{topic.mastery_pct}%</span>
            </div>
            <div className="h-2 bg-background rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-700 ${masteryColor(topic.mastery_pct)}`}
                style={{ width: `${topic.mastery_pct}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-muted mt-2">
              <span>{topic.concept_count} concepts</span>
              <span>Target: {Math.round(topic.target_retention * 100)}% retention</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MasteryPage() {
  return (
    <AuthGuard>
      <Header />
      <main className="flex-1 px-6 py-8 max-w-2xl mx-auto w-full">
        <h1 className="text-xl font-semibold mb-6">Your Mastery</h1>
        <MasteryContent />
      </main>
    </AuthGuard>
  );
}
