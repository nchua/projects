# Jarvis — AI-Powered Personal Chief of Staff

A desktop web app that acts as your morning command center. It syncs your email, Slack, GitHub, calendar, and meeting notes — then uses AI to extract action items, surface contextual memory, and rank everything by what actually matters to you.

**What makes it different:** Jarvis learns from your behavior. It tracks which items you dismiss, which contacts matter most, and which sources produce noise — then adapts its filtering and ranking automatically. No prompt engineering, no manual rules.

## Interactive Walkthrough

Open **[`walkthrough.html`](walkthrough.html)** in your browser for a visual, 5-scene walkthrough showing:

1. **Morning Briefing** — the full dashboard with memory context, reranked action items, and AI insights
2. **Smart Reranking** — how composite scoring demotes a spammy newsletter from #1 to last place
3. **Memory Supersession** — when Alice pushes a deadline, the old fact is retired automatically
4. **Adaptive Triage** — how dismissal patterns raise confidence thresholds per source
5. **After 2 Weeks** — memory decay, contact scores, and the noise reduction feedback loop

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Tauri Desktop Shell (optional — macOS native)                   │
│  System Tray · ⌘J Spotlight · Notifications · Auto-launch        │
├──────────────────────────────────────────────────────────────────┤
│  Next.js Frontend (port 3000 / static export)                    │
│  Dashboard: Tasks · Action Items · Calendar · Insights · Context │
└──────────────────────┬───────────────────────────────────────────┘
                       │ REST API
┌──────────────────────▼───────────────────────────────────────────┐
│  FastAPI Backend (port 8000)                                     │
│  ┌──────────┐ ┌──────────────┐ ┌─────────────┐ ┌──────────────┐ │
│  │ Auth     │ │ Briefings    │ │ Action Items│ │ Memory API   │ │
│  │ (JWT)    │ │ (rule + AI)  │ │ (CRUD)      │ │ (CRUD)       │ │
│  └──────────┘ └──────────────┘ └─────────────┘ └──────────────┘ │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ Services Layer                                               ││
│  │ · Extraction (Haiku triage → Sonnet extract)                 ││
│  │ · Memory (Haiku extract → Mem0 CRUD → Zep temporal)          ││
│  │ · Triage Rules (adaptive thresholds from dismissal patterns) ││
│  │ · Prioritization (RFM contact scoring + composite ranking)   ││
│  │ · Briefing Engine (rule-based assembly + Claude insights)    ││
│  └──────────────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ ARQ Worker (background)                                      ││
│  │ · Sync connectors (Gmail, GitHub, Slack, Granola)            ││
│  │ · AI extraction pipeline                                     ││
│  │ · Memory fact extraction (parallel with action extraction)   ││
│  │ · Daily cleanup + memory decay cron                          ││
│  └──────────────────────────────────────────────────────────────┘│
└──────────────────────┬───────────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
     PostgreSQL     Redis      Claude API
     (data)       (job queue)  (Haiku + Sonnet)
```

## Key Features

### Contextual Memory (Mem0 + Zep pattern)
- Extracts commitments, deadlines, decisions, and follow-ups from every message
- **Mem0 CRUD**: new facts are ADD, updated facts are UPDATE (old fact retired, linked via `superseded_by_id`), duplicates are NOOP
- **Bi-temporal timestamps**: `valid_from` / `valid_until` for fact validity, `extracted_at` / `invalidated_at` for system lifecycle
- **Exponential decay**: importance fades over time if facts aren't accessed; archived below 0.05
- Costs ~$0.0002/message (Haiku)

### Adaptive Triage (structured rules, not prompt injection)
- Per-source confidence thresholds that escalate based on dismissal patterns
- Cold start protection: no adaptation until 20+ dismissals per source
- Sender suppression: contacts with >70% dismissal rate are auto-filtered
- Deterministic, testable, debuggable — no LLM in the filtering loop

### Smart Prioritization (RFM-based)
- **Contact importance**: recency (30-day half-life decay) × frequency (log-normalized) × dismissal penalty
- **Composite action item score**: 30% priority + 25% contact importance + 20% source reliability + 15% extraction confidence + 10% deadline urgency
- Scores computed at query time so deadline urgency stays current

### Morning Briefings
- Rule-based assembly: calendar, recurring tasks, action items, integration health
- Memory context injected into AI prompt for cross-day awareness
- Claude Sonnet generates priority ranking, risk flags, and focus suggestion
- Graceful degradation: briefing always generates even without API key

## Setup — Local Development

### Prerequisites

- Python 3.11+
- Node.js 18+
- Redis (for background worker — optional for basic usage)

### 1. Clone

```bash
git clone https://github.com/nchua/projects.git
cd projects/chief-of-staff
```

### 2. Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env   # then edit .env (see Environment Variables below)

# Create database (SQLite for local dev)
python3 -c "from app.core.database import Base, engine; import app.models; Base.metadata.create_all(bind=engine)"

# Run the server
python3 main.py
# → http://localhost:8000
# → http://localhost:8000/docs (Swagger UI)
```

