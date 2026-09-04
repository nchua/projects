# ARISE v3 — The System Coaches

> **Status:** Draft v2 for review (2026-09-04). Written from a first-principles review of the
> shipped v2/v2.1 product, the `training-calendar` PWA, the `Fitness Coach` Cowork job, and
> two code audits (iOS logging flow; backend intelligence primitives), then revised after two
> independent red-team passes (product/athlete lens; staff-engineer feasibility lens — §19).
> Code anchors verified against the working tree on 2026-09-04; re-verify `file:line` before
> each build phase, they drift.
>
> **What this is:** the product definition for the next step-change. It keeps the v2 thesis
> ("every gamified element derives from real data") and closes the loop the v2 spec left
> open: the app records and grades, but it does not **plan, prescribe, or adapt**. v3 makes
> the System a coach — with the engine owning every number and the model owning the prose.
>
> **What this is not:** a redesign. Minimal Void, the 4-tab structure, Condition, Gates, XP,
> and the ingestion paths all stay. v3 adds three systems (Campaign, Load, Coach), rebuilds
> one surface (the active-hunt logger), and retires two external crutches (the PWA and the
> Cowork weekly-review job).

---

## 0. TL;DR

Today the user's training system is spread across four things that don't talk to each
other:

| Artifact | Holds | Problem |
|---|---|---|
| ARISE iOS + backend | logging, XP, Condition, Directive, Gates, analytics | no concept of a plan; Directive is a rules engine that mostly says MAINTAIN; Gates have never spawned |
| `training-calendar/` PWA | the actual 6-month run+lift program, weekly check-offs, a hand-rolled "AHEAD — EASE UP" pace verdict | static `data.js`, no loads, manual check-off, its injury guard is 15 lines of JS |
| `Fitness Coach/` + scheduled Cowork job | the intended weekly coach: review the week, prescribe next week's loads | 7 consecutive failed runs (May 10 → Aug 6); depends on a `weekly_export.py` that does not exist; its Week 1 plan (Fri push / Sat pull / Sun legs, 3×3) contradicts the PWA plan (Sat squat 5×5 / Sun bench 5×5) |
| Apple Watch / WHOOP → HealthKit → app | HR, runs, sleep, HRV, RHR, recovery | foreground-only sync; runs lag until the app is opened; HRV is stored and Condition never reads it |

**v3 collapses these into one loop inside the app: Plan → Prescribe → Log → Adapt.**

1. **LogView v2 + Gates v2 first** (one session, no new tables). "Last time" beside every
   set, ghost values from the last session, an explicit ✓ that starts a countdown rest timer,
   drafts that survive an app kill, and the four constant changes that let a Gate actually
   spawn. This is the change that alters Saturday behavior; everything else builds on the
   data it produces.
2. **Campaign** — the program becomes a first-class object (arcs, weeks, hunt templates,
   progression rules). The PWA's `data.js` is imported once and the PWA is retired.
3. **Prescription** — every planned hunt materialized with real loads (weight × reps, RPE
   optional; miles × HR cap for runs) from the user's own last session and e1RM.
   Prescribed sets become the ghost values in the logger.
4. **Load + Overreach Guard** — one training-load currency, a run-only acute:chronic ratio,
   and mileage rules stated against the *plan's* ramp. The injury guard the PWA hand-rolled,
   done properly and without vetoing the plan it protects.
5. **The Coach** — a Sunday **Weekly Debrief** written by Claude over a structured athlete
   context: the narrative, the concerns, and a ranked set of typed plan adjustments that the
   engine generated and the user accepts with a tap. Replaces the weekly report's template
   prose and the Cowork job. The daily line stays deterministic in v3.
6. **Plumbing** — background HealthKit delivery, a profile timezone and `local_day` on
   every session, honest `weight_unit` math, one exercise-family scheme, an SDK pin.

---

## 1. Jobs to be done

Written for the actual user: a hybrid athlete who lifts heavy Saturday/Sunday at a full gym,
trains light at an apartment gym on WFH days, runs three days a week on a 6-month mileage
ramp, wears an Apple Watch and a WHOOP, was injured in 2024 by ramping mileage too fast, and
cares most about PRs on the big lifts (roadmap §1: "North star: Strength PRs").

| # | Job | How it's served today | Evidence | Served |
|---|---|---|---|---|
| J1 | **Tell me what to do today** — the session, the loads, push or back off | Directive (one line, rules engine); the PWA (static plan, no loads); the Coach job (never ran) | Rules 4 (BREAK_PLATEAU) and 5 (FREQUENCY) are structurally dead for a 2-lift-day/week user (`analytics.py:690` needs >8 e1RM points per lift; `analytics.py:701` counts imported runs as sessions). Rule 7 (LIFT_LAG) fires spuriously every Saturday because the rolling 7-day window holds only last Sunday (`directive_service.py:48-62`, `:397`). Rule 1 (REST) needs a WHOOP score. The user sees MAINTAIN most days (v2.1 interview: "Directive is too vague") | ~20% |
| J2 | **Let me log it fast, without thinking** | Manual entry from blank rows; screenshot scan behind a credit paywall; HealthKit import for runs | No "last time" anywhere in the logger (`LogViewModel.swift:93-102` creates one blank set; `getExerciseTrend` never called from Log). Set completion is derived from `weight>0 && reps>0` in five places, so the rest timer fires while typing "1" of "12" (`LogView.swift:1108-1115`). Timer is global count-up, off-screen by exercise 3. No templates, no routines, no repeat-last-workout. Draft dies on swipe-back or app kill. Session duration measured then discarded (`LogViewModel.swift:232`); bodyweight flag dropped at save (`APITypes.swift:191-204`); `rir` hardcoded nil (`LogViewModel.swift:217`) though the contract carries it | runs ~70%, lifts ~30% |
| J3 | **Show me I'm getting stronger and when I'm ready to PR** | e1RM charts, percentiles, PR detection, Gates | Charts are good. Gates need 6 Monday-keyed weekly points per lift (`SLOPE_WINDOW_WEEKS`, `trend_service.py:19`, used as both the minimum and the fit window at `:59-61`) and a projection 1% past the **all-time** best (`gate_service.py:274`) — a 5×5 trajectory cannot beat an old heavy single; Sat+Sun sessions collapse to one weekly point. No gate has spawned since Phase 2 shipped (2026-07-12) | ~55% |
| J4 | **Keep me from getting hurt while I ramp mileage and lift heavy** | Muscle cooldowns, Condition, the PWA's "AHEAD — EASE UP" | No acute:chronic ratio, ramp rate, or long-run share anywhere in the backend. Cardio fatigue is duration-only and capped at 5 effective sets, so a 15-mile long run costs the same recovery as a 75-minute jog (`cooldown_service.py:122-123`). Condition's strain input is yesterday-only | ~25% |
| J5 | **Review my week and adjust the plan** | Weekly report (goal pace only, five static template suggestions at `weekly_report_service.py:354`); the Cowork job | The weekly report has no plan to compare against. The Cowork job was the user's attempt to bolt a real coach on from outside and it never produced a review | ~10% |
| J6 | **Make training feel like a game I want to open** | XP, rank, achievements, celebrations, Condition gauge | The parts tied to real signal land. The daily hook (Directive) and the boss fight (Gate) are the weak links because they rarely say anything true or new. Streaks lie for a runner: HealthKit imports never call `award_xp` (verified: no XP/streak path in `healthkit_service.py` or the import endpoint) | ~60% |
| J7 | **Get my wearable data in without effort** | HealthKit foreground sync, WHOOP OAuth sync, screenshot fallback | All sync is foreground-triggered (`SyncCoordinator.swift:23`; no `HKObserverQuery`/`enableBackgroundDelivery` anywhere despite `UIBackgroundModes` declaring fetch/processing). The PWA README apologizes for the lag. HRV is written (`whoop_service.py:606`, HealthKit since v2.1) and returned by `/activity`, but no scorer reads it | ~60% |

