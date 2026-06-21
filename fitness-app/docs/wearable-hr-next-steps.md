# Wearable HR — Next Steps Spec

**Status:** Design / ready to implement
**Author:** Claude Code (web session), 2026-06-21
**Picks up from:** `b39fb9b` — *feat(backend): WHOOP API integration (Phase 1 wearable HR)*
**Parent doc:** [`wearable-heart-rate-quest-integration.md`](./wearable-heart-rate-quest-integration.md) (the original phased scoping)

> This is the "what to do next" companion to the scoping doc. It records exactly
> where the stage-one build ended, splits the remaining work into **web-session-doable
> (backend-only)** vs. **desktop/Xcode-bound**, and gives file-by-file task lists,
> API contracts, and acceptance criteria so the desktop session can one-shot each piece.

---

## 1. Where stage one ended (the baseline)

**Done and verified (backend, 299 tests green, ruff clean):**

- **Phase 0 — HR data foundation.** Per-set timing + `avg/peak_heart_rate` on `sets`;
  session HR summary on `workout_sessions` (`avg/peak_heart_rate`, `strain`, `kilojoules`,
  `hr_zone_seconds`, `hr_source`); new `heart_rate_samples` table; `heart_rate_service`
  attributes samples to sets by timestamp window; wired into `POST /workouts`.
- **HR-aware quests.** New `QuestType`s `HR_ZONE_TIME`, `PEAK_HR`, `SESSION_STRAIN`
  (`models/quest.py`); `workout_stats` emits `elevated_zone_minutes` / `peak_heart_rate` /
  `strain`; `quest_service` scores them and seeds definitions. **HR quests are excluded
  from the random daily pool** (`generate_daily_quests`, `HR_QUEST_TYPES` filter) so
  non-wearable users never get impossible quests.
- **Phase 1 — WHOOP API (backend).** `whoop_connections` table (tokens Fernet-encrypted
  at rest), OAuth connect/callback, token refresh, `POST /whoop/sync` pulls
  `/v1/activity/workout` and backfills session HR by **time overlap**, then re-runs
  quest recalculation so HR quests credit after the fact. Endpoints return **503 until
  `WHOOP_CLIENT_ID/SECRET/REDIRECT_URI` are set**. Setup: `docs/whoop-setup.md`.

**What this means:** the backend can already store and serve per-set + per-session HR and
credit HR quests. **Nothing is wired into the iOS app yet, and there is no watchOS target.**

### Backend contract the iOS app must consume

WHOOP endpoints (all `/api/...`, auth required except `/callback`):

| Endpoint | Returns |
|---|---|
| `GET /whoop/connect` | `{ "authorize_url": "https://..." }` |
| `GET /whoop/callback` | HTML page (browser redirect target — not called by the app) |
| `POST /whoop/sync?days=30` | `{ workouts_fetched, sessions_matched, sessions_updated, workouts_unmatched, updated_session_ids[], quests_completed[] }` |
| `GET /whoop/status` | `{ connected, configured, whoop_user_id?, scope?, expires_at?, last_synced_at? }` |

HR fields now present on workout responses (`schemas/workout.py`):

- **Session** (`WorkoutResponse` / `WorkoutSummaryResponse`): `avg_heart_rate: Int?`,
  `peak_heart_rate: Int?`, `strain: Double?`, `kilojoules: Double?`,
  `hr_zone_seconds: [String:Int]?` (e.g. `{"z2": 540}`), `hr_source: String?`.
- **Set** (`SetResponse`): `start_time: String?`, `end_time: String?`,
  `avg_heart_rate: Int?`, `peak_heart_rate: Int?`.

---

## 2. Work split: web session vs. desktop

| Item | Where | Why |
|---|---|---|
| **1.5 — Wearable-gated quest generation** | ✅ Web session (backend-only) | Pure Python; no Xcode. Closes the "HR quests for connected users" TODO. |
| **1.6 — Sync scheduling / freshness** (optional) | ✅ Web session (backend-only) | Background/cron sync; no Xcode. |
| **1A — iOS WHOOP connect flow** | 🖥️ Desktop (Xcode) | SwiftUI + `xcodegen` + build check. |
| **1B — iOS HR display wiring** | 🖥️ Desktop (Xcode) | `APITypes.swift` + views; build check. |
| **2 — Apple Watch live HR (watchOS target)** | 🖥️ Desktop (Xcode) | New target, provisioning, on-device HealthKit. |
| **3 — Exertion analytics** | Mixed | Backend math = web; charts = desktop. |

> Recommendation: knock out **1.5** in this/next web session (it makes the feature
> actually useful for a connected WHOOP user), then do **1A + 1B** together on desktop
> as the first Xcode sitting. **Phase 2 (watchOS)** is the big desktop project.

---

## 3. Phase 1.5 — Wearable-gated quest generation *(web-session-doable now)*

**Problem:** HR quests exist and seed, but `generate_daily_quests` filters them out for
everyone (`QuestDefinition.quest_type.notin_(HR_QUEST_TYPES)`), so a connected WHOOP user
never sees an HR quest in their daily 3.

