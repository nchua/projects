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
| **1.5 — Wearable-gated quest generation** | ✅ **DONE** (web session) | Shipped: `user_has_wearable` + HR quests capped at 1/day for wearable users. |
| **1.6 — Sync scheduling / freshness** (optional) | ✅ Web session (backend-only) | Background/cron sync; no Xcode. |
| **1A — iOS WHOOP connect flow** (+ D1 attach/dismiss) | 🖥️ Desktop (Xcode) | SwiftUI + `xcodegen` + build check. |
| **1B — iOS HR display wiring** | 🖥️ Desktop (Xcode) | `APITypes.swift` + views; build check. |
| **1.7a — HealthKit import: backend ingest endpoint** | ✅ Web session (backend-only) | Reuses screenshot activity-matching; no Xcode. |
| **1.7b — HealthKit import: iOS read + post** | 🖥️ Desktop (Xcode) | `HealthKitManager` `HKWorkout` reads; no watchOS target. |
| **2 (optional) — watchOS companion (live HR only)** | 🖥️ Desktop (Xcode) | New target, provisioning. Lower priority — per-set HR already covered by 1.7. |
| **3 — Exertion analytics** | Mixed | Backend math = web; charts = desktop. |

> **Decision D3 (Nick): Apple Watch is the primary path for runs/cardio.** Because iPhone
> HealthKit exposes completed `HKWorkout`s *with raw HR samples*, **1.7 needs no watchOS app** and
> delivers both run summaries and per-set HR for strength. The watchOS companion (old "Phase 2")
> is demoted to an optional live-HR enhancement.
>
> Recommendation: do the web-session backend chunks (**1.5**, **1.7a**, the **D1 sync-detail
> endpoints**) now; then on desktop do **1A + 1B + 1.7b** together. Treat **Phase 2 (watchOS)**
> as optional/later.

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

> **⚠️ DESKTOP PREREQUISITE (Nick): run a full council pass on the UI/UX *before* building these
> source-connection flows.** Convene the engineer + designer + PM agents on the end-to-end UX of
> **adding wearable sources** — the WHOOP connect/attach/dismiss flow (1A), the "Sync Apple Health"
> import flow (1.7b), and HR display (1B). Decide the unified "connect a source" surface,
> onboarding/empty states, where sync lives, and the async-credit UX (HR quests crediting after a
> sync) before writing SwiftUI. This gates §4–§6.
>
> **✅ Council ran 2026-06-20 (engineer + designer + PM). Decisions locked in §10 below.**

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

## 6. Phase 1.7 — Apple Watch workout import via HealthKit *(no watchOS app — Decision D3)*

**This is Nick's preferred path for runs.** iPhone HealthKit can read completed Apple-Watch
workouts **and their raw HR samples**, so this delivers run summaries *and* per-set HR for
strength without a watchOS target. The backend HR ingestion (Phase 0) is already built; what's
new is (a) a thin backend ingest endpoint that reuses the screenshot path's activity matching,
and (b) the iOS HealthKit read.

### 6a. Backend ingest endpoint *(web-session-doable)*
- New `POST /workouts/import-healthkit` (or extend `POST /workouts`) accepting a completed-workout
  payload: `hk_uuid`, `activity_type`, `start`, `end`, `duration`, `kilojoules`/energy,
  `avg/peak_heart_rate`, `hr_zone_seconds`, `heart_rate_samples[]`, optional `distance_meters`.
- **Reuse** `screenshot_service`'s `_match_activity_to_exercise` + synthetic-session builder:
  - **Cardio/run:** create a `WorkoutSession` with the matched Cardio/Sport exercise + session HR
    summary, `hr_source="apple_watch"`. (Mirror how the WHOOP-screenshot path already logs runs.)
  - **Strength:** match to an existing logged session by **time overlap** (reuse the WHOOP
    matcher); attribute `heart_rate_samples[]` to sets via the **Phase-0 timestamp-window** logic
    → per-set HR. No match → reuse the **D1 attach/dismiss** flow.
