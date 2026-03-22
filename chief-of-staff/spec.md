# Chief of Staff - Product Spec

## Vision

A personal chief of staff app that ensures nothing falls through the cracks. It monitors your calendars, emails, texts, Slack, notes, and GitHub — then synthesizes everything into actionable briefings and smart reminders. It manages your recurring routines (daily, weekly, monthly) and uses AI to extract commitments and deadlines from your communications.

**Platforms**: iOS app + Web app (built simultaneously)

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

### 2. AI-Powered Communication Monitoring

The app actively monitors and analyzes:

| Source | What It Extracts |
|--------|-----------------|
| **Google Calendar** | Upcoming meetings, prep needed, conflicts |
| **Apple Calendar (iCal)** | Same as above, merged view |
| **Gmail** | Action items, commitments made, follow-ups needed |
| **Apple Mail** | Same as above |
| **iMessage** | Promises, plans, RSVPs, things you said you'd do |
| **Slack / Discord** | Action items, mentions, threads needing response |
| **Apple Notes / Notion** | TODOs, tagged items, draft action items |
| **GitHub** | Open PRs needing review, issues assigned, CI failures |

**AI Analysis Features:**
- Extracts action items from natural language ("I'll send that over tomorrow")
- Detects commitments you've made to others
- Flags items at risk of falling through the cracks
- Identifies scheduling conflicts
- Surfaces forgotten follow-ups (e.g., email sent 3 days ago with no reply)

### 3. Briefings

#### Morning Briefing
Generated daily, available as a push notification + in-app view:
- Today's calendar at a glance
- Overdue/carried-forward tasks
- Today's recurring tasks (non-negotiables + any weeklies/monthlies due)
- AI-flagged items: commitments, follow-ups, things at risk
- Priority ranking of what to tackle first

#### Evening Review
End-of-day prompt:
- What got done today (auto-detected + manual check-off)
- What didn't get done — reschedule or dismiss
- Any new commitments extracted from today's communications
- Quick reflection prompt (optional, free-text)
- Preview of tomorrow

### 4. Notifications & Nudges

Three notification layers:

1. **Scheduled reminders**: Push notifications at set times for recurring tasks
2. **Daily digest**: Morning briefing notification
3. **Smart nudges**: AI-driven, pattern-based alerts:
   - "You usually take supplements by 9am — it's 10:30am"
   - "You committed to sending X to Y yesterday — still pending"
   - "Meeting with Z in 2 hours — no prep notes yet"
   - "You haven't responded to [email] from 3 days ago"

Nudge frequency and aggressiveness are user-configurable (gentle / moderate / persistent).

### 5. One-Off Reminders

Beyond recurring tasks, users can create ad-hoc reminders:
- Time-based: "Remind me at 3pm to call the dentist"
- Location-based (iOS): "Remind me when I get to the office"
- Context-based: "Remind me about this next time I talk to [person]"
- Follow-up: "If I don't hear back from [email] by Friday, remind me"

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
│  │ ○ Supplements              │ │
│  │ ○ Reading                  │ │
│  │ ○ Writing                  │ │
│  │ ○ Coding                   │ │
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

### Tabs / Sections
1. **Home** — Dashboard with briefing, today's tasks, calendar
2. **Tasks** — All recurring + one-off tasks, filterable by cadence/status
3. **Inbox** — AI-extracted action items from all sources, triage view
4. **Calendar** — Unified calendar view (Google + Apple merged)
5. **Settings** — Integrations, notification preferences, task configuration

---

## Technical Architecture

### Backend
- **Framework**: FastAPI (Python) — consistent with existing fitness app stack
- **Database**: PostgreSQL
- **AI**: Claude API for communication analysis and action item extraction
- **Task scheduling**: Celery + Redis for background processing (polling integrations, generating briefings)
- **Deployment**: Railway

### iOS App
- **Framework**: SwiftUI
- **Local storage**: Core Data / SwiftData for offline support
- **Notifications**: APNs for push, UNUserNotificationCenter for local
- **HealthKit**: Not needed (unless tracking sleep for "rest" routines)
- **Calendar**: EventKit for native Apple Calendar access
- **Contacts**: ContactsKit for person-context reminders

### Web App
- **Framework**: Next.js (React)
- **Auth**: Shared JWT auth with backend
- **Real-time**: WebSocket for live updates to dashboard

### Integrations

