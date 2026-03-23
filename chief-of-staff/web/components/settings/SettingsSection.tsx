"use client";

import type { ReactNode } from "react";

interface SettingsSectionProps {
  title: string;
  description?: string;
  children: ReactNode;
  danger?: boolean;
}

export function SettingsSection({
  title,
  description,
  children,
  danger,
}: SettingsSectionProps) {
  return (
    <div className="mb-9">
      <div className="mb-3 pl-1">
        <h2 className="text-xs font-semibold uppercase tracking-[0.06em] text-text-muted">
          {title}
        </h2>
        {description && (
          <p className="text-xs text-text-dim mt-0.5">{description}</p>
        )}
      </div>
      <div
        className={
          danger
            ? "bg-surface-2 border border-red-500/20 rounded-[10px] overflow-hidden"
            : "bg-surface-2 border border-surface-3 rounded-[10px] overflow-hidden"
        }
      >
        {children}
      </div>
    </div>
  );
}
