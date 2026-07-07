# ARISE v2 — Product Spec

> **Status:** Draft for build. Written 2026-07-06 from the first-principles product review
> (session: 5-tab audit + backend inventory). Companion mockup:
> `docs/mockups/arise-v2-mockup.html` (interactive, phone-viewable).
>
> **Scope of this doc:** the full v2 product definition — what gets cut, what gets built,
> exact formulas, API shapes, and the backend↔iOS contract registry. No code ships from
> this session; future sessions build from this spec phase by phase.

---

## 1. Vision

### 1.1 The problem with v1

The app drifted from its core loop. Five tabs, two of them misspent:

- **Dungeons** has a whole tab but is unused. Two seeded objective types (`PR_ACHIEVED`,
  `STREAK_MAINTAIN`) never increment, so some dungeons are uncompletable. The only recent
  work on the feature was a crash fix.
- **Friends** is a full social layer for an effectively solo user.
- **"Quests" tab is actually the workout archive** while daily quests live on Home — a
  vocabulary inversion that makes the app harder to explain than it should be.
- **Profile is hidden** behind an avatar tap.
- **Home stacks 8–9 sections** across two coexisting design dialects (sharp "System
  Window" mono vs. rounded "Edge Flow") — `plans/03-designer-ui-refresh.md` diagnosed
  both problems.
- **The richest data in the app is the least surfaced:** per-set HR attribution, Apple
  Watch exertion scores (0–21, `backend/app/core/exertion.py`), strength percentiles,
  the cooldown engine, and WHOOP recovery/HRV/sleep all land in the DB and barely reach
  the UI.

Meanwhile the user's confirmed anchors are: **logging lifts, strength progress, and
recovery/strain data.** XP, ranks, and achievements land; daily rep-grind quests and
dungeons don't.

### 1.2 The first-principles insight

Solo Leveling's core fantasy is not "do 100 push-ups." It's **the System** — an
omniscient window that quantifies the hunter, tells him his condition, and marks when
he's ready for a boss fight.

Wearable + strength data *is* that System:

| Solo Leveling | ARISE v2 | Real data behind it |
|---|---|---|
| Mana / condition | **Hunter Condition** (0–100) | WHOOP recovery, muscle cooldowns, sleep, yesterday's strain, resting HR |
| The System speaks | **System Directive** (one line/day) | Condition + training deltas from analytics |
| A Gate opens | **PR Gate** | e1RM trend says a PR is within reach *and* Condition is high |
| Clearing the dungeon | Hitting the lift | Existing PR detection on workout create |
| Battle fatigue | **Strain** (unified 0–21) | WHOOP strain + Apple Watch exertion score |

The game layer gets *stronger* when every gamified element is derived from real
physiology and real strength trends instead of arbitrary rep grinds. That's the whole
reimagining.

### 1.3 Design pillars

1. **The System knows you.** Every gamified element is derived from real data (HR,
   recovery, e1RM trends) — never arbitrary. If a number can't be traced to physiology
   or performance, it doesn't get gamified.
2. **One visual language.** Edge Flow rounded cards as structure + System Window
   mono/bracket accents for data labels only — the "ARISE 2.0 Minimal Void" direction
   from `plans/03-designer-ui-refresh.md`, finished rather than half-adopted.
3. **Strength is the story.** XP, rank, and Gates all orbit the user's actual lifts.
4. **Fewer, denser surfaces.** 4 tabs. Home (now **Status**) cut to ~5 sections, one
   screen-height of signal before the fold.

## 2. Tab structure: 5 → 4

| # | Tab | Replaces | Contents |
|---|-----|----------|----------|
| 0 | **Status** | Home | The Status Window: hunter header, Condition, Directive, open Gate, This Week, power snapshot |
| 1 | **Hunt** | "Quests" archive + Log entry points | Calendar, workout history, BEGIN HUNT + SCAN CTAs |
| 2 | **Power** | Stats | e1RM trends, per-lift ranks, records, vessel, **new Exertion analytics** |
| 3 | **Hunter** | (Profile was hidden behind avatar tap) | Identity, achievements, Hunter Network (friends), integrations, settings |

- **Dungeons tab: deleted** (feature reborn as PR Gates, §5).
- **Friends tab: deleted** (UI demoted to a Hunter-tab section; backend untouched).
- **"Hunt" fixes the naming inversion:** workouts are hunts; the daily to-do line is a
  Directive; "quest" vocabulary is retired from navigation.

## 3. Cut list (Phase 0 cleanup)

Everything here was verified against the current tree (2026-07-06). "Cut" means delete;
"fix" means keep but repair.

### 3.1 Backend cuts

| Item | Where | Notes |
|---|---|---|
| Dungeons API | `app/api/dungeons.py` + mount in `main.py` | 9 endpoints under `/dungeons` |
| Dungeon service | `app/services/dungeon_service.py` | spawn RNG (`BASE_SPAWN_CHANCE=0.20`, `maybe_spawn_dungeon`, `ensure_minimum_dungeons`), lifecycle, claims |
| Dungeon seeds | `app/services/dungeon_seed.py` | all 18 definitions (Goblin Cave → Absolute Being's Gate). 6 of them (`dragon_lair_b`, `celestial_temple_a`, `monarchs_domain_s`, `architects_tower_s`, `rulers_gate_s_plus`, `absolute_being_gate_s_plus_plus`) are **uncompletable today**: their required `pr_achieved` objectives are never incremented — `dungeon_service.py:605` says "handled separately" but no such handling exists |
| Dungeon models + tables | `app/models/dungeon.py` (`dungeon_definitions`, `dungeon_objective_definitions`, `user_dungeons`, `user_dungeon_objectives`) | drop via Alembic migration (see prod-stamp-drift caution in memory: make it idempotent) |
| Dungeon hook in workout create | `update_dungeon_progress` call sites in `app/api/workouts.py` + screenshot service | replaced by the Gate clear-check (§6) |
| Daily quest generation + claim | `app/services/quest_service.py`: `generate_daily_quests`, `claim_quest_reward`, `seed_quest_definitions` (21 defs); `app/api/quests.py` (`GET /quests`, `POST /quests/{id}/claim`, `POST /quests/refresh`, `POST /quests/seed`) | **Keep** the helpers the Directive reuses: `calculate_todays_workout_stats` (elevated-zone minutes, peak HR, strain aggregation) and `user_has_wearable` |
| Quest models + tables | `app/models/quest.py` (`quest_definitions`, `user_quests`) | drop after Directive ships (Phase 1), not before |
| Weekly Missions — entire feature | `app/services/mission_service.py` (1,977 lines): template generators (`_generate_ppl_workouts:1264`, `_generate_upper_lower_workouts:1396`, `_generate_full_body_workouts:1521`, `_generate_single_focus_workouts:1173`, `_generate_same_group_workouts:1084`), `accessory_templates.py`, mission-mode quest takeover (`get_active_mission_for_quests:1938`, `format_mission_as_quests:1952`), **dead** `check_mission_workout_completion:1652` (never called from any path — mission workouts never auto-complete and mission XP is never credited); `app/api/missions.py` (5 endpoints) | **Goals stay**: `create_goal`, `get_user_goals`, `update_goal`, `update_goal_progress` (+ `Goal`, `GoalProgressSnapshot` models, `/goals` endpoints). Weekly report stays (`/progress/weekly-report`, `weekly_report_service.py`). Extract goal functions into a `goal_service.py` before deleting `mission_service.py` |
| Mission models + tables | `app/models/mission.py`: `WeeklyMission`, `MissionWorkout`, `ExercisePrescription`, `MissionGoal` | keep `Goal`, `GoalProgressSnapshot`, `GoalStatus` |
| Notification types | `dungeon_spawned`, `dungeon_expiring`, `mission_offered`, `mission_expiring` in `app/models/notification.py` + notifiers in `notification_service.py` | replaced by `gate_opened` (§11) |

### 3.2 Backend fixes (keep, repair)

1. **Achievement XP bypasses `award_xp`** — `achievement_service.py:112` does
   `progress.total_xp += xp` directly, so achievement XP never triggers a level-up
   check until the next workout. Route it through `award_xp(count_workout=False)`.
2. **`POST /sync` awards nothing** — `app/api/sync.py` creates workouts and PRs but
   never calls `calculate_workout_xp`/`award_xp` (no XP, no streak). Unify with the
   `POST /workouts` path.
3. **Dead XP constant** — `XP_REWARDS["first_workout_today"]` (25) is defined and never
   awarded; delete or wire (v2: delete — Directive covers the daily incentive).

### 3.3 iOS cuts

| Item | Where | Notes |
|---|---|---|
| Dungeons tab + folder | `Views/Dungeons/` — `DungeonsView.swift`, `DungeonsViewModel.swift`, `DungeonCardView.swift`, `DungeonDetailSheet.swift`, `DungeonRewardSheet.swift`, `DungeonSpawnOverlay.swift` (already dead) — 1,930 lines | Cross-cutting scrub: tab entry `ContentView.swift:67-70`; `APIClient.swift:342-390` (7 dungeon methods); `APITypes.swift` dungeon response structs + `dungeonSpawned`/`dungeonProgress` fields on the workout-create response; `DungeonDisplayable` protocol in `Utils/Extensions.swift:32-39`; `NotificationManager.swift:128`; "Missions & Dungeons" rows in `NotificationSettingsView(Model).swift` |
| Friends tab (UI move, not delete) | `Views/Friends/` stays as views; tab entry deleted; `FriendsView` re-rooted as a Hunter-tab section (§8.4) | Backend untouched |
| Daily quests UI | `Components/DailyQuestsCard.swift` (`DailyQuestsSection`, `EdgeFlowQuestRow`), `Components/QuestDetailSheet.swift` | Replaced by the Directive card (§5) |
| MissionCard + coaching setup flow | `Components/MissionCard.swift` (all 6 states), `AcceptMissionSheet`, mission paths in `Views/Coaching/` | **Keep** `GoalSetupView`, `MultiGoalSetupView`, `GoalsListSheet` — Goals survive; re-home their entry point in Power › records/goals area |
| Dead legacy Home structs | `HomeView.swift` (~23 structs, file is 2,294 lines): `QuickActionsRow:499`, `StatsScrollSection:535`, `WeeklyQuestCard:577`, `QuestStatItem:653`, `LastQuestCard:680`, `EmptyQuestCard:795`, `HunterStatsGrid:833`, `HunterStatCard:889`, `StrengthTrendCard:938`, `AchievementCard:1047`, `SystemInsightCard:1130`, `ExerciseHistorySheet:1212`, `ExerciseStatBox:1465`, `SectionHeader:1827`, `EmptyStateCard:1843`, `PRCard:1876`, `InsightCard:1883`, `QuickStatsGrid:1890`, `TodaysWorkoutCard:1900`, `ActivityRingsCard:1909`, `WeeklyStatItem:2050`, `ActivityStatItem:2082`, `HealthKitConnectCard:2127` | Verified zero external refs (some reference each other in dead chains) |
| `HistoryView.swift` — partial | Dead: `HistoryView:3`, `QuestArchiveHeader`, `AriseCalendarView`, `AriseCalendarDayCell`, `CompletedQuestRow`, `EmptyQuestArchiveView`, typealias block `:1000-1006` | **NOT fully deletable**: `QuestDetailView:661`, `QuestSummaryCard:727`, `ObjectiveDetailCard:848` are live (used by `QuestsView.swift:719,728` and `StatsView:760`); `HistoryViewModel.swift` is live via `StatsView:717`. Move the live structs out, then delete the file |
| `CooldownCard.swift` | entire file (incl. `CooldownMuscleCell`, `CooldownInfoSheet`) | preview-only; superseded by `RecoveryStatusSection` + `RecoveryDetailSheet` |
| `XPBarView.swift` | `XPBarView`, `QuestProgressBar`, `DayTrackerView`, `DayCircle` dead today; `AriseProgressBar:68` is live **only** via `DungeonDetailSheet:194` | fully deletable once Dungeons are cut |
| Dead structs elsewhere | `RecoveryMuscleTag` + `FlowLayout` (`RecoveryStatusSection.swift:134,189`), `AppTextFieldStyle` (`ContentView.swift:389`), preview-only members of `StatCard.swift` (`LiftStatCard`, `StatGridView`, `CurrencyDisplayView`, `AccessoryCard`) and `RankBadgeView.swift` (`LevelDisplayView`, `HunterTitleView`, `HunterHeaderView`, `StreakDisplayView`) | |
| Typealias migration blocks | `StatsView.swift:2295-2310` (16 aliases: `ProgressHeader`, `E1RMTrendChart`, `PercentileCard`, …), `ProfileView.swift:1404-1415` (12 aliases: `ProfileHeader`, `SettingsRow`, …) | migrate call sites to the real names, delete blocks |

### 3.4 Renames (naming inversion fix)

| Old | New |
|---|---|
| "Quests" tab (`QuestsView`) | **Hunt** tab (`HuntView`) |
| "Begin Quest" CTA | **BEGIN HUNT** |
| "Quest Archive" | **Hunt Log** |
| Home tab ("Status" label already) | Status tab, view renamed `HomeView` → `StatusView` |
| Daily quests | **System Directive** (one/day, §5) |
| Dungeons | **PR Gates** (§6) |

## 4. Hunter Condition (0–100)

The mana bar. Hero of the Status tab; input to Directive generation (§5) and Gate
spawning (§6). Computed on the fly (like `exertion_score` — never stored), new service
`app/services/condition_service.py`.

### 4.1 Inputs and normalization

Each input is normalized to a 0–100 sub-score. All source data already lands in the DB:

| # | Input | Source of truth | Weight | Normalization |
|---|---|---|---|---|
| 1 | Recovery | `daily_activity.recovery_score` (WHOOP, today) | 0.40 | as-is (already 0–100) |
| 2 | Muscle freshness | `cooldown_service.calculate_cooldowns(db, user_id, user_age)` | 0.25 | `100 − mean(cooldown_percent over the 8 tracked muscles)`, where muscles absent from `muscles_cooling` count as 0% cooldown (fully fresh) |
| 3 | Sleep | `daily_activity.sleep_hours` (today) | 0.15 | `clamp((sleep_hours − 4.0) / 3.5, 0, 1) × 100` → 7.5 h+ = 100, ≤4 h = 0 |
| 4 | Yesterday's strain | `daily_activity.strain` (WHOOP) **else** max `exertion_score` across yesterday's workouts (`compute_exertion_score` on `hr_zone_seconds`) | 0.10 | `100` if ≤10; linear down to `40` at 21 — hard training is expected, only heavy strain suppresses Condition |
| 5 | Resting-HR trend | `daily_activity.resting_heart_rate` today vs. 14-day mean | 0.10 | `100 − 10 × max(0, today − mean14)`, floor 40 — elevated RHR is an early overreach flag |

**Score** = `Σ(subscore × weight) / Σ(weight)` over **available** inputs only
(renormalization = the graceful-degradation rule). Input 2 is always available for any
user with workouts, so Condition never comes up empty. Round to integer.

### 4.2 Bands

| Band | Range | Color token | Copy |
|---|---|---|---|
| **PEAK** | 85–100 | `systemPrimary` #00D4FF | "The System favors you." |
| **BATTLE READY** | 65–84 | `successGreen` #33FF88 | "Cleared for battle." |
| **STRAINED** | 40–64 | `gold` #FFD700 | "Fight carefully." |
| **CRITICAL** | 0–39 | `warningRed` #FF3333 | "REST DECREED." |

Band thresholds are shared constants — Gates require Condition ≥ 65 to spawn (§6.2),
and the CRITICAL band forces a rest Directive (§5.2).

### 4.3 API

`GET /condition` (no `/api` prefix — routers mount bare, see §13):

```json
{
  "score": 77,
  "band": "battle_ready",
  "generated_at": "2026-07-06T14:02:11Z",
  "inputs": [
    {"key": "recovery",  "label": "Recovery",        "raw": 72,   "subscore": 72,
     "weight": 0.40, "effective_weight": 0.40, "available": true,  "source": "whoop"},
    {"key": "cooldowns", "label": "Muscle Freshness", "raw": null, "subscore": 85,
     "weight": 0.25, "effective_weight": 0.25, "available": true,  "source": "app"},
    {"key": "sleep",     "label": "Sleep",            "raw": 7.2,  "subscore": 84, ...},
    {"key": "strain_yesterday", ...},
    {"key": "rhr_trend", ...}
  ],
  "muscles_cooling": [ /* pass-through of calculate_cooldowns entries for the detail sheet */ ]
}
```

`effective_weight` is the post-renormalization weight so the detail sheet can show the
real contribution. `source` drives the provenance badges (`AriseSourceBadge` pattern:
`whoop`, `apple_watch`, `app`).

### 4.4 UI

- **Status tab hero**: arc gauge, Orbitron score, band label + band color, provenance
  chips for live inputs. Tap → **Condition detail sheet**.
- **Condition detail sheet** absorbs today's `RecoveryStatusSection`: per-input
  contribution bars (subscore × effective weight), then the muscle pills
  (`RecoveryPill` visual language, fresh/moderate/fatigued) with the existing
  `fatigue_breakdown` drill-down from `RecoveryDetailSheet`, then HRV
  (`daily_activity.hrv`) and sleep rows. Missing inputs render as
  `NO SIGNAL — weight redistributed`, never as zero.

## 5. System Directive

One line from the System per day. Replaces 3-a-day quests (cut, §3.1).

### 5.1 Generation

Server-side, on first `GET /directive/today` of the user's local day (client passes
`client_date` like the weekly report does). Deterministic for the day (persisted row).
Inputs, all existing:

- Condition score + band (§4)
- `calculate_cooldowns` — which muscle groups cleared since yesterday
- `GET /analytics/insights` engine (`IMPROVING`/`REGRESSING`/`PLATEAU`/`VOLUME_LOW`/`VOLUME_HIGH`)
- Per-lift weekly volume vs. its 4-week mean (reuse `_get_exercise_weekly_sets` logic
  from `weekly_report_service.py`)
- Streak state from `UserProgress`

### 5.2 Rule table (first match wins)

| Priority | Trigger | Directive template | Completion check |
|---|---|---|---|
| 1 | Condition band CRITICAL | "Rest decreed. Condition {score}. The System forbids the hunt." | No workout logged that local day (awarded next morning) |
| 2 | Streak lapses today without a workout **and** Condition ≥ 65 | "Your streak wavers, Hunter. One hunt keeps the flame." | Workout logged today |
| 3 | Muscle group cleared overnight **and** its top lift's weekly volume < 85% of 4-wk mean | "{Muscle} cleared for battle. {Lift} volume down {Δ}% — reclaim it." | That lift's sets today ≥ its median daily sets (4-wk) |
| 4 | Insight `PLATEAU` on a big-three lift | "{Lift} stagnates. Break the pattern — new rep range or +5 lb." | Any set on that lift today at a weight×rep bucket unused in 4 wks |
| 5 | Insight `VOLUME_LOW` (frequency < 2/wk) | "The System detects idleness. Two hunts this week — minimum." | Workout logged today |
| 6 | Open Gate exists (§6) | "The Gate waits. {GateName} closes in {n} days." | Gate cleared or attempted (workout containing that lift) |
| 7 | Default | "Maintain the pace, Hunter. {n} hunts this week." | Workout logged today |

### 5.3 Data model + API

New table `user_directives`: `id, user_id, date, directive_type, message, params (JSON),
xp_reward (default 40), is_completed, completed_at, created_at`. Unique on
`(user_id, date)`.

- `GET /directive/today?client_date=` → today's row (generates if absent)
- Completion is auto-detected (no claim button): checked on workout create (types 2–7)
  or on next-day generation (type 1), then `award_xp(xp_reward, count_workout=False)`
  — same non-workout XP path quests used.
- `GET /directive/history?limit=` → recent directives for the detail sheet.

### 5.4 UI

Renders on Status directly under Condition as a System message: mono/bracket "System
Window" styling (this card and sheet headers are where the sharp dialect survives,
§9). States: ACTIVE / COMPLETE (+40 XP stamp). Tap → Directive sheet: message, the
"why" (input lines with real numbers), reward, last-7-days history.

