# Chief of Staff -- Frontend Engineering Spec

> Generated from backend schemas, API endpoints, and designer mockups.
> Target: executable by a coding agent without follow-up questions.

---

## 1. Project Setup

### 1.1 Create Project

```bash
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir \
  --import-alias "@/*" \
  --no-turbopack
```

### 1.2 Required Packages

```bash
# UI framework
npx shadcn@latest init  # dark theme, zinc palette, CSS variables
npx shadcn@latest add button input label card tabs dialog badge toggle separator dropdown-menu sheet toast skeleton

# Data fetching + state
npm install swr

# Utilities
npm install clsx tailwind-merge
npm install date-fns         # date formatting
npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities  # drag-and-drop reorder
```

No other packages. No Redux, no Zustand, no React Query -- SWR handles the cache/revalidation pattern the app needs.

### 1.3 Environment Variables

Create `frontend/.env.local` (gitignored):

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

Production will point to the Railway backend.

### 1.4 Directory Structure

```
frontend/src/
├── app/
│   ├── layout.tsx                    # Root layout (AuthProvider wraps everything)
│   ├── (auth)/
│   │   ├── layout.tsx                # Centered layout, no sidebar
│   │   ├── login/page.tsx            # Sign in / register
│   │   └── onboarding/page.tsx       # 4-step setup wizard
│   ├── (app)/
│   │   ├── layout.tsx                # Sidebar + HealthBanner + main wrapper
│   │   ├── page.tsx                  # Dashboard (default route "/")
│   │   ├── tasks/page.tsx            # Task management
│   │   └── settings/page.tsx         # Integrations + preferences
│   └── globals.css                   # Tailwind base + custom dark theme tokens
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   └── HealthBanner.tsx
│   ├── dashboard/
│   │   ├── NonNegotiablesCard.tsx
│   │   ├── ActionItemsCard.tsx
│   │   ├── CalendarCard.tsx
│   │   └── InsightsCard.tsx
│   ├── tasks/
│   │   ├── SegmentTabs.tsx
│   │   ├── RecurringTaskRow.tsx
│   │   ├── ActionItemRow.tsx
│   │   ├── ReminderRow.tsx
│   │   └── AddTaskModal.tsx
│   ├── settings/
│   │   ├── IntegrationRow.tsx
│   │   ├── SettingRow.tsx
│   │   └── ToggleSwitch.tsx
│   └── shared/
│       ├── ShortcutOverlay.tsx
│       ├── StreakBadge.tsx
│       ├── PriorityDot.tsx
│       ├── ConfidenceTag.tsx
│       └── CadenceTag.tsx
├── hooks/
│   ├── useKeyboardShortcuts.ts
│   └── useActionItemTriage.ts
├── lib/
│   ├── api.ts                       # Fetch wrapper + all API functions
│   ├── auth.ts                      # AuthContext, useAuth, ProtectedRoute
│   ├── types.ts                     # All TypeScript interfaces
│   └── utils.ts                     # cn(), date helpers
└── styles/
    └── theme.ts                     # Color tokens matching mockup palette
```

### 1.5 Tailwind Theme Extension

Add to `tailwind.config.ts` to match the mockup dark palette:

```ts
theme: {
  extend: {
    colors: {
      // Surface hierarchy
      surface: {
        0: '#0a0c10',   // sidebar, deepest
        1: '#0f1117',   // body bg
        2: '#151922',   // cards
        3: '#1e2330',   // borders, subtle bg
      },
      // Text hierarchy
      text: {
        primary: '#f9fafb',
        secondary: '#d1d5db',
        tertiary: '#9ca3af',
        muted: '#6b7280',
        dim: '#4b5563',
        ghost: '#374151',
      },
      // Accent
      accent: {
        DEFAULT: '#3b82f6',
        hover: '#2563eb',
        subtle: 'rgba(96,165,250,0.06)',
        muted: 'rgba(96,165,250,0.12)',
      },
      // Status
      status: {
        healthy: '#22c55e',
        degraded: '#f59e0b',
        failed: '#ef4444',
        disabled: '#374151',
      },
    },
    fontFamily: {
      mono: ['SF Mono', 'Cascadia Code', 'Fira Code', 'monospace'],
    },
  },
},
```

---

## 2. TypeScript Interfaces (`lib/types.ts`)

These mirror the backend Pydantic schemas exactly as serialized over JSON.

