import type {
  Token,
  UserResponse,
  UserRegisterPayload,
  UserLoginPayload,
  UserUpdatePayload,
  RecurringTaskResponse,
  RecurringTaskCreatePayload,
  RecurringTaskUpdatePayload,
  TaskCompletionResponse,
  ActionItemResponse,
  ActionItemCreatePayload,
  ActionItemStatus,
  ActionItemSource,
  ActionItemPriority,
  DismissReason,
  BriefingResponse,
  IntegrationResponse,
  IntegrationHealthResponse,
  TodayTasksResponse,
  AllTasksResponse,
  DismissalStats,
  MemoryFactResponse,
  MemoryFactCreatePayload,
} from "./types";

// ── Base URL ─────────────────────────────────────────────────────

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// ── Error class ──────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ── Token refresh mutex ──────────────────────────────────────────
// Only one refresh request should be in-flight at a time.

let refreshPromise: Promise<boolean> | null = null;

async function tryRefreshToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) return false;

    try {
      const response = await fetch(`${API_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) return false;
      const tokens: Token = await response.json();
      localStorage.setItem("access_token", tokens.access_token);
      localStorage.setItem("refresh_token", tokens.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

// ── Core fetch wrapper ───────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const accessToken = localStorage.getItem("access_token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  let response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  // Auto-refresh on 401
  if (response.status === 401 && accessToken) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      headers["Authorization"] = `Bearer ${localStorage.getItem("access_token")}`;
      response = await fetch(`${API_URL}${path}`, { ...options, headers });
    } else {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      window.location.href = "/login";
      throw new ApiError(401, "Session expired");
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(response.status, body.detail || "Request failed");
  }

  return response.json();
}

// ── API namespace ────────────────────────────────────────────────

export const api = {
  // ── Auth ──────────────────────────────────────────────────────
  auth: {
    register: (data: UserRegisterPayload) =>
      apiFetch<UserResponse>("/auth/register", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    login: (data: UserLoginPayload) =>
      apiFetch<Token>("/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    refresh: (refreshToken: string) =>
      apiFetch<Token>("/auth/refresh", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken }),
      }),

    me: () => apiFetch<UserResponse>("/auth/me"),

    updateMe: (data: UserUpdatePayload) =>
      apiFetch<UserResponse>("/auth/me", {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
  },

  // ── Recurring Tasks ──────────────────────────────────────────
  recurringTasks: {
    list: (includeArchived = false) =>
      apiFetch<RecurringTaskResponse[]>(
        `/tasks/recurring?include_archived=${includeArchived}`,
      ),

    create: (data: RecurringTaskCreatePayload) =>
      apiFetch<RecurringTaskResponse>("/tasks/recurring", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    update: (taskId: string, data: RecurringTaskUpdatePayload) =>
      apiFetch<RecurringTaskResponse>(`/tasks/recurring/${taskId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    archive: (taskId: string) =>
      apiFetch<void>(`/tasks/recurring/${taskId}`, {
        method: "DELETE",
      }),

    complete: (taskId: string) =>
      apiFetch<TaskCompletionResponse>(
        `/tasks/recurring/${taskId}/complete`,
        { method: "POST" },
      ),

    skip: (taskId: string, notes?: string) =>
      apiFetch<TaskCompletionResponse>(
        `/tasks/recurring/${taskId}/skip${notes ? `?notes=${encodeURIComponent(notes)}` : ""}`,
        { method: "POST" },
      ),

    reorder: (taskIds: string[]) =>
      apiFetch<void>("/tasks/recurring/reorder", {
        method: "PUT",
        body: JSON.stringify({ task_ids: taskIds }),
      }),
  },

  // ── Action Items ─────────────────────────────────────────────
  actionItems: {
    list: (params?: {
      status?: ActionItemStatus;
      source?: ActionItemSource;
      priority?: ActionItemPriority;
      limit?: number;
      offset?: number;
    }) => {
      const searchParams = new URLSearchParams();
      if (params?.status) searchParams.set("status", params.status);
      if (params?.source) searchParams.set("source", params.source);
      if (params?.priority) searchParams.set("priority", params.priority);
      if (params?.limit) searchParams.set("limit", String(params.limit));
      if (params?.offset) searchParams.set("offset", String(params.offset));
      const qs = searchParams.toString();
      return apiFetch<ActionItemResponse[]>(
        `/action-items${qs ? `?${qs}` : ""}`,
      );
    },

    get: (itemId: string) =>
      apiFetch<ActionItemResponse>(`/action-items/${itemId}`),

    create: (data: ActionItemCreatePayload) =>
      apiFetch<ActionItemResponse>("/action-items", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    acknowledge: (itemId: string) =>
      apiFetch<ActionItemResponse>(
        `/action-items/${itemId}/acknowledge`,
        { method: "POST" },
      ),

    action: (itemId: string) =>
      apiFetch<ActionItemResponse>(`/action-items/${itemId}/action`, {
        method: "POST",
      }),

    dismiss: (itemId: string, reason: DismissReason) =>
      apiFetch<ActionItemResponse>(`/action-items/${itemId}/dismiss`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      }),

    snooze: (itemId: string, snoozedUntil: string) =>
      apiFetch<ActionItemResponse>(`/action-items/${itemId}/snooze`, {
        method: "POST",
        body: JSON.stringify({ snoozed_until: snoozedUntil }),
      }),

    dismissalStats: () =>
      apiFetch<DismissalStats>("/action-items/stats/dismissals"),
  },

  // ── Briefings ────────────────────────────────────────────────
  briefings: {
    today: () => apiFetch<BriefingResponse>("/briefings/today"),

    byDate: (date: string) =>
      apiFetch<BriefingResponse>(`/briefings/${date}`),

    markViewed: () =>
      apiFetch<BriefingResponse>("/briefings/today/viewed", {
        method: "POST",
      }),

    preview: () =>
      apiFetch<BriefingResponse>("/briefings/preview", {
        method: "POST",
      }),
  },

  // ── Integrations ─────────────────────────────────────────────
  integrations: {
    list: () => apiFetch<IntegrationResponse[]>("/integrations"),

    health: () =>
      apiFetch<IntegrationHealthResponse[]>("/integrations/health"),

    googleAuthorize: (redirectUri: string) =>
      apiFetch<{ authorization_url: string; state: string }>(
        `/integrations/google/authorize?redirect_uri=${encodeURIComponent(redirectUri)}`,
        { method: "POST" },
      ),

    googleCallback: (code: string, redirectUri: string, state: string, provider: string = "google_calendar") =>
      apiFetch<IntegrationResponse>("/integrations/google/callback", {
        method: "POST",
        body: JSON.stringify({
          provider,
          code,
          redirect_uri: redirectUri,
          state,
        }),
      }),

    githubAuthorize: (redirectUri: string) =>
      apiFetch<{ authorization_url: string; state: string }>(
        `/integrations/github/authorize?redirect_uri=${encodeURIComponent(redirectUri)}`,
        { method: "POST" },
      ),

    githubCallback: (code: string, redirectUri: string, state: string) =>
      apiFetch<IntegrationResponse>("/integrations/github/callback", {
        method: "POST",
        body: JSON.stringify({
          provider: "github",
          code,
          redirect_uri: redirectUri,
          state,
        }),
      }),

    slackAuthorize: (redirectUri: string) =>
      apiFetch<{ authorization_url: string; state: string }>(
        `/integrations/slack/authorize?redirect_uri=${encodeURIComponent(redirectUri)}`,
        { method: "POST" },
      ),

    slackCallback: (code: string, redirectUri: string, state: string) =>
      apiFetch<IntegrationResponse>("/integrations/slack/callback", {
        method: "POST",
        body: JSON.stringify({
          provider: "slack",
          code,
          redirect_uri: redirectUri,
          state,
        }),
      }),

    granolaConfigure: (cachePath: string) =>
      apiFetch<IntegrationResponse>(
        `/integrations/granola/configure?cache_path=${encodeURIComponent(cachePath)}`,
        { method: "POST" },
      ),

    appleCalendarListCalendars: () =>
      apiFetch<{ calendars: string[] }>(
        "/integrations/apple_calendar/calendars",
      ),

    appleCalendarConfigure: (calendars?: string[]) =>
      apiFetch<IntegrationResponse>(
        "/integrations/apple_calendar/configure",
        {
          method: "POST",
          body: JSON.stringify({ calendars: calendars ?? null }),
        },
      ),

    syncAll: () =>
      apiFetch<{ synced: Record<string, { status: string; documents_fetched?: number; error?: string }> }>(
        "/integrations/sync-all",
        { method: "POST" },
      ),

    disconnect: (integrationId: string) =>
      apiFetch<void>(`/integrations/${integrationId}`, {
        method: "DELETE",
      }),

    test: (integrationId: string) =>
      apiFetch<IntegrationHealthResponse>(
        `/integrations/${integrationId}/test`,
        { method: "POST" },
      ),

    sync: (integrationId: string) =>
      apiFetch<IntegrationResponse>(
        `/integrations/${integrationId}/sync`,
        { method: "POST" },
      ),

    panicRevokeAll: () =>
      apiFetch<void>("/integrations/panic", {
        method: "POST",
      }),
  },

  // ── Memory ─────────────────────────────────────────────────────
  memory: {
    list: (activeOnly = true) =>
      apiFetch<MemoryFactResponse[]>(
        `/memory?active_only=${activeOnly}`,
      ),

    create: (data: MemoryFactCreatePayload) =>
      apiFetch<MemoryFactResponse>("/memory", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    delete: (factId: string) =>
      apiFetch<void>(`/memory/${factId}`, {
        method: "DELETE",
      }),
  },

  // ── Unified Tasks ────────────────────────────────────────────
  tasks: {
    today: () => apiFetch<TodayTasksResponse>("/tasks/today"),

    all: (taskType?: "recurring" | "action_item") => {
      const qs = taskType ? `?task_type=${taskType}` : "";
      return apiFetch<AllTasksResponse>(`/tasks/all${qs}`);
    },
  },
};
