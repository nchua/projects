"use client";

import { useEffect } from "react";
import type { Rating } from "@/lib/types";

interface Props {
  onRate: (rating: Rating) => void;
  disabled: boolean;
}

const RATINGS: { rating: Rating; label: string; key: string; color: string }[] = [
  { rating: "forgot", label: "Forgot", key: "1", color: "bg-red-500/15 text-red-400 border-red-500/30 hover:bg-red-500/25" },
  { rating: "struggled", label: "Struggled", key: "2", color: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30 hover:bg-yellow-500/25" },
  { rating: "got_it", label: "Got it", key: "3", color: "bg-green-500/15 text-green-400 border-green-500/30 hover:bg-green-500/25" },
  { rating: "easy", label: "Easy", key: "4", color: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/25" },
];

export default function RatingButtons({ onRate, disabled }: Props) {
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (disabled) return;
      const idx = ["1", "2", "3", "4"].indexOf(e.key);
      if (idx !== -1) {
        onRate(RATINGS[idx].rating);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onRate, disabled]);

  return (
    <div className="grid grid-cols-4 gap-3">
      {RATINGS.map((r) => (
        <button
          key={r.rating}
          onClick={() => onRate(r.rating)}
          disabled={disabled}
          className={`border rounded-xl py-3 px-2 text-sm font-medium transition-all disabled:opacity-40 ${r.color}`}
        >
          {r.label}
          <span className="block text-xs opacity-60 mt-0.5">{r.key}</span>
        </button>
      ))}
    </div>
  );
}
