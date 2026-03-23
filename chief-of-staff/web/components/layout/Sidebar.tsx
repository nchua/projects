"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/", icon: "\u25A0" },
  { label: "Settings", href: "/settings", icon: "\u2699" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-[220px] min-w-[220px] bg-surface-0 border-r border-surface-3 flex flex-col py-6 fixed top-0 left-0 bottom-0 z-50">
      {/* Brand */}
      <div className="px-5 pb-7 text-sm font-semibold text-text-tertiary tracking-widest uppercase">
        Jarvis
      </div>

      {/* Nav */}
      <nav className="flex-1">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 px-5 py-2.5 text-sm border-l-[3px] border-transparent transition-all",
                isActive
                  ? "text-text-primary border-l-accent bg-accent-subtle"
                  : "text-text-tertiary hover:text-text-secondary hover:bg-white/[0.03]",
              )}
            >
              <span className="w-[18px] text-center text-[15px]">
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 pt-4 border-t border-surface-3 text-xs text-text-dim">
        v0.1.0
      </div>
    </aside>
  );
}
