# ARISE Control Plane — The Owner's Console

> **Status:** Draft v1 for review (2026-09-05). Produced by a four-role council (staff engineer,
> security engineer, product designer, product manager) with one security ↔ engineer cross-review
> round; council record at `plans/COUNCIL_SUMMARY_admin-control-plane_2026-09-05.md`. Code anchors
> verified against the working tree at `b37b2c6`; re-verify `file:line` before each workstream.
>
> **What this is:** the product and technical definition of an owner-operated control plane for
> ARISE — one place, reachable from a phone or a laptop, to manage users, permissions
> (entitlements), pricing and credits, usage, campaign import, data repair, and account
> deletion/restore. It retires the three prod-touching owner scripts and the read-only usage
> snapshot that the ARISE v3 ship needed the owner to run by hand with `!`.
>
> **What this is not:** a second product. No new deployable, no scheduler service, no admin
> framework, no multi-admin RBAC, no MFA. The console is a single HTML file served by the backend
> it already deploys with, and every action it offers is a thin, audited wrapper over a service
> function that already exists or that the scripts already contain.

---

## 0. TL;DR

Today every per-user change on prod is a script the owner runs from a terminal, with the prod
`DATABASE_URL` in a local `.env` and the owner's password passed to the script by hand. That
does not scale past one user, and it is also the
reason Claude cannot help operate the app: the auto-mode classifier blocks prod-DB access.

| Owner job today | How it is done | Problem |
|---|---|---|
| Give someone unlimited scans | `scripts/grant_owner_unlimited_scans.py` (direct DB write) | terminal + `.env` with prod credentials; no record of who/why |
| Load a training plan into a user's Campaign | `scripts/import_training_calendar.py` (logs in as the user over HTTP) | needs the user's password in the environment |
| Repair exercise families after a dictionary change | `scripts/backfill_exercise_families.py` | direct DB write, no dry-run |
| See how a user is doing | `scripts/usage_snapshot.py` (read-only SQL) | Postgres-only SQL, buckets on `date` not `local_date` |
| Recover a deleted account | nothing — login says "Contact support to recover" (`app/api/auth.py:128`) | there is no support path |
| Delete data after 30 days | nothing — `/privacy` promises it (`main.py:344`) | the promise is unimplemented |

**v1 collapses these into `/admin/ui`**, served by FastAPI like `/privacy`, gated by a
DB-checked admin flag and a 15-minute admin token, with every mutation confirmed with a
before→after diff and a mandatory reason that lands in an append-only audit log.

1. **Identity and session** (§4): `users.is_admin` set only by a startup bootstrap from one env
   var; a separate admin token that no user route accepts; `users.token_version` so restore and
   "log out everywhere" actually revoke; DB-backed lockout on the admin login.
2. **Audit log** (§5): one row per mutation, written in the same transaction, allow-listed
   before/after, reason, request id; Postgres trigger makes it append-only.
3. **Entitlements and pricing** (§6): a small `user_entitlements` table and a `products` catalog
   replacing the hardcoded product dict; `has_unlimited` stays the one boolean the scanner reads,
   with a single writer; per-user scan limits overlay the global defaults.
4. **Support actions** (§7): credits adjust, campaign import for a target user (pasted phases or
   the committed owner template, dry-run first), family backfill (dry-run first), seed
   achievements — the scripts as audited endpoints.
5. **Account lifecycle** (§8): admin soft-delete, restore, and hard purge with a 30-day grace
   window, an explicit delete order (21 foreign keys to `users.id` have no cascade), and a
   startup sweep behind an env flag so the privacy promise becomes true at zero infra.
6. **Read surfaces and the console** (§9–§10): user list, the user detail "customer view", fleet
   usage, audit; a desktop-first static page with a scoped phone lane and a confirm-with-reason
   pattern for every action.
7. **Hygiene folded in** (§11): the pre-existing holes that share the console's origin — a
   reflected XSS on the WHOOP callback, passwords echoed into logs by the validation handler,
   an unverified purchase endpoint — get their cheap fixes in the same workstream.

Build: **W0 foundations → W1 reads → W2 mutations → W3 console**, ~1.5 sessions (§15). Owner
behavior changes at the end of W1: the next "how is X doing" is a URL, not a script.

---

## 1. Jobs to be done (the owner's)

| # | Job | Today | v1 |
|---|---|---|---|
| O1 | Grant or take back a permission for one person — from my desk in seconds, from my phone in under a minute | script + terminal | Hunter detail › Scans / Entitlements card (phone lane) |
| O2 | Put a training plan into someone's Campaign without their password | script logs in as them | Hunter detail › Campaign › Import (dry-run, then apply) |
| O3 | Fix data after a dictionary or rule change and see what is still unresolved | script, no preview | Overview › Attention › Backfill (dry-run, then apply) |
| O4 | See how any user is doing without opening the database | `usage_snapshot.py` | Hunter detail + Usage |
| O5 | Know what I changed, for whom, and why, a month later | nothing | Audit |
| O6 | Recover a deleted account; delete for real after 30 days | nothing / nothing | Danger zone › Restore / Purge; startup sweep |
| O7 | Change what a product is worth without a deploy | edit `PRODUCT_CREDITS` and push | Catalog |
| O8 | Not be paywalled or rate-limited out of my own app, and give the same to a friend | one-time script | entitlement grant |

---

## 2. Design pillars

1. **The database is the authority, never the token.** Admin status, revocation, and lockout are
   read from the `users` row on every request. A token proves who you are for 15 minutes; the
   row decides what you may do right now.
2. **Every mutation is single-target, previewed, reasoned, and audited.** One `{user_id}` per
   request. The console shows the diff before the call; the server records the real diff after.
   No bulk endpoints in v1.
3. **Dry-run is the default for anything that writes many rows.** Backfill, campaign import, and
   the purge sweep return counts first; `apply`/`force` is explicit.
4. **Wrap, don't re-implement.** Every action calls the service function the scripts or the app
   already call (`import_campaign`, `assign_family_ids`, `award_xp`-style readers). The scripts
   keep working as break-glass and share symbols with the routes, so they cannot drift.
5. **The scanner's hot path does not change.** `_reserve_scan_credits` still reads one boolean
   under one row lock (`app/api/screenshot.py:251`). Entitlements are resolved on write, not
   inside the critical section.
6. **Proportionate to a solo operator.** Audit log, step-up re-auth, short tokens, lockout: yes.
   MFA, RBAC, SIEM, a second deployable: no, with the trigger that would change the answer
   written down (§14).

---

## 3. Object model

| Object | What it is | Key fields | Storage | Writer |
|---|---|---|---|---|
| **Account** | login identity + lifecycle | `id`, `email`, `username`, `is_deleted`, `deleted_at`, **`is_admin`**, **`token_version`**, **`admin_failed_logins`**, **`admin_locked_until`** | `users` (`app/models/user.py:37-48`) + 4 new columns | user (register, self-delete), bootstrap (`is_admin`), admin (delete/restore), system (purge) |
| **Profile** | athlete settings the engines read | age, sex, unit, formula, injury notes, HR cap | `user_profiles` (`user.py:61-90`) | user only; admin reads |
| **Balance** | countable scan credits — a ledger quantity, not a right | `scan_credits`, `has_unlimited` (cached), `free_scans_reset_at` | `scan_balances` (`app/models/scan_balance.py:12-26`) | purchase, monthly reset, scanner deduct, **admin adjust** |
| **Entitlement** | a keyed right or limit for one user, with provenance | `key`, `value` JSON, `source` purchase\|admin_grant\|backfill, `granted_by`, `purchase_record_id`, `reason`, `expires_at`, `revoked_at` | **new `user_entitlements`** | purchase path, admin grant/revoke, migration backfill |
| **Product** | catalog SKU → its effect | `id` (= App Store product id, immutable), `kind` consumable\|non_consumable\|subscription, `credits`, `entitlement_key`, `display_name`, `active`, `sort_order` | **new `products`** (replaces `PRODUCT_CREDITS`, `app/api/scan_balance.py:28-34`) | migration seed; admin upsert (deactivate only, never delete) |
| **Purchase** | immutable IAP receipt / idempotency key | `transaction_id` (unique), `product_id`, `credits_added`, `purchase_type`, `user_id` (nullable after purge) | `purchase_records` (`scan_balance.py:29-40`) | user purchase only — admin grants never write here |
| **Audit event** | the record of one admin mutation | actor, action, target, before/after (allow-listed), reason, request id, ip, idempotency key + body hash | **new `admin_audit_log`** | every `/admin/*` mutation, the bootstrap, the sweep |
| **Support action** | a parameterized job the owner used to run as a script | action, params, result counts | no table — the result lives in the audit row's `after` | admin |
| **Usage aggregate** | per-user and fleet rollups | sessions by ISO week, top exercises, scans, gates, coverage, integrations | computed on read (port of `scripts/usage_snapshot.py:37-210`) | system |
| **Global setting** | app-wide defaults and kill switches | `FREE_MONTHLY_SCANS`, `DAILY_SCREENSHOT_LIMIT`, `COOLDOWN_SECONDS`, `SCREENSHOT_PROCESSING_ENABLED`, `PURGE_GRACE_DAYS`, `PURGE_SWEEP_ENABLED` | `Settings` (env) — read-only card in v1 | Railway env |
| **Admin principal** | who may call `/admin/*` | `users.is_admin = true` | bootstrapped from `ADMIN_BOOTSTRAP_EMAIL` | startup bootstrap only (no promote route in v1) |