## 6. PR Gates

Dungeons reborn as boss fights the data says you can win. A Gate is a time-boxed PR
attempt on a specific lift, spawned only when the trend engine says the PR is within
reach **and** Condition says you're ready. Clearing it = actually hitting the lift.

### 6.1 Trend extension (prerequisite)

`GET /analytics/exercise/{id}/trend` today returns `weekly_best_e1rm`,
`rolling_average_4w`, `current_e1rm`, `trend_direction`, `percent_change` — **no slope
or projection**. Add to the trend engine (`app/api/analytics.py` → extract into
`app/services/trend_service.py`):

- `weekly_slope`: least-squares fit over the last 6 `weekly_best_e1rm` points
  (lb/week). Require ≥6 weeks with data, else no Gate for that lift.
- `projected_e1rm(days)`: `current_e1rm + weekly_slope × days/7`, only valid while
  `trend_direction == improving`.

### 6.2 Spawn rules

Evaluated on workout create (after PR detection) and by a nightly job. For each
canonical lift in `STRENGTH_STANDARDS` with ≥6 weeks of data:

1. `baseline` = current best e1RM across canonical aliases (same query PR detection uses).
2. Spawn candidate if `projected_e1rm(14) ≥ baseline × 1.01` (a real PR is projected
   inside the window).