**The pattern:** J1, J4, J5 are the coach's jobs and the least served. J2 is the daily
friction that decides whether the data the coach needs exists at all. J3's payoff mechanic
exists but is miscalibrated. v3 orders work accordingly: J2 + J3 in one session (they need
no new tables), then plan + prescribe (J1), then load (J4), then the coach (J5).

---

## 2. Product loop

### 2.1 Today

```
open app → glance Condition + Directive (MAINTAIN)
        → decide session from the PWA, from memory
        → train
        → log from blank rows (or scan, or wait for HealthKit on next open)
        → PR / XP celebration
        → (rarely) Power tab; (rarely) weekly report
```

No arrow feeds back into tomorrow. The app grades what happened; nothing it computes
changes what the user does next.

### 2.2 v3

```
 open app → Status: TODAY'S HUNT (prescribed, readiness-modulated at fetch time)
                    ▼
          BEGIN HUNT (pre-filled: ghost targets + "last time")
                    ▼
          confirm-or-adjust each set · ✓ → rest countdown
                    ▼
          save → one celebration (PR · Gate · XP)
                    ▼
          planned_hunt linked · load updated · next hunt re-prescribed on next fetch
                    ▼
 Sunday → WEEKLY DEBRIEF (engine ops + Coach prose) → ACCEPT → next week rewritten
```

Every arrow is a real data path. Generation is lazy (on fetch, idempotent per day) in v3;
a scheduler is added only when pushes need pre-written content (§9.2).

---

## 3. Design pillars (v2's, plus two)

1. **The System knows you.** (v2) Derived from real data or it doesn't ship.
2. **One visual language.** (v2) Minimal Void, finished.
3. **Strength is the story.** (v2)
4. **Fewer, denser surfaces.** (v2)
5. **The System prescribes, the Hunter decides.** New. Every prescription and every
   proposal shows its numbers and has a one-tap override. No silent changes to the plan.
6. **The engine owns the numbers; the model owns the prose.** New. Every load, mile, flag,
   and adjustment op is computed deterministically and validated against hard bounds. The
   LLM explains, prioritizes, and narrates; it never decides a weight.

---

## 4. Campaign — the program as a first-class object

### 4.1 Vocabulary

| Term | Meaning | Maps to |
|---|---|---|
| **Campaign** | A multi-month program with a goal | the PWA's whole `PHASES` array |
| **Arc** | A block with its own mileage band and emphasis | one PWA phase ("Months 1–2, 7–13 mi/wk, long run 4.5") |
| **Hunt template** | A weekday's session shape inside an arc | one PWA `days[]` entry |
| **Planned hunt** | A template materialized onto a calendar date, with a prescription | new |
| **Prescription** | Concrete targets for a planned hunt | new (§5) |

### 4.2 Data model

New tables (all keyed by `user_id`; idempotent migrations chaining from the current single
head `lying_tricep_aliases`):

```
campaigns            id, user_id, name, goal, start_date, status(active|paused|completed),
                     source(import|template), created_at
campaign_arcs        id, campaign_id, index, name, weeks, run_miles_min, run_miles_max,
                     long_run_miles, deload_every_n_weeks (default 4), deload_factor (0.75),
                     notes
hunt_templates       id, arc_id, weekday(0-6), type(lift|run|light|rest), title,
                     location_tag, load_hint(0-100), items JSON
planned_hunts        id, user_id, campaign_id, arc_id, template_id, date(local),
                     status(planned|done|modified|skipped|moved), session_id FK, moved_to,
                     prescription JSON, prescription_version, generated_at, rationale JSON
```

`hunt_templates.items` is the plan's *shape*, not its loads. Every item that the PWA writes
as "A or B" carries `alternatives` with a default, so WFH days don't import as blank rows:

```json
[
  {"family": "back_squat", "sets": 5, "reps": [5,5], "role": "main",
   "progression": "linear", "increment_lb": 10, "rpe_cap": 8},
  {"family": "leg_press", "alternatives": ["walking_lunge"], "sets": 3, "reps": [10,12],
   "role": "accessory", "progression": "double", "increment_lb": 10},
  {"note": "Core circuit — 10 min"}
]
```

Runs: `{"run": "easy", "miles": [2, 2.5]}` or `{"run": "long", "miles": "arc"}`.

**`family`** is the one canonicalization scheme. The seed already groups 169 canonical
exercises and 349 aliases by `canonical_id` (`models/exercise.py:19`), so a family is
`canonical_id` plus a curated overlay for the cases the audit found disagreeing
(`xp_service.py:31` big-three substrings, `analytics.py:126` keyword map,
`cooldown_service.py:437` fuzzy muscle map, `pr_detection.py:44`; `exercise_equivalence.py`
has no caller outside its test):

```
exercise_families    id (slug), display_name, primary_muscle, is_big_three, standards_key
exercises            + family_id FK — backfilled from canonical_id via a committed
                       name→slug dict; custom exercises name-matched, NULL allowed
```

Consumers switch to `family_id` in the phase where each first needs it (§16); the
substring schemes are deleted when their last reader moves, not before.

### 4.3 Import and templates

- **`POST /campaign/import`** accepts the PWA's `data.js` shape verbatim. Sets × reps
  strings ("5×5", "3×10-12", "2–2.5 mi", "3 → 4.5 mi (build weekly)") parse into `items`;
  "A or B" becomes `family` + `alternatives`; time-based items ("Core circuit 10 min",
  "Light accessory only 15–20 min") become `note` rows. Anything unparseable is flagged in
  the response so nothing is silently dropped. One-time script
  `scripts/import_training_calendar.py` runs it for the owner.
- **Which plan:** the PWA plan is the default import (it has check-offs and was trained
  against). The Cowork Week 1 plan was never trained and is not imported. Open question
  §18.2 records this as a decision to confirm, not to revisit.
- **Templates:** one seed — the owner's hybrid plan. No library in v3.
- Editing is in-app and coarse: move a hunt, skip it, swap two templates, change an arc's
  mileage band. Template item editing stays a JSON edit in v3.

### 4.4 Materialization and linking

- **Lazy, idempotent.** `GET /hunts/today` and `GET /hunts/week` materialize any missing
  `planned_hunts` for the requested range (+7 days) on first fetch. No scheduler needed;
  the same pattern v2 chose for gate evaluation.