What deliberately does **not** exist: an XP/rank editor (pillar 1 of the v3 spec — "derived from
real data or it doesn't ship"; the dead `XPAwardRequest` at `app/schemas/progress.py:27-48` stays
dead), an impersonation token (§9.2), editable global settings (§14), a support-notes table (§14).

---

## 4. Identity, sessions, and step-up

### 4.1 Who is an admin

`users.is_admin BOOLEAN NOT NULL DEFAULT false`. Options considered and rejected: a `role` enum
(Postgres `ALTER TYPE` pain for a second role that does not exist), an env-only allowlist
(authorization outside the DB — no audit of who is admin, removing the var silently revokes,
and it can never be extended from the console).

**Bootstrap, not a promote route.** `app/core/admin_bootstrap.py::bootstrap_admin()` runs in
the FastAPI lifespan on every boot:

```
UPDATE users SET is_admin = true
WHERE lower(email) = lower(:ADMIN_BOOTSTRAP_EMAIL) AND is_deleted = false AND is_admin = false
```

- Promotes only an **existing, non-deleted** account; never creates one; never "promotes on
  first login". A typo means nobody is admin and an ERROR log line, not a future takeover.
- `users.email` is case-sensitive unique (`app/models/user.py:42`) and register stores the raw
  string (`app/api/auth.py:59-66`), so the case-insensitive match must affect **≤ 1 row**; more
  → skip with an ERROR log.