3. Condition gate: today's Condition ≥ 65 (BATTLE READY+).
4. At most **one open Gate per lift**, at most **two open Gates total** (scarcity keeps
   them special).
5. Target set: choose `weight × reps` (weight in 5 lb increments, reps 1–8) whose Epley
   e1RM lands in `[baseline × 1.01, projected × 1.02]`, preferring plate-milestone
   weights (…, 185, 225, 275, 315, …) and rep counts near the user's recent working
   range for that lift.

### 6.3 Ranking

Rank encodes the size of the jump, sweetened for the big three:

| Rank | e1RM gain over baseline | XP on clear |
|---|---|---|
| C | 1.0–2.0% | 300 |
| B | 2.0–3.5% | 500 |
| A | 3.5–5.0% | 800 |
| S | > 5.0% | 1200 |

Big-three lifts (`back squat`, `bench press`, `deadlift` — the existing `BIG_THREE`
list in `xp_service.py:32`) get +1 rank step (cap S). Names are generated:
"B-Rank Gate: Bench 225×4".

### 6.4 Lifecycle

`open → active → cleared | expired` (statuses reuse the dungeon vocabulary minus
`claimed`/`abandoned` — XP awards on clear, no claim step; declining is just letting
it expire).

- **open**: spawned, visible on Status + push (§11). Default window **14 days**.
- **active**: user tapped ACCEPT GATE. Purely a commitment marker (shows on Status,
  Directive rule 6 references it); no mechanical difference.
