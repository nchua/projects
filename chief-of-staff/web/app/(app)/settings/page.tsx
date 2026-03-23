"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import useSWR from "swr";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { IntegrationCard } from "@/components/settings/IntegrationCard";
import type {
  IntegrationResponse,
  IntegrationProvider,
} from "@/lib/types";
import { isTauri } from "@/lib/tauri";

// ── Timezone options ────────────────────────────────────────────

const TIMEZONES = [
  { value: "America/Los_Angeles", label: "America/Los_Angeles (PT)" },
  { value: "America/Denver", label: "America/Denver (MT)" },
  { value: "America/Chicago", label: "America/Chicago (CT)" },
  { value: "America/New_York", label: "America/New_York (ET)" },
  { value: "Asia/Taipei", label: "Asia/Taipei (CST)" },
  { value: "Asia/Tokyo", label: "Asia/Tokyo (JST)" },
  { value: "Europe/London", label: "Europe/London (GMT)" },
  { value: "Europe/Berlin", label: "Europe/Berlin (CET)" },
  { value: "UTC", label: "UTC" },
];

// ── Integration providers to show ───────────────────────────────

const INTEGRATION_PROVIDERS: IntegrationProvider[] = [
  "google_calendar",
  "gmail",
  "apple_calendar",
  "github",
  "slack",
  "granola",
];

