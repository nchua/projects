"use client";

import { useEffect, useState, useCallback } from "react";
import AuthGuard from "@/components/layout/AuthGuard";
import Header from "@/components/layout/Header";
import { api } from "@/lib/api";
import type { InboxItemResponse } from "@/lib/types";

function confidenceColor(score: number): string {
  if (score >= 0.85) return "text-green-400 bg-green-500/15 border-green-500/30";
  if (score >= 0.7) return "text-yellow-400 bg-yellow-500/15 border-yellow-500/30";
  return "text-red-400 bg-red-500/15 border-red-500/30";
}

function InboxCardItem({
  item,
  onAction,
}: {
  item: InboxItemResponse;
  onAction: (id: number, action: "accepted" | "rejected") => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [front, setFront] = useState(item.front_content);
  const [back, setBack] = useState(item.back_content);

  async function handleSaveEdit() {
    // Accept first, then update content
    await api.put(`/inbox/${item.id}`, { status: "accepted" });
    await api.put(`/learning-units/${item.learning_unit_id}`, {
      front_content: front,
      back_content: back,
    });
    onAction(item.id, "accepted");
  }

  return (
    <div className="bg-surface border border-border rounded-xl p-5 space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {item.source_name && <span className="text-sm text-muted">{item.source_name}</span>}
          <span className={`text-xs px-2 py-0.5 rounded-full border ${confidenceColor(item.confidence_score)}`}>
            {Math.round(item.confidence_score * 100)}%
          </span>
          <span className="text-xs text-muted uppercase">{item.unit_type}</span>
        </div>
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-muted hover:text-foreground transition-colors">
          {expanded ? "Collapse" : "Preview"}
        </button>
      </div>

      {/* Card preview */}
      <div className="text-sm">
        <p className="text-foreground/90">{item.front_content}</p>
      </div>

      {expanded && (
        <div className="text-sm text-muted border-t border-border pt-3 animate-reveal">
          <p>{item.back_content}</p>
        </div>
      )}

      {/* Edit mode */}
      {editing && (
        <div className="space-y-3 border-t border-border pt-3 animate-reveal">
          <div>
            <label className="block text-xs text-muted mb-1">Front</label>
            <textarea
              value={front}
              onChange={(e) => setFront(e.target.value)}
              rows={2}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-amber resize-none"
            />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">Back</label>
            <textarea
              value={back}
              onChange={(e) => setBack(e.target.value)}
              rows={2}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-amber resize-none"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleSaveEdit}
              className="text-sm bg-green-500/15 text-green-400 border border-green-500/30 rounded-lg px-3 py-1.5 hover:bg-green-500/25 transition-colors"
            >
              Save & Accept
            </button>
            <button
              onClick={() => setEditing(false)}
              className="text-sm text-muted hover:text-foreground transition-colors px-3 py-1.5"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Actions */}
      {!editing && (
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => onAction(item.id, "accepted")}
            className="text-sm bg-green-500/15 text-green-400 border border-green-500/30 rounded-lg px-3 py-1.5 hover:bg-green-500/25 transition-colors"
          >
            Accept
          </button>
          <button
            onClick={() => setEditing(true)}
            className="text-sm bg-surface text-foreground border border-border rounded-lg px-3 py-1.5 hover:border-amber transition-colors"
          >
            Edit
          </button>
          <button
            onClick={() => onAction(item.id, "rejected")}
            className="text-sm bg-red-500/15 text-red-400 border border-red-500/30 rounded-lg px-3 py-1.5 hover:bg-red-500/25 transition-colors"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

function InboxContent() {
  const [items, setItems] = useState<InboxItemResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<InboxItemResponse[]>("/inbox")
      .then(setItems)
      .finally(() => setLoading(false));
  }, []);

  const handleAction = useCallback(async (id: number, action: "accepted" | "rejected") => {
    await api.put(`/inbox/${id}`, { status: action });
    setItems((prev) => prev.filter((i) => i.id !== id));
  }, []);

  if (loading) {
    return <p className="text-muted animate-pulse">Loading inbox...</p>;
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-muted">No pending cards. All clear.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((item) => (
        <InboxCardItem key={item.id} item={item} onAction={handleAction} />
      ))}
    </div>
  );
}

export default function InboxPage() {
  return (
    <AuthGuard>
      <Header />
      <main className="flex-1 px-6 py-8 max-w-2xl mx-auto w-full">
        <h1 className="text-xl font-semibold mb-6">Inbox</h1>
        <InboxContent />
      </main>
    </AuthGuard>
  );
}
