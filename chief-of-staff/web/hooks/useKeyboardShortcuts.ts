"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";

export type ActiveCard = "non-negotiables" | "action-items" | null;

interface CardHandlers {
  moveUp: () => void;
  moveDown: () => void;
  primary: () => void; // Space for tasks, a for action items
  secondary?: () => void; // d for dismiss on action items
}

interface UseKeyboardShortcutsReturn {
  showOverlay: boolean;
  closeOverlay: () => void;
  activeCard: ActiveCard;
  setActiveCard: (card: ActiveCard) => void;
  registerCard: (card: ActiveCard, handlers: CardHandlers) => void;
  unregisterCard: (card: ActiveCard) => void;
}

export function useKeyboardShortcuts(): UseKeyboardShortcutsReturn {
  const router = useRouter();
  const [showOverlay, setShowOverlay] = useState(false);
  const [activeCard, setActiveCard] = useState<ActiveCard>(null);
  const handlersRef = useRef<Map<ActiveCard, CardHandlers>>(new Map());

  const registerCard = useCallback(
    (card: ActiveCard, handlers: CardHandlers) => {
      handlersRef.current.set(card, handlers);
    },
    [],
  );

  const unregisterCard = useCallback((card: ActiveCard) => {
    handlersRef.current.delete(card);
  }, []);

  const closeOverlay = useCallback(() => {
    setShowOverlay(false);
  }, []);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Ignore when typing in input fields
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable
      ) {
        return;
      }

      // Shortcut overlay toggle
      if (e.key === "?") {
        e.preventDefault();
        setShowOverlay((prev) => !prev);
        return;
      }

      // Skip everything else when overlay is open
      if (showOverlay) return;

      // Global navigation
      if (e.key === "b" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        router.push("/");
        return;
      }
      if (e.key === "s" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        router.push("/settings");
        return;
      }

      // Card-specific shortcuts
      if (activeCard) {
        const handlers = handlersRef.current.get(activeCard);
        if (!handlers) return;

        switch (e.key) {
          case "j":
            e.preventDefault();
            handlers.moveDown();
            break;
          case "k":
            e.preventDefault();
            handlers.moveUp();
            break;
          case " ":
            if (activeCard === "non-negotiables") {
              e.preventDefault();
              handlers.primary();
            }
            break;
          case "a":
            if (activeCard === "action-items") {
              e.preventDefault();
              handlers.primary();
            }
            break;
          case "d":
            if (activeCard === "action-items" && handlers.secondary) {
              e.preventDefault();
              handlers.secondary();
            }
            break;
          case "Escape":
            e.preventDefault();
            setActiveCard(null);
            break;
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeCard, showOverlay, router]);

  return {
    showOverlay,
    closeOverlay,
    activeCard,
    setActiveCard,
    registerCard,
    unregisterCard,
  };
}