- **Linking a logged session:** on save (all ingest paths), link to the planned hunt on the
  same `local_day` with a matching `type`; else the nearest same-type planned hunt within
  ±2 days → that hunt becomes `moved` with `moved_to = session day`. A Friday lift against
  a Saturday plan is `moved`, not `skipped` + unlinked.
- **Status:** `done` = every `main` and `secondary` family in the template appears in the
  session (accessories dropped still count as done); `modified` = a main/secondary family
  is missing or swapped outside `alternatives`; `skipped` = the day passed with no link.
  Past `planned` hunts flip to `skipped` on the next fetch.

### 4.5 API

| Endpoint | Returns |
|---|---|
| `GET /campaign/current` | campaign + arcs + current arc index + week-in-arc + deload flag |
| `GET /hunts/today?client_date=` | today's `PlannedHuntResponse` (prescription + modulation applied now), or `null` on rest days |
| `GET /hunts/week?start=` | 7 planned hunts with status + linked session summaries — the Hunt tab week view and the PWA replacement |
| `PUT /hunts/{id}` | `{status: skipped}` · `{moved_to: date}` · `{swap_with: id}` |
| `POST /campaign/import`, `POST /campaign`, `PUT /campaign/{id}` | as above |

### 4.6 UI

- **Status tab:** **TODAY'S HUNT** card takes the Directive card's slot (the System line
  renders inside it, §8.3). Type, title, location tag, the main lift's prescribed top set
  ("Back Squat 5×5 @ 235 · +5"), or the run ("Easy 2.5 mi · HR ≤ 150"), modulation line if
  any, BEGIN HUNT. Rest days: quiet REST card with tomorrow's hunt.
- **Hunt tab:** the month calendar gains a **week strip**: 7 day cells with planned type
  glyph and done/moved/skipped state, plus the pace strip the PWA had
  (`WK 5 · 4.8/9.6 MI · 2 LIFTS · ON PACE`). Tap a future day → planned hunt sheet with
  the prescription and move/skip. PWA parity; the PWA retires when it ships (§11).

---

## 5. Prescription engine (deterministic)

`app/services/prescription_service.py`. Pure function of (template item, athlete history,
readiness, load state) → concrete sets, with a `rationale` carrying the real numbers used.
No LLM in this path.

### 5.1 Lifts

**Anchor selection**, per family, in order:

1. Last linked session of that family within 21 days → anchor = that session's working
   weight and the progression verdict below.
2. Else e1RM-derived start: best set in 90 days **with reps ≤ 8** (Epley overestimates
   high-rep sets), weight = `round_to_increment(e1rm × pct_for_reps(target) × 0.90)`.
3. Else no anchor → sets × reps with weight `null`; rationale "first session — pick a load
   you can finish at RPE 7–8" (the Coach's own Week 1 instruction, now in-app).

**Progression verdicts** are decided by **reps**; RPE is optional and only ever slows
progression:

| Rule | Last session | Next prescription |
|---|---|---|
| `linear` (main lifts) | every set hit target reps | `+increment_lb` — unless RPE was logged and any set was ≥ `rpe_cap + 2`, then hold |
| | any set short by 1 rep | hold weight |
| | ≥ 2 sets short by ≥ 2 reps, **twice in a row** | `−10%`, round to increment, flag `deload_lift` |
| `double` (accessories, range [lo, hi]) | every set ≥ `hi` | `+increment_lb`, target reps reset to `lo` |
| | else | hold weight, target `min(hi, last_reps + 1)` |

RPE absent = pass. Two successful 5×5 sessions at RPE 9 progress; the next miss holds.

**Readiness modulation** is applied at **fetch time** (`GET /hunts/today`), never at
materialization — the morning's sleep, HRV, and WHOOP recovery don't exist at 02:00:

| Band | Modulation |
|---|---|
| PEAK / BATTLE READY | none; if a Gate targets this hunt, the gate attempt is set 1 (§10) |
| STRAINED | main lifts ×0.95, drop the last accessory set; a Gate attempt is deferred to the next hunt on that family |
| CRITICAL | hunt becomes `light`: main lifts ×0.85 for 3 sets, or the REST option on the card |

Lifts never enter the Overreach Guard's veto path (§6.4); `deload_lift` and the arc's
deload cadence are their back-off mechanisms.

Rounding: 5 lb barbell, 2.5 lb dumbbell (per family), honoring `preferred_unit` (2.5 /
1.25 kg) once §12 lands `weight_lb`.

### 5.2 Runs

- **Weekly target miles** = linear ramp from `run_miles_min` to `run_miles_max` across the
  arc's weeks; every `deload_every_n_weeks`-th week × `deload_factor`. Same math as the
  PWA's `expectedMiles()`, moved server-side and stored on the planned week so §6 can
  compare against it.
- **Long run** = the arc's `long_run_miles` progression for that week (the plan is the
  authority). Easy runs split the remainder across the template's easy-run days, clamped to
  each template's range.
- **Effort, not pace:** easy and long runs carry an HR cap = the upper bound of zone 2 in
  the app's existing zone table (the same `zoneKey(forPercent:)` boundaries
  `HealthKitManager` uses to compute `hr_zone_seconds`, keyed off profile age), overridable
  in Hunter › Coach settings. Pace is reported after, never prescribed.
- **Guard:** §6.4 may reduce a run's distance or convert it to easy; the card says why.

### 5.3 Where prescriptions show

Today's Hunt card (top set), planned hunt sheet (all sets), and pre-filled into LogView v2
as ghost values (§7.1).

---

## 6. Load and the Overreach Guard

### 6.1 One currency

`app/services/training_load_service.py`. Per session, one `load` number; `miles` kept
separately because the rules are stated in miles:

| Source | Load formula | Fallback |
|---|---|---|
| Run/cardio with HR zones | Edwards TRIMP: `Σ zone_minutes × zone_weight`, z1..z5 = 1..5 (from `hr_zone_seconds`) | duration × 2.5, flagged `estimated` |
| Lift | session-RPE (Foster): `(session_rpe or mean set rpe) × duration_minutes` | if no RPE: `Σ sets × 6 × duration/60`, flagged `estimated` (duration persists after §7.5) |
| WHOOP strain | display only (`arise_strain`); never mixed into load | — |

TRIMP also replaces duration-with-a-cap as the cardio input to `cooldown_service`
(`cooldown_service.py:122-123`), so a long run finally costs more recovery than a jog.

### 6.2 Daily series

New table `daily_training_load`: `user_id, local_day, run_load, lift_load, total_load,
miles, run_acute_7d, run_chronic_28d, run_acwr, miles_7d, miles_plan_7d, longest_run_7d,
flags JSON`. Recomputed for the trailing 35 days on every ingest path (the three that share
PR detection plus HealthKit import) and on any `GET /load`. Acute/chronic are 7- and 28-day
EWMAs (a rest day decays rather than cliff-drops). Requires `local_day` (§12.1).

### 6.3 Rules

