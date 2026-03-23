// ── Enums (match backend string values) ──────────────────────────

export type Cadence = "daily" | "weekly" | "monthly" | "custom";
export type MissedBehavior = "roll_forward" | "mark_missed";
export type TaskPriority = "non_negotiable" | "flexible";

export type ActionItemSource =
  | "gmail"
  | "github"
  | "slack"
  | "notion"
  | "discord"
  | "manual";
export type ActionItemPriority = "high" | "medium" | "low";
export type ActionItemStatus =
  | "new"
  | "acknowledged"
  | "actioned"
  | "dismissed";
export type DismissReason =
  | "not_action_item"
  | "already_done"
  | "not_relevant";

export type IntegrationProvider =
  | "google_calendar"
  | "gmail"
  | "github"
  | "slack"
  | "notion"
  | "discord"
  | "apple_calendar";
export type IntegrationStatusValue =
  | "healthy"
  | "degraded"
  | "failed"
  | "disabled";

// ── Auth ─────────────────────────────────────────────────────────

export interface Token {
  access_token: string;
  refresh_token: string;
  token_type: string; // always "bearer"
}

export interface UserResponse {
  id: string;
  email: string;
  timezone: string | null;
  wake_time: string | null; // "HH:MM" or null
  sleep_time: string | null; // "HH:MM" or null
  created_at: string; // ISO 8601 datetime
  updated_at: string;
}

export interface UserRegisterPayload {
  email: string;
  password: string; // min 8, max 100, must have upper+lower+digit
}

export interface UserLoginPayload {
  email: string;
  password: string;
}

export interface UserUpdatePayload {
  timezone?: string;
  wake_time?: string; // "HH:MM"
  sleep_time?: string; // "HH:MM"
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
  last_completed_at: string | null; // ISO datetime
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
  date: string; // "YYYY-MM-DD"
  completed_at: string | null;
  skipped: boolean;
  notes: string | null;
}

export interface RecurringTaskReorderRequest {
  task_ids: string[];
}

// ── Action Items ─────────────────────────────────────────────────

export interface ActionItemResponse {
  id: string;
  source: ActionItemSource;
  source_id: string | null;
  source_url: string | null;
  title: string;
  description: string | null;
  extracted_deadline: string | null; // ISO datetime
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

export interface ActionItemDismissPayload {
  reason: DismissReason;
}

export interface ActionItemSnoozePayload {
  snoozed_until: string; // ISO datetime
}

// ── Briefings ────────────────────────────────────────────────────

export interface BriefingCalendarEvent {
  title: string;
  start_time: string; // ISO datetime
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
  briefing_type: string; // "morning"
  date: string; // "YYYY-MM-DD"
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

export interface OAuthCallbackRequest {
  provider: IntegrationProvider;
  code: string;
  redirect_uri: string;
  state: string;
}

// ── Unified Tasks Endpoint ───────────────────────────────────────

export interface TodayRecurringTask {
  id: string;
  type: "recurring";
  title: string;
  cadence: Cadence;
  priority: TaskPriority;
  streak_count: number;
  completed_today: boolean;
  skipped_today: boolean;
}

export interface TodayActionItem {
  id: string;
  type: "action_item";
  title: string;
  source: ActionItemSource;
  priority: ActionItemPriority;
  status: ActionItemStatus;
  confidence_score: number | null;
}

export interface TodayTasksResponse {
  date: string; // "YYYY-MM-DD"
  recurring_tasks: TodayRecurringTask[];
  action_items: TodayActionItem[];
}

export interface AllTasksResponse {
  recurring_tasks?: Array<{
    id: string;
    type: "recurring";
    title: string;
    cadence: Cadence;
    priority: TaskPriority;
    streak_count: number;
    is_archived: boolean;
  }>;
  action_items?: Array<{
    id: string;
    type: "action_item";
    title: string;
    source: ActionItemSource;
    priority: ActionItemPriority;
    status: ActionItemStatus;
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
