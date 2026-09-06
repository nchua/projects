# Council Summary — ARISE Control Plane (owner console)

**Date:** 2026-09-05
**Council:** Senior Staff Engineer, Security Engineer, Product Designer, Product Manager (cross-review: security ↔ engineer)
**Deliverable:** `fitness-app/docs/arise-control-plane-spec.md` (+ mockup `fitness-app/docs/mockups/admin-control-plane-mockup.html`)

## Objective

Give the ARISE owner one place — a phone-and-laptop web console served by the existing FastAPI backend — to manage users, entitlements/permissions, pricing and credits, usage, campaign import, data repair, and account deletion/restore, so the three prod-touching owner scripts (`grant_owner_unlimited_scans.py`, `import_training_calendar.py`, `backfill_exercise_families.py`) and the read-only `usage_snapshot.py` are never needed again. Solo developer, ~1 user today, scaling to a handful; no new infrastructure.

**In scope:** admin identity + session model, audit log, entitlements + product catalog, per-user scan limits, credits adjust, campaign import for a target user, family backfill, soft-delete/restore/purge + startup sweep, user list/detail/usage, single-file console at `/admin/ui`, and the pre-existing security fixes that share the console's origin.
**Out of scope:** App Store JWS verification of purchases (separate follow-up; interim caps only), impersonation tokens, multi-admin RBAC, MFA, editable global settings, a separate admin deployable, push broadcast, cohorts, pricing experiments.

## Design (Product Designer, revised after owner review)

- **Surface:** static files (`index.html`, `admin.js`, `admin.css`) served by FastAPI on one `StaticFiles` mount at `/admin/ui/`, same pattern as `/privacy` (`backend/main.py:294`). No build step; deploys with the API it calls.
- **Desktop-first with a scoped phone lane** (owner decision 2026-09-05: "the web app should be the first-class experience"). Desktop ≥1024px: 220px left rail, dense sortable Hunters table, two-column customer view, right-side 420px drawer for actions, audit table with expandable JSON. Phone <768px: bottom tabs Hunters · Audit · Overview; detail in quick-action order (Scans → Entitlements → Danger zone → …); bottom sheets; Catalog, Settings, fleet usage, and paste-JSON import are desktop-only.
- **IA:** Overview → Hunters → Hunter detail (Identity · Scans · Entitlements · Purchases · Campaign | Progress · Integrations · Data health · Preview · Audit-this-hunter; Danger zone full-width) → Audit → Catalog → Settings (read-only in v1).
- **Action pattern:** drawer (desktop) / sheet (phone) with before→after diff + required reason → confirm → toast with audit id. Destructive tier adds typed-email confirm and password re-entry. Dry-run actions render the proposal in place; Confirm becomes Apply.
- **Cut from the designer's draft (no-extraneous-features):** Retry WHOOP sync, Send test push, Repair dates, editable global defaults, "view as" banner.
- Mockup: desktop frames at 1280px (Hunters, detail + credits drawer, detail + purge drawer, Audit, Overview, Catalog + Settings) plus one phone-lane frame; Minimal Void tokens, event delegation, placeholder emails only.

## Technical Plan (Senior Staff Engineer, after security cross-review)