- **cleared**: any set logged with `e1rm ≥ target_e1rm` on that canonical lift — hook
  into the `detect_and_create_prs` return in `app/api/workouts.py` (and the `/sync` +
  screenshot paths once §3.2-2 unifies them). Awards XP via `award_xp` immediately +
  achievement check + celebration overlay (reuse `PRCelebrationView` pattern).
- **expired**: window passed. Quiet — row moves to history, **no penalty, no nag**.

### 6.5 Data model + API

New table `pr_gates`: `id, user_id, exercise_id (canonical), rank, name,
target_weight, target_reps, target_e1rm, baseline_e1rm, projected_e1rm, weekly_slope,
condition_at_spawn, status, spawned_at, expires_at, accepted_at, cleared_at,
cleared_by_set_id (FK sets), xp_awarded, created_at`. Index `(user_id, status)`.

- `GET /gates` → open/active gates + proximity (`baseline_e1rm / target_e1rm`)
- `POST /gates/{id}/accept`
- `GET /gates/history?limit=`
- Spawn is server-driven only — no force-spawn endpoints in prod (dev seeds okay).

New service `app/services/gate_service.py`. The 18 dungeon definitions, spawn RNG, and
stretch/rare-gate mechanics die with §3.1; no definition table is needed at all —
Gates are fully generated from the user's own data.

