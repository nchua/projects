# WHOOP API Setup (Phase 1 wearable HR)

How to register a WHOOP developer app and wire its credentials into the backend.
The backend reads all secrets from environment variables — **never hardcode
them** (per CLAUDE.md security rules).

## 1. Register a WHOOP developer app

1. Sign in at **<https://developer.whoop.com>** with a WHOOP account.
2. Open the **Developer Dashboard** → **Create New App** (you may need to create
   a team first).
3. Fill in the app details:
   - **Name:** e.g. `ARISE Fitness`
   - **Scopes:** select at minimum
     - `read:workout` — pull workout HR summaries + zones
     - `read:profile` — read the WHOOP `user_id`
     - `offline` — receive a **refresh token** (required for background sync;
       without it the access token expires in ~1 hour and can't be renewed)
   - **Redirect URIs:** add the exact callback URL(s). It must match
     `WHOOP_REDIRECT_URI` **byte-for-byte**, including scheme and path:
     - Production: `https://backend-production-e316.up.railway.app/whoop/callback`
     - Local dev: `http://localhost:8000/whoop/callback`
4. Save. WHOOP shows a **Client ID** and **Client Secret** — copy both. The
   secret is shown once; regenerate it from the dashboard if you lose it.

> WHOOP developer apps require approval/keys; access and rate limits are governed
> by WHOOP. See the API reference at <https://developer.whoop.com/api>.

## 2. Set the environment variables

### Railway (production)

In the backend service → **Variables**, add:

| Variable | Value |
|---|---|
| `WHOOP_CLIENT_ID` | from the WHOOP dashboard |
| `WHOOP_CLIENT_SECRET` | from the WHOOP dashboard |
| `WHOOP_REDIRECT_URI` | `https://backend-production-e316.up.railway.app/whoop/callback` |

Optional overrides (sensible defaults already in `app/core/config.py`):

| Variable | Default |
|---|---|
| `WHOOP_SCOPES` | `offline read:profile read:workout` |
| `WHOOP_AUTH_URL` | `https://api.prod.whoop.com/oauth/oauth2/auth` |
| `WHOOP_TOKEN_URL` | `https://api.prod.whoop.com/oauth/oauth2/token` |
| `WHOOP_API_BASE_URL` | `https://api.prod.whoop.com/developer` |

### Local development (`backend/.env`)

```
WHOOP_CLIENT_ID=your-client-id
WHOOP_CLIENT_SECRET=your-client-secret
WHOOP_REDIRECT_URI=http://localhost:8000/whoop/callback
```

When `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` / `WHOOP_REDIRECT_URI` are unset,
the WHOOP endpoints return **503 Service Unavailable** and the rest of the app
works normally — so you can deploy this code before you have credentials.

## 3. Run the migration

A new `whoop_connections` table stores each user's OAuth tokens (encrypted at
rest with Fernet, keyed off `SECRET_KEY`).

```bash
cd backend
alembic upgrade head   # applies add_whoop_connections (chained off add_wearable_hr)
```

## 4. OAuth + sync flow

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /whoop/connect` | Bearer | Returns `{ "authorize_url": ... }`; open it in a browser |
| `GET /whoop/callback?code=&state=` | none | WHOOP redirect target; exchanges the code, stores tokens |
| `POST /whoop/sync?days=30` | Bearer | Pulls recent WHOOP workouts, backfills matching sessions' HR, re-credits HR quests |
| `GET /whoop/status` | Bearer | `{ connected, whoop_user_id, scope, expires_at, last_synced_at }` |

End-to-end:

1. App calls `GET /whoop/connect` and opens the returned `authorize_url`.
2. User authorizes on WHOOP; WHOOP redirects to `/whoop/callback` with a signed
   `state` (so the callback knows which user) and an authorization `code`.
3. Backend exchanges the code for an access + refresh token and stores an
   (encrypted) `WhoopConnection`.
4. App calls `POST /whoop/sync`. The backend pulls recent WHOOP workouts
   (`GET /v1/activity/workout`), matches each to an app `WorkoutSession` by
   **time overlap**, and backfills the session's `avg_heart_rate`,
   `peak_heart_rate`, `strain`, `kilojoules`, and `hr_zone_seconds` (derived from
   WHOOP's `zone_duration` milli fields). It then re-runs
   `recalculate_quest_progress` for each affected day so HR-based quests get
   credited (HR arrives *after* the workout was logged).

## What WHOOP provides (and doesn't)

WHOOP's API returns a **session-level** summary + HR-zone durations, **not** raw
per-second HR samples. So this path populates session-level fields only. Per-set
HR granularity comes from the Apple Watch companion app (Phase 2).