### 3. Frontend

```bash
cd web

# Install dependencies
npm install

# Configure API URL
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1' > .env.local

# Run dev server
npm run dev
# → http://localhost:3000
```

### 4. Desktop App (optional — macOS)

Wraps the frontend in a native macOS shell with system tray, global shortcut, and notifications.

**Prerequisites:** Rust toolchain (`curl --proto '=https' --tlsv1.2 https://sh.rustup.rs -sSf | sh`)

```bash
cd web

# Install Tauri dependencies (already in package.json)
npm install

# Development — opens native window loading localhost:3000
npm run tauri:dev

# Production build — produces Jarvis.app + .dmg
npm run tauri:build
# Output: web/src-tauri/target/release/bundle/dmg/Jarvis_*.dmg
```

**Desktop features:**
- **System tray** — menubar icon with briefing popup (polls every 60s, red dot when unviewed)
- **⌘J global shortcut** — spotlight-style search overlay, works from any app
- **Native notifications** — fires when morning briefing is ready or new context is detected
- **Auto-launch on login** — toggle in Settings (only visible in desktop app)

The backend still runs separately — the desktop app just wraps the frontend.

### 5. Background Worker (optional)

The ARQ worker handles integration sync, AI extraction, and memory fact extraction. Without it, you can still use the app manually (create action items, memory facts, briefings via API).

```bash
# Requires Redis running locally
redis-server &

# In the backend directory with venv activated:
arq app.worker.WorkerSettings
```

### 6. Register and Login

Open `http://localhost:3000` → register an account → log in. The dashboard will show empty cards until you add data.

To test with the API directly:
```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"YourPass123!"}'

# Login (save the access_token)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"YourPass123!"}'

# Create a memory fact
curl -X POST http://localhost:8000/api/v1/memory \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"fact_text":"Launch demo is next Friday","fact_type":"deadline","importance":0.9}'

# Preview a briefing
curl -X POST http://localhost:8000/api/v1/briefings/preview \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

## Environment Variables

Create `backend/.env` with:

```bash
# Required
SECRET_KEY=your-random-secret-key-here          # python3 -c "import secrets; print(secrets.token_urlsafe(32))"
DATABASE_URL=sqlite:///./chief_of_staff.db      # SQLite for local, PostgreSQL for production

# AI (required for memory extraction + briefing insights)
ANTHROPIC_API_KEY=sk-ant-...                    # Get from console.anthropic.com

# OAuth token encryption (required for integrations)
TOKEN_ENCRYPTION_KEY=...                        # python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Google OAuth (for Gmail + Calendar sync)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# GitHub OAuth (for notification sync)
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...

# Slack OAuth (for message sync)
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
SLACK_SIGNING_SECRET=...

# Redis (for background worker)
REDIS_URL=redis://localhost:6379/0

# Optional
CORS_ORIGINS=["http://localhost:3000"]
GRANOLA_CACHE_PATH=                             # Path to Granola's cache-v6.json if using Granola
```

### 7. Google API Setup (required for Gmail + Google Calendar sync)

The Google OAuth credentials alone aren't enough — you also need to enable the APIs in your GCP project:

1. Go to [Google Cloud Console → APIs & Services → Library](https://console.cloud.google.com/apis/library)
2. Select the GCP project that owns your OAuth credentials
3. Search for and **Enable** each of these APIs:
   - **Google Calendar API** — required for calendar event sync
   - **Gmail API** — required for email sync and action item extraction
4. No code changes needed — the existing OAuth tokens will work once the APIs are enabled

Without this step, sync will return HTTP 403 `accessNotConfigured`.

### 8. Apple Calendar (macOS only)

Apple Calendar sync uses AppleScript and requires no OAuth or API keys. On first sync, macOS will prompt you to grant Calendar access to the terminal/app running the backend. Accept the prompt, or enable it manually:

**System Settings → Privacy & Security → Calendars** → toggle on your terminal app.

## Setup — Production Deployment

For deploying to a cloud provider (Railway, Render, Fly.io, etc.):

### Database

Use PostgreSQL instead of SQLite:

```bash
DATABASE_URL=postgresql://user:password@host:5432/jarvis
```

Most cloud providers offer managed Postgres. On Railway: add a PostgreSQL plugin and it sets `DATABASE_URL` automatically.

### Backend Deployment

1. **Set all environment variables** from the section above on your cloud provider
2. **Build command**: `pip install -r requirements.txt`
3. **Start command**: `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}`
4. **Create tables** on first deploy:
   ```bash
   # Via Railway CLI or your provider's shell:
   python3 -c "from app.core.database import Base, engine; import app.models; Base.metadata.create_all(bind=engine)"
   ```

### Redis

Required for the background worker. Most cloud providers offer managed Redis (Railway: add Redis plugin, Render: add Redis instance). Set `REDIS_URL` to the provided connection string.

### Worker

The ARQ worker needs to run as a separate process alongside the web server:
- **Start command**: `arq app.worker.WorkerSettings`
- Same environment variables as the backend
- Needs access to both PostgreSQL and Redis

On Railway, add a second service in the same project pointing to the same repo but with the worker start command.

### Frontend Deployment

Deploy the `web/` directory to Vercel, Netlify, or any Next.js host:

1. **Root directory**: `chief-of-staff/web`
2. **Build command**: `npm run build`
3. **Environment variable**: `NEXT_PUBLIC_API_URL=https://your-backend-url.com/api/v1`

