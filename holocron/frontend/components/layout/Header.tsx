"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/review", label: "Review" },
  { href: "/inbox", label: "Inbox" },
  { href: "/mastery", label: "Mastery" },
];

export default function Header() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  if (!user) return null;

  return (
    <header className="border-b border-border px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-8">
        <Link href="/" className="font-mono text-amber font-bold tracking-widest text-lg">
          HOLOCRON
        </Link>
        <nav className="flex gap-6">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`text-sm transition-colors ${
                pathname === item.href
                  ? "text-amber"
                  : "text-muted hover:text-foreground"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
      <button
        onClick={logout}
        className="text-sm text-muted hover:text-foreground transition-colors"
      >
        Sign out
      </button>
    </header>
  );
}
