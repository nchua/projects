"use client";

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import { api } from "./api";
import type { UserResponse, TokenResponse } from "./types";

interface AuthState {
  user: UserResponse | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("holocron_token");
    if (!token) {
      setIsLoading(false);
      return;
    }
    api
      .get<UserResponse>("/auth/me")
      .then(setUser)
      .catch(() => localStorage.removeItem("holocron_token"))
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.post<TokenResponse>("/auth/login", { email, password });
    localStorage.setItem("holocron_token", data.access_token);
    const me = await api.get<UserResponse>("/auth/me");
    setUser(me);
  }, []);

  const register = useCallback(async (email: string, password: string, displayName?: string) => {
    const data = await api.post<TokenResponse>("/auth/register", {
      email,
      password,
      display_name: displayName,
    });
    localStorage.setItem("holocron_token", data.access_token);
    const me = await api.get<UserResponse>("/auth/me");
    setUser(me);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("holocron_token");
    setUser(null);
    window.location.href = "/login";
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
