# ARISE v3 — Build Session Prompt

> Paste into the next Claude Code session from `/Users/nickchua/Desktop/AI`:
>
> **"Read `fitness-app/docs/arise-v3-build-prompt.md` and execute it end to end. Use the
> subagent workstreams as written. Do not stop for approval between workstreams; stop
> only at the decision points marked ASK."**
>
> Written 2026-09-05 against spec v2.2 and the mockup. The spec estimated 7–9 sessions;
> this prompt compresses it into one long session by running independent workstreams as
> parallel subagents and shipping in a fixed order so a partial session still leaves
> `main` in a usable state at every checkpoint.

---

## 0. Mission

Build ARISE v3 as specified in `fitness-app/docs/arise-v3-spec.md` (v2.2) and shown in
`fitness-app/docs/mockups/arise-v3-mockup.html`. Everything in the spec's Phases 1–4.
Phase 5 (scheduler, widgets, Live Activity, Ask the System, daily LLM line, plate calc) is
**out of scope** for this session.

Sources of truth, in precedence order:

1. The spec — formulas, tables, ops, validators, contract registry (§15).
2. The mockup — layout, copy tone, states. Where the mockup and spec differ, the spec wins
   and the mockup gets a follow-up note.
3. The code — when a spec `file:line` anchor is stale, trust the code and note the drift.

The user is the only user. Optimize for them: the imported plan is the
`training-calendar/data.js` plan (spec §18.2 default), lifts are logged in lb, and the app
renders system fonts (the bundled custom fonts are not registered; **do not** add
`UIAppFonts` — that is a separate decision).

---

## 1. Session start (do all of these before spawning anything)

1. `git pull` and confirm `git log --oneline -3` includes `368ba2c` (Objectives) or later.
2. Confirm a single alembic head: `cd fitness-app/backend && venv/bin/alembic heads` →
   must be `add_workout_local_date`. If not, stop and reconcile (memory:
   `feedback_railway_alembic_multi_head`).
3. Run the backend suite once to get a green baseline:
   `SECRET_KEY=test JWT_SECRET_KEY=test venv/bin/python -m pytest tests/ -n auto -q`.
   Use the absolute venv path (memory: `project_fitness_backend_python_env`).
4. Re-verify the spec's anchors that the build depends on (they drift):
   `trend_service.py` `SLOPE_WINDOW_WEEKS`; `gate_service._candidate_lifts` baseline
   query; `directive_service.py:31` import from `quest_service`; `LogViewModel.swift`
   `rir: nil`; `schemas/workout.py` `SetCreate`; `api/goals.py` `MAX_ACTIVE_GOALS`.
5. **ASK** the user to run the read-only usage snapshot and paste the output
   (`! cd fitness-app/backend && venv/bin/python scripts/usage_snapshot.py`). The
   `exercise_families` backfill dict and the family names in the prescription engine
   depend on which lift names are actually logged. If the user declines, proceed with
   the seed names and flag it in the final report.
6. **ASK** one question, batched with the above: "Import the training-calendar plan as the
   campaign (default), or hold?" Proceed on the default if there is no answer within the
   same reply.
7. Read `fitness-app/CLAUDE.md` (build check commands, `local_date` rule, joinedload
   rule, display-location checklist) and `~/.claude/CLAUDE.md` (pathspec commits,
   auto-QA triggers, no extraneous features).

---

## 2. Ground rules for every workstream

- **Commits are pathspec commits** (`git commit -- <paths>`), one per workstream
  checkpoint, never a bare `git commit` — other sessions stage files in this monorepo.
  Trailer on every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`
  plus the `Claude-Session:` line the harness provides.
- **Backend gates before any push:** `ruff check .` (CI runs it), pytest green, single
  alembic head. **iOS gates:** `xcodegen generate` if files were added, simulator build
  green, `bash ios/scripts/lint-entitlements.sh`.
- **Contract mirrors:** every new Pydantic response that iOS decodes triggers the
  `contract-mirror-check` agent against the *Pydantic file*, not the spec table. Run it
  once after the contract freeze (§4) and once at the end.
- **Migrations are idempotent** (`IF NOT EXISTS` / `IF EXISTS`), chain in one line from
  `add_workout_local_date`, and never run from anything but the web service's
  `startCommand`.
- **No scope additions.** If something tempting appears, write it to the final report's
  "future work" list. Specifically not this session: scheduler/cron, Power › Load
  segment, plate calculator, widgets, daily LLM line, push types beyond the existing
  ones, template library, `UIAppFonts`.
- **Every number the app shows must come from the engine.** The model writes prose and
  ranks ops (spec pillar 6). If an agent finds itself putting a weight in a prompt, stop.
- **Deploy verification:** after each backend push, `/deploy-watch` (Railway CLI may
  need `railway login`; if unavailable, poll `https://backend-production-e316.up.railway.app/health`
  and the new routes, and say so).

