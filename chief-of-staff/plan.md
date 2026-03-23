# Implementation Plan: Chief of Staff

## Conventions

All paths relative to `chief-of-staff/`. The project lives at `/Users/nickchua/Desktop/AI/chief-of-staff/` in the monorepo. Patterns are drawn from:

- **fitness-app/backend/** -- FastAPI structure, SQLAlchemy models (sync), Pydantic schemas, Alembic, JWT auth, Railway deploy
- **travel-planning/backend/** -- ARQ + Redis worker, async SQLAlchemy, cron jobs, phase-based polling
- **holocron/backend/** -- Google OAuth connectors, base connector pattern, AI card generation

Complexity labels: **S** = small (< 1 hour), **M** = medium (1-3 hours), **L** = large (3-8 hours), **XL** = extra-large (8+ hours).

---

## Phase 0: Prompt Harness

**Goal**: Validate that Claude can reliably extract action items from emails/messages before building any infrastructure. This is the make-or-break feature.

**Dependencies**: None. Build first, completely standalone.

### Step 0.1: Create test corpus [M]

**File**: `prompt-harness/test_corpus.py`

Create a Python file with a list of test email/message fixtures. Each fixture is a dict with:
- `id`: unique identifier
- `source`: "gmail" | "github" | "slack"
- `raw_text`: the email/message body (use realistic but synthetic content)
- `expected_action_items`: list of dicts with `title`, `people`, `deadline`, `confidence`
- `expected_non_items`: texts that look like action items but are not (newsletters, marketing, automated notifications)

Include at minimum:
- 5 emails with clear commitments ("I'll send that over tomorrow")
- 5 emails with implicit action items ("Can you review this by Friday?")
- 5 emails with no action items (newsletters, receipts, automated alerts)
- 3 GitHub notifications (PR review requests, issue assignments, CI failures)
- 3 ambiguous cases (CC'd on threads, FYI emails, meeting notes with vague action items)
- 2 emails with multiple action items in one message

### Step 0.2: Build the extraction prompt [M]

**File**: `prompt-harness/prompts.py`

Create the system prompt and extraction prompt templates. Two tiers per spec:
- `TRIAGE_PROMPT` (Haiku): Quick classification -- "Does this message contain action items worth extracting? Return yes/no with reasoning."
- `EXTRACTION_PROMPT` (Sonnet): Full extraction -- structured output with title, description, people involved, deadline (if detected), confidence score, priority.

Include the data minimization preprocessing function here:
- `strip_email_noise(raw_text: str) -> str` -- removes signatures, quoted replies (`>` lines, `On ... wrote:`), marketing footers, unsubscribe links, HTML tags.
- `truncate_for_api(text: str, max_chars: int = 8000) -> str` -- truncates with `[truncated]` marker.

Reference: `holocron/backend/app/services/connectors/gmail.py` lines 31-61 for the HTML-to-text extraction pattern.

Output schema (as a Pydantic model in the prompt instructions):
```
{
  "has_action_items": bool,
  "action_items": [
    {
      "title": "short imperative title",
      "description": "context for why this matters",
      "people": ["name or email"],
      "deadline": "ISO date or null",
      "confidence": 0.0-1.0,
      "priority": "high|medium|low",
      "commitment_type": "you_committed|they_requested|mutual|fyi"
    }
  ]
}
```

### Step 0.3: Build the harness runner [M]

**File**: `prompt-harness/run_harness.py`

A CLI script that:
1. Loads test corpus
2. For each fixture, runs triage (Haiku) then extraction (Sonnet) if triage says yes
3. Compares extracted items against expected items using fuzzy matching
4. Prints a scorecard: precision, recall, false positives, false negatives
5. Saves results to `prompt-harness/results/run_{timestamp}.json`

Use `anthropic` Python SDK directly. Require `ANTHROPIC_API_KEY` env var.

**File**: `prompt-harness/requirements.txt`
```
anthropic>=0.40.0
pydantic>=2.0
```

### Step 0.4: Iterate on prompts [M]

Run the harness repeatedly, tuning prompts until:
- Triage precision > 90% (not sending newsletters to Sonnet)
- Extraction recall > 80% (catching real action items)
- False positive rate < 15% (not creating noise)

Save the winning prompts. These will be copied into the backend service later.

**Acceptance criteria**: A `prompt-harness/results/` directory with at least one run showing acceptable metrics, and finalized prompts in `prompts.py`.

---

## Phase 1A: Backend Foundation

**Goal**: Project scaffolding, database, models, config, auth. Everything needed before adding integrations.

**Dependencies**: None (can start in parallel with Phase 0).

### Step 1A.1: Project scaffolding [S]

Create the directory structure mirroring `fitness-app/backend/`:

```
chief-of-staff/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   └── __init__.py
│   │   ├── core/
│   │   │   └── __init__.py
│   │   ├── models/
│   │   │   └── __init__.py
│   │   ├── schemas/
│   │   │   └── __init__.py
│   │   └── services/
│   │       └── __init__.py
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   ├── alembic.ini
│   ├── main.py
│   ├── worker.py
│   ├── requirements.txt
│   ├── Procfile
│   └── .env.example
├── prompt-harness/          (from Phase 0)
├── web/                     (Phase 1G — Next.js frontend)
└── spec.md
```

### Step 1A.2: Configuration [S]

**File**: `backend/app/core/config.py`

Pattern: Hybrid of `travel-planning/backend/app/core/config.py` (uses `@lru_cache` + lowercase fields) and `fitness-app/backend/app/core/config.py` (singleton `settings`).

Use the travel-planning pattern (more modern):

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Database
    database_url: str

    # Auth
    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 1 day

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AI
    anthropic_api_key: str = ""

    # Token encryption (SEPARATE from secret_key per spec)
    token_encryption_key: str = ""  # AES-256-GCM key for OAuth tokens

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""

    # Web Push (VAPID)
    vapid_private_key: str = ""
    vapid_claims_email: str = ""

    # App
    app_name: str = "Chief of Staff"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    # Worker
    worker_db_pool_size: int = 5
    worker_db_max_overflow: int = 10
```

### Step 1A.3: Database setup [S]

**File**: `backend/app/core/database.py`

Use sync SQLAlchemy for the API server (matching fitness-app pattern), async for the worker (matching travel-planning). Create both:
- `engine`, `SessionLocal`, `Base`, `get_db()` -- sync, for FastAPI endpoints
- `create_async_engine` factory function -- for worker.py startup

Pattern: `fitness-app/backend/app/core/database.py` for the sync side.

### Step 1A.4: Security & auth utilities [S]

**File**: `backend/app/core/security.py`

Copy pattern from `fitness-app/backend/app/core/security.py`: `hash_password`, `verify_password`, `create_access_token`, `create_refresh_token`, `decode_token`, `verify_token`.

**File**: `backend/app/core/dependencies.py`

Copy pattern from `fitness-app/backend/app/core/dependencies.py`: `get_current_user` dependency.

### Step 1A.5: Token encryption module [M]

**File**: `backend/app/core/encryption.py`

**This is new -- no existing pattern in the monorepo.** Implements AES-256-GCM encryption for OAuth tokens per spec.

```python
# Uses cryptography.fernet for simplicity (Fernet uses AES-128-CBC + HMAC,
# which is simpler than raw AES-GCM and still secure for this use case)
from cryptography.fernet import Fernet

def encrypt_token(plaintext: str) -> str:
    """Encrypt an OAuth token. Returns base64-encoded ciphertext."""

def decrypt_token(ciphertext: str) -> str:
    """Decrypt an OAuth token."""
```

Uses `TOKEN_ENCRYPTION_KEY` from config (separate from `SECRET_KEY`).

Add to `requirements.txt`: `cryptography>=42.0`.

### Step 1A.6: SQLAlchemy models [L]

All models follow the fitness-app pattern: `Column`, `String` primary keys with `uuid.uuid4()`, `DateTime` with `datetime.utcnow`, relationships with `back_populates`.

**File**: `backend/app/models/user.py`
- `User`: id, email, password_hash, timezone, wake_time, sleep_time, is_deleted, created_at, updated_at
- Relationships to all child models

**File**: `backend/app/models/recurring_task.py`
- `RecurringTask`: id, user_id (FK), cadence (enum: daily/weekly/monthly/custom), cron_expression, title, description, time_window_start, time_window_end, timezone, missed_behavior (enum: roll_forward/mark_missed), priority (enum: non_negotiable/flexible), streak_count, last_completed_at, sort_order, is_archived, created_at, updated_at
- `TaskCompletion`: id, recurring_task_id (FK), date, completed_at, skipped (bool), notes

**File**: `backend/app/models/action_item.py`
- `ActionItem`: id, user_id (FK), source (enum: gmail/github/manual), source_id, source_url, title, description, extracted_deadline, confidence_score, priority (enum: high/medium/low), status (enum: new/acknowledged/actioned/dismissed), dismiss_reason (nullable enum), snoozed_until, linked_task_id (nullable FK to RecurringTask), dedup_hash, created_at, actioned_at

**File**: `backend/app/models/one_off_reminder.py`
- `OneOffReminder`: id, user_id (FK), title, description, trigger_type (enum: time/follow_up), trigger_config (JSON), source_action_item_id (nullable FK), status (enum: pending/completed/dismissed), created_at, completed_at

**File**: `backend/app/models/contact.py`
- `Contact`: id, user_id (FK), display_name, email, github_username, notes, last_interaction_at, created_at
- `ActionItemContact` (association table): action_item_id, contact_id

**File**: `backend/app/models/briefing.py`
- `Briefing`: id, user_id (FK), type (enum: morning), date, content (JSON -- use `Column(JSON)` for structured briefing data), integration_gaps (JSON array), generated_at, viewed_at

**File**: `backend/app/models/integration.py`
- `Integration`: id, user_id (FK), provider (enum: google_calendar/gmail/github), encrypted_auth_token, encrypted_refresh_token, scopes, status (enum: healthy/degraded/failed/disabled), error_count, last_error, last_synced_at, rate_limit_remaining, rate_limit_reset_at, is_active, created_at, updated_at
- Note: `encrypted_auth_token` and `encrypted_refresh_token` store the output of `encrypt_token()` from step 1A.5

**File**: `backend/app/models/sync_state.py`
- `SyncState`: id, integration_id (FK), resource_type (enum: inbox/calendar/notifications), cursor_value, cursor_type, last_sync_status (enum: success/failed/partial), last_sync_error, updated_at

**File**: `backend/app/models/calendar_event.py`
- `CalendarEvent`: id, user_id (FK), provider (enum: google/apple), external_id, title, start_time, end_time, location, attendees (JSON), needs_prep (bool), prep_notes, synced_at

**File**: `backend/app/models/notification.py`
- `PushSubscription`: id, user_id (FK), subscription_json (Web Push subscription endpoint + keys), platform (default "web"), is_active, created_at, updated_at
- `NotificationLog`: id, user_id (FK), notification_type (enum: briefing/task_reminder), related_entity_type, related_entity_id, title, body, sent_at, delivered_at, opened_at, channel (enum: web_push/email_digest/in_app)

**File**: `backend/app/models/audit_log.py`
- `AuditLog`: id, timestamp, action_type, integration_id (nullable), user_id (nullable), success (bool), error_details, metadata (JSON)
- Per spec: "Store logs separately from the main database" -- for Phase 1, store in same DB but separate table. Can migrate to separate DB later.

**File**: `backend/app/models/__init__.py`

Import all models so Alembic discovers them. Pattern: `fitness-app/backend/app/models/__init__.py`.

### Step 1A.7: Pydantic schemas [M]

**File**: `backend/app/schemas/auth.py` -- UserRegister, UserLogin, Token, TokenRefresh, UserResponse. Pattern: `fitness-app/backend/app/schemas/auth.py`.

**File**: `backend/app/schemas/recurring_task.py` -- RecurringTaskCreate, RecurringTaskUpdate, RecurringTaskResponse, TaskCompletionCreate, TaskCompletionResponse. Include streak_count in response.

**File**: `backend/app/schemas/action_item.py` -- ActionItemCreate (for manual creation), ActionItemResponse, ActionItemDismiss (with dismiss_reason), ActionItemSnooze.

**File**: `backend/app/schemas/one_off_reminder.py` -- ReminderCreate, ReminderUpdate, ReminderResponse.

**File**: `backend/app/schemas/briefing.py` -- BriefingResponse, BriefingContent (structured Pydantic model for the JSON content field: calendar_events, overdue_tasks, todays_tasks, action_items, integration_health, ai_insights).

**File**: `backend/app/schemas/integration.py` -- IntegrationResponse (never expose tokens), IntegrationCreate, IntegrationHealthResponse.

**File**: `backend/app/schemas/notification.py` -- PushSubscriptionRegister (accepts Web Push subscription JSON), NotificationPreferenceUpdate.

### Step 1A.8: Alembic setup [S]

**File**: `backend/alembic.ini` -- standard template, `sqlalchemy.url` overridden in env.py.

**File**: `backend/alembic/env.py` -- Pattern: `fitness-app/backend/alembic/env.py`. Import `Base` and `app.models`, override URL from settings.

Generate initial migration: `alembic revision --autogenerate -m "initial schema"`

### Step 1A.9: Main application entry point [S]

**File**: `backend/main.py`

Pattern: `fitness-app/backend/main.py`. Include:
- Logging config (stdout for Railway)
- Alembic migration on startup
- CORS middleware
- Exception handlers (validation, HTTP, general)
- Health check endpoint
- Root endpoint
- Router includes (added incrementally in later steps)

### Step 1A.10: Auth API endpoints [S]

**File**: `backend/app/api/auth.py`

Pattern: `fitness-app/backend/app/api/auth.py`. Endpoints:
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`

Include router in `main.py`.

### Step 1A.11: Requirements [S]

**File**: `backend/requirements.txt`

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
sqlalchemy>=2.0
alembic>=1.13.0
pydantic>=2.0
pydantic-settings>=2.0
python-jose[cryptography]>=3.3.0
bcrypt>=4.1.0
anthropic>=0.40.0
cryptography>=42.0
httpx>=0.27.0
google-auth>=2.28.0
google-api-python-client>=2.120.0
google-auth-oauthlib>=1.2.0
arq>=0.26.0
redis>=5.0
pywebpush>=2.0.0
psycopg2-binary>=2.9.0
python-multipart>=0.0.7
```

**Build order for 1A**: 1A.1 -> 1A.2 -> 1A.3 -> 1A.4 + 1A.5 (parallel) -> 1A.6 -> 1A.7 -> 1A.8 -> 1A.9 + 1A.10 (parallel) -> 1A.11

---

## Phase 1B: Integration Layer (Google Calendar + Gmail + GitHub)

**Goal**: OAuth connectors that can authenticate and fetch data from all three Phase 1 sources.

**Dependencies**: Phase 1A (models, config, encryption).

### Step 1B.1: Base connector [M]

**File**: `backend/app/services/connectors/__init__.py`
**File**: `backend/app/services/connectors/base.py`

Adapt from `holocron/backend/app/services/connectors/base.py` but redesigned for this app:

```python
class BaseConnector(ABC):
    """Base for all integration connectors."""

    provider: IntegrationProvider  # enum

    def __init__(self, integration: Integration, encryption_key: str):
        self.integration = integration
        self._encryption_key = encryption_key

    @abstractmethod
    async def authenticate(self) -> bool:
        """Validate/refresh credentials. Updates integration status."""

    @abstractmethod
    async def sync(self, sync_state: SyncState | None) -> SyncResult:
        """Fetch new data since last sync. Returns structured result."""

    async def refresh_token_if_needed(self) -> bool:
        """Proactive token refresh at 75% lifetime per spec."""

    def _decrypt_token(self, encrypted: str) -> str:
        """Decrypt stored OAuth token."""

    def _encrypt_token(self, plaintext: str) -> str:
        """Encrypt OAuth token for storage."""
```

Key difference from holocron: async methods, token encryption built in, explicit SyncState management.

`SyncResult` dataclass: documents_fetched, new_cursor, errors, raw_items (list of dicts to process).

### Step 1B.2: Google Calendar connector [L]

**File**: `backend/app/services/connectors/google_calendar.py`

- `authenticate()`: Use `google.oauth2.credentials.Credentials` with encrypted tokens from Integration model. Refresh if within 75% of lifetime.
- `sync()`: Use Calendar API `events().list()` with `syncToken` (stored in SyncState.cursor_value) for incremental sync. Fetch events for next 7 days. Returns list of CalendarEvent-shaped dicts.
- Handle token refresh and update encrypted tokens in DB.
- Rate limit tracking: update `integration.rate_limit_remaining` from response headers.

Reference: `holocron/backend/app/services/connectors/gmail.py` for Google API client pattern.

### Step 1B.3: Gmail connector [L]

**File**: `backend/app/services/connectors/gmail.py`

- `authenticate()`: Same Google OAuth pattern as calendar.
- `sync()`: Use Gmail API `history().list()` with `historyId` (stored in SyncState.cursor_value) for incremental sync. Only fetch new messages since last sync.
- `fetch_message(msg_id)`: Get full message, extract headers (From, To, Subject, Date), body text.
- `preprocess_for_ai(raw_text: str) -> str`: Strip signatures, quoted replies, marketing content. This is the data minimization step from spec.
- Scope: `gmail.readonly` (restricted scope -- noted in spec that testing mode requires re-auth every 7 days).

Reference: `holocron/backend/app/services/connectors/gmail.py` for message parsing, HTML extraction.

### Step 1B.4: GitHub connector [M]

**File**: `backend/app/services/connectors/github.py`

- `authenticate()`: GitHub OAuth token (simpler than Google -- no refresh dance, tokens are long-lived).
- `sync()`: Use GitHub REST API notifications endpoint with `since` parameter (stored in SyncState.cursor_value as ISO timestamp). Fetch:
  - PR review requests assigned to user
  - Issues assigned to user
  - CI failures on user's PRs
- Returns list of structured items with source_url pointing to the PR/issue.

### Step 1B.5: OAuth flow API endpoints [M]

**File**: `backend/app/api/integrations.py`

Endpoints:
- `GET /api/v1/integrations` -- list all integrations with health status (never expose tokens)
- `POST /api/v1/integrations/google/authorize` -- return Google OAuth URL with correct scopes (calendar + gmail)
- `POST /api/v1/integrations/google/callback` -- exchange auth code for tokens, encrypt and store
- `POST /api/v1/integrations/github/authorize` -- return GitHub OAuth URL
- `POST /api/v1/integrations/github/callback` -- exchange code for token, encrypt and store
- `DELETE /api/v1/integrations/{id}` -- disconnect: revoke token at provider, delete from DB
- `POST /api/v1/integrations/panic` -- revoke ALL tokens, invalidate sessions (spec: "panic button")
- `POST /api/v1/integrations/{id}/test` -- trigger a test sync, return health status

Include router in `main.py`.

### Step 1B.6: Audit logging service [S]

**File**: `backend/app/services/audit_log.py`

Simple function: `log_audit(db, action_type, integration_id, success, error_details, metadata)`.

Called by every connector on every sync, token refresh, and OAuth callback. Per spec: "Log every OAuth token usage (without token values), every Claude API call (without content), every data sync, and every token refresh."

**Build order for 1B**: 1B.1 -> 1B.2 + 1B.3 + 1B.4 (parallel) -> 1B.5 -> 1B.6

---

## Phase 1C: AI Extraction Pipeline

**Goal**: Take raw messages from connectors and produce ActionItems using Claude API.

**Dependencies**: Phase 0 (finalized prompts), Phase 1A (models), Phase 1B (connectors provide raw data).

### Step 1C.1: Email preprocessor [S]

**File**: `backend/app/services/email_preprocessor.py`

Port `strip_email_noise()` and `truncate_for_api()` from `prompt-harness/prompts.py` into the backend. Add content hashing: `hash_content(text: str) -> str` using SHA-256 for dedup (spec: "Store hash of processed content for 'already processed?' dedup checks").

### Step 1C.2: AI extraction service [L]

**File**: `backend/app/services/extraction_service.py`

The core service. Functions:

- `async def triage_message(text: str, source: str) -> bool`: Call Haiku with triage prompt. Returns True if worth extracting.
- `async def extract_action_items(text: str, source: str, source_id: str, source_url: str) -> list[ActionItemCreate]`: Call Sonnet with extraction prompt. Parse structured JSON response. Compute dedup_hash.
- `async def process_gmail_messages(messages: list[dict], user_id: str, db: Session) -> list[ActionItem]`: Full pipeline -- preprocess, dedup check, triage, extract, persist.
- `async def process_github_notifications(notifications: list[dict], user_id: str, db: Session) -> list[ActionItem]`: GitHub-specific processing (simpler -- PRs and issues have structured data, less AI needed).

Reference: `fitness-app/backend/app/services/screenshot_service.py` for the pattern of calling Anthropic API and parsing structured responses.

Audit log every Claude API call (without content).

### Step 1C.3: Feedback loop service [S]

**File**: `backend/app/services/feedback_service.py`

- `async def dismiss_action_item(item_id: str, reason: str, user_id: str, db: Session)`: Mark as dismissed, record reason.
- `async def get_dismissal_stats(user_id: str, db: Session) -> dict`: Aggregate dismissal patterns for prompt refinement.
- Future: feed dismissal patterns back into extraction prompt as few-shot examples.

### Step 1C.4: Action item API endpoints [M]

**File**: `backend/app/api/action_items.py`

Endpoints:
- `GET /api/v1/action-items` -- list action items, filterable by status, source, priority. Paginated.
- `POST /api/v1/action-items` -- manual creation (not AI-dependent per spec)
- `GET /api/v1/action-items/{id}` -- detail view
- `PUT /api/v1/action-items/{id}` -- update status, snooze
- `POST /api/v1/action-items/{id}/dismiss` -- dismiss with reason
- `POST /api/v1/action-items/{id}/acknowledge` -- mark as acknowledged
- `POST /api/v1/action-items/{id}/action` -- mark as actioned

Include router in `main.py`.

**Build order for 1C**: 1C.1 -> 1C.2 -> 1C.3 + 1C.4 (parallel)

---

## Phase 1D: Briefing Engine

**Goal**: Generate morning briefings using hybrid approach (rule-based assembly + Claude for insights).

**Dependencies**: Phase 1A (models), Phase 1B (calendar data), Phase 1C (action items exist).

### Step 1D.1: Briefing content assembler [L]

**File**: `backend/app/services/briefing_service.py`

The hybrid briefing generator:

- `async def generate_morning_briefing(user_id: str, db: Session) -> Briefing`:
  1. **Rule-based assembly** (no AI needed):
     - Query today's CalendarEvents, sorted by start_time
     - Query overdue RecurringTasks (missed_behavior=roll_forward, not completed)
     - Query today's RecurringTasks (by cadence + day of week/month)
     - Query open ActionItems (status=new or acknowledged), sorted by priority
     - Query Integration health statuses
  2. **AI insights** (Claude Sonnet call):
     - Pass the assembled data as structured context
     - Ask for: priority ranking, risk flags, suggested focus areas
     - Keep prompt tight -- the AI is ranking/synthesizing, not generating raw content
  3. **Assemble BriefingContent** Pydantic schema:
     - `calendar_events`: list of events with times
     - `overdue_tasks`: list with days overdue
     - `todays_tasks`: recurring + one-off due today
     - `action_items`: top action items by priority
     - `integration_health`: list of {provider, status, last_synced}
     - `ai_insights`: priority ranking, risk flags (from step 2)
  4. **Degraded mode**: If any integration is `failed`/`degraded`, include in `integration_gaps`. Briefing always generates with available data.
  5. Persist `Briefing` record with content as JSONB.

### Step 1D.2: Briefing API endpoints [S]

**File**: `backend/app/api/briefings.py`

Endpoints:
- `GET /api/v1/briefings/today` -- get today's briefing (generate if not exists)
- `GET /api/v1/briefings/{date}` -- get briefing for specific date
- `POST /api/v1/briefings/today/viewed` -- mark as viewed (updates viewed_at)
- `POST /api/v1/briefings/preview` -- generate a preview briefing (for onboarding)

Include router in `main.py`.

**Build order for 1D**: 1D.1 -> 1D.2

---

## Phase 1E: Task Management API

**Goal**: CRUD for recurring tasks, one-off reminders, and task completion tracking.

**Dependencies**: Phase 1A (models, schemas).

### Step 1E.1: Recurring tasks API [M]

**File**: `backend/app/api/recurring_tasks.py`

Endpoints:
- `GET /api/v1/tasks/recurring` -- list all (with today's completion status)
- `POST /api/v1/tasks/recurring` -- create
- `PUT /api/v1/tasks/recurring/{id}` -- update
- `DELETE /api/v1/tasks/recurring/{id}` -- archive (soft delete)
- `POST /api/v1/tasks/recurring/{id}/complete` -- mark complete for today, update streak
- `POST /api/v1/tasks/recurring/{id}/skip` -- skip for today with optional note
- `PUT /api/v1/tasks/recurring/reorder` -- bulk reorder (update sort_order)

Streak logic:
- On complete: if yesterday was also completed (or today is first day), increment streak_count. Otherwise reset to 1.
- `last_completed_at` updated on every completion.
- Response includes `streak_count` and `completed_today` (bool).

### Step 1E.2: One-off reminders API [S]

**File**: `backend/app/api/reminders.py`

Endpoints:
- `GET /api/v1/reminders` -- list pending reminders
- `POST /api/v1/reminders` -- create (time-based or follow-up)
- `PUT /api/v1/reminders/{id}` -- update
- `POST /api/v1/reminders/{id}/complete` -- mark complete
- `POST /api/v1/reminders/{id}/dismiss` -- dismiss
- `DELETE /api/v1/reminders/{id}` -- delete

### Step 1E.3: Unified tasks endpoint [S]

**File**: `backend/app/api/tasks.py`

Per spec, the Tasks tab shows recurring + one-off + action items in a merged view:
- `GET /api/v1/tasks/today` -- combined view: today's recurring tasks (with completion status), pending reminders, open action items. Merged and sorted by priority/time.
- `GET /api/v1/tasks/all` -- all tasks, filterable by type (recurring/action_item/reminder)

### Step 1E.4: Onboarding defaults [S]

**File**: `backend/app/services/onboarding_service.py`

- `async def create_default_tasks(user_id: str, db: Session)`: Pre-populate default daily non-negotiables (supplements, reading, writing, coding) per spec onboarding flow. User can edit/remove after.
- Called after user registration.

**Build order for 1E**: 1E.1 + 1E.2 (parallel) -> 1E.3 -> 1E.4

---

## Phase 1F: ARQ Worker

**Goal**: Background sync jobs on a cron schedule using ARQ + Redis.

**Dependencies**: Phase 1B (connectors), Phase 1C (extraction service), Phase 1D (briefing service).

### Step 1F.1: Worker setup [M]

**File**: `backend/worker.py`

Pattern: `travel-planning/backend/worker.py`. Direct copy of the structure:

```python
class WorkerSettings:
    redis_settings = _parse_redis_url(os.environ.get("REDIS_URL"))

    functions = [
        _sync_integration,
        _process_new_messages,
        _generate_briefing,
        _send_web_push_notification,
        _cleanup_old_data,
    ]

    cron_jobs = [
        cron(_scan_integrations, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),  # Every 5 min during active hours
        cron(_generate_morning_briefings, hour=7, minute=0),  # 7am daily (configurable per user in the job itself)
        cron(_cleanup_old_data, hour=3, minute=0),  # 3am daily
        cron(_health_check, second={0, 30}),  # Every 30s
    ]

    on_startup = startup
    on_shutdown = shutdown
```

`startup()`: Initialize async DB engine, httpx client, Anthropic client.
`shutdown()`: Close connections.

### Step 1F.2: Integration scanner cron job [M]

**File**: `backend/app/services/integration_scanner.py`

Pattern: `travel-planning/backend/app/services/trip_scanner.py` (phase-based polling).

- `async def scan_integrations(ctx)`:
  1. Query all active Integrations
  2. For each, determine if it's active hours (between user's wake_time and sleep_time)
  3. If active hours: poll every 5 min. If not: skip (dormant).
  4. Check rate limits before enqueuing
  5. Enqueue `_sync_integration` job for each due integration
  6. Handle degraded integrations: increment error_count, mark as failed after 3 consecutive errors

- `async def sync_integration(ctx, integration_id: str)`:
  1. Load integration + connector
  2. Call `connector.sync(sync_state)`
  3. If Gmail/GitHub: enqueue `_process_new_messages` with raw items
  4. Update SyncState with new cursor
  5. Update integration.last_synced_at
  6. Audit log

### Step 1F.3: Message processing job [M]

**File**: `backend/app/services/message_processor.py`

- `async def process_new_messages(ctx, integration_id: str, messages: list[dict])`:
  1. For each message, check dedup hash
  2. Run triage (Haiku)
  3. If triage passes, run extraction (Sonnet)
  4. Persist ActionItems
  5. Audit log (without content)

### Step 1F.4: Briefing generation cron job [S]

- `async def generate_morning_briefings(ctx)`:
  1. Query all users with active integrations
  2. Check each user's configured briefing time (default 7am in their timezone)
  3. If it's briefing time: generate briefing + enqueue push notification

### Step 1F.5: Data cleanup cron job [S]

- `async def cleanup_old_data(ctx)`:
  1. Purge raw sync data older than 7 days (spec: "Raw sync data purged after 7 days")
  2. Auto-archive ActionItems older than 30 days if never acknowledged
  3. Clean up expired audit logs per retention policy

### Step 1F.6: Redis setup [S]

**File**: `backend/app/core/redis.py`

Pattern: `travel-planning/backend/app/core/redis.py`. Async Redis connection pool.

**Build order for 1F**: 1F.6 -> 1F.1 -> 1F.2 + 1F.3 + 1F.4 + 1F.5 (parallel)

---

## Phase 1G: Next.js Web App

**Goal**: Desktop-first web app with sidebar navigation (Dashboard, Tasks, Settings), keyboard shortcuts, multi-column layout.

**Dependencies**: Phase 1A (auth API), Phase 1D (briefing API), Phase 1E (tasks API), Phase 1B (integrations API).

### Step 1G.1: Project scaffolding [S]

```
chief-of-staff/web/
├── app/
│   ├── layout.tsx              # Root layout with sidebar navigation
│   ├── page.tsx                # Dashboard (morning briefing)
│   ├── login/page.tsx
│   ├── register/page.tsx
│   ├── tasks/page.tsx          # Tasks view
│   └── settings/page.tsx       # Integration + preference management
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   └── IntegrationHealthBanner.tsx
│   ├── dashboard/
│   │   ├── BriefingCard.tsx
│   │   ├── NonNegotiables.tsx
│   │   ├── ActionItems.tsx
│   │   ├── CalendarTimeline.tsx
│   │   └── AiInsights.tsx
│   ├── tasks/
│   │   ├── RecurringTaskRow.tsx
│   │   ├── ActionItemRow.tsx
│   │   ├── ReminderRow.tsx
│   │   └── AddTaskDialog.tsx
│   └── settings/
│       ├── IntegrationCard.tsx
│       └── PreferencesForm.tsx
├── lib/
│   ├── api.ts                  # API client (fetch + JWT)
│   ├── auth.ts                 # Token management (login, refresh, logout)
│   └── hooks/
│       ├── useKeyboardShortcuts.ts
│       └── useAuth.ts
├── public/
│   └── sw.js                   # Service worker for Web Push
├── next.config.ts
├── tailwind.config.ts
├── package.json
└── tsconfig.json
```

Initialize with `npx create-next-app@latest --typescript --tailwind --app --src-dir=false`. Add shadcn/ui: `npx shadcn@latest init`.

### Step 1G.2: API client + auth library [M]

**File**: `web/lib/api.ts`

Fetch-based API client with JWT token management:
- Stores access/refresh tokens in localStorage (or httpOnly cookies for production)
- Automatic token refresh on 401 responses
- Typed request/response functions for all endpoints
- Base URL from environment variable

**File**: `web/lib/auth.ts`

Auth context provider:
- `login(email, password)` → stores tokens, redirects to dashboard
- `register(email, password)` → creates account, auto-login
- `logout()` → clears tokens, redirects to login
- `useAuth()` hook → current user, isAuthenticated, loading state
- Protected route wrapper (redirect to login if unauthenticated)

### Step 1G.3: Auth pages [S]

**File**: `web/app/login/page.tsx`
**File**: `web/app/register/page.tsx`

Simple login/register forms. Redirect to dashboard on success.

### Step 1G.4: Dashboard (multi-column briefing view) [L]

**File**: `web/app/page.tsx`
**File**: `web/components/dashboard/BriefingCard.tsx`
**File**: `web/components/dashboard/NonNegotiables.tsx`
**File**: `web/components/dashboard/ActionItems.tsx`
**File**: `web/components/dashboard/CalendarTimeline.tsx`
**File**: `web/components/dashboard/AiInsights.tsx`

Per spec's multi-column wireframe:
- Left column: Non-negotiables (checkboxes + streaks) + Action items (keyboard-navigable list)
- Right column: Calendar timeline + AI insights
- Top: Greeting + integration health banner
- SSR for the briefing data → no loading spinner on first paint

### Step 1G.5: Tasks page [L]

**File**: `web/app/tasks/page.tsx`
**File**: `web/components/tasks/RecurringTaskRow.tsx`
**File**: `web/components/tasks/ActionItemRow.tsx`
**File**: `web/components/tasks/ReminderRow.tsx`
**File**: `web/components/tasks/AddTaskDialog.tsx`

Per spec: merged view of Routines + Action Items + Reminders. Segmented filter: Routines | Action Items | All.

Features:
- Click to complete/dismiss, keyboard shortcuts for batch operations
- Click to expand detail inline (not modal)
- Confidence score indicator for AI-extracted items (low confidence visually distinct)
- Add button + dialog for manual action items and reminders
- Drag to reorder recurring tasks (dnd-kit or similar)

### Step 1G.6: Settings page [M]

**File**: `web/app/settings/page.tsx`
**File**: `web/components/settings/IntegrationCard.tsx`
**File**: `web/components/settings/PreferencesForm.tsx`

Sections:
- Integrations: cards with health status indicators (green/yellow/red), connect/disconnect buttons, OAuth redirect flow (native browser)
- Briefing time picker
- Notification preferences (browser notifications toggle)
- Task management (edit recurring tasks)
- Account (timezone, data export, delete account)

### Step 1G.7: Onboarding flow [M]

**File**: `web/components/onboarding/OnboardingWizard.tsx`

Multi-step wizard (shown on first login):
1. Welcome + pre-populate default daily non-negotiables (editable)
2. Connect integrations (start with Google Calendar — native OAuth redirect)
3. Set briefing time
4. Generate preview briefing

### Step 1G.8: Sidebar layout + integration health [S]

**File**: `web/components/layout/Sidebar.tsx`
**File**: `web/components/layout/IntegrationHealthBanner.tsx`

Sidebar navigation: Dashboard, Tasks, Settings. Active state indicator. Collapsible on smaller screens.

Integration health banner: shown at top when any integration is degraded/failed. Click to go to settings.

### Step 1G.9: Keyboard shortcut system [M]

**File**: `web/lib/hooks/useKeyboardShortcuts.ts`

Global keyboard shortcut system:
- **Navigation**: `b` dashboard, `t` tasks, `s` settings, `?` show shortcut help overlay
- **Action item triage**: `j/k` navigate list, `d` dismiss, `a` acknowledge, `s` snooze, `Enter` expand
- **Tasks**: `Space` complete, `n` add new
- Context-aware: shortcuts change based on current page/focus
- Help overlay (modal) showing all available shortcuts

### Step 1G.10: Service worker for Web Push [S]

**File**: `web/public/sw.js`

Service worker that:
- Registers for Web Push notifications (VAPID)
- Handles push events → shows native macOS notification banner
- Click handler: opens dashboard when notification is clicked
- Subscription management: register/unregister with backend

**Build order for 1G**: 1G.1 -> 1G.2 -> 1G.3 -> 1G.8 -> 1G.4 + 1G.5 + 1G.6 (parallel) -> 1G.7 -> 1G.9 + 1G.10 (parallel)

---

## Phase 1H: Browser Notifications

**Goal**: Web Push notifications for morning briefing, email digest as fallback.

**Dependencies**: Phase 1A (notification models), Phase 1F (worker generates briefings), Phase 1G (service worker registration).

### Step 1H.1: Web Push notification service [S]

**File**: `backend/app/services/notification_service.py`

Uses `pywebpush` library with VAPID keys:
- `send_web_push(db, user_id, notification_type, title, body, data)` — sends to all active subscriptions for user
- `notify_morning_briefing(db, user_id)` — convenience wrapper
- Handles expired/invalid subscriptions (remove from DB on 410 response)

### Step 1H.2: Notification API endpoints [S]

**File**: `backend/app/api/notifications.py`

Endpoints:
- `POST /api/v1/notifications/subscribe` — register Web Push subscription (JSON blob with endpoint + keys)
- `DELETE /api/v1/notifications/unsubscribe` — deactivate subscription
- `GET /api/v1/notifications/preferences`
- `PUT /api/v1/notifications/preferences`

### Step 1H.3: Email digest service [S]

**File**: `backend/app/services/email_digest_service.py`

Fallback notification channel:
- `send_briefing_email(user_id, briefing)` — sends morning briefing summary via transactional email (Resend or SES)
- Triggered when Web Push delivery fails or user opts into email digest
- Simple HTML email template with briefing highlights + link to dashboard

**Build order for 1H**: 1H.1 + 1H.2 + 1H.3 (all parallel)

---

## Phase 1I: Security Hardening

**Goal**: Pre-commit hooks, audit log verification, data export/delete.

**Dependencies**: Phase 1A (encryption, models), Phase 1B (integrations).

### Step 1I.1: Pre-commit secret scanning [S]

**File**: `chief-of-staff/.pre-commit-config.yaml`

Per spec (and the credential leak incident documented in MEMORY.md):

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

Also add to root `.pre-commit-config.yaml` if it exists, or create one.

### Step 1I.2: Token redaction in logging [S]

**File**: `backend/app/core/logging_config.py`

Custom logging filter that redacts anything matching OAuth token patterns, API keys, or the word "token" followed by a string value. Applied to all loggers.

### Step 1I.3: Data export and delete endpoint [M]

**File**: `backend/app/api/account.py`

Per spec: "Endpoint to export all user data and nuke the account from day one."

- `GET /api/v1/account/export` -- JSON export of all user data (tasks, action items, briefings, completions). Excludes encrypted tokens.
- `DELETE /api/v1/account` -- soft delete user, revoke all integration tokens at providers, invalidate sessions. Hard delete after 30 days.

### Step 1I.4: Encryption key validation on startup [S]

In `main.py` startup:
- Verify `TOKEN_ENCRYPTION_KEY` is set and is a valid Fernet key
- Verify it's different from `SECRET_KEY`
- Log warning (not the key value) if missing in production mode

**Build order for 1I**: All steps can be done in parallel.

---

## Phase 1J: Deployment

**Goal**: Railway deployment with separate API server and worker processes.

**Dependencies**: Everything above.

### Step 1J.1: Procfile [S]

**File**: `backend/Procfile`

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
worker: arq backend.worker.WorkerSettings
```

Pattern: travel-planning uses this exact setup for Railway (two processes: web + worker).

### Step 1J.2: Environment variables [S]

**File**: `backend/.env.example`

Document all required env vars:
```
DATABASE_URL=postgresql://...
SECRET_KEY=...
TOKEN_ENCRYPTION_KEY=...   # MUST be different from SECRET_KEY
ANTHROPIC_API_KEY=...
REDIS_URL=redis://...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
VAPID_PRIVATE_KEY=...      # Web Push VAPID key
VAPID_CLAIMS_EMAIL=...     # Contact email for VAPID
NEXT_PUBLIC_API_URL=...    # Backend URL for frontend
```

### Step 1J.3: Railway configuration [S]

Create Railway project with:
- PostgreSQL database
- Redis instance
- Two services: API (web) and Worker
- All env vars configured
- Custom domain if desired

### Step 1J.4: CLAUDE.md for the project [S]

**File**: `chief-of-staff/CLAUDE.md`

Project instructions for Claude Code, following the pattern of `fitness-app/CLAUDE.md`. Include:
- Project structure
- Common commands
- Deployment info
- Security guidelines
- Environment variables

---

## Build Order Summary

The overall dependency graph:

```
Phase 0 (Prompt Harness)     Phase 1A (Backend Foundation)
         |                            |
         v                            v
Phase 1C (AI Extraction) <-- Phase 1B (Integration Layer)
         |                            |
         v                            v
Phase 1D (Briefing Engine)   Phase 1E (Task Management API)
         |                            |
         +----------+  +-----------+
                    |  |
                    v  v
              Phase 1F (ARQ Worker)
                    |
                    v
              Phase 1G (Next.js Web App)
                    |
                    v
              Phase 1H (Browser Notifications)
                    |
                    v
         Phase 1I (Security Hardening)
                    |
                    v
             Phase 1J (Deployment)
```

**Parallelism opportunities**:
- Phase 0 and Phase 1A can be built simultaneously
- Phase 1B connectors (Calendar, Gmail, GitHub) can be built in parallel
- Phase 1D and Phase 1E are independent of each other
- Phase 1G web pages (Dashboard, Tasks, Settings) can be built in parallel
- Phase 1I steps are all independent

**Critical path**: Phase 0 -> Phase 1A -> Phase 1B -> Phase 1C -> Phase 1F -> Phase 1G -> Phase 1J

**Estimated total effort**: ~60-70 hours of implementation across all phases (~50% less frontend effort vs. original iOS plan).
