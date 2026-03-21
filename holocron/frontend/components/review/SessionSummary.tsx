"use client";

import Link from "next/link";

interface SessionResult {
  totalReviewed: number;
  recalled: number;
  struggled: number;
  forgot: number;
  durationSeconds: number;
  strongestTopic: string | null;
  weakestTopic: string | null;
}

interface Props {
  result: SessionResult;
  inboxCount: number;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s} sec`;
  return `${m} min ${s} sec`;
}

export default function SessionSummary({ result, inboxCount }: Props) {
  if (result.totalReviewed === 0) {
    return (
      <div className="text-center space-y-6">
        <h2 className="text-xl font-semibold">No cards due</h2>
        <p className="text-muted">You&apos;re all caught up. Come back later.</p>
        <Link
          href="/"
          className="inline-block bg-amber text-black font-medium rounded-xl py-2 px-6 hover:bg-amber/90 transition-colors"
        >
          Done
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h2 className="text-sm text-muted uppercase tracking-wider">Session Complete</h2>
        <p className="text-2xl font-semibold mt-2">{formatDuration(result.durationSeconds)}</p>
      </div>

      {/* Breakdown */}
      <div className="bg-surface border border-border rounded-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500" />
            <span className="text-sm">Recalled</span>
          </div>
          <span className="text-sm font-medium text-green-400">{result.recalled}</span>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-yellow-500" />
            <span className="text-sm">Struggled</span>
          </div>
          <span className="text-sm font-medium text-yellow-400">{result.struggled}</span>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            <span className="text-sm">Forgot</span>
          </div>
          <span className="text-sm font-medium text-red-400">{result.forgot}</span>
        </div>
      </div>

      {/* Topic insights */}
      {(result.strongestTopic || result.weakestTopic) && (
        <div className="bg-surface border border-border rounded-2xl p-6 space-y-2 text-sm">
          {result.strongestTopic && (
            <div className="flex justify-between">
              <span className="text-muted">Strongest</span>
              <span className="text-green-400">{result.strongestTopic}</span>
            </div>
          )}
          {result.weakestTopic && result.weakestTopic !== result.strongestTopic && (
            <div className="flex justify-between">
              <span className="text-muted">Focus area</span>
              <span className="text-yellow-400">{result.weakestTopic}</span>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <Link
          href="/"
          className="flex-1 bg-amber text-black font-medium rounded-xl py-3 text-center hover:bg-amber/90 transition-colors"
        >
          Done
        </Link>
        {inboxCount > 0 && (
          <Link
            href="/inbox"
            className="flex-1 bg-surface border border-border text-foreground font-medium rounded-xl py-3 text-center hover:border-amber transition-colors"
          >
            Inbox ({inboxCount})
          </Link>
        )}
      </div>
    </div>
  );
}