- Writes an audit row (`actor NULL, action = "admin.bootstrap"`) when it changes something.
- Wrapped in try/except; logs only the last four characters of the id (the scripts' convention).
- Re-evaluated every boot, so setting the var after the first deploy works. Consequence:
  **demoting the bootstrap account = remove the env var and redeploy.** v1 ships **zero**
  request paths that set `is_admin = true`; a promote route is the v2 trigger for a second admin.
- Mass-assignment guard: `is_admin` is never declared on any request schema, and the
  regression test posts `{"is_admin": true}` to `/auth/register`, `/profile`, and
  `/users/username` and asserts the column is unchanged. (Today `register` uses an explicit
  constructor, `auth.py:64-67`, and `PUT /profile`'s `setattr` loop runs over a closed schema
  onto `UserProfile`, `app/api/profile.py:92-94` — keep both properties.)

### 4.2 The admin token

Reusing the app's access token was rejected: the phone holds a 30-day refresh token
(`app/core/config.py:38`), so a stolen phone would be a 30-day admin credential, and the
browser page would have to store a refresh token. Instead:

| | |
|---|---|
| Mint | `POST /admin/session {email, password}` — no prior `/auth/login`; the page never sees a refresh token |
| Checks | `is_admin`, `not is_deleted`, `admin_locked_until`, password via `verify_password_with_rehash` (`app/core/security.py:48`) |
| Claims | `{sub, ver, type: "admin", aud: "arise-admin", iat, exp: now + 15 min}` — HS256 with the existing `SECRET_KEY` |
| Refresh | **none.** Extend = log in again. UI shows a countdown |
| Storage | a JavaScript module variable. **Not** `localStorage`, `sessionStorage`, or a cookie — `/whoop/callback` reflects a query parameter unescaped on the same origin (§11), and Bearer-in-memory also means no CSRF surface, so the CORS config at `main.py:179-196` is untouched |
| Rate limit | `@limiter.limit(LOGIN_RATE_LIMIT)` (`app/core/rate_limit.py:56`) **plus** the DB lockout below, because slowapi's storage is per-process and resets on deploy (`rate_limit.py:48-50`) |
| Responses | 401 bad password (counts toward lockout); 403 valid password but not admin (does not count — `/auth/login` already confirms password validity, so there is no new oracle); 423 locked |
| Audit | `session.create` row on success |

`require_admin` (`app/core/admin_auth.py`), attached once at the router —
`APIRouter(dependencies=[Depends(require_admin)])` — and re-declared as `actor: User =
Depends(require_admin)` in mutating handlers (FastAPI caches it per request):

```
HTTPBearer (reuse dependencies.security)
 → jwt.decode(token, settings.SECRET_KEY, algorithms=[HS256], audience=ADMIN_AUDIENCE)
 → payload["type"] == "admin"            # the enforced discriminator; verified: python-jose 3.3.0
                                         # accepts a token WITHOUT aud when decoding with audience=,
                                         # so aud alone cannot gate — it only makes admin tokens fail
                                         # on every normal route (security.py:134 has no audience=)
 → user = db.query(User).get(sub)        # fresh row every request, mirrors dependencies.py:55
 → 401 if missing or is_deleted
 → 403 if not is_admin
 → 401 if payload["ver"] != user.token_version
 → sentry tag admin_actor; request.state.audit_ip = _client_ip(request)   # rate_limit.py:13
```

The two token classes cannot cross: `get_current_user` rejects `type != "access"`
(`security.py:156`) and `require_admin` rejects anything but `type == "admin"`. Tests assert
both directions.

### 4.3 Revocation: `users.token_version`

One integer column, default 0, embedded as `ver` in **every** token minted from now on via a
new `security.user_token_claims(user) -> {"sub", "ver"}` used at login (`auth.py:148-149`),
refresh (`auth.py:209-210`, comparing against the row already fetched at `:192`), the password
reset's token mint if it has one (`app/api/password_reset.py:97` — verify), and the admin
session. Readers — `get_current_user` (`dependencies.py:55`, row already loaded, zero extra
queries), `/auth/refresh`, `require_admin` — reject `ver != users.token_version`; a token with
no `ver` is treated as 0, so every existing token keeps working until the first bump.

Bumps: **restore** (kills refresh tokens minted before deletion, which `/auth/refresh` would
otherwise honour for 30 days — it only checks `is_deleted`, `auth.py:201`), **five failed
step-ups**, **a completed password reset** (every device is logged out after a reset), and a
future "log out everywhere". `SECRET_KEY` rotation is **not** a revocation
mechanism: it also bricks every stored WHOOP token (`app/core/crypto.py:8-10`).

### 4.4 Lockout

`users.admin_failed_logins INT NOT NULL DEFAULT 0`, `users.admin_locked_until DATETIME NULL`
(the pattern already used for reset codes, `app/api/password_reset.py:124-135`). Incremented on
a bad-password 401 at `/admin/session` and on a failed step-up; **10 → locked 15 minutes**;
**5 failed step-ups → `token_version += 1`** (the session dies) and the counter resets. Success
resets the counter. Per-account lockout means an attacker can lock the owner out of the console;
break-glass is one line the owner runs with `!`:
`UPDATE users SET admin_locked_until = NULL, admin_failed_logins = 0 WHERE id = '<id>';`

### 4.5 Step-up for destructive actions

Destructive routes take `password` and `reason` in the body (`StepUpBody{password: str,
reason: str (min 3)}`) and re-verify the password server-side. A route-level dependency cannot
read the endpoint's own body model without nesting two body params, so the check is
`admin_auth.verify_step_up(db, actor, password)` called as the **first line of each destructive
service function** — the enforcement test parametrizes over that list and asserts 401 and no
audit row on a wrong password.

Destructive tier: purge, force-purge, soft-delete, restore, entitlement revoke, campaign import
with `replace = true`, family backfill apply, credits adjust with `|delta| > 50`, product
upsert that sets `active = false`. Purge additionally requires `confirm_email` equal to the
target's email. Everything else (grant, small credit adjust, dry-runs, reads) needs only the
admin token and — for mutations — a reason.

---

## 5. Audit log

`admin_audit_log` (`app/models/admin.py`):

| Column | Type | Notes |
|---|---|---|
| `id` | String PK (uuid4) | |
| `actor_user_id` | String, nullable, **not an FK** | NULL = system (bootstrap, sweep); a purged actor's id stays in the trail, and a SET NULL cascade would itself be an UPDATE the trigger rejects |
| `action` | String, indexed | dotted verbs: `session.create`, `admin.bootstrap`, `credits.adjust`, `entitlement.grant`, `entitlement.revoke`, `product.upsert`, `campaign.import`, `maintenance.family_backfill`, `maintenance.seed_achievements`, `maintenance.purge_sweep`, `user.soft_delete`, `user.restore`, `user.purge` |
| `target_type` | String | `user` / `product` / `entitlement` / `campaign` / `system` |
| `target_id` | String, nullable, **not an FK** | survives purge — the trail outlives the row |
| `before`, `after` | JSON, nullable | **allow-listed** snapshots via `snapshot(obj, fields)`; never email, `password_hash`, `*_encrypted`, device tokens, reset codes |
| `reason` | Text, nullable | required by the API on every mutation |
| `request_id`, `ip` | String | from `get_request_id()` (`app/core/request_context.py:34`) and `request.state.audit_ip` |
| `idempotency_key`, `body_sha256` | String, nullable | credits adjust replay record (§7.1) |
| `created_at` | DateTime, `server_default=now()` | |

Indexes: `(target_type, target_id, created_at)`, `(actor_user_id, created_at)`, and a
**partial unique** `(actor_user_id, idempotency_key) WHERE idempotency_key IS NOT NULL`
(`postgresql_where` + `sqlite_where`; SQLite enforces partial indexes, so the test DB does too).
JSON column precedent: `app/models/campaign.py:74,132,169`.

**Same-transaction rule.** `audit_service.audit(db, *, actor, action, target_type, target_id,
before=None, after=None, reason=None, request=None, idempotency_key=None, body_sha256=None)`
does `db.add` + `db.flush()` and **never commits**; the caller commits the change and the audit
row together, so a failure after `audit()` rolls both back. Every admin mutation lives in
`admin_service.py`, `entitlement_service.py`, or `purge_service.py`, takes `actor`, and calls
`audit()` before returning; `tests/test_admin_audit.py` parametrizes over that list and asserts
exactly one new row per call carrying the round-tripped `X-Request-ID`.

**Append-only.** (1) No update/delete code path: the model has no mutator and the router exposes
only `GET /admin/audit`; a test asserts no PUT/PATCH/DELETE route exists under `/admin/audit`.
(2) A Postgres trigger `BEFORE UPDATE OR DELETE ON admin_audit_log … RAISE EXCEPTION`, created in
the migration under `if bind.dialect.name == "postgresql"` with `CREATE OR REPLACE FUNCTION` /
`DROP TRIGGER IF EXISTS` (raw-SQL precedent `alembic/versions/add_workout_local_date.py:35`).
(3) A second least-privilege DB role — skipped: the Railway role owns the table and can re-grant,
so the trigger is the 80/20 for one operator.

**PII rule.** List and detail views show emails unmasked (owner-only page, a handful of users,
paginated, `no-store`, no export route). Audit JSON, log lines, and Sentry tags carry ids only.

---

## 6. Entitlements and pricing

### 6.1 Vocabulary

| Key | Type | Default | Where it is read |
|---|---|---|---|
| `scans.unlimited` | bool | false | via the cached `scan_balances.has_unlimited` (§6.2) |
| `scans.daily_limit` | int | `settings.DAILY_SCREENSHOT_LIMIT` (moved from `app/api/screenshot.py:26`) | `_check_screenshot_rate_limit` (`screenshot.py:189,193`) |
| `scans.cooldown_seconds` | int | `settings.COOLDOWN_SECONDS` (moved from `:27`) | `screenshot.py:202,206` |
| `scans.free_monthly` | int | `settings.FREE_MONTHLY_SCANS` (`app/core/config.py:44`) | both monthly-reset helpers (`screenshot.py:77`, `scan_balance.py:58`) and both `_get_or_create_balance` copies (`scan_balance.py:43`, `screenshot.py:53`) — collapse the copies into `entitlement_service.get_or_create_balance` while here |

Credits are a **balance, not an entitlement**: consumables are a ledger quantity (Stripe
customer balance; RevenueCat does not model consumables as entitlements at all), and a key/value
override would break the atomic `FOR UPDATE` deduct. Not reserved yet: `coach.debrief` (a global
kill switch is cheap if friends onboard before per-user overrides — open question §18),
`campaign.import` (any user may import their own; importing *for* someone is an admin
capability), `beta.*` (reserve when the first beta feature exists; the resolver is key-agnostic).

**Resolution:** active per-user row → product-derived → global default. Active ⇔
`revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now)`; multiple rows per key are
history, the newest active wins. `effective_limits(db, user_id, *, defaults: ScanLimits) ->
ScanLimits` is one indexed query (`key IN (…)`, active filter) overlaid on defaults built from
`settings.*` **at call time**, so tests keep patching settings
(`monkeypatch.setattr(settings, "COOLDOWN_SECONDS", 0)`, precedent
`tests/test_whoop_service.py:466`; `tests/test_scan_credit_transaction.py:162` and
`test_screenshot_rate_limit.py` switch from patching the module constant).

### 6.2 `has_unlimited` stays cached, with one writer

`_reserve_scan_credits` reads the flag on the row it already holds `FOR UPDATE`
(`screenshot.py:236-253`); `_refund_scan_credits` (`:101`) and the iOS contract
(`ios/FitnessApp/Services/APITypes.swift:1274-1294`) read the same column. Deriving it inside
the critical section would add a query; so the column stays and gets exactly one writer:

```
entitlement_service.sync_unlimited_flag(db, user_id):
    balance = get_or_create_balance(db, user_id, for_update=True)   # same lock as the scanner
    balance.has_unlimited = is_entitled(db, user_id, "scans.unlimited")
```

Called by `grant`, `revoke`, `verify_purchase`, and `restore_purchases` — inside the caller's
transaction, holding the balance lock, so it cannot race a concurrent scan. The fleet view lists
**drift** (`has_unlimited != derived`) so a future writer that bypasses the helper is visible.

### 6.3 `user_entitlements`

`id`, `user_id` (FK `users.id`, no cascade — purge deletes explicitly), `key`, `value` JSON
(`true` / int), `source` (`purchase` | `admin_grant` | `backfill`), `granted_by` (admin user id,
nullable), `purchase_record_id` (String, nullable, not an FK, indexed), `reason`, `expires_at`,
`revoked_at`, `created_at`. Index `(user_id, key)`. Grant validates the key against
`ENTITLEMENT_KEYS` (422 otherwise) and the value type.

**Revoke survives "Restore Purchases".** `grant(source="purchase", purchase_record_id=X)` is a
**no-op if any row — active or revoked — already references X**. `restore_purchases`
(`scan_balance.py:171-180`) stops writing `has_unlimited = True` directly (`:177`) and calls
`grant(...)` → `sync_unlimited_flag`. A re-grant after a revoke is `source = "admin_grant"`.
Purchase-sourced entitlements **are** revocable (destructive tier, with the source shown in the
confirm sheet) because the purchase endpoint accepts fabricated transaction ids today (§6.5).

Migration backfill: for every `scan_balances.has_unlimited = true` without an active
`scans.unlimited` row, insert one (`source = purchase` if an unlimited `purchase_records` row
exists, else `backfill`) — the owner's script-granted flag is represented on day one and the
drift list starts empty.

### 6.4 `products`

`id` (String PK = App Store product id, **immutable after create**), `kind`
(`consumable` | `non_consumable` | `subscription`), `credits` int default 0, `entitlement_key`
nullable (`scans.unlimited` for the unlimited SKU), `display_name`, `active`, `sort_order`,
timestamps. Seeded insert-if-missing from the three ids at `scan_balance.py:29-31` so
`verify-purchase` cannot 400 on deploy. **No DELETE** — `purchase_records.product_id` references
it by string; deactivate instead (destructive tier). `verify_purchase` reads the table: unknown or
inactive → 400; `entitlement_key` set → `grant(source="purchase")` + sync; else
`scan_credits += credits`. Prices live in App Store Connect; this table only maps id → effect.
If scope must shrink, cut `products` (keep the dict) before cutting `user_entitlements`.

Subscriptions are representable (`kind`, `expires_at`) but no expiry re-sync exists; when a
subscription SKU actually ships, switch `_reserve_scan_credits` to `is_entitled()` (one indexed
query) instead of the cached flag. Not built now.

### 6.5 Purchases: interim controls, verification later

`POST /scan-balance/verify-purchase` (`scan_balance.py:83-153`) credits packs and sets unlimited
from a client-supplied `transaction_id` + `product_id`; `signed_transaction` is accepted and
ignored, and iOS sends `nil` (`ios/FitnessApp/Services/StoreKitManager.swift:93`). With any user
who is not the owner, that is a self-serve unlimited grant and unbounded Vision spend. Full
StoreKit 2 JWS verification (x5c chain to Apple Root CA G3; `bundleId`, `productId`,
`transactionId` match) is a **separate follow-up session**; the unlimited SKU stays enabled
because today's users are trusted. Interim controls shipped in W0:

- per-user caps inside `verify_purchase`: ≤ 100 credits per 24 h, at most one unlimited grant
  ever (a second unlimited transaction id → 409, logged);
- at most 5 verifications per user per 24 h, counted from `purchase_records` in the DB rather
  than a slowapi limit (the in-memory limiter is per-process and resets on deploy);
- reject a non-numeric `transaction_id` (StoreKit ids are integers);
- email the owner on every unlimited grant via the existing SendGrid service
  (`app/services/email_service.py`);
- iOS starts passing `verification.jwsRepresentation` now, so the follow-up is server-only.

All caps are evaluated **after** taking the balance row lock, so concurrent calls with distinct
fabricated ids are serialised per user instead of each seeing zero prior purchases.

The console's Purchases card shows every row (product, credits, date, truncated transaction
id) so fabricated ids are visible next to the entitlement they produced.