---

## 3. Workstreams and subagents

Spawn with the Agent tool (`general-purpose`), one agent per workstream, with the full
prompt block below plus the ground rules. Each agent reports back a **≤ 400-word summary
+ the list of files it touched + test counts**; the orchestrator (you) integrates, commits,
and runs gates. Agents never commit or push.

### W0 — Schema and foundations (backend, **sequential, runs first, one agent**)

Everything downstream imports these models, so W0 finishes and is committed before W1–W3
start.

Deliverables (spec §12 0a, §4.2, §4.6, §6.2, §8.5, §7.5):

- Migrations, in one chain: `Set.is_bodyweight`, `Set.is_warmup`, `Set.weight_lb`
  (populate from `weight` at ingest; one-line backfill `weight_lb = weight` — no kg rows
  exist), `exercise_families` + `exercises.family_id` (+ backfill script
  `scripts/backfill_exercise_families.py` from a committed name→slug dict covering the 169
  seed canonicals; custom exercises name-matched, NULL allowed), `goals.campaign_id`
  (nullable) + `goals.kind` (default `strength`), `campaigns`, `campaign_arcs`,
  `hunt_templates`, `planned_hunts`, `daily_training_load`, `coach_outputs`.
- `WorkoutCreate.duration_seconds`, `WorkoutCreate.planned_hunt_id`, `SetCreate.is_bodyweight`,
  `SetCreate.is_warmup`; persist them in `api/workouts.py`, `api/sync.py`, and the
  screenshot save path. `e1rm` computed from `weight_lb`; warm-up sets excluded from PR
  detection and volume.
- Move `calculate_todays_workout_stats` and `user_has_wearable` from `quest_service.py`
  to `services/workout_stats.py` (or a new neutral module); update `directive_service.py`
  imports. Do **not** drop the quest tables yet (W3 does, after the Directive retires).
- Pin `anthropic==0.111.0` in `requirements.txt`; verify the screenshot service still
  imports.
- `scripts/grant_owner_unlimited_scans.py` (idempotent; takes the email from
  `SEED_USER_EMAIL`).
- Plateau insight: `api/analytics.py` `len(data) > 8` → `≥ 5` distinct `local_date`s in 28
  days.
- Public helpers the other workstreams will call: `daily_activity_series(db, user_id, days)`
  and `families_for_user(db, user_id) -> list[{family_id, exercise_ids, display_name,
  is_big_three}]`.
- Tests for each migration's idempotency and for the helpers. Ruff clean.

Checkpoint commit: `feat(arise-v3): W0 schema + foundations`. Push, verify deploy (the
migrations run on Railway now — confirm `railway status` SUCCESS or `/health` + a new
column visible via a read-only script before continuing).

### W1 — Campaign, Prescription, Objectives (backend, parallel with W2 and W3)

Spec §4, §5, §4.6. Owns: `services/campaign_service.py`, `services/prescription_service.py`,
`api/campaign.py`, `api/hunts.py`, `schemas/campaign.py`, `schemas/hunt.py`,
`scripts/import_training_calendar.py`, changes to `api/goals.py` / `services/goal_service.py`.

- `POST /campaign/import` accepting the `data.js` shape (parse "5×5", "3×10-12",
  "2–2.5 mi", "3 → 4.5 mi (build weekly)", "A or B" → `family` + `alternatives`, time
  items → `note` rows; flag unparseables in the response). The import script reads
  `training-calendar/data.js`, strips the `const PHASES =` wrapper, and posts for the
  owner.
- Lazy, idempotent materialization on `GET /hunts/today` and `GET /hunts/week` (+7 days);
  past `planned` → `skipped`.
- Linking on save from all ingest paths: same `local_date` + type, else nearest same-type
  within ±2 days → `moved`; `done` / `modified` per §4.4.
- Prescription engine per §5.1–5.2 exactly (anchor order, reps-keyed verdicts with RPE
  only slowing, e1RM-derived start ignoring >8-rep sets at 0.90, double progression, arc
  ramp + deload week, long run from the arc, HR cap from the zone table). Readiness
  modulation applied at **fetch time**. Rationale lines with the real numbers.
