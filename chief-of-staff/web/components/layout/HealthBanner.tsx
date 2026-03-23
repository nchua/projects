"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import type { IntegrationHealthResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";

const STATUS_DOT_CLASSES: Record<string, string> = {
  healthy: "bg-status-healthy",
  degraded: "bg-status-degraded animate-[pulse-warn_2s_infinite]",
  failed: "bg-status-failed animate-[pulse-warn_1.5s_infinite]",
  disabled: "bg-status-disabled",
};

function formatSyncTime(iso: string | null): string {
  if (!iso) return "never";
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true });
  } catch {
    return "unknown";
  }
}

export function HealthBanner() {
  const { data: integrations } = useSWR<IntegrationHealthResponse[]>(
    "/integrations/health",
    () => api.integrations.health(),
    { refreshInterval: 60_000 },
  );

  // Only show when at least one integration is not healthy
  const hasDegraded = integrations?.some(
    (i) => i.status !== "healthy",
  );

  if (!integrations || integrations.length === 0) return null;
  if (!hasDegraded) return null;

  return (
    <div className="flex items-center gap-5 px-8 py-2.5 bg-surface-0 border-b border-surface-3 text-xs">
      {integrations.map((integration) => (
        <div key={integration.provider} className="flex items-center gap-1.5">
          <span
            className={cn(
              "w-[7px] h-[7px] rounded-full",
              STATUS_DOT_CLASSES[integration.status] ?? "bg-status-disabled",
            )}
          />
          <span className="text-text-tertiary capitalize">
            {integration.provider.replace("_", " ")}
          </span>
          <span className="text-text-dim">
            {formatSyncTime(integration.last_synced_at)}
          </span>
        </div>
      ))}
    </div>
  );
}
