"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ActionItemResponse, MemoryFactResponse } from "@/lib/types";

interface SearchResult {
  id: string;
  type: "action_item" | "memory";
  title: string;
  subtitle: string;
  priority?: string;
}

const PRIORITY_COLORS: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-amber-500",
  low: "bg-blue-400",
};

export default function SpotlightPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [allItems, setAllItems] = useState<SearchResult[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load data on mount
  useEffect(() => {
    async function loadData() {
      const items: SearchResult[] = [];

      try {
        const actionItems: ActionItemResponse[] = await api.actionItems.list({
          status: "new",
          limit: 50,
        });
        for (const item of actionItems) {
          items.push({
            id: item.id,
            type: "action_item",
            title: item.title,
            subtitle: `${item.source} · ${item.priority}`,
            priority: item.priority,
          });
        }
      } catch {
        // Backend may not be running
      }

      try {
        const facts: MemoryFactResponse[] = await api.memory.list();
        for (const fact of facts) {
          items.push({
            id: fact.id,
            type: "memory",
            title: fact.fact_text,
            subtitle: `${fact.fact_type} · ${fact.source}`,
          });
        }
      } catch {
        // Backend may not be running
      }

      setAllItems(items);
      setResults(items.slice(0, 8));
    }

    loadData();
    inputRef.current?.focus();
  }, []);

  // Filter results when query changes
  useEffect(() => {
    if (!query.trim()) {
      setResults(allItems.slice(0, 8));
      setSelectedIndex(0);
      return;
    }

    const q = query.toLowerCase();
    const filtered = allItems.filter(
      (item) =>
        item.title.toLowerCase().includes(q) ||
        item.subtitle.toLowerCase().includes(q),
    );
    setResults(filtered.slice(0, 8));
    setSelectedIndex(0);
  }, [query, allItems]);

  const hideWindow = useCallback(() => {
    import("@tauri-apps/api/webviewWindow").then(({ getCurrentWebviewWindow }) => {
      getCurrentWebviewWindow().hide();
    });
  }, []);

  const openInMain = useCallback(async () => {
    const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    const main = await WebviewWindow.getByLabel("main");
    if (main) {
      await main.show();
      await main.setFocus();
    }
    hideWindow();
  }, [hideWindow]);

  function handleKeyDown(e: React.KeyboardEvent) {
    switch (e.key) {
      case "Escape":
        hideWindow();
        break;
      case "ArrowDown":
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
        break;
      case "Enter":
        if (results[selectedIndex]) {
          openInMain();
        }
        break;
    }
  }

  return (
    <div
      className="flex items-start justify-center pt-[60px] h-full"
      onKeyDown={handleKeyDown}
    >
      <div className="w-[640px] bg-surface-1/95 backdrop-blur-xl rounded-2xl border border-surface-3/50 shadow-2xl overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-surface-3/40">
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="text-text-dim shrink-0"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search action items, memory..."
            className="flex-1 bg-transparent text-[15px] text-text-primary outline-none placeholder:text-text-ghost"
            autoFocus
          />
          <kbd className="text-[11px] text-text-ghost bg-surface-3/50 px-1.5 py-0.5 rounded font-mono">
            esc
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-[320px] overflow-y-auto py-1">
          {results.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-text-dim">
              {query ? "No results found" : "Loading..."}
            </div>
          ) : (
            results.map((item, index) => (
              <button
                key={item.id}
                onClick={openInMain}
                onMouseEnter={() => setSelectedIndex(index)}
                className={`w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors ${
                  index === selectedIndex
                    ? "bg-accent/10"
                    : "hover:bg-surface-2/50"
                }`}
              >
                {item.type === "action_item" && item.priority && (
                  <div
                    className={`w-2 h-2 rounded-full shrink-0 ${
                      PRIORITY_COLORS[item.priority] ?? "bg-gray-400"
                    }`}
                  />
                )}
                {item.type === "memory" && (
                  <div className="w-2 h-2 rounded-sm shrink-0 bg-violet-400/60" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-text-secondary truncate">
                    {item.title}
                  </div>
                  <div className="text-[11px] text-text-dim truncate">
                    {item.subtitle}
                  </div>
                </div>
                {index === selectedIndex && (
                  <kbd className="text-[10px] text-text-ghost bg-surface-3/40 px-1 py-0.5 rounded font-mono shrink-0">
                    &#9166;
                  </kbd>
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