export default function SettingsPage() {
  const { user, updateUser } = useAuth();

  // ── Integrations data ───────────────────────────────────────
  const {
    data: integrations,
    mutate: mutateIntegrations,
  } = useSWR<IntegrationResponse[]>(
    "/integrations",
    () => api.integrations.list(),
    { refreshInterval: 30_000 },
  );

  // ── Preferences state ───────────────────────────────────────
  const [timezone, setTimezone] = useState(user?.timezone ?? "");
  const [wakeTime, setWakeTime] = useState(user?.wake_time ?? "07:00");
  const [prefsSaving, setPrefsSaving] = useState(false);
  const [prefsSaved, setPrefsSaved] = useState(false);
  const [prefsError, setPrefsError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      setTimezone(user.timezone ?? "");
      setWakeTime(user.wake_time ?? "07:00");
    }
  }, [user]);

  async function savePreferences() {
    setPrefsSaving(true);
    setPrefsError(null);
    setPrefsSaved(false);
    try {
      await updateUser({
        timezone: timezone || undefined,
        wake_time: wakeTime || undefined,
      });
      setPrefsSaved(true);
      setTimeout(() => setPrefsSaved(false), 2000);
    } catch {
      setPrefsError("Failed to save preferences.");
    } finally {
      setPrefsSaving(false);
    }
  }

  // ── Autostart state (Tauri only) ────────────────────────────
  const [autostart, setAutostart] = useState(false);
  const [autostartLoading, setAutostartLoading] = useState(false);

  useEffect(() => {
    if (!isTauri) return;
    import("@tauri-apps/plugin-autostart").then(({ isEnabled }) => {
      isEnabled().then(setAutostart);
    });
  }, []);

  async function toggleAutostart() {
    if (!isTauri) return;
    setAutostartLoading(true);
    try {
      const { enable, disable } = await import(
        "@tauri-apps/plugin-autostart"
      );
      if (autostart) {
        await disable();
        setAutostart(false);
      } else {
        await enable();
        setAutostart(true);
      }
    } finally {
      setAutostartLoading(false);
    }
  }

  // ── Panic state ─────────────────────────────────────────────
  const [panicInput, setPanicInput] = useState("");
  const [panicking, setPanicking] = useState(false);
  const [panicDone, setPanicDone] = useState(false);
  const [panicError, setPanicError] = useState<string | null>(null);

  async function handlePanic() {
    if (panicInput !== "REVOKE") return;
    setPanicking(true);
    setPanicError(null);
    try {
      await api.integrations.panicRevokeAll();
      setPanicDone(true);
      setPanicInput("");
      void mutateIntegrations();
    } catch {
      setPanicError("Failed to revoke integrations.");
    } finally {
      setPanicking(false);
    }
  }

  // ── OAuth connect handlers ──────────────────────────────────

  const getRedirectUri = useCallback(() => {
    if (typeof window === "undefined") return "";
    return `${window.location.origin}/callback`;
  }, []);

  // Refs to track pending Tauri OAuth state (avoids stale closures)
  const pendingProviderRef = useRef<string | null>(null);
  const pendingPortRef = useRef<number | null>(null);
  const [oauthError, setOauthError] = useState<{ provider: string; message: string } | null>(null);

  // Listen for oauth-callback events from the Rust listener
  useEffect(() => {
    if (!isTauri) return;
    let unlisten: (() => void) | null = null;

    import("@tauri-apps/api/event").then(({ listen }) => {
      listen<{ code: string; state: string }>("oauth-callback", async (event) => {
        const { code, state } = event.payload;
        const port = pendingPortRef.current;
        const provider = pendingProviderRef.current;
        if (!port) return;

        const redirectUri = `http://localhost:${port}/callback`;

        try {
          if (provider === "github") {
            await api.integrations.githubCallback(code, redirectUri, state);
          } else if (provider === "slack") {
            await api.integrations.slackCallback(code, redirectUri, state);
          } else {
            await api.integrations.googleCallback(code, redirectUri, state, provider ?? "google_calendar");
          }
          void mutateIntegrations();
          setOauthError(null);
        } catch (e) {
          setOauthError({
            provider: provider ?? "unknown",
            message: e instanceof Error ? e.message : "OAuth exchange failed",
          });
        } finally {
          pendingProviderRef.current = null;
          pendingPortRef.current = null;
        }
      }).then((fn) => { unlisten = fn; });
    });

    return () => { unlisten?.(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function startTauriOAuth(
    provider: string,
    getAuthUrl: (redirectUri: string) => Promise<{ authorization_url: string }>,
  ) {
    const { invoke } = await import("@tauri-apps/api/core");
    const port = await invoke<number>("start_oauth_listener");
    const redirectUri = `http://localhost:${port}/callback`;

    pendingProviderRef.current = provider;
    pendingPortRef.current = port;

    const { authorization_url } = await getAuthUrl(redirectUri);

    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(authorization_url);
  }

  async function connectGoogle() {
    if (isTauri) {
      await startTauriOAuth("google_calendar", (uri) =>
        api.integrations.googleAuthorize(uri),
      );
    } else {
      const { authorization_url } = await api.integrations.googleAuthorize(
        getRedirectUri(),
      );
      window.location.href = authorization_url;
    }
  }

  async function connectGmail() {
    if (isTauri) {
      await startTauriOAuth("gmail", (uri) =>
        api.integrations.googleAuthorize(uri),
      );
    } else {
      const { authorization_url } = await api.integrations.googleAuthorize(
        getRedirectUri(),
      );
      window.location.href = authorization_url;
    }
  }

  async function connectGitHub() {
    if (isTauri) {
      await startTauriOAuth("github", (uri) =>
        api.integrations.githubAuthorize(uri),
      );
    } else {
      const { authorization_url } = await api.integrations.githubAuthorize(
        getRedirectUri(),
      );
      window.location.href = authorization_url;
    }
  }

  async function connectSlack() {
    if (isTauri) {
      await startTauriOAuth("slack", (uri) =>
        api.integrations.slackAuthorize(uri),
      );
    } else {
      const { authorization_url } = await api.integrations.slackAuthorize(
        getRedirectUri(),
      );
      window.location.href = authorization_url;
    }
  }

  // ── Apple Calendar selection state ──────────────────────────
  const [appleCalendars, setAppleCalendars] = useState<string[] | null>(null);
  const [appleSelected, setAppleSelected] = useState<Set<string>>(new Set());
  const [appleLoading, setAppleLoading] = useState(false);
  const [appleError, setAppleError] = useState<string | null>(null);

  async function connectAppleCalendar() {
    // If we haven't fetched calendars yet, fetch them and show picker
    if (!appleCalendars) {
      setAppleLoading(true);
      setAppleError(null);
      try {
        const { calendars } = await api.integrations.appleCalendarListCalendars();
        setAppleCalendars(calendars);
        setAppleSelected(new Set(calendars)); // default: all selected
      } catch (e) {
        setAppleError(e instanceof Error ? e.message : "Failed to list calendars");
      } finally {
        setAppleLoading(false);
      }
      return;
    }

    // If we have calendars, configure with selected ones
    if (appleSelected.size === 0) {
      setAppleError("Select at least one calendar");
      return;
    }
    setAppleLoading(true);
    setAppleError(null);
    try {
      await api.integrations.appleCalendarConfigure([...appleSelected]);
      setAppleCalendars(null); // reset picker
      void mutateIntegrations();
    } catch (e) {
      setAppleError(e instanceof Error ? e.message : "Failed to configure");
    } finally {
      setAppleLoading(false);
    }
  }

  // ── Granola configure state ───────────────────────────────
  const [granolaPath, setGranolaPath] = useState(
    "~/Library/Application Support/Granola/cache-v6.json",
  );
  const [granolaError, setGranolaError] = useState<string | null>(null);

  async function connectGranola() {
    setGranolaError(null);
    try {
      await api.integrations.granolaConfigure(granolaPath);
      void mutateIntegrations();
    } catch (e) {
      setGranolaError(e instanceof Error ? e.message : "Failed to configure Granola");
    }
  }

  async function disconnectIntegration(id: string) {
    await api.integrations.disconnect(id);
    void mutateIntegrations();
  }

  async function syncIntegration(id: string) {
    await api.integrations.sync(id);
    void mutateIntegrations();
  }

  // ── Connect handler router ─────────────────────────────────

  function getConnectHandler(provider: IntegrationProvider) {
    switch (provider) {
      case "google_calendar":
        return connectGoogle;
      case "gmail":
        return connectGmail;
      case "github":
        return connectGitHub;
      case "slack":
        return connectSlack;
      case "apple_calendar":
        return connectAppleCalendar;
      case "granola":
        return connectGranola;
      default:
        return async () => {};
    }
  }

  function findIntegration(
    provider: IntegrationProvider,
  ): IntegrationResponse | null {
    return integrations?.find((i) => i.provider === provider) ?? null;
  }

  // ── Render ──────────────────────────────────────────────────

  return (
    <div className="px-8 pt-7 pb-12 max-w-[860px]">
      <h1 className="text-[22px] font-semibold text-text-primary mb-7">
        Settings
      </h1>

      {/* ── Integrations ──────────────────────────────────────── */}
      <SettingsSection title="Integrations">
        {INTEGRATION_PROVIDERS.map((provider) => (
          <IntegrationCard
            key={provider}
            provider={provider}
            integration={findIntegration(provider)}
            error={oauthError?.provider === provider ? oauthError.message : undefined}
            connectDisabled={provider === "apple_calendar" && appleCalendars !== null}
            onConnect={getConnectHandler(provider)}
            onDisconnect={disconnectIntegration}
            onSync={syncIntegration}
          />
        ))}

        {/* Apple Calendar picker */}
        {appleCalendars && !findIntegration("apple_calendar") && (
          <div className="px-[18px] py-3.5 border-t border-surface-3/40">
            <div className="text-xs text-text-dim mb-2">
              Select which calendars to sync from Calendar.app:
            </div>
            <div className="flex flex-col gap-1.5 max-h-[200px] overflow-y-auto mb-3">
              {appleCalendars.map((name) => (
                <label
                  key={name}
                  className="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer hover:text-text-primary"
                >
                  <input
                    type="checkbox"
                    checked={appleSelected.has(name)}
                    onChange={() => {
                      setAppleSelected((prev) => {
                        const next = new Set(prev);
                        if (next.has(name)) next.delete(name);
                        else next.add(name);
                        return next;
                      });
                    }}
                    className="accent-accent"
                  />
                  {name}
                </label>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={connectAppleCalendar}
                disabled={appleLoading || appleSelected.size === 0}
                className="px-3.5 py-1.5 text-xs rounded-md bg-accent-muted text-accent border border-accent/20 transition-colors hover:bg-accent/20 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {appleLoading ? "Connecting..." : `Connect ${appleSelected.size} calendar${appleSelected.size !== 1 ? "s" : ""}`}
              </button>
              <button
                onClick={() => setAppleCalendars(null)}
                className="px-3.5 py-1.5 text-xs rounded-md bg-white/[0.04] text-text-secondary border border-surface-3 transition-colors hover:bg-white/[0.08]"
              >
                Cancel
              </button>
            </div>
            {appleError && (
              <div className="text-xs text-red-400 mt-1.5">{appleError}</div>
            )}
          </div>
        )}

        {/* Granola cache path configuration */}
        {!findIntegration("granola") && (
          <div className="px-[18px] py-3.5 border-t border-surface-3/40">
            <div className="text-xs text-text-dim mb-2">
              Granola reads meeting notes from a local cache file.
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={granolaPath}
                onChange={(e) => setGranolaPath(e.target.value)}
                placeholder="Path to Granola cache"
                className="flex-1 px-2.5 py-[7px] text-[13px] bg-surface-0 border border-surface-3 rounded-md text-text-secondary outline-none transition-colors focus:border-accent font-mono placeholder:text-text-ghost"
              />
            </div>
            {granolaError && (
              <div className="text-xs text-red-400 mt-1.5">{granolaError}</div>
            )}
          </div>
        )}
      </SettingsSection>

      {/* ── Preferences ───────────────────────────────────────── */}
      <SettingsSection title="Morning Briefing">
        {/* Timezone */}
        <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-surface-3/40">
          <div className="flex-1">
            <div className="text-sm text-text-secondary">Timezone</div>
            <div className="text-xs text-text-dim mt-0.5">
              All times are based on this timezone
            </div>
          </div>
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="px-2.5 py-[7px] text-[13px] bg-surface-0 border border-surface-3 rounded-md text-text-secondary outline-none transition-colors focus:border-accent w-[200px]"
          >
            <option value="">Select timezone</option>
            {TIMEZONES.map((tz) => (
              <option key={tz.value} value={tz.value}>
                {tz.label}
              </option>
            ))}
          </select>
        </div>

        {/* Briefing time */}
        <div className="flex items-center justify-between px-[18px] py-3.5 border-b border-surface-3/40">
          <div className="flex-1">
            <div className="text-sm text-text-secondary">Briefing time</div>
            <div className="text-xs text-text-dim mt-0.5">
              When your morning briefing is generated
            </div>
          </div>
          <input
            type="time"
            value={wakeTime}
            onChange={(e) => setWakeTime(e.target.value)}
            className="px-2.5 py-[7px] text-[13px] bg-surface-0 border border-surface-3 rounded-md text-text-secondary outline-none transition-colors focus:border-accent w-[120px]"
          />
        </div>

        {/* Save button row */}
        <div className="flex items-center justify-end gap-3 px-[18px] py-3.5">
          {prefsError && (
            <span className="text-xs text-red-400">{prefsError}</span>
          )}
          {prefsSaved && (
            <span className="text-xs text-status-healthy">Saved</span>
          )}
          <button
            onClick={savePreferences}
            disabled={prefsSaving}
            className="px-4 py-1.5 text-xs font-medium rounded-md bg-accent text-white transition-colors hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {prefsSaving ? "Saving..." : "Save"}
          </button>
        </div>
      </SettingsSection>

      {/* ── Desktop App (Tauri only) ────────────────────────── */}
      {isTauri && (
        <SettingsSection title="Desktop App">
          <div className="flex items-center justify-between px-[18px] py-3.5">
            <div className="flex-1">
              <div className="text-sm text-text-secondary">
                Launch on login
              </div>
              <div className="text-xs text-text-dim mt-0.5">
                Start Jarvis automatically when you log in to your Mac
              </div>
            </div>
            <button
              onClick={toggleAutostart}
              disabled={autostartLoading}
              className={`relative w-10 h-[22px] rounded-full transition-colors ${
                autostart ? "bg-accent" : "bg-surface-3"
              } disabled:opacity-50`}
            >
              <div
                className={`absolute top-[3px] w-4 h-4 rounded-full bg-white shadow transition-transform ${
                  autostart ? "left-[22px]" : "left-[3px]"
                }`}
              />
            </button>
          </div>
        </SettingsSection>
      )}

      {/* ── Danger Zone ───────────────────────────────────────── */}
      <SettingsSection title="Danger Zone" danger>
        <div className="px-[18px] py-4">
          <div className="text-sm text-text-secondary mb-1">
            Revoke all integrations
          </div>
          <div className="text-xs text-text-dim mb-3">
            Immediately disconnect all integrations and revoke their OAuth
            tokens. This cannot be undone.
          </div>

          {panicDone && (
            <div className="text-xs text-status-healthy mb-3">
              All integrations have been revoked.
            </div>
          )}
          {panicError && (
            <div className="text-xs text-red-400 mb-3">{panicError}</div>
          )}

          <div className="flex items-center gap-3">
            <input
              type="text"
              value={panicInput}
              onChange={(e) => setPanicInput(e.target.value)}
              placeholder='Type "REVOKE" to confirm'
              className="px-2.5 py-[7px] text-[13px] bg-surface-0 border border-surface-3 rounded-md text-text-secondary outline-none transition-colors focus:border-red-500/50 w-[200px] placeholder:text-text-ghost"
            />
            <button
              onClick={handlePanic}
              disabled={panicInput !== "REVOKE" || panicking}
              className="px-3.5 py-1.5 text-xs rounded-md bg-red-500/8 text-red-500 border border-red-500/15 transition-colors hover:bg-red-500/15 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              {panicking ? "Revoking..." : "Revoke All"}
            </button>
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
