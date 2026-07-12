# ARISE v2 — Roadmap & Execution Status

> **Status:** Live tracker. Written 2026-07-12, after Phase 0 shipped. This document is
> the **single source of truth for build status and per-session execution maps**; the
> product definition (formulas, contracts, UI specs) stays in `docs/arise-v2-spec.md`.
> When this doc and spec §12 disagree, this doc wins — §12 was written before Phase 0
> and has drifted (see §2 below).
>
> Code citations verified against the working tree 2026-07-12. Re-verify `file:line`
> anchors at the start of each build session — they drift.

---

## 1. Goals & priorities (interview record, 2026-07-12)

Recorded so future sessions know *why* the order is what it is.

- **North star: Strength PRs.** The metric the user actually cares about is hitting
  new PRs on his lifts. PR Gates (Phase 2) is the payoff feature; everything before it
  is either prerequisite (Condition gates the spawn rule) or pain-point relief.
- **Pain point 1 — no daily guidance.** The app never tells him what to do today.
  Fixed by the System Directive (Phase 1, spec §5).
- **Pain point 2 — recovery data buried in the DB.** WHOOP recovery/HRV/sleep and the
  cooldown engine land in the database and barely reach the UI. Fixed by Hunter
  Condition (Phase 1, spec §4).
- **Decision: complete the existing spec, no pivot.** The ARISE v2 spec as written is
  the product. **No scope additions** — anything tempting goes in a "future work" note,
  not the build.
- **Decision: keep the spec's phase order.** Phase 1 (Condition + Directive) →
  Phase 2 (PR Gates) → Phase 3 (Exertion analytics + achievements). Phase 1 first
  because it fixes both pain points directly and Gates depend on Condition (spawn rule
  requires Condition ≥ 65, spec §6.2).
- **Cadence (revised 2026-07-12): the whole remaining build in one session** — Phases
  1 → 2 → 3 → QA pass, sequentially. The original one-phase-per-session plan was
  superseded by user decision the same day the roadmap was written. Per-phase ship
  criteria (§7) still gate each phase: commit + push + verified Railway deploy before
  moving to the next.
- **After Phase 3: the QA/polish pass** (§6 below) before calling v2 done.

## 2. Current state — post-Phase-0 reconciliation

Phase 0 shipped in commits `580a5f6..e7eb28e` (2026-07-12), deployed to Railway
(deployment `df27cd19`, `/health` 200, `/dungeons` `/missions` `/quests` gone).
385 backend tests green, ruff clean, iOS build green.

### 2.1 What §12 says vs. what actually shipped

| Spec item | §12 placement | Reality |
|---|---|---|
| §3 cuts (Dungeons, Missions, daily quests, iOS dead code) | Phase 0 | **Done** (Layers 1–2) |
| §3.4 renames + §2 four-tab restructure + §8.4 Hunter tab | Phase 0 | **Done** (Layer 3) |
| §9 design consolidation (Minimal Void) | Phase 0 | **Done** (Layer 4; `LogView` interior deliberately skipped per §8.2 out-of-scope rule) |
| §3.2 XP fixes (achievement XP via `award_xp`, `/sync` full XP pipeline, dead `first_workout_today`) | **§12 lists these under Phase 3 — wrong** | **Done in Phase 0 Layer 1** (`580a5f6`). Phase 3 drops this item. |
| §10.1 "`POST /sync` = 0 XP (bug)" row | implied open | **Fixed** — `/sync` runs the full XP pipeline, including a retry double-award guard added at the QA gate (`e7eb28e`) |
| Condition + Directive (§4–§5, §8.1 Status order, §13.1–13.2 mirrors) | Phase 1 | **Done** (2026-07-12, backend `958bc3f` + iOS commit same day; Railway SUCCESS verified; contract-mirror PASS) |
| PR Gates + notification prompt (§6, §11, §13.3 mirror) | Phase 2 | **Done** (2026-07-12, backend `bf636b1` + iOS commit same day; Railway SUCCESS verified; contract-mirror PASS) |
| Exertion analytics, new achievements, `arise_strain`, cardio-screenshot upgrade (§7, §10.2, §13.4–13.6 mirrors) | Phase 3 | **Done** (2026-07-12, backend `4308b0e` + iOS commit same day; Railway SUCCESS verified; contract-mirror PASS) |