```ts
// ── Enums (match backend string values) ──────────────────────────

export type Cadence = 'daily' | 'weekly' | 'monthly' | 'custom';
export type MissedBehavior = 'roll_forward' | 'mark_missed';
export type TaskPriority = 'non_negotiable' | 'flexible';

export type ActionItemSource = 'gmail' | 'github' | 'slack' | 'notion' | 'discord' | 'manual';
export type ActionItemPriority = 'high' | 'medium' | 'low';
export type ActionItemStatus = 'new' | 'acknowledged' | 'actioned' | 'dismissed';
export type DismissReason = 'not_action_item' | 'already_done' | 'not_relevant';

export type TriggerType = 'time' | 'location' | 'context' | 'follow_up';
export type ReminderStatus = 'pending' | 'completed' | 'dismissed';

export type IntegrationProvider =
  | 'google_calendar' | 'gmail' | 'github'
  | 'slack' | 'notion' | 'discord' | 'apple_calendar';
export type IntegrationStatusValue = 'healthy' | 'degraded' | 'failed' | 'disabled';

// ── Auth ─────────────────────────────────────────────────────────

export interface Token {
  access_token: string;
  refresh_token: string;
  token_type: string;  // always "bearer"
}

export interface UserResponse {
  id: string;
  email: string;
  timezone: string | null;
  wake_time: string | null;   // "HH:MM" or null
  sleep_time: string | null;  // "HH:MM" or null
  created_at: string;         // ISO 8601 datetime
  updated_at: string;
}

export interface UserRegisterPayload {
  email: string;
  password: string;  // min 8, max 100, must have upper+lower+digit
}

export interface UserLoginPayload {
  email: string;
  password: string;
}

export interface UserUpdatePayload {
  timezone?: string;
  wake_time?: string;   // "HH:MM"
  sleep_time?: string;  // "HH:MM"
}

// ── Recurring Tasks ──────────────────────────────────────────────

export interface RecurringTaskResponse {
  id: string;
  title: string;
  description: string | null;
  cadence: Cadence;
  cron_expression: string | null;
  start_time: string | null;
  end_time: string | null;
  timezone: string | null;
  missed_behavior: MissedBehavior;
  priority: TaskPriority;
  streak_count: number;
  last_completed_at: string | null;  // ISO datetime
  sort_order: number;
  is_archived: boolean;
  created_at: string;
}

export interface RecurringTaskCreatePayload {
  title: string;
  description?: string;
  cadence: Cadence;
  cron_expression?: string;
  start_time?: string;
  end_time?: string;
  timezone?: string;
  missed_behavior?: MissedBehavior;
  priority?: TaskPriority;
  sort_order?: number;
}

export interface RecurringTaskUpdatePayload {
  title?: string;
  description?: string;
  cadence?: Cadence;
  cron_expression?: string;
  start_time?: string;
  end_time?: string;
  timezone?: string;
  missed_behavior?: MissedBehavior;
  priority?: TaskPriority;
  sort_order?: number;
  is_archived?: boolean;
}

export interface TaskCompletionResponse {
  id: string;
  recurring_task_id: string;
  date: string;           // "YYYY-MM-DD"
  completed_at: string | null;
  skipped: boolean;
  notes: string | null;
}

// ── Action Items ─────────────────────────────────────────────────

export interface ActionItemResponse {
  id: string;
  source: ActionItemSource;
  source_id: string | null;
  source_url: string | null;
  title: string;
  description: string | null;
  extracted_deadline: string | null;  // ISO datetime
  confidence_score: number | null;
  priority: ActionItemPriority;
  status: ActionItemStatus;
  dismiss_reason: DismissReason | null;
  snoozed_until: string | null;
  linked_task_id: string | null;
  created_at: string;
  actioned_at: string | null;
}

export interface ActionItemCreatePayload {
  source?: ActionItemSource;
  source_id?: string;
  source_url?: string;
  title: string;
  description?: string;
  extracted_deadline?: string;
  confidence_score?: number;
  priority?: ActionItemPriority;
  dedup_hash?: string;
}

// ── Reminders ────────────────────────────────────────────────────

export interface ReminderResponse {
  id: string;
  title: string;
  description: string | null;
  trigger_type: TriggerType;
  trigger_config: Record<string, unknown> | null;
  source_action_item_id: string | null;
  status: ReminderStatus;
  created_at: string;
  completed_at: string | null;
}

export interface ReminderCreatePayload {
  title: string;
  description?: string;
  trigger_type: TriggerType;
  trigger_config?: Record<string, unknown>;
  source_action_item_id?: string;
}

export interface ReminderUpdatePayload {
  title?: string;
  description?: string;
  trigger_type?: TriggerType;
  trigger_config?: Record<string, unknown>;
  status?: ReminderStatus;
}

// ── Briefings ────────────────────────────────────────────────────

export interface BriefingCalendarEvent {
  title: string;
  start_time: string;  // ISO datetime
  end_time: string;
  location: string | null;
  attendees: string[] | null;
  needs_prep: boolean;
}

export interface BriefingTaskItem {
  id: string;
  title: string;
  cadence: Cadence;
  priority: TaskPriority;
  streak_count: number;
  is_overdue: boolean;
}

export interface BriefingActionItem {
  id: string;
  title: string;
  source: ActionItemSource;
  priority: ActionItemPriority;
  extracted_deadline: string | null;
  confidence_score: number | null;
}

export interface IntegrationHealthItem {
  provider: IntegrationProvider;
  status: IntegrationStatusValue;
  last_synced_at: string | null;
  error_message: string | null;
}

export interface BriefingContent {
  calendar_events: BriefingCalendarEvent[];
  overdue_tasks: BriefingTaskItem[];
  todays_tasks: BriefingTaskItem[];
  action_items: BriefingActionItem[];
  integration_health: IntegrationHealthItem[];
  ai_insights: string | null;
}

export interface BriefingResponse {
  id: string;
  briefing_type: string;     // "morning"
  date: string;              // "YYYY-MM-DD"
  content: BriefingContent | null;
  integration_gaps: string[] | null;
  generated_at: string | null;
  viewed_at: string | null;
  created_at: string;
}

// ── Integrations ─────────────────────────────────────────────────

export interface IntegrationResponse {
  id: string;
  provider: IntegrationProvider;
  scopes: string | null;
  status: IntegrationStatusValue;
  error_count: number;
  last_error: string | null;
  last_synced_at: string | null;
  is_active: boolean;
  created_at: string;
}

export interface IntegrationHealthResponse {
  provider: IntegrationProvider;
  status: IntegrationStatusValue;
  last_synced_at: string | null;
  is_active: boolean;
}

// ── Unified Tasks Endpoint ───────────────────────────────────────

export interface TodayRecurringTask {
  id: string;
  type: 'recurring';
  title: string;
  cadence: Cadence;
  priority: TaskPriority;
  streak_count: number;
  completed_today: boolean;
  skipped_today: boolean;
}

export interface TodayReminder {
  id: string;
  type: 'reminder';
  title: string;
  description: string | null;
  trigger_type: TriggerType;
  status: ReminderStatus;
}

export interface TodayActionItem {
  id: string;
  type: 'action_item';
  title: string;
  source: ActionItemSource;
  priority: ActionItemPriority;
  status: ActionItemStatus;
  confidence_score: number | null;
}

export interface TodayTasksResponse {
  date: string;  // "YYYY-MM-DD"
  recurring_tasks: TodayRecurringTask[];
  reminders: TodayReminder[];
  action_items: TodayActionItem[];
}

export interface AllTasksResponse {
  recurring_tasks?: Array<{
    id: string;
    type: 'recurring';
    title: string;
    cadence: Cadence;
    priority: TaskPriority;
    streak_count: number;
    is_archived: boolean;
  }>;
  action_items?: Array<{
    id: string;
    type: 'action_item';
    title: string;
    source: ActionItemSource;
    priority: ActionItemPriority;
    status: ActionItemStatus;
  }>;
  reminders?: Array<{
    id: string;
    type: 'reminder';
    title: string;
    trigger_type: TriggerType;
    status: ReminderStatus;
  }>;
}

// ── Dismissal Stats ──────────────────────────────────────────────

export interface DismissalStats {
  total_items: number;
  total_dismissed: number;
  dismissal_rate: number;
  by_reason: Record<DismissReason, number>;
  by_source: Record<ActionItemSource, number>;
}
```

