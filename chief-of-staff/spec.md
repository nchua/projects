# Chief of Staff - Product Spec

## Vision

A personal chief of staff app that ensures nothing falls through the cracks. It monitors your calendars, emails, Slack, and GitHub — then synthesizes everything into actionable briefings and smart reminders. It manages your recurring routines (daily, weekly, monthly) and uses AI to extract commitments and deadlines from your communications.

**Platform**: iOS app (Phase 1). Web app deferred to Phase 2.

---

## Core Concepts

### 1. Recurring Tasks (Routines)

Structured, repeating tasks organized by cadence:

#### Daily Non-Negotiables
- Supplements
- Reading
- Writing
- Coding
- *(User-configurable list)*

#### Weekly Tasks
- Brainstorming session
- Insights review (`/insights`)
- Weekly review/retrospective
- *(User-configurable)*

#### Monthly Tasks
- Replace sparkling water
- Monthly goal review
- *(User-configurable)*

Each recurring task is configurable:
- **Missed behavior**: Roll forward (carry over as overdue) OR mark as missed and reset — set per task
- **Time window**: When during the day/week/month it should be completed
- **Priority level**: Non-negotiable vs. flexible
- **Notes/context**: Attach instructions, links, or context to any task
- **Timezone**: Per-task timezone for "by 9am" logic (defaults to user timezone)

### 2. AI-Powered Communication Monitoring

The app actively monitors and analyzes:

| Source | What It Extracts | Phase |
|--------|-----------------|-------|
| **Google Calendar** | Upcoming meetings, prep needed, conflicts | 1 |
| **Gmail** | Action items, commitments made, follow-ups needed | 1 |
| **GitHub** | Open PRs needing review, issues assigned, CI failures | 1 |
| **Apple Calendar** | Same as Google Calendar, merged view (via EventKit → backend) | 2 |
| **Slack** | Action items, mentions, threads needing response | 2 |
| **Notion** | TODOs, tagged items, draft action items | 2 |
| **Discord** | Action items, mentions, threads needing response | 3 |

**Dropped integrations** (no viable API):
- ~~iMessage~~ — No public API. Use manual capture (share sheet/paste) if needed.
- ~~Apple Notes~~ — No public API. Use Notion as canonical notes platform.
- ~~Apple Mail~~ — IMAP is painful and low-value if Gmail is primary email.

**AI Analysis Features:**
- Extracts action items from natural language ("I'll send that over tomorrow")
- Detects commitments you've made to others
- Flags items at risk of falling through the cracks
- Identifies scheduling conflicts
- Surfaces forgotten follow-ups (e.g., email sent 3 days ago with no reply)
- **Data minimization**: Strip signatures, quoted replies, marketing content before sending to Claude API. Use Haiku for initial triage, Sonnet only for ambiguous cases.

### 3. Briefings

#### Morning Briefing
Generated daily at a fixed time (default 7:00 AM, user-configurable). Available as push notification + in-app view.

**Generation strategy**: Hybrid — rule-based assembly for structured data (calendar events, tasks, action items), Claude API call only for the insights/priority ranking section.

Contents:
- Today's calendar at a glance (Google Calendar + Apple Calendar merged)
- Overdue/carried-forward tasks
- Today's recurring tasks (non-negotiables + any weeklies/monthlies due)
- AI-flagged items: commitments, follow-ups, things at risk
- Priority ranking of what to tackle first
- **Integration health**: If any integration is down, clearly flag: "Gmail data unavailable — last synced 6 hours ago. Tap to reconnect."

**Degraded mode**: Briefing always generates with available data. Missing sources are flagged, never silently omitted.

#### Evening Review (Phase 2)
Deferred from Phase 1. When the user opens the app in the evening, show an optional "wrap up your day?" card they can tap or ignore. Full structured evening review added in Phase 2 if the morning habit sticks.

### 4. Notifications & Nudges

**Phase 1: Minimal notifications to earn trust.**
- **Morning briefing**: One push notification per day at the configured time
- **Task reminders**: Only for non-negotiable items the user explicitly opts into