On Vercel: connect your GitHub repo, set the root directory to `chief-of-staff/web`, add the env var, deploy.

### OAuth Redirect URIs

Update your OAuth app configurations (Google Cloud Console, GitHub Developer Settings, Slack API) to include your production callback URL:

```
https://your-frontend-url.com/callback
```

Set `OAUTH_REDIRECT_URIS` on the backend to restrict allowed redirect URIs:
```bash
OAUTH_REDIRECT_URIS=["https://your-frontend-url.com/callback"]
```

## API Reference

| Group | Endpoint | Description |
|-------|----------|-------------|
| **Auth** | `POST /api/v1/auth/register` | Create account |
| | `POST /api/v1/auth/login` | Get JWT tokens |
| | `GET /api/v1/auth/me` | Current user |
| **Memory** | `GET /api/v1/memory` | List active memory facts |
| | `POST /api/v1/memory` | Add manual memory fact |
| | `DELETE /api/v1/memory/{id}` | Soft-delete a fact |
| **Briefings** | `GET /api/v1/briefings/today` | Today's briefing |
| | `POST /api/v1/briefings/preview` | Generate preview |
| **Action Items** | `GET /api/v1/action-items` | List (filterable) |
| | `POST /api/v1/action-items` | Create manually |
| | `POST /api/v1/action-items/{id}/dismiss` | Dismiss with reason |
| | `GET /api/v1/action-items/stats/dismissals` | Dismissal analytics |
| **Tasks** | `GET /api/v1/tasks/today` | Today's unified view |
| | `GET /api/v1/tasks/recurring` | Recurring tasks |
| **Integrations** | `GET /api/v1/integrations` | List connected |
| | `POST /api/v1/integrations/google/authorize` | Start Google OAuth |
| | `POST /api/v1/integrations/github/authorize` | Start GitHub OAuth |
| | `POST /api/v1/integrations/slack/authorize` | Start Slack OAuth |

Full interactive docs at `http://localhost:8000/docs` (Swagger UI).

## Running Tests

```bash
cd backend
python3 -m pytest tests/ -v    # 167 tests
```

```bash
cd web
npm run build                  # TypeScript + Next.js compilation check
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React, TypeScript, Tailwind CSS, SWR |
| Desktop | Tauri v2 (Rust), macOS native shell |
| Backend | FastAPI, SQLAlchemy, Pydantic, Alembic |
| AI | Claude Haiku 4.5 (triage + memory), Claude Sonnet 4.5 (extraction + insights) |
| Database | SQLite (dev), PostgreSQL (prod) |
| Queue | Redis + ARQ |
| Auth | JWT (access + refresh tokens), bcrypt, Fernet encryption for OAuth tokens |

## Research Sources

The memory and adaptive triage systems are informed by:

- **Mem0**: ADD/UPDATE/NOOP pattern for fact lifecycle management
- **Zep/Graphiti**: Bi-temporal timestamps, 94.8% accuracy on memory benchmarks
- **SaneBox**: Per-sender frequency analysis for adaptive filtering
- **Gmail Priority Inbox**: Per-user logistic regression with transfer learning
- **RFM (Recency-Frequency-Monetary)**: Framework underlying all contact scoring
- **MIT 2026**: Research showing prompt-based personalization leads to sycophancy — structured rules are more robust