- **Interface contract with W2 (agree now, both agents implement to it):**
  `prescription_service.prescribe(db, planned_hunt, *, condition: dict | None,
  guard_flags: list[str], gate: PRGate | None) -> Prescription`. W1 owns the function;
  it applies §6.4 actions by flag name and inserts a gate attempt as set 1 with −10%
  back-offs when `gate` is passed. W2 owns producing `guard_flags` and `gate`.
- Objectives: `goals.campaign_id`/`kind`, `POST /goals/preview` returning the pace
  preview (e1RM today, target e1RM, required lb/wk, 6-week slope, `ambitious` flag), run
  objectives derived from the arc, `goal_behind` / `goal_ambitious` flags exposed for W3.
- Adherence XP per §13 (`done` +40, `modified`/`moved` +25, week +150) via `award_xp`;
  retire streak XP; leave `streak_at_risk` scheduling for W5 to remove on iOS.
- Tests: import parser (every string shape in `data.js`), materialization idempotency,
  linking edge cases (Friday lift vs Saturday plan; two sessions one day), every
  progression verdict row in the §5.1 table, guard actions by flag, gate-as-set-1.

### W2 — Load, Guard, Condition v2, Gates v2, local_date readers (backend, parallel)

Spec §6, §10, §12 0b. Owns: `services/training_load_service.py`, `api/load.py`,
`schemas/load.py`, `services/condition_service.py`, `services/cooldown_service.py`
(cardio input), `services/gate_service.py`, `services/trend_service.py`, and the
`local_date` / `weight_lb` read switches in `trend_service`, `gate_service`,
`condition_service`, `directive_service`, `weekly_report_service`, `api/analytics.py`
(use `derive_local_date` fallback for NULL rows).

- Load per §6.1 (TRIMP from `hr_zone_seconds`, session-RPE for lifts, `estimated` flags),
  `daily_training_load` recompute (35 days, EWMA 7/28, run-only ACWR) on every ingest path
  and on `GET /load`. Flags per §6.3 stated against `miles_plan_7d` (from W1's planned
  week — read `planned_hunts` for the week; if absent, no `ramp_high`), 28-day cold start.
- `GET /load` → `TrainingLoadResponse` (§15.4).
- Condition v2: replace `strain_yesterday` with the load-ratio input; add HRV trend;
  weights per §6.5; TRIMP replaces the capped duration in `cooldown_service`.
- Gates v2: `MIN_WEEKLY_POINTS = 4` split from the 6-point fit window; baseline = campaign
  best (fallback last 12 weeks) via a `since` filter; family-based weekly points; spawn
  targets the next planned hunt with that family (window = hunt + 7 days); objective
  tie-break; `gate_cleared` in the workout-create response; expose
  `gate_for_planned_hunt(db, user_id, planned_hunt) -> PRGate | None` for W1's
  `prescribe(...)`.
- Tests: TRIMP/sRPE math, EWMA cold start (`run_acwr` null before day 28), each flag's
  threshold at the boundary, Condition v2 renormalization with/without HRV, gate spawn
  with 4 points, campaign-best vs lifetime baseline, weekly bucketing on `local_date`
  with a NULL-row fallback.

### W3 — The Coach (backend, parallel)

Spec §8. Owns: `services/coach_context_service.py`, `services/debrief_service.py`,
`api/coach.py`, `schemas/coach.py`, `app/coach/prompts/debrief_v1.md`, retirement of
`directive_service` / `user_directives` / `_generate_suggestions`, the quest-table drop.

- Context builder composing the existing functions listed in §8.2 plus W0's helpers;
  fixed key order and precision; `context_hash`. Budget ≈ 8K tokens; assert under 12K in
  a test with a seeded 4-week user.
- Engine step `build_candidates(db, user_id, week_start)` → adherence, highlights,
  concerns (including W1's `goal_behind` / `goal_ambitious` and W2's flags), candidate
  ops with numeric justification.
- Model step: `client.beta.messages.parse(model="claude-opus-5", ...)` with the §8.4
  schema (adjustments include `source ∈ engine|model` and `set_goal_deadline`), adaptive
  thinking (omit `thinking`), `output_config={"effort": "high"}`, `betas=
  ["server-side-fallback-2026-07-01"]`, `fallbacks="default"`, `timeout=60`,
  `max_retries=1`, system prompt + schema first with `cache_control`. Never send a number
  the engine did not compute.