**Phase 2: Expand based on proven value.**
- Smart nudges (pattern-based): "You usually take supplements by 9am — it's 10:30am"
- Follow-up nudges: "You committed to sending X to Y yesterday — still pending"
- Nudge frequency configurable (gentle / moderate / persistent)

**Key principle**: Start with 1 notification/day. Earn the right to send more by proving value.

### 5. One-Off Reminders

Beyond recurring tasks, users can create ad-hoc reminders:
- Time-based: "Remind me at 3pm to call the dentist"
- Follow-up: "If I don't hear back from [email] by Friday, remind me"
- Manual action items: User can manually add "I need to follow up on X" (not solely AI-dependent)

Phase 2+:
- Location-based (iOS): "Remind me when I get to the office"
- Context-based: "Remind me about this next time I talk to [person]"

### 6. AI Feedback Loop

When the AI extracts a wrong action item, users can dismiss with a reason:
- "Not an action item"
- "Already done"
- "Not relevant"

Dismissal patterns are tracked and used to refine extraction prompts over time. Low-confidence items (below threshold) are visually distinct in the UI.

---

## Information Architecture

### Dashboard (Home)
```
┌─────────────────────────────────┐
│  Good morning, Nick              │
│  Tuesday, March 22               │
│                                  │
│  ┌─ TODAY'S BRIEFING ─────────┐ │
│  │ 3 meetings | 2 follow-ups  │ │
│  │ 1 item at risk             │ │
│  └────────────────────────────┘ │
│                                  │
│  ┌─ NON-NEGOTIABLES ──────────┐ │
│  │ ○ Supplements    (5 days)  │ │
│  │ ○ Reading        (3 days)  │ │
│  │ ○ Writing        (1 day)   │ │
│  │ ○ Coding         (12 days) │ │
│  └────────────────────────────┘ │
│                                  │
│  ┌─ ACTION ITEMS ─────────────┐ │
│  │ ⚡ Reply to investor email  │ │
│  │ ⚡ Send deck to Sarah       │ │
│  │ 📋 Review PR #42           │ │
│  └────────────────────────────┘ │
│                                  │
│  ┌─ CALENDAR ─────────────────┐ │
│  │ 10:00  Team standup        │ │
│  │ 14:00  Design review       │ │
│  │ 16:30  1:1 with Alex       │ │
│  └────────────────────────────┘ │
└─────────────────────────────────┘
```

### Tabs (Simplified)
1. **Home** — Dashboard with briefing, today's tasks, calendar, action items
2. **Tasks** — All recurring + one-off tasks + AI-extracted action items, filterable by type (Routines | Action Items | All)
3. **Settings** — Integrations (with health status), notification preferences, task configuration

**Rationale**: Merged Tasks + Inbox (user mental model is "what do I need to do?", not "is this recurring or extracted?"). Dropped Calendar tab (calendar events shown inline on Home). Three tabs keeps navigation simple.

### iOS Widget
- **Small widget**: Today's non-negotiables with checkboxes and streak counts
- **Medium widget**: Non-negotiables + next calendar event + action item count

---

## Technical Architecture

### Backend
- **Framework**: FastAPI (Python) — consistent with existing fitness app stack
- **Database**: PostgreSQL
- **AI**: Claude API for communication analysis and action item extraction
- **Task scheduling**: ARQ + Redis for background processing (polling integrations, generating briefings) — matches travel-planning project pattern, async-native, built-in cron scheduling
- **Deployment**: Railway
- **Auth**: JWT (single-user now, User model in place for multi-user later)

