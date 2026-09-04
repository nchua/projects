# ARISE v3 — The System Coaches

> **Status:** Draft for review. Written 2026-09-04 from a first-principles review of the
> shipped v2/v2.1 product, the `training-calendar` PWA, the `Fitness Coach` Cowork job, and
> two code audits (iOS logging flow; backend intelligence primitives). Code anchors were
> verified against the working tree on 2026-09-04 — re-verify `file:line` before each build
> phase, they drift.
>
> **What this is:** the product definition for the next step-change. It keeps the v2 thesis
> ("every gamified element derives from real data") and closes the loop the v2 spec left
> open: the app records and grades, but it does not **plan, prescribe, or adapt**. v3 makes
> the System a coach.
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
| Apple Watch / WHOOP → HealthKit → app | HR, runs, sleep, HRV, RHR, recovery | foreground-only sync; runs lag until the app is opened; HRV is stored and never read |

**v3 collapses these into one loop inside the app: Plan → Prescribe → Log → Adapt.**

1. **Campaign** — the program becomes a first-class object (arcs, weeks, hunt templates,
   progression rules). The PWA's `data.js` is imported once and the PWA is retired.
2. **Prescription** — every planned hunt is materialized with real loads (weight × reps ×
   RPE, or miles × effort) from the user's own e1RM, last session, and readiness.
3. **LogView v2** — logging becomes confirm-or-adjust: prescribed sets pre-filled, "last
   time" beside every row, an explicit ✓ that starts a countdown rest timer, drafts that
   survive an app kill. Target: **≤ 5 seconds per set** on a prescribed hunt.
4. **Load + Overreach Guard** — one training-load currency across running and lifting,
   acute:chronic ratio, mileage ramp and long-run share rules. Feeds Condition v2 and
   vetoes prescriptions. This is the injury guard the PWA hand-rolled, done properly.
5. **The Coach** — a server-side Claude coach with a structured athlete context: a
   3-sentence **Hunt Briefing** every training morning, and a Sunday **Weekly Debrief** that
   proposes typed plan adjustments the user accepts with a tap. Deterministic validators
   bound everything the model proposes. Replaces the Directive's voice, the weekly report's
   template suggestions, and the Cowork job.
6. **Gates v2** — the north-star feature gets a fair chance to fire: baseline = campaign
   best not lifetime best, 4 weekly points not 6, spawn onto the next planned heavy day,
   and the clear celebration that was deferred in v2.

Plus the plumbing that makes a coach trustworthy: background HealthKit delivery, a nightly
job, one exercise-canonicalization scheme, honest `weight_unit` math, and a `local_day` on
every session.

---

## 1. Jobs to be done

Written for the actual user: a hybrid athlete who lifts heavy Saturday/Sunday at a full gym,
trains light at an apartment gym on WFH days, runs three days a week on a 6-month mileage
ramp, wears an Apple Watch and a WHOOP, was injured in 2024 by ramping mileage too fast, and
cares most about PRs on the big lifts (roadmap §1: "North star: Strength PRs").

| # | Job | How it's served today | Evidence | Served |
|---|---|---|---|---|
| J1 | **Tell me what to do today** — the session, the loads, push or back off | Directive (one line, rules engine); the PWA (static plan, no loads); the Coach job (never ran) | Rules 4 (BREAK_PLATEAU) and 5 (FREQUENCY) are structurally dead for a 2-lift-day/week user (`analytics.py:690` needs >8 sessions per lift per 28 days; `analytics.py:701` counts imported runs as sessions). Rule 7 (LIFT_LAG) fires spuriously every Saturday because the rolling 7-day window holds only last Sunday (`directive_service.py:48-62`, `:397`). Rule 1 (REST) needs a WHOOP score. The user sees MAINTAIN most days (v2.1 interview: "Directive is too vague") | ~20% |
| J2 | **Let me log it fast, without thinking** | Manual entry from blank rows; screenshot scan behind a credit paywall; HealthKit import for runs | No "last time" anywhere in the logger (`LogViewModel.swift:93-102` creates one blank set; `getExerciseTrend` never called from Log). Set completion is derived from `weight>0 && reps>0` in five places, so the rest timer fires while typing "1" of "12" (`LogView.swift:1108-1115`). Timer is global count-up, off-screen by exercise 3. No templates, no routines, no repeat-last-workout. Draft dies on swipe-back or app kill. Session duration measured then discarded (`LogViewModel.swift:232`); bodyweight flag dropped at save (`APITypes.swift:191-204`) | runs ~70%, lifts ~30% |
| J3 | **Show me I'm getting stronger and when I'm ready to PR** | e1RM charts, percentiles, PR detection, Gates | Charts are good. Gates need 6 unbroken Monday-keyed weekly points per lift (`trend_service.py:19`) and a projection 1% past the **all-time** best (`gate_service.py:274`) — a 5×5 trajectory cannot beat an old heavy single; Sat+Sun sessions collapse to one weekly point. No gate has spawned since Phase 2 shipped (2026-07-12). The payoff loop has been empty for the entire v2 era | ~55% |
| J4 | **Keep me from getting hurt while I ramp mileage and lift heavy** | Muscle cooldowns, Condition, the PWA's "AHEAD — EASE UP" | No acute:chronic ratio, ramp rate, or long-run share anywhere in the backend (`grep acute|chronic|acwr|ramp` → nothing). Cardio fatigue is duration-only and capped at 5 effective sets, so a 15-mile long run costs the same recovery as a 75-minute jog (`cooldown_service.py:122-123`). Condition's strain input is yesterday-only | ~25% |
| J5 | **Review my week and adjust the plan** | Weekly report (goal pace only, five static template suggestions at `weekly_report_service.py:354`); the Cowork job | The weekly report has no plan to compare against. The Cowork job was the user's attempt to bolt a real coach on from outside and it never produced a review | ~10% |
| J6 | **Make training feel like a game I want to open** | XP, rank, achievements, celebrations, Condition gauge | The parts tied to real signal land. The daily hook (Directive) and the boss fight (Gate) are the weak links because they rarely say anything true or new | ~60% |
| J7 | **Get my wearable data in without effort** | HealthKit foreground sync, WHOOP OAuth sync, screenshot fallback | All sync is foreground-triggered (`SyncCoordinator.swift:23`; no `HKObserverQuery`/`enableBackgroundDelivery` anywhere despite `UIBackgroundModes` declaring fetch/processing). The PWA README apologizes for the lag. HRV is written (`whoop_service.py:606`) and never read | ~60% |

