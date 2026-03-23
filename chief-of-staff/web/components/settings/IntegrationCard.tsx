"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";
import type {
  IntegrationProvider,
  IntegrationResponse,
  IntegrationStatusValue,
} from "@/lib/types";

// ── Provider display config ─────────────────────────────────────

interface ProviderConfig {
  label: string;
  icon: string;
  iconBg: string;
  iconColor: string;
}

const PROVIDER_CONFIG: Record<string, ProviderConfig> = {
  google_calendar: {
    label: "Google Calendar",
    icon: "\uD83D\uDCC5",
    iconBg: "rgba(66,133,244,0.12)",
    iconColor: "#4285f4",
  },
  gmail: {
    label: "Gmail",
    icon: "\u2709",
    iconBg: "rgba(234,67,53,0.12)",
    iconColor: "#ea4335",
  },
  github: {
    label: "GitHub",
    icon: "\uD83D\uDEE0",
    iconBg: "rgba(139,92,246,0.12)",
    iconColor: "#a78bfa",
  },
  slack: {
    label: "Slack",
    icon: "\uD83D\uDCAC",
    iconBg: "rgba(74,21,75,0.12)",
    iconColor: "#e01e5a",
  },
  granola: {
    label: "Granola",
    icon: "\uD83C\uDF99",
    iconBg: "rgba(245,158,11,0.12)",
    iconColor: "#f59e0b",
  },
  apple_calendar: {
    label: "Apple Calendar",
    icon: "\uD83C\uDF4E",
    iconBg: "rgba(255,59,48,0.12)",
    iconColor: "#ff3b30",
  },
};

const STATUS_DOT: Record<IntegrationStatusValue, string> = {
  healthy: "bg-status-healthy",
  degraded: "bg-status-degraded animate-[pulse-warn_2s_infinite]",
  failed: "bg-status-failed animate-[pulse-warn_1.5s_infinite]",
  disabled: "bg-status-disabled",
};

const STATUS_LABEL: Record<IntegrationStatusValue, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  failed: "Failed",
  disabled: "Not connected",
};

// ── Component ───────────────────────────────────────────────────

interface IntegrationCardProps {
  provider: IntegrationProvider;
  integration: IntegrationResponse | null;
  error?: string | null;
  onConnect: () => Promise<void>;
  onDisconnect: (id: string) => Promise<void>;
}

function formatSyncTime(iso: string | null): string {
  if (!iso) return "never";
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true });
  } catch {
    return "unknown";
  }
}

export function IntegrationCard({
  provider,
  integration,
  error: externalError,
  onConnect,
  onDisconnect,
}: IntegrationCardProps) {
  const [loading, setLoading] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const error = externalError ?? localError;

  const config = PROVIDER_CONFIG[provider] ?? {
    label: provider,
    icon: "\u2022",
    iconBg: "rgba(255,255,255,0.06)",
    iconColor: "#fff",
  };

  const isConnected = integration !== null && integration.is_active;
  const status: IntegrationStatusValue = integration?.status ?? "disabled";

  async function handleConnect() {
    setLoading(true);
    setLocalError(null);
    try {
      await onConnect();
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : "Connection failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleDisconnect() {
    if (!integration) return;
    if (!showConfirm) {
      setShowConfirm(true);
      return;
    }
    setLoading(true);
    setShowConfirm(false);
    try {
      await onDisconnect(integration.id);
    } catch {
      // Parent handles errors
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center gap-3.5 px-[18px] py-4 border-b border-surface-3/40 last:border-b-0">
      {/* Icon */}
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center text-lg flex-shrink-0"
        style={{ background: config.iconBg, color: config.iconColor }}
      >
        {config.icon}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="text-sm text-text-secondary font-medium">
          {config.label}
        </div>
        <div className="text-xs text-text-dim mt-0.5 flex items-center gap-1.5">
          <span
            className={cn("w-[7px] h-[7px] rounded-full flex-shrink-0", STATUS_DOT[status])}
          />
          <span className={status === "degraded" ? "text-status-degraded" : status === "failed" ? "text-status-failed" : ""}>
            {STATUS_LABEL[status]}
          </span>
          {isConnected && (
            <>
              <span className="text-text-ghost">&middot;</span>
              <span>Last synced {formatSyncTime(integration.last_synced_at)}</span>
            </>
          )}
          {integration?.scopes && (
            <span className="text-[10px] text-text-dim bg-white/[0.03] border border-surface-3 rounded px-1.5 py-px font-mono">
              {integration.scopes}
            </span>
          )}
        </div>
        {error && (
          <div className="text-xs text-red-400 mt-1">{error}</div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {loading && (
          <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-text-dim/30 border-t-text-dim rounded-full" />
        )}

        {!isConnected && (
          <button
            onClick={handleConnect}
            disabled={loading}
            className="px-3.5 py-1.5 text-xs rounded-md bg-accent-muted text-accent border border-accent/20 transition-colors hover:bg-accent/20 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Connect
          </button>
        )}

        {isConnected && status === "degraded" && (
          <button
            onClick={handleConnect}
            disabled={loading}
            className="px-3.5 py-1.5 text-xs rounded-md bg-status-degraded/10 text-status-degraded border border-status-degraded/20 transition-colors hover:bg-status-degraded/[0.18] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Reconnect
          </button>
        )}

        {isConnected && (
          <button
            onClick={handleDisconnect}
            disabled={loading}
            className={cn(
              "px-3.5 py-1.5 text-xs rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
              showConfirm
                ? "bg-red-500/20 text-red-400 border border-red-500/30"
                : "bg-red-500/8 text-red-500 border border-red-500/15 hover:bg-red-500/15",
            )}
          >
            {showConfirm ? "Confirm?" : "Disconnect"}
          </button>
        )}
      </div>
    </div>
  );
}