- **Dedup:** persist `hk_uuid` per user; skip re-imports. Don't double-count a workout already
  ingested from WHOOP (see open question 8 / risk D3).
- Run quest recalculation after ingest (same idempotent path as WHOOP sync).
- *Refactor note:* lift `_match_activity_to_exercise` + the synthetic-session builder out of
  `screenshot_service.py` into a shared helper so screenshot + WHOOP + HealthKit stay consistent.

### 6b. iOS HealthKit read *(desktop / Xcode)*
- `Services/HealthKitManager.swift`: add `HKObjectType.workoutType()` + `.heartRate`
  (and `.restingHeartRate`, `.heartRateVariabilitySDNN`) to `readTypes` (currently only
  steps/energy/exercise time).
- Query completed `HKWorkout`s since the last import; for each, read HR samples via
  `HKQuery.predicateForObjects(from: workout)`; compute `hr_zone_seconds` on-device from the
  user's max HR; POST to the ingest endpoint. Track the last-import date + imported `hk_uuid`s.
- Trigger: a "Sync Apple Health" button in the same settings area as WHOOP connect, and/or on
  app foreground. (Background delivery needs an entitlement that was intentionally removed — keep
  it manual/foreground for now; see scoping-doc risk on background delivery.)

**Acceptance:** an Apple-Watch run appears in History as a cardio session with HR summary + zone
breakdown and credits HR quests; a strength workout recorded on the watch backfills per-set HR via
timestamp windows; re-running import doesn't duplicate. No watchOS target added. Simulator build
clean.

---

## 7. Phase 2 (optional) — watchOS companion: live HR only *(desktop / Xcode — lower priority)*

With Phase 1.7 covering per-set HR post-hoc, the watchOS app is **no longer required** — it only
adds **live** mid-workout HR display + exact live set boundaries. Build it only if live-on-wrist
HR is wanted.

**Scope (if pursued):** new watchOS target + shared models in `ios/project.yml`; `HKWorkoutSession`
+ `HKLiveWorkoutBuilder` streaming `.heartRate` to the phone via `WCSession`; live set boundaries;
live HR UI. Samples + per-set timing flow into the **already-built** `POST /workouts`
(`heart_rate_samples[]` + set `start_time/end_time`).

**Provisioning gotcha (verify first):** watchOS workout background entitlements vs. the existing
"minimal entitlements for personal team" decision (`FitnessApp.entitlements`,
`ios/scripts/lint-entitlements.sh`). **No Apple Pay entitlement, ever** (CLAUDE.md).

**Acceptance:** live BPM on-wrist + mirrored to phone during a workout; exact (live) set windows.

---

## 8. Phase 3 — Exertion analytics *(later; backend math = web, charts = desktop)*
<!-- numbering: §7 = optional watchOS, §8 = analytics, §9 = sequencing -->


Per-set work density, HR recovery between sets (`hr_recovery_60s` already scoped as a
nullable column), cardiovascular cost per lift, session-efficiency trends. Feed into the
strength-coach reporting + iOS Progress views. The raw `heart_rate_samples` table exists
precisely so these can be recomputed without re-ingesting.

**Personalized strain metrics (Decision D4) — two related things:**
- **(D4a) Per-exercise cardiac cost / efficiency trend — the headline personalized signal.** Hold
  external load constant, watch internal cost fall: per-set `ΔHR = peak − pre-set baseline` (window
  `[start, end+~30s]` for HR lag), normalized per exercise, trended over weeks. Falling ΔHR for the
  same set = better conditioning for that lift (e.g. bench 155×6: 95→135 today, 95→125 next month).
  Pair with HR recovery (`hr_recovery_60s`); control rest/set-position/RPE confounders.
- **(D4b) Custom "ARISE" session strain** — aggregate cross-source internal-load score replacing
  WHOOP's 0-21 (HR-zone time × HR reserve/Karvonen + mechanical load + per-exercise weighting),
  can roll up the D4a costs and back a cross-source strain quest.