**Goal:** if (and only if) the user has a usable wearable, allow HR quests into the daily pool.

**Design:**
1. Add a helper `user_has_wearable(db, user_id) -> bool` in `quest_service.py` (or a small
   `wearable_service`). True when **either**:
   - a `whoop_connections` row exists for the user (`whoop_service.get_connection`), **or**
   - the user has logged any session with `hr_source` set in the last N days (covers Apple
     Watch / screenshot HR without a WHOOP link).
2. In `generate_daily_quests`, drop the `notin_(HR_QUEST_TYPES)` filter when
   `user_has_wearable` is true; optionally cap HR quests to **at most 1 of the 3** so the
   day isn't all-cardio.
3. Keep the async-credit path intact: HR quests can still complete on `POST /whoop/sync`
   (already idempotent via `recalculate_quest_progress`).

**Files:** `backend/app/services/quest_service.py` (primary),
`backend/app/services/whoop_service.py` (reuse `get_connection`).

**Acceptance:**
- A user with a WHOOP connection gets 0–1 HR quests in their daily set; a user without any
  wearable gets none (existing behavior preserved).
- New unit tests: `generate_daily_quests` with/without a wearable; the "≤1 HR quest" cap.
- Full suite still green; ruff clean.

**Risk:** don't assign an HR quest to a WHOOP user whose data only arrives post-sync — that's
fine (it credits on sync), but verify the daily-quest UX shows 0% until sync rather than
looking broken. Note for the iOS session.

---

## 4. Phase 1A — iOS "Connect WHOOP" flow *(desktop / Xcode)*

**Goal:** user can connect WHOOP from the app, trigger a sync, and see connection status.

**Placement:** new row in `Views/Profile/ProfileView.swift` → `SystemSettingsSection`
("Connect WHOOP" / "WHOOP Connected · last synced …"). Mirror the existing settings-row
styling (ARISE aesthetic).

**OAuth flow (browser round-trip):**
1. App calls `GET /whoop/connect` → gets `authorize_url`.
2. Open it with `ASWebAuthenticationSession` (preferred — handles the callback cleanly) or
   `SFSafariViewController` / `openURL`.
3. WHOOP redirects to the backend `GET /whoop/callback`, which stores tokens and shows the
   styled confirmation page (already built).
4. App returns to foreground → re-fetch `GET /whoop/status`; if `connected`, show connected
   state and offer **Sync now** (`POST /whoop/sync`).

> The callback lands on the **backend**, not a deep link into the app, so the app can't
> observe completion directly. Poll `GET /whoop/status` on `scenePhase` → `.active` after
> launching the auth session (or after `ASWebAuthenticationSession` returns).

**New iOS files / changes:**
- `Services/APITypes.swift`: `WhoopConnectResponse { authorize_url }`,
  `WhoopStatusResponse { connected, configured, whoop_user_id?, scope?, expires_at?, last_synced_at? }`,
  `WhoopSyncResponse { workouts_fetched, sessions_matched, sessions_updated, workouts_unmatched, quests_completed[] }`.
- `Services/APIClient.swift`: `whoopConnect()`, `whoopStatus()`, `whoopSync(days:)`.
- `Views/Profile/` (or a new `Views/Settings/WhoopConnectionView.swift`): the connect row +
  status + "Sync now" button + result toast ("Synced 3 workouts, 1 quest completed").
- Handle `configured == false` (503): show "WHOOP not available yet" disabled state instead
  of an error.

**Unmatched-workout attach UI (Decision D1, option c):** when a sync returns WHOOP workouts
with no matching app session, let the user **attach** one to an existing session or **dismiss**
it — don't auto-create sessions.
- *Backend prerequisite (web-session-doable, do before 1A):* extend `POST /whoop/sync` to return
  unmatched workout **details** (WHOOP id, sport/activity, start/end, strain, avg/peak HR), and
  add a way to **attach** a WHOOP workout to a chosen session (e.g. `POST /whoop/attach`
  `{whoop_workout_id, session_id}` → applies the HR summary + recalcs quests) and to **dismiss**
  one so it stops resurfacing (persist dismissed WHOOP ids per user). Today sync only returns
  `workouts_unmatched` as a count.
- *iOS:* after "Sync now", if unmatched details are present, show a small review list →
  Attach (pick a recent session) / Dismiss. Non-blocking; matched workouts still backfill silently.

**Acceptance:** connect → browser → backend confirmation → app shows Connected; "Sync now"
returns a result and any completed HR quests surface; unmatched WHOOP workouts appear for
attach/dismiss and, once attached, backfill HR + credit quests. `xcodegen generate` + simulator
build clean (`error:` grep empty) per `fitness-app/CLAUDE.md` build rule. Lint entitlements.

---

## 5. Phase 1B — iOS HR display wiring *(desktop / Xcode)*

**Goal:** surface the HR data the backend already returns.

**Per the CLAUDE.md "touch-all" workout-field rule**, add HR fields to every display layer:
- `Services/APITypes.swift`: add `avg_heart_rate`, `peak_heart_rate`, `strain`,
  `kilojoules`, `hr_zone_seconds`, `hr_source` to `WorkoutResponse` (and `strain` already on
  `WorkoutSummaryResponse` — add the rest); add `start_time`, `end_time`, `avg_heart_rate`,
  `peak_heart_rate` to `SetResponse`. (All optional — backward compatible.)