| Service | Method | Scope |
|---------|--------|-------|
| Google Calendar | OAuth 2.0 / Google API | Read events |
| Gmail | OAuth 2.0 / Gmail API | Read emails, extract metadata |
| Apple Calendar | EventKit (iOS) / CalDAV (web) | Read events |
| Apple Mail | Not directly accessible — use IMAP or Mail.app rules | Read emails |
| iMessage | Not directly accessible via API — iOS shortcuts or on-device only | Limited |
| Slack | Slack OAuth / Bot API | Read channels, DMs, mentions |
| Discord | Discord Bot API | Read servers, DMs, mentions |
| Apple Notes | No public API — CloudKit private DB or Shortcuts | Limited |
| Notion | Notion API (OAuth) | Read pages, databases |
| GitHub | GitHub OAuth / REST + GraphQL API | PRs, issues, notifications |

**Note on Apple ecosystem limitations**: iMessage and Apple Notes lack public APIs. Options:
- Use iOS Shortcuts automations to bridge data
- On-device processing via App Intents / Siri Shortcuts
- For iMessage: Surface recent conversations but extraction is limited to what Shortcuts can provide
- For Apple Notes: Use Shortcuts to export tagged notes, or use Notion as primary notes platform

### Data Model

```
User
├── RecurringTask
│   ├── cadence (daily | weekly | monthly | custom)
│   ├── title, description
│   ├── time_window (start_time, end_time)
│   ├── missed_behavior (roll_forward | mark_missed)
│   ├── priority (non_negotiable | flexible)
│   └── TaskCompletion[] (date, completed_at, skipped, notes)
│
├── OneOffReminder
│   ├── title, description
│   ├── trigger_type (time | location | context | follow_up)
│   ├── trigger_config (JSON — time, coordinates, person_id, email_id)
│   ├── status (pending | completed | dismissed)
│   └── created_at, completed_at
│
├── ActionItem (AI-extracted)
│   ├── source (gmail | slack | imessage | notion | github)
│   ├── source_id, source_url
│   ├── title, description
│   ├── extracted_deadline (if detected)
│   ├── confidence_score
│   ├── status (new | acknowledged | actioned | dismissed)
│   ├── people[] (who's involved)
│   └── created_at, actioned_at
│
├── Briefing
│   ├── type (morning | evening)
│   ├── date
│   ├── content (structured JSON)
│   ├── generated_at
│   └── viewed_at
│
├── Integration
│   ├── provider (google | apple | slack | discord | notion | github)
│   ├── auth_token, refresh_token
│   ├── scopes
│   ├── last_synced_at
│   └── is_active
│
└── NudgePreference
    ├── aggressiveness (gentle | moderate | persistent)
    ├── quiet_hours (start, end)
    ├── channels (push | digest | both)
    └── per_task_overrides (JSON)
```

---

## Privacy & Security

- All communication data processed server-side via encrypted connections
- OAuth tokens stored encrypted at rest
- Email/message content is processed for action items then discarded — only extracted metadata is stored
- Option for on-device-only processing (iOS) for sensitive sources like iMessage
- User can revoke any integration at any time
- Clear data retention policy: raw sync data purged after 30 days, extracted items kept until user dismisses

---

## MVP Scope (Phase 1)

Focus on the highest-value features first:

1. **Recurring task management** — daily/weekly/monthly with configurable miss behavior
2. **Morning & evening briefings** — AI-generated summaries
3. **Google Calendar + Gmail integration** — most accessible APIs
4. **Push notifications + smart nudges**
5. **Basic web dashboard + iOS app**

### Phase 2
- Slack + GitHub integration
- Notion integration
- Follow-up tracking (unanswered emails)
- Location-based reminders (iOS)

### Phase 3
- Discord integration
- Apple Calendar/Mail via CalDAV/IMAP
- iMessage via Shortcuts bridge
- Apple Notes via Shortcuts
- Context-based reminders ("next time I talk to X")

---

## Open Questions

1. **Notification timing**: Should morning briefing be at a fixed time or adapt to your wake-up pattern?
2. **Shared tasks**: Will you ever need to assign/share tasks with others, or is this purely personal?
3. **Voice input**: Should the app support "Hey Siri, add a reminder to Chief of Staff" via App Intents?
4. **Widget**: iOS home screen widget showing today's non-negotiables and next action item?
5. **Apple Watch**: Worth building a watchOS companion for quick task check-offs?
6. **Offline mode**: How important is full offline functionality vs. always-connected?