**Identity:** `users.is_admin` (bool, default false) set only by a startup bootstrap from `ADMIN_BOOTSTRAP_EMAIL` (existing non-deleted account; case-insensitive match must hit ≤1 row; writes an audit row; never blocks boot). No API path sets it true in v1.
**Session:** `POST /admin/session {email,password}` → admin token `{sub, ver, type:"admin", aud:"arise-admin", exp:+15m}`, no refresh, held in a JS variable only. `require_admin` decodes with `audience`, requires `type` of `admin`, and loads a fresh DB row (`is_admin`, `!is_deleted`, `ver` equal to `users.token_version`). Attached at router level.
**Revocation:** `users.token_version` int, embedded as `ver` in all tokens (missing ⇒ 0); checked in `get_current_user`, `/auth/refresh`, `require_admin`. Restore bumps it; 5 failed step-ups bump it.
**Lockout:** `users.admin_failed_logins` + `admin_locked_until` (10 failures → 15 min), counted only on bad-password 401s; break-glass SQL documented.
**Step-up:** `verify_step_up(db, actor, password)` called first in every destructive service function; bodies inherit `StepUpBody{password, reason}`; purge adds `confirm_email`.
**Audit:** `admin_audit_log` (actor FK SET NULL, `target_id` non-FK string, allow-listed before/after JSON, reason, request_id, ip, idempotency_key + body_sha256, created_at); same transaction as the change; Postgres BEFORE UPDATE/DELETE trigger, dialect-guarded; only `GET /admin/audit`.
**Entitlements:** `user_entitlements` (key, value JSON, source purchase|admin_grant|backfill, granted_by, purchase_record_id, expires_at, revoked_at). `scan_balances.has_unlimited` stays a cached column with one writer `sync_unlimited_flag()` run inside the balance `FOR UPDATE`. Keys: `scans.unlimited`, `scans.daily_limit`, `scans.cooldown_seconds`, `scans.free_monthly`. `effective_limits()` overlays overrides on `Settings` defaults.
**Products:** `products` table seeded from `PRODUCT_CREDITS`; id immutable; no delete; deactivate is destructive-tier.
**Purchases interim controls:** per-user cap (100 credits/24h, one unlimited grant ever), `5/day` limit, numeric `transaction_id`, owner email on unlimited grant, iOS starts sending `jwsRepresentation`. Full JWS verification = separate follow-up.
**Support actions:** credits adjust (FOR UPDATE, Idempotency-Key), campaign import for `{user_id}` from pasted phases or the committed `owner_hybrid` template (dry-run via `parse_phases`), family backfill (dry-run default), seed-achievements duplicate under `/admin/maintenance`.
**Lifecycle:** admin soft-delete/restore mirror `auth.py:238-239`; `purge_service.PURGE_ORDER` explicit deletes (21 FKs to `users.id` lack cascade), `purchase_records.user_id` SET NULL instead of delete, one transaction per user, grace 30 d unless `force`; startup sweep behind `PURGE_SWEEP_ENABLED` (default false), skipped on SQLite, actor NULL.
**Reads:** list/detail/usage compose existing `user_id`-taking services; `usage_snapshot.py` ported dialect-neutral on `local_date`.
**Hygiene on the shared origin:** `html.escape` in `whoop.py` callback; strip `input`/`ctx` from `main.py:148`; `/admin/*` out of OpenAPI; `no-store` + `X-Frame-Options: DENY` + CSP; daily-count check moved after the balance lock; scripts keep working as fallbacks with `getpass`; rotate the leaked password.
**Migrations:** `admin_schema` (users columns, admin_audit_log, products, user_entitlements, PG trigger) → `admin_seed_backfill` (3 products; `scans.unlimited` rows for existing `has_unlimited` users). Head: `admin_seed_backfill`.

## Acceptance Criteria (Product Manager, amended)

- Every `/admin/*` route: 401 no token / 401 access-token / 403 non-admin admin-token / 200 admin. Enumeration test over `app.routes`.
- Grant unlimited from the console produces the same `scan_balances` row the script did, idempotently, with one audit row (before/after/reason). iOS shows `∞`.
- Revoke sets `has_unlimited = derived`; a revoked purchase-sourced grant is not re-created by `restore-purchases`.
- Credits adjust: exact delta, never below 0 (409), same `Idempotency-Key` → one change, `replayed=true`; same key + different body → 422; `FOR UPDATE` path unchanged (`test_scan_credit_transaction.py` green).
- Campaign import with the committed template reproduces the script's result (3 arcs, 21 templates, 0 warnings); 409 without `replace`; replace records `planned_hunts_deleted`.
- Backfill dry-run writes nothing and returns unresolved names; apply twice → 0 updates.
- Soft-delete → next user request 401; restore → login 200 and old refresh tokens 401 (`token_version`).
- Purge inside grace → 409; `force` + reason + password + `confirm_email` → 200; audit row survives; metadata test covers every FK to `users.id`.
- Reason mandatory (422 blank); console disables Confirm until typed.
- Console: login → grant → `∞` in under a minute on iOS Safari; no inline handlers; 44px targets.
- Ship gates: ruff, pytest, single alembic head, Railway SUCCESS.

