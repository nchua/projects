"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";

type CallbackState =
  | { phase: "exchanging" }
  | { phase: "success" }
  | { phase: "error"; message: string };

/** Decode the provider from the state JWT payload (base64url-encoded, not secret). */
function getProviderFromState(state: string): string {
  try {
    const payload = JSON.parse(atob(state.split(".")[1]));
    return payload.provider ?? "google_calendar";
  } catch {
    return "google_calendar";
  }
}

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [state, setState] = useState<CallbackState>({ phase: "exchanging" });

  useEffect(() => {
    const code = searchParams.get("code");
    const stateParam = searchParams.get("state");
    // Provider is encoded in the state JWT payload
    const provider = stateParam
      ? getProviderFromState(stateParam)
      : searchParams.get("provider") ?? "google_calendar";

    if (!code || !stateParam) {
      setState({
        phase: "error",
        message: "Missing authorization code or state parameter.",
      });
      return;
    }

    const redirectUri = `${window.location.origin}/callback`;

    async function exchangeCode() {
      try {
        if (provider === "github") {
          await api.integrations.githubCallback(code!, redirectUri, stateParam!);
        } else if (provider === "slack") {
          await api.integrations.slackCallback(code!, redirectUri, stateParam!);
        } else {
          // google_calendar, gmail — both use Google OAuth
          await api.integrations.googleCallback(code!, redirectUri, stateParam!, provider);
        }
        setState({ phase: "success" });
        // Redirect to settings after a short delay to show success
        setTimeout(() => {
          router.replace("/settings");
        }, 1200);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to complete authorization.";
        setState({ phase: "error", message });
      }
    }

    void exchangeCode();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="w-full max-w-[400px] px-6 text-center">
      {/* Brand */}
      <div className="w-12 h-12 mx-auto mb-6 bg-gradient-to-br from-blue-700 to-blue-500 rounded-xl flex items-center justify-center text-[22px] text-white">
        &#9632;
      </div>

      {state.phase === "exchanging" && (
        <>
          <div className="flex items-center justify-center gap-2 mb-3">
            <span className="animate-spin inline-block w-4 h-4 border-2 border-accent/30 border-t-accent rounded-full" />
            <span className="text-sm text-text-secondary">
              Completing authorization...
            </span>
          </div>
          <p className="text-xs text-text-dim">
            Exchanging code with provider. This should only take a moment.
          </p>
        </>
      )}

      {state.phase === "success" && (
        <>
          <div className="text-lg text-status-healthy mb-2">&#10003;</div>
          <div className="text-sm text-text-secondary mb-2">
            Integration connected successfully
          </div>
          <p className="text-xs text-text-dim">
            Redirecting to settings...
          </p>
        </>
      )}

      {state.phase === "error" && (
        <>
          <div className="text-lg text-red-400 mb-2">&#10007;</div>
          <div className="text-sm text-text-secondary mb-2">
            Authorization failed
          </div>
          <div className="px-3 py-2.5 text-xs text-red-400 bg-red-500/8 border border-red-500/15 rounded-md mb-4">
            {state.message}
          </div>
          <button
            onClick={() => router.replace("/settings")}
            className="px-4 py-2 text-xs font-medium rounded-md bg-surface-2 border border-surface-3 text-text-secondary transition-colors hover:bg-surface-3"
          >
            Back to Settings
          </button>
        </>
      )}
    </div>
  );
}

export default function CallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="w-full max-w-[400px] px-6 text-center">
          <div className="flex items-center justify-center gap-2">
            <span className="animate-spin inline-block w-4 h-4 border-2 border-accent/30 border-t-accent rounded-full" />
            <span className="text-sm text-text-secondary">Loading...</span>
          </div>
        </div>
      }
    >
      <CallbackHandler />
    </Suspense>
  );
}