---

## 3. API Client Layer (`lib/api.ts`)

### 3.1 Fetch Wrapper

```ts
const API_URL = process.env.NEXT_PUBLIC_API_URL!;

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const accessToken = localStorage.getItem('access_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  let response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  // Auto-refresh on 401
  if (response.status === 401 && accessToken) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      headers['Authorization'] = `Bearer ${localStorage.getItem('access_token')}`;
      response = await fetch(`${API_URL}${path}`, { ...options, headers });
    } else {
      // Refresh failed -- clear tokens, redirect to login
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
      throw new ApiError(401, 'Session expired');
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new ApiError(response.status, body.detail || 'Request failed');
  }

  return response.json();
}

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return false;

  try {
    const response = await fetch(`${API_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) return false;
    const tokens: Token = await response.json();
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
    return true;
  } catch {
    return false;
  }
}
```

### 3.2 API Functions (every endpoint)

```ts
// ── Auth ─────────────────────────────────────────────────────────

export const api = {
  auth: {
    register: (data: UserRegisterPayload) =>
      apiFetch<UserResponse>('/auth/register', {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    login: (data: UserLoginPayload) =>
      apiFetch<Token>('/auth/login', {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    refresh: (refreshToken: string) =>
      apiFetch<Token>('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken }),
      }),

    me: () =>
      apiFetch<UserResponse>('/auth/me'),

    updateMe: (data: UserUpdatePayload) =>
      apiFetch<UserResponse>('/auth/me', {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
  },

  // ── Recurring Tasks ────────────────────────────────────────────

  recurringTasks: {
    list: (includeArchived = false) =>
      apiFetch<RecurringTaskResponse[]>(
        `/tasks/recurring?include_archived=${includeArchived}`
      ),

    create: (data: RecurringTaskCreatePayload) =>
      apiFetch<RecurringTaskResponse>('/tasks/recurring', {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    update: (taskId: string, data: RecurringTaskUpdatePayload) =>
      apiFetch<RecurringTaskResponse>(`/tasks/recurring/${taskId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),

    archive: (taskId: string) =>
      apiFetch<void>(`/tasks/recurring/${taskId}`, {
        method: 'DELETE',
      }),

    complete: (taskId: string) =>
      apiFetch<TaskCompletionResponse>(`/tasks/recurring/${taskId}/complete`, {
        method: 'POST',
      }),

    skip: (taskId: string, notes?: string) =>
      apiFetch<TaskCompletionResponse>(
        `/tasks/recurring/${taskId}/skip${notes ? `?notes=${encodeURIComponent(notes)}` : ''}`,
        { method: 'POST' }
      ),

    reorder: (taskIds: string[]) =>
      apiFetch<void>('/tasks/recurring/reorder', {
        method: 'PUT',
        body: JSON.stringify({ task_ids: taskIds }),
      }),
  },

  // ── Action Items ───────────────────────────────────────────────

  actionItems: {
    list: (params?: {
      status?: ActionItemStatus;
      source?: ActionItemSource;
      priority?: ActionItemPriority;
      limit?: number;
      offset?: number;
    }) => {
      const searchParams = new URLSearchParams();
      if (params?.status) searchParams.set('status', params.status);
      if (params?.source) searchParams.set('source', params.source);
      if (params?.priority) searchParams.set('priority', params.priority);
      if (params?.limit) searchParams.set('limit', String(params.limit));
      if (params?.offset) searchParams.set('offset', String(params.offset));
      const qs = searchParams.toString();
      return apiFetch<ActionItemResponse[]>(
        `/action-items${qs ? `?${qs}` : ''}`
      );
    },

    get: (itemId: string) =>
      apiFetch<ActionItemResponse>(`/action-items/${itemId}`),

    create: (data: ActionItemCreatePayload) =>
      apiFetch<ActionItemResponse>('/action-items', {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    acknowledge: (itemId: string) =>
      apiFetch<ActionItemResponse>(`/action-items/${itemId}/acknowledge`, {
        method: 'POST',
      }),

    action: (itemId: string) =>
      apiFetch<ActionItemResponse>(`/action-items/${itemId}/action`, {
        method: 'POST',
      }),

    dismiss: (itemId: string, reason: DismissReason) =>
      apiFetch<ActionItemResponse>(`/action-items/${itemId}/dismiss`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }),

    snooze: (itemId: string, snoozedUntil: string) =>
      apiFetch<ActionItemResponse>(`/action-items/${itemId}/snooze`, {
        method: 'POST',
        body: JSON.stringify({ snoozed_until: snoozedUntil }),
      }),

    dismissalStats: () =>
      apiFetch<DismissalStats>('/action-items/stats/dismissals'),
  },

  // ── Briefings ──────────────────────────────────────────────────

  briefings: {
    today: () =>
      apiFetch<BriefingResponse>('/briefings/today'),

    byDate: (date: string) =>
      apiFetch<BriefingResponse>(`/briefings/${date}`),

    markViewed: () =>
      apiFetch<BriefingResponse>('/briefings/today/viewed', {
        method: 'POST',
      }),

    preview: () =>
      apiFetch<BriefingResponse>('/briefings/preview', {
        method: 'POST',
      }),
  },

  // ── Integrations ───────────────────────────────────────────────

  integrations: {
    list: () =>
      apiFetch<IntegrationResponse[]>('/integrations'),

    health: () =>
      apiFetch<IntegrationHealthResponse[]>('/integrations/health'),

    googleAuthorize: (redirectUri: string) =>
      apiFetch<{ authorization_url: string; state: string }>(
        `/integrations/google/authorize?redirect_uri=${encodeURIComponent(redirectUri)}`,
        { method: 'POST' }
      ),

    googleCallback: (code: string, redirectUri: string, state: string) =>
      apiFetch<IntegrationResponse>('/integrations/google/callback', {
        method: 'POST',
        body: JSON.stringify({
          provider: 'google_calendar',
          code,
          redirect_uri: redirectUri,
          state,
        }),
      }),

    githubAuthorize: (redirectUri: string) =>
      apiFetch<{ authorization_url: string; state: string }>(
        `/integrations/github/authorize?redirect_uri=${encodeURIComponent(redirectUri)}`,
        { method: 'POST' }
      ),

    githubCallback: (code: string, redirectUri: string, state: string) =>
      apiFetch<IntegrationResponse>('/integrations/github/callback', {
        method: 'POST',
        body: JSON.stringify({
          provider: 'github',
          code,
          redirect_uri: redirectUri,
          state,
        }),
      }),

    disconnect: (integrationId: string) =>
      apiFetch<void>(`/integrations/${integrationId}`, {
        method: 'DELETE',
      }),

    test: (integrationId: string) =>
      apiFetch<IntegrationHealthResponse>(
        `/integrations/${integrationId}/test`,
        { method: 'POST' }
      ),

    panicRevokeAll: () =>
      apiFetch<void>('/integrations/panic', {
        method: 'POST',
      }),
  },

  // ── Reminders ──────────────────────────────────────────────────

  reminders: {
    list: (includeCompleted = false) =>
      apiFetch<ReminderResponse[]>(
        `/reminders?include_completed=${includeCompleted}`
      ),

    create: (data: ReminderCreatePayload) =>
      apiFetch<ReminderResponse>('/reminders', {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    update: (reminderId: string, data: ReminderUpdatePayload) =>
      apiFetch<ReminderResponse>(`/reminders/${reminderId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),

    complete: (reminderId: string) =>
      apiFetch<ReminderResponse>(`/reminders/${reminderId}/complete`, {
        method: 'POST',
      }),

    dismiss: (reminderId: string) =>
      apiFetch<ReminderResponse>(`/reminders/${reminderId}/dismiss`, {
        method: 'POST',
      }),

    delete: (reminderId: string) =>
      apiFetch<void>(`/reminders/${reminderId}`, {
        method: 'DELETE',
      }),
  },

  // ── Unified Tasks ──────────────────────────────────────────────

  tasks: {
    today: () =>
      apiFetch<TodayTasksResponse>('/tasks/today'),

    all: (taskType?: 'recurring' | 'action_item' | 'reminder') => {
      const qs = taskType ? `?task_type=${taskType}` : '';
      return apiFetch<AllTasksResponse>(`/tasks/all${qs}`);
    },
  },
};
```

### 3.3 SWR Key Conventions

All SWR keys follow the pattern of the API path. Example:

```ts
const { data, error, mutate } = useSWR('/briefings/today', () => api.briefings.today());
const { data: tasks } = useSWR('/tasks/today', () => api.tasks.today());
const { data: integrations } = useSWR('/integrations/health', () => api.integrations.health());
```

This keeps keys deterministic and easy to invalidate.

---

## 4. Auth Flow (`lib/auth.ts`)

### 4.1 Token Storage Strategy

- **`localStorage`** for both `access_token` and `refresh_token`
- Access token: 60-minute expiry (per backend config)
- Refresh token: 7-day expiry
- On 401 response: auto-attempt refresh, redirect to `/login` if refresh fails

### 4.2 AuthContext

```ts
interface AuthContextValue {
  user: UserResponse | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  updateUser: (data: UserUpdatePayload) => Promise<void>;
}
```

**Provider logic:**

1. On mount, check if `access_token` exists in localStorage
2. If yes, call `GET /auth/me` to validate it and hydrate `user`
3. If `/auth/me` returns 401, attempt refresh; if refresh fails, clear tokens
4. `login()`: call `POST /auth/login`, store both tokens, call `/auth/me` to hydrate user, then redirect:
   - If `user.timezone === null` (first login / not onboarded): redirect to `/onboarding`
   - Otherwise: redirect to `/` (dashboard)
5. `register()`: call `POST /auth/register`, then auto-login (call `login()` with same credentials)
6. `logout()`: clear localStorage tokens, set `user = null`, redirect to `/login`

### 4.3 Protected Route Wrapper

The `(app)/layout.tsx` checks `isAuthenticated` from AuthContext. If false and not loading, redirect to `/login`. This means all routes under `(app)/` -- dashboard, tasks, settings -- are protected.

The `(auth)/layout.tsx` does the inverse: if already authenticated, redirect to `/`.

---

## 5. Page-by-Page Spec

---

### 5.1 Login Page (`(auth)/login/page.tsx`)

**Visual reference:** `mockups/login.html`

**Data fetching:** None. Client-side only.

**Behavior:**
- Tabbed interface: "Sign In" (default) and "Create Account"
- Sign In form: email + password fields, "Sign In" submit button
- Register form: email + password + confirm password fields, "Create Account" submit button
- Error state: red banner below tabs for invalid credentials (backend returns `401` with `detail: "Incorrect email or password"`)
- Loading state: button text changes to "Signing in..." / "Creating account...", button disabled
- On successful login: redirect per auth context logic (onboarding or dashboard)
- On successful register: auto-login, redirect to onboarding

**Component breakdown:**
- `page.tsx` -- owns form state, calls `useAuth().login` / `useAuth().register`
- No child components needed; the form is simple enough to be self-contained

**Keyboard shortcuts:** None (form inputs active).

**Validation:**
- Email: HTML `type="email"` + required
- Password (register): min 8 chars, must contain uppercase, lowercase, digit (match backend validator)
- Confirm password: must match password (client-side only)
- Show validation errors inline under each field

---

### 5.2 Onboarding Page (`(auth)/onboarding/page.tsx`)

**Visual reference:** `mockups/onboarding.html`

**Data fetching:** Client-side POST calls during wizard steps.

**Behavior:** 4-step wizard with progress dots. State managed locally with `useState(step)`.

**Step 1: Set up your routines**
- Pre-populated checklist of common recurring tasks (hardcoded in frontend)
- Default selected: Supplements, Reading, Writing, Coding (daily)
- Unselected: Weekly review, Brainstorming session (weekly)
- "+ Add a custom task" opens inline input
- On "Continue": batch-create all selected tasks via `POST /tasks/recurring` (fire in parallel, await all)

**Step 2: Connect your tools**
- Three integration cards: Google Calendar, Gmail, GitHub
- Each has "Connect" button that:
  1. Calls `POST /integrations/{provider}/authorize` with `redirect_uri` = `window.location.origin + '/onboarding?step=2'`
  2. Redirects browser to the returned `authorization_url`
  3. On OAuth callback redirect back, extracts `code` and `state` from URL params
  4. Calls `POST /integrations/{provider}/callback`
  5. Card changes to "Connected" state with green check
- "You can connect more integrations later in Settings" skip text
- All three are optional -- user can "Continue" without connecting any

**Step 3: Choose your briefing time**
- Large time display (e.g., "7:00 AM")
- Time preset buttons: 6:00 AM, 6:30 AM, 7:00 AM (default), 7:30 AM, 8:00 AM, 8:30 AM, 9:00 AM
- Timezone dropdown (detect via `Intl.DateTimeFormat().resolvedOptions().timeZone` on mount)
- On "Continue": call `PATCH /auth/me` with `{ timezone, wake_time }` where wake_time = selected briefing time

**Step 4: Preview briefing**
- Show loading spinner, call `POST /briefings/preview`
- Once loaded, render a preview briefing card with:
  - Calendar events (from BriefingContent.calendar_events)
  - Non-negotiables checklist (from BriefingContent.todays_tasks)
  - AI insights (from BriefingContent.ai_insights)
- "Go to Dashboard" button: redirects to `/`

**Component breakdown:**
- `page.tsx` -- owns `currentStep` state, renders step panels conditionally
- Step indicator component (dot + line progress bar)
- Each step is a section within the page, not separate components (they share wizard state)

**Keyboard shortcuts:** None.

---

### 5.3 Dashboard Page (`(app)/page.tsx`)

**Visual reference:** `mockups/dashboard.html`

**Data fetching:** Client-side with SWR.

```ts
// All fetched in parallel on mount
const { data: briefing } = useSWR('/briefings/today', () => api.briefings.today());
const { data: todayTasks } = useSWR('/tasks/today', () => api.tasks.today());
const { data: integrationHealth } = useSWR('/integrations/health', () => api.integrations.health());
```

On first load, also fire `POST /briefings/today/viewed` (fire-and-forget, no need to await).

**Layout:** 2-column grid (`grid-cols-2 gap-5`, max-width ~1400px).

**Left column:**
1. `NonNegotiablesCard` -- recurring tasks due today
2. `ActionItemsCard` -- action items with triage controls

**Right column:**
1. `CalendarCard` -- today's calendar events
2. `InsightsCard` -- AI insights from briefing

**Above grid:**
- `HealthBanner` (from layout, but data from this page's SWR)
- Header section: greeting ("Good morning, {name}"), date, briefing meta line

**Component: `NonNegotiablesCard`**

Props:
```ts
interface NonNegotiablesCardProps {
  tasks: TodayRecurringTask[];
  onComplete: (taskId: string) => void;
}
```

- Renders card with "Non-Negotiables" header, count of done/total
- Each row: checkbox, task title, `StreakBadge`, keyboard hint "Space"
- Completed tasks: checkbox filled blue, title struck through + dimmed
- Progress bar at bottom: filled width = (completed / total * 100)%
- `onComplete` calls `POST /tasks/recurring/{id}/complete`, then `mutate('/tasks/today')`

**Component: `ActionItemsCard`**

Props:
```ts
interface ActionItemsCardProps {
  items: TodayActionItem[];
  onAcknowledge: (itemId: string) => void;
  onDismiss: (itemId: string) => void;
  selectedIndex: number;
  onSelectIndex: (idx: number) => void;
}
```

- Renders card with "Action Items" header, count pending
- Each row: source icon (gmail=red envelope, github=purple wrench, manual=blue), `PriorityDot`, title, source + time + `ConfidenceTag`
- Selected row: left blue border + subtle blue bg
- Low confidence items (< 0.6): reduced opacity (0.6)
- Hover: shows `a` (acknowledge) and `d` (dismiss) buttons
- Triage footer: `j` `k` navigate, `a` acknowledge, `d` dismiss, `Enter` expand

**Component: `CalendarCard`**

Props:
```ts
interface CalendarCardProps {
  events: BriefingCalendarEvent[];
}
```

- Renders card with "Today's Schedule" header, event count
- Each row: time (HH:MM mono font), color bar (cycle through blue/purple/green/amber), title, subtitle (location + duration + attendee count)
- Events with `needs_prep: true` show an amber "prep needed" tag

**Component: `InsightsCard`**

Props:
```ts
interface InsightsCardProps {
  insights: string | null;
}
```

- Renders card with "AI Insights" header
- Parses the `ai_insights` string from the briefing
- Shows labeled sections: Priority (blue), At Risk (amber), Today/Opportunity (green)
- If `insights` is null: show empty state "No insights available. Connect integrations to enable AI analysis."

**Keyboard shortcuts (via `useKeyboardShortcuts` hook):**

| Key | Action |
|-----|--------|
| `b` | No-op (already on dashboard) |
| `t` | Navigate to `/tasks` |
| `s` | Navigate to `/settings` |
| `?` | Toggle `ShortcutOverlay` |
| `j` | Move action item selection down |
| `k` | Move action item selection up |
| `a` | Acknowledge selected action item |
| `d` | Dismiss selected action item (with `not_relevant` as default reason) |
| `Space` | Complete first incomplete non-negotiable task |
| `Esc` | Close shortcut overlay |

**Loading state:** Show `Skeleton` components matching card shapes (4 skeleton cards in grid).

**Error state:** If briefing fetch fails, show error banner: "Failed to load briefing. Retrying..." with SWR auto-retry.

**Empty state:** If no tasks and no briefing content, show centered message: "Your morning briefing will appear here. Set up your first routines in Settings."

---

### 5.4 Tasks Page (`(app)/tasks/page.tsx`)

**Visual reference:** `mockups/tasks.html`

**Data fetching:**

```ts
const { data: recurringTasks, mutate: mutateRecurring } =
  useSWR('/tasks/recurring', () => api.recurringTasks.list());
const { data: actionItems, mutate: mutateActions } =
  useSWR('/action-items', () => api.actionItems.list());
const { data: reminders, mutate: mutateReminders } =
  useSWR('/reminders', () => api.reminders.list());
```

**Layout:**
- Page header: "Tasks" + "Add Task" button (with `n` keyboard hint)
- `SegmentTabs`: All (total count), Routines (recurring count), Action Items (action count), Reminders (reminder count)
- Sections shown/hidden based on active segment tab

**Component: `SegmentTabs`**

Props:
```ts
interface SegmentTabsProps {
  activeTab: 'all' | 'recurring' | 'action_item' | 'reminder';
  onTabChange: (tab: string) => void;
  counts: { all: number; recurring: number; action_item: number; reminder: number };
}
```

- Pill-shaped tab group matching mockup (dark bg, active tab = raised card bg)
- Count badge in mono font after each label

**Section: Daily Non-Negotiables (recurring, priority=non_negotiable)**

- Filter: `recurringTasks.filter(t => t.priority === 'non_negotiable' && t.cadence === 'daily')`
- Section header: "Daily Non-Negotiables" + "Drag to reorder"
- Card containing `RecurringTaskRow` for each task

**Section: Weekly (recurring, cadence=weekly)**

- Filter: `recurringTasks.filter(t => t.cadence === 'weekly')`
- Section header: "Weekly"

**Component: `RecurringTaskRow`**

Props:
```ts
interface RecurringTaskRowProps {
  task: RecurringTaskResponse;
  isCompletedToday: boolean;
  onToggleComplete: (taskId: string) => void;
  onSkip: (taskId: string) => void;
  onEdit: (task: RecurringTaskResponse) => void;
}
```

- Drag handle (six dots, from @dnd-kit)
- Checkbox (blue filled when complete, title struck through)
- Task info: title, meta row with `CadenceTag` + priority tag
- `StreakBadge` (fire emoji + count when hot, dot + count otherwise)
- Hover actions: "Edit", "Skip" buttons

Note: To know if a task is completed today, the dashboard uses `/tasks/today` which includes `completed_today`. On the tasks page, we need to cross-reference. Strategy: also call `/tasks/today` and build a `Set<string>` of completed task IDs.

**Section: Action Items**

- Section header: "Action Items" with j/k navigation hint

**Component: `ActionItemRow`**

Props:
```ts
interface ActionItemRowProps {
  item: ActionItemResponse;
  isSelected: boolean;
  onSelect: () => void;
  onAcknowledge: (itemId: string) => void;
  onDismiss: (itemId: string) => void;
}
```

- Source icon (gmail/github/manual)
- `PriorityDot` + title
- Meta: source, relative time (from `created_at`), status tag (new=blue, acknowledged=amber), `ConfidenceTag`
- Description line (if present, shown below meta)
- Low confidence (< 0.6): row has `opacity-55`
- Selected: blue left border + subtle blue bg
- Hover/selected: show `a` and `d` action buttons

**Section: Reminders**

**Component: `ReminderRow`**

Props:
```ts
interface ReminderRowProps {
  reminder: ReminderResponse;
  onComplete: (id: string) => void;
  onDismiss: (id: string) => void;
}
```

- Icon (clock for time, envelope for follow_up, calendar for context)
- Title
- Meta: trigger description + trigger_type label
- Hover actions: "Done", "Dismiss" buttons

**Component: `AddTaskModal`**

Props:
```ts
interface AddTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
  defaultType?: 'recurring' | 'action_item' | 'reminder';
}
```

- Modal overlay with form:
  - Title input (required)
  - Type select: Recurring Task / Action Item / Reminder
  - Cadence select: Daily / Weekly / Monthly (shown only for recurring)
  - Priority select: Non-negotiable / Flexible (for recurring), High / Medium / Low (for action items)
  - Missed behavior select: Roll forward / Mark as missed (shown only for recurring)
  - Notes input (optional)
- "Cancel" (Esc) + "Create Task" buttons
- On submit:
  - Recurring: `POST /tasks/recurring`
  - Action Item: `POST /action-items` with `source: 'manual'`
  - Reminder: `POST /reminders` with `trigger_type: 'time'` as default
- After creation: close modal, call relevant `mutate()` to refresh list

**Drag-and-drop reorder:**
- Use `@dnd-kit/sortable` on recurring task sections
- On drop: collect new task ID order, call `PUT /tasks/recurring/reorder` with `{ task_ids: [...] }`
- Optimistically update the local sort order

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `b` | Navigate to `/` (dashboard) |
| `s` | Navigate to `/settings` |
| `n` | Open AddTaskModal |
| `Esc` | Close AddTaskModal |
| `j` / `k` | Navigate action items (when action items segment is active) |
| `a` | Acknowledge selected action item |
| `d` | Dismiss selected action item |

**Loading state:** Skeleton rows within each card section.

**Empty states:**
- No recurring tasks: "No routines set up yet. Click + Add Task to create your first one."
- No action items: "No action items. Connect integrations to start extracting items automatically."
- No reminders: "No reminders. Create one to get nudged at the right time."

---

### 5.5 Settings Page (`(app)/settings/page.tsx`)

**Visual reference:** `mockups/settings.html`

**Data fetching:**

```ts
const { data: user, mutate: mutateUser } = useSWR('/auth/me', () => api.auth.me());
const { data: integrations, mutate: mutateIntegrations } =
  useSWR('/integrations', () => api.integrations.list());
```

**Layout:** Single column, max-width ~860px. Sections stacked vertically.

**Section: Integrations**

Renders `IntegrationRow` for each provider. Hardcoded provider list:

```ts
const PROVIDERS = [
  { provider: 'google_calendar', name: 'Google Calendar', icon: 'calendar', phase: 1 },
  { provider: 'gmail', name: 'Gmail', icon: 'mail', phase: 1 },
  { provider: 'github', name: 'GitHub', icon: 'github', phase: 1 },
  { provider: 'slack', name: 'Slack', icon: 'slack', phase: 2 },
  { provider: 'notion', name: 'Notion', icon: 'notion', phase: 2 },
] as const;
```

**Component: `IntegrationRow`**

Props:
```ts
interface IntegrationRowProps {
  provider: IntegrationProvider;
  displayName: string;
  icon: string;
  integration: IntegrationResponse | null;  // null = not connected
  isPhase2: boolean;
  onConnect: (provider: IntegrationProvider) => void;
  onDisconnect: (integrationId: string) => void;
  onReconnect: (provider: IntegrationProvider) => void;
}
```

- Icon: colored square (google_calendar=blue, gmail=red, github=purple, slack=pink, notion=white)
- Name + status line:
  - Connected healthy: green dot + "Healthy" + relative time since last sync + scopes tag
  - Connected degraded: amber dot + error message + relative time + "Reconnect" button
  - Connected failed: red dot + error message + "Reconnect" button
  - Not connected (phase 1): gray dot + "Not connected" + "Connect" button
  - Not connected (phase 2): dimmed row (opacity 0.5) + "Coming Soon" disabled button
- Disconnect button (red outline) for connected integrations

Connect flow:
1. Call `api.integrations.googleAuthorize(redirectUri)` or `api.integrations.githubAuthorize(redirectUri)`
2. `redirectUri` = `window.location.origin + '/settings?oauth_callback=true'`
3. Redirect to `authorization_url`
4. On return, check URL params for `code` and `state`
5. Call the appropriate callback endpoint
6. `mutate('/integrations')` to refresh

**Section: Morning Briefing**

Three `SettingRow` components:
1. Briefing time: `<input type="time">` bound to `user.wake_time`. On change: `PATCH /auth/me { wake_time }`
2. Timezone: `<select>` with common timezones. On change: `PATCH /auth/me { timezone }`
3. Include AI insights: `ToggleSwitch` (currently cosmetic -- no backend field yet, store in localStorage)

**Section: Notifications**

Four `SettingRow` components:
1. Browser notifications: `ToggleSwitch`. On enable: request browser Notification permission
2. Email digest fallback: `ToggleSwitch` (cosmetic for phase 1)
3. Task reminders: `ToggleSwitch` (cosmetic for phase 1)
4. Quiet hours: two `<input type="time">` for start/end (cosmetic for phase 1; store in localStorage)

**Section: AI Extraction**

Two `SettingRow` components:
1. Confidence threshold: `<input type="range" min="0" max="100">` displaying value as 0.XX. Store in localStorage, used by ActionItemRow to determine the opacity threshold.
2. Auto-dismiss newsletters: `ToggleSwitch` (cosmetic for phase 1)

**Section: Account (Danger Zone)**

- Export all data: button that calls all list endpoints and downloads as JSON blob
- Revoke all integrations: button that calls `POST /integrations/panic` with confirmation dialog
- Delete account: button (disabled for phase 1 -- no backend endpoint yet)

**Component: `SettingRow`**

Props:
```ts
interface SettingRowProps {
  label: string;
  description: string;
  children: React.ReactNode;  // The control (toggle, input, select, button)
}
```

**Component: `ToggleSwitch`**

Props:
```ts
interface ToggleSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}
```

40px wide, 22px tall toggle matching mockup. Blue when on, gray when off.

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `b` | Navigate to `/` (dashboard) |
| `t` | Navigate to `/tasks` |

(No other shortcuts -- most settings involve form inputs.)

---

## 6. Shared Components Spec

### `ShortcutOverlay`

Props:
```ts
interface ShortcutOverlayProps {
  isOpen: boolean;
  onClose: () => void;
}
```

- Full-screen overlay (dark bg + blur), centered panel
- Groups: Navigation, Action Item Triage, Tasks
- Lists each shortcut as `label .... kbd` row
- "Press Esc to close" footer

### `StreakBadge`

Props:
```ts
interface StreakBadgeProps {
  count: number;
  cadence: Cadence;
}
```

- If `count >= 7` (daily) or `count >= 4` (weekly): "hot" style (amber color, fire emoji prefix)
- Otherwise: muted style (gray, dot prefix)
- Label: `{count} {unit}` where unit = "days" (daily), "wks" (weekly), "mos" (monthly)

### `PriorityDot`

Props: `{ priority: ActionItemPriority }`

- 6px circle: high=red, medium=amber, low=gray

### `ConfidenceTag`

Props: `{ score: number | null }`

- Mono font, score displayed as 0.XX
- Color: >= 0.8 green, >= 0.6 amber, < 0.6 red
- If null: don't render

### `CadenceTag`

Props: `{ cadence: Cadence }`

- Pill: daily=blue bg, weekly=purple bg, monthly=green bg
- Uppercase text, small font

---

## 7. Hooks Spec

### `useKeyboardShortcuts`

```ts
function useKeyboardShortcuts(shortcuts: Record<string, () => void>): void
```

- Registers a `keydown` listener on `document`
- Ignores events when `e.target` is `INPUT`, `TEXTAREA`, or `SELECT`
- Cleans up on unmount
- Called from each page with that page's shortcut map

### `useActionItemTriage`

```ts
interface UseActionItemTriageReturn {
  selectedIndex: number;
  selectNext: () => void;
  selectPrev: () => void;
  select: (index: number) => void;
  acknowledgeSelected: () => Promise<void>;
  dismissSelected: () => Promise<void>;
}

function useActionItemTriage(
  items: Array<{ id: string }>,
  onAcknowledge: (id: string) => Promise<void>,
  onDismiss: (id: string) => Promise<void>,
): UseActionItemTriageReturn
```

- Manages `selectedIndex` state
- `selectNext` / `selectPrev` clamp to array bounds
- `acknowledgeSelected` / `dismissSelected` call the callbacks with the selected item's ID, then advance selection

---

## 8. Layout Components

### `(app)/layout.tsx`

```tsx
// Wraps all authenticated pages
// - Checks auth, redirects to /login if not authenticated
// - Renders Sidebar on the left (fixed, 220px)
// - Renders HealthBanner at top of main content area
// - Renders children in main content area (margin-left: 220px)
```

Fetches integration health for the HealthBanner:
```ts
const { data: healthData } = useSWR('/integrations/health', () => api.integrations.health());
```

### `Sidebar`

Props:
```ts
interface SidebarProps {
  currentPath: string;  // from usePathname()
}
```

- Fixed left, 220px wide, dark bg (#0a0c10)
- Brand: "CHIEF OF STAFF" uppercase
- Nav links:
  - Dashboard (icon: square) -- shortcut `b` -- active when path = `/`
  - Tasks (icon: checkbox) -- shortcut `t` -- active when path starts with `/tasks`
  - Settings (icon: gear) -- shortcut `s` -- active when path starts with `/settings`
- Active link: white text, blue left border, subtle blue bg
- Footer: "v0.1.0 -- Phase 1"

### `HealthBanner`

Props:
```ts
interface HealthBannerProps {
  integrations: IntegrationHealthResponse[];
  onShowShortcuts: () => void;
}
```

- Horizontal bar below top of main area
- For each active integration: colored dot (healthy=green, degraded=amber, failed=red) + provider name + relative sync time
- Right side: `?` button to open ShortcutOverlay

---

## 9. Build Order

### Phase 1: Foundation (build sequentially)

| Step | What | Complexity | Depends on |
|------|------|-----------|------------|
| 1 | Project scaffolding: `create-next-app`, install deps, tailwind config, directory structure | S | -- |
| 2 | `lib/types.ts` -- all TypeScript interfaces | S | -- |
| 3 | `lib/utils.ts` -- `cn()` helper, date formatters | S | -- |
| 4 | `lib/api.ts` -- fetch wrapper + all API functions | M | types.ts |
| 5 | `lib/auth.ts` -- AuthContext provider, useAuth hook | M | api.ts |
| 6 | `app/layout.tsx` -- root layout with AuthProvider | S | auth.ts |
| 7 | `(auth)/layout.tsx` + `login/page.tsx` -- login/register page | M | auth.ts |

**Milestone: can log in and reach an empty dashboard.**

### Phase 2: Dashboard (build sequentially, components in parallel)

| Step | What | Complexity | Depends on |
|------|------|-----------|------------|
| 8 | `(app)/layout.tsx` -- sidebar + health banner + protected route check | M | auth.ts |
| 9 | `Sidebar` component | S | -- |
| 10 | `HealthBanner` component | S | types.ts |
| 11a | `NonNegotiablesCard` + `StreakBadge` | M | api.ts, types.ts |
| 11b | `CalendarCard` | S | types.ts |
| 11c | `InsightsCard` | S | types.ts |
| 11d | `ActionItemsCard` + `PriorityDot` + `ConfidenceTag` | M | api.ts, types.ts |
| 12 | `(app)/page.tsx` -- dashboard page assembling all cards, SWR fetching | M | 11a-d |
| 13 | `useKeyboardShortcuts` + `useActionItemTriage` hooks | S | -- |
| 14 | `ShortcutOverlay` | S | -- |
| 15 | Wire keyboard shortcuts into dashboard | S | 12, 13, 14 |

**Milestone: fully functional dashboard with keyboard triage.**

Steps 11a-d can all be built in parallel since they are independent components.

### Phase 3: Tasks Page (build sequentially, components in parallel)

| Step | What | Complexity | Depends on |
|------|------|-----------|------------|
| 16 | `SegmentTabs` component | S | -- |
| 17a | `RecurringTaskRow` + `CadenceTag` | M | types.ts |
| 17b | `ActionItemRow` (full version for tasks page) | M | types.ts |
| 17c | `ReminderRow` | S | types.ts |
| 18 | `AddTaskModal` | M | api.ts |
| 19 | `tasks/page.tsx` -- assemble sections + segment filter | L | 16, 17a-c, 18 |
| 20 | Drag-and-drop reorder for recurring tasks | M | 17a, api.ts |

**Milestone: full task management with CRUD, filtering, and reorder.**

Steps 17a-c can be built in parallel.

### Phase 4: Settings Page

| Step | What | Complexity | Depends on |
|------|------|-----------|------------|
| 21 | `IntegrationRow` + `ToggleSwitch` + `SettingRow` | M | types.ts |
| 22 | `settings/page.tsx` -- all sections assembled | M | 21, api.ts |
| 23 | OAuth connect/disconnect flows | L | 22, api.ts |

**Milestone: integration management and user preferences.**

### Phase 5: Onboarding

| Step | What | Complexity | Depends on |
|------|------|-----------|------------|
| 24 | `onboarding/page.tsx` -- 4-step wizard | L | api.ts (recurring tasks, integrations, briefings, auth) |

**Milestone: complete first-run experience.**

### Phase 6: Polish

| Step | What | Complexity | Depends on |
|------|------|-----------|------------|
| 25 | Loading skeletons for all pages | S | all pages |
| 26 | Error boundaries + toast notifications | S | -- |
| 27 | Empty states for all lists | S | all pages |
| 28 | Responsive tweaks (single-column dashboard on narrow screens) | S | -- |

---

## 10. Technical Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data fetching | SWR | Lightweight, handles cache + revalidation, no boilerplate reducers |
| UI library | shadcn/ui | Composable primitives, Tailwind-native, copy-paste ownership |
| State management | React Context (auth only) + SWR cache | No global store needed -- all state is server state or local |
| Routing | Next.js App Router with route groups | `(auth)` and `(app)` groups enable different layouts |
| Styling | Tailwind CSS | Matches mockup approach of utility classes + dark theme tokens |
| Drag-and-drop | @dnd-kit | Accessible, lightweight, composable for list reordering |
| Token storage | localStorage | Simple, works for single-user web app. HttpOnly cookies not needed (no SSR data fetching with auth) |
| SSR | Disabled for all data fetching | All pages fetch client-side after auth check. No server components calling the API (backend requires JWT in Authorization header, not cookies) |

---

## 11. CORS Configuration Note

The backend currently has `cors_origins: ["*"]`. Before deploying the frontend, update the backend's `.env` to:

```env
CORS_ORIGINS=["http://localhost:3000","https://your-production-domain.com"]
```

---

## 12. File-Level Reference

Backend files that define the API contract:

| Frontend concern | Backend source file |
|------------------|-------------------|
| Auth types + endpoints | `backend/app/schemas/auth.py`, `backend/app/api/auth.py` |
| Recurring task types + endpoints | `backend/app/schemas/recurring_task.py`, `backend/app/api/recurring_tasks.py` |
| Action item types + endpoints | `backend/app/schemas/action_item.py`, `backend/app/api/action_items.py` |
| Reminder types + endpoints | `backend/app/schemas/one_off_reminder.py`, `backend/app/api/reminders.py` |
| Briefing types + endpoints | `backend/app/schemas/briefing.py`, `backend/app/api/briefings.py` |
| Integration types + endpoints | `backend/app/schemas/integration.py`, `backend/app/api/integrations.py` |
| Unified tasks endpoint | `backend/app/api/tasks.py` |
| All enum values | `backend/app/models/enums.py` |
| API prefix (`/api/v1`) | `backend/app/core/config.py` line 54 |
| Route registration | `backend/main.py` lines 114-154 |