- `Views/Home/HomeView.swift`: recent-workout card shows avg/peak HR or strain when present.
- `Views/History/HistoryView.swift` + workout detail: HR summary row + per-zone breakdown
  (`hr_zone_seconds` → minutes per zone bar); per-set HR if present.
- `Components/`: a small `HRZoneBar` / `StatCard` HR variant (follow `{DesignSystem}{DataType}{ComponentType}` naming; grep before creating).
- Quest UI: `Components/DailyQuestsCard.swift` + `Components/QuestDetailSheet.swift` — emoji/
  label/icon for `hr_zone_time` / `peak_hr` / `session_strain`; ensure `QuestResponse` carries
  whatever the cards need (check current fields first).

**Acceptance:** a workout with HR shows avg/peak/strain + zone breakdown in Home + History +
detail; HR quests render with sensible icons/labels; no layout break when HR fields are nil.
Simulator build clean.

---

## 6. Phase 2 — Apple Watch live HR *(desktop / Xcode — the big one)*

True live HR during a workout **requires a watchOS companion app** (the one hard constraint
from the scoping doc — iPhone HealthKit alone cannot stream live HR).

**Scope:**
- New **watchOS app target** + shared-models setup in `ios/project.yml` (xcodegen).
- watchOS app runs `HKWorkoutSession` + `HKLiveWorkoutBuilder`, subscribes to
  `HKQuantityType(.heartRate)`, streams BPM to the phone via `WCSession`, and records **set
  boundaries live** (exact per-set mapping — the best-case alignment).
- `Services/HealthKitManager.swift`: add `.heartRate` (and `.restingHeartRate`,
  `.heartRateVariabilitySDNN`) to `readTypes` (currently only steps/energy/exercise time).
- iOS batches samples + per-set `start_time`/`end_time` + summaries into the workout
  create/update payload (`heart_rate_samples[]` + set timing are **already accepted** by
  `schemas/workout.py` / `POST /workouts` from Phase 0 — backend is ready).
- Live HR UI during an active workout.

**Provisioning gotcha (verify first):** watchOS workout background entitlements vs. the
existing "minimal entitlements for personal team" decision (`FitnessApp.entitlements`,
`ios/scripts/lint-entitlements.sh`). **No Apple Pay entitlement, ever** (CLAUDE.md). Confirm
the workout-processing background mode is available on the current provisioning before
committing the target.

**Acceptance:** start a workout on the watch → live BPM on-wrist and mirrored to phone →
finish → samples + per-set HR land via `POST /workouts` → per-set analytics populate with
exact (not inferred) set windows.

---

## 7. Phase 3 — Exertion analytics *(later; backend math = web, charts = desktop)*

Per-set work density, HR recovery between sets (`hr_recovery_60s` already scoped as a
nullable column), cardiovascular cost per lift, session-efficiency trends. Feed into the
strength-coach reporting + iOS Progress views. The raw `heart_rate_samples` table exists
precisely so these can be recomputed without re-ingesting.

**Open:** raw-sample retention/downsampling (~1 Hz → ~3,600 rows/hr) before this scales.

---

## 8. Sequencing & open questions

**Suggested order:** 1.5 (web) → 1A + 1B (desktop, one sitting) → 2 (desktop, multi-session)
→ 3 (later).

**Decisions to confirm before/while building:**
1. **Live-HR appetite.** If live HR mid-workout is must-have *now*, Phase 2 jumps ahead of the
   1A/1B polish. Current order assumes analytics value first.
2. **WHOOP credentials.** `GET /whoop/status.configured` is `false` until Railway env vars are
   set + a WHOOP developer app is approved (`docs/whoop-setup.md`). Sync can't be tested
   end-to-end until then — 1A should degrade gracefully meanwhile.
3. **Network egress.** Railway must allow outbound to `api.prod.whoop.com`.
4. **Async quest crediting UX.** HR quests complete on sync (minutes after the workout) —
   decide notification vs. silent backfill so the daily card at 0% pre-sync doesn't look broken.
5. **HR-quest cap** in the daily pool (recommend ≤1 of 3).
6. **Unmatched WHOOP workouts (Decision D1). ✅ RESOLVED.** Keep current drop-and-count behavior
   now; add a **surface & attach/dismiss** UI as part of Phase 1A (below); synthetic sessions
   deferred. See `wearable-heart-rate-quest-integration.md` → Resolved decisions.

**Key files (quick reference):**
`backend/app/services/quest_service.py` · `…/whoop_service.py` · `…/workout_stats.py` ·
`backend/app/api/whoop.py` · `backend/app/schemas/workout.py` ·
`ios/FitnessApp/Services/APITypes.swift` · `…/APIClient.swift` ·
`…/Services/HealthKitManager.swift` · `…/Views/Profile/ProfileView.swift` ·
`…/Components/DailyQuestsCard.swift` · `ios/project.yml` · `docs/whoop-setup.md`
</content>
</invoke>
