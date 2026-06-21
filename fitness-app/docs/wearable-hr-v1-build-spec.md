# Wearable HR v1 — Build Spec (living document)

**Status:** In progress · Chunk A `Done (304511f)` · Chunk B `Done (00c0cdc)` · Chunks C/D `Not started`
**Author:** Claude Code (spec-writing council: backend / iOS / design / PM), 2026-06-20
**Branch:** `claude/next-steps-design-spec-83n3jo` → merges to `main`
**Scope:** Apple Health import (1.7a backend + 1.7b iOS) + HR display (1B). WHOOP (1A) stubbed.

## What this document is

This is the **single executable source of truth** for building Wearable HR v1 across four chunks
(A → B → C → D), each in its own section below, each ending at a build/test gate. It exists so a
**fresh Claude session, with no memory of prior sessions, can open this file, find the next
unfinished chunk, and execute it correctly** — including absorbing anything earlier chunks discovered.

It is a **LIVING document.** Chunk sections are not frozen plans — they are updated in place as builds
reveal reality (a reused backend function behaves differently, a contract field is renamed, an
entitlement surprises us). The mechanism that keeps those updates consistent across sessions is the
**[Contract Registry](#contract-registry)** + the **[Amendment Protocol](#amendment-protocol-how-to-adjust-chunks-mid-build)**.
Read those two sections before trusting any chunk body — a chunk's prose may have been amended after it
was first written, and the dated notes will tell you.

## Relationship to the other docs

| Doc | Role | Relationship |
|---|---|---|
| [`wearable-heart-rate-quest-integration.md`](./wearable-heart-rate-quest-integration.md) | Original phased scoping; decisions **D1–D4**; the "why" | Background. Don't re-litigate D1–D4 here. |
| [`wearable-hr-next-steps.md`](./wearable-hr-next-steps.md) | The plan; **§10 locked council decisions**; where stage-one ended | **Parent plan.** §10 is binding. This doc is the execution wrapper around §10's chunked build order. |
| **this doc** | Orchestration + per-chunk build specs + contract registry + amendment protocol | The thing you open to build. Updates as builds happen. |

> **Precedence:** if this doc and the plan disagree on *scope*, §10 wins — amend this doc to match
> (and log it). If they disagree on a *contract field*, the **Contract Registry below wins** (it's the
> live mirror; the plan is a snapshot).

---

## How to use this spec (for a future session)

You are likely a fresh session. Do this, in order, every time:

1. **Find the next chunk.** Scan chunk sections A → B → C → D for the first `Status: Not started`. That
   is your chunk. Do **not** skip — the order is a hard dependency chain (see [Dependency graph](#dependency-graph--sequencing)).
   If a chunk is `In progress` (a prior session stopped mid-build), resume *that* one; read its build-note.
2. **Re-read three things before writing code:** (a) the **chunk's own section** — it may carry dated
   amendment notes; (b) the **Contract Registry** (current `version` + field tables); (c) the
   **Amendment Log** — skim every row dated after this chunk was last touched.
3. **Build to the gate.** Implement only what the chunk lists. Run the chunk's build/test gate (backend:
   pytest + ruff; iOS: xcodegen + xcodebuild + lint-entitlements). Not done until the gate is green and
   you've pasted the gate output into the build-note.
4. **On green, close the chunk:** flip `Status: Not started` → `Status: Done (YYYY-MM-DD, <sha>)`; append
   a **build-note** (what you actually built, what differed, gate output, commit); commit (and for Chunk A,
   deploy — see [Cross-cutting acceptance](#cross-cutting-acceptance--smoke-test)).
5. **If anything material changed, run the [Amendment Protocol](#amendment-protocol-how-to-adjust-chunks-mid-build) BEFORE the next chunk.** A future session
   won't have your discovery except through this doc. Propagation is part of finishing the current chunk.
6. **Checkpoint at session boundaries** — natural stops are *between* chunks. If you must stop mid-chunk,
   set `In progress`, write a build-note of exactly where you stopped, leave the gate red-but-explained.

> **Mental model:** *pick next `Not started` → re-read it + Registry + Log → build to gate → on green,
> mark Done + build-note → if material change, amend everywhere + log → next.*

---

## Contract Registry

The **single source of truth for every contract that crosses a chunk boundary.** Pre-filled to **v1**
from the backend author's finalized design + assembly reconciliations; **Chunk A confirms each table
against the built code on first build** (and bumps the version only if reality differs).

**Authority & mirroring rules**
- **Chunk A is the authority.** The backend Pydantic schemas are canonical. If A's built code deviates
  from a table here, **amend the table to match the code** (not vice-versa), via the Amendment Protocol.
- **B, C, D mirror A** field-for-field, including optionality (Swift `?` ⇔ Pydantic `Optional`/nullable)
  and JSON key casing (backend is **snake_case**; the iOS decoder does **not** auto-convert — every Swift
  field needs an explicit `CodingKey`).
- **A change here triggers the Amendment Protocol** — bump `version`, update downstream chunks inline, log it.
- **Optionality is load-bearing.** Apple-Watch sessions have no `strain`; sets may have no HR; zones are
  null when age is unknown. Nil-safety is a v1 acceptance criterion.

**Registry version:** `v1 (2026-06-21) — CONFIRMED against built code (Chunk A, 304511f). Contract holds as written: request/response field names + types as in §1–§2; backend is Pydantic v2 (snake_case keys, no alias generator); is_strength present; unmatched is objects; _build_workout_response + WorkoutSummary now return HR. No field changes.`

### 1. `POST /workouts/import-healthkit` — request

`HealthKitImportRequest { workouts: HealthKitWorkout[1..100] }`

`HealthKitWorkout`:

| Field | Type | Req? | Notes |
|---|---|---|---|
| `hk_uuid` | str | ✅ | `HKWorkout.uuid.uuidString`. Dedup key. `1..64` chars. |
| `activity_type` | str | ✅ | Controlled vocab mapped from `HKWorkoutActivityType` on-device (see Chunk C map). `1..64`. |
| `is_strength` | bool | ✅ (default `false`) | **Client declares** strength-vs-cardio; backend routes on it (avoids brittle server inference). |
| `start` | datetime ISO8601-UTC | ✅ | Fractional seconds + trailing `Z` accepted (validator mirrors `WorkoutCreate.parse_date`). |
| `end` | datetime ISO8601-UTC | ✅ | Must be `>= start`. |
| `duration_seconds` | int | ✅ | `>= 1`. |
| `kilojoules` | float? | — | Client converts HealthKit kcal → kJ (`× 4.184`). `>= 0`. |
| `avg_heart_rate` | int? | — | `20..250`. |
| `peak_heart_rate` | int? | — | `20..250`. |
| `hr_zone_seconds` | dict[str,int]? | — | e.g. `{"z1":120,...,"z5":30}`. Computed on-device from `220−age`; stored verbatim. **null when age unknown.** |
| `heart_rate_samples` | `[{timestamp: ISO8601-UTC, bpm: int}]?` | — | Reuses existing `HeartRateSampleCreate` shape. Decimate to ~1 sample / 5s on-device. |
| `distance_meters` | float? | — | Accepted but **low priority**; v1 stores only in `notes` (no column). Client may send `null`. |

`hr_source` is **not** in the request — the backend hard-stamps `"apple_watch"`.

### 2. `POST /workouts/import-healthkit` — response

`HealthKitImportResponse`:

| Field | Type | Notes |
|---|---|---|
| `imported` | str[] | `hk_uuid`s newly ingested this call. |
| `skipped_duplicates` | str[] | `hk_uuid`s already present for this user (idempotent skip). |
| `sessions_created` | str[] | new `WorkoutSession.id`s (cardio path). |
| `sessions_updated` | str[] | existing session ids that got HR backfilled (strength matches). |
| `unmatched` | `HealthKitUnmatched[]` | `{hk_uuid, activity_type, start, end}` — strength workouts with no overlapping session. **Objects, not strings.** |
| `quests_completed` | str[] | `UserQuest.id`s completed across affected days (deduped). |

### 3. Session + set HR response fields (consumed by Chunk D)

**`WorkoutResponse`** (`schemas/workout.py`) — fields already declared; **Chunk A must populate them in
`_build_workout_response`** (today they are dropped — see Chunk A "critical gap"):
`avg_heart_rate: int?`, `peak_heart_rate: int?`, `strain: float?`, `kilojoules: float?`,
`hr_zone_seconds: dict?`, `hr_source: str?`.

**`WorkoutSummary`** (list-view schema) — **does NOT currently carry HR; Chunk A must ADD**
`avg_heart_rate: int?`, `peak_heart_rate: int?`, `hr_source: str?` (it already has `strain`) so the
History-row provenance badge + strain render. (Touch-all rule.)

**`SetResponse`** — fields already declared; **Chunk A must populate in `_build_workout_response`**:
`start_time: str?`, `end_time: str?`, `avg_heart_rate: int?`, `peak_heart_rate: int?`.

**`hr_source` canonical values:** `"apple_watch"` · `"whoop"` · `"screenshot"` · `null`. (Underscore form —
the badge mapping in Chunk D must use these exact strings.)

### 4. Swift mirror structs (`APITypes.swift`, owned by Chunk B)

- Request: `HealthKitImportRequest`, `HealthKitWorkoutImport` (incl. `isStrength: Bool`,
  `hrZoneSeconds: [String:Int]?` as a **dict**, `heartRateSamples: [HealthKitHRSample]?`), `HealthKitHRSample`.
- Response: `HealthKitImportResponse` with `unmatched: [HealthKitUnmatched]` (**struct, not `[String]`**),
  `HealthKitUnmatched { hkUuid, activityType, start, end }`.
- Additive optional HR fields on `WorkoutResponse`, `WorkoutSummaryResponse`, `SetResponse`.
- `WhoopStatusResponse { connected: Bool, configured: Bool }` + `APIClient.getWhoopStatus()` (used by C's stub row).

### Reconciliation notes (assembly, 2026-06-20)

Deltas applied while merging the four drafts so the chunks are internally consistent:
1. **`hr_source` = `"apple_watch"`** (underscore), not `"applewatch"`. Chunk D badge map keyed on the underscore form.
2. **`unmatched` is `HealthKitUnmatched[]`** (objects), not `[String]`. Chunk B uses a struct.
3. **`hr_zone_seconds` is a `dict[str,int]` / `[String:Int]`** on both request and response (not a fixed 5-key struct), to match backend storage and Chunk D's data-driven bar.
4. **`is_strength` added to the request** (Chunk A recommendation) — client declares; Chunk B/C send it.
5. **`WorkoutSummary` gains `avg/peak_heart_rate` + `hr_source`** (Chunk A scope) — required by Chunk D History-row rendering.
6. **`_build_workout_response` HR-population fix is Chunk A scope** — without it sets/sessions never return HR.
7. **`WhoopStatusResponse` + `getWhoopStatus()` belong to Chunk B** (Chunk C consumes them).
8. **Open — `hr_zone_time` quest unit** (seconds vs minutes for `target_value`/`progress`): Chunk A to confirm; Chunk D formats accordingly. Tracked in the Amendment Log if it forces a copy change.

---

## Dependency graph & sequencing

```
        ┌──────────────────────────────────────────────────────────────┐
        │ Stage 0 (DONE): HR foundation + WHOOP API, 306 tests ✅        │
        └───────────────────────────────┬──────────────────────────────┘
                                         │ heart_rate_service, workout_stats,
                                         │ quest_service, session/set HR fields,
                                         │ alembic head `add_whoop_connections`
                                         ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │ CHUNK A — backend ingest  POST /workouts/import-healthkit  (1.7a)        │
   │ no Xcode · independently deployable · gate: pytest + ruff               │
   │ CONFIRMS THE CONTRACT REGISTRY · adds migration #3 (off whoop head)     │
   └───────────────────────────┬────────────────────────────────────────────┘
                               │ Registry confirmed (request/response + HR fields)
                               ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │ CHUNK B — iOS API plumbing  (APITypes.swift mirrors A · APIClient call)  │
   │ gate: xcodegen + xcodebuild + lint-entitlements                          │
   └───────────────────────────┬────────────────────────────────────────────┘
                               │ typed structs + import() client method
                ┌──────────────┴───────────────┐
                ▼                               ▼
   ┌───────────────────────────────┐  ┌──────────────────────────────────────┐
   │ CHUNK C — HealthKit read +    │  │ CHUNK D — HR display (1B)             │
   │ foreground auto-sync +        │  │ HRZoneBar, StatCards, provenance      │
   │ settings rows + WHOOP stub    │  │ badges, per-set HR column, quest icons│
   │ gate: build + entitlements    │  │ gate: build                           │
   │ needs A live + DEVICE          │  │ needs A's fields + B's structs        │
   └───────────────────────────────┘  └──────────────────────────────────────┘
```

**Hard dependencies:** A → B (B can't mirror non-existent structs); B → C and B → D (both consume B's
types); A → C at runtime (C calls A's live endpoint; can be *coded* against the Registry before A deploys,
but on-device acceptance needs A on Railway).

**Parallelizable:** within A (schemas + handler + reuse-wiring together; tests last); C and D are
independent of each other once B lands (prefer C alone — it's the longer one — then D); within D the
`HRZoneBar`/`StatCard`s/badge helper/quest icons are independent SwiftUI pieces.

**Session boundaries:** clean cuts are *between* chunks (each ≈ one session, ends at a green gate + commit).

**Environment:** Chunk A is independently deployable/testable with **no Xcode** (ship + smoke-test via
curl before iOS work). Chunks C and D need a **real iPhone + Apple Watch** for full verification — the
**Simulator has no HealthKit workout/HR data**, so the build/lint gates are compile-only; functional
acceptance is on-device (`importNewWorkouts()` returns empty on Simulator — expected, not a bug).

---

# Build chunks

## Chunk A — Backend HealthKit ingest (1.7a)

- **Status:** Done (2026-06-21, `304511f`; QA fixes `9b49409`)
- **Depends on:** nothing (first chunk). Builds on shipped Phase 0 (`add_wearable_hr`) + Phase 1 WHOOP (`add_whoop_connections`).

> **Build-note (2026-06-21, `304511f`):** Built by a 4-agent parallel team (data layer / service / API / tests). All tasks landed as specified — `schemas/healthkit.py`, `services/healthkit_service.py`, `hk_uuid` column + `add_healthkit_uuid` migration (single head, confirmed via `alembic heads`), the `POST /workouts/import-healthkit` route, the `_build_workout_response` HR-population fix, and `WorkoutSummary` HR fields. **Gate green:** `319 passed` (306 existing + 13 new), `ruff check` clean, single alembic head. Two integration bugs were found + fixed during verification (see Amendment Log 2026-06-21 rows): (1) a real shared-code bug in `heart_rate_service._aware` (normalized aware datetimes to system-LOCAL, not UTC, breaking per-set attribution on non-UTC hosts like this dev Mac — Railway is UTC so it was latent); (2) a test used an unrealistic `activity_type` (`"Outdoor Run"`, fuzz-score 60 < 70) — corrected to the canonical client string `"running"`. **Independent `/evaluate` pass** (fresh agent, generator-evaluator separation) then found a real defect the 13 tests missed — fixed in `9b49409` (see Amendment Log 2026-06-21): two strength HKWorkouts overlapping one logged session in a batch clobbered the session's `hk_uuid` (lost dedup key → duplicate HR samples on re-import). Now one-session-↔-one-workout per batch; +1 regression test (320 total pass). Also logged the swallowed import exception + minor type-hint/naming cleanups. Verdict after fix: ship-ready. **Not yet deployed to Railway** (see Cross-cutting deployment note — deploy deliberately).
- **Goal:** Add authenticated `POST /workouts/import-healthkit` that accepts a batch of completed
  Apple-Watch `HKWorkout`s + raw HR samples, dedups by HealthKit UUID, routes cardio/runs into synthetic
  `WorkoutSession`s (reusing the screenshot activity→exercise matcher) and strength into existing logged
  sessions by time-overlap (reusing the WHOOP matcher + Phase-0 per-set window attribution), and
  idempotently re-credits HR quests. **Also fixes `_build_workout_response` so HR fields actually return.**

### Canonical contract
See the **[Contract Registry](#contract-registry)** §1–§3 (request, response, response HR fields). On first
build, **confirm each table against the built Pydantic** and the Reconciliation notes; if anything
differs, amend the Registry + bump version. New schemas live in **`app/schemas/healthkit.py`**
(`HealthKitWorkout`, `HealthKitImportRequest`, `HealthKitUnmatched`, `HealthKitImportResponse`), importing
`HeartRateSampleCreate` from `app/schemas/workout.py`.

> **CRITICAL GAP (must fix in Chunk A).** `_build_workout_response` (`app/api/workouts.py:774–821`) builds
> `SetResponse` **without** `start_time/end_time/avg_heart_rate/peak_heart_rate` and `WorkoutResponse`
> **without** the six session HR fields — so although the schema fields exist, no GET returns them today.
> Wire these through, or the whole feature (and existing WHOOP/Watch HR) is invisible to the app.

### Files (create / change)
- **Create** `backend/app/schemas/healthkit.py` — the four schemas above.
- **Create** `backend/app/services/healthkit_service.py` — `import_healthkit_workouts(db, user_id, workouts) -> dict`
  (dedup, cardio/strength routing, reuse-wiring, per-day quest recalc). Keeps the endpoint thin.
- **Change** `backend/app/api/workouts.py` — add `POST /import-healthkit` (final path `/workouts/import-healthkit`
  under the existing prefix); **fix `_build_workout_response`** to populate set + session HR.
- **Change** `backend/app/schemas/workout.py` — add `avg_heart_rate`, `peak_heart_rate`, `hr_source` to
  `WorkoutSummary` (it already has `strain`); confirm the summary builder emits them.
- **Change** `backend/app/models/workout.py` — add `hk_uuid = Column(String, nullable=True, index=True)` to
  `WorkoutSession` + a partial-unique index on `(user_id, hk_uuid)` (mirror the existing `client_id` pattern, ~lines 44/87–95).
- **Create** `backend/alembic/versions/add_healthkit_uuid.py` — `down_revision = 'add_whoop_connections'`.
- **Create** `backend/tests/test_healthkit_service.py` — unit + e2e (pattern: `tests/test_whoop_service.py`).
- **Optional refactor** lift `whoop_service._find_matching_session` / `_session_window` / `_overlap_seconds`
  into `app/services/session_matching.py` shared by whoop + healthkit (default: import them; refactor only if clean).

> Router already registered (`main.py:388`, prefix `/workouts`) — no `main.py` change.

### Data model + migration
- **`hk_uuid` lives as a nullable `String` column on `WorkoutSession`** (not a separate table): the dedup
  target *is* a session (cardio creates one; strength backfills one), and it mirrors the `client_id`
  precedent exactly. Strength backfill writes `hk_uuid` onto the matched existing session.
- **Migration** `add_healthkit_uuid.py`: `revision='add_healthkit_uuid'`, `down_revision='add_whoop_connections'`.
  **upgrade:** `add_column('workout_sessions', Column('hk_uuid', String(), nullable=True))` + partial unique
  index `ix_workout_sessions_user_hk_uuid_unique` on `(user_id, hk_uuid)` with
  `postgresql_where=text('hk_uuid IS NOT NULL')` (multiple NULLs distinct in PG; SQLite tests ignore the
  `postgresql_where` and keep the column plain-nullable so `create_all` stays valid). **downgrade:** drop
  index then column. Mirror the index in the model `__table_args__`. Confirm `alembic heads` → single head
  `add_healthkit_uuid` after.

### Step-by-step tasks
1. **Schemas** — create `app/schemas/healthkit.py`; copy `WorkoutCreate.parse_date` (`workout.py:107–124`) as
   the `start`/`end` `field_validator(mode="before")`; model-validate `end >= start`; reuse `HeartRateSampleCreate`.
2. **Model + migration** — add `hk_uuid` column + partial-unique index; write the migration chained off `add_whoop_connections`.
3. **Service skeleton** — `import_healthkit_workouts(db, user_id, workouts)`; the **endpoint** owns the final
   `db.commit()` (match `whoop_service.sync_recent_workouts` flush/commit split, `whoop.py:108`).
4. **Dedup (idempotency)** — load existing `hk_uuid`s for the user up front; any incoming (or intra-batch
   duplicate) `hk_uuid ∈ known` → `skipped_duplicates`, skip.
5. **Route** — `is_strength == True` → strength path (task 7); else cardio path (task 6).
6. **Cardio/run → synthetic session** — reuse `screenshot_service.match_activity_to_exercise(db, activity_type, threshold=70)`
   (`screenshot_service.py:255` — **actual name has no leading underscore**; strips "Indoor/Outdoor/Pool/Open Water "
   prefixes, fuzzy-matches Sport/Cardio/Flexibility/Strength, resolves aliases). Build the session **inline**
   (mirror `save_whoop_activity` body, ~`screenshot_service.py:1010–1066/1156–1177`, but do NOT call that
   function — it drags in DailyActivity/XP/PR writes): `WorkoutSession(user_id, date=start(naive-UTC),
   duration_minutes=round(duration_seconds/60), hk_uuid, avg/peak HR, kilojoules, hr_zone_seconds,
   hr_source="apple_watch", notes=f"{activity_type} - Apple Watch")`; `db.flush()`; if matched, add one
   `WorkoutExercise(order_index=0)` (no sets); append id to `sessions_created`.
7. **Strength → match existing session by overlap** — reuse `whoop_service._find_matching_session` /
   `_session_window` / `_overlap_seconds` (`whoop_service.py:323–356`). Load candidate sessions in a padded
   window around the batch (mirror `whoop_service.py:420–431`); pass `ensure_utc(start/end)` (aware) into the
   matcher. On match: set `session.hk_uuid`; backfill HR **non-destructively** (only fill empty
   `avg/peak/kilojoules/hr_zone_seconds`, set `hr_source` if None) like `apply_whoop_summary`
   (`whoop_service.py:359–397`); append to `sessions_updated`. On no match: append
   `{hk_uuid, activity_type, start, end}` to `unmatched` and **skip** (do not create an empty strength session;
   do **not** consume the `hk_uuid` so a later import can attach once the lift is logged).
8. **Per-set HR (strength)** — after a match with `heart_rate_samples`, **re-query the session with
   `joinedload` (exercises→sets) before** calling the service (CLAUDE.md joinedload rule), then
   `heart_rate_service.ingest_heart_rate(db, session, samples, source="apple_watch")` (`:31`) — persists
   `HeartRateSample`s, attributes each to a set by `[start_time, end_time]` window, rolls up per-set + session
   avg/peak (non-clobbering). Cardio sessions (no sets) may still call it to persist raw samples (all `set_id=None`).
9. **Idempotent quest recalc (per affected day)** — collect local dates of all created/updated sessions; for
   each, fetch unclaimed `UserQuest`s for that day and call
   `quest_service.recalculate_quest_progress(db, user_id, unclaimed, day)` (`:298`) — re-reads the day's
   workouts, idempotent. Extend `quests_completed` (dedupe). HealthKit carries no `strain` → `session_strain`
   quests won't credit from Watch (expected).
10. **Endpoint** — `@router.post("/import-healthkit", response_model=HealthKitImportResponse)` with
    `get_current_user` + `get_db`; call the service; `db.commit()`; on error `db.rollback()` + `HTTPException`
    (mirror `whoop.py:106–122`). Bound `workouts` `max_length`.
11. **Fix `_build_workout_response`** (`:774–821`) — populate set `start_time/end_time/avg/peak HR` (via
    `to_iso8601_utc`) and session `avg/peak HR, strain, kilojoules, hr_zone_seconds, hr_source`. Also confirm
    the `WorkoutSummary` builder emits the three new summary HR fields.
12. **Gate** — run below; confirm single alembic head.

### Acceptance criteria
- Auth required (401 without bearer). Cardio (`is_strength=false`) creates one session, `hr_source="apple_watch"`,
  zones stored verbatim, linked to the canonical run exercise, id in `sessions_created`.
- Re-POSTing the same batch → all `hk_uuid`s in `skipped_duplicates`, nothing created/updated (idempotent).
- Strength overlapping a logged session sets `hk_uuid`, backfills only empty HR, attributes samples to sets
  (per-set avg/peak populated), id in `sessions_updated`.
- Strength with no overlap → in `unmatched`, nothing created, `hk_uuid` not consumed.
- An `hr_zone_time`/`peak_hr` quest assigned that day flips `is_completed=True`, id in `quests_completed`;
  recalc for an empty day returns `[]`.
- `GET /workouts/{id}` after import returns session + set HR fields (proves the `_build_workout_response` fix).
- `alembic upgrade head` clean; `alembic heads` single = `add_healthkit_uuid`; downgrade reverts.
- All datetime comparisons naive/aware-safe (`ensure_utc`) — no Postgres `TypeError`.

### Test / build gate
```bash
cd backend
./venv/bin/python -m pytest -q                          # 306 existing must stay green
./venv/bin/python -m pytest -q tests/test_healthkit_service.py
ruff check app/ tests/
./venv/bin/alembic upgrade head && ./venv/bin/alembic heads   # expect single head: add_healthkit_uuid
```
Use **`backend/venv`** (per memory: system 3.9 can't import the app; 3.13 needs test-only pins). New tests
(mirror `test_whoop_service.py`): `TestDedup` (known uuid skip; intra-batch dup), `TestCardioImport`
(run→Running exercise + zones verbatim; unknown activity → exerciseless session), `TestStrengthImport`
(overlap match + non-destructive backfill; per-set attribution; no-match→unmatched & uuid not consumed),
`TestQuestRecredit` (e2e zone quest credited), `TestEndpoint` (requires auth; round-trip returns HR; GET returns HR).

### Risks / open questions
- **Unmatched strength = skip + report (v1).** No ghost session (would pollute history/quests with 0 volume);
  leaving the `hk_uuid` unconsumed lets a re-import attach later. Client surfaces it as "log the workout first."
- **`is_strength` flag vs inference** — explicit flag chosen (Apple labels like "HIIT"/"Cross Training" are
  ambiguous). Fallback if vetoed: strength iff matched exercise category ∈ {Strength, Functional Strength Training}.
  **Material — Chunk B/C must send it.**
- **Reuse scope** — `match_activity_to_exercise` is a clean standalone (import as-is). The cardio-session
  builder is embedded in `save_whoop_activity` + tangled with DailyActivity/XP — **build inline (~20 lines)**.
  Overlap matchers are private in `whoop_service` — importing works but lifting to `session_matching.py` is cleaner.
- **Naive/aware on Postgres** — DB stores **naive UTC**; matchers use **aware** (`ensure_utc`); `ingest_heart_rate`
  normalizes samples to naive. Store new `session.date` naive-UTC (`ensure_utc(start).replace(tzinfo=None)`) so
  quest day-bucketing (`quest_service.py:42–55`) files it correctly. Add a test asserting an aware start lands in the right day.
- **`hr_zone_time` quest unit** — confirm `target_value`/`progress` unit (seconds vs minutes); record in the
  Amendment Log if Chunk D copy must change.
- **Batch partial failure** — recommend all-or-nothing transaction for v1 + bounded `max_length`.

### Possible downstream impact
- **B:** mirrors request/response field-for-field; must send `is_strength`; `unmatched` is objects; handle
  `unmatched` (show "log first") vs `skipped_duplicates` (silent) distinctly.
- **C:** v1 has **no server-side import cursor** (client tracks via local dedup) → C stays thin; a "last
  HealthKit sync" surface would need new state (material).
- **D:** depends on the `_build_workout_response` fix + the `WorkoutSummary` HR additions; if A defers either,
  D sees nulls. Strain never comes from Watch → D copy must not promise strain for Apple Watch.

---

## Chunk B — iOS API plumbing

- **Status:** Done (2026-06-21, `00c0cdc`)
- **Depends on:** Chunk A (confirmed contract).

> **Build-note (2026-06-21, `00c0cdc`):** Implemented exactly as specced against the **CONFIRMED v1**
> Contract Registry — no contract changes, so **no Amendment Protocol / Log row** was needed. Verified
> the decoder still has `keyDecodingStrategy = .convertFromSnakeCase` commented out (`APIClient.swift:838–841`)
> and the encoder is a plain `JSONEncoder()` (`:810`), so every new field carries an explicit snake_case
> `CodingKey`. **`APITypes.swift`:** added `HealthKitHRSample`/`HealthKitWorkoutImport`/`HealthKitImportRequest`
> (Encodable) + `HealthKitUnmatched`/`HealthKitImportResponse`/`WhoopStatusResponse` (Decodable), verbatim from
> the spec (`unmatched: [HealthKitUnmatched]` objects; `hrZoneSeconds: [String:Int]?`; `isStrength: Bool`).
> Additive optional HR fields (additive-only, missing keys → nil): `WorkoutResponse` += `avg/peakHeartRate`,
> `hrZoneSeconds`, `kilojoules`, `hrSource`, `hkUuid`; `WorkoutSummaryResponse` += `avg/peakHeartRate`, `hrSource`;
> `SetResponse` += `startTime`, `endTime`, `avg/peakHeartRate`. **`APIClient.swift`:** added a `// MARK: - HealthKit
> Workout Import` section after Activity (`:514`) with `importHealthKitWorkouts(_:)` → `post("/workouts/import-healthkit")`
> and `getWhoopStatus()` → `get("/whoop/status")` (routes through the private `request(...)` → Bearer/401-refresh/`APIError`).
> No view code touches these yet; no `project.yml`/entitlement change; no new files (xcodegen auto-includes — pbxproj untracked, no churn).
> **Gate green:** `xcodegen generate` clean; `xcodebuild … build` → `** BUILD SUCCEEDED **`, `grep "error:"` empty;
> `scripts/lint-entitlements.sh` → "All checks passed" (no Apple Pay, no background-delivery). **Contract proof:**
> a standalone `swift` decode/encode harness (exact struct copies) ran **19/19 green** — full + empty
> `HealthKitImportResponse` decode, `unmatched` as objects, `WhoopStatusResponse`, `WorkoutResponse`/`SetResponse`
> **with** new keys decode, **legacy** `WorkoutResponse`/`SetResponse` JSON **without** the new keys still decode
> (all HR → nil, no throw), `hr_source == "apple_watch"` (underscore), and `HealthKitImportRequest` encodes
> snake_case with the nil `distance_meters` optional **omitted** and no camelCase leakage. Two SourceKit
> diagnostics seen mid-edit (`parseISO8601Date` "no member", `UIKit` "no such module") were cross-file
> indexing false positives — the authoritative `xcodebuild` is clean. **Downstream unblocked:** C (request
> types + `importHealthKitWorkouts` + `getWhoopStatus`) and D (HR fields decode on the workout/set structs).
- **Goal:** Add the Swift request/response types for the import endpoint to `APITypes.swift`, an
  `importHealthKitWorkouts(...)` method to `APIClient` mirroring the existing JSON POST, the
  `WhoopStatusResponse` + `getWhoopStatus()` the stub row needs, and backward-compatible optional HR fields
  on the existing workout response structs so Chunk D can render HR without breaking current decode.

### Contract types (add to `APITypes.swift`)
The decoder does **not** auto-convert snake_case (`APIClient.swift:838–841` is commented out) — **every
field needs an explicit `CodingKey`**, and every backend-omittable field is `Optional` so a lean payload
never throws.

```swift
// MARK: - HealthKit Workout Import
struct HealthKitHRSample: Encodable { let timestamp: String; let bpm: Int }   // ISO8601 UTC + fractional

struct HealthKitWorkoutImport: Encodable {
    let hkUuid: String
    let activityType: String
    let isStrength: Bool
    let start: String                 // ISO8601 UTC w/ fractional seconds
    let end: String
    let durationSeconds: Int
    let kilojoules: Double?
    let avgHeartRate: Int?
    let peakHeartRate: Int?
    let hrZoneSeconds: [String: Int]? // dict, matches backend storage; nil if age unknown
    let heartRateSamples: [HealthKitHRSample]?
    let distanceMeters: Double?       // deferred v1 — send nil
    enum CodingKeys: String, CodingKey {
        case start, end, kilojoules
        case hkUuid = "hk_uuid"; case activityType = "activity_type"; case isStrength = "is_strength"
        case durationSeconds = "duration_seconds"; case avgHeartRate = "avg_heart_rate"
        case peakHeartRate = "peak_heart_rate"; case hrZoneSeconds = "hr_zone_seconds"
        case heartRateSamples = "heart_rate_samples"; case distanceMeters = "distance_meters"
    }
}
struct HealthKitImportRequest: Encodable { let workouts: [HealthKitWorkoutImport] }

struct HealthKitUnmatched: Decodable {
    let hkUuid: String; let activityType: String; let start: String; let end: String
    enum CodingKeys: String, CodingKey { case start, end; case hkUuid = "hk_uuid"; case activityType = "activity_type" }
}
struct HealthKitImportResponse: Decodable {
    let imported: [String]; let skippedDuplicates: [String]
    let sessionsCreated: [String]; let sessionsUpdated: [String]
    let unmatched: [HealthKitUnmatched]; let questsCompleted: [String]
    enum CodingKeys: String, CodingKey {
        case imported, unmatched
        case skippedDuplicates = "skipped_duplicates"; case sessionsCreated = "sessions_created"
        case sessionsUpdated = "sessions_updated"; case questsCompleted = "quests_completed"
    }
}

// MARK: - WHOOP status (for the disabled "coming soon" row in Chunk C)
struct WhoopStatusResponse: Decodable { let connected: Bool; let configured: Bool }
```

**Additive optional HR fields** (additive-only; missing keys → nil, cannot break existing decode):
- `WorkoutResponse` += `avgHeartRate: Int?`, `peakHeartRate: Int?`, `hrZoneSeconds: [String:Int]?`,
  `kilojoules: Double?`, `hrSource: String?`, `hkUuid: String?` (+ CodingKeys).
- `WorkoutSummaryResponse` += `avgHeartRate: Int?`, `peakHeartRate: Int?`, `hrSource: String?` (+ CodingKeys).
- `SetResponse` += `startTime: String?`, `endTime: String?`, `avgHeartRate: Int?`, `peakHeartRate: Int?` (+ CodingKeys).

### Files (create / change)
- `ios/FitnessApp/Services/APITypes.swift` — the structs above + the additive HR fields.
- `ios/FitnessApp/Services/APIClient.swift` — `importHealthKitWorkouts(_:)` + `getWhoopStatus()` in a new
  `// MARK: - HealthKit Workout Import` section (~after the Activity section, line ~515).

### Step-by-step tasks
1. Add the HealthKit + WhoopStatus structs to `APITypes.swift` exactly as above.
2. Add the optional HR fields + CodingKeys to `WorkoutResponse`, `WorkoutSummaryResponse`, `SetResponse`
   (additive only — do not reorder/remove existing keys).
3. Add to `APIClient.swift`:
   ```swift
   func importHealthKitWorkouts(_ workouts: [HealthKitWorkoutImport]) async throws -> HealthKitImportResponse {
       try await post("/workouts/import-healthkit", body: HealthKitImportRequest(workouts: workouts))
   }
   func getWhoopStatus() async throws -> WhoopStatusResponse { try await get("/whoop/status") }
   ```
   (Routes through the private `request(...)` → Bearer auth, 401→refresh→retry, `APIError` mapping.)
4. Build-verify (gate). No view code touches these yet.

### Acceptance criteria
- Compiles after `xcodegen generate` + `xcodebuild … build`, **no `error:` lines**.
- `HealthKitImportResponse`/`HealthKitUnmatched`/`WhoopStatusResponse` decode sample backend JSON; empty arrays decode.
- Existing `WorkoutResponse`/`WorkoutSummaryResponse`/`SetResponse` JSON **without** the new keys still decodes (→ nil).
- `HealthKitImportRequest` encodes snake_case; nil optionals omitted (backend treats absent as missing).

### Test / build gate
```bash
cd ios && xcodegen generate
xcodebuild -project FitnessApp.xcodeproj -scheme FitnessApp \
  -destination 'generic/platform=iOS Simulator' build 2>&1 | grep "error:"   # expect empty
bash scripts/lint-entitlements.sh                                            # expect pass; no new entitlements
```

### Risks / open questions
- **CodingKeys** — no auto snake_case; a missing key silently nils (optional) or throws (non-optional). Double-check each.
- **Date formatting** — `start`/`end`/`timestamp` must be ISO8601 **UTC + fractional seconds** to match the
  read-back parser `parseISO8601Date()` (`Extensions.swift:508`). Chunk C uses
  `ISO8601DateFormatter([.withInternetDateTime,.withFractionalSeconds])` in UTC. Confirm backend accepts `Z` + fractional.
- **Request timeout** — shared `request(...)` uses 10s; a big first-run batch × samples may exceed it →
  Chunk C should chunk the batch rather than raise the global timeout.

### Possible downstream impact
- A field rename in Chunk A ripples to one construction site in Chunk C; update names/CodingKeys/types here.
- `hrSource` on the workout structs is the provenance hook Chunk D relies on — if backend names it differently, reconcile here.

---

## Chunk C — iOS HealthKit read + foreground auto-sync + settings rows

- **Status:** Not started
- **Depends on:** Chunk B (request types + `APIClient.importHealthKitWorkouts` + `getWhoopStatus`).
- **Goal:** Extend `HealthKitManager` to read completed `HKWorkout`s + raw HR samples, compute zones from
  `220−age`, dedup by `hk_uuid`, and POST; wire **one** global `scenePhase → .active` observer (debounced)
  that silently auto-imports new workouts on every foreground; add the distinct "Apple Health — Workouts & HR"
  settings surface (+ manual "Import now" fallback) and the disabled "Connect WHOOP — coming soon" row.

### Files (create / change)
- `ios/FitnessApp/Services/HealthKitManager.swift` — **change**: enlarge `readTypes` + auth; add
  `importNewWorkouts()`.
- `ios/FitnessApp/Services/WorkoutImportStore.swift` — **create**: UserDefaults-backed `lastWorkoutImportDate`
  + imported `hk_uuid` set (capped). Keeps dedup state out of the SwiftData schema.
- `ios/FitnessApp/Services/SyncCoordinator.swift` — **create**: `@MainActor ObservableObject` owning
  `syncOnForeground()` (debounce + concurrency guard), funneling foreground work so it doesn't fight the
  existing daily activity sync.
- `ios/FitnessApp/FitnessApp.swift` — **change**: own the single global `@Environment(\.scenePhase)` observer
  at `WindowGroup`, call `SyncCoordinator.shared.syncOnForeground()` on `.active`.
- `ios/FitnessApp/Views/Profile/ProfileView.swift` — **change**: add the two new rows in `SystemSettingsSection` (~1147).
- `ios/FitnessApp/Views/Profile/AppleHealthWorkoutSettingsView.swift` — **create**: detail screen + state machine + "Import now".
- `ios/FitnessApp/Services/WhoopConnectionViewModel.swift` — **create** (stub): loads `getWhoopStatus()` → `configured`.

**No `project.yml`/entitlements changes.** HealthKit entitlement + `NSHealthShareUsageDescription` already
exist; `.heartRate`/`workoutType()` are read-only additions covered by the existing usage string. **Do NOT**
add HealthKit background-delivery / any background mode. **No Apple Pay entitlement, ever.** (Files dropped
under `FitnessApp/` are auto-included by `xcodegen` — no manual pbxproj edits.)

### Step-by-step tasks
1. **Read-types + auth** — add `HKObjectType.workoutType()` + `.heartRate` (and best-effort `.restingHeartRate`,
   `.heartRateVariabilitySDNN`) to `readTypes` (`HealthKitManager.swift:27–45`). `requestAuthorization()` (`:55`)
   unchanged — the enlarged set means the **single** Apple Health sheet now covers steps/calories + workouts/HR
   (permission asked once). Note: read denials are hidden by HealthKit, so `isAuthorized` only means "sheet shown
   without error" — the import path must tolerate empty results as a no-op, not an error.
2. **Query + build request** — read cursor from `WorkoutImportStore.lastWorkoutImportDate` (default 30 days ago
   first run). `HKSampleQuery(.workoutType(), predicateForSamples(withStart:end:options:.strictStartDate))` →
   `[HKWorkout]` (wrap in `withCheckedContinuation` like the existing `fetchStandHours`, `:246`). Per workout:
   second `HKSampleQuery(.heartRate, predicateForObjects(from: workout))` → bpm via
   `quantity.doubleValue(for: .count()/.minute())`, timestamp `sample.startDate`; compute mean/max → avg/peak;
   **decimate to ~1 sample / 5s** (cap ~720) so set boundaries stay sliceable. Energy via
   `workout.statistics(for: .activeEnergyBurned)` kcal → **kJ ×4.184**. Map `HKWorkoutActivityType` →
   `activity_type` string (lock the vocabulary against Chunk A): `traditional/functionalStrengthTraining →
   "strength_training"`, `running → "running"`, `walking/cycling/hiit/coreTraining/yoga/rowing/elliptical → …`,
   else `"other"`; set `isStrength` from the activity type.
   > **Amended 2026-06-21 (from Chunk A):** the backend cardio matcher (`match_activity_to_exercise`) fuzz-matches `activity_type` (≥70) against seeded Sport/Cardio exercise **names**. Emit strings that score ≥70 vs a seeded name — `"running"`→"Running"=100 ✓; avoid short/partial labels like `"Outdoor Run"`→"Run"=60 ✗ (creates an exerciseless session). Cardio types without a seeded exercise (e.g. `"hiit"`, `"elliptical"`) still create a session, just unlinked — fine. Confirm the seeded Sport/Cardio names cover what you emit.

   Compute `hrZoneSeconds` from `220−age` (walk
   consecutive samples, attribute inter-sample interval to the earlier sample's zone); **nil the field if age
   unknown**. Build `HealthKitWorkoutImport` (`hkUuid = workout.uuid.uuidString`, ISO8601-UTC-fractional
   start/end via a cached formatter, `durationSeconds = Int(workout.duration)`, `distanceMeters = nil`).
   **Dedup/persist via `WorkoutImportStore` (UserDefaults, not SwiftData)**: filter out workouts whose uuid is
   already sent; after a successful POST, union `imported + skipped_duplicates` into the set and advance the
   cursor. Backend is idempotent so a missed local dedup is harmless. Signature:
   `@discardableResult func importNewWorkouts(age: Int?) async -> HealthKitImportResponse?` (guard
   `isHealthDataAvailable` + `isAuthorized`; use a dedicated `isImportingWorkouts` flag, NOT the daily `isSyncing`).
3. **Foreground auto-import (headline UX)** — add the **single** global observer in `FitnessApp.swift` at the
   `WindowGroup` content (today there's none; LogView's local scenePhase at `:333` is a different concern —
   leave it):
   ```swift
   .onChange(of: scenePhase) { _, phase in
       if phase == .active { Task { await SyncCoordinator.shared.syncOnForeground() } }
   }
   ```
   `SyncCoordinator.syncOnForeground()`: guard `AuthManager.shared.isAuthenticated` + `isHealthDataAvailable`;
   **debounce** (skip if last foreground sync < 5 min ago); **concurrency guard** (`isRunning` + `defer`); call
   `HealthKitManager.shared.importNewWorkouts(age:)` **silently** (no toast/alert/notification); set
   `lastForegroundSyncAt`. Coexistence: keep the existing daily `syncTodayOnly()` (`/activity`) where it is;
   use a **separate** import flag so the two don't block each other. Do **not** auto-prompt HealthKit from the
   silent path — prompt only from the settings "Connect Apple Health" action.
4. **Settings UI** — disambiguate from the existing "Health Sync · CONNECTED" daily row (`:1147–1162`,
   `heart.fill`/`warningRed`):
   - **New row** after it (+ `AriseDivider()`): `AriseSettingsRow(icon: "figure.run", iconColor: .systemPrimary,
     title: "Apple Health — Workouts & HR")` as a `NavigationLink { AppleHealthWorkoutSettingsView() }` with a
     trailing chevron + compact status pill. Different glyph (run vs heart) + color (cyan vs red) + title scope.
   - **`AppleHealthWorkoutSettingsView`** — state machine: `.notAvailable` (iPad), `.notAuthorized`
     ("Connect Apple Health" → `requestAuthorization()` then first import), `.idle` (last-imported + "Import now"),
     `.importing` (ProgressView), `.lastImported(summary)` (counts from the response — the ONE place results
     surface; foreground path stays silent), `.error` (note read denials surface as "No new workouts found",
     not failure). Use `VoidBackground`, `AriseSectionHeader`, `AriseSettingsRow`.
   - **Disabled "Connect WHOOP — coming soon" row** — `WhoopConnectionViewModel` loads `getWhoopStatus()`;
     render `AriseSettingsRow(icon: "circle.circle", title: "Connect WHOOP")` with muted title (needs a
     `titleColor` param on `AriseSettingsRow` since it hardcodes `.textPrimary` at `:1216` — add it or wrap),
     trailing `Text("COMING SOON")` pill in `.textMuted`/`voidLight`, whole row `.opacity(0.5)`, **not** a
     Button (non-interactive). Keep disabled for v1 regardless of `configured`.

### Acceptance criteria (device)
- Apple Watch run done → open app cold → new `HKWorkout` imports silently on foreground (no toast). Re-open
  within 5 min → debounce skips; after >5 min → re-checks but uuid is known / returned in `skipped_duplicates`
  → no duplicate. Permission asked **once** (enlarged read set). Two visibly distinct settings rows
  ("Health Sync" red-heart-daily vs "Apple Health — Workouts & HR" cyan-run). "Import now" shows counts.
  "Connect WHOOP" visibly disabled "COMING SOON". Age present → zones populated; age missing → zones nil, import still succeeds.

### Test / build gate
```bash
cd ios && xcodegen generate
xcodebuild -project FitnessApp.xcodeproj -scheme FitnessApp \
  -destination 'generic/platform=iOS Simulator' build 2>&1 | grep "error:"   # expect empty
bash scripts/lint-entitlements.sh                                            # expect pass; no new entitlements
```
**Build-verifiable (Simulator):** compiles; settings rows render; state machine transitions; scenePhase
observer fires; `WhoopStatusResponse` decodes. **Device-only:** real `HKWorkout`/HR reads, the permission
sheet, silent foreground import, dedup. Simulator has no Watch data → `importNewWorkouts()` returns nil/empty
(expected — note in the PR so "0 imported on Simulator" isn't read as a bug).

### Risks / open questions
- **scenePhase double-fire** (cold launch, post-permission-sheet, Control Center) → `isRunning` guard + 5-min debounce absorb it; idempotent endpoint makes a double-call harmless.
- **Auth race** — if the observer fires before first auth, `importNewWorkouts` early-returns (no throw, no surprise sheet).
- **Age source** — `age` lives in `ProfileResponse.age` (`APITypes.swift:46`, via `GET /profile`); `HealthKitManager`
  doesn't hold the profile. **Pass `age` in from the caller** (coordinator/VM loads profile); if nil, **omit
  `hr_zone_seconds`** (send avg/peak only — backend still derives per-set HR from raw samples). Confirm `hr_zone_seconds` optional server-side.
- **Simulator gap** — gate device verification accordingly.
- **Daily-sync interaction** — separate flag from `isSyncing`; distinct `lastWorkoutImportDate` vs daily `lastSyncDate`.
- **Payload size/timeout** — 30-day initial cursor + 5s decimation + consider per-POST workout cap (Chunk B's `request` is 10s).

### Possible downstream impact (Chunk D)
- Imported sessions must carry `hr_source = "apple_watch"` (stamped server-side in Chunk A) so D's cyan
  provenance badge renders. Don't decimate samples below ~5s or D's per-set HR resolution degrades. D surfaces
  `quests_completed` via the next data-load in-place update; this chunk shows no notification of its own.

---

## Chunk D — HR display (1B)

- **Status:** Not started
- **Depends on:** Chunk A (response fields populated, incl. the `_build_workout_response` fix + `WorkoutSummary`
  HR additions) + Chunk B (Swift decodes them). Hard dependency — the iOS models carry **no** HR fields until B
  (`SetResponse:265`, `WorkoutSummaryResponse:190`, `WorkoutResponse:225`, `QuestResponse:848` all lack HR today).
- **Goal:** Surface avg/peak HR, HR-zone time breakdown, strain, and source provenance across Home recent card,
  History row + workout detail, and the per-set table; give the three HR quest types real icons/labels — all in
  the ARISE language. Every HR field is optional; the UI must degrade to today's exact layout when all are nil.

### New components (create — grep first per `{DesignSystem}{DataType}{ComponentType}`)
**`Components/AriseHRZoneBar.swift`** — segmented variant of `AriseProgressBar` (`XPBarView.swift:68`).
```swift
struct AriseHRZoneBar: View {
    let zoneSeconds: [String: Int]   // {"z1":120,...,"z5":30}
    var height: CGFloat = 12
    var showLegend: Bool = true
    var maxHR: Int? = nil
}
```
Fixed cold→hot palette (endpoints locked, never data-driven):

| Key | Label | %MaxHR | Token |
|---|---|---|---|
| `z1` | RECOVERY | 50–60% | `.systemPrimary` (cyan, cold endpoint) |
| `z2` | AEROBIC | 60–70% | `.successGreen` |
| `z3` | TEMPO | 70–80% | `.gold` |
| `z4` | THRESHOLD | 80–90% | `Color(hex:"FF8C42")` (local `hrZ4Orange`) |
| `z5` | MAX | 90–100% | `.warningRed` (hot endpoint, +glow) |

- Iterate a fixed ordered key list `["z1".."z5"]`, include keys present with `value > 0`. **5-zone** data →
  up to 5 segments. **3-zone** data (`low/mid/high` or only `z1/z3/z5`) → 3 segments at fixed endpoints
  (cyan / gold / red) via a parallel `zoneOrder3` + `zoneMeta(for:)` lookup; detect scheme by present keys,
  default 5-key. **Unknown keys dropped** (never a gray mystery segment). Widths ∝ seconds/total; `HStack(spacing:0)`
  of `Rectangle().fill` inside a `RoundedRectangle(cornerRadius:2)` over a `Color.voidLight` track; z5 gets glow.
- **Nil/empty → `EmptyView`** (belt-and-suspenders; callers also guard).
- Legend (when `showLegend`): wrapping row of `[8×8 swatch ● + LABEL + mm:ss]` in `.ariseMono(9,.medium)`,
  `.tracking(0.5)`; only zones with `>0`; `%MaxHR` appended in `.textMuted` if `maxHR` given.

**`Components/AriseSourceBadge.swift`** — replaces the inline orange WHOOP badge (`HistoryView.swift:422–435`).
```swift
struct AriseSourceBadge: View { let source: String?; var compact: Bool = false }
```
Chrome pixel-identical to the existing badge: `HStack` of `Image(systemName:)` + `Text(label)` in
`.ariseMono(compact ? 8 : 9, .semibold)`, `.tracking(0.5)`, color, `.padding`, `.background(color.opacity(0.1))`,
`.cornerRadius(2)`. **Mapping keyed on the canonical `hr_source` strings:**

| `hr_source` | SF Symbol | Color | Label |
|---|---|---|---|
| `"whoop"` | `circle.circle` | `.orange` | `WHOOP` |
| `"apple_watch"` | `applewatch` | `.systemPrimary` (cyan) | `APPLE WATCH` |
| `"screenshot"` | `camera.fill` | `.textMuted` | `SCREENSHOT` |
| `nil` / other | — | — | (no badge → `EmptyView`) |

> **Note:** value is **`"apple_watch"`** (underscore), per the Registry — not `"applewatch"`. The old inline
> badge wrongly used the `applewatch` *glyph* for WHOOP; the new component fixes WHOOP to `circle.circle`.
> **Confirm preferred WHOOP glyph in review.**

**HR-zone tint helper** — `static func hrZoneColor(forHR bpm: Int, maxHR: Int?) -> Color` (on `AriseHRZoneBar`
or in `Utils/Colors.swift`); maxHR nil → absolute bpm thresholds (`<114 z1, <133 z2, <152 z3, <171 z4, else z5`).

### Per-surface changes
**A) Home recent card** (`HomeView.swift`, stat row ~1611–1646) — the row is bespoke mini-stats, not `StatCard`s.
Add a **separate HR section below the row + `AriseDivider()`** (after ~1646, before Notes): gate on a computed
`workout.hasHRData`; `AriseSectionHeader(title:"Biometrics", trailing: AriseSourceBadge(source: workout.hrSource))`;
`HStack` of `StatCard("heart.fill", avg, "AVG BPM", valueColor:.systemPrimary)` + `StatCard(peak, "PEAK BPM",
valueColor:.warningRed, showGlow:true)` + (only if `isWhoopActivity==true`) `StatCard("bolt.fill", strain,
"STRAIN", valueColor:.orange)`; then `if let zones = workout.hrZoneSeconds, !zones.isEmpty { AriseHRZoneBar(zoneSeconds: zones, maxHR: workout.maxHR) }`.
Each `StatCard` independently `if let`; everything nil → byte-identical to today.

**B) History** (`HistoryView.swift`) — (B1) replace the inline WHOOP `HStack` (~422–435) with
`AriseSourceBadge(source: workout.hrSource, compact:true)` (now drives WHOOP/Watch/screenshot from one field).
(B2) leave the existing row strain (gated on `isWhoopActivity`). (B3) workout detail: add a session-level HR
block at the top of the detail scroll, same structure as Home's (StatCards + `AriseHRZoneBar(showLegend:true)`),
header `AriseSectionHeader(title:"Heart Rate", trailing: AriseSourceBadge(...))`, gated on `hasHRData`.

**C) Per-set table** (`HistoryView.swift`, header ~868, rows ~916) — `let showHRCol = exercise.sets.contains
{ $0.avgHeartRate != nil || $0.peakHeartRate != nil }`. Insert an `HR` column (width ~40, between RPE and e1RM)
only when `showHRCol`; let the flexible WEIGHT column absorb the width. Value tinted by
`AriseHRZoneBar.hrZoneColor(forHR:hr, maxHR:nil)`; a missing-set cell shows `"-"` (table's existing nil convention).
Verify no overflow on iPhone SE (drop RPE/HR to 36/36 if tight).

**D) `DailyQuestsCard`** (`questIcon` switch ~88–99) — add `case "hr_zone_time": "\u{2764}\u{FE0F}"` (❤️),
`case "peak_hr": "\u{1F525}"` (🔥), `case "session_strain": "\u{26A1}"` (⚡). 0% still shows gray `0/X`. No
awaiting-sync state, no celebration.

**E) `QuestDetailSheet`** — mirror the three cases in `questEmoji` (~16–24), and add `progressText`/`motivationalText`
formatting cases (~38–48 / ~282–296): `hr_zone_time → "X / Y min"` *(confirm unit with Chunk A)*, `peak_hr → "X / Y bpm"`,
`session_strain → "X / Y strain"`. Gradient bar unchanged.

### HR quest icons/labels — `QuestResponse` gap
Verified `QuestResponse` (`APITypes.swift:848`) carries `questType, progress, targetValue, name, description,
difficulty, xpReward` — enough for icons + copy. **No unit field** → the `hr_zone_time` seconds-vs-minutes
ambiguity can't be resolved client-side; Chunk D hardcodes the assumed unit and **Chunk A confirms** the backend's
`target_value`/`progress` unit (Amendment Log it if it forces a copy change). No new `QuestResponse` fields needed.

### Chunk C settings rows (visual spec) — see Chunk C task 4 for behavior
```
┌──────────────────────────────────────────────┐
│ [♥]  Health Sync              ● CONNECTED     │  existing — red heart, daily
│ ──────────────────────────────────────────── │
│ [🏃] Apple Health — Workouts & HR  ● CONNECTED│  NEW — cyan run glyph
│ ──────────────────────────────────────────── │
│ [◌]  Connect WHOOP            COMING SOON      │  NEW — disabled, gray, opacity .5
└──────────────────────────────────────────────┘
```
Disambiguation = different glyph (run vs heart) + color (cyan vs red) + title scope. WHOOP row: gray
`circle.circle`, muted title (needs `AriseSettingsRow.titleColor`), static `COMING SOON` pill, `.opacity(0.5)`, non-interactive.

### Acceptance criteria
- A workout with HR shows avg+peak `StatCard`s (avg cyan, peak red+glow) + `AriseHRZoneBar` in Home, History
  detail, and (badge+strain) the History row. **Strain only on WHOOP** sessions; absent (not "—") on Apple-Watch.
  Per-set HR column only when ≥1 set has HR; values zone-tinted; missing cells `"-"`. Zone bar 5→3 collapse,
  fixed endpoints, unknown keys dropped, nothing when empty. HR quests show ❤️/🔥/⚡ with normal progress UI.
  Provenance badge correct per `hr_source`; nil → none. **No layout break when all HR nil** (byte-identical to today). Build clean.

### Test / build gate
```bash
cd ios && xcodegen generate
xcodebuild -project FitnessApp.xcodeproj -scheme FitnessApp \
  -destination 'generic/platform=iOS Simulator' build 2>&1 | grep "error:"   # expect empty
bash scripts/lint-entitlements.sh                                            # display-only; no new entitlements
```
Manual: render a WHOOP workout (all HR), an Apple-Watch workout (no strain), a screenshot workout, and a legacy
gym workout (all HR nil) — confirm the four surfaces + nil-degradation.

### Risks / open questions
- **Zone-key mismatch** — confirm Chunk A's exact keys (`z1..z5` vs `low/mid/high`); unexpected scheme silently drops segments.
- **`hr_zone_time` unit gap** — hardcoded assumption must match Chunk A.
- **Set-table width on iPhone SE** — HR column only when present; WEIGHT absorbs; shrink RPE/HR if tight.
- **Zone palette accessibility** — z3 gold + z4 orange adjacent; always pair swatch with label; spatial order carries meaning.
- **`AriseSettingsRow` title color** hardcodes `.textPrimary` (`:1216`) — add `titleColor` param for the disabled WHOOP row.

### Possible downstream impact
Last chunk — none downstream. Upstream coupling: any rename of zone keys / `hr_source` / the HR field names in
A/B, or an `hr_zone_time` unit change, forces a Chunk D edit (the `if let`/`hasHRData` props won't compile, or the
badge/segment mapping breaks).

---

## Amendment Protocol (how to adjust chunks mid-build)

The mechanism that lets a discovery in one chunk's build ripple cleanly into later chunks **without a future
session ever building against a stale assumption.** Builds reveal reality; this protocol captures it once and
propagates it everywhere it matters.

### What counts as a "material change" (must be amended + logged)
A change is **material** if it alters something a later chunk — or an already-done chunk — relies on:
- A **Contract Registry field change** (add/remove/rename/type/optionality) on the import request, the import
  response, or any session/set HR field.
- A **reused backend function not behaving as assumed** (`heart_rate_service` attribution, `screenshot_service`
  matching, `quest_service` recalc invocation).
- A **missing or differently-named field** the plan assumed (`hr_source`, the user's `age`, a zone key like
  `z2`→`zone_2`, `kilojoules`→`energy`, `hk_uuid` location).
- A **renamed zone key / changed zone count or semantics** (affects D's bar + C's on-device computation).
- An **entitlement/capability surprise** (a missing Info.plist usage string; a forbidden entitlement re-added).
- A **dedup/idempotency contract change** (`hk_uuid` uniqueness; `skipped` semantics).
- A **migration head/shape change** (different `down_revision`; a "nullable" column that must be non-null).

**Immaterial** (just build it; no protocol): private helper rename, log message, test-only refactor, SwiftUI
view-internal layout, variable naming, comments. **When unsure, treat it as material** — a log row is cheap; a
fresh session building Chunk C against a wrong contract is not.

### The procedure (part of finishing the current chunk)
1. **(a) Record it in the Amendment Log** — one row.
2. **(b) Update the Contract Registry + every affected downstream chunk *inline*,** each with a dated, greppable note:
   `> **Amended YYYY-MM-DD (from Chunk X):** <what changed and what to do now>.`
   For a contract field, **edit the Registry table and bump `version`.** Edit the actual task text in each
   affected chunk (not just a banner) so a fresh session reads the corrected instruction.
3. **(c) Re-verify already-done chunks if impacted** — flip `Done` → `Done → needs re-verify (YYYY-MM-DD)`, state
   in its build-note what to re-check, re-run its gate.

### Who updates what
- **The session that surfaces the change owns propagating it** — fully, before moving on (a future session has
  no idea it happened except through this doc).
- **The Registry is edited by whoever changes the contract**, regardless of which chunk owns the field.
- **Downstream chunk bodies are edited by the surfacing session**, not their original author.
- **The Amendment Log is append-only** — superseded amendments get a follow-up row, never an edit.

### Worked example
> **During Chunk A**, you discover per-set HR attribution needs the client to send **per-set time boundaries**
> (the watch sample stream alone can't be sliced server-side because a HealthKit import has no set timing). Fix:
> (a) log it; (b) Registry — add `sets:[{order_index,start_time,end_time}]` to the request table, bump v1→v1.1,
> dated note; Chunk B — add a `SetBoundary` struct + field, dated note; Chunk C — update the payload builder to
> derive boundaries from the matched logged sets, dated note; Chunk D — confirm "no change" (you actually checked).
> (c) if B were `Done`, flip to `needs re-verify`, re-run its gate.

### Amendment Log
Append-only. The first row is a **labeled template** (example, not a real change); the log otherwise starts empty.

| Date | Surfaced in | Change | Downstream sections updated | By |
|---|---|---|---|---|
| _2026-06-21_ | _A (TEMPLATE — example, not a real change)_ | _Per-set HR attribution needs client-supplied set boundaries; added `set_boundaries[]` to import request. Registry v1→v1.1._ | _Registry (request table + version); Chunk B (`SetBoundary` struct); Chunk C (payload builder). Chunk D: confirmed no change._ | _Claude (session, sha)_ |
| 2026-06-21 | A | **Shared-code bug:** `heart_rate_service._aware()` did `astimezone(tz=None)` (system-LOCAL) despite a "naive UTC" docstring, so aware-UTC samples landed outside set windows on non-UTC hosts → per-set HR never attributed. Fixed to `astimezone(timezone.utc).replace(tzinfo=None)`. **No contract change.** Also fixes the existing Apple-Watch live-session per-set path. | None to contracts. Noted here because it's a reused function that behaved differently than assumed. Re-verified full suite (319 pass). | Claude (304511f) |
| 2026-06-21 | A | **Contract clarification for Chunk C:** the matcher `match_activity_to_exercise` fuzz-matches `activity_type` (≥70) against seeded Sport/Cardio exercise **names**. The iOS `HKWorkoutActivityType → activity_type` map (Chunk C task 2) MUST emit strings that score ≥70 vs a seeded exercise name (e.g. `"running"`→"Running"=100). Short/partial labels like `"Outdoor Run"`→"Run" score 60 and won't link. | Chunk C task 2 (dated note added). No Registry change. | Claude (304511f) |
| 2026-06-21 | A (`/evaluate`) | **Dedup-clobber bug fixed:** two strength HKWorkouts overlapping one logged session in a single batch overwrote the session's `hk_uuid` (lost a dedup key → duplicate `HeartRateSample` rows on re-import) + duplicated `sessions_updated`. Fix: candidate query excludes `hk_uuid IS NOT NULL` sessions; matched sessions are removed from the candidate pool per batch (second overlapping workout → `unmatched`). +regression test. Also: endpoint now logs the swallowed exception; `_local_day`→`_session_day`; `set[date]`/`set[str]` hints. **No contract change.** | `healthkit_service.py`, `api/workouts.py`, `tests/`. No Registry/Chunk B/C/D change. | Claude (9b49409) |

---

## Cross-cutting acceptance & smoke test

**End-to-end v1 acceptance (proves all four chunks add up):**
1. **Apple Watch run → silent foreground import.** Finish a run; open the app; on `.active` (debounced, no tap)
   the `HKWorkout` imports silently — no toast/notification. (C)
2. **Appears with HR + zones.** History/Home show avg/peak `StatCard`s + `AriseHRZoneBar`; `hr_source="apple_watch"`
   → **cyan** badge; **strain absent** (not "—"). (D)
3. **Credits an HR quest.** An active `hr_zone_time`/`peak_hr` quest credits; card updates in place. (A recalc + D icons)
4. **Strength per-set HR backfill.** A logged strength session + overlapping watch HR → per-set avg/peak; the
   set table shows the HR column only when sets carry HR. (A attribution + D conditional column)
5. **Idempotent re-import.** Re-open / re-import skips known `hk_uuid`s — no duplicates. (A dedup)
6. **WHOOP row disabled** — "Connect WHOOP — coming soon", no connect flow. (C stub)
7. **Nil-safe rendering** — partial/no HR renders cleanly, no crashes, no "broken data" placeholders. (D)
8. **Gates green** — backend `pytest -q` + `ruff check`; iOS `xcodegen generate` + `xcodebuild … build 2>&1 |
   grep "error:"` (empty) + `lint-entitlements.sh` (no Apple Pay, no bg-delivery).

**On-device validation (Simulator can't):** pair iPhone + Apple Watch; grant Apple Health once; do a short
workout; open the app and confirm 1–5 on real data; confirm the permission copy + the **distinct** import surface
(not the existing daily "Health Sync"); confirm silent behavior (no notification on routine foreground sync).

**Deployment note (Chunk A — deliberate):**
- Chunk A adds **migration #3** (`add_healthkit_uuid`, the `hk_uuid` column), chaining off the single head
  `add_whoop_connections`, **nullable**. Confirm a single alembic head before pushing (`alembic heads`).
- The **first prod deploy of stage one runs two migrations** (`add_wearable_hr`, `add_whoop_connections`); Chunk
  A's deploy adds the third. **Deploy deliberately, not a drive-by push.**
- After pushing to `main`, **verify `railway status --json` = `SUCCESS`** — a multi-head alembic state **silently
  blocks** the deploy while the old instance keeps serving (masking failure). Then **smoke-test** the live
  `POST /workouts/import-healthkit` (auth, a sample payload, a re-post for idempotency) before iOS chunks.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Contract drift A ↔ B/C/D (field name/type/optionality) | High | High | Registry = single source of truth; B mirrors field-for-field; any change runs the Amendment Protocol + version bump | A authority |
| Naive/aware datetime on Postgres (`TypeError`) | Med | High | `ensure_utc()` on DB datetimes; payload timestamps parsed tz-aware; store `session.date` naive-UTC | A |
| scenePhase `.active` double-fire | High | Med | Debounce (5 min) + in-flight guard; idempotent endpoint makes a double-call harmless | C |
| HealthKit Simulator gap (no Watch data) | Certain | Med | Gates compile-only; functional acceptance on Nick's device; documented | C, D |
| Age missing for `220−age` zones | Med | Med | Pass `age` from profile; if nil omit `hr_zone_seconds` (avg/peak still sent); confirm field optional server-side | C (+A confirm) |
| Dedup correctness (`hk_uuid` uniqueness) | Med | High | Per-user partial-unique index; idempotent re-import test in A's gate | A |
| Migration/deploy silently blocked (multi-head) | Med | High | Single head off `add_whoop_connections`; `alembic heads` pre-push; verify `railway status --json SUCCESS`; smoke-test | A |
| Reused backend service mismatch (matching/attribution) | Med | Med | Verify behavior early in A; if it differs → Amendment Protocol (material) | A |
| joinedload-before-services (empty relationships post-commit) | Med | High | Re-query with `joinedload()` before `quest_service`/`heart_rate_service` | A |
| Touch-all field rule missed (HR field in one place only) | Med | Med | Registry checklist: `schemas/workout.py` → `api/workouts.py` → `APITypes.swift` → Home/History; `WorkoutSummary` HR fields included | A defines, B/C/D mirror |
| Entitlement surprise (missing usage string; forbidden entitlement) | Low | High | `lint-entitlements.sh` in gate (no Apple Pay / bg-delivery); HealthKit usage strings already present | C |
| Nil-safe display (missing strain/zones/samples → "broken") | Med | Med | Strain absent (not "—") off-WHOOP; HRZoneBar 5→3 + EmptyView; per-set HR column only when present | D |
| `hr_zone_time` quest unit ambiguity (seconds vs minutes) | Med | Low | A confirms unit; D formats to match; Amendment Log if copy changes | A + D |

---

## Out of scope for v1 (anti-gold-plating)

| Deferred item | Revisit when |
|---|---|
| watchOS companion app (live HR) | A live in-workout HR readout is wanted; per-set HR is already covered post-hoc. |
| Completion notifications | Users want to be told when a quest credits while the app is closed (pairs with background delivery). |
| D4 / D4a / D4b analytics + custom strain | After v1 ships and there's enough HR history for trends. |
| Celebration animations | Visual-polish pass after the data path is proven. |
| Synthetic sessions for unmatched workouts | A real volume of unmatched HealthKit workouts worth surfacing appears. |
| Full "Data Sources" hub | WHOOP becomes a real second source (v2) — then generalize the settings row into a hub. |
| WHOOP connect / attach / dismiss (1A + D1) | Railway `WHOOP_*` creds + an approved WHOOP dev app exist; until then WHOOP is the disabled "coming soon" row. |
| Editable max-HR / zone override | Users want to override `220−age`; v1 estimates on-device only. |
| Multi-source conflict resolution beyond id-skip | Two live sources supply HR for the same session. |
| HealthKit background delivery (true closed-app sync) | A non-personal provisioning profile allows the entitlement; foreground-on-open meets v1 intent. |