### 2.2 Deliberately kept groundwork (don't "clean up")

- `quest_service.py` keeps `calculate_todays_workout_stats`
  (`app/services/quest_service.py:29`) and `user_has_wearable` (`:102`) with **zero
  callers today** — reserved for Directive generation (Phase 1). Not dead code.
- `quest_definitions` / `user_quests` tables were **not dropped** — spec §3.1 says drop
  after the Directive ships and is proven. Decision point recorded for Phase 3 (§5).
- ~~The `quest_completed` notification enum + iOS "Quest Completed" toggle survive until
  Phase 1 decides whether the Directive re-emits that type.~~ **Resolved in Phase 1:**
  cut (`quest_completed` + dead `quest_reset` enum values, the settings row, and the
  uncalled local-notif schedulers) — spec §11 says no push for the daily Directive.

### 2.3 Build-on points for the next phases

- **Alembic:** single head = `drop_dungeon_mission_tables`. New migrations
  (Phase 1 `user_directives`, Phase 2 `pr_gates`) chain off it. Make them idempotent
  (prod-stamp-drift memory) and verify `railway status --json` SUCCESS after push.
- **XP path:** `award_xp` (`app/services/xp_service.py:143`) is now the only XP
  entry point; non-workout grants use `count_workout=False`. `BIG_THREE` list at
  `xp_service.py:31`.
- **PR detection:** `detect_and_create_prs` (`app/services/pr_detection.py:110`)
  is called from all three ingest paths — `app/api/workouts.py:352`,
  `app/api/sync.py:209`, and `screenshot_service.py`. Gate clear-detection (Phase 2)
  hooks the same three call sites.
