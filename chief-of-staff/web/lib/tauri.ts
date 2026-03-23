/** True when running inside a Tauri webview (desktop app). */
export const isTauri =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