**The pattern:** J1, J4, J5 are the coach's jobs, and they are the least served. J2 is the
daily friction that determines whether the data the coach needs exists at all. J3's payoff
mechanic exists but is miscalibrated. v3 orders work accordingly: fix the logging friction
and the data foundations first (they gate everything), then plan + prescribe, then load,
then the coach, then delight.

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
                     ┌──────────────── nightly job ────────────────┐
                     │ load recompute · ACWR · gate spawn ·        │
                     │ materialize tomorrow's hunt · write briefing│
                     └──────────────────────┬──────────────────────┘
                                            ▼
 morning push (training days only) → Status: TODAY'S HUNT card + Briefing
                                            ▼
                     BEGIN HUNT (pre-filled from prescription)
                                            ▼
                     confirm-or-adjust each set · ✓ → rest countdown
                                            ▼
                     save → one celebration (PR · Gate · XP)
                                            ▼
                     planned_hunt marked done · load updated · next hunt re-prescribed
                                            ▼
 Sunday evening → WEEKLY DEBRIEF (Coach) → typed adjustments → user accepts → next week rewritten
```

Every arrow is a real data path. The Coach only ever writes *proposals*; the deterministic
engine validates them and the user accepts them.

---

## 3. Design pillars (v2's, plus two)

1. **The System knows you.** (v2) Derived from real data or it doesn't ship.
2. **One visual language.** (v2) Minimal Void, finished.
3. **Strength is the story.** (v2)
4. **Fewer, denser surfaces.** (v2)
5. **The System prescribes, the Hunter decides.** New. Every prescription and every
   coach proposal shows its numbers and has a one-tap override. No silent changes to the plan.
6. **The model proposes, the engine disposes.** New. LLM output is structured, validated
   against hard bounds (ramp rate, ACWR, load caps, deload cadence), and stored with its
   context hash so "why did it say that" is always answerable.

---

## 4. Campaign — the program as a first-class object

### 4.1 Vocabulary

| Term | Meaning | Maps to |
|---|---|---|
| **Campaign** | A multi-month program with a goal | the PWA's whole `PHASES` array; "6-month hybrid: run base + strength" |
| **Arc** | A block inside a campaign with its own mileage band and emphasis | one PWA phase ("Months 1–2, 7–13 mi/wk, long run 4.5") |
| **Hunt template** | A weekday's session shape inside an arc | one PWA `days[]` entry ("Saturday — Squat Day, Heavy, 5×5 …") |
| **Planned hunt** | A template materialized onto a calendar date, with a prescription | new |
| **Prescription** | Concrete targets for a planned hunt: per exercise, sets × reps × weight × RPE; for runs, miles × effort | new (§5) |

The Hunt tab already calls workouts "hunts"; a planned hunt is the same noun before it
happens.

### 4.2 Data model

New tables (all keyed by `user_id`; idempotent migrations per the prod-stamp-drift rule):

```
campaigns            id, user_id, name, goal, start_date, status(active|paused|completed),
                     source(import|template|coach), created_at
campaign_arcs        id, campaign_id, index, name, weeks, run_miles_min, run_miles_max,
                     long_run_miles, deload_every_n_weeks (default 4), deload_factor (0.75),
                     notes
hunt_templates       id, arc_id, weekday(0-6), type(lift|run|light|rest), title,
                     location_tag, load_hint(0-100), items JSON  -- see below
planned_hunts        id, user_id, campaign_id, arc_id, template_id, date(local),
                     status(planned|done|modified|skipped|moved), session_id FK, moved_to,
                     prescription JSON, prescription_version, generated_at, rationale JSON