Backend math = web-session-doable when we get to it; the Phase-0 data model already has every input.
Until then `strain` stays WHOOP-only and `SESSION_STRAIN` quests stay WHOOP-gated. See scoping-doc
D4 for open normalization/weighting questions.

**Open:** raw-sample retention/downsampling (~1 Hz → ~3,600 rows/hr) before this scales.

---

## Deployment / merge status

- **Everything on `claude/next-steps-design-spec-83n3jo` is meant to land on `main`** (Nick).
  Deferred to the **desktop session** — do NOT auto-merge from web.
- ⚠️ **`main` is behind:** as of 2026-06-21 `origin/main` is at `d452c20`, which **predates the
  stage-one build** (Phase 0 + WHOOP backend `b39fb9b`). So merging this branch is a **clean
  fast-forward** but it is the **first production deploy of stage one** — Railway auto-deploys on
  push to `main` and will run **two new migrations** on the prod DB (`add_wearable_hr`,
  `add_whoop_connections`). Migration chain verified **single head** (`add_whoop_connections`).
- Changes are backward-compatible (nullable columns + new tables; WHOOP endpoints 503 until
  `WHOOP_*` env vars set; Phase 1.5 tested, 306 backend tests green). Still — deploy intentionally
  from desktop and watch the Railway deploy + a smoke test after.

---

## 9. Sequencing & open questions

**Status / order (updated 2026-06-21):** **1.5 ✅ done** (web). Per Nick, the remaining backend
chunks (**1.7a** HealthKit ingest, **D1** WHOOP attach/dismiss) are **deferred and batched with
their iOS counterparts on desktop** — build each backend+frontend pair together (1A+D1 endpoints;
1.7a+1.7b) rather than pre-building the backend in a web session. Then **3** (analytics, later) →
**2** (watchOS live HR, optional/later).

**🛑 First action on desktop (Nick): run a full council pass (engineer + designer + PM agents) on
the UI/UX of adding wearable sources** — WHOOP connect/attach/dismiss (1A), Apple Health import
(1.7b), HR display (1B). This precedes any SwiftUI work in §4–§6. See the callout in §4.

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
7. **Apple Watch = primary run/cardio path (Decision D3). ✅ RESOLVED.** Import completed
   `HKWorkout`s via HealthKit (no watchOS app); per-set HR for strength via timestamp windows.
   See §6 + scoping-doc D3.
8. **Dedup across sources.** A workout may exist in both WHOOP and Apple Watch — dedup by id +
   time overlap, one provenance per session (prefer Apple Watch for runs). Don't double-credit.
9. **`hr_zone_seconds` for Apple Watch** is computed on-device from the user's **max HR** — need a
   max-HR setting (or estimate `220−age`). Decide where that lives (profile setting vs. estimate).

---

## 10. Council resolution (2026-06-20) — locked v1 decisions

> **▶ Build spec:** the full file-by-file, build-ready spec for all four chunks (A→D) — with a contract
> registry and an amendment protocol so it survives across sessions — lives in
> [`wearable-hr-v1-build-spec.md`](./wearable-hr-v1-build-spec.md). That is the doc to open when building.

Full council pass (engineer + designer + PM) on the wearable-source UX. Resolved:

**Scope — v1 = Apple Health import + HR display; WHOOP stubbed (Nick).**
- Build **1.7a (backend HealthKit ingest)** + **1.7b (iOS HealthKit read)** + **1B (HR display)** now —
  testable on Nick's own devices today and his primary run path (D3).
- **WHOOP (1A)** renders as a disabled "Connect WHOOP — coming soon" row driven by
  `GET /whoop/status.configured == false`; full connect/attach/dismiss (+ D1 endpoints) is **v2**,
  once Railway `WHOOP_*` creds + an approved WHOOP dev app exist. Don't build OAuth/attach/dismiss
  against an endpoint that can't be exercised end-to-end.

**Sync model — connect once, auto-sync on foreground (Nick): "don't make me sync every time."**
- After a one-time Apple Health permission grant, the app **auto-imports new completed `HKWorkout`s
  on app foreground** (`scenePhase` → `.active`, debounced) — opening the app pulls anything new with
  no manual tap. A manual "Import now" stays as a fallback.