## Test Plan (from engineer + security)

`test_admin_auth`, `_users`, `_credits`, `_entitlements`, `_audit` (parametrized over every mutation; same-transaction rollback), `_purge` (metadata + end-to-end seeded user), `_campaign_import`, `_families`, `_usage`, `_migrations` (SQLite round-trip CHAIN), `_ui` (headers), `_step_up` (401 + no audit row on wrong password), mass-assignment regression (`is_admin` in register/profile/username bodies ignored), admin-token-on-user-route and user-token-on-admin-route rejections. Update `test_scan_balance_api.py` (no `PRODUCT_CREDITS` import) and the two rate-limit tests (`monkeypatch.setattr(settings, …)`).

## Execution Order

1. **W0 — foundations:** models + `admin_schema`/`admin_seed_backfill`; `Settings` additions; `admin_auth.py` (`create_admin_token`, `require_admin`, `verify_step_up`); `admin_bootstrap.py`; `audit_service.py`; `entitlement_service.py`; rewire `scan_balance.py` + `screenshot.py`; `ver` claim via `user_token_claims()` in login/refresh/`get_current_user`; hygiene fixes; conftest fixtures; tests.
2. **W1 — reads:** `api/admin.py` skeleton (`/session`, `/me`), `admin_service.list_users/get_user_detail`, `admin_usage_service`, `/audit`, `/products` GET; router in `main.py` with `no-store`.
3. **W2 — mutations:** credits, entitlements grant/revoke, products upsert, campaign import (+ `campaign_templates/owner_hybrid.json`), family backfill `dry_run`, seed-achievements, soft-delete/restore, `purge_service` + sweep. Purge is the slip point if the session runs long.
4. **W3 — console:** `app/admin_ui/index.html`, `GET /admin/ui` + headers, `test_admin_ui`. Script docstrings → "fallback only". Update v3 spec §11 row; memory.
5. **Follow-ups (own sessions):** App Store JWS verification; iOS `jwsRepresentation` + Hunter › System Settings "Admin console" link; remove public `seed-achievements` with the next iOS release.

## Execution Strategy

**Recommended:** Single Agent for W0→W2 (one backend session; the files overlap heavily: `admin.py`, `entitlement_service.py`, `scan_balance.py`, `screenshot.py`, conftest), then a second short session for W3 where the UI (desktop layout first, then the phone lane) can be a separate agent against the frozen W1/W2 contracts. Run `/evaluate` after W0 and after W2 (4+ files, multi-layer); `contract-mirror-check` is not triggered until the iOS link lands.

## Risks & Open Questions

- `verify-purchase` remains a self-serve credit path until JWS verification ships; interim caps + console visibility only.
- Cached `has_unlimited` drift if a future writer bypasses `sync_unlimited_flag()`; the fleet view lists drift.
- Purge order correctness for non-cascading child FKs (`prs.set_id`, `pr_gates.*`, `goal_progress_snapshots.workout_id`, `goals.campaign_id`); the seeded end-to-end test is the guard.
- Per-account lockout lets an attacker lock the owner out of the console; break-glass is one SQL line.
- Bootstrap re-promotes on every boot: demoting the bootstrap account = remove the env var + redeploy.
- Open: rotate the owner's password (leaked into a transcript last session); confirm `PURGE_GRACE_DAYS` (30) stays aligned with `/privacy`; confirm friends' plans will be authored as `data.js` phases vs in-app `POST /campaign`.