### iOS App
- **Framework**: SwiftUI
- **Local storage**: SwiftData for offline cache (today's briefing + task list)
- **Notifications**: APNs for push (morning briefing), UNUserNotificationCenter for local task reminders
- **Calendar**: EventKit for Apple Calendar access — reads on-device, pushes events to backend for briefing generation
- **Widget**: WidgetKit + SwiftData for home screen widgets
- **Contacts**: ContactsKit for person-context reminders (Phase 2+)

### Web App (Phase 2)
- **Framework**: Next.js (React)
- **Auth**: Shared JWT auth with backend
- **Real-time**: SSE (Server-Sent Events) for dashboard updates — simpler than WebSocket, unidirectional is sufficient

### Integrations

| Service | Method | Feasibility | Phase |
|---------|--------|-------------|-------|
| Google Calendar | OAuth 2.0 / Google API | Easy | 1 |
| GitHub | OAuth / REST + GraphQL API | Easy | 1 |
| Gmail | OAuth 2.0 / Gmail API | Easy-Moderate | 1 |
| Slack | Slack OAuth / Bot API (Socket Mode) | Easy-Moderate | 2 |
| Notion | Notion API (OAuth) | Easy-Moderate | 2 |
| Apple Calendar | EventKit (iOS) → push to backend | Moderate | 2 |
| Discord | Discord Bot API | Moderate | 3 |

**Sync strategy**: Phase-based polling — aggressive (every 5 min) during active hours, dormant overnight. Per-integration rate limiting with exponential backoff.

**Google OAuth note**: Gmail `gmail.readonly` is a "restricted" scope. For personal use, "testing" mode works (tokens expire every 7 days, requiring re-auth). Plan for full verification if distributing.

### Data Model

```
User
├── timezone, wake_time, sleep_time
├── created_at, updated_at
│
├── RecurringTask
│   ├── cadence (daily | weekly | monthly | custom)
│   ├── cron_expression (for custom cadence)
│   ├── title, description
│   ├── time_window (start_time, end_time)
│   ├── timezone
│   ├── missed_behavior (roll_forward | mark_missed)
│   ├── priority (non_negotiable | flexible)
│   ├── streak_count, last_completed_at
│   ├── sort_order, is_archived
│   └── TaskCompletion[] (date, completed_at, skipped, notes)
│
├── OneOffReminder
│   ├── title, description
│   ├── trigger_type (time | location | context | follow_up)
│   ├── trigger_config (JSON — time, coordinates, person_id, email_id)
│   ├── source_action_item_id (optional — links back to AI-extracted item)
│   ├── status (pending | completed | dismissed)
│   └── created_at, completed_at
│
├── ActionItem (AI-extracted)
│   ├── source (gmail | slack | notion | github)
│   ├── source_id, source_url
│   ├── title, description
│   ├── extracted_deadline (if detected)
│   ├── confidence_score
│   ├── priority (high | medium | low)
│   ├── status (new | acknowledged | actioned | dismissed)
│   ├── dismiss_reason (not_action_item | already_done | not_relevant) — nullable
│   ├── snoozed_until — nullable
│   ├── linked_task_id — nullable (connect to existing recurring task)
│   ├── dedup_hash (for duplicate detection across sources)
│   ├── people[] → Contact
│   └── created_at, actioned_at
│
├── Contact
│   ├── display_name
│   ├── email, slack_id, github_username, phone
│   ├── notes
│   └── last_interaction_at
│
├── Briefing
│   ├── type (morning)
│   ├── date
│   ├── content (structured JSONB — defined Pydantic schema)
│   ├── integration_gaps[] (which sources were unavailable)
│   ├── generated_at
│   └── viewed_at
│
├── Integration
│   ├── provider (google_calendar | gmail | github | slack | notion | discord | apple_calendar)
│   ├── auth_token (encrypted), refresh_token (encrypted)
│   ├── scopes
│   ├── status (healthy | degraded | failed | disabled)
│   ├── error_count, last_error
│   ├── last_synced_at
│   ├── rate_limit_remaining, rate_limit_reset_at
│   └── is_active
│
├── SyncState
│   ├── integration_id
│   ├── resource_type (inbox | calendar | channels | notifications)
│   ├── cursor_value (text — history_id, sync_token, timestamp, etc.)
│   ├── cursor_type
│   ├── last_sync_status (success | failed | partial)
│   ├── last_sync_error
│   └── updated_at
│
├── CalendarEvent (cache)
│   ├── provider (google | apple)
│   ├── external_id
│   ├── title, start_time, end_time, location
│   ├── attendees (JSONB)
│   ├── needs_prep (bool), prep_notes
│   └── synced_at
│
├── NotificationLog
│   ├── notification_type (briefing | task_reminder | nudge)
│   ├── related_entity_type, related_entity_id
│   ├── title, body
│   ├── sent_at, delivered_at, opened_at
│   └── channel (push | local)
│
└── NudgePreference
    ├── aggressiveness (gentle | moderate | persistent)
    ├── quiet_hours (start, end)
    └── channels (push | digest | both)
```

---

## Privacy & Security

### Threat Model
This app aggregates OAuth tokens for Gmail, Google Calendar, GitHub, Slack, and Notion into a single database. A server compromise would give an attacker read access to all connected services. Security is a first-class architectural concern.

### Token Encryption
- OAuth tokens encrypted using **AES-256-GCM** with a dedicated `TOKEN_ENCRYPTION_KEY` environment variable
- `TOKEN_ENCRYPTION_KEY` is separate from `DATABASE_URL` and `SECRET_KEY` — compromise of the database alone does not expose tokens
- Implementation: `cryptography.fernet` or direct AES-GCM via the `cryptography` library
- Never log token values — ensure logging configuration redacts tokens in request/response bodies and error tracebacks
- Request minimum OAuth scopes per integration (e.g., `gmail.readonly`, not `mail.google.com`)

### Token Refresh Strategy
- **Proactive refresh**: Refresh tokens at 75% of lifetime, before expiry
- **Refresh failures**: Mark integration as `degraded`/`failed`, notify user, do not silently fail
- **Token rotation**: When Google issues a new refresh token, immediately update storage (use a mutex to prevent race conditions)
- **External revocation**: Detect when user revokes access from provider settings — mark integration as disconnected, notify user
- **Panic button**: Admin endpoint that revokes all integration tokens and invalidates all sessions simultaneously

### Data Flow & Privacy
- **Data minimization for Claude API**: Strip email signatures, quoted replies, marketing content, and attachments before sending to Claude. Send only the minimum text necessary for action item extraction.
- **Tiered AI models**: Use Haiku for initial triage (is this worth extracting?), Sonnet only for ambiguous or complex cases. Reduces cost and data exposure.
- **Process then discard**: Raw email/message content is processed for action items then discarded from our database. Only extracted metadata (title, description, people, deadline) is stored.
- **Acknowledgment**: Content is sent to Anthropic's API servers for processing. Under Anthropic's API terms, inputs are not used for training but may be retained up to 30 days for trust & safety.
- **Third-party data**: People who email/message you have not consented to AI processing. For personal use this is acceptable, but design with opt-out/filtering capability for future expansion.

### Audit Logging
- Log every OAuth token usage (without token values), every Claude API call (without content), every data sync, and every token refresh
- Store logs separately from the main database
- Include: timestamp, action_type, integration_id, success/failure, error details

### Additional Security Measures
- **Rate limiting** on all API endpoints and per-integration sync frequency
- **Pre-commit hook** for secret scanning (prevent repeat of prior credential leak incident)
- **Content hashing**: Store hash of processed content (not content itself) for "already processed?" dedup checks
- **Data export & delete**: Endpoint to export all user data and nuke the account from day one
- **JWT secret**: Use a distinct `SECRET_KEY` per application — do not share with fitness-app or other Railway services
- **Data retention**: Raw sync data purged after 7 days (reduced from 30). Extracted action items auto-archive after 30 days if never acknowledged. Database backup retention aligned with purge schedule.

---

## Onboarding Flow

First launch experience (critical for retention — blank dashboard is a killer):

1. **Welcome + defaults**: Pre-populate suggested daily non-negotiables (supplements, reading, writing, coding) — user can edit, add, or remove
2. **Connect integrations**: Step-by-step wizard. Start with Google Calendar (fastest value). Gmail and GitHub optional but encouraged. Each integration shows clear "what you'll get" preview.
3. **Set briefing time**: Default 7:00 AM, user can adjust
4. **First briefing**: Generate an immediate "preview briefing" with whatever data is available, even if just calendar events. User should see value in the first session.

---

## MVP Scope

### Phase 0: Prompt Harness (build first)
Build a standalone script that tests the commitment extraction prompt against sample emails and messages. Validate AI extraction quality before building infrastructure around it. This is the make-or-break feature — if extraction is noisy, the app is a worse Apple Reminders.

### Phase 1: Core Daily Loop (iOS only)
The goal: **Do you open this app every morning for 2 weeks?**

1. **Recurring task management** — daily non-negotiables with streaks. Weekly/monthly tasks.
2. **Morning briefing** — push notification + in-app view (hybrid generation)
3. **Google Calendar + Gmail + GitHub integration** — highest-value, most reliable APIs
4. **iOS widget** — small (task checklist) + medium (tasks + next event)
5. **Manual action item creation** — user can add items directly, not solely AI-dependent
6. **AI action item extraction** — from Gmail, with dismiss + teach feedback loop
7. **Quick-add from notification** — tap notification to mark done, snooze, or dismiss without opening app
8. **Onboarding flow** — guided setup with defaults and integration wizard

### Phase 2: Expand Integrations + Web
- Slack + Notion + Apple Calendar (EventKit) integration
- Next.js web dashboard (SSE for real-time)
- Evening review (optional "wrap up" card)
- Smart nudges (pattern-based, once usage data exists)
- Follow-up tracking (unanswered emails)
- Location-based reminders (iOS)
- Siri integration via App Intents
- Completion streaks / historical stats view
- Search across action items, tasks, and briefings

### Phase 3: Extended Platform
- Discord integration
- Apple Watch companion (if daily loop is strong)
- Context-based reminders ("next time I talk to X")
- Semantic duplicate detection across sources (embeddings + cosine similarity)

### Dropped (no viable API)
- ~~iMessage~~ — No public API, no terms-compliant access
- ~~Apple Notes~~ — No public API, use Notion instead
- ~~Apple Mail (IMAP)~~ — Painful protocol, low value if Gmail is primary

---

## Decisions Log

Decisions made during council review (2026-03-22):

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Users | Single-user now, multi-user later | Keep User model + JWT auth, but don't build multi-tenant features |
| Briefing generation | Hybrid (rule-based + Claude for insights) | Balance cost and intelligence |
| Sync frequency | Phase-based (aggressive when active, dormant overnight) | Matches travel-planning pattern, balances freshness and cost |
| Degraded mode | Generate briefing with gaps, flag missing sources | Briefing always ships — never silently incomplete |
| Apple Calendar flow | EventKit on-device → push to backend | Backend needs calendar data for complete briefings |
| AI feedback loop | Dismiss with reason | Builds data for prompt refinement over time |
| iOS Widget | Phase 1 | Highest-leverage feature for daily engagement |
| Platforms | iOS only Phase 1, web Phase 2 | Avoid doubling frontend work before validating core loop |
| Background jobs | ARQ + Redis (not Celery) | Async-native, simpler, already proven in travel-planning |
| Real-time (web) | SSE (not WebSocket) | Unidirectional is sufficient, simpler |
| Prompt harness | Build before infrastructure | Extraction quality is the make-or-break feature |
| Evening briefing | Cut from Phase 1 | Morning is the high-value touchpoint; evening is aspirational |
| Tab structure | 3 tabs (Home, Tasks, Settings) | Merged Tasks+Inbox, dropped Calendar tab |
| Notification strategy | 1/day in Phase 1, earn the right to expand | Notification fatigue is the #1 product risk |
| Notification timing | Fixed time (7am default) | Predictability creates ritual |
| Shared tasks | Personal only, forever | Adding shared tasks means building Asana |
| Siri/Voice | Phase 2 via App Intents | Get core app working first |
| Apple Watch | Phase 3+ | Push notifications already arrive on wrist |
| Offline | Minimal — SwiftData cache for today's briefing + tasks | Single user with reliable internet |