---

## 7. Support actions

All are `POST /admin/…`, take a `reason`, write one audit row in the same transaction, and wrap
a function the scripts already call (pillar 4). Request/response shapes are in §13.

### 7.1 Credits adjust

`POST /admin/users/{id}/credits {delta ≠ 0, reason}` with a **required `Idempotency-Key`
header** (a UUID per form submission, not per session). Locks the balance with
`.with_for_update()` (the scanner's lock), 409 if the result would go negative, writes the audit
row with `idempotency_key` and `body_sha256` in the same transaction. Replay with the same key
and body → the stored `after` with `replayed = true`; same key, different body → 422. The audit
row *is* the idempotency record — no extra table. `|delta| > 50` is destructive tier.

### 7.2 Campaign import for a target user

Replaces `scripts/import_training_calendar.py`. `AdminCampaignImportRequest` extends
`CampaignImportRequest` (`app/schemas/campaign.py:38-45`) with `phases` optional plus
`template: "owner_hybrid" | None` and `dry_run` — exactly one of `phases` / `template`. The
server-side template is a committed copy of the PWA's `PHASES`
(`backend/campaign_templates/owner_hybrid.json`; v3 spec §4.3 "one seed"), and the regex
parser moves out of the script (`import_training_calendar.py:42-55`) into
`app/services/campaign_templates.py` (the JSON sits beside `app/`, not inside the package, so
the module and the directory do not collide). Dry-run calls `parse_phases` (`app/services/campaign_service.py:273`)
only and returns warnings + an arc summary. Apply wraps `import_campaign(db, user_id, …,
replace=)` (`campaign_service.py:491-534`) and handles `objectives` exactly as
`app/api/campaign.py:78-85`. `replace = true` is destructive tier because `retire_campaign`
deletes future planned hunts (`campaign_service.py:475-489`). Audit: `before = {active_campaign_id,
status}`, `after = {campaign_id, arcs, templates_created, retired_campaign_id,
planned_hunts_deleted}`; the raw payload is stored for replay.

### 7.3 Exercise-family backfill

Replaces `scripts/backfill_exercise_families.py`. `ensure_families` / `assign_family_ids`
(`app/services/exercise_family_service.py:27,56`) gain `dry_run: bool = False` that computes
counts and skips the write + commit. `POST /admin/maintenance/exercise-families {dry_run =
true, reason}` returns `{families_changed, exercises_updated, assigned, total, unresolved:
[{name, is_custom, user_id?}]}` — the script's report (`backfill_exercise_families.py:50-62`).
Apply is destructive tier; audit only on apply. Manual `family_id` assignment for one custom
exercise is v2 (§14).

### 7.4 Seed achievements

`POST /progress/seed-achievements` (`app/api/progress.py:129-141`) is callable by any user and
**iOS calls it** (`ios/FitnessApp/Services/APIClient.swift:362`), so it cannot be removed
without an iOS release. v1 adds the audited duplicate `POST /admin/maintenance/seed-achievements`
and schedules removal of the public route with the next iOS release.

---

## 8. Account lifecycle

### 8.1 Soft-delete and restore

Admin soft-delete mirrors the self-serve path (`app/api/auth.py:238-239`) without the user's
password: sets `is_deleted`, `deleted_at`; the user's next request 401s
(`app/core/dependencies.py:64`). Refuses self and other admins. Restore clears both fields,
**bumps `token_version`** (§4.3), and is proven by `login` (`auth.py:124`) returning 200. Both
are destructive tier; 409 if already in the requested state. Self-deleted accounts
(`DELETE /auth/account`) appear in the list's Deleted filter with days-until-purge — this is what
makes the login copy "Contact support to recover" (`auth.py:128`) true.

### 8.2 Hard purge

Allowed iff `is_deleted AND deleted_at <= now − PURGE_GRACE_DAYS` (30, matching `/privacy`,
`main.py:344,349`), or `force = true` with a reason ≥ 10 characters; always requires
`password` + `confirm_email`; 403 for admins and self.

Only `device_tokens`, `notification_preferences`, `whoop_connections`, `friend_requests`, and
`friendships` cascade from `users.id`; **21 other FKs do not** (`user_profiles`,
`workout_sessions`, `heart_rate_samples`, `bodyweight_entries`, `daily_activity`,
`password_reset_tokens`, `prs`, `coach_outputs`, `pr_gates`, `goals`, `user_achievements`,
`scan_balances`, `purchase_records`, `campaigns`, `planned_hunts`, `user_directives`,
`screenshot_usage`, custom `exercises`, `user_progress`, `daily_training_load`,
`user_entitlements`). A "add CASCADE to 21 FKs" migration was rejected (this repo has needed
orphan pre-cleaning for FK migrations before, `alembic/versions/add_workout_cascade_fks.py:66-67`,
and cascades are not testable on SQLite). Instead `purge_service.purge_user` runs explicit
deletes in `PURGE_ORDER`, one transaction per user, respecting the non-cascading child FKs:

```
user_achievements → user_progress
prs, pr_gates (before sets / planned_hunts), goal_progress_snapshots → goals (before campaigns)
planned_hunts → campaigns (arcs / templates cascade)
heart_rate_samples → workout_sessions (exercises / sets cascade)
custom exercises · bodyweight_entries · daily_activity · daily_training_load · coach_outputs
user_directives · screenshot_usage · scan_balances · user_entitlements · password_reset_tokens
device_tokens · notification_preferences · whoop_connections · friend_requests (both columns)
friendships (both) · user_profiles → users
```

Two exceptions survive: **`admin_audit_log`** (neither `actor_user_id` nor `target_id` is an
FK, so purge never touches it) and **`purchase_records`**, whose `user_id` becomes nullable and is **SET NULL** rather than
deleted — refund disputes cite transaction ids and Apple holds the receipts. Response
`{tables: {name: rows}}`; audit `before` = those counts. A metadata test asserts every table with
an FK to `users.id` appears in `PURGE_ORDER`, so a future table
cannot be forgotten silently; the seeded end-to-end purge test is the guard on *order*. Verify
while building: `create_workout` must never let user B reference user A's custom exercise, or
deleting A's exercises cascades into B's `workout_exercises`
(`add_workout_cascade_fks.py:80-89`).

### 8.3 The sweep

| Option | Verdict |
|---|---|
| Railway cron service | second service + duplicated env — new infra. No |
| In-process scheduler | new dependency; v3 spec §9.2 already deferred a scheduler. No |
| Console button only | explicit and audited, but the promise then depends on memory |
| **Button + startup sweep** | `POST /admin/maintenance/purge-eligible {dry_run = true}` is the visible surface; a lifespan background task calls `purge_eligible()` 30 s after boot, audited with `actor NULL, reason = "startup sweep"`. Every push to `main` is a deploy, so "at least once per deploy" is real cadence at zero infra |

Gated by `PURGE_SWEEP_ENABLED` (**default false**; skipped on SQLite) so tests and the first
deploy are inert. Rollout: deploy, run the dry-run from the console, confirm the eligible list,
then set the flag on Railway. Never blocks boot: fire-and-forget task, try/except, one log line;
two instances racing find zero rows on the second delete.

---

## 9. Read surfaces and usage

### 9.1 User list and detail

`GET /admin/users` — filters `q` (email/username `ILIKE`), `deleted`, `unlimited`,
`active_days` (any `workout_sessions.local_date >= today − N`, `deleted_at IS NULL`); `sort`
(`last_active` default, `created`, `email`, `credits`) + `order`; `limit/offset` (keyset paging
is unnecessary at this scale). Row: id, email, username,
created, deleted state, `is_admin`, level/rank, last workout date, session count, credits,
unlimited.

`GET /admin/users/{id}` composes readers that already take a bare `user_id`:
`get_user_progress_summary` (`app/services/xp_service.py:240`), `get_active_campaign` +
`campaign_to_dict` + `hunt_on` (`app/services/campaign_service.py:304,1156,676`),
`get_load_state` (`app/services/training_load_service.py:596`), `compute_condition`
(`app/services/condition_service.py:210` — verify it takes `user_id`), the balance + purchases,
entitlements, WHOOP freshness (`last_synced_at`, scope — never the tokens), active device-token
count, the last 10 audit rows for `target_id`, and the per-user usage block. Every response is
an explicit Pydantic allow-list (no `from_attributes` dump of `User`).

### 9.2 Preview instead of impersonation

A "view as user" token was cut. It would need an `act_as` claim, an actor/subject split in
`get_current_user`, a write refusal in every user route, and it would misattribute slowapi keys
and Sentry tags — for N ≈ a handful. `get_current_user` accepting only `type == "access"` is the
control: no impersonation token exists that any user route honours. The feasible safe version is
the **`preview` block inside user detail** — what the Status tab shows (today's hunt, load
state, condition, progress, scan balance), composed server-side from the same services. No
separate route, no banner, no new auth semantics.

### 9.3 Usage

`admin_usage_service.py` ports `scripts/usage_snapshot.py:37-210` into dialect-neutral
SQLAlchemy: bucket by `local_date` with the `derive_local_date` fallback (the CLAUDE.md rule; the
script groups by `date`, `:42-45,59-66`, so some historical week buckets will shift), compute
ISO weeks in Python, drop `date_trunc` / `::date` (`:112,144,204`) so it runs on SQLite in tests.

- **Per user** (`GET /admin/users/{id}/usage?weeks=20`): sessions by ISO week split
  strength/cardio/other + miles, top exercises (12 wk), big-three weekly best e1RM (16 wk),
  session meta, gates by status, daily-activity coverage by source (30 d), integrations, scans
  (12 wk), runs (8 wk).
- **Fleet** (`GET /admin/usage`): users total / deleted / active 7 d / 30 d / purge-eligible;
  sessions and scans by week; balances (unlimited count, credits total); integrations; exercises
  total / custom / without family; **`unlimited_flag_drift`** (§6.2).

Read routes use a read-only transaction where the dialect supports it (precedent
`usage_snapshot.py:24`).

---

## 10. The console

### 10.1 Surface

**Static files served by FastAPI at `/admin/ui/`** — the `/privacy` pattern (`main.py:294-366`)
grown to three files (`app/admin_ui/index.html`, `admin.js`, `admin.css`) under one
`StaticFiles` mount, `include_in_schema=False`, no build step. Zero server-side interpolation:
the shell contains no data; every `fetch` carries the admin token; API base is
`window.location.origin`. Deploys on the same push as the endpoints it calls, so UI and API
cannot drift; works from the laptop and the phone; the Minimal Void tokens from
`docs/mockups/arise-v3-mockup.html` are a complete palette. Vanilla JS with a hash router is
enough for six screens; graduate to a bundled frontend (Vite output served from the same mount)
only when charts or a second admin arrive.

**Desktop-first, with a phone lane.** Control planes are operated at a desk: Stripe Dashboard,
RevenueCat, and Django admin are desktop-first with responsive layouts, and Stripe's mobile app
is a deliberately reduced lane for lookups and a few actions. This console follows that split.
The desktop layout is the primary design target (dense tables, a two-column customer view, a
side drawer for actions, JSON diffs). The phone gets a **scoped lane** rather than a responsive
fallback, because the highest-frequency actions — grant, adjust credits, restore — are triggered
by a friend's text message away from the laptop.

Rejected: **an in-app Hunter › Admin section** (every change is an Xcode build + TestFlight,
the laptop is excluded, pasted-JSON import and dry-run diffs are painful in native forms, and
the phone build would carry a privileged surface that must be hidden from every other user) and
**a separate Next.js / Retool app** (a second deploy target, auth integration, and env set — the
exact premature infra the house rules forbid; Retool would also need a third party on the prod
connection). Once the page exists, a Hunter › System Settings row that opens `/admin/ui/` in
Safari is a one-line iOS follow-up.

Headers on the page and on every `/admin/*` JSON: `Cache-Control: no-store`,
`X-Frame-Options: DENY`, and a CSP (`default-src 'self'; script-src 'self'` — the split into
`admin.js` removes the need for `'unsafe-inline'`). The global mobile touch rules apply to the
phone lane: delegated `click` on `closest('[data-action]')`, no inline handlers,
`touch-action: manipulation`, 44 px targets, `:active` feedback.

### 10.2 Information architecture

Desktop (≥ 1024 px): a 220 px left rail (wordmark, nav, a persistent search box, the session
countdown and admin email at the bottom) and a content area. Phone (< 768 px): a bottom tab bar
with Hunters · Audit · Overview; Catalog and Settings are not reachable. Hierarchy: **Fleet →
Hunter → per-user objects**; Catalog and Settings are fleet singletons.

| Screen | Purpose | Desktop | Phone lane |
|---|---|---|---|
| Overview | fleet numbers, **Attention** list (purge-eligible, exercises without family, unlimited drift), last audit rows | stat tiles + attention list with deep-link buttons + recent audit | tiles + attention list |
| Hunters | find a user | dense sortable table (id, email, username, rank·level, last active, sessions, credits/∞, campaign, WHOOP, state); filter chips Deleted / Unlimited / Inactive 30 d; sort headers via `sort`/`order` on `GET /admin/users` | search + filter chips; compact rows |
| Hunter detail | the customer view (§10.3) | header + two-column card grid + full-width danger zone | single column, quick-action order, Preview hidden |
| Audit | the append-only history | table (time, actor, action, target, reason, request id); a row expands to before/after JSON side by side; filters by actor / action / target | list; tap a row for the JSON |
| Catalog | `products` | table with active toggle (destructive when deactivating), edit drawer (credits, display name, sort), add a SKU | — |
| Settings | global defaults and kill switches | **read-only in v1** with a note "edit on Railway" (editing needs an `app_settings` table — §14) | — |

### 10.3 Hunter detail

Desktop: the identity header spans the width (rank-lettered avatar, username, email, truncated
id; chips: Active/Deleted, rank·level, credits or ∞, WHOOP, Override, Admin), then a two-column
card grid sized so the cards the owner touches most are visible without scrolling on a
13-inch laptop:

| Left column | Right column |
|---|---|
| `[ IDENTITY ]` email, username, created (+age), last active, experience · unit. Copy id | `[ PROGRESS ]` level·rank, XP, streak·longest, workouts·PRs, last workout. **Read-only** |
| `[ SCANS ]` credits, unlimited, reset date, used 30 d. **− / + Credits**, **Grant / Revoke unlimited** (revoke shows the source; purchase-sourced gets a warning line) | `[ INTEGRATIONS ]` WHOOP last sync / scope with a failure state, active push devices, HealthKit last seen. Read-only in v1 |
| `[ ENTITLEMENTS ]` override · default columns for free monthly, daily cap, cooldown. **Set limits**, **Reset to defaults** | `[ DATA HEALTH ]` exercises without a family (fleet count + this user's custom ones), sessions with `local_date` NULL, last backfill. **Dry-run backfill → Apply** |
| `[ PURCHASES ]` product, kind, credits, date, truncated transaction id. Read-only | `[ PREVIEW ]` the Status tab as the user sees it (§9.2) |
| `[ CAMPAIGN ]` name, status·source, start·current arc, arcs, next planned hunt. **Import / Replace** (template or pasted phases → dry-run → apply), **View arcs** | `[ AUDIT · THIS HUNTER ]` last rows scoped to this target; link to the full log |
| `[ DANGER ZONE ]` (full width) deleted state, days until purge. **Soft-delete** (active) / **Restore** + **Purge** (deleted) | |

Phone lane: one column in quick-action order — Scans → Entitlements → Danger zone (soft-delete /
restore; purge is desktop-only) → Identity → Progress → Purchases → Campaign (read-only; import is
desktop-only) → Integrations → Data health (read-only; backfill is desktop-only) → Audit. Preview
is hidden.

### 10.4 Interaction model

- **Action pattern.** Desktop: an action opens a **420 px right-side drawer**; the record stays
  visible behind it while the operator types the reason. Phone: a bottom sheet. Both show a
  field-level **before → after diff** (unchanged fields dimmed so the operator sees the full
  record state), a **required reason**, Cancel / Confirm. The form's diff is a preview; the server
  computes and stores the real one. Result: toast (top-right on desktop) with the summary and the
  new audit row id; the card re-renders. Dry-run actions render the proposal in the same drawer
  and turn Confirm into **Apply**. Esc closes the drawer.
- **Destructive tier.** Impact counts up front, typed-email unlock (purge), and the password
  re-prompt in the drawer (§4.5). Confirm stays disabled until the reason is typed and the typed
  email matches.
- **Tables.** Rows are clickable; header click sorts (server-side `sort`/`order`); filters are
  chips above the table; pagination at 50.
- **Login / expiry.** Email + password → admin session; countdown in the rail; a 401 from any
  call clears the in-memory token and returns to Login with the drawer's reason preserved.
- **Empty / loading / error.** Directive empty copy ("No hunter matches 'x' — check the Deleted
  filter"); skeleton rows, never spinners; errors as the app's `sysline` block with inline Retry;
  a failed mutation keeps the drawer open with the error above Confirm.
- **Idempotency.** Every credits form generates a UUID on open and sends it as
  `Idempotency-Key`; a retry after a network error reuses it.

### 10.5 Mockup

`docs/mockups/admin-control-plane-mockup.html` — desktop frames at 1280 px stacked vertically:
Hunters table, Hunter detail with the Adjust-credits drawer open, Hunter detail (deleted user)
with the Purge drawer open, Audit with one row expanded, Overview, Catalog + read-only Settings;
plus one phone-lane frame (search results and the detail in quick-action order with a
Grant-unlimited sheet open). Placeholder data only. Nothing in the mockup is outside v1.

---

## 11. Hygiene folded in (existing code on the same origin)

Found by the security review and verified against the code. Cheap, and they share the
console's origin or its auth path, so they ship in W0 rather than as a separate project.

| Anchor | Issue | Fix | Tier |
|---|---|---|---|
| `app/api/whoop.py:53-66` → `_callback_page` `:158` | the `error` query param is interpolated into HTML unescaped — reflected XSS on the API origin | `html.escape` title and message | MUST |
| `main.py:148` | prints Pydantic v2 `errors()` including `input` — verified: a weak-password register attempt echoes the password into Railway logs; admin bodies with `password`/`reason` would too | strip `input` and `ctx` from the log line (keep them in the 422 body) | MUST |
| `main.py:84-85` | OpenAPI is public | all `/admin/*` routes `include_in_schema=False` | MUST |
| `app/api/screenshot.py:168-207` → `:210-262` | the daily-count check runs before the balance lock, so two concurrent scans can both pass `DAILY_SCREENSHOT_LIMIT` | move the daily-count check after `with_for_update()` while wiring `effective_limits` | SHOULD |
| `app/api/scan_balance.py:83-153` | unverified purchases (§6.5) | interim caps now; JWS verification follow-up | MUST (interim) |
| `app/api/password_reset.py:56,86,89,91`, `app/services/email_service.py:106,109` | emails in INFO/ERROR logs become Sentry breadcrumbs despite `send_default_pii=False` (`main.py:54`) | log user ids | SHOULD |
| `app/api/friends.py:263` | `current_user.email` used as the push sender name shown to another user | `username or "A hunter"` | SHOULD |
| `app/api/workouts.py:173-190` | `debug-error` returns tracebacks when `DEBUG` (prod forbids DEBUG, `config.py:104`) | delete, or `include_in_schema=False` + keep the guard | SHOULD |
| `scripts/import_training_calendar.py:87-99` | a password passed on argv is visible in shell history and process lists | `getpass.getpass()` fallback when the env var is absent; retire the script once §7.2 ships | MUST |
| `backend/.env` | holds the prod public `DATABASE_URL` on the laptop | consider `railway run` injection; keep FileVault on | note |

---

## 12. Data model and migrations

Two revisions, chained from `v3_drop_quest_tables`, following the inspector-guarded pattern
(`alembic/versions/v3_exercise_families.py:35-53`), `batch_alter_table(recreate="always")` on
SQLite, and a `tests/test_v3_migrations.py`-style SQLite round-trip with a `CHAIN` list. CI runs
only `upgrade heads` on Postgres 15 (`.github/workflows/ci.yml:105`); the round-trip test is what
proves `downgrade`. New head: **`admin_seed_backfill`**.

| Revision | Upgrade | Downgrade |
|---|---|---|
| `admin_schema` | `users` + `is_admin` (bool NN default false), `token_version` (int NN default 0), `admin_failed_logins` (int NN default 0), `admin_locked_until` (datetime NULL); `purchase_records.user_id` → nullable; `admin_audit_log` + 3 indexes (partial unique guarded by `_has_index`) + PG-only append-only trigger; `products`; `user_entitlements` + indexes `(user_id, key)`, `(purchase_record_id)` | guarded drops; trigger drop; column drops via batch |
| `admin_seed_backfill` | insert-if-missing the 3 products (`scan_20` 20 consumable, `scan_50` 50 consumable, `scan_unlimited` non_consumable → `scans.unlimited`); insert `scans.unlimited` rows for `has_unlimited = true` users lacking an active one (§6.3) | no-op (never delete user data on downgrade) |

New settings (`app/core/config.py`): `ADMIN_BOOTSTRAP_EMAIL` (""), `ADMIN_TOKEN_EXPIRE_MINUTES`
(15), `ADMIN_LOCKOUT_THRESHOLD` (10), `ADMIN_LOCKOUT_MINUTES` (15), `PURGE_GRACE_DAYS` (30),
`PURGE_SWEEP_ENABLED` (false), `DAILY_SCREENSHOT_LIMIT` (20), `COOLDOWN_SECONDS` (10).

Models: `app/models/user.py` (+4 columns), `app/models/admin.py` (`AdminAuditLog`),
`app/models/entitlement.py` (`Product`, `UserEntitlement`), registered in
`app/models/__init__.py`. Test fixtures: a session-scoped `_products` seed mirroring
`_families` (`tests/conftest.py:88`), `admin_user`, `admin_headers`, `step_up_body`.

---

## 13. Contract registry

All under `/admin`, JSON snake_case, hidden from OpenAPI, `require_admin` unless noted, `no-store`.
Schemas in `app/schemas/admin.py`. `StepUpBody{password, reason}` marks the destructive tier.

| Method & path | Request | Response | Wraps |
|---|---|---|---|
| `POST /session` (no auth; `LOGIN_RATE_LIMIT` + lockout) | `AdminSessionRequest{email, password}` | `AdminSessionResponse{admin_token, expires_at}` | `admin_service.mint_admin_session`; audit `session.create` |
| `GET /me` | — | `AdminMeResponse{user_id, token_expires_at}` | `require_admin` |
| `GET /users` | `q?, deleted?, unlimited?, active_days?, sort=last_active\|created\|email\|credits, order=asc\|desc, limit=50, offset=0` | `AdminUserListResponse{items: [AdminUserRow], total}` | `admin_service.list_users` |
| `GET /users/{id}` | — | `AdminUserDetailResponse{user, profile, progress, balance{…, purchases}, entitlements, campaign?, integrations, data_health, preview, recent_audit, usage}` | `admin_service.get_user_detail` (§9.1) |
| `GET /users/{id}/usage` | `weeks=20` | `UserUsageResponse` (§9.3) | `admin_usage_service.user_usage` |
| `GET /usage` | `weeks=20` | `FleetUsageResponse` (§9.3) | `admin_usage_service.fleet_usage` |
| `POST /users/{id}/credits` (header `Idempotency-Key`) | `CreditsAdjustRequest{delta ≠ 0, reason, password?}` | `CreditsAdjustResponse{scan_credits_before, scan_credits_after, audit_id, replayed}` | `admin_service.adjust_credits` (`FOR UPDATE`); audit `credits.adjust` |
| `POST /users/{id}/entitlements` | `EntitlementGrantRequest{key, value, expires_at?, reason}` | `EntitlementResponse{id, user_id, key, value, source, granted_by, purchase_record_id?, expires_at, revoked_at, created_at}` | `entitlement_service.grant` + `sync_unlimited_flag`; audit `entitlement.grant` |
| `POST /users/{id}/entitlements/{eid}/revoke` | `StepUpBody` | `EntitlementResponse` | `entitlement_service.revoke` + sync; audit `entitlement.revoke` |
| `POST /users/{id}/campaign/import` | `AdminCampaignImportRequest(CampaignImportRequest){phases?, template?, dry_run=false, replace, name, start_date?, client_date?, goal?, objectives, password?}` | `AdminCampaignImportResponse(CampaignImportResponse){dry_run, retired_campaign_id?, planned_hunts_deleted, arcs_preview?}` | `parse_phases` / `import_campaign` + `create_objective`; audit `campaign.import` |
| `POST /maintenance/exercise-families` | `FamilyBackfillRequest{dry_run=true, reason, password?}` | `FamilyBackfillResponse{dry_run, families_changed, exercises_updated, assigned, total, unresolved}` | `ensure_families` / `assign_family_ids(dry_run=)`; audit on apply |
| `POST /maintenance/seed-achievements` | `ReasonBody` | `{seeded}` | `seed_achievement_definitions`; audit |
| `POST /maintenance/purge-eligible` | `PurgeSweepRequest{dry_run=true, password?, reason}` | `PurgeSweepResponse{eligible: [{user_id, deleted_at, days_deleted}], purged: [PurgeResponse]}` | `purge_service.purge_eligible` |
| `POST /users/{id}/delete` | `StepUpBody` | `AdminUserStateResponse{id, is_deleted, deleted_at}` | `admin_service.soft_delete_user`; audit `user.soft_delete` |
| `POST /users/{id}/restore` | `StepUpBody` | `AdminUserStateResponse` | `admin_service.restore_user` (+ `token_version`); audit `user.restore` |
| `POST /users/{id}/purge` | `PurgeRequest(StepUpBody){confirm_email, force=false}` | `PurgeResponse{user_id, deleted_at, tables: {str: int}, audit_id}` | `purge_service.purge_user`; audit `user.purge` |
| `GET /audit` | `target_type?, target_id?, actor_user_id?, action?, limit=50, offset=0` | `AuditListResponse{items: [AuditEntry], total}` | `admin_service.list_audit` |
| `GET /products` | — | `[ProductResponse]` | query |
| `POST /products` / `PATCH /products/{id}` | `ProductUpsertRequest{id, kind, credits, entitlement_key?, display_name, active, sort_order, password?, reason}` | `ProductResponse` | `admin_service.upsert_product` (id immutable; deactivate = step-up); audit `product.upsert` |
| `GET /ui` (no auth, no schema) | — | HTML + headers (§10.1) | file read |

Non-admin contract changes: `POST /scan-balance/verify-purchase` reads `products`, applies the
§6.5 caps, and accepts (and the follow-up will verify) `signed_transaction`; `/auth/login` and
`/auth/refresh` tokens gain `ver`. No iOS mirror changes in v1 — `ScanBalanceResponse` and
`PurchaseVerifyResponse` are unchanged — so `contract-mirror-check` is not triggered until the
iOS follow-up (pass `jwsRepresentation`; Admin console link).

---

## 14. Cut list — v2 with triggers, and never

| Item | Bucket | Trigger / why |
|---|---|---|
| Promote a second admin from the console | v2 | a second person needs the console; until then the bootstrap account is the only admin (§4.1) |
| Editable global settings (`app_settings` table) | v2 | the first time a kill switch must flip without a redeploy |
| Manual `family_id` assignment for one custom exercise | v2 | the first friend's custom lift the exact-match resolver leaves NULL and the prescription engine needs |
| `coach.debrief` per-user switch | v2 (global kill switch: open question §18) | every registered user currently triggers a weekly Opus call with no gate (`app/api/coach.py:46-65`) |
| Retry WHOOP sync, Send test push, Repair `local_date` | v2 | sketched in the mockup; none has a current failure to fix |
| Support notes on a user; promo credit codes; push broadcast; cohorts | v2 | more than a handful of users |
| Login-notification email on every admin session | v2 | noisy at a 15-min TTL; revisit if a second admin or an incident |
| Subscription expiry re-sync (`is_entitled()` in the scanner) | v2 | the first subscription SKU |
| App Store JWS verification of purchases | **follow-up session, before any non-trusted user** | §6.5 |
| Remove the public `seed-achievements` route | with the next iOS release | iOS calls it (§7.4) |
| Multi-admin RBAC, `role` enum | never (for now) | one admin; a boolean plus a promote route covers a second |
| MFA / TOTP / WebAuthn, IP allowlisting | never (for now) | one admin, 15-min token, step-up, DB lockout; phone-first on cellular makes IP lists unworkable |
| Separate admin deployable / subdomain, Retool | never | same secret, same DB; doubles deploy surface |
| Redis-backed limiter, second least-privilege DB role, hash-chained audit, SIEM export | never | single worker; the owning role can re-grant; Railway backups + trigger are proportionate |
| Impersonation tokens | never | §9.2 |
| XP / rank editor | never | v3 pillar 1 |
| Bulk user mutations, CSV export | never | blast radius; no need at this scale |
| A/B pricing, experiments | never | pricing has never been exercised against a real buyer |

---

## 15. Build phases

Each workstream ends with the v3 ship criteria: pytest + ruff, single alembic head, pathspec
commit, verified Railway SUCCESS. `/evaluate` after W0 and after W2 (4+ files, multi-layer).

| Phase | Scope | Size | Ship signal |
|---|---|---|---|
| **W0 — foundations** | models + both migrations (§12); `Settings` additions; `admin_auth.py` (`create_admin_token`, `require_admin`, `verify_step_up`); `admin_bootstrap.py` (bootstrap + sweep hook); `audit_service.py`; `entitlement_service.py` (`ensure_products`, `is_entitled`, `effective_limits`, `grant`, `revoke`, `sync_unlimited_flag`, `get_or_create_balance`); rewire `scan_balance.py` (products, entitlement path, interim caps) and `screenshot.py` (`effective_limits`, daily check after the lock); `user_token_claims()` + `ver` in login / refresh / `get_current_user`; hygiene (§11 MUSTs); conftest fixtures; `test_admin_auth`, `test_admin_entitlements`, `test_admin_migrations`, mass-assignment and token-class tests | ½ session | `ADMIN_BOOTSTRAP_EMAIL` set on Railway → `POST /admin/session` returns a token; `GET /scan-balance` unchanged for every user; the two rate-limit tests patch `settings` |
| **W1 — reads** | `api/admin.py` (`/session`, `/me`, `/users`, `/users/{id}`, `/users/{id}/usage`, `/usage`, `/audit`, `/products` GET); `admin_service.list_users` / `get_user_detail`; `admin_usage_service`; router in `main.py` with `no-store` + `include_in_schema=False`; `test_admin_users`, `test_admin_usage`, `test_admin_audit` (read half) | ⅓ session | the next "how is X doing" is a `curl` of `/admin/users/{id}`, not `usage_snapshot.py` |
| **W2 — mutations** | credits (+ idempotency), entitlement grant/revoke, products upsert, campaign import (+ `campaign_templates/owner_hybrid.json`, parser moved), family backfill `dry_run`, seed-achievements, soft-delete / restore, `purge_service` + sweep; `test_admin_credits`, `_campaign_import`, `_families`, `_purge`, `_step_up`, `_audit` (parametrized); script docstrings → "fallback — prefer `/admin/ui`" | ½ session | grant-unlimited via `curl` yields the row the script yields; **purge is the slip point** if the session runs long |
| **W3 — console** | `app/admin_ui/{index.html, admin.js, admin.css}` on a `StaticFiles` mount at `/admin/ui/` + headers + CSP; desktop layout first, then the phone lane; `test_admin_ui`; v3 spec §11 row (line 719) → points at the console; memory update | ½ session | the full customer view is readable on a 13-inch laptop without scrolling the top of both columns; login → grant → ∞ on the phone in under a minute; `PURGE_SWEEP_ENABLED` flipped after a clean dry-run |
| **Follow-ups** | JWS verification (server); iOS: pass `jwsRepresentation`, Hunter › System Settings "Admin console" link, drop the public seed route | own sessions | |

Total: **~2 sessions.** W0 → W1 → W2 share files (`admin.py`, `entitlement_service.py`,
`scan_balance.py`, `screenshot.py`, conftest) and run as one agent in sequence; W3 can be a
second agent against the frozen W1/W2 contracts.

---

## 16. Tests

| File | Key cases |
|---|---|
| `test_admin_auth.py` | session 200 admin / 401 bad password / 403 non-admin / 423 locked; access token on `/admin/users` → 401; admin token on `/workouts` → 401; expired → 401; `is_admin` flipped mid-session → 403; `ver` mismatch → 401; bootstrap flips once, idempotent, case-insensitive, refuses > 1 match, writes an audit row; every `/admin` path in `app.routes` → 401 with no token and 403 with a normal user's admin attempt; `{"is_admin": true}` ignored on register / profile / username |
| `test_admin_step_up.py` | parametrized over the destructive service list: wrong password → 401 and no audit row; 5 failures → `token_version` bump; counter resets on success |
| `test_admin_users.py` | filters, search, pagination; detail composes every block on a fresh user (no balance, no campaign, no sessions) and never emits `password_hash`; soft-delete → login 403; **restore → login 200 and a pre-deletion refresh token → 401**; 409 on state mismatch; self/admin refused |
| `test_admin_credits.py` | ± delta with before/after; negative → 409; same key + same body → one change, one audit row, `replayed`; same key + different body → 422; missing key → 400; `> 50` needs step-up |
| `test_admin_entitlements.py` | grant `scans.unlimited` → flag true and `_reserve_scan_credits` passes with 0 credits (`_seed_balance`, `tests/test_scan_credit_transaction.py:49`); revoke → 402 path; revoke of a purchase-sourced row survives `restore-purchases`; `daily_limit = 2` → 429 on the third; `cooldown_seconds = 0`; `free_monthly = 10` → reset credits 10; expired row ignored; unknown key → 422; `verify-purchase` of the unlimited SKU creates a `source = purchase` row; products drive `credits_added`; inactive product → 400; interim caps (101 credits / 24 h → 409; second unlimited → 409; non-numeric id → 422) |
| `test_admin_audit.py` | one row per mutation with the sent `X-Request-ID`; failure after `audit()` → no row (monkeypatch); no mutating route under `/admin/audit`; PG trigger test `skipif` on SQLite; allow-list never contains email / hash / token keys |
| `test_admin_purge.py` | not deleted → 409; inside grace → 409; `force` + reason + password + `confirm_email` → 200; wrong `confirm_email` → 422; admin / self → 403; a user seeded across every table is gone, `purchase_records.user_id` is NULL, the audit row remains with `target_id`; **metadata: every FK to `users.id` is in `PURGE_ORDER`** (audit actor exempt); `purge_eligible` dry-run lists only > 30 d; sweep is inert when `PURGE_SWEEP_ENABLED` is false and on SQLite |
| `test_admin_campaign_import.py` | phases vs template; both / neither → 422; 409 without `replace`; replace retires + deletes future hunts and records the count; dry-run writes nothing; the committed template reproduces 3 arcs / 21 templates / 0 warnings |
| `test_admin_families.py` | dry-run returns unresolved and writes nothing; apply updates custom rows; second apply → 0 |
| `test_admin_usage.py` | fleet + per-user on SQLite bucketed by `local_date`; drift list |
| `test_admin_migrations.py` | `CHAIN = ["admin_schema", "admin_seed_backfill"]` round-trip; products seeded; backfill rows; re-run no-op |
| `test_admin_ui.py` | `/admin/ui/` 200 with `no-store`, `X-Frame-Options`, CSP; `/admin/users` JSON `no-store`; no inline `onclick` in `index.html` or `admin.js`; `sort`/`order` on `/admin/users` |
| existing | `test_scan_balance_api.py:19` stops importing `PRODUCT_CREDITS`; the two rate-limit tests patch `settings`; a symbol test asserts the scripts and the routes import the same service functions |

---

## 17. Success metrics

| Job | Metric | Baseline | Target |
|---|---|---|---|
| O1–O3 | owner script runs against prod in the 30 days after W3 | 3 in one session (2026-09-05) | 0 |
| O1 | seconds from phone unlock to ∞ visible in the app (phone lane) | minutes + a laptop | ≤ 60 |
| O4 | a user's full customer view readable on a 13-inch laptop without scrolling the top of both columns | `usage_snapshot.py` output in a terminal | yes |
| O5 | admin-driven changes to `has_unlimited`, `campaigns.status`, `users.is_deleted` with a matching audit row | 0% | 100% (asserted by tests; shown as a reconciliation count on Audit) |
| O6 | soft-deleted accounts recovered without a terminal | impossible | one console action |
| Trust | prod credentials required in a terminal for a routine owner task | `DATABASE_URL` + a password | none |
| Trust | purchase rows with no matching entitlement provenance | unknown | 0 on the fleet view |

---

## 18. Risks and open questions

**Risks**

1. **`verify-purchase` remains self-serve** until JWS verification ships; the interim caps bound
   the damage (≤ 100 credits / day, one unlimited ever, owner email) and the console makes it
   visible, but a trusted user base is the real control today.
2. **Cached `has_unlimited` drift** if a future writer bypasses `sync_unlimited_flag()`;
   mitigated by the single-writer convention, the migration backfill, and the drift list.
3. **Purge order** for non-cascading child FKs (`prs.set_id`, `pr_gates.cleared_by_set_id` /
   `planned_hunt_id`, `goal_progress_snapshots.workout_id`, `goals.campaign_id`); the metadata
   test catches missing tables, only the seeded end-to-end test catches wrong order.
4. **Per-account lockout** lets an attacker lock the owner out of the console for 15 minutes at
   a time; break-glass is one SQL line (§4.4).
5. **Bootstrap re-promotes every boot**, so an accidental demotion is undone by the next deploy;
   acceptable because demotion = remove the env var.
6. **Usage buckets shift** versus the script's historical output once aggregates use `local_date`
   (the CLAUDE.md rule) — expected, not a bug.
7. **Test churn**: three test files patch module constants that move into `Settings`; the
   `settings` monkeypatch precedent keeps the change mechanical.

**Open questions**

1. `coach.debrief` global kill switch in v1 (one flag + a 503)? Recommended if friends onboard
   before v2's per-user overrides.
2. Will friends' plans be authored as `data.js` phases (the console needs the parser) or created
   in-app via `POST /campaign` (`app/api/campaign.py:97`)? Determines whether admin import stays
   owner-only.
3. `PURGE_GRACE_DAYS = 30` matches `/privacy` — any plan to change the policy text?
4. Keep the three scripts as documented fallbacks (the memory note says yes) or delete after one
   clean month?

---

## 19. Security review checklist (self-check before each workstream ships)

- [ ] Zero request paths set `users.is_admin = true`; the bootstrap promotes an existing account, affects ≤ 1 row, and audits.
- [ ] Admin authority is read from the DB on every `/admin` request; demotion is instant regardless of outstanding tokens.
- [ ] `require_admin` enforces `type == "admin"` explicitly, decodes with `audience`, checks `ver`, and is attached at the router.
- [ ] Admin token ≤ 15 min, no refresh, `ver` claim, JS memory only.
- [ ] Every destructive action re-verifies the password and requires a reason; purge also requires `confirm_email`.
- [ ] Every mutation is single-target; backfill and sweep are dry-run by default.
- [ ] Audit row in the same transaction; neither audit id column is an FK; allow-listed before/after; PG trigger.
- [ ] Response schemas are explicit allow-lists; audit JSON and logs carry ids only.
- [ ] Restore bumps `token_version`; `/auth/refresh` checks `ver`.
- [ ] Admin UI files are static, `no-store`, `X-Frame-Options: DENY`, CSP without `'unsafe-inline'`; `/admin/*` hidden from OpenAPI.
- [ ] `/admin/session`: `LOGIN_RATE_LIMIT` + DB lockout; counter increments only on bad-password 401s.
- [ ] `verify-purchase` interim caps in place; revoke survives `restore-purchases`.
- [ ] Purge: 30-day grace unless `force`; audit rows survive; `purchase_records` unlinked not deleted; sweep behind `PURGE_SWEEP_ENABLED`.
- [ ] No impersonation token is accepted by `get_current_user`.
- [ ] Tests named in §16 exist: route enumeration, mass-assignment, token-class rejection both ways, same-transaction audit, purge-keeps-audit, step-up enforcement.
- [ ] WHOOP callback escaped; validation log strips `input`; `getpass` in the import script.

---

## 20. Revision log

- **v1 (2026-09-05):** initial draft from the four-role council and one security ↔ engineer
  cross-review. Council decisions recorded against the PM's leaner draft: `users.is_admin` +
  bootstrap over an env-only allowlist; a separate 15-minute admin token in memory over reusing
  the app token or a 12-hour cookie; `user_entitlements` + `products` in v1 with the cached
  `has_unlimited` kept; purge in v1 as an explicit ordered service plus an opt-in startup sweep;
  impersonation replaced by a server-composed preview; the designer's extra actions (retry sync,
  test push, repair dates, editable settings) cut to v2. Security cross-review added: case
  collision guard on the bootstrap email, lockout counted only on bad passwords, `body_sha256`
  beside the idempotency key, `purchase_records.user_id` SET NULL on purge, `PURGE_SWEEP_ENABLED`,
  `sync_unlimited_flag` inside the balance lock, daily-count check after the lock, and the
  interim purchase caps.

- **v1.1 (2026-09-05, evening):** console re-targeted **desktop-first with a scoped phone lane**
  after the owner's review ("the web app should be the first-class experience"). §10 rewritten:
  left rail + dense tables + two-column customer view + right-side drawer on desktop; the phone
  keeps search, Scans / Entitlements / Danger zone, and Audit as a bottom-sheet lane; Catalog,
  Settings, fleet usage, and paste-JSON import are desktop-only. Static page split into three
  files on one `StaticFiles` mount (CSP without `'unsafe-inline'`); `sort`/`order` added to
  `GET /admin/users`; a desktop readability criterion added to W3 and §17; mockup redone at
  1280 px with one phone-lane frame.

- **v1.2 (2026-09-06, W0 build):** amendments from the W0 `/evaluate` pass. `admin_audit_log.actor_user_id`
  is a plain string, not an FK — the SET NULL cascade would have been an UPDATE the append-only
  trigger rejects, and the trail should keep the actor id after a purge. Purchase caps are checked
  under the balance lock; the 5/day cap is a DB count, not a slowapi limit. A completed password
  reset bumps `token_version`. `get_or_create_balance` gains `commit=False` for callers inside a
  transaction so `grant`/`revoke` never commit underneath the audit row. The break-glass
  `grant_owner_unlimited_scans.py` now grants through `entitlement_service` and audits as the
  system actor; `import_training_calendar.py` prompts for the password with `getpass`.

- **v1.3 (2026-09-06, W2 build):** amendments from the W2 build and `/evaluate` pass. The
  committed template lives at `backend/campaign_templates/owner_hybrid.json` (§7.2). Campaign
  import audits with `target_type = user` / `target_id = <target user>` (the campaign id is in
  `after`) so the row shows in the hunter's audit view; a dry run answers 200, not 201. Purge
  maps a foreign non-cascading reference (another account's goal on the target's custom
  exercise) to 409 instead of a 500, `create_objective` now refuses another user's custom
  exercise (the `create_workout` rule), and a sweep that loses the two-instance race writes no
  zero-count audit row. `ensure_families` / `assign_family_ids` / `seed_achievement_definitions`
  gained `dry_run` / `commit` keywords (defaults unchanged) so the console commits the change
  and its audit row together.
