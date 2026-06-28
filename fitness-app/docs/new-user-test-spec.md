# New-User Registration & First-Workout — Test Spec

Status: proposed · Scope: backend (`app/api/auth.py`, `app/api/workouts.py`, gamification services) · Owner: backend

## 1. Purpose

Pin the behavior of the **new-user lifecycle** — registration through a freshly
registered user's *first* gamified workout — so the path can't silently break
again. The registration endpoint itself is already well covered; the gap this
spec fills is the **end-to-end "new user logs their first workout"** flow.

## 2. Why now (motivation)

On **2026-06-28**, production 500'd on *every* workout create — including a
brand-new user's first one — because `user_quests.completed_by_workout_id` was
missing from the prod schema and `update_quest_progress` selects it
(`quest_service.py:380`). Fixed by the corrective migration
`alembic/versions/repair_completed_by_workout_id.py` (PR #23).

The existing tests didn't surface the risk because:

- The **registration** tests stop at signup (they assert the response shape, not
  that the new user can then *do* anything).
- The **workout** tests use the `create_test_user` fixture (which hand-creates
  `User` + `UserProfile`), **not** the real `POST /auth/register` path — so no
  test drives a genuinely registered user through the gamification pipeline.

This spec adds a smoke test that walks the real `/auth/register` → first workout
→ quests/cooldown path, plus a note on the environment caveat that makes
unit tests blind to prod schema drift (§7).

## 3. System under test

### `POST /auth/register`  (anti-enumeration, by design)

| Case | Status | Side effect | Response body |
|------|--------|-------------|---------------|
| New email | `201` | Creates `User` **+ default `UserProfile`** (`auth.py:64-74`) | `{message, user:{id=real, email, created_at=real}}` |
| Existing email | `201` | **No-op** — no second row (email is `unique=True`, `user.py:42`) | identical shape, but `id`/`created_at` are **synthetic decoys** (`auth.py:87-91`) so existence can't be probed |

Password policy (`UserRegister`, `schemas/auth.py:17-37`): `EmailStr`; password
**≥12 chars**, ≤100, and must contain upper + lower + digit + symbol. Violations → `422`.

### `DELETE /auth/account`  (soft delete)
Requires a `DeleteAccountRequest` body `{password}` (`auth.py:219-242`). Wrong
password → `401`; success → `204`, sets `is_deleted=True` + `deleted_at`. A
deleted account's email can't be re-registered into a fresh account (the
duplicate-email decoy path applies) and login returns `403`.

## 4. Existing coverage (do NOT duplicate)

| Test | File |
|------|------|
| `test_register_success` | `tests/test_auth_api.py:12` |
| `test_register_duplicate_email_is_indistinguishable` | `tests/test_auth_api.py:24` |
| `test_register_weak_password` | `tests/test_auth_api.py:59` |
| `test_delete_account_success` / `_wrong_password` / `_sets_flags` | `tests/test_auth_api.py:162-183` |
| `test_fresh_and_duplicate_register_share_shape` | `tests/test_auth_hardening.py:150` |
| `test_duplicate_register_does_not_overwrite_password` | `tests/test_auth_hardening.py:170` |

## 5. New tests to add (the gap)

Add a `tests/test_new_user_lifecycle.py`. All steps use the **real HTTP
endpoints via `client`** (not the `create_test_user` fixture) so the actual
registration → gamification wiring is exercised.

**T1 — New user can log their first strength workout (regression guard for the incident)**
- *Given* a brand-new email registered via `POST /auth/register` (`201`)
- *And* a login via `POST /auth/login` yielding a JWT
- *And* one seeded library `Exercise`
- *When* the user `POST /workouts` with one exercise + one set
- *Then* the response is **`201`** (not `500`)
- *And* the workout, XP/level, and quest progress fields are populated for a
  user who had no prior `UserProgress`/quests (proves
  `get_or_create_user_progress` + `update_quest_progress` tolerate the fresh state).

**T2 — New user can import their first Apple-Watch cardio workout**
- *Given* the same new user and a seeded `"Running"` Sport/Cardio exercise
- *When* `POST /workouts/import-healthkit` with one cardio (`is_strength=false`) workout
- *Then* `200` with `sessions_created` length 1
- *And* `GET /workouts` shows it as an activity (`is_activity=true`, `activity_type`,
  `calories`, `exertion_score`, proxy `primary_muscles`)
- *And* `GET /analytics/cooldowns` returns the activity's muscles (no `500`).

**T3 — Brand-new user's analytics endpoints are empty, not broken**
- *Given* a freshly registered user with zero workouts
- *When* `GET /analytics/cooldowns` (and `/progress/summary`)
- *Then* `200` with empty/zeroed payloads (guards the no-data path).

**T4 — Re-registering a deleted account's email cannot resurrect or hijack it**
- *Given* a user who `DELETE /auth/account`-ed (soft-deleted)
- *When* `POST /auth/register` with the same email + a new password
- *Then* `201` with the decoy shape, **no** new active user, and login with the
  new password fails (`401`/`403`) — the account stays deleted.

## 6. Negative/validation cases to assert (cheap, pin them)

- Invalid email (`not-an-email`) → `422`.
- Password too short (<12) / missing a class (no symbol, no digit, …) → `422`,
  one case per rule in `validate_password`.
- `DELETE /auth/account` with no body → `422`; wrong password → `401`.

## 7. Environment caveat (important)

The backend test suite runs against **in-memory SQLite built from the models via
`create_all`** (`tests/conftest.py`). That means the schema always matches the
models, so **these tests cannot catch the prod failure mode** (alembic_version
stamped ahead of the real Postgres schema). The real guards for *that* class of
bug are:

1. The **"Alembic — up/down/up on Postgres"** CI job (runs migrations on real PG).
2. A **post-deploy smoke check** against prod: register a throwaway user → `POST
   /workouts` (assert `201`) → `DELETE /auth/account`. Recommend wiring this as a
   scheduled check or a post-deploy step so schema drift pages instead of waiting
   to be discovered by hand (as it was on 2026-06-28).

## 8. Definition of done

- `tests/test_new_user_lifecycle.py` added with T1–T4 + §6 cases, all green under
  `./venv/bin/python3.13 -m pytest`.
- `ruff check .` clean.
- (Recommended, separate) a post-deploy prod smoke check exists per §7.

## 9. References

- `app/api/auth.py` (register `:47`, delete_account `:219`)
- `app/schemas/auth.py` (`UserRegister:17`, `DeleteAccountRequest:74`)
- `app/api/workouts.py` (`_create_workout_impl`, `import-healthkit:566`)
- `app/services/quest_service.py:380` (the query that broke)
- `alembic/versions/repair_completed_by_workout_id.py` (the corrective migration)
