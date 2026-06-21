# Wearable Heart Rate → Quest Integration (Scoping)

**Status:** Scoping / design — no code written yet
**Branch:** `claude/wearable-health-quest-integration-li4wah`
**Author:** Claude Code session, 2026-06-20
**Decision locked:** Both sources (user wears Apple Watch + WHOOP). Build the
watchOS companion app (none exists today) for live HR.

## Build progress

- ✅ **Phase 0 — backend foundation (DONE, verified, committed):** per-set
  timing + avg/peak HR on `sets`; session HR summary on `workout_sessions`
  (avg/peak HR, strain, kilojoules, `hr_zone_seconds`, `hr_source`); new
  `heart_rate_samples` table; `heart_rate_service.ingest_heart_rate` (persists
  samples, attributes to sets **by timestamp window**, rolls up avg/peak);
  wired into `POST /workouts`; HR-aware `workout_stats` + `quest_service` with
  `HR_ZONE_TIME` / `PEAK_HR` / `SESSION_STRAIN` quest types + seeds (kept out
  of the random daily pool — wearable-gated, follow-up); Alembic migration
  unifies the 4 divergent heads + adds the schema. Verified via the full
  backend test suite + an end-to-end HR-attribution test.
- ✅ **Phase 1 — WHOOP API (DONE, backend; needs credentials to go live):**
  `whoop_connections` table (tokens encrypted at rest with Fernet keyed off
  `SECRET_KEY` — `app/core/crypto.py`); `whoop_service` with OAuth authorize-URL
  generation, code→token exchange, token refresh, and a sync that pulls
  `GET /v1/activity/workout` (httpx) and backfills each matching session's HR
  summary (avg/peak HR, strain, kJ, `hr_zone_seconds` from WHOOP's
  `zone_duration` milli fields) by **time overlap** — session-level only (WHOOP
  gives a summary + zones, not raw samples; per-set is the Watch's job). After a
  sync updates a session's HR it re-runs `recalculate_quest_progress` for that
  day so HR quests credit (HR arrives after the workout was logged). Router
  `app/api/whoop.py` (`GET /whoop/connect`, `GET /whoop/callback`,
  `POST /whoop/sync`, `GET /whoop/status`); config in `app/core/config.py`
  (`WHOOP_CLIENT_ID/SECRET/REDIRECT_URI` from env — never hardcoded); Alembic
  migration `add_whoop_connections` chained off `add_wearable_hr`. Endpoints
  return 503 until credentials are set, so this ships before WHOOP signup.
  Setup: `docs/whoop-setup.md`. Verified via the backend test suite +
  `tests/test_whoop_service.py` (encryption, OAuth state, zone mapping,
  time-overlap matching, end-to-end sync crediting an HR quest).
- ⏳ **Phase 2 — Apple Watch live HR + watchOS app:** not started (needs Xcode
  to build — done on the desktop). iOS HealthKit live-HR reads,
  `APITypes.swift` / display wiring, watchOS companion target.

### Refinements made during Phase 0 (supersede earlier notes below)
- HR samples are attributed to sets **purely by timestamp window**, not by
  `set_number` (which is only unique within an exercise).
- `hr_zone_seconds` is supplied by the client/provider (WHOOP returns zones;
  the Watch app computes them on-device from the user's max HR). The backend
  stores them rather than guessing max HR.
- HR quests are **excluded from the random daily pool** until wearable-gated
  generation exists, so non-wearable users don't get impossible quests.

### Refinements made during Phase 1 (supersede earlier notes below)
- **WHOOP is session-level only — there is NO per-set HR from WHOOP.** The
  `/v1/activity/workout` endpoint returns an aggregate *summary* (avg/max HR,
  strain, kJ) + HR-zone *durations* — **not** a per-second HR timeseries. So the
  earlier "Phase 1 post-hoc per-set alignment" idea (slice a WHOOP HR series into
  set windows) is **not possible** for WHOOP and was dropped. Phase 1's WHOOP
  deliverable is HR/strain in quests + **session-level** analytics, not per-set.
  *(Per-set HR **is** possible from Apple Watch — see Decision D3 below — because
  HealthKit exposes raw HR samples even without a companion app.)*
- **Session matching is greatest-overlap, and unmatched WHOOP workouts are
  counted, not absorbed.** `sync_recent_workouts` picks the app session with the
  most time overlap; if none overlaps it increments `workouts_unmatched` and moves
  on. The earlier idea to **create a synthetic session** for unmatched workouts (à
  la the screenshot path) or **attach to the nearest within a tolerance** was **not
  built** — see Open Decision D1 below. Backfill is **non-destructive** (won't
  clobber existing Apple-Watch/screenshot HR) and **skips unscored** WHOOP workouts
  (`score_state != "SCORED"`).
- **Quest types built:** `HR_ZONE_TIME`, `PEAK_HR`, `SESSION_STRAIN`. The earlier
  `HR_AVG_SESSION` candidate was **not** built (add later only if wanted).
- **`whoop_connections` carries more than first scoped:** also `scope`,
  `last_synced_at`, `whoop_user_id`; access/refresh tokens are **Fernet-encrypted
  at rest** (`app/core/crypto.py`, keyed off `SECRET_KEY`). OAuth `state` is a
  signed JWT so the browser callback recovers the user.
- **WHOOP v1 + v2 key names** both handled for zone durations (`zone_duration` /
  `zone_durations`).

## Goal

Bring wearable heart-rate (and downstream exertion) data into the app so we can:

1. **Short term:** Track heart rate during a workout and surface it in the quest/mission
   system (e.g. "spend 20 min in Zone 2", "hit a 15 strain session").
2. **Long term:** Map HR and other wearable analytics **to individual sets** so we can run
   exertion/recovery analytics per exercise and per set (work density, HR recovery between
   sets, cardiovascular cost of a lift, etc.).

---

## The one constraint that shapes everything

> **"Live" heart rate during a workout requires an Apple Watch + a watchOS companion app
> running an `HKWorkoutSession` / `HKLiveWorkoutBuilder`. The WHOOP API is post-workout only.**

- **iPhone HealthKit alone cannot stream live HR.** The current `HealthKitManager`
  (`ios/FitnessApp/Services/HealthKitManager.swift`) only runs `HKStatisticsQuery` for daily
  aggregates (steps, calories, exercise minutes, stand hours). There is **no watchOS target**
  in the project today (`ios/project.yml` defines a single iOS app target).
- **WHOOP has a real OAuth 2.0 cloud API** (`/v1/cycle`, `/v1/recovery`, `/v1/activity/workout`)
  that returns avg/max HR, strain, kJ, and HR-zone durations — but only **after** a workout
  syncs to WHOOP's cloud. It is **not** a live stream.

Implication for the phased plan:

| Capability | WHOOP API | Apple Watch + HealthKit |
|---|---|---|
| Live HR shown mid-set | ❌ No | ✅ Yes (watchOS app) |
| Post-workout avg/max HR + zones | ✅ Yes | ✅ Yes |
| Per-set HR time-alignment | ✅ (server-side, post-hoc) | ✅ (best — watch logs set boundaries live) |
| New watchOS target required | ❌ No | ✅ Yes |
| External dependency / auth | WHOOP account + OAuth | Apple Watch hardware only |

So **Phase 1 = WHOOP API** gets us HR-in-quests + per-set analytics fastest with no watchOS
work. **Phase 2 = Apple Watch app** adds true live HR and the most accurate per-set mapping.

---

## Current state (what already exists)

### Quest system
- **Backend models:** `backend/app/models/quest.py` — `QuestDefinition`
  (`quest_type` enum: `TOTAL_REPS`, `COMPOUND_SETS`, `TOTAL_VOLUME`, `EXERCISE_SPECIFIC`,
  `WORKOUT_DURATION`), `UserQuest` (progress/completed/claimed).
- **Logic:** `backend/app/services/quest_service.py` generates 3 daily quests and updates
  progress; `backend/app/services/workout_stats.py` computes `total_reps`, `compound_sets`,
  `total_volume` from a `WorkoutSession`.
- **Trigger point:** `backend/app/api/workouts.py` calls `update_quest_progress(db, user_id, workout)`
  after a workout is created (~line 340).
- **Missions** (`backend/app/models/mission.py`) can override daily quests.
- **iOS:** `Components/DailyQuestsCard.swift`, `Components/QuestDetailSheet.swift`,
  `Views/Quests/QuestsView.swift`; API models in `Services/APITypes.swift`
  (`QuestResponse`, `DailyQuestsResponse`, `QuestClaimResponse`).
- **Today quests use only:** rep count, compound-set count, total volume, workout count,
  exercise-specific progress. **No HR, no time-in-zone, no strain.**

### Wearable / health touchpoints today
- `HealthKitManager.swift` reads: `stepCount`, `activeEnergyBurned`, `basalEnergyBurned`,
  `appleExerciseTime`, `appleStandHour`. **Heart rate is NOT read.** Sync payload
  (`DailyHealthData.toActivityCreate()`) already has `nil` placeholders for `hrv`,
  `restingHeartRate`, `strain`, `recoveryScore`, `sleepHours`.
- `DailyActivity` model (`backend/app/models/activity.py`) already has columns: `strain`,
  `recovery_score`, `hrv`, `resting_heart_rate`, `sleep_hours` — **day-level only**, not
  per-workout or per-set.
- **WHOOP today is screenshot-based only.** `backend/app/services/screenshot_service.py`
  uses Claude Vision to extract `activity_type`, `strain`, `avg_hr`, `max_hr`,
  `heart_rate_zones[]` from WHOOP screenshots and stores them on a `DailyActivity` +
  a synthetic `WorkoutSession`. There is **no WHOOP API connection.**
- Entitlements/permissions: `com.apple.developer.healthkit: true` is set
  (`ios/FitnessApp/FitnessApp.entitlements`, `ios/project.yml`); `NSHealthShareUsageDescription`
  present. Restricted entitlements (background delivery) were intentionally removed for
  personal-team provisioning — **see "Background delivery" risk below.**

### Workout data model — the per-set mapping gap
- `backend/app/models/workout.py`: `WorkoutSession.date` (start), `duration_minutes`;
  `WorkoutExercise.order_index`; `Set` has `weight/reps/rpe/rir/set_number/e1rm/created_at`.
- **Critical gap:** a `Set` has **only `created_at`** (when it was logged, UTC). There is
  **no set start time and no set duration.** Sets are logged after the fact. To attribute
  HR samples to a specific set we must add timing, or infer it.

---

## Recommended architecture

### New data model

Rather than overloading day-level `DailyActivity`, introduce workout- and set-scoped HR data.

**1. Per-set timing + summary HR (new nullable columns on `sets`)** — backward compatible:

```python
# Set model additions
start_time            = Column(DateTime, nullable=True)  # set start (UTC)
end_time              = Column(DateTime, nullable=True)  # set end (UTC)
avg_heart_rate        = Column(Integer, nullable=True)   # BPM during set
peak_heart_rate       = Column(Integer, nullable=True)   # BPM during set
hr_recovery_60s       = Column(Integer, nullable=True)   # BPM drop 60s after set (long-term)
```

**2. Raw HR samples (new table)** — enables re-derivation of any per-set metric later:

```python
class HeartRateSample(Base):
    __tablename__ = "heart_rate_samples"
    id          = Column(String, primary_key=True)
    user_id     = Column(String, ForeignKey("users.id"), index=True)
    session_id  = Column(String, ForeignKey("workout_sessions.id", ondelete="CASCADE"), index=True)
    set_id      = Column(String, ForeignKey("sets.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp   = Column(DateTime, nullable=False, index=True)  # UTC
    bpm         = Column(Integer, nullable=False)
    source      = Column(String, nullable=False)  # "apple_watch" | "whoop" | "screenshot"
```

**3. Session-level wearable summary (new columns on `workout_sessions`)**:

```python
avg_heart_rate   = Column(Integer, nullable=True)
peak_heart_rate  = Column(Integer, nullable=True)
strain           = Column(Float,   nullable=True)   # WHOOP strain 0-21
kilojoules       = Column(Float,   nullable=True)
hr_zone_seconds  = Column(JSON,    nullable=True)   # {"z1": 120, "z2": 540, ...}
hr_source        = Column(String,  nullable=True)   # provenance
```

> Storing **both** raw samples and rolled-up summaries is deliberate: summaries power quests
> and fast reads; raw samples let us recompute per-set analytics as the algorithm evolves
> without re-ingesting. Add a retention/downsampling policy for raw samples later if volume
> grows (HR at ~1 Hz over a 60-min session ≈ 3,600 rows).

### Per-set time-alignment strategy (the hard part)

Given a session HR timeline and a set list, attribute samples to sets:

- **Phase 2 (Apple Watch, best):** the watchOS app records each set's `start_time`/`end_time`
  as the user logs it during the live `HKWorkoutSession`. Mapping is exact — slice samples by
  `[start_time, end_time]`.
- ~~**Phase 1 (WHOOP / post-hoc, good enough):** WHOOP gives a session HR series with timestamps
  but no set boundaries. Infer boundaries from `Set.created_at` ordering + `duration_minutes`...~~
  **SUPERSEDED (see Phase 1 refinements above):** WHOOP does **not** return an HR timeseries —
  only an aggregate summary, so there is nothing to slice into per-set windows. Per-set HR is
  **Phase 2 (Apple Watch) only**. The `Set.start_time/end_time` columns exist and are populated
  by the Watch path (exact boundaries), not inferred from WHOOP.

### WHOOP API integration (Phase 1)

- OAuth 2.0 Authorization Code flow. Add a `whoop_connections` table
  (`user_id`, `access_token`, `refresh_token`, `expires_at`, `whoop_user_id`).
- New backend module `backend/app/services/whoop_service.py` + `backend/app/api/whoop.py`:
  - `GET /whoop/connect` → returns WHOOP authorize URL
  - `GET /whoop/callback` → exchanges code, stores tokens
  - `POST /whoop/sync` → pull recent `/v1/activity/workout` + HR series, match to sessions
- **Secrets:** `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `WHOOP_REDIRECT_URI` as Railway env
  vars (per CLAUDE.md: never hardcode; use `os.environ.get`). Tokens encrypted at rest.
- **Network:** outbound calls to `api.prod.whoop.com` — confirm the remote/Railway egress
  policy allows it.
- **Session matching (as built):** match a WHOOP workout to the app `WorkoutSession` with the
  **greatest time overlap**. If none overlaps, the workout is **counted in
  `workouts_unmatched` and skipped** — no synthetic session, no nearest-within-tolerance
  fallback, no surfacing to the user yet. (The original "create a synthetic session / attach to
  nearest / surface ambiguous matches" plan was **not** built — see **Open Decision D1**.)

### Apple Watch live HR (Phase 2)

- Add a **watchOS app target** + a WatchConnectivity bridge in `ios/project.yml`
  (new `xcodegen` target, shared models).
- watchOS app starts an `HKWorkoutSession` + `HKLiveWorkoutBuilder`, subscribes to
  `HKQuantityType(.heartRate)`, streams BPM to the phone via `WCSession`, and records set
  boundaries as the user advances sets.
- Add `HKQuantityTypeIdentifier.heartRate` (and `.restingHeartRate`, `.heartRateVariabilitySDNN`)
  to `HealthKitManager.readTypes`.
- New `UIBackgroundModes` / workout-processing entitlement on the watch target. **Note** the
  prior decision to keep iOS entitlements minimal for personal-team provisioning — verify the
  watch workout entitlements are available on the current provisioning setup before committing.
- iOS batches samples + per-set summaries into the workout create/update payload.

### Quest system changes

- Extend `QuestType` enum with HR-driven types, e.g. `HR_ZONE_TIME` (minutes in a target zone),
  `PEAK_HR`, `SESSION_STRAIN`, `HR_AVG_SESSION`.
- Add zone/target metadata to `QuestDefinition` (e.g. `zone`, secondary `target_value`).
- Extend `workout_stats.calculate_workout_stats()` to emit HR metrics
  (`hr_zone_seconds`, `peak_hr`, `avg_hr`, `strain`) from the session's wearable summary.
- `update_quest_progress()` / `recalculate_quest_progress()` consume the new metrics.
- **Async caveat:** WHOOP HR arrives *after* the workout POST, so HR-based quests must be
  (re)evaluated on `POST /whoop/sync`, not only on workout creation. Make quest recalculation
  idempotent and callable from both paths. (For Apple Watch, HR is in the create payload, so
  the existing trigger works.)
- Seed new HR quest definitions via the existing `POST /quests/seed` path.
- iOS: add HR quest emoji/type handling in `DailyQuestsCard.swift` + `QuestDetailSheet.swift`;
  add HR fields to `QuestResponse` in `APITypes.swift`.

### Touch-all checklist (per CLAUDE.md workout-field rule)

When adding HR fields to sets/sessions, update **all** of:
`schemas/workout.py` → `api/workouts.py` → `services/workout_stats.py` →
`screenshot_service.py` (keep screenshot path consistent) → iOS `APITypes.swift` →
`HomeView.swift` / `HistoryView.swift` (+ quest components). Add an Alembic migration
(nullable columns; HR/WHOOP heads `add_wearable_hr` → `add_whoop_connections` are already
applied — chain new migrations off the current head, don't hardcode an old revision).
Remember the
**`joinedload` rule** before passing refreshed sessions into `update_quest_progress`.

---

## Phased plan

### Phase 0 — Foundations (backend only, ships independently)
- Alembic migration: HR columns on `sets` + `workout_sessions`, new `heart_rate_samples` table.
- Schema + API changes to accept/return HR fields (Apple Watch payload-ready, WHOOP-ready).
- Extend `workout_stats` + quest recalculation to be HR-aware (no-ops until data arrives).
- **Deliverable:** DB + API can store and serve per-set HR; nothing user-visible yet.

### Phase 1 — WHOOP API (no watchOS app) — ✅ backend done
- `whoop_connections` table, OAuth connect/callback, `whoop_service`, `POST /whoop/sync`.
- Session matching (greatest time overlap) — **session-level only** (WHOOP has no samples).
- New HR quest types + seeds; quest recalculation on sync.
- iOS (remaining): "Connect WHOOP" settings flow, HR display on workout detail + quest cards.
- **Deliverable:** HR/strain in quests and **session-level** HR analytics for WHOOP users
  (post-workout). *(Per-set analytics need raw samples — see Phase 1.7.)*

### Phase 1.7 — Apple Watch workout import via HealthKit (iOS, **no watchOS app**) — primary path for runs (D3)
- iOS `HealthKitManager`: add `.heartRate` + `HKObjectType.workoutType()` to read types; query
  completed `HKWorkout`s since last import and their raw HR samples
  (`HKQuery.predicateForObjects(from: workout)`); compute `hr_zone_seconds` on-device from max HR.
- Backend ingest endpoint (web-session-doable) that **reuses the screenshot path's
  activity→Cardio-exercise matching + session builder**: runs/cardio → `WorkoutSession` with a
  Cardio exercise + session HR summary (`hr_source="apple_watch"`); strength → match to a logged
  session by time overlap and attribute samples to sets via Phase-0 timestamp windows (per-set HR,
  no companion app). Dedup by HealthKit workout UUID.
- Reuse the D1 attach/dismiss flow for `HKWorkout`s that don't match a logged session.
- **Deliverable:** Apple-Watch runs logged with HR summaries + quest credit; **per-set HR for
  strength** — all without a watchOS target.

### Phase 2 (optional) — watchOS companion: live HR only
- Only needed for **live** mid-workout HR display + exact live set boundaries. Per-set HR is
  already covered by Phase 1.7, so this is a lower-priority enhancement.
- watchOS target + WatchConnectivity, `HKWorkoutSession`/`HKLiveWorkoutBuilder` live HR.
- **Deliverable:** true live HR mid-workout; most accurate (live) set boundaries.

### Phase 3 — Exertion analytics (long-term)
- Per-set work density, HR recovery between sets, cardiovascular cost per lift, session
  efficiency trends; feed into the strength-coach reporting and progress views.

---

## Resolved decisions (Phase 1 audit + roadmap)

- **D1 — Unmatched WHOOP workouts. ✅ RESOLVED (2026-06-21, Nick).** Phased approach:
  - **Now (a):** keep current behavior — WHOOP only enriches workouts you logged in the app;
    unmatched workouts stay counted in `workouts_unmatched` and are dropped. No code change.
  - **With the iOS sync UI (Phase 1A) (c):** surface unmatched WHOOP workouts in the app and
    let the user **attach** one to an existing session or **dismiss** it (CLAUDE.md "add manual
    controls"). This is the only path that creates set/session associations from WHOOP.
  - **Deferred (b):** auto-creating synthetic sessions for unmatched workouts is **not** planned
    — revisit only if standalone WHOOP-cardio tracking becomes a goal.
  - *Implementation note for 1A:* `POST /whoop/sync` already returns `workouts_unmatched` as a
    count. To support (c), extend the sync response to include unmatched workout **details**
    (WHOOP id, sport, start/end, strain, avg/peak HR) so the client can render them for
    attach/dismiss; persist a dismissed/attached state so they don't reappear each sync.

- **D2 — `HR_AVG_SESSION` quest type.** Not built. Add it only if "average HR ≥ X for the
  session" is a quest worth having beyond zone-time / peak / strain.

- **D3 — Apple Watch is the primary path for runs/cardio; ingest completed `HKWorkout`s via
  HealthKit (no watchOS companion app). ✅ RESOLVED (2026-06-21, Nick).** Nick logs runs on the
  Apple Watch, which produces good post-workout summaries. Key fact: the **iPhone's** HealthKit
  can read completed Apple-Watch workouts *and their raw HR samples* (`HKWorkout` +
  `HKQuantityType(.heartRate)` via `HKQuery.predicateForObjects(from: workout)`) — **no watchOS
  target required.** This reshapes the roadmap:
  - **Runs / cardio:** import the `HKWorkout` and represent it the way the screenshot path already
    does — match the activity (e.g. `RUNNING`) to a **seeded Cardio/Sport exercise**, create a
    `WorkoutSession` with that exercise + session HR summary (`hr_source = "apple_watch"`,
    avg/peak HR, `kilojoules`, `hr_zone_seconds` computed on-device from the user's max HR). This
    is the **primary** way runs get logged. *(WHOOP stays for strain/recovery + as an alt source.)*
  - **Strength done on the watch:** because HealthKit gives **raw HR samples**, a post-hoc import
    can attribute them to logged sets via the **existing Phase-0 timestamp-window logic** — i.e.
    **per-set HR with no companion app.** Match the `HKWorkout` to the logged session by time
    overlap (same matcher as WHOOP); reuse the D1 attach/dismiss flow for non-matches.
  - **`strain` is WHOOP-only** (0-21). Apple Watch sets `strain = null`; `SESSION_STRAIN` quests
    won't credit from Apple-Watch data (HR_ZONE_TIME / PEAK_HR do). Acceptable.
  - **Dedup across sources:** store the HealthKit workout UUID per user to avoid re-importing, and
    avoid double-counting a workout present in **both** WHOOP and Apple Watch (prefer the
    Apple-Watch import for runs since it carries samples). See risk #8.
  - **Demotes old "Phase 2".** The watchOS companion app is no longer required for per-set HR; it
    becomes an **optional** enhancement that only adds **live** mid-workout HR + exact live set
    boundaries. Lower priority given Nick's post-hoc, summary-first usage.
  - *Optional later:* add `distance_meters` / `pace` columns to `WorkoutSession` for richer run
    records (HealthKit provides `totalDistance`). Not required for HR/quests.

## Open questions / risks

1. **Live vs. post-hoc expectation.** Confirm the near-term "live HR during workout" appetite —
   if it's must-have now, Phase 2 (watchOS) jumps ahead of Phase 1. The phased order assumes
   analytics value first, live HR second.
2. **WHOOP API access.** Requires a WHOOP developer app + approved scopes; rate limits apply.
   Confirm account/credentials availability.
3. **Network egress.** Remote/Railway network policy must permit `api.prod.whoop.com`.
4. **Provisioning / entitlements.** watchOS workout background entitlements vs. the existing
   "minimal entitlements for personal team" decision — verify before Phase 2.
5. **Raw sample volume & retention.** ~1 Hz HR → thousands of rows per session; decide
   downsampling/retention before scaling.
6. **Set-timestamp accuracy.** *(N/A for WHOOP — per-set inference dropped.)* For the **Apple
   Watch HealthKit import** (D3), raw samples are attributed to logged sets by **timestamp
   window** (Phase-0 logic), so accuracy depends on how promptly sets were logged vs. performed.
   The watchOS companion app (optional) would give exact live boundaries. `Set.created_at` lag on
   screenshot/offline-queued workouts is the main error source — keep a manual nudge in mind.
7. **Async quest crediting.** HR quests completing minutes after the workout (on WHOOP sync **or**
   an Apple-Watch HealthKit import) needs UX thought (notification? silent backfill?) and
   idempotent recalculation. Same recalc path serves both.
8. **Dedup across HR sources.** A single workout can appear in **both** WHOOP and Apple Watch.
   Dedup by HealthKit/WHOOP id + time overlap; pick one provenance per session (prefer Apple
   Watch for runs since it carries raw samples). Don't double-count toward quests.

---

## Key files reference

| Area | File |
|---|---|
| Quest models | `backend/app/models/quest.py` |
| Quest logic | `backend/app/services/quest_service.py` |
| Workout stats | `backend/app/services/workout_stats.py` |
| Quest trigger | `backend/app/api/workouts.py` (~line 340) |
| Workout models | `backend/app/models/workout.py` |
| Workout schemas | `backend/app/schemas/workout.py` |
| Activity model (day-level HR) | `backend/app/models/activity.py` |
| Screenshot WHOOP path | `backend/app/services/screenshot_service.py` |
| Migrations | `backend/alembic/versions/` (latest `e741d5fb553c`) |
| HealthKit manager | `ios/FitnessApp/Services/HealthKitManager.swift` |
| iOS API types | `ios/FitnessApp/Services/APITypes.swift` |
| Quest UI | `ios/FitnessApp/Components/DailyQuestsCard.swift`, `Components/QuestDetailSheet.swift` |
| Project / capabilities | `ios/project.yml`, `ios/FitnessApp/FitnessApp.entitlements` |
| Related doc | `docs/healthkit-integration.md` |