Stated against the **plan**, not last week, so a post-deload week (×0.75 → ×1.0 is a 33%
jump by design) does not trip the guard:

| Flag | Condition | Meaning |
|---|---|---|
| `ramp_high` | `miles_7d > 1.20 × miles_plan_7d` and `miles_7d > 8` | ahead of the plan's ramp — the PWA's rule, kept |
| `long_run_share` | `miles_7d ≥ 15` and `longest_run_7d > 0.40 × miles_7d` | too much of a real week in one run; below 15 mi/week the plan's `long_run_miles` is the authority and no flag exists |
| `run_acwr_high` | `run_acwr > 1.30`, **only after 28 days of run history** | acute running load outrunning fitness |
| `run_acwr_critical` | `run_acwr > 1.50`, same cold-start rule | classic injury-risk zone |
| `deload_due` | week-in-arc hits the arc's cadence, or two `deload_lift` verdicts in one week | planned or earned back-off |

ACWR is computed on **run load only**. A heavy Sat/Sun weekend spikes total load every
Monday; that is the plan working, not a risk signal.

### 6.4 The Overreach Guard

Applied at fetch time to **runs only**, after readiness modulation:

| Flag(s) | Action |
|---|---|
| `run_acwr_critical` **or** (`run_acwr_high` and Condition < 65) | today's run → REST DECREED (v2 copy) with the numbers |
| `run_acwr_high` | −20% distance, converted to easy |
| `ramp_high` | cap the week's remaining run miles so `miles_7d ≤ 1.20 × miles_plan_7d`; long run cut first |
| `long_run_share` | cap the next long run at 40% of `miles_7d` |
| `deload_due` | arc `deload_factor` on runs; lifts drop one set per main lift |

Everything the guard does is written into `planned_hunts.rationale` and rendered on the
card ("Run cut to 2 mi: 14% ahead of the arc's ramp").

### 6.5 Condition v2

Two contained changes in `condition_service` (weights at `condition_service.py:25-30`):

- **Input 4 replaced:** "yesterday's strain" → **acute-vs-chronic total load**, subscore
  `100` at ratio ≤ 1.0, linear to `40` at 1.5, floor 40; unavailable (renormalized away)
  until 28 days of history. Same weight 0.10.
- **Input 6 added:** **HRV trend** (weight 0.10; recovery's 0.40 → 0.30 when HRV is
  present): 7-day mean vs 28-day mean, subscore `100 − 300 × max(0, 1 − ratio)`, floor 40.

Band thresholds unchanged.

### 6.6 Surfaces

A compact **LOAD** strip on Status under Condition (28-day run acute/chronic sparkline,
ACWR badge, `miles_7d` vs plan), tap → Load sheet (rules, flags, the week's runs and lifts
as load bars). **No Power › Load segment** — the unopened Exertion segment is the precedent;
Power keeps its current four segments.

---

## 7. LogView v2 — confirm-or-adjust

The v2 spec ruled the active-hunt flow out of scope. It is the first thing v3 ships because
it changes Saturday behavior with no new tables, and because a prescription is worthless if
confirming it costs more taps than typing from scratch. Split into **2a** (no plan
dependency) and **2b** (prescription pre-fill).

### 7.1 Entry (2a → 2b)

- **2a — Repeat last hunt** on the Hunt tab and the idle screen: copies the last session's
  exercises with its weights as ghost values. The only "template" in v3 until Campaign ships.
- **2b — BEGIN HUNT** on a day with a planned hunt opens **pre-populated**: exercises in
  template order, prescribed sets as ghost values, "last time" beside each row. "Start empty
  hunt" stays one tap away.

### 7.2 Set row (2a unless noted)