### 6.6 UI

- **Status tab**: Open Gate card between Directive and This Week (conditional). Rank
  sigil in rank color (`rankB` #9B4A9B etc. from `Colors.swift`), lift + target set,
  proximity bar, closes-in countdown. Tap → Gate sheet.
- **Gate sheet**: designation header, target, WHY THIS GATE (weekly slope + projection
  with real numbers — the System shows its work), Condition requirement check, window,
  reward, ACCEPT GATE / let-it-close. Cleared state = celebration + achievement.
- **Hunt Log**: cleared gates render a small rank sigil on the workout row that
  cleared them.

## 7. ARISE Strain unification + Exertion analytics

### 7.1 Strain unification (D4b, presentation tier)

Today: `WorkoutSession.strain` is WHOOP-only (0–21, null otherwise);
`exertion_score` is computed on the fly from `hr_zone_seconds`
(`app/core/exertion.py: compute_exertion_score`, also 0–21, `min(21, 21·Σ(zone_weight·s)/18000)`)
and returned as a separate response field. Two names for one concept.

**v2 rule: one user-facing metric, "Strain", source-badged.** Workout responses add:

```json
"arise_strain": {"value": 14.2, "source": "whoop"}       // WHOOP present
"arise_strain": {"value": 12.8, "source": "apple_watch"} // else exertion_score
"arise_strain": null                                       // no HR data
```

Precedence: WHOOP `strain` if non-null, else `compute_exertion_score(hr_zone_seconds)`
with the session's `hr_source` as the badge source. Existing `strain` and
`exertion_score` fields stay in the payload during migration; iOS switches to
`arise_strain` everywhere strain shows (Hunt rows, detail sheets, weekly stats,
Exertion analytics). This is deliberately **not** the full custom D4b formula
(Karvonen + mechanical load) — that stays Phase-3+ future work; v2 unifies
presentation only, per the D4 decision in
`docs/wearable-heart-rate-quest-integration.md`.

### 7.2 Exertion analytics (D4a surfaces) — new Power-tab segment

All inputs already land in the DB: per-set `start_time`/`end_time`/`avg_heart_rate`/
`peak_heart_rate` (`sets` table), raw `heart_rate_samples` (set-attributed via
`ingest_heart_rate`), session `hr_zone_seconds`, weight/reps/e1RM.

**New endpoints** (`app/api/analytics.py` or a new `exertion_analytics.py` router):

1. `GET /analytics/exertion/weekly?weeks=8` — per ISO week:
   `{week_start, strain_total, strain_avg, workout_count, volume_lb, zone_seconds: {z1..z5}}`.
   Strain per workout = the §7.1 unified value. Backs two charts: strain trend and
   volume trend (**two aligned small multiples, never a dual-axis chart**), plus the
   zone-distribution stack.
2. `GET /analytics/exercise/{id}/cardiac-cost?weeks=12` — the D4a headline metric:
   - **ΔHR per matched set**: for each set with HR samples, `ΔHR = peak HR in
     [start_time, end_time + 30s] − baseline`, baseline = median bpm in the 60 s
     before `start_time` (from `heart_rate_samples`). Falls back to
     `set.peak_heart_rate − session avg` when raw samples are missing.
   - **Matched-set normalization** (v1): group sets by (weight bucket, reps) —
     same `_weight_bucket` helper PR detection uses; trend median ΔHR per group per
     week. Report the largest group with ≥2 weeks of data.
   - Response: `{exercise_id, matched_set: {weight, reps}, points: [{week_start,
     delta_hr_median, n_sets}], percent_change, trend_direction}`.
   - Confounders (rest interval, set position, RPE) are **recorded but not modeled**
     in v1 — noted in the response as `caveats` so the UI can footnote it. Full
     %e1RM-normalized modeling stays future work per D4a open questions.

**UI (Power › EXERTION segment):** strain weekly trend, volume weekly trend (aligned),
per-exercise cardiac-cost card ("Bench: −18% cardiac cost vs. 8 wks ago" — falling ΔHR
= conditioning gain), zone-distribution stacked bars per week (locked
`AriseHRZoneBar` palette, 2px gaps, fixed z1→z5 order with duration labels — the zone
colors' CVD separation is below target, so order + labels carry identity, never color
alone).

### 7.3 Cardio/sport ingestion (decided 2026-07-06)

Three-tier hierarchy for runs and sports:

1. **Apple Watch via HealthKit import — primary** (D3 decision, already resolved).
   `POST /workouts/import-healthkit` creates a real `WorkoutSession` matched to a
   seeded Cardio/Sport exercise with raw HR samples → avg/peak HR, `hr_zone_seconds`,
   computed exertion. Screenshots never compete with this path.
2. **WHOOP API sync — enrichment.** Strain/recovery via `POST /whoop/sync`, as today.
3. **Screenshot fallback — upgrade (Phase 3 work item).** The extractor already pulls
   `activity_type`, `time_range`, `duration_minutes`, `strain`, `steps`, `calories`,
   `avg_hr`, `max_hr`, and per-zone `heart_rate_zones`
   (`app/schemas/screenshot.py:54-83`; the Vision prompt covers WHOOP, Apple Fitness,
   and Strava-style summaries). **But the save path drops the richness**: activity
   screenshots persist only to `daily_activity` (which has no HR columns), no
   `WorkoutSession` is created, and `hr_source="screenshot"` is never emitted even
   though `AriseSourceBadge` supports it.

   **Upgrade:** create a `WorkoutSession` from activity screenshots using the existing
   `match_activity_to_exercise` (`app/services/screenshot_service.py:257`) → seeded
   Cardio/Sport exercise; persist `duration_minutes`, `avg_hr`/`max_hr` →
   `avg_heart_rate`/`peak_heart_rate`, extracted zone breakdown → `hr_zone_seconds`
   (parse the mm:ss zone durations), `hr_source="screenshot"`. Keep the existing
   `daily_activity` strain write for WHOOP screenshots. Result: screenshot runs appear
   in the Hunt log with a strain badge, feed Condition's yesterday-strain input, and
   count in zone analytics.

   **Strain rules by source:**
   - WHOOP screenshot → keep WHOOP's stated strain (already 0–21); `arise_strain`
     source `"screenshot"`. Never recompute over better data.
   - Non-WHOOP apps → **never convert** app-specific effort metrics (not 0–21). If a
     zone breakdown was extracted, compute our own `compute_exertion_score` from it;
     if only avg HR + duration, leave `arise_strain` null in v1 (a single-zone
     estimate is possible later but must be labeled estimated).

   **Manual controls** (CLAUDE.md philosophy): extracted duration and avg/max HR are
   editable before save — extend the `ScreenshotExerciseEditView` pattern to the
   activity fields.

## 8. Screen-by-screen

Interactive reference: `docs/mockups/arise-v2-mockup.html`. Section order below is
render order.

### 8.1 Status (tab 0, was Home — 9 sections → 5)

1. **Hunter header** (compact, keep `HunterStatusHeader` Edge Flow gradient): avatar
   (tap → **Hunter tab**, no longer a hidden sheet), name, rank/level/streak,
   inline `EdgeFlowXPBar`.
2. **Condition gauge** (§4.4) — the hero. Tap → Condition sheet.
3. **System Directive** (§5.4). Tap → Directive sheet.
4. **Open Gate card** (§6.6, conditional — hidden when no open/active gate).
5. **This Week** — merge of today's `DashboardCard` + `WeeklyReportCard` entry:
   workouts vs. goal bar, volume / time / PR pills, **BEGIN HUNT** (primary pill) +
   **SCAN** (secondary), small "Weekly Report →" link row (opens existing
   `WeeklyReportView` sheet).
6. **Power snapshot** — keep `PowerLevelsCard` (big-three e1RM + trend), "Details" →
   Power tab.

Removed from Status: `MissionCard` (cut), `DailyQuestsSection` (cut),
`RecoveryStatusSection` (absorbed into Condition sheet), Latest Achievement card
(moves to Hunter tab). Error banner + pull-to-refresh behavior unchanged.

### 8.2 Hunt (tab 1, was "Quests")

Existing `QuestsView` structure survives with renames (§3.4): header ("Hunt Log"),
BEGIN HUNT + SCAN pills (unchanged `LogView` push + photo picker), month calendar
toggle (`EdgeFlowCalendarDayCell`), history rows (`EdgeFlowWorkoutRow` — now showing
unified `arise_strain` + source badge per §7.1, and a rank sigil when the workout
cleared a Gate). Detail push (`QuestsDetailView` → rename `HuntDetailView`) unchanged
except naming. **Active-workout flow (`LogView` + children) is out of scope for v2**
apart from copy renames.

### 8.3 Power (tab 2, was Stats)

Segments: `["Power", "Exertion", "Vessel", "Records"]` (insert Exertion second).
Power/Vessel/Records keep their current views (`PowerProgressView`,
`VesselProgressView`, `RecordsView`) restyled per §9; Exertion is new (§7.2). Goals
management (kept from the mission cut) gets its entry here: a compact "Goals" row
under Power linking `GoalsListSheet`.

### 8.4 Hunter (tab 3, new — Profile promoted from hidden sheet)

Order: `HunterProfileHeader` (avatar, rank badge, level) → `HunterStatsPanel` →
**Achievements** (`HunterAchievementsSection` + the Latest Achievement card from Home)
→ **Hunter Network** (FriendsView content re-rooted: ALL FRIENDS / REQUESTS segments,
`AddFriendSheet`) → **Integrations** (Apple Health row, WHOOP row — real status, drop
the hardcoded "CONNECTED" Health Sync row) → `HunterAttributesSection` →
`SystemSettingsSection` (notifications, units, e1RM formula, privacy) → account
actions. `ProfileView` stops being a sheet; it becomes the tab root.

### 8.5 Sheets

- **Condition sheet** (§4.4), **Directive sheet** (§5.4), **Gate sheet** (§6.6).
- Keep: `WeeklyReportView`, `WorkoutDetailSheet` (with `AriseWorkoutHRSection`),
  goal sheets, achievement sheets.
- Presentation: `.presentationDetents([.medium, .large])`, drag indicator, per
  `plans/03` interaction spec.

## 9. Design-system consolidation ("Minimal Void", finished)

The rules that end the two-dialect split. Source direction:
`plans/03-designer-ui-refresh.md`; tokens live in `Utils/Colors.swift` +
`Utils/Fonts.swift` (authoritative hexes mirrored in the mockup).

1. **Structure is Edge Flow.** Cards: `cornerRadius 20` primary / `12` compact,
   `bgCard` #0f1018 on `bgVoid` #050508, `glassBorder` (white @ 0.04) 1px. Left
   accent bars only where they encode identity (lift color on exercise cards);
   otherwise none. Pills are capsules (`EdgeFlowPillButtonStyle`).
2. **System Window survives as an accent, not a structure.** Mono/bracket styling
   (`ariseMono`, `[ … ]` tags, ◆ section markers, sharp 4px corners) is reserved for:
   the Directive card + sheet, section header labels, data labels/provenance badges,
   and the auth screen. Everything else drops sharp panels — including `StatsView`,
   `ProfileView`, `FriendsView` chrome.
3. **Background**: replace `VoidBackground(showGrid:)` grid with ambient radial
   gradient (`systemPrimary` @ 0.02, per plans/03 §1).
4. **One lift-color system.** `Color.exerciseColor(for:)` (`Colors.swift:223`) is the
   only lift mapping. Retire `BigThreeLift.liftColor` (`PowerLevelsCard.swift:20-27`)
   and the ad-hoc `muscleColor(for:)` in `EdgeFlowWorkoutRow`
   (`QuestsView.swift:651-666`) — muscle pills derive from a fixed muscle→lift-color
   table added next to `exerciseColor`.
5. **Typography**: `ariseDisplay` (Orbitron) for stat values, `ariseHeader` (Rajdhani)
   for section headers/titles, `ariseMono` (JetBrains Mono) for labels/tags/metrics,
   system font for body — Edge Flow surfaces stop bypassing the semantic constructors.
6. **Emoji → SF Symbols** everywhere (mapping table in plans/03).
7. **Legacy color aliases** (`appPrimary`, `appEnergy`, `gradientStrength`, … at
   `Colors.swift:157-195`) deleted once their last references go with the dead-code cut.
8. **Rank colors**: `rankE` #808080 · `rankD` #4A9B4A · `rankC` #4A7BB5 · `rankB`
   #9B4A9B · `rankA` #FFD700 · `rankS` #FF4444; titles Awakened / Hunter / Warrior /
   Elite / Commander / Shadow Monarch (`HunterRank`, `Colors.swift:240-304`) — used by
   Gate sigils as well.

## 10. XP economy rebalance

Level curve unchanged: `xp_for_level(level) = 100 × level^1.5`
(`xp_service.py:35`); ranks E 1–10 / D 11–25 / C 26–45 / B 46–70 / A 71–90 / S 91+.

### 10.1 Source-by-source

| Source | Current | v2 | Notes |
|---|---|---|---|
| Workout complete | 50 | 50 | unchanged (`XP_REWARDS`) |
| Volume bonus | 5 / 1,000 lb | 5 / 1,000 lb | unchanged |
| Big-three working set | 3 / set | 3 / set | unchanged |
| PR | 100 each | 100 each | unchanged |
| Streak | 150 @7d, 500 @30d, 75 @other 7-multiples | same | unchanged (`award_xp:193-204`) |
| Daily quests | 3/day × 15–70 (potential ~735/wk) | **0 — cut** | |
| System Directive | — | **+40/day followed** (potential 280/wk) | §5 |
| Dungeons | 150–3,000 + stretch bonus | **0 — cut** | |
| PR Gates | — | **C 300 / B 500 / A 800 / S 1,200 per clear** (~1–3/month) | §6.3 |
| Achievements | 26 defs, 50–1,000 | + ~8 new defs below | now routed through `award_xp` (§3.2-1) |
| Weekly mission | 50 + 50/goal (never actually credited — dead code) | **0 — cut** | |
| `POST /sync` workouts | **0 (bug)** | same as `POST /workouts` | §3.2-2 |

**Pacing check:** on a realistic 4-hunts/week schedule, workout-path XP is ~650/wk.
Current *potential* adds ~900/wk of quest+dungeon XP — but the owner's actual usage
(quests part-claimed, dungeons ignored) earned a fraction of that. v2 potential adds
~280 (Directive) + ~150/wk amortized (Gates) + achievement grants — **similar to
actual current earnings, so perceived level pacing holds** while every remaining XP
grant is tied to real training signal.

### 10.2 New achievement lines (`seed_achievement_definitions` additions)

| id | Name | Requirement (new `requirement_type`s) | XP |
|---|---|---|---|
| `gate_first` | Gate Breaker | `gate_cleared` ≥ 1 | 200 |
| `gate_5` | Gatekeeper | `gate_cleared` ≥ 5 | 400 |
| `gate_s_rank` | S-Rank Clearance | clear an S-rank gate | 750 |
| `directive_7` | The System's Chosen | 7 consecutive directives followed | 200 |
| `directive_30` | Absolute Obedience | 30 consecutive | 500 |
| `condition_peak_7` | Peak Form | 7 consecutive days Condition ≥ 85 | 300 |
| `strain_18` | Redline | single workout `arise_strain` ≥ 18 | 250 |
| `engine_built` | Engine Built | cardiac cost −15% on any lift (8-wk window) | 400 |

`check_and_unlock_achievements` gains the new requirement types; existing 26
definitions unchanged.

## 11. Notifications (wired at last)

**Permission prompt: after the first completed workout** — resolves the CLAUDE.md open
decision. Trigger: dismissal of the post-save celebration in `LogView` (the user just
had their best moment; the ask lands with context: "The System wants to notify you
when a Gate opens."). Call the existing, currently-uncalled
`NotificationManager.requestAuthorization()` (`Services/NotificationManager.swift:22`).

| Notification | Kind | Status |
|---|---|---|
| `gate_opened` | push (APNs, new notifier) | new — "A B-Rank Gate has opened: Bench 225×4. 14 days." |
| `weekly_report_ready` | push | exists (`notification_service.py`) — keep |
| `streak_at_risk` | local | exists (scheduled in `HomeViewModel.scheduleLocalNotifications`) — keep |
| `achievement_unlocked`, `level_up`, `rank_promotion`, friend types | push | exist — keep |
| `dungeon_spawned`, `dungeon_expiring`, `mission_offered`, `mission_expiring` | — | **cut** (§3.1) |

No push for the daily Directive — it greets you on open; notifying daily would train
ignore-behavior and cheapen `gate_opened`.

## 12. Build phases (one per future session, roughly)

- **Phase 0 — Cleanup + restructure.** Everything in §3 (cuts, fixes, renames), tab
  restructure to 4 tabs (§2, §8.4 Hunter tab from ProfileView + FriendsView), design
  consolidation pass (§9). Pure subtraction + reshuffle; no new systems. Ship criteria:
  build green, `pytest` green, app usable with 4 tabs.
- **Phase 1 — Condition + Status + Directive.** `condition_service.py` + `GET
  /condition` (§4), `user_directives` + `GET /directive/today` (§5), Status tab
  redesign (§8.1) with Condition hero, Directive card, sheets.
- **Phase 2 — PR Gates.** Trend slope/projection (§6.1), `gate_service.py` +
  `pr_gates` table + endpoints (§6.5), clear-detection hook, Status Gate card + Gate
  sheet, `gate_opened` push + the permission prompt (§11).
- **Phase 3 — Exertion analytics + achievements + XP.** §7 endpoints + Power Exertion
  segment, §10.2 achievements, XP fixes (§3.2), Hunt-row strain unification, cardio
  screenshot upgrade (§7.3 tier 3: activity screenshots → `WorkoutSession` with
  `hr_source="screenshot"`).

Each phase that mirrors backend schemas into Swift triggers the contract-mirror QA
rule (global CLAUDE.md): run `/evaluate` pointed at the backend Pydantic schemas, not
the spec prose. §13 is the checklist input for that.

## 13. Contract registry (backend ↔ iOS)

Mount note: routers mount **without** an `/api` prefix (`main.py:389-409`) — paths
below are the real ones. JSON is snake_case; iOS `APITypes.swift` structs use explicit
`CodingKeys`.

### 13.1 `GET /condition` → `ConditionResponse`

| JSON field | Type | Null? | Swift property |
|---|---|---|---|
| `score` | int 0–100 | no | `score: Int` |
| `band` | `"peak" \| "battle_ready" \| "strained" \| "critical"` | no | `band: ConditionBand` (enum, raw String) |
| `generated_at` | ISO8601 | no | `generatedAt: Date` |
| `inputs[].key` | `"recovery" \| "cooldowns" \| "sleep" \| "strain_yesterday" \| "rhr_trend"` | no | `key: String` |
| `inputs[].label` | string | no | `label: String` |
| `inputs[].raw` | number | yes | `raw: Double?` |
| `inputs[].subscore` | int 0–100 | yes (unavailable) | `subscore: Int?` |
| `inputs[].weight` / `effective_weight` | float | no | `weight` / `effectiveWeight: Double` |
| `inputs[].available` | bool | no | `available: Bool` |
| `inputs[].source` | `"whoop" \| "apple_watch" \| "app"` | yes | `source: String?` |
| `muscles_cooling[]` | existing cooldown entry shape (`GET /analytics/cooldowns`) | no (may be empty) | reuse existing `MuscleCooldown` struct |

### 13.2 `GET /directive/today` → `DirectiveResponse`

| JSON field | Type | Null? | Swift property |
|---|---|---|---|
| `id` | string | no | `id: String` |
| `date` | `YYYY-MM-DD` | no | `date: String` |
| `directive_type` | `"rest" \| "streak_save" \| "reclaim_volume" \| "break_plateau" \| "frequency" \| "gate_reminder" \| "maintain"` | no | `directiveType: String` |
| `message` | string | no | `message: String` |
| `params` | object (type-specific: `lift`, `muscle`, `delta_pct`, `gate_id`, …) | yes | `params: [String: AnyCodable]?` (or typed per-case) |
| `xp_reward` | int | no | `xpReward: Int` |
| `is_completed` | bool | no | `isCompleted: Bool` |
| `completed_at` | ISO8601 | yes | `completedAt: Date?` |

### 13.3 `GET /gates` → `[GateResponse]`

| JSON field | Type | Null? | Swift property |
|---|---|---|---|
| `id` | string | no | `id: String` |
| `exercise_id` / `exercise_name` | string | no | `exerciseId` / `exerciseName: String` |
| `rank` | `"C" \| "B" \| "A" \| "S"` | no | `rank: String` |
| `name` | string ("B-Rank Gate: Bench 225×4") | no | `name: String` |
| `target_weight` / `target_reps` | float / int | no | `targetWeight: Double`, `targetReps: Int` |
| `target_e1rm` / `baseline_e1rm` / `projected_e1rm` | float | no | `targetE1rm` etc. |
| `weekly_slope` | float (lb/wk) | no | `weeklySlope: Double` |
| `condition_at_spawn` | int | no | `conditionAtSpawn: Int` |
| `status` | `"open" \| "active" \| "cleared" \| "expired"` | no | `status: GateStatus` |
| `spawned_at` / `expires_at` | ISO8601 | no | dates |
| `accepted_at` / `cleared_at` / `cleared_by_set_id` / `xp_awarded` | — | yes | optionals |

### 13.4 Workout payload addition (`GET/POST /workouts*`) — §7.1

| JSON field | Type | Null? | Swift property |
|---|---|---|---|
| `arise_strain` | object | yes | `ariseStrain: AriseStrain?` |
| `arise_strain.value` | float 0–21 | no | `value: Double` |
| `arise_strain.source` | `"whoop" \| "apple_watch" \| "screenshot"` | no | `source: String` |

(`strain`, `exertion_score` remain during migration; remove from iOS use.)

### 13.5 `GET /analytics/exertion/weekly` → `[ExertionWeekPoint]`

`week_start` (date, no) · `strain_total` / `strain_avg` (float, yes when no data) ·
`workout_count` (int) · `volume_lb` (float) · `zone_seconds` (`{z1..z5: int}`, may be
empty — same shape as `WorkoutSession.hr_zone_seconds`).

### 13.6 `GET /analytics/exercise/{id}/cardiac-cost` → `CardiacCostResponse`

`exercise_id` · `matched_set {weight, reps}` (yes — null when no matched group) ·
`points [{week_start, delta_hr_median, n_sets}]` · `percent_change` (float, yes) ·
`trend_direction` (reuse `TrendDirection` values) · `caveats [string]`.

### 13.7 Existing endpoints v2 depends on (verified 2026-07-06)

`GET /analytics/exercise/{id}/trend` · `GET /analytics/percentiles` ·
`GET /analytics/prs` · `GET /analytics/insights` · `GET /analytics/cooldowns` ·
`GET /progress/weekly-report` · `GET /progress` (+ achievements routes) · `/goals` CRUD ·
`/friends` routes · `/activity` routes · `POST /workouts` · `POST /notifications/device-token`.

---

*End of spec. Mockup: `docs/mockups/arise-v2-mockup.html`. Code cited throughout was
verified against the tree on 2026-07-06; re-verify file:line anchors before each build
phase — they drift.*

