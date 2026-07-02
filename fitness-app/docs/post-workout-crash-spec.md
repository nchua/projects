# Spec: Post-Workout Crash Investigation & Fix

## Problem

Reported symptom: the app **fully terminates** (not a freeze, not an error alert)
immediately after finishing and saving a workout. This regressed after a run of
recent feature work (Apple Watch cardio/cooldown, dungeons, wearable-HR quests).
The user recalls a similar crash existing "a long time ago" that was already
fixed once.

No crash-reporting SDK is wired up (confirmed — see `plans/01-engineer-technical-analysis.md`,
"Zero analytics or crash reporting SDKs"), and this environment cannot build/run
the iOS app (no macOS/Xcode), so there is no symbolicated stack trace to work
from. This spec documents a full static-analysis pass over the save → celebrate
→ return-to-idle path, what was ruled out, what was found and fixed, and what's
still open.

## Scope of the audit

Traced the entire "finish workout" pipeline end to end:

- `LogViewModel.saveWorkout()` (`ios/FitnessApp/Views/Log/LogViewModel.swift`) —
  request construction, response handling, offline-queue fallback.
- `APIClient.request(...)` (`ios/FitnessApp/Services/APIClient.swift:805`) —
  decode path, error mapping. No force-unwraps or `try!` on the decode call.
- The full `LogView.swift` celebration state machine: PR celebration →
  rank-up celebration → XP reward, including the `.onChange` re-entry guard
  (`pendingXPResponse` id matching) that exists specifically to prevent an
  infinite-loop regression of the kind the CLAUDE.md "onChange: Guard against
  infinite loops" rule warns about. Verified line-by-line: no infinite loop,
  no double-dismiss, no stale-index crash.
- `XPRewardView.swift`, `PRCelebrationView.swift`, `RankUpCelebrationView.swift`
  — all correctly guard `isDismissed` before firing their dismiss closures.
- `PendingWorkoutStore.swift` (offline queue / drain-on-save-success) — no
  force-unwraps, array mutation is bounds-checked.
- Backend `_create_workout_impl` (`backend/app/api/workouts.py`) — already
  follows the documented "re-query with `joinedload()` before touching
  relationships" rule from `fitness-app/CLAUDE.md`; this was the fix for a
  previous, different crash class (empty relationship collections after
  `db.commit()`/`db.refresh()`) and is intact.
- `HomeViewModel`, `CooldownCard.swift`, `DailyQuestsCard.swift` (what the user
  sees on returning to Home) — all optional-safe, bounds-checked (e.g.
  `names.count <= 2` guard before `names[0]/names[1]`, `.max() ?? 0`).
- `HealthKitManager.swift` / `SyncCoordinator.swift` — the foreground HR/cardio
  sync that now runs on every `scenePhase == .active` transition
  (`FitnessApp.swift`) — thoroughly guarded, debounced, no force-unwraps.
- Whole-tree grep for `try!`, `as!`, `.first!`, `.last!`, `fatalError(` — only
  two hits, both provably safe (`APIClient.swift:846` guarded by a type check
  one line above; `FitnessApp.swift:46` only fires on `ModelContainer` init
  failure at app *launch*, unrelated to workout save).

**Conclusion: no force-unwrap, out-of-bounds index, or fatal-error call was
found anywhere on the direct save/celebrate/return path.** This codebase is
unusually well-guarded against exactly this bug class already.

## Bug found and fixed

`WorkoutCreateResponse.dungeon_spawned` had a schema mismatch between backend
and iOS:

- iOS `DungeonSpawnedResponse` (`ios/FitnessApp/Services/APITypes.swift:1476-1497`)
  declares `let isRareGate: Bool` as **required** (`"is_rare_gate"` coding key,
  no default).
- Backend's `DungeonSpawnedResponse` schema used specifically for the
  workout-creation response (`backend/app/schemas/workout.py:184-195`) never
  defined `is_rare_gate`, and the construction site in
  `backend/app/api/workouts.py` (`_create_workout_impl`, dungeon-spawn branch)
  never passed it — even though `dungeon_service.maybe_spawn_dungeon()` already
  computes and returns `is_rare_gate` in its result dict.

Effect: whenever saving a workout triggers a new dungeon spawn, the JSON
response is missing `is_rare_gate`, `JSONDecoder.decode(WorkoutCreateResponse.self, ...)`
throws `DecodingError.keyNotFound`, which is caught by `LogViewModel.saveWorkout()`'s
generic `catch { self.error = ... }` branch — so the save silently fails into
a "System Error" alert (XP/PR/level-up celebration never shows) rather than
crashing outright. Confirmed this is a genuinely dead/unreachable field on the
iOS side too — `DungeonSpawnOverlay.swift` (the only consumer of `isRareGate`)
is never instantiated anywhere in the app; `dungeon_spawned` is decoded but
never rendered.

This is a real regression in the exact "log a workout" flow (introduced when
`is_rare_gate` was added to the dungeon feature but not threaded through the
workout-creation response), so it's fixed regardless of whether it's the exact
crash reported:

- `backend/app/schemas/workout.py`: added `is_rare_gate: bool = False` to
  `DungeonSpawnedResponse`.
- `backend/app/api/workouts.py`: pass `is_rare_gate=d["is_rare_gate"]` when
  constructing the response.

## Open question / what's still needed

Because this fix resolves a **caught decode error**, not a **fatal crash**, it
likely is not the exact bug reported (the user confirmed the symptom is a full
app termination, distinct from "error message then stuck"). If the crash
recurs after this fix ships:

1. Capture a symbolicated crash log — on the test device: **Settings → Privacy
   & Security → Analytics & Improvements → Analytics Data**, look for a
   `FitnessApp-YYYY-MM-DD-*.ips` file near the crash time, or pull it from
   **Xcode → Window → Devices and Simulators → View Device Logs** if building
   from source. This is the fastest way to get an exact frame instead of
   continuing to guess against an already well-guarded codebase.
2. Note the exact circumstances: did a PR happen? A rank-up? A dungeon spawn?
   Multiple PRs queued? Each of those puts a different view on screen, and
   narrows which of the three celebration screens (or none — first-load Home)
   was active when it crashed.
3. Consider adding a crash-reporting SDK (Sentry, per
   `plans/01-engineer-technical-analysis.md` §2) — already on the roadmap as a
   pre-launch item; would make the next occurrence trivial to diagnose instead
   of requiring a full manual trace like this one.