- **Silent by default — no toast/notification on every sync.** Quest cards update in place; surface
  only the existing quest-complete affordance when one actually credits. No completion notifications
  in v1. (Resolves §9 Q4 toward silent foreground backfill.)
- **Constraint:** true background sync (app *closed*) needs the HealthKit background-delivery
  entitlement intentionally removed for personal-team provisioning. Foreground-on-open auto-sync is
  the closest available and meets the intent; re-adding background delivery is a later option.
- **Drop the bespoke "AWAITING SYNC" quest state** — foreground auto-sync keeps quests fresh by the
  time the user looks; not worth building.

**Import payload — lean / HR-focused (Nick): "ok if there's not much besides HR data saved."**
- Persist HR-relevant fields only: session avg/peak HR, `hr_zone_seconds`, `kilojoules`,
  `hr_source="apple_watch"`, raw `heart_rate_samples[]` (for per-set attribution), per-set avg/peak HR.
  Defer `distance_meters`/pace/extra metadata.

**Max HR — estimate `220 − age` on-device** (age already captured in the profile attributes); **no
setting screen in v1.** Compute `hr_zone_seconds` on-device from the estimate; backend stores the
supplied zones (no new `max_hr` column needed for v1). Editable override deferred (§9 Q9).

**HR display (1B) — shared foundation, build in v1.**
- New `HRZoneBar` (data-driven segment count: 5 zones when available, collapse to 3; fixed cold→hot
  palette so it always looks intentional), `StatCard`s for avg/peak HR.
- **Strain is WHOOP-only** — shown only on WHOOP sessions; simply **absent** (not "—"/"N/A") on
  Apple-Watch sessions so a missing slot never reads as broken data.
- **Provenance badges** off `hr_source`: WHOOP orange (exists), Apple Watch cyan, screenshot gray —
  one `hr_source → badge` helper.
- Per-set HR column added to the set table only when sets carry HR; HR quest types
  (`hr_zone_time`/`peak_hr`/`session_strain`) get icons/labels in `DailyQuestsCard`/`QuestDetailSheet`.

**Surface placement — the Apple Health workout import is a DISTINCT surface from the existing daily
"Health Sync" row** (steps/calories): different scope, different HealthKit read types — never two
identical-looking Health rows. v1 ships it as a lightweight settings row/section (not a full hub);
generalize into a "Data Sources" hub in v2 when WHOOP is a real second source.

**Dedup:** persist the HealthKit workout UUID (`hk_uuid`) per user; re-import skips known ids
(idempotent, same as WHOOP sync).

**Deferred (anti-gold-plating):** watchOS live-HR app; completion notifications; D4/D4a/D4b analytics
+ custom strain; celebration animations; synthetic sessions for unmatched workouts; multi-source
conflict resolution beyond id-skip; editable max-HR/zone config; the full "Data Sources" hub.

**v1 build order (chunked):** A) backend ingest `POST /workouts/import-healthkit` (1.7a) →
B) iOS API plumbing (`APITypes`/`APIClient`) → C) iOS HealthKit read + foreground auto-sync +
settings row + stubbed WHOOP row → D) HR display (1B). Each chunk ends at its build/test gate.

---

**Key files (quick reference):**
`backend/app/services/quest_service.py` · `…/whoop_service.py` · `…/workout_stats.py` ·
`…/services/screenshot_service.py` (activity→exercise matching to reuse for HealthKit) ·
`…/services/heart_rate_service.py` (per-set sample attribution) ·
`backend/app/api/whoop.py` · `…/api/workouts.py` · `backend/app/schemas/workout.py` ·
`ios/FitnessApp/Services/APITypes.swift` · `…/APIClient.swift` ·
`…/Services/HealthKitManager.swift` · `…/Views/Profile/ProfileView.swift` ·
`…/Components/DailyQuestsCard.swift` · `ios/project.yml` · `docs/whoop-setup.md`
</content>
</invoke>
