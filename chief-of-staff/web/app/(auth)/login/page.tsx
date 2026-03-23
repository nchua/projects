"use client";

import { FormEvent, useState } from "react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

type AuthTab = "login" | "register";

export default function LoginPage() {
  const { login, register } = useAuth();
  const [tab, setTab] = useState<AuthTab>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (tab === "register" && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      if (tab === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="w-full max-w-[400px] px-6">
      {/* Brand */}
      <div className="text-center mb-10">
        <div className="w-12 h-12 mx-auto mb-4 bg-gradient-to-br from-blue-700 to-blue-500 rounded-xl flex items-center justify-center text-[22px] text-white">
          &#9632;
        </div>
        <div className="text-xl font-semibold text-text-primary tracking-tight">
          Jarvis
        </div>
        <div className="text-[13px] text-text-dim mt-1">
          At your service
        </div>
      </div>

      {/* Card */}
      <div className="bg-surface-2 border border-surface-3 rounded-xl p-7">
        {/* Tabs */}
        <div className="flex gap-0.5 bg-surface-0 border border-surface-3 rounded-lg p-[3px] mb-6">
          <button
            type="button"
            className={cn(
              "flex-1 py-2 text-[13px] rounded-md transition-all text-center",
              tab === "login"
                ? "bg-surface-2 text-text-primary shadow-sm"
                : "text-text-muted hover:text-text-tertiary",
            )}
            onClick={() => {
              setTab("login");
              setError(null);
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            className={cn(
              "flex-1 py-2 text-[13px] rounded-md transition-all text-center",
              tab === "register"
                ? "bg-surface-2 text-text-primary shadow-sm"
                : "text-text-muted hover:text-text-tertiary",
            )}
            onClick={() => {
              setTab("register");
              setError(null);
            }}
          >
            Create Account
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="px-3 py-2.5 text-xs text-red-400 bg-red-500/8 border border-red-500/15 rounded-md mb-4">
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="mb-[18px]">
            <label className="block text-xs text-text-muted mb-1.5 uppercase tracking-wider font-medium">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete={tab === "login" ? "email" : "email"}
              autoFocus
              className="w-full px-3 py-2.5 text-sm bg-surface-0 border border-surface-3 rounded-[7px] text-text-secondary outline-none transition-colors focus:border-accent placeholder:text-text-ghost"
            />
          </div>

          <div className="mb-[18px]">
            <label className="block text-xs text-text-muted mb-1.5 uppercase tracking-wider font-medium">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={
                tab === "login" ? "Enter your password" : "Create a password"
              }
              required
              autoComplete={
                tab === "login" ? "current-password" : "new-password"
              }
              className="w-full px-3 py-2.5 text-sm bg-surface-0 border border-surface-3 rounded-[7px] text-text-secondary outline-none transition-colors focus:border-accent placeholder:text-text-ghost"
            />
          </div>

          {tab === "register" && (
            <div className="mb-[18px]">
              <label className="block text-xs text-text-muted mb-1.5 uppercase tracking-wider font-medium">
                Confirm Password
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm your password"
                required
                autoComplete="new-password"
                className="w-full px-3 py-2.5 text-sm bg-surface-0 border border-surface-3 rounded-[7px] text-text-secondary outline-none transition-colors focus:border-accent placeholder:text-text-ghost"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-[11px] text-sm font-medium text-white bg-blue-700 rounded-[7px] transition-colors hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed mt-1"
          >
            {submitting
              ? tab === "login"
                ? "Signing in..."
                : "Creating account..."
              : tab === "login"
                ? "Sign In"
                : "Create Account"}
          </button>
        </form>
      </div>

      {/* Footer */}
      <div className="text-center mt-5 text-xs text-text-ghost">
        By signing in, you agree to our Terms of Service and Privacy Policy.
      </div>
    </div>
  );
}