```

`hunt_templates.items` is the plan's *shape*, not its loads:

```json
[
  {"exercise_family": "back_squat", "sets": 5, "reps": [5,5], "role": "main",
   "progression": "linear", "increment_lb": 10, "rpe_cap": 8},
  {"exercise_family": "deadlift",   "sets": 4, "reps": [5,5], "role": "secondary",
   "progression": "linear", "increment_lb": 10, "rpe_cap": 8},
  {"exercise_family": "leg_press_or_lunge", "sets": 3, "reps": [10,12], "role": "accessory",
   "progression": "double", "increment_lb": 10},
  {"exercise_family": "hanging_leg_raise",  "sets": 3, "reps": [12,12], "role": "accessory",
   "progression": "double"}
]
```

For runs: `{"run": "easy", "miles": [2, 2.5]}` or `{"run": "long", "miles": "arc"}` (arc
ramp decides).

**`exercise_family`** is new and is the fix for the audit's finding that four
substring-matching schemes disagree (`xp_service.py:31`, `analytics.py:126`,
`cooldown_service.py:437`, `pr_detection.py:44`; `exercise_equivalence.py` is a fifth, with
no callers). One table, one truth:

```
exercise_families    id (slug), display_name, primary_muscle, is_big_three, standards_key
exercises            + family_id FK (backfilled by a one-time script from name/canonical_id)
```

`BIG_THREE`, the strength-standards lookup, PR canonical grouping, cooldown muscle mapping,
and the Directive's `_big_three_exercise_groups` all read `family_id`. The substring code
paths are deleted, not kept as fallbacks.

### 4.3 Import and templates

- **`POST /campaign/import`** accepts the PWA's `data.js` shape verbatim (phases → arcs,
  days → templates). One-time script `scripts/import_training_calendar.py` runs it for the
  owner. Sets × reps strings ("5×5", "3×10-12", "2–2.5 mi", "3 → 4.5 mi (build weekly)")
  are parsed into `items`; anything unparseable lands as a `note` and is flagged in the
  response so nothing is silently dropped.
- **`POST /campaign`** from a template picker with two seeds: the owner's hybrid plan and a
  generic 4-day upper/lower. That is the entire template library for v3 — no marketplace.
- Editing is in-app and coarse: move a hunt to another day, skip it, swap two templates,
  change an arc's mileage band. Fine-grained template editing stays a JSON edit in v3.

### 4.4 Materialization

`planned_hunts` are written 8 days ahead by the nightly job (§9.2) and on any campaign edit.
Materialization is idempotent per `(user_id, date)`. A planned hunt with `status=planned`
and a past date becomes `skipped` at the next nightly run; a session logged on a day with a
matching-type planned hunt links to it (`done`, or `modified` if the exercise set differs by
more than one family).

### 4.5 API

| Endpoint | Returns |
|---|---|
| `GET /campaign/current` | campaign + arcs + current arc index + week-in-arc + deload flag |
| `GET /hunts/today?client_date=` | today's `PlannedHuntResponse` (prescription included), or `null` on rest days |
| `GET /hunts/week?start=` | 7 planned hunts with status + linked session summaries — the Hunt tab week view and the PWA replacement |
| `PUT /hunts/{id}` | `{status: skipped}` · `{moved_to: date}` · `{swap_with: id}` |
| `POST /campaign/import`, `POST /campaign`, `PUT /campaign/{id}` | as above |

### 4.6 UI

- **Status tab:** the **TODAY'S HUNT** card replaces the Directive card's position (the
  Directive/Briefing line renders *inside* it, §8.3). Shows type, title, location tag, the
  main lift's prescribed top set ("Back Squat 5×5 @ 235"), or the run ("Easy 2.5 mi · HR ≤
  150"), Condition modulation if any, and BEGIN HUNT. Rest days show a quiet REST card with
  tomorrow's hunt.
- **Hunt tab:** the month calendar gains a **week strip** at the top: 7 day cells with
  planned type glyph, done/skipped state, and the pace strip the PWA had
  (`WK 5 · 4.8/9.6 MI · 2 LIFTS · ON PACE`). Tap a future day → planned hunt sheet with the
  prescription and move/skip. This is PWA parity; the PWA retires when it ships (§11).

---

## 5. Prescription engine (deterministic)

`app/services/prescription_service.py`. Pure function of (template item, athlete history,
readiness, load state) → concrete sets. No LLM in this path. Every output carries a
`rationale` with the real numbers used, because pillar 5 says the Hunter must be able to
see why.

### 5.1 Lifts

**Anchor selection**, per exercise family, in order:

1. Last completed session of that family within 21 days with ≥ 1 set at `rpe ≤ rpe_cap+1`
   → anchor = that session's working weight and the progression rule's verdict.
2. Else current e1RM (`trend_service.weekly_best_e1rm_series` last point, or best set in
   90 days) → weight = `round_to_increment(e1rm × pct_for_reps(reps_target) × 0.95)`, using
   the Epley inverse the app already uses (`core/e1rm.py`).
3. Else no anchor → prescription is sets × reps with weight `null` and rationale
   "first session — pick a load you can finish at RPE 7–8" (this is exactly the Coach's
   Week 1 instruction, now in-app).

**Progression rules** (from `items[].progression`):

| Rule | Verdict from last session | Next prescription |
|---|---|---|
| `linear` (main lifts, e.g. 5×5) | all sets hit target reps and max RPE ≤ `rpe_cap` | `+increment_lb` |
| | any set short by ≤ 1 rep, or RPE = cap+1 | hold weight |
| | short by ≥ 2 reps on ≥ 2 sets, or two consecutive holds | `−10%`, round to increment, flag `deload_lift` |
| `double` (accessories, rep range [lo, hi]) | all sets ≥ `hi` | `+increment_lb`, reps reset to `lo` |
| | else | hold weight, target `min(hi, last_reps+1)` |
| `rpe` (top set + backoffs, future) | — | out of scope v3 |

**Readiness modulation** (Condition band from `condition_service`, plus §6 guard):

| Band | Modulation |
|---|---|
| PEAK | no change; if a Gate is open on this family, the gate's target set is appended as a final "Gate attempt" set (§10) |
| BATTLE READY | no change |
| STRAINED | main lifts `×0.95`, drop the last accessory set; rationale says so |
| CRITICAL | hunt becomes `light`: main lifts ×0.85 for 3 sets, or the user takes the rest option the card offers |
| Overreach Guard veto (§6.4) | overrides the above with its own rule; always shown |

Rounding: 5 lb barbell, 2.5 lb dumbbell (per family), honoring `preferred_unit` (2.5/1.25
kg) — which requires the `weight_unit` fix in §12.

### 5.2 Runs

- **Weekly target miles** = linear ramp from `run_miles_min` to `run_miles_max` across the
  arc's weeks; every `deload_every_n_weeks`-th week × `deload_factor`. Same math the PWA's
  `expectedMiles()` does, moved server-side.
- **Per-run distance:** long run = `min(long_run_miles_target_for_week, 0.35 × weekly)`;
  easy runs split the remainder evenly across the template's easy-run days, clamped to
  the template's range.
- **Effort, not pace:** easy = HR cap at the user's zone-2 ceiling (from
  `hr_zone_seconds` history: the bpm below which ≥ 70% of easy-run time has fallen over
  the last 6 easy runs; fallback = 180 − age × 0.9 until 6 runs exist). Long runs get the
  same cap. Pace is reported after, never prescribed in v3.
- **Guard:** §6.4 can reduce a run's distance or convert it to `easy`; the card says why.

### 5.3 Where prescriptions show

- Today's Hunt card (top set only), planned hunt sheet (all sets), and — the point of the
  exercise — **pre-filled into LogView v2** (§7).

---

## 6. Load and the Overreach Guard

### 6.1 One currency

`app/services/training_load_service.py`. Per session, one `load` number, plus `miles` kept
separately because mileage rules are stated in miles:

| Source | Load formula | Fallback |
|---|---|---|
| Run/cardio with HR zones | Edwards TRIMP: `Σ zone_minutes × zone_weight` with z1..z5 = 1..5 (from `hr_zone_seconds`) | duration × 2.5 (moderate) when zones are missing; flagged `estimated` |
| Lift with per-set RPE | session-RPE (Foster): `session_rpe_or_mean_set_rpe × duration_minutes` | if no RPE: `Σ(sets) × 6 × (duration/60)`; flagged `estimated`. Duration now persists (§7 fix) |
| Anything with WHOOP strain | keep `arise_strain` for display; **do not** mix into load (different scale) | — |

This is deliberately simple. The audit's item 10 (cardio fatigue capped at 5 effective sets)
is fixed by feeding TRIMP into `cooldown_service` for cardio instead of duration-with-a-cap.

### 6.2 Daily series

New table `daily_training_load`: `user_id, date(local), run_load, lift_load, total_load,
miles, acute_7d, chronic_28d, acwr, miles_7d, miles_prev_7d, long_run_share, flags JSON`.
Recomputed for the trailing 35 days on every ingest path (the three that already share PR
detection: `api/workouts.py`, `api/sync.py`, screenshot save; plus HealthKit import) and by
the nightly job. Acute/chronic are 7- and 28-day EWMAs of `total_load` (EWMA, not rolling
sum, so a rest day decays rather than cliff-drops).

### 6.3 Rules (the guard's vocabulary)

| Flag | Condition | Meaning |
|---|---|---|
| `acwr_high` | `acwr > 1.30` | acute load outrunning fitness |
| `acwr_critical` | `acwr > 1.50` | classic injury-risk zone |
| `ramp_high` | `miles_7d > 1.10 × miles_prev_7d` and `miles_7d > 8` | the 2024 failure mode |
| `long_run_share` | longest run in 7d > 35% of `miles_7d` | too much of the week in one run |
| `deload_due` | week-in-arc hits the arc's cadence, or two `deload_lift` verdicts in one week | planned or earned back-off |
| `monotony_high` | mean/sd of daily load over 7d > 2.0 | same load every day, no variation |

### 6.4 The Overreach Guard (how flags change prescriptions)

Applied after readiness modulation, before the prescription is stored:

| Flag(s) | Action |
|---|---|
| `acwr_critical` **or** (`acwr_high` and Condition < 65) | today's run → skipped-with-reason (REST DECREED, the v2 copy); lifts → `light` |
| `acwr_high` | runs −20% distance, converted to `easy`; lifts unchanged |
| `ramp_high` | cap this week's remaining run miles so `miles_7d ≤ 1.10 × miles_prev_7d`; long run first |
| `long_run_share` | cap the next long run at 35% of the weekly target |
| `deload_due` | apply the arc's `deload_factor` to runs and −15% to lift volume (drop a set) |

Everything the guard does is written into `planned_hunts.rationale` and rendered on the
card ("Run cut to 2 mi: 7-day miles are 14% over last week").

### 6.5 Condition v2

Two changes to `condition_service`:

- **Input 4 replaced:** "yesterday's strain" → **acute-vs-chronic load**: subscore
  `100` at `acwr ≤ 1.0`, linear to `40` at `acwr = 1.5`, floor 40. Same weight (0.10).
- **Input 6 added:** **HRV trend** (weight 0.10, taken from recovery's 0.40 → 0.30 when
  HRV is present; renormalization handles absence as today): 7-day mean vs 28-day mean,
  subscore `100 − 300 × max(0, 1 − ratio)`, floor 40. HRV is already stored from both
  HealthKit (v2.1 chunk 1) and WHOOP; today nothing reads it.

Band thresholds unchanged so Gates and the rest directive keep their meaning.

### 6.6 Surfaces

- **Status:** a compact **LOAD** strip under Condition: acute/chronic sparkline (28 days),
  ACWR badge in band color, `miles_7d` vs plan. Tap → Load sheet (rules, current flags,
  the week's runs and lifts as load bars).
- **Power › Load** segment replaces the unopened Exertion segment (v2.1 interview: "Exertion
  tab: unopened"). Keeps the strain/volume small multiples; adds the ACWR series and weekly
  miles vs plan. Cardiac cost stays as a card inside it.

---

## 7. LogView v2 — confirm-or-adjust

The v2 spec ruled the active-hunt flow out of scope. It is the center of v3 because a
prescription is worthless if confirming it costs more taps than typing from scratch. Every
item below has an anchor in the iOS audit.

### 7.1 Entry

- **BEGIN HUNT** on a day with a planned hunt opens the session **pre-populated**: exercises
  in template order, prescribed sets as ghost values (grey, italic), "last time" beside each
  row. The free-form path (blank session) remains one tap away ("Start empty hunt").
- **Repeat last hunt** on the Hunt tab and the idle screen (audit gap 5) — copies exercises
  and last weights as ghosts. Zero templates exist today; this is the cheapest one.

### 7.2 Set row

| Element | Today | v3 |
|---|---|---|
| Completion | derived from `weight>0 && reps>0` in five places (`LogView.swift:1193`, `:1319`, `LogViewModel.swift:58`, `:76`, `SupersetCard.swift:19`) | stored `isCompleted` + `completedAt`; a ✓ button on the row. Tapping ✓ on a row with empty fields **accepts the ghost values** (one tap logs a prescribed set) |
| Last time | none | grey column `225×5` from `GET /exercises/{id}/last-performance` (new; returns last session's sets, best e1RM, days ago) |
| Target | none | ghost weight/reps from the prescription; a small `↑+5` chip when the progression rule moved the weight |
| Live feedback | none | e1RM of the entered set vs the family's best; turns gold when it would be a PR, purple when it clears an open Gate |
| Unit | hardcoded `lb` (`LogView.swift:1423`, `LogViewModel.swift:214`) | honors `preferred_unit` |
| Warm-up | none; screenshot import drops warm-ups (`ScreenshotProcessingViewModel.swift:145`) | "Add warm-ups" generates 40/60/80% ramp rows marked `isWarmup` (persisted; excluded from PRs/volume) |
| Plate math | none | tap the weight → plate sheet for the bar in use (45/35 lb, 20 kg) |
| RIR | hardcoded nil (`LogViewModel.swift:216`) | sent when set |

### 7.3 Rest timer v2

Replaces `QuestTimerCard` (`LogView.swift:973-1141`): per-exercise default countdown
(main 180 s, secondary 120 s, accessory 90 s, editable per family), starts on ✓ not on
keystroke, lives in a **sticky bottom bar** (always visible), haptic at 10 s and 0, and a
**local notification** at zero when backgrounded (`NotificationManager` already schedules
locals for `streak_at_risk`). Phase 5 adds a Live Activity for the same state.

### 7.4 Draft persistence

An `ActiveHuntStore` mirroring `PendingWorkoutStore` (`PendingWorkoutStore.swift:91-135`)
saves the in-progress session on every mutation. Reopening the app within 12 hours shows a
RESUME HUNT banner on Status and the idle screen. Swipe-back on an active hunt asks before
discarding (today only the X button does, `LogView.swift:278-288`).

### 7.5 Save

- Sticky FINISH bar; `canSave` no longer blocks on blank trailing sets (they are dropped
  with a toast).
- One celebration screen stacking PR(s) → Gate clear → XP → rank, with a single CONTINUE
  (today: up to three sequential full-screen covers, `LogView.swift:142-221`).
- The create payload carries `duration_seconds` (measured today, discarded at
  `LogViewModel.swift:232`), `is_bodyweight`, `is_warmup`, `rir`, `completed_at` per set,
  and `planned_hunt_id`. Backend links the session to the planned hunt and sets its status.
- Post-save edit: date, notes, RPE, and sets become editable from the detail view
  (today only the name is, `QuestDetailView.swift:102-130`). `PUT /workouts/{id}` exists.

### 7.6 Picker

Recents (last 30 days, most-frequent first), favorites, multi-select, muscle filter, and
clearing filters on dismiss (`LogView.swift:1628-1634` leaks state). Swapping an exercise
inside a prescribed hunt offers same-family alternatives first, then same-primary-muscle.

### 7.7 Small fixes folded in

Locale-safe number parsing (`Double(weightText)` fails on comma decimals,
`LogViewModel.swift:343`); next-field keyboard affordance; exercise reorder; swipe-to-delete
set; enqueue offline on 5xx too, not only `networkError` (`LogViewModel.swift:245-251`).

### 7.8 Instrumentation

Client-side timing: `set_logged` events with milliseconds since previous set and
`source: prescribed|ghost_accepted|typed`. This is the one metric v3 is judged on for J2.
Stored locally and summarized into a `logging_stats` field on the weekly debrief request;
no third-party analytics SDK.

---

## 8. The Coach

### 8.1 Why an LLM, and where it is allowed

The deterministic engine (§5, §6) already answers "what weight." What it cannot do is the
thing the user built a Cowork job to get: read the week as a whole, notice that squat
stalled the week sleep fell apart, connect the WHOOP recovery dip to the long-run jump, and
say so in two sentences with a concrete change. That is language over structured data, and
it is what Claude is for.

The Coach is allowed to: **explain**, **prioritize**, **propose typed adjustments**, and
**answer questions over the athlete's own data**. It is not allowed to: write to any table
directly, prescribe outside the guard's bounds, or invent numbers not present in its
context. Structured outputs plus a validator enforce all four.

### 8.2 Athlete context builder

`app/services/coach_context_service.py` composes existing functions — the backend audit
confirmed most of it is callable without new SQL:

| Section | Source | Budget |
|---|---|---|
| Campaign, current arc, week-in-arc, next 7 planned hunts with prescriptions | §4 | ~600 tokens |
| Last 4 weeks of sessions: lifts with sets (weight, reps, RPE, e1RM), runs with miles/pace/avg HR, weekly `run_miles` | `api/calendar.py:49` (`weeks=4`) | ~3,000 |
| Per-family weekly-best e1RM series (12 wks), slope, projection | `trend_service.py:22`, `:52`, `:76` | ~400 |
| Condition today + inputs, muscles cooling | `condition_service.py:155` | ~250 |
| Load: 28-day daily series, ACWR, flags | §6.2 | ~500 |
| Sleep / HRV / RHR / recovery 14-day series | **new** `daily_activity_series()` — the audit's missing helper #1 | ~400 |
| Goals + pace, PRs in window, open/cleared gates | `goal_service.py:287`, `weekly_report_service.py:162`, `gate_service.py:365` | ~300 |
| Last debrief's accepted/rejected adjustments, last 7 briefings | `coach_outputs` (§8.5) | ~400 |
| Athlete profile: age, sex, bodyweight trend, injury notes (new free-text profile field) | `UserProfile` + bodyweight | ~150 |

≈ 6–8K tokens of context. The system prompt (coaching philosophy, voice, output contract,
guardrail statement) is frozen text and cached with `cache_control` (§8.6). Volatile context
goes in the user turn. Numbers are serialized with fixed key order and fixed precision so
identical weeks hash identically (`context_hash` on the stored output).

### 8.3 Hunt Briefing (daily)

- **When:** written by the nightly job for the next local day, **only for days with a
  planned hunt** (lift, run, or light). Rest days get no briefing and no push — the v2 §11
  argument against daily nags holds; the difference is that a training-day briefing has
  content.
- **Output contract** (structured output, JSON schema):

```json
{
  "headline": "≤ 90 chars, System voice",
  "body": "≤ 2 sentences with the numbers that matter",
  "modulation": {"type": "none|reduce_run|reduce_lift|swap_to_easy|rest",
                 "magnitude_pct": 0, "reason": "…"} ,
  "watch": ["acwr_high"]
}
```

- **Validator:** `modulation` may only move within what §5.1/§6.4 already allow (±5% lift,
  −20% run, swap-to-easy, rest); anything larger is clamped and logged. If the engine's own
  guard already decided REST, the model's job is to explain, not re-decide.
- **Where it renders:** inside the TODAY'S HUNT card as the System line (mono/bracket
  styling — the v2 Directive's dialect survives here), tap → Briefing sheet with the "why"
  (context numbers cited) and the last 7 briefings. The `user_directives` table and rules
  engine are retired; the rules' *flags* (streak lapse, plateau, volume gap, lift lag) move
  into the context builder as inputs the Coach can cite. XP for "directive followed" becomes
  XP for **hunt completed as planned** (§13).
- **Push:** `hunt_briefing` at a user-set time (default 06:30 local), training days only,
  opt-in via the existing preferences table. Payload = headline.

### 8.4 Weekly Debrief (Sunday)

- **When:** nightly job on Sunday 20:00 local (or Monday 05:00 if Sunday's hunt isn't
  logged yet — configurable). Also on demand from the Status "This Week" card.
- **Output contract:**

```json
{
  "summary": "≤ 4 sentences: what happened vs plan, the one thing that mattered",
  "adherence": {"planned": 5, "done": 4, "modified": 1, "skipped": 0},
  "highlights": [{"kind": "pr|gate|milestone|consistency", "text": "…"}],
  "concerns":   [{"flag": "ramp_high|acwr_high|sleep_low|lift_stall|…", "text": "…"}],
  "adjustments": [
    {"op": "set_progression", "family": "back_squat", "increment_lb": 5,
     "reason": "…", "confidence": "high|medium|low"},
    {"op": "set_week_miles", "week_start": "2026-09-07", "miles": 12.5, "reason": "…"},
    {"op": "deload_now", "scope": "lifts|runs|all", "reason": "…"},
    {"op": "swap_days", "a": "2026-09-09", "b": "2026-09-10", "reason": "…"},
    {"op": "extend_arc", "weeks": 1, "reason": "…"},
    {"op": "change_reps", "family": "bench_press", "sets": 3, "reps": [3,3], "reason": "…"}
  ],
  "next_week_focus": "one line"
}
```

- **Typed ops are the whole point.** Each op has a deterministic applier in
  `campaign_service` and a validator (miles within ±15% of the arc's ramp value unless
  `deload_now`; increments within the family's increment; no more than one `deload_now`
  per 3 weeks; `extend_arc` ≤ 2 weeks). Invalid ops are returned to the user as
  "suggested, out of bounds" — visible, not applied.
- **UI:** `WeeklyReportView` becomes the **Debrief sheet**: summary, adherence ring,
  highlights, concerns, then adjustments as cards with ACCEPT / DISMISS. Accepting rewrites
  next week's `planned_hunts` and stores the decision. The existing goal-pace section stays
  below as "Goal pace". The static `_generate_suggestions` prose is deleted.
- **Push:** `weekly_report_ready` already exists and is already sent from
  `api/weekly_report.py:53` — it now fires from the job, not from a GET.

### 8.5 Storage and auditability

```
coach_outputs   id, user_id, kind(briefing|debrief|answer), for_date, context_hash,
                prompt_version, model, input_tokens, output_tokens, cache_read_tokens,
                output JSON, validated JSON, decisions JSON (accepted/dismissed op ids),
                created_at