- **Known Info-level leftovers from the Phase 0 evaluation** (fold in opportunistically,
  don't dedicate a session): `HuntDetailView` near-duplicates `QuestDetailView` minus
  the HR section (drift risk); `EdgeFlowAchievementCard` lives in `StatusView.swift`
  but is only used by `HunterView`; `BigThreeLift.liftColor` kept as a thin wrapper
  over `exerciseColor` (3 call sites; spec §9.4 said retire).

## 3. Phase 1 session — Condition + Directive

> **Status: SHIPPED 2026-07-12.** All §7 ship criteria met: 418 backend tests green,
> ruff clean, sim build green, entitlements lint clean, contract-mirror `/evaluate`
> PASS (no blockers), Railway deploy SUCCESS (`958bc3f`), prod routes verified live.
> Deviations from the plan below: `FlowLayout` was NOT dead (live in
> `AriseHRZoneBar` legend) — moved to `Components/FlowLayout.swift` instead of
> deleted. Directive rule 6 (gate_reminder) is a stub until Phase 2.

Spec sections: **§4 (Condition), §5 (Directive), §8.1 (Status tab), §13.1–13.2
(contracts).** Fixes both interview pain points.

### 3.1 Backend

1. **`app/services/condition_service.py` (new).** Computes the 0–100 score on the fly
   — never stored (same pattern as `exertion_score`). All five inputs verified present
   in the tree:
   - `daily_activity.strain / recovery_score / hrv / resting_heart_rate / sleep_hours`
     (`app/models/activity.py:35-39`)
   - `cooldown_service.calculate_cooldowns` (`app/services/cooldown_service.py:612`)
   - `compute_exertion_score` (`app/core/exertion.py:34`) for the yesterday-strain
     fallback when WHOOP strain is null
   - Weights, normalizations, renormalization rule, and band thresholds: spec §4.1–4.2.
     Band constants are shared with Gate spawning (Phase 2) — put them somewhere
     importable, not inline.
2. **`GET /condition`** per spec §4.3 (routers mount bare, no `/api` prefix).
3. **`user_directives` table + migration** (chains off `drop_dungeon_mission_tables`).
   Schema per spec §5.3; unique on `(user_id, date)`.
4. **Directive generation** — server-side on first `GET /directive/today?client_date=`
   of the local day, rule table per spec §5.2. Reuses (all verified):
   - `calculate_todays_workout_stats` + `user_has_wearable` (the §2.2 groundwork)
   - the `GET /analytics/insights` engine (`app/api/analytics.py:602`)
   - `_get_exercise_weekly_sets` (`app/services/weekly_report_service.py:330`) for
     per-lift weekly volume vs. 4-week mean
   - streak state from `UserProgress`
5. **Completion auto-detection** on workout create (rule types 2–7) or next-day
   generation (type 1); XP via `award_xp(40, count_workout=False)`. No claim button.
6. `GET /directive/history?limit=` for the sheet.

### 3.2 iOS

- **Status hero: Condition arc gauge** (spec §4.4) — Orbitron score, band label/color,
  provenance chips. Tap → Condition detail sheet.
- **Condition detail sheet absorbs `RecoveryStatusSection` + `RecoveryDetailSheet`**
  (`Views/Home/RecoveryStatusSection.swift`, `RecoveryDetailSheet.swift`): per-input
  contribution bars, muscle pills with the existing `fatigue_breakdown` drill-down,
  HRV + sleep rows. Missing inputs render `NO SIGNAL — weight redistributed`, never 0.
- **Directive card** directly under Condition — System Window mono/bracket styling
  (one of the few places the sharp dialect survives, spec §9.2). States
  ACTIVE / COMPLETE (+40 XP stamp). Tap → Directive sheet (message, "why" with real
  numbers, reward, 7-day history).
- Status tab lands at its final §8.1 section order: header → Condition → Directive →
  (Gate slot, Phase 2) → This Week → Power snapshot.

### 3.3 Phase-1 QA

- **Contract-mirror rule triggers** (global CLAUDE.md): `ConditionResponse` +
  `DirectiveResponse` Swift structs mirror spec §13.1–13.2 — run `/evaluate` pointed
  at the **actual Pydantic schemas**, not the spec tables.
- Decide the `quest_completed` notification question: Directive completion either
  re-emits that type or the toggle/enum gets cut here.

## 4. Phase 2 session — PR Gates

> **Status: SHIPPED 2026-07-12.** All §7 ship criteria met: 442 backend tests green,
> ruff clean, sim build green, entitlements lint clean, contract-mirror `/evaluate`
> PASS (all 19 GateResponse fields match), Railway SUCCESS (`bf636b1`), `/gates`
> live. **Deviations:** (1) the spec's "nightly job" for spawn evaluation is
> implemented as lazy evaluation on GET /gates (+ on workout create) — no scheduler
> infra was added, deliberately (no-extraneous-features rule; the Status tab hits
> GET /gates on every open). (2) Hunt Log rank sigils match cleared gates to rows
> by local clear *day* (GateResponse carries cleared_by_set_id, which summaries
> can't resolve to a workout client-side). (3) The CLAUDE.md notification-permission
> Open Decision is resolved: prompt on post-save celebration dismissal via
> `requestAuthorizationIfNeeded()`.

Spec sections: **§6 (Gates), §11 (notifications), §13.3 (contract).** This is the
**north-star phase** — the feature the whole roadmap exists to ship.

### 4.1 Backend

1. **Trend extension (prerequisite, spec §6.1).** Extract the trend math from
   `app/api/analytics.py` into a new `app/services/trend_service.py`; add
   `weekly_slope` (least-squares over the last 6 `weekly_best_e1rm` points, lb/week)
   and `projected_e1rm(days)`. Today's trend endpoint has `weekly_best_e1rm` but no
   slope/projection (verified).
2. **`gate_service.py` + `pr_gates` table + migration** per spec §6.5. Spawn rules
   §6.2 (evaluated on workout create after PR detection + nightly job), ranking §6.3
   (`BIG_THREE` +1 rank step), lifecycle §6.4.
3. **Clear-detection** hooked into all three `detect_and_create_prs` call sites
   (workouts, sync, screenshot — see §2.3). Award via `award_xp`, run achievement
   check, no claim step.
4. **`gate_opened` APNs type** — does not exist yet (verified: `NotificationType`
   in `app/models/notification.py` has no gate entry). Add enum value + notifier in
   `notification_service.py`.
5. Endpoints: `GET /gates`, `POST /gates/{id}/accept`, `GET /gates/history?limit=`.
   No force-spawn in prod.

### 4.2 iOS

- **Status Gate card** (between Directive and This Week, conditional) + **Gate sheet**
  per spec §6.6 — rank sigil in rank color, target set, proximity bar, countdown,
  WHY THIS GATE with real slope/projection numbers.
- **Hunt Log rank sigil** on workout rows that cleared a Gate.
- **Notification permission prompt** — this session **resolves the
  `fitness-app/CLAUDE.md` "Open Decisions" item**: call the currently-uncalled
  `NotificationManager.requestAuthorization()`
  (`Services/NotificationManager.swift:22`) on dismissal of the post-save celebration
  in `LogView` (spec §11 rationale: the ask lands right after the user's best moment).
  Update that CLAUDE.md section when done.

### 4.3 Prerequisite & QA

- **Data prerequisite:** Gates need **≥ 6 weeks of weekly-best e1RM data per lift**
  (spec §6.1). If no lift qualifies at ship time, that's expected behavior, not a bug
  — verify spawn logic with dev seeds instead.
- Contract-mirror rule triggers again: `GateResponse` vs spec §13.3 → `/evaluate`
  against the Pydantic schema.

## 5. Phase 3 session — Exertion analytics + achievements

> **Status: SHIPPED 2026-07-12.** All §7 ship criteria met: 460 backend tests green,
> ruff clean, sim build green, entitlements lint clean, contract-mirror `/evaluate`
> PASS (all §13.4–13.6 mirrors + ActivitySave contracts), Railway SUCCESS (`4308b0e`).
> **Deviations/notes:** (1) The §7.3 edit-before-save flow is implemented as a new
> `save_activity=false` form flag on /screenshot/process (single-image path) +
> `POST /screenshot/save-activity` — batch keeps auto-save; old clients keep
> auto-save via the flag's default. (2) **Post-deploy manual step:** the 8 new
> achievement defs seed via `POST /progress/seed-achievements` (idempotent,
> auth-required) — hit it once from the app/curl; no startup auto-seed exists.
> (3) `condition_peak_7` recomputes historical Condition with current cooldowns
> (approximation — Condition is never stored). (4) §5.3 decision below: tables kept.

Spec sections: **§7 (strain unification + analytics + cardio screenshots), §10.2
(achievements), §13.4–13.6 (contracts).** Note: §12's "XP fixes (§3.2)" item is
already done (see §2.1) — it is **not** part of this phase.

### 5.1 Backend

1. **`arise_strain` unified field** on workout responses (spec §7.1): WHOOP `strain`
   if non-null, else `compute_exertion_score(hr_zone_seconds)` with the session's
   `hr_source` as the badge. Keep `strain`/`exertion_score` in the payload during
   migration.
2. **`GET /analytics/exertion/weekly?weeks=8`** (spec §7.2-1).
3. **`GET /analytics/exercise/{id}/cardiac-cost?weeks=12`** (spec §7.2-2) — ΔHR per
   matched set, grouped by the same `_weight_bucket` helper PR detection uses
   (`app/services/pr_detection.py:92`); confounders recorded as `caveats`, not modeled.
4. **Cardio-screenshot upgrade** (spec §7.3 tier 3): activity screenshots create a real
   `WorkoutSession` via `match_activity_to_exercise` with `hr_source="screenshot"`,
   persisting duration, avg/max HR, and parsed zone breakdown. Strain rules by source
   per §7.3 (never convert non-WHOOP effort metrics). Extracted fields editable before
   save (manual-controls philosophy).
5. **8 new achievement defs** in `seed_achievement_definitions`
   (`app/services/achievement_service.py:200`) + new `requirement_type`s in
   `check_and_unlock_achievements`, per spec §10.2 table.

### 5.2 iOS

- **Power › EXERTION segment** (insert second): strain weekly trend + volume weekly
  trend as aligned small multiples (never dual-axis), per-exercise cardiac-cost card,
  zone-distribution stacked bars (locked `AriseHRZoneBar` palette; order + labels
  carry identity, never color alone).
- **Hunt rows + detail sheets switch to `arise_strain`** with source badge everywhere
  strain shows.
- Activity-screenshot edit flow: extend the `ScreenshotExerciseEditView` pattern to
  the activity fields.

### 5.3 Decision point (flagged for this session, decide then)

**Drop `quest_definitions` / `user_quests` tables now, or leave?** Spec §3.1 says drop
after the Directive is proven. By Phase 3 the Directive will have run for two phases —
if it's stable, add the drop to this phase's migration; if in doubt, leave them (they
cost nothing) and note it for the QA pass.

> **Decided 2026-07-12: LEAVE.** All three phases shipped in one session, so the
> Directive has zero days of real-world use — not "proven" by any reading. The
> tables cost nothing; drop them in a future session once the Directive has run
> for a few weeks in prod.

### 5.4 QA

Contract-mirror rule triggers for §13.4–13.6 (`AriseStrain`, `ExertionWeekPoint`,
`CardiacCostResponse`) → `/evaluate` against the Pydantic schemas.

## 6. QA/polish pass session (after Phase 3)

> **Status: DONE 2026-07-12.** Independent full-app `/evaluate` (defect-first,
> separate agent): **B+ (7.95), PASS WITH WARNINGS** — 0 Critical, 2 Error,
> 10 Warning, 9 Info. Contract mirrors re-verified clean (all §13.1–13.6 +
> §13.7 spot-checks). **Fixed in the QA pass:** both Errors (pure-cardio
> screenshot saves now run directive completion; `_directive_streak` tolerates
> client/server day drift), plus W4 (Gate Opened notification toggle row),
> W6 (achievement check moved after HR ingest + directive completion),
> W7 (out-of-scale non-WHOOP strain dropped before any persistence),
> W9 (`app` source badge case), W10 (`int(zone)` guard in zone parsing).
> Also fixed the **pre-existing red CI** (failing since before this session):
> stale `scripts/backfill_goal_progress.py` import of the Phase-0-deleted
> `app.models.mission` + import-sort error only newest ruff flags — file fixed
> (imports now from `app.models.goal`) and ruff pinned to 0.15.18 so CI and
> local agree. 3 regression tests added (463 total).
>
> **Deferred (known, recorded — not bugs to rediscover):**
> - W1: lazy achievement checks (`condition_peak_streak` = 7× cooldown calc,
>   `cardiac_cost_drop` = per-lift scan) run on every ingest until unlocked —
>   acceptable for a solo user; revisit if ingest latency grows.
> - W2: gate-spawn Condition + `_condition_peak_streak` use the server's UTC
>   day (no client_date on GET /gates) — evening spawns read a mostly-empty
>   "today"; renormalization degrades gracefully. Fix = optional client_date
>   param on GET /gates.
> - W3: rest-directive award requires generation exactly next day (spec-faithful
>   "next morning"; a skipped day forfeits the 40 XP).
> - W5/W8: gate clears are not surfaced in the workout-create response and the
>   §6.4 celebration overlay is unimplemented — the clear shows via Hunt Log
>   sigil + XP totals. Needs a contract addition; schedule as v2.1 polish.
> - Info items: `accept` on unswept overdue gate (narrow race), sigil
>   day-matching, GateSheet hardcodes "BATTLE READY" caption, silent
>   `client_date` fallback, WHOOP-zones-without-strain badge, `volume_lb`
>   ignores weight_unit (app-wide convention), `refresh(None)` edge in the
>   directive race handler, retro-synced workout can't revoke an awarded rest
>   directive, trend weekly-best math duplicated between trend_service and the
>   /trend endpoint.

**Entry criteria:** Phase 3 live on Railway, all four phases' ship criteria met.

**Scope:**
- Full-app `/evaluate` (independent QA agent, defect-first).
- **Cross-boundary contract audit of every §13 mirror** in one sweep
  (`contract-mirror-check` agent): §13.1–13.6 plus the §13.7 pre-existing endpoints
  the new UI leans on.
- Bug hunt: edge cases around renormalization (§4.1 with sparse `daily_activity`),
  Gate expiry/timezone boundaries, directive `client_date` handling, screenshot-created
  sessions in analytics.
- Feel/consistency: Minimal Void conformance on the new Phase 1–3 surfaces, copy tone,
  the §2.3 Info-level leftovers if still open.

**Explicitly not:** a redesign. No new features, no spec additions.

## 7. Per-phase ship criteria (mirrors Phase 0)

Every phase ends with all of (even when phases run back-to-back in one session):

1. Backend: `pytest` green (`venv/bin/python -m pytest tests/ -n auto -q`), `ruff
   check .` clean (CI runs it; local pytest alone misses it).
2. iOS: `xcodegen generate` after any new Swift files, simulator build green,
   entitlements lint clean.
3. Contract-mirror `/evaluate` for any phase that adds §13 mirrors (all of them do).
4. Commit + push per feature; **verify Railway deploy SUCCESS** (`railway status
   --json` or `/deploy-watch`) — the alembic multi-head failure mode deploys "green"
   while the old instance keeps serving.
5. Remind the user to rebuild in Xcode (Cmd+R) after iOS changes.

## 8. Risks & watch items

- **Condition's biggest input may often be missing.** Recovery (weight 0.40) reads
  `daily_activity.recovery_score`, which is populated by **WHOOP screenshot scans /
  HealthKit** — the WHOOP API sync (`whoop_service.sync_recent_workouts`,
  `app/services/whoop_service.py:395`) pulls **workouts only**, not `/v1/recovery`.
  Renormalization (§4.1) degrades gracefully, and muscle freshness is always available,
  so Condition never comes up empty — but expect the score to lean on cooldowns+sleep
  on days without a WHOOP scan. Extending the WHOOP API sync to recovery is **future
  work, not scope** (no-scope-additions decision, §1).
- **Gates may not spawn for weeks after Phase 2 ships** — the ≥6-weeks-per-lift data
  prerequisite (§4.3). Set expectations in the session summary; don't "fix" it.
- **Migrations:** two new tables across Phases 1–2, both chaining off
  `drop_dungeon_mission_tables`. Idempotent DDL + post-push Railway verification every
  time (memory: prod stamp drift + multi-head both bite silently).
- **`HuntDetailView` / `QuestDetailView` drift** (§2.3) — Phase 3 touches workout
  detail surfaces for `arise_strain`; that's the natural moment to converge them.
- **Spec line anchors go stale** — Phase 0 already moved thousands of lines. Re-verify
  every `file:line` cited in the spec/roadmap at session start, per the spec's own
  closing note.

---

## 9. v2.1 — retro-driven scope (interview 2026-07-12)

> **Status: SHIPPED 2026-07-12** (same day as v2, all five chunks). Every
> chunk passed the full §7 gates (474 backend tests, ruff clean, sim build
> green, entitlements lint, contract-mirror PASS on the WHOOP and Directive
> contracts, pathspec commits, Railway SUCCESS verified via /deploy-watch).
> Chunks: 1 = `92a9d5f` (HealthKit RHR/HRV/sleep), 2 = `029dce0` (WHOOP v2
> migration + recovery sync + live connect row), 3 = `d899d12` (Condition
> explainability), 4 = `39d1813` (LIFT_LAG prescription), 5 = cleanup (this
> commit).
>
> **Post-ship user steps:** rebuild in Xcode; grant the new Apple Health
> sleep permission on next app open; tap Hunter › Integrations › WHOOP →
> CONNECT (credentials were set on Railway 2026-07-12, deploys verified).
>
> **Known deferrals from v2.1 verification (recorded, not bugs to rediscover):**
> - `WhoopStatusResponse` deliberately doesn't mirror `whoop_user_id` /
>   `scope` / `expires_at` / `last_synced_at` (unused by UI today).
> - GATE_REMINDER's `gate_id`/`gate_name`/`days_left` params aren't rendered
>   in the Directive why-sheet (pre-existing).
> - Retro-synced workout still can't revoke an already-awarded rest directive
>   (v2 QA Info item, unchanged).
> - W1 (lazy achievement-check perf) untouched — still fine for a solo user.

### 9.1 Interview record (why this scope)

- **No Gate has spawned yet.** Expected (§8 data prerequisite), but a read-only
  prod diagnostic (scratchpad script, replicates `evaluate_gate_spawns`
  rule-by-rule without writing) is written and pending user approval for prod-DB
  access. User deferred it until WHOOP setup was resolved.
- **Directive is too vague.** "6 hunts this week" is rule 7 (MAINTAIN), a
  *status readout* misread as a goal. User wants per-lift prescriptions with
  real volume numbers (chose that over session-level sets×reps×weight).
- **Condition is directionally right but unexplained.** The detail sheet's
  "100w 29%" rows (value + effective weight) are cryptic; "yesterday's strain"
  is uninterpretable; resting HR shows NO SIGNAL despite Apple Health having it.
- **Root cause found for the RHR gap:** `HealthKitManager.swift`
  `DailyHealthData.toActivityCreate()` hardcodes `restingHeartRate`/`hrv`/
  `sleepHours` to `nil` — HK read permission for RHR is requested but the
  values are never fetched. Backend upsert is per date+source and skips `None`
  (`api/activity.py:67-78`), and `condition_service._pick_activity_value` reads
  across source rows, so filling these is clobber-safe.
- **Exertion tab: unopened.** Explicitly no v2.1 work.
- **Notifications: prompt hasn't fired** — it triggers on post-save celebration
  dismissal and no in-app workout has been logged since the rebuild. Not a bug.
- **WHOOP recovery sync (the §8 risk / noted future work): user approved.**
  Developer app registered 2026-07-12; `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET`
  / `WHOOP_REDIRECT_URI` set on Railway (deploys skipped). Privacy policy
  (`GET /privacy`) and callback (`GET /whoop/callback`) were already live and
  used for the registration form. User connects from the app AFTER chunk 2
  deploys (scopes must include `read:recovery` at authorize time).

### 9.2 Chunks (priority order, agreed 2026-07-12)

1. **HealthKit Condition inputs (iOS).** Fetch resting HR, HRV (SDNN), and
   sleep hours in the daily HealthKit sync; populate the `ActivityCreate`
   fields currently hardcoded `nil`. No backend change.
2. **WHOOP recovery sync (backend).** Add `read:recovery read:sleep` to
   default scopes; pull recovery (+ sleep) into `daily_activity`
   (`recovery_score`, `hrv`, `resting_heart_rate`, `sleep_hours`) alongside the
   existing workout sync triggers; add a WHOOP paragraph to `/privacy`.
   **Verify WHOOP API version during build** — v1 endpoints were deprecated for
   v2; the existing service targets v1 paths.
3. **Condition explainability (iOS).** Rewrite `ConditionDetailSheet` input
   rows in plain language (value with units, "X% of today's score"), one-line
   "what this means" per input, NO SIGNAL states say why + how to fix.
4. **Directive per-lift prescription (backend + iOS).** New rule above the
   MAINTAIN fallback: most-lagging big-three lift by weekly volume vs 4-week
   mean (`_get_exercise_weekly_sets` infra), message with real lb numbers,
   completion when that lift is logged that day. Fix MAINTAIN copy so counts
   read as status, never goals.
5. **Deferred cleanup.** W2 (`client_date` on GET /gates + iOS passes it),
   W3 (rest-award survives a skipped day), HuntDetailView/QuestDetailView
   convergence (§2.3), cheap Info items (GateSheet hardcoded caption, silent
   client_date fallback).

**Out of scope for v2.1:** gate-clear celebration overlay (W5/W8 — user did not
rank Gates; revisit when the first gate spawns), Exertion changes, quest-table
drop (§5.3 — Directive still has ~0 real-world days).

---

*Companion docs: product spec `docs/arise-v2-spec.md` (formulas, contracts, UI);
mockup `docs/mockups/arise-v2-mockup.html`. Update this file's §2 table and phase
sections as each phase ships.*