| Element | Today | v3 |
|---|---|---|
| Completion | derived from `weight>0 && reps>0` in five places (`LogView.swift:1193`, `:1319`, `LogViewModel.swift:58`, `:76`, `SupersetCard.swift:19`) | stored `isCompleted`; ✓ button on the row. Tapping ✓ on an empty row **accepts the ghost values** — one tap logs a set |
| Last time | none | grey column `225×5` from `GET /exercises/{id}/last-performance` (new; last session's sets, best e1RM, days ago) |
| Target (2b) | none | ghost weight/reps from the prescription; `↑+5` chip when the rule moved the weight |
| Live feedback | none | e1RM of the entered set vs the family's best; gold when it would be a PR, purple when it clears an open Gate |
| Unit | hardcoded `lb` (`LogView.swift:1423`, `LogViewModel.swift:214`) | honors `preferred_unit` (after §12.3) |
| Warm-up | none; screenshot import drops warm-ups (`ScreenshotProcessingViewModel.swift:145`) and has no column to persist them | "Add warm-ups" generates 40/60/80% rows marked `is_warmup` (new column; excluded from PRs/volume) |
| RIR | hardcoded nil at `LogViewModel.swift:217` though `SetCreate` carries it on both sides | send the entered value; no contract change |

Plate calculator: **v3.1**.

### 7.3 Rest timer v2

Replaces `QuestTimerCard` (`LogView.swift:973-1141`): per-exercise default countdown (main
180 s, secondary 120 s, accessory 90 s, editable), starts on ✓ not on keystroke, lives in a
**sticky bottom bar**, haptic at 10 s and 0, local notification at zero when backgrounded
(`NotificationManager` already schedules locals). Live Activity for the same state: Phase 5.

### 7.4 Draft persistence

An `ActiveHuntStore` mirroring `PendingWorkoutStore` (`PendingWorkoutStore.swift:91-135`)
saves the in-progress session on every mutation. Reopening within 12 hours shows RESUME HUNT
on Status and the idle screen. Swipe-back on an active hunt asks before discarding (today
only the X button does, `LogView.swift:278-288`).

### 7.5 Save

- Sticky FINISH bar; `canSave` no longer blocks on blank trailing sets (dropped with a
  toast).
- One celebration screen stacking PR(s) → Gate clear → XP → rank, single CONTINUE (today:
  up to three sequential full-screen covers, `LogView.swift:142-221`).
- **Contract (net new only — the audit found most of it already exists):**
  `WorkoutCreate.duration_seconds` (the column and response exist, `models/workout.py:85`,
  the create schema doesn't), `WorkoutCreate.planned_hunt_id` (2b), `Set.is_bodyweight`,
  `Set.is_warmup` (new columns + `SetCreate` fields). Per-set completion time reuses the
  existing `Set.end_time`. `rir` is a one-line iOS fix.
- Post-save edit: date, notes, RPE, and sets editable from the detail view (today only the
  name is, `QuestDetailView.swift:102-130`); `PUT /workouts/{id}` exists.

### 7.6 Picker

Recents (30 days, most-frequent first), favorites, multi-select, muscle filter; clear
filters on dismiss (`LogView.swift:1628-1634` leaks state). Swapping inside a prescribed hunt
(2b) offers the item's `alternatives` first, then same-family, then same-primary-muscle.

### 7.7 Small fixes folded in

Locale-safe number parsing (`Double(weightText)`, `LogViewModel.swift:343`); next-field
keyboard affordance; exercise reorder; swipe-to-delete set; enqueue offline on 5xx too, not
only `networkError` (`LogViewModel.swift:245-251`).

### 7.8 Acceptance

No analytics SDK, no event table. Acceptance for 2a is a stopwatch: the owner logs a
prescribed-shape 5×5 session and the median set takes ≤ 5 s from ✓ to ✓. Recorded in the
roadmap when it passes.

---

## 8. The Coach

### 8.1 Division of labor (revised after red-team)

The first draft had the model proposing daily modulations and weekly ops that the engine
then clamped — two deciders for one number. Revised rule: **the engine generates every
number, every flag, and every candidate adjustment; the model ranks, explains, and
narrates.** Concretely:

| Surface | Engine | Model |
|---|---|---|
| Daily System line (Today's Hunt card) | rationale text with real numbers ("+5: last week 225×5×5 · Condition 71 BATTLE READY") | **not used in v3** — "System voice" rewrite of the same line is a v3.1 toggle |
| Weekly Debrief | adherence, highlights, concerns from flags, **candidate ops** from §5/§6 verdicts (progression holds/deloads, next week's miles vs plan, `deload_due`, `moved` patterns) | writes `summary` and `concerns[].text`, **ranks candidate ops to ≤ 3**, writes each op's `reason`; may add ops **only** from the typed vocabulary, subject to the same validators |
| Ask the System (v3.1) | context | bounded Q&A over the athlete context; any op it proposes goes through the same accept flow |

This halves the LLM surface, keeps hallucinated numbers off the daily card, and still
delivers the thing the Cowork job was built for: a Sunday read of the week that connects
sleep, mileage, and the squat stall in two sentences.

### 8.2 Athlete context builder

`app/services/coach_context_service.py` composes existing functions — the backend audit
confirmed most of it is callable without new SQL:

| Section | Source | Budget |
|---|---|---|
| Campaign, arc, week-in-arc, next 7 planned hunts with prescriptions and status | §4 | ~600 tokens |
| Last 4 weeks of sessions: lifts with sets, runs with miles/pace/avg HR, weekly `run_miles` | `api/calendar.py:49` (`weeks=4`) | ~3,000 |
| Per-family weekly-best e1RM series (12 wks), slope, projection | `trend_service.py:22`, `:52`, `:76` | ~400 |
| Condition today + inputs, muscles cooling | `condition_service.py:155` | ~250 |
| Load: 28-day daily series, run ACWR, flags | §6.2 | ~500 |
| Sleep / HRV / RHR / recovery 14-day series | **new** `daily_activity_series()` | ~400 |
| Goals + pace, PRs in window, open/cleared gates | `goal_service.py:287`, `weekly_report_service.py:162`, `gate_service.py:365` | ~300 |
| Candidate ops (engine) + last debrief's decisions | §8.4, `coach_outputs` | ~400 |
| Profile: age, sex, bodyweight trend, injury notes (new free-text profile field) | `UserProfile` + bodyweight | ~150 |

≈ 6–8K tokens. Serialized with fixed key order and precision so identical weeks hash
identically (`context_hash`).

### 8.3 Daily System line

Engine-generated, rendered inside the TODAY'S HUNT card in the mono/bracket dialect the v2
Directive used. Content = the prescription rationale + the highest-priority flag, with
numbers. Tap → the planned hunt sheet (the "why" is the rationale itself). The
`user_directives` table and rules engine retire in Phase 4; the rules' useful *flags*
(streak lapse, per-lift volume gap, lift lag with a calendar-week window) move into the
context builder and the Debrief's concerns.

### 8.4 Weekly Debrief

- **When:** generated lazily on the first fetch after Sunday 20:00 local (or on demand from
  the This Week card any time after Saturday's hunt is logged). Push arrives only once §9.2
  exists.
- **Engine step** (`debrief_service.build_candidates`): adherence counts; highlights from
  PRs, gate clears, `week completed as planned`; concerns from §6 flags, `deload_lift`
  verdicts, Condition < 65 streaks, sleep < 6 h ≥ 3 nights; **candidate ops** with their
  numeric justification.
- **Model step:** `client.beta.messages.parse(...)` with the schema below; the candidate ops
  are in the context; the model returns them ranked with reasons, possibly fewer, possibly
  plus additional typed ops.
- **Output contract:**

```json
{
  "summary": "≤ 4 sentences: what happened vs plan, the one thing that mattered",
  "concerns":   [{"flag": "ramp_high|run_acwr_high|sleep_low|lift_stall|…", "text": "…"}],
  "adjustments": [
    {"op": "set_progression", "family": "back_squat", "increment_lb": 5, "reason": "…",
     "confidence": "high|medium|low", "source": "engine|model"},
    {"op": "set_week_miles", "week_start": "2026-09-07", "miles": 12.5, "reason": "…"},
    {"op": "deload_now", "scope": "lifts|runs|all", "reason": "…"},
    {"op": "swap_days", "a": "2026-09-09", "b": "2026-09-10", "reason": "…"},
    {"op": "extend_arc", "weeks": 1, "reason": "…"},
    {"op": "change_reps", "family": "bench_press", "sets": 3, "reps": [3,3], "reason": "…"}
  ],
  "next_week_focus": "one line"
}
```

- **Validators** (deterministic appliers in `campaign_service`): miles within ±15% of the
  arc's ramp value unless `deload_now`; increments equal to the family's increment; at most
  one `deload_now` per 3 weeks; `extend_arc ≤ 2`; ≤ 3 adjustments; every family named must
  exist in the context. Out-of-bounds ops render as "suggested, out of bounds" — visible,
  not applied. Adherence, highlights, and all numbers come from the engine step, not the
  model output.
- **UI:** `WeeklyReportView` becomes the **Debrief sheet**: summary, adherence ring,
  highlights, concerns, adjustments as ACCEPT / DISMISS cards. Accepting rewrites next
  week's `planned_hunts`. The goal-pace section stays below. The static
  `_generate_suggestions` prose is deleted.
- **Fallback:** on refusal, timeout, or schema failure the sheet shows the engine step
  alone (summary = adherence + top concern). The app never shows an empty debrief.

### 8.5 Storage

```
coach_outputs   id, user_id, kind(debrief|answer), for_date, context_hash, prompt_version,
                model, output JSON, validated JSON, decisions JSON, created_at
```

Token counts are logged, not stored. "Why did it say that" = the stored context hash plus
the candidate-ops snapshot inside `validated`.

### 8.6 Model, SDK, cost

- **Model:** `claude-opus-5`, adaptive thinking (default), `output_config.effort: "high"`,
  structured output via `client.beta.messages.parse(...)` (beta namespace is required
  because the call also passes `betas` for `fallbacks: "default"` with
  `server-side-fallback-2026-07-01`, so a policy decline on injury-adjacent text re-runs
  instead of blanking the sheet). Explicit `timeout` (60 s) and `max_retries=1`; one
  try/except per user so one failure never aborts a batch. The screenshot extractor stays
  on `claude-sonnet-5`.
- **SDK pin:** `requirements.txt:22` is `anthropic>=0.49.0` (floating); the local venv has
  0.111.0, which has `beta.messages.parse`; PyPI's 1.x line is a breaking rewrite. **Pin
  `anthropic==0.111.0`** in Phase 0 and treat the 1.x upgrade as its own task.
- **Caching:** frozen system prompt + schema first with `cache_control`; volatile context
  after.
- **Cost, one user:** one debrief/week ≈ 10K input + 1.5K output ≈ $0.09 → **≈ $0.40/month**.
  The v3.1 daily line would add ≈ $0.10/week. Cost is not a design constraint.

### 8.7 Prompt principles

Voice: the System — terse, declarative, numbers over adjectives, no exclamation marks. Cite
the context (validator rejects unknown families). Prefer one change over three. Never
argue with a flag. Prompt versioned in `app/coach/prompts/` with a replay test over three
stored contexts. Budget a tone-tuning pass over 10 stored contexts before enabling any push.

---

## 9. Plumbing

### 9.1 Background ingestion (iOS)

`HKObserverQuery` + `enableBackgroundDelivery` for workouts (immediate), sleep, HRV, and
resting HR (hourly). The observer's handler runs the existing
`HealthKitManager.importNewWorkouts` / `syncTodayOnly` and calls the completion handler.
`UIBackgroundModes` already declares `fetch` and `processing`; this finally uses them.
Success: a run recorded on the watch is visible in Hunt within 15 minutes with the phone in
a pocket. Foreground sync stays as the backstop; iOS throttles background delivery.

### 9.2 Scheduler — deferred until pushes need it

Everything in v3 generates lazily and idempotently on fetch (§4.4, §8.4, gate evaluation
as today). A scheduler is needed only for content that must exist *before* the user opens
the app: a `weekly_report_ready` push with a real debrief behind it, `gate_opened` pushes
that don't wait for a Status open, and the v3.1 daily line. When that time comes:

- A second Railway service in the same project **with its own config file** —
  `backend/railway.cron.toml` — because a cron service that inherits `backend/railway.toml`
  would run `alembic upgrade head && uvicorn …` (never exits, so every hourly run is skipped
  as "still running"), fail the `/` healthcheck, and run migrations:

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python -m app.jobs.hourly"
cronSchedule = "0 * * * *"
restartPolicyType = "never"
```

- Reference `DATABASE_URL`, `ANTHROPIC_API_KEY`, `SENTRY_DSN` from the web service; the job
  calls `sentry_sdk.init` itself (`main.py:40` only initializes it for the FastAPI app); the
  whole pass must finish under 60 minutes (Railway skips overlapping runs); tasks are
  idempotent per `(user, local_day, task)` and log to a `job_runs` table.

### 9.3 Notifications

| Type | Kind | v3 |
|---|---|---|
| `rest_timer_done` | local | new (§7.3) |
| `weekly_report_ready` | push | exists, fires from `api/weekly_report.py:53` on GET today; moves to the job when §9.2 lands |
| `gate_opened` | push | exists; unchanged |
| `hunt_briefing` | push | **v3.1**, off by default, training days only, payload = planned hunt title + top set (engine text, no LLM at push time) |
| `overreach_warning` | — | **not built** — flags surface on the Today card and in the Debrief |
| `streak_at_risk` | local | **retired**; plan adherence replaces streak semantics (§13) |

Net: no new push types in v3. The v2 §11 no-nag stance holds.

### 9.4 Widgets and Live Activity (Phase 5, optional)

Lock-screen widget: Today's Hunt + Condition score, from a cached JSON the app writes.
Live Activity during an active hunt: current exercise, next prescribed set, rest countdown.
Ship only if the Today card and the timer bar are being used daily.

---

## 10. Gates v2 (ships in the first session, with LogView 2a)

Four contained changes in `gate_service.py` / `trend_service.py`:

1. **Baseline = campaign best** — best e1RM on the family since the campaign `start_date`
   (before Campaign exists: last 12 weeks). `_candidate_lifts` (`gate_service.py:169-215`)
   takes `func.max(Set.e1rm)` all-time today; adding a `since` filter is contained. Lifetime
   PRs stay lifetime PRs in Records.
2. **Split `SLOPE_WINDOW_WEEKS`** (`trend_service.py:19`, used as both the minimum-points
   gate at `:59` and the fit window at `:61`) into `MIN_WEEKLY_POINTS = 4` and a 6-point fit
   window. Weekly points come from the family (a Saturday squat and a Sunday front squat both
   feed `back_squat`; still one point per week).
3. **Spawn onto the plan** (after Campaign ships): a spawned gate targets the *next planned
   hunt* containing that family; window = that hunt + 7 days. Readiness is checked at fetch
   time on the day: STRAINED defers the attempt one hunt.
4. **Gate attempt is set 1 after warm-ups**, and that day's working sets become −10%
   back-offs. A PR attempt after 5×5 squat and 4×5 deadlift is a bad prescription.
5. **Clear feedback:** `gate_cleared` in the workout-create response (v2 QA W5/W8), one
   celebration screen (§7.5), Hunt Log sigil as today.

Expected effect for a Sat/Sun 5×5 lifter: first gate within 4–5 weeks of consistent logging.

---

## 11. Cut list and retirements

| Item | Action | Why |
|---|---|---|
| `training-calendar/` PWA | Retire one release after §4.6 ships; gh-pages read-only for 30 days, then remove the workflow | one plan, one place |
| `Fitness Coach/` Cowork job + `weekly-export` skill + `Workout Exports/` | Delete the scheduled task and the skill; archive the folder | 7 failed runs; replaced by §8.4 |
| `user_directives` + `directive_service` rule engine | Retire in Phase 4; first move `calculate_todays_workout_stats` and `user_has_wearable` out of `quest_service.py` (`directive_service.py:31` imports from it) into a neutral module | replaced by the engine line + Debrief concerns |
| `weekly_report_service._generate_suggestions` | Delete in Phase 4 | replaced by Debrief |
| `quest_definitions` / `user_quests` tables | Drop (idempotent `IF EXISTS`) in Phase 4 after the helper move above and the `app/models/__init__.py` registration is removed | dead weight |
| `exercise_equivalence.py` + the substring canonicalizers | Replace with `family_id` reads, per consumer, as each phase touches it | audit item 2 |
| Power › Exertion segment | Leave as is; no Power › Load segment is built | unopened; Load lives on Status |
| `streak_at_risk` + streak XP | Retire in Phase 2 when plan-adherence XP ships | HealthKit runs never sustain streaks (no `award_xp` in the import path) |
| Scan-credit paywall for the owner | One-time `has_unlimited = true` for the owner via an admin script; IAP code stays | the owner should not be paywalled out of his own scanner |
| Plate calculator, briefing-history sheet, second campaign template, `set_logged` instrumentation, `overreach_warning` push, daily LLM line | **v3.1 or never** | overbuilt for N=1 |
| Friends UI | No change | already demoted |

---

## 12. Foundations (split 0a / 0b after the engineering review)

**0a — write-side, one session, no behavior change:**

1. **`user_profiles.timezone`** (IANA string). Nothing persists an offset today:
   `client_date` is a date, `tz_offset_minutes` is a query param on `api/calendar.py:52`
   and never stored. Owner default via admin script; iOS sends it on create/sync/import.
2. **`WorkoutSession.local_day`** (Date) populated at every ingest path from the profile
   timezone. Manual creates and screenshot-dated rows already carry a local date
   (`schemas/workout.py:117` → naive local midnight, used by `api/workouts.py:280`,
   `api/sync.py:159`, `screenshot_service.py:814`); HealthKit stores a true UTC instant
   (`healthkit_service.py:98`); the screenshot fallback is `datetime.now(utc)`
   (`screenshot_service.py:816-818`). Backfill: `.date()` for manual/screenshot-dated rows,
   `zoneinfo` conversion for HealthKit and fallback rows. **`date` stays the instant** —
   WHOOP overlap matching depends on it; only bucketing moves.
3. **`Set.weight_lb`** written at ingest and used for e1RM at `workouts.py:337`. No kg rows
   exist today (iOS hardcodes lb at `LogViewModel.swift:214`, screenshot at
   `screenshot_service.py:900`, `:1151`), so the backfill is one line. The 29 `.weight` read
   sites across 8 files switch to `weight_lb` in 0b.
4. **`Set.is_bodyweight`, `Set.is_warmup`, `WorkoutCreate.duration_seconds`** (§7.5).
5. **`exercise_families` + `exercises.family_id`** backfilled from `canonical_id` via a
   committed dict; no consumers switched yet.
6. **Pin `anthropic==0.111.0`.**
7. **Owner unlimited scans** admin script.
8. **Plateau insight:** `api/analytics.py:690` counts e1RM points per exercise with `> 8`
   and no explicit 28-day cap; reword to `≥ 5` distinct `local_day`s in 28 days.

**0b — read-side switches, done inside the phase that first needs each:**

- Weekly bucketing to `local_day`: `trend_service`, `gate_service`, `condition_service`,
  `weekly_report_service`, `api/calendar` (drop the uniform offset subtraction at
  `api/calendar.py:94`), `api/analytics` — required by Phase 3 (Load's daily series).
- `.weight` → `weight_lb` reads — Phase 3 (tonnage) and Phase 2b (rounding with units).
- `family_id` consumers: `xp_service` BIG_THREE (Phase 1, gates), `pr_detection` grouping
  (Phase 1), `analytics` keyword map + `cooldown_service` fuzzy map (Phase 3), then delete
  the substring schemes and `exercise_equivalence.py`.

**Independent iOS item:** HealthKit background delivery (§9.1) — half a session, any time.

---

## 13. XP economy delta

| Source | v2 | v3 |
|---|---|---|
| Directive followed | +40/day | **0 — retired** (Phase 4) |
| **Hunt completed as planned** (`done`) | — | **+40**; `modified` / `moved` +25; free-form hunt still earns the base 50 |
| **Week completed as planned** (no `skipped`) | — | **+150** (replaces the 7-day streak bonus) |
| Gate clear | C 300 / B 500 / A 800 / S 1200 | unchanged |
| Guard respected (a run was cut and the logged run was ≤ the cut distance) | — | **+30** — the game rewards restraint |
| Everything else | unchanged | unchanged |

New achievements: `campaign_arc_complete`, `four_weeks_on_plan`, `guard_respected_10`,
`first_debrief_accepted`. Pacing stays within the v2 envelope.

---

## 14. Screens (delta only)

- **Status:** header → Condition → **TODAY'S HUNT** (with System line) → **LOAD strip** →
  Gate card(s) → This Week (adherence ring; "Debrief →") → Power snapshot. Six sections.
- **Hunt:** week strip with plan overlay + pace strip; BEGIN HUNT / REPEAT LAST / SCAN;
  calendar and log as today; planned-hunt sheet for future days; RESUME HUNT banner.
- **Active hunt (LogView v2):** §7.
- **Power:** unchanged.
- **Hunter:** Campaign row (name, arc, week; edit/pause/import), Coach settings (HR cap
  override, debrief time), Integrations gains a background-delivery status line.
- **Sheets:** Planned Hunt, Debrief (replaces Weekly Report), Load.

Design language unchanged. Mockup before Phase 1b per the house rule
(`docs/mockups/arise-v3-mockup.html`): Today's Hunt, LogView v2 set row + timer bar,
Debrief sheet, Hunt week strip.

---

## 15. Contract registry (backend ↔ iOS mirrors that trigger `/evaluate`)

Routers mount without `/api`. Snake_case JSON; explicit `CodingKeys` in `APITypes.swift`.

### 15.1 `GET /exercises/{id}/last-performance` → `LastPerformanceResponse` (Phase 1)

`exercise_id`, `family_id`, `date` (local), `days_ago`, `sets [{weight_lb, reps, rpe,
is_warmup}]`, `best_e1rm`, `best_e1rm_date`.

### 15.2 Workout create additions (`POST /workouts`, `/sync`) (Phase 1)

Request: `duration_seconds?`, `planned_hunt_id?` (Phase 2b), per set `is_bodyweight`,
`is_warmup`, `end_time?` (existing field, now sent on ✓). Response adds `gate_cleared?` and
`planned_hunt_status?` (2b).

### 15.3 `GET /hunts/today` → `PlannedHuntResponse?` (Phase 2)

| JSON | Type | Null? |
|---|---|---|
| `id`, `campaign_id`, `arc_id`, `template_id` | string | no |
| `date` | `YYYY-MM-DD` | no |
| `type` | `lift \| run \| light \| rest` | no |
| `title`, `location_tag` | string | tag yes |
| `status` | `planned \| done \| modified \| skipped \| moved` | no |
| `session_id`, `moved_to` | string | yes |
| `prescription` | `PrescriptionResponse` | yes (rest) |
| `rationale` | `[{key, text, numbers}]` | no, may be empty |
| `system_line` | string (engine, §8.3) | no |
| `modulation` | `{band, factor, note}` | yes |
| `guard_flags` | `[string]` | no |

`PrescriptionResponse`: `version`; `exercises[] {family_id, exercise_id, exercise_name,
role ∈ main|secondary|accessory|gate|warmup, alternatives [exercise_id], sets [{set_number,
target_weight_lb?, target_reps_lo, target_reps_hi, target_rpe?, is_warmup, is_gate_attempt}],
last_performance?, progression_note?}`; `run? {kind ∈ easy|long|shakeout, miles, hr_cap_bpm,
note}`; `notes [string]`.

### 15.4 `GET /load` → `TrainingLoadResponse` (Phase 3)

`as_of`, `run_acute_7d`, `run_chronic_28d`, `run_acwr?` (null before 28 days), `band`,
`miles_7d`, `miles_plan_7d`, `longest_run_7d`, `flags [string]`, `series [{local_day,
run_load, lift_load, total_load, miles, run_acwr?}]` (28 days).

### 15.5 `GET /coach/debrief?week_start=` → `DebriefResponse` (Phase 4)

`id`, `week_start`, `summary`, `adherence {planned, done, modified, moved, skipped}`,
`highlights [{kind, text}]`, `concerns [{flag, text}]`, `adjustments [{id, op, params, reason,
confidence, source, status ∈ proposed|accepted|dismissed|out_of_bounds}]`, `next_week_focus`,
`goal_reports` (existing shape), `generated_at`, `source ∈ model|engine_fallback`.
`POST /coach/debrief/{id}/adjustments/{adj_id}` with `{decision: accept|dismiss}`.

---

## 16. Build phases (reordered after red-team: daily win first)

Each phase ends with the v2 ship criteria (pytest + ruff, sim build + entitlements lint,
contract-mirror `/evaluate` against the Pydantic schemas, pathspec commit, verified Railway
SUCCESS, Xcode rebuild reminder). Sessions are the unit v2 used.

| Phase | Scope | Sessions | Ship signal |
|---|---|---|---|
| **1 — Log fast + Gates fire** | §7 items marked 2a (last time, ghost from last session, ✓ + countdown bar, drafts, save compression, repeat last hunt, picker); §15.1–15.2; §10 items 1, 2, 4, 5 (campaign-best → last-12-weeks baseline for now); §12 items 3, 4, 6, 7 | 1 | ≤ 5 s per set on a stopwatch; a gate spawns for at least one big-three lift within 4 weeks |
| **2 — Plan + Prescribe** | §12 items 1, 2, 5, 8 (0a); §4 tables, import of `data.js`, lazy materialization, linking; §5 engine (linear/double, runs vs arc ramp); Today's Hunt card + Hunt week strip + pace strip; LogView 2b pre-fill; §13 adherence XP, retire streak; §10 item 3 | 2 | the PWA can be deleted from the home screen and nothing is lost; a prescribed hunt logs with ghost-accept taps only |
| **3 — Load + Guard + Condition v2** | 0b `local_day` and `weight_lb` read switches; §6 service, table, rules, guard; Load strip + sheet; Condition v2; TRIMP into cooldowns; HealthKit background delivery (§9.1, parallel iOS item) | 1–2 | ACWR shows `null` until day 28 then a number; a run appears in Hunt without opening the app |
| **4 — The Coach** | §8 context builder, engine candidates, model debrief, validators, Debrief sheet + accept flow; retire Directive tables, static suggestions, the Cowork job and skill (§11) | 2 | first debrief with an accepted adjustment; fallback path exercised once by forcing a schema failure |
| **5 — Optional delight** | §9.2 scheduler + `weekly_report_ready` from the job; widgets/Live Activity; Ask the System; v3.1 daily line; plate calc; PWA workflow removal | 1–2 | only what is used daily |

Total: **7–9 sessions**, with a behavior change after the first one. Phase 1 has no schema
dependency beyond the three set columns; Phase 2 depends on 1 (ghost plumbing); 3 on 2
(planned week miles); 4 on 2–3; 5 on 4.

---

## 17. Success metrics

| Job | Metric | Baseline | Target |
|---|---|---|---|
| J2 | seconds per set on a prescribed-shape 5×5 (stopwatch, median) | est. 15–25 s | ≤ 5 s |
| J2 | lift sessions logged in-app on the day | unknown | ≥ 90% (visible once `local_day` exists) |
| J3 | gates spawned per big-three lift per arc; cleared per arc | 0 since 2026-07-12 | ≥ 1 spawned per lift; ≥ 1 cleared |
| J1/J5 | planned-hunt adherence (`done + modified + moved`) / planned | — | ≥ 80% per arc |
| J4 | weeks with an unresolved `run_acwr_critical` or `ramp_high` | not measured | 0 after day 28 |
| J5 | debriefs with ≥ 1 accepted adjustment | 0 | ≥ 75% of weeks |
| J7 | minutes from watch save to session visible in Hunt, phone in pocket | until next app open | ≤ 15 |
| Trust | debriefs served from `engine_fallback` | — | ≤ 5% |

---

## 18. Risks and open questions

1. **Prod usage is unverified.** This session's read-only prod snapshot was blocked by the
   permission classifier; the JTBD "served" estimates are inferred from code and docs.
   `backend/scripts/usage_snapshot.py` (committed, read-only) prints sessions/week split
   lift vs run, logged lift names (the family backfill depends on them), directive type
   distribution, gate history, and daily-activity coverage. Run it before Phase 2.
2. **Which plan is the plan.** PWA plan (Sat squat / Sun bench, 5×5) is the default
   import; the Cowork Week 1 plan is not. Confirm before Phase 2.
3. **Guard thresholds are literature defaults** (1.20× plan, 1.3/1.5 ACWR, 40% long-run
   share above 15 mi/wk, 28-day cold start). They live in one module; a
   `set_guard_threshold` op is a reasonable v3.1 addition once the Debrief has data.
4. **`local_day` backfill** rewrites the axis every chart uses. Verify on a prod copy;
   HealthKit rows are the ones that move.
5. **SDK line.** Pinning 0.111.0 defers the 1.x upgrade (httpx2, breaking); do it as its
   own task with the migration guide, not inside Phase 4.
6. **Scheduler config collision** (§9.2) is a real deploy risk when Phase 5 arrives; the
   separate config file is not optional.
7. **Tone.** A Sunday summary in the System's voice can read cheesy or clinical; the
   10-context tuning pass in §8.7 is the mitigation, and the engine fallback is the floor.
8. **N=1 by design.** Everything is per-user, but the template, import format, and prompt
   are tuned for one athlete. Stated so a later launch decision doesn't inherit it by
   accident.

---

## 19. Revision log

- **v1 (2026-09-04, morning):** initial draft from the two audits.
- **v2 (2026-09-04, after two independent red-team passes):**
  - Product/athlete review: guard rules restated against the plan's ramp (ramp-vs-last-week
    fired after every deload; 35% long-run cap cut the plan's own long run); ACWR made
    run-only with a 28-day cold start and lifts removed from the veto path; progression
    verdicts keyed on reps with RPE optional; readiness modulation moved to fetch time;
    gate attempt moved to set 1; import gained `alternatives` and note rows; linking gained
    the ±2-day `moved` rule; e1RM-derived starts ignore >8-rep sets and use 0.90; LLM scope
    cut to the Sunday debrief with engine-generated candidate ops; daily LLM line, Power ›
    Load segment, plate calc, instrumentation, overreach push, and second template cut or
    deferred; phases reordered so the first session changes daily behavior.
  - Engineering review: cron service gets its own `railway.cron.toml` (inheriting the web
    config would loop forever and run migrations) and is deferred behind lazy generation;
    `local_day` needs a stored profile timezone and keeps `date` as the instant; Phase 0
    split into write-side 0a and per-phase 0b; quest-table drop sequenced after moving the
    helpers `directive_service` imports; `SLOPE_WINDOW_WEEKS` split rather than a
    non-existent `MIN_WEEKLY_POINTS` edited; SDK pinned; contract additions reduced to the
    fields that don't already exist (`rir`, `end_time`, `duration_seconds` on the model all
    exist); four wrong anchors corrected.

*Companion docs to be written: `docs/arise-v3-roadmap.md` after Phase 1;
`docs/mockups/arise-v3-mockup.html` before Phase 2.*