```

Every card that shows Coach text links to its row's "why" (the context sections it cited).
If the model refuses (`stop_reason == "refusal"`) or the call fails, the card falls back to
the engine's own rationale — the app never shows an empty briefing.

### 8.6 Model, cost, and API shape

- **Model:** `claude-opus-5` (the current default; the screenshot extractor stays on
  `claude-sonnet-5` — vision extraction is a different job). Adaptive thinking on (the
  default); `output_config.effort` `medium` for briefings, `high` for debriefs.
  Structured outputs via `output_config.format` with the schemas above (`client.messages
  .parse()` in the Python SDK). Include `fallbacks: "default"` with the
  `server-side-fallback-2026-07-01` beta so a policy decline (unlikely for fitness text,
  possible for injury questions) is re-run automatically rather than blanking the card.
- **Caching:** frozen system prompt + output schema first with `cache_control`; the
  volatile athlete context after. Debrief and briefing share the same system prefix.
- **Cost, one user:** briefing ≈ 8K input (≈ 2K uncached after the prefix caches) + 300
  output ≈ $0.02; ×5 training days ≈ $0.10/week. Debrief ≈ 10K input + 1.5K output ≈
  $0.09. **≈ $0.80/month.** Ten users: $8/month. Cost is not a design constraint here; the
  scan-credit paywall was built for a per-image cost this feature does not have.
- **Ask the System** (v3.1): a bounded chat over the same context ("why is bench stalled?",
  "can I move Saturday's squat to Friday?"). Multi-turn with the SDK's conversation
  pattern; ops proposed in chat go through the same validators and ACCEPT cards. Not in the
  v3 critical path.

### 8.7 Prompt principles (recorded so the first prompt isn't written from scratch)

- Voice: the System — terse, declarative, numbers over adjectives. No exclamation marks.
- Cite the context: every claim in `body`/`summary` must reference a number present in the
  context; the validator rejects outputs that name a lift family absent from the context.
- Prefer one change over three. `adjustments` ≤ 3 per debrief.
- Never contradict the guard: if a flag is set, the coach explains it; it cannot argue it
  away.
- Prompt is versioned (`prompt_version`) and lives in `app/coach/prompts/`. Changing it is
  a code change with a test that replays three stored contexts and checks the schema.

---

## 9. Plumbing

### 9.1 Background ingestion (iOS)

`HKObserverQuery` + `enableBackgroundDelivery` for workouts (immediate), sleep, HRV, and
resting HR (hourly). The observer's update handler runs the existing
`HealthKitManager.importNewWorkouts` / `syncTodayOnly` paths and calls the completion
handler. `UIBackgroundModes` already declares `fetch` and `processing`; this finally uses
them. Success metric: a run recorded on the watch is visible in Hunt within 15 minutes with
the phone in a pocket. This also removes the PWA README's "can lag a minute or two" caveat
and makes the nightly job's inputs complete before it runs.

### 9.2 Nightly job (backend)

The v2 roadmap deliberately avoided scheduler infra ("no-extraneous-features"). v3 needs
one: prescriptions must exist before the user wakes up, briefings need to be pre-written for
the push, and gate spawn should not depend on someone opening the Status tab.

- **Mechanism:** a second Railway service in the same project, `cron`, with
  `cronSchedule = "0 * * * *"` and `startCommand = "python -m app.jobs.hourly"`. Hourly so
  each user's local 02:00 / 20:00 windows are hit; the job is idempotent per
  `(user, date, task)`. No long-running process, no APScheduler, no Redis.
- **Tasks:** `expire_stale_gates`, recompute `daily_training_load` (35 days), Condition v2
  snapshot for the day (stored now — the audit's `condition_peak_7` approximation goes
  away), `evaluate_gate_spawns`, materialize planned hunts (+8 days), generate tomorrow's
  prescription, write tomorrow's briefing (training days), Sunday debrief, send pushes,
  mark past `planned` hunts `skipped`.
- **Observability:** each task writes a `job_runs` row (task, user, started, finished,
  status, error). Sentry is already wired in `main.py`.

### 9.3 Notifications

| Type | Kind | v3 |
|---|---|---|
| `hunt_briefing` | push, training days only, opt-in, user-set time | new |
| `weekly_report_ready` | push | exists; fires from the job |
| `gate_opened` | push | exists; fires from the job |
| `overreach_warning` | push, at most once per 3 days | new — only on `acwr_critical` or `ramp_high` |
| `rest_timer_done` | local | new (§7.3) |
| `streak_at_risk` | local | exists; **retired** — streak semantics move to plan adherence (§13) |

The permission prompt stays where v2 put it (post-save celebration dismissal).

### 9.4 Widgets and Live Activity (Phase 5)

- Lock-screen / home widget: Today's Hunt (type, top set or miles) + Condition score.
  Reads a cached JSON written by the app; refreshes on the background HealthKit callback.
- Live Activity during an active hunt: current exercise, next prescribed set, rest
  countdown. Same state as the sticky timer bar.

---

## 10. Gates v2

The north star has not fired in eight weeks. Four calibration changes, all in
`gate_service.py` / `trend_service.py`:

1. **Baseline = campaign best**, i.e. best e1RM on that family since the campaign
   `start_date` (fallback: last 12 weeks), not the all-time best (`gate_service.py:274`
   compares against all-time today). Lifetime PRs stay lifetime PRs in Records; a Gate is
   about beating *this campaign's* ceiling. Rank still keys off the % jump.
2. **`MIN_WEEKLY_POINTS` 6 → 4** (`trend_service.py:19`), and weekly points come from the
   family, so a Saturday squat and a Sunday front squat both count toward `back_squat`'s
   series (one point per week — that rule stays; two lifts in one weekend is still one
   week of evidence).
3. **Spawn onto the plan.** Evaluated by the nightly job; a spawned gate targets the *next
   planned hunt* containing that family, and the prescription engine appends the gate set
   ("Gate attempt: 235×5 after working sets"). Window = until that planned hunt + 7 days
   (not a flat 14). Condition is checked the morning of the attempt, not at spawn:
   STRAINED → the gate set is dropped from the prescription that day and the window
   extends one hunt.
4. **Clear feedback.** `gate_cleared` returned in the workout-create response (v2 QA
   W5/W8), one celebration screen (§7.5), Hunt Log sigil as today.

Expected effect for a Sat/Sun 5×5 lifter: first gate within 4–5 weeks of consistent
logging, roughly one gate per lift per arc.

---

## 11. Cut list and retirements

| Item | Action | Why |
|---|---|---|
| `training-calendar/` PWA | Retire one release after §4.6 week view ships; leave gh-pages read-only for 30 days, then remove the workflow | one plan, one place |
| `Fitness Coach/` Cowork job + `weekly-export` skill + `Workout Exports/` | Delete the scheduled task and the skill; archive the folder | 7 failed runs; replaced by §8.4 |
| `user_directives` + `directive_service` rule engine | Retire the table and the user-facing rules; keep `calculate_todays_workout_stats`, `_week_windows`, `_volume_lb` as context-builder inputs (make them public) | replaced by Briefing; rules 4/5 dead by construction, rule 7 spurious |
| `weekly_report_service._generate_suggestions` | Delete | replaced by Debrief |
| `quest_definitions` / `user_quests` tables | Drop (the v2 §5.3 decision was "leave until proven"; the Directive ran 8 weeks and is itself being replaced) | dead weight, 5 migrations reference them |
| `exercise_equivalence.py` and the four substring canonicalizers | Replace with `exercise_families` (§4.2) | audit item 2 |
| Power › Exertion segment | Folded into Power › Load (§6.6) | unopened |
| `streak_at_risk` local notification + streak XP | Retire; plan-adherence XP replaces it (§13) | HealthKit runs don't sustain streaks today (`healthkit_service.py:19-27`), so the streak lies for a runner |
| Scan-credit paywall for the owner | One-time `has_unlimited = true` for the owner account (admin script); IAP code stays for other users | the owner should not be paywalled out of his own scanner |
| Friends UI | No change | already demoted in v2 |

---

## 12. Foundations (Phase 0 — do first, everything depends on them)

From the backend audit, each of these silently corrupts a coach's inputs:

1. **`WorkoutSession.local_day`** (Date) + `tz_offset_minutes`. Manual creates parse
   `"YYYY-MM-DD"` to naive midnight (`schemas/workout.py:117`) while HealthKit imports
   store a true UTC instant (`healthkit_service.py:98`); every weekly bucket in analytics
   compares the same column. Backfill: manual rows → `date.date()`; HealthKit rows →
   `(date + offset).date()` using the profile timezone (new field, default from the last
   `client_date` seen). All week/day math switches to `local_day`. The calendar endpoint's
   uniform offset subtraction (`api/calendar.py:94`) goes away.
2. **`exercise_families`** table + `exercises.family_id` + backfill script + delete the
   substring schemes (§4.2).
3. **Honor `weight_unit`.** e1RM (`workouts.py:337`), tonnage (`weekly_report_service.py:126`,
   `directive_service.py:209`), PR buckets (`pr_detection.py:92`), plate milestones
   (`gate_service.py:55`), strength standards (`analytics.py:480`) all treat `weight` as lb.
   Normalize to lb at ingest (store `weight_lb` alongside `weight`+`weight_unit`), read
   `weight_lb` everywhere. Small change, large honesty gain.
4. **Persist session duration** and per-set `completed_at`, `is_bodyweight`, `is_warmup`,
   `rir` — the create contract (§7.5).
5. **`daily_activity_series()`** helper and a public per-family enumeration helper (the
   audit's missing primitives #1 and #2).
6. **Drop the quest tables**; add `job_runs`; add the cron service (§9.2) with a no-op task
   so deploy shape is proven before it has real work.
7. **HealthKit background delivery** (§9.1) — iOS, independent of the backend items.
8. **Plateau threshold** `>8` → `≥5` distinct dates per family per 28 days
   (`analytics.py:690`) so the insight can exist for anyone under 2.25 sessions/week per
   lift. Cheap, and it feeds the context builder.

---

## 13. XP economy delta

| Source | v2 | v3 |
|---|---|---|
| Directive followed | +40/day | **0 — retired** |
| **Hunt completed as planned** (`planned_hunts.status = done`) | — | **+40**; `modified` +25; free-form hunt still earns the base 50 |
| **Week completed as planned** (all planned hunts done/modified, none skipped) | — | **+150** (replaces the 7-day streak bonus) |
| Gate clear | C 300 / B 500 / A 800 / S 1200 | unchanged |
| Overreach Guard respected (guard cut a run/lift and the user logged the reduced version, not more) | — | **+30** — the game rewards restraint, which is the whole point of J4 |
| Everything else | unchanged | unchanged |

New achievements: `campaign_arc_complete`, `four_weeks_on_plan`, `guard_respected_10`,
`first_debrief_accepted`. Pacing stays within the v2 envelope.

---

## 14. Screens (delta only)

- **Status:** header → Condition → **TODAY'S HUNT** (with Briefing line) → **LOAD strip** →
  Gate card(s) → This Week (adherence ring replaces workouts-vs-goal bar; "Debrief →" link)
  → Power snapshot. Still six sections.
- **Hunt:** week strip with plan overlay + pace strip; BEGIN HUNT / REPEAT LAST / SCAN;
  calendar and log as today. Planned-hunt sheet for future days.
- **Active hunt (LogView v2):** §7.
- **Power:** segments `["Power", "Load", "Vessel", "Records"]`; Goals row unchanged.
- **Hunter:** Campaign row (name, arc, week; edit/pause/import), Coach settings (briefing
  time, push toggles), Integrations gains a "background delivery" status line.
- **Sheets:** Planned Hunt, Briefing, Debrief (replaces Weekly Report), Load, Plate calc.

Design language unchanged. Mockup to be produced before Phase 1 per the house rule
(`docs/mockups/arise-v3-mockup.html`), covering Today's Hunt, LogView v2 set row + timer bar,
Debrief sheet, and the Hunt week strip.

---

## 15. Contract registry (backend ↔ iOS, the mirrors that trigger `/evaluate`)

Routers mount without `/api`. Snake_case JSON; explicit `CodingKeys` in `APITypes.swift`.
Field tables for the three contracts LogView v2 and Status depend on; the rest follow the
same discipline when built.

### 15.1 `GET /hunts/today` → `PlannedHuntResponse?`

| JSON | Type | Null? | Swift |
|---|---|---|---|
| `id`, `campaign_id`, `arc_id`, `template_id` | string | no | `id` … |
| `date` | `YYYY-MM-DD` | no | `date: String` |
| `type` | `lift \| run \| light \| rest` | no | `type: PlannedHuntType` |
| `title`, `location_tag` | string | tag yes | |
| `status` | `planned \| done \| modified \| skipped \| moved` | no | `status: PlannedHuntStatus` |
| `session_id` | string | yes | |
| `prescription` | `PrescriptionResponse` | yes (rest) | |
| `rationale` | `[RationaleLine]` `{key, text, numbers: {…}}` | no, may be empty | |
| `briefing` | `BriefingResponse` | yes | §15.3 |
| `modulation` | `{band, factor, note}` | yes | |
| `guard_flags` | `[string]` | no | |

### 15.2 `PrescriptionResponse`

| JSON | Type | Null? |
|---|---|---|
| `version` | int | no |
| `exercises[]` | array | no |
| `exercises[].family_id`, `exercise_id`, `exercise_name`, `role` | string; `role ∈ main\|secondary\|accessory\|gate\|warmup` | no |
| `exercises[].sets[]` | array of `{set_number, target_weight_lb, target_reps_lo, target_reps_hi, target_rpe, is_warmup, is_gate_attempt}` | `target_weight_lb` yes (no anchor) |
| `exercises[].last_performance` | `{date, sets: [{weight_lb, reps, rpe}], best_e1rm, days_ago}` | yes |
| `exercises[].progression_note` | string ("+5 — last week 225×5×5 @ RPE 8") | yes |
| `run` | `{kind: easy\|long\|shakeout, miles, hr_cap_bpm, note}` | yes |

### 15.3 `BriefingResponse` / `DebriefResponse`

`BriefingResponse`: `id`, `for_date`, `headline`, `body`, `modulation {type,
magnitude_pct, reason}`, `watch [string]`, `why [{section, text}]`, `generated_at`.

`DebriefResponse`: `id`, `week_start`, `summary`, `adherence {planned, done, modified,
skipped}`, `highlights [{kind, text}]`, `concerns [{flag, text}]`, `adjustments
[{id, op, params {…}, reason, confidence, status: proposed|accepted|dismissed|out_of_bounds}]`,
`next_week_focus`, `goal_reports` (existing shape), `generated_at`.
`POST /coach/debrief/{id}/adjustments/{adj_id}` with `{decision: accept|dismiss}`.

### 15.4 Workout create additions (`POST /workouts`, `/sync`)

Request: `planned_hunt_id?`, `duration_seconds?`, per set `is_bodyweight`, `is_warmup`,
`rir?`, `completed_at?`, `weight_unit`. Response adds `gate_cleared?` (v2 W5) and
`planned_hunt_status?`.

### 15.5 `GET /load` → `TrainingLoadResponse`

`as_of`, `acute_7d`, `chronic_28d`, `acwr`, `band`, `miles_7d`, `miles_plan_7d`,
`long_run_share`, `flags [string]`, `series [{date, run_load, lift_load, total_load, miles,
acwr}]` (28 days).

---

## 16. Build phases

Each phase ends with the v2 ship criteria (pytest + ruff, sim build + entitlements lint,
contract-mirror `/evaluate` against the Pydantic schemas, pathspec commit, verified Railway
SUCCESS, Xcode rebuild reminder). Sessions are the unit v2 used; v2 shipped four phases in
one day, so these are upper bounds.

| Phase | Scope | Sessions | Ship signal |
|---|---|---|---|
| **0 — Foundations** | §12 items 1–8; owner unlimited scans; cron service with a no-op task | 1 | analytics unchanged on a before/after snapshot except where `local_day` corrects a bucket; a run lands without opening the app |
| **1 — Campaign + Prescription** | §4 tables/API/import of `data.js`; §5 engine; Today's Hunt card; Hunt week strip + pace strip (PWA parity); Directive text now comes from the engine's rationale (no LLM yet) | 2 | the user can delete the PWA from the home screen and lose nothing |
| **2 — LogView v2** | §7 in full; contract §15.4; `/exercises/{id}/last-performance` | 2 | median seconds-per-set on a prescribed hunt ≤ 5 (instrumented) |
| **3 — Load + Guard + Condition v2 + Gates v2** | §6, §10; Power › Load; nightly job takes over spawn/expire/materialize | 1–2 | a gate spawns onto a planned heavy day; ACWR and mileage flags visible; Condition shows HRV |
| **4 — The Coach** | §8 context builder, briefing, debrief, ops + accept UI, pushes; retire Directive tables, static suggestions, the Cowork job and skill | 2 | first debrief accepted in-app; briefing push arrives before the alarm |
| **5 — Delight** | Widgets + Live Activity (§9.4); Ask the System; PWA removal; §13 achievements | 1–2 | — |

Total: 9–11 sessions. Phases 1 and 2 are independent of each other after Phase 0 and can
be built in either order; 3 needs 1; 4 needs 1–3; 5 needs 2 and 4.

---

## 17. Success metrics (what "next level" means, measurably)

| Job | Metric | Baseline (today) | Target (after Phase 4) |
|---|---|---|---|
| J2 | median seconds per logged set, prescribed hunts | not instrumented (est. 15–25 s) | ≤ 5 s |
| J2 | % of lift sessions logged in-app the same day | unknown (no `local_day`) | ≥ 90% |
| J1 | % training days with a Briefing that names a number specific to that day | 0 (MAINTAIN) | 100% |
| J1/J5 | planned-hunt adherence (done + modified) / planned | — | ≥ 80% per arc |
| J3 | gates spawned per lift per arc; gates cleared | 0 since 2026-07-12 | ≥ 1 spawned per big-three lift per arc; ≥ 1 cleared per arc |
| J4 | weeks with `acwr > 1.5` or `ramp_high` unresolved by a prescription cut | not measured | 0 |
| J5 | debriefs with ≥ 1 accepted adjustment | 0 (no debrief exists) | ≥ 75% of weeks |
| J7 | minutes from watch save to session visible in Hunt (phone in pocket) | until next app open | ≤ 15 |
| Trust | Coach outputs falling back to engine rationale (refusal/error/out-of-bounds) | — | ≤ 5% |

---

## 18. Risks and open questions

1. **Prod usage is unverified.** This session's read-only prod snapshot was blocked by the
   permission classifier. The JTBD "served" estimates are inferred from code and docs. A
   read-only script exists at the scratchpad path noted in the session summary; run it
   before Phase 1 to confirm: sessions/week split lift vs run, which lift names are actually
   logged (family backfill depends on it), directive type distribution, whether any gate has
   spawned since July, and daily-activity input coverage.
2. **Plan conflict.** The PWA plan (Sat squat / Sun bench, 5×5) and the Coach's Week 1 plan
   (Fri push / Sat pull / Sun legs, 3×3) are different programs. §4.3 imports the PWA plan
   because it is the one with check-offs; the user should confirm before Phase 1.
3. **Load formulas are first-order.** TRIMP and session-RPE are standard but coarse; the
   guard's thresholds (1.3/1.5, 10%, 35%) are literature defaults, not fitted to this user.
   They are constants in one module and the Debrief can propose changing them
   (`set_guard_threshold` is a reasonable v3.1 op).
4. **Nightly job on Railway cron:** verify a cron service can reach the same Postgres and
   that its alembic head matches the web service's (it must not run migrations). Hourly
   granularity means "06:30 local" pushes land at the top of the hour; acceptable for v3.
5. **Background HealthKit delivery** is best-effort by design; iOS throttles it. The
   foreground sync stays as the backstop.
6. **The Coach's tone** in a 90-character headline is easy to get wrong (cheesy or
   clinical). Budget a prompt-tuning pass with 10 stored contexts before enabling the
   push.
7. **Multi-user shape is preserved** (everything is per-user; the cron loops over active
   campaigns) but the template library, the import format, and the coach prompt are tuned
   for one athlete. That is the correct trade for now (solo dev, N=1) and is stated so a
   later "launch" decision doesn't inherit it as an accident.
8. **`local_day` backfill** must be verified on a prod copy before it runs — it rewrites
   the axis every chart uses.

---

*Companion docs to be written: `docs/arise-v3-roadmap.md` (live tracker, same role as the
v2 roadmap) after Phase 0; `docs/mockups/arise-v3-mockup.html` before Phase 1. Code cited
was verified against the tree on 2026-09-04.*