- Validators + appliers per §8.4 (incl. `set_goal_deadline`: extend only, ≤ 4 weeks, once
  per objective) in `campaign_service` (coordinate with W1 by importing its functions;
  do not duplicate). Out-of-bounds ops returned with `status: out_of_bounds`.
- `GET /coach/debrief?week_start=` (lazy, idempotent per week, on-demand allowed after
  Saturday's hunt), `POST /coach/debrief/{id}/adjustments/{adj_id}`. Fallback
  `source: engine_fallback` on refusal / timeout / schema failure.
- Retire: `user_directives` endpoints and card contract (keep the table drop for the same
  migration that drops `quest_definitions` / `user_quests`, `IF EXISTS`); delete
  `_generate_suggestions`; the weekly-report push now fires when a debrief is generated.
- Tests: replay test over 3 stored contexts (schema validity, ≤ 3 adjustments, family
  names present in context), every validator bound, fallback path with a mocked refusal,
  applier rewrites next week's `planned_hunts`. **The LLM call is mocked in tests**; one
  live smoke call is run by the orchestrator after deploy with the owner's data.

### Contract freeze (orchestrator, after W1–W3 land)

1. Merge W1–W3 into the tree, run pytest + ruff, fix cross-workstream seams (the
   `prescribe(...)` call site in `api/hunts.py` must pass W2's `guard_flags` and `gate`).
2. Commit `feat(arise-v3): W1–W3 backend — campaign, prescription, load, gates v2, coach`
   with a pathspec. Push. Verify deploy. Run `scripts/import_training_calendar.py`,
   `scripts/backfill_exercise_families.py`, `scripts/grant_owner_unlimited_scans.py`
   against prod **only if the user says go** (ASK once, batched: "run the three owner
   scripts against prod now?"). Then a live `GET /hunts/today` + `GET /coach/debrief`
   smoke for the owner.
3. Generate the Swift mirrors for every new response (§15.1–15.5 + `PlannedHuntResponse`,
   `PrescriptionResponse`, `TrainingLoadResponse`, `DebriefResponse`, `GoalPreviewResponse`,
   `CampaignResponse`) into `APITypes.swift` in one pass, then run `contract-mirror-check`
   against the Pydantic files. iOS agents consume these; they do not edit `APITypes.swift`
   except to add `CodingKeys` fixes they discover (report them).

### W4 — LogView v2 (iOS, parallel with W5)

Spec §7 (2a + 2b). Owns: `Views/Log/*`, `Services/ActiveHuntStore.swift` (new),
`Services/PendingWorkoutStore.swift` (5xx enqueue), `Components/SupersetCard.swift`,
`APIClient.swift` methods for `last-performance` and `hunts/today` (add only).

- Set row per the mockup: stored `isCompleted` + `completedAt` (sent as `end_time`),
  LAST column from `/exercises/{id}/last-performance`, ghost values (prescribed on a
  planned day, last session's on repeat-last), ✓ accepts ghosts, live e1RM chip (gold on
  PR pace, purple on gate clear), `is_bodyweight`/`is_warmup`/`rir`/`duration_seconds`
  in the payload, units from `preferredUnit`.
- Rest countdown v2 in a sticky bottom bar (defaults 180/120/90 s by role, haptics, local
  notification at zero), replacing `QuestTimerCard`.
- `ActiveHuntStore` draft persistence + RESUME banner hook (W5 renders the banner; W4
  exposes `ActiveHuntStore.shared.draft`).
- Save compression: sticky FINISH, blank trailing sets dropped, one celebration screen
  (PR → gate → XP → rank, one CONTINUE), `gate_cleared` consumed.
- Picker: recents, favorites, multi-select, muscle filter, filters cleared on dismiss;
  swap offers `alternatives` first.
- Post-save edit of date/notes/RPE/sets in `QuestDetailView` via `PUT /workouts/{id}`.
- Small fixes: locale-safe parsing, next-field keyboard, reorder, swipe-to-delete.
- Build green after `xcodegen generate`.

### W5 — Status, Hunt, Hunter, Debrief, background delivery (iOS, parallel)

Spec §4.7, §6.6, §8.4 UI, §4.6, §9.1, §14. Owns: `Views/Home/*` (new `TodaysHuntCard`,
`LoadStripCard`, `LoadSheet`, adherence ring in `DashboardCard`), `Views/Hunt/*` (week
strip, pace strip, planned-hunt sheet, RESUME banner, REPEAT LAST), `Views/Profile/*`
(Campaign card, Objectives sheet re-homing `GoalSetupView`, Coach settings rows),
`Views/Home/WeeklyReportView.swift` → Debrief sheet, `Services/HealthKitManager.swift`
(background delivery), `Services/SyncCoordinator.swift`, `NotificationManager.swift`
(remove `streak_at_risk`, add `rest_timer_done`), `APIClient.swift` methods for the new
endpoints (add only).

- Today's Hunt card in the three readiness states from the mockup, System line from
  `system_line`, goal chip, BEGIN HUNT → LogView with `planned_hunt_id`; REST card.
- Load strip + sheet from `/load`. No Power changes.
- Hunt week strip + pace strip + planned-hunt sheet (move/skip via `PUT /hunts/{id}`),
  calendar keeps working, hunt rows show `AS PLANNED` / `MOVED` chips.
- Debrief sheet: summary, adherence ring, highlights, concerns, adjustment cards with
  ACCEPT / DISMISS / out-of-bounds state, goal line → Objectives sheet, `engine_fallback`
  state rendered honestly ("The System's summary; the Coach did not answer").
- Objectives sheet with the pace preview (`POST /goals/preview`) and run objectives from
  the campaign; Hunter › Campaign row and Objectives row.
- HealthKit background delivery (`HKObserverQuery` + `enableBackgroundDelivery` for
  workouts, sleep, HRV, RHR) driving the existing import; Integrations row shows status.
- Remove the Directive card, `DirectiveSheet`, and their API calls.
- Build green after `xcodegen generate`; entitlements lint clean.

### W6 — Integration and QA (orchestrator + agents)

1. Merge W4 + W5; `xcodegen generate`; build; entitlements lint; fix seams (W4's LogView
   reads `PlannedHuntResponse` from W5's card).
2. `contract-mirror-check` (final), then `/evaluate` on the whole diff (defect-first),
   fix Errors and Warnings, then `/simplify`, then ruff + pytest + build again.
3. Commit `feat(arise-v3): W4–W5 iOS — LogView v2, Today's Hunt, week strip, Debrief,
   Objectives, background delivery` with a pathspec. Push. Verify deploy (backend
   unchanged in this commit; deploy is a no-op).
4. Update `docs/arise-v3-spec.md` §19 with a v3.0 build entry and any anchor drift, and
   write `docs/arise-v3-roadmap.md` (status tracker, deviations, deferred items) in the
   v2 roadmap's format. Commit.
5. Remind the user to rebuild in Xcode (Cmd+R), grant the new HealthKit background
   permission, and open Status.

---

## 4. Ship order and stop line

If the session must end early, `main` must be left at one of these checkpoints, each
independently usable:

| Checkpoint | State of the app |
|---|---|
| after W0 | schema + foundations live; nothing visible changes |
| after W1–W3 + contract freeze | backend fully v3; iOS still v2.1 (old endpoints kept until W5 removes them — do not delete `/directive/*` before W5 lands; W3 marks it deprecated instead) |
| after W6 | v3 complete through Phase 4 |

Never leave the tree between checkpoints with a red build or a multi-head alembic.

---

## 5. Decisions already made (do not re-open)

- Plan import default = `training-calendar/data.js`; the Cowork Week 1 plan is not imported.
- Engine owns every number; the model only writes prose and ranks engine candidates.
- ACWR is run-only, 28-day cold start; lifts never enter the guard's veto path.
- Guard rules compare to the plan's ramp, not last week.
- Gate attempt is set 1 after warm-ups; working sets back off 10%.
- No scheduler, no daily LLM line, no Power › Load segment, no plate calculator, no
  `UIAppFonts` this session.
- `date` stays the instant; `local_date` is the bucketing axis; readers switch in W2.
- The Directive retires only after W5 renders its replacement.

---

## 6. Final report format

Under 500 words, for a reader who did not watch the session:

1. What shipped, by checkpoint, with commit hashes and the Railway deploy status.
2. Test counts before/after; ruff; build; contract-mirror result; `/evaluate` grade and
   what was fixed.
3. Prod steps run or still pending for the user (owner scripts, Xcode rebuild, HealthKit
   permission, first debrief).
4. Deviations from the spec, each with a one-line reason.
5. Future work captured but not built.
6. Anchors that had drifted and were corrected in the spec.
