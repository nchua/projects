# App Store Launch — Implementation Spec

**Status:** draft, 2026-09-06 · **Companion to:** [`app-store-launch.md`](./app-store-launch.md) (the phased checklist) and [`app-store-metadata.md`](./app-store-metadata.md) (ASC copy)

This spec covers only the **engineering work** left before submission. Purely
human App Store Connect actions (signing the Paid Applications Agreement, creating
the app record and IAP products, the age-rating questionnaire) live in the
checklist, not here.

Gates already closed in `e311c94` and `74baed3` — privacy manifest accuracy, export
compliance, the production APNs entitlement split, `/terms` + `/support`, the
preflight script, and iPhone-only device family — are **not** repeated here.

---

## Scope

| Gate | Deliverable | Blocking? |
|---|---|---|
| **G1** | App Review demo account + seed data | Yes — Guideline 2.1 |
| **G2** | Screenshot capture | Yes — required ASC asset |
| **G3** | Legal/support deploy + a real inbox | Yes — required ASC field |
| **G4** | Production hardening (narrowed, see §G4) | No — but cheap |
| **G5** | App-name rollout procedure | Yes, when the name is chosen |
| **G6** | Release procedure | Yes |

### Non-goals

- **StoreKit JWS server-side verification.** `verify-purchase` still trusts the
  client's `transaction_id`. Deliberately deferred: the §6.5 interim caps (numeric
  ids only, daily verification count, daily credit cap, one unlimited grant per
  account, owner alert on every unlimited grant, all under the balance row lock)
  bound the damage. Revisit once real money is moving.
- **Redis-backed rate limiting.** See §G4.3 — flagged, not scheduled.
- Renaming the "Shadow Monarch" S-rank title, and the final app name itself. Both
  deferred by decision; §G5 makes the rename a single mechanical sweep when ready.
- iPad support. Decided against for v1.0.

### Decisions locked

| Decision | Value | Date |
|---|---|---|
| Launch path | Direct App Store submission, no TestFlight beta | 2026-09-06 |
| Device family | iPhone only (`TARGETED_DEVICE_FAMILY = 1`) | 2026-09-06 |
| Legal hosting | Railway backend routes | 2026-09-06 |
| Screenshot method | Manual capture, scripted setup | 2026-09-06 |
| G4 depth | Rate limits + cost ceiling; no JWS work | 2026-09-06 |

---

## G1 — App Review demo account

**Why it blocks:** the app is fully login-gated. A reviewer with no credentials
cannot see past the auth screen, and Guideline 2.1 rejection is automatic. The
same seeded data also makes G2's screenshots look like a real user's account
rather than a set of empty states.

### G1.1 Seed script

New file: `backend/scripts/seed_review_account.py`

Model it on `scripts/grant_owner_unlimited_scans.py`, which already establishes
the conventions this script must follow:

- `load_dotenv` + `sys.path.insert` bootstrap, `import app.models` to register
  every model before touching the session.
- Credentials from the environment, **never** literals. Reuse the existing
  `SEED_USER_EMAIL` / `SEED_USER_PASSWORD` names. A hardcoded credential in this
  repo has already caused one GitGuardian incident; the script must fail loudly
  with a usage message when either variable is unset.
- **Never log the email or password**, matching `grant_owner_unlimited_scans.py`.
- Idempotent: a second run updates the existing account in place and reports what
  changed. Re-running before a resubmission must not duplicate history.

```
Run from fitness-app/backend:
    SEED_USER_EMAIL=<reviewer email> SEED_USER_PASSWORD=<password> \
      venv/bin/python scripts/seed_review_account.py
```

### G1.2 What the account contains

Goal: a plausible ~10 weeks of training, ending *yesterday* so nothing looks stale
and no session sits in the future.

| Data | Target | Notes |
|---|---|---|
| Workout sessions | ~30 over 10 weeks, 3/week | Push/pull/legs split; realistic durations and session RPE |
| Exercises per session | 4–6 | Draw from the seeded exercise table, not free text, so families and analytics resolve |
| Sets per exercise | 3–4 | Weights must progress over the 10 weeks or the trend charts are flat and the app undersells itself |
| Personal records | Several, spread across weeks | Must fall out of the set data via the normal e1RM path — do **not** insert PR rows directly |
| Bodyweight entries | Weekly, gentle trend | Populates the bodyweight chart |
| Profile | Age, sex, height set | Several analytics surfaces are gated on these |
| Scan entitlement | `scans.unlimited` | Via `entitlement_service.grant_from_purchase`-equivalent admin path, exactly as `grant_owner_unlimited_scans.py` does — that is the only sanctioned writer of `scan_balances.has_unlimited` (control-plane spec §6.2) |
| Rank/level | Whatever XP falls out | Do not force a rank; let the real progression compute it |

**Derived state must be derived.** PRs, e1RM, XP, level, and rank all have to come
out of the same code paths a real user hits. Hand-inserting them produces an account
that looks right on screen but is internally inconsistent — and it means the
screenshots show numbers the app cannot actually reproduce.

### G1.3 HealthKit and WHOOP

Neither can be seeded — HealthKit lives on-device and WHOOP needs a real OAuth
grant. Both are already optional, and the app must stay fully functional without
them. The App Review notes in `app-store-metadata.md` §3 already say so explicitly;
verify that claim is still true by running the demo account with Health permission
denied before submitting.

### G1.4 Acceptance

- [ ] Script runs clean twice in a row; second run reports "already seeded".
- [ ] Script exits non-zero with a usage message when either env var is missing.
- [ ] `grep -rn "@" backend/scripts/seed_review_account.py` shows no literal address.
- [ ] Log in as the account on a device: Home, Progress, History, and PRs are all
      populated. No empty states, no zeroes, no placeholder text.
- [ ] Scan a screenshot end-to-end without hitting the credit wall.
- [ ] Credentials pasted into ASC → App Review Information.

---

## G2 — Screenshots

**Method:** manual capture with scripted setup. No XCUITest target — five screens
once does not justify a new target plus accessibility identifiers across the app.

**Set required:** iPhone 6.9" only (iPhone-only was decided; no iPad set).
Confirm exact pixel dimensions in ASC at upload — Apple revises them.

### G2.1 Setup

```bash
xcrun simctl boot "iPhone 17 Pro Max"
xcrun simctl status_bar booted override \
  --time "9:41" --batteryLevel 100 --batteryState charged --cellularBars 4 --wifiBars 3
# build + install the Release app, log in as the G1 demo account, then per screen:
xcrun simctl io booted screenshot ~/Desktop/appstore/01-status.png
```

### G2.2 Shot list

Ordered by what carries the pitch — most users only ever see the first two.

| # | Screen | Must prove |
|---|---|---|
| 1 | Home / Status | The identity: rank, level, XP |
| 2 | Scan → extracted result | The "logs itself" claim, made concrete |
| 3 | Progress / e1RM trend | Real strength math over real history |
| 4 | Personal records | Payoff and progression |
| 5 | Readiness / recovery | The Health + WHOOP differentiator |

### G2.3 Rules

- Real app UI only. No mockups, no marketing renders, no composited device frames
  containing non-app content — Guideline 2.3.
- Every screen populated (this is what G1 is for).
- No debug overlays, no placeholder copy, no other user's data.
- Shot 5 needs recovery data present; if WHOOP is not connected on the capture
  device, either connect it or drop shot 5 rather than showing an empty state.

### G2.4 Acceptance

- [ ] 5 PNGs at the ASC-required 6.9" dimensions.
- [ ] Status bar consistent across all five.
- [ ] A second person can tell what the app does from shots 1–2 alone.

---

## G3 — Legal, support, and a real inbox

### G3.1 Deploy

`/terms` and `/support` exist in `backend/main.py` and are covered by
`tests/test_legal_pages.py`, but are **not deployed**. Push to `main` → Railway
auto-deploys. `preflight-appstore.sh` fails until all three return 200.

Per project convention, confirm `railway status --json` reports SUCCESS after the
push — a multi-head alembic state fails the deploy while the old instance keeps
serving, which masks the failure.

### G3.2 The inbox is the real work

`/privacy` advertises `privacy@arise-fitness.app` and `/support` and `/terms`
advertise `support@arise-fitness.app`. **Confirm that domain exists and receives
mail.** A dead contact address on a published privacy policy is worse than no
address: Apple may mail it, and users certainly will.

Options, cheapest first: forwarding addresses on a domain already owned; a new
domain with email forwarding; or change the pages to an address that already works.
If the app name changes (§G5), the domain likely changes with it — so either settle
the name first, or use an address that survives a rename.

### G3.3 Acceptance

- [ ] `curl -s -o /dev/null -w "%{http_code}" .../privacy` → 200, same for `/terms`, `/support`.
- [ ] `bash ios/scripts/preflight-appstore.sh` passes with zero issues.
- [ ] A test message to the support address arrives somewhere a human reads.

---

## G4 — Production hardening

**Narrowed after reading the code.** The endpoints are better defended than a
first pass suggested, so this gate is much smaller than scoped:

- `/screenshot/process` already enforces a per-user daily cap
  (`DAILY_SCREENSHOT_LIMIT`, default 20), a cooldown (`COOLDOWN_SECONDS`,
  default 10s), and credit debit — `screenshot.py:129-182`. Stronger cost control
  than an IP rate limit would be.
- `/password-reset/request` already enforces a per-email 2-minute cooldown and
  returns identically whether or not the account exists; `/verify` enforces a
  per-token attempt limit and bumps `token_version` on success —
  `password_reset.py:47-123`.
- Login (`5/10min`), registration (`20/10min`), and admin login are rate limited,
  keyed on the last X-Forwarded-For hop to survive Railway's edge proxy.

### G4.1 Global Anthropic spend ceiling — the actual gap

Every existing control is **per user**. Aggregate spend across all users is
unbounded, and `scans.unlimited` is a one-time payment against an unbounded
recurring cost. One shared screenshot on social media is all it takes.

Add a global daily ceiling on vision calls, enforced before the Anthropic request:

- `ANTHROPIC_DAILY_CALL_CEILING: int = Field(default=...)` on `Settings`, following
  the `PURCHASE_MAX_*` pattern in `app/core/config.py`.
- Sum `ScreenshotUsage.screenshots_count` since UTC midnight **without** the
  `user_id` filter — the same table and column `_assert_daily_cap`
  (`screenshot.py:129`) already reads per user, so no new table and no new writes.
- Over ceiling → HTTP 503 with a "try again tomorrow" message that does **not**
  debit a credit, matching the existing timeout behaviour at `screenshot.py:375`.
- Fire `send_owner_alert(subject, body)` on the first breach of a day, as
  `verify-purchase` already does for unlimited grants — via `BackgroundTasks`,
  since SendGrid is a blocking HTTP call and must stay off the event loop. **Alert before the ceiling
  is reached, not only at it** — a ceiling you learn about by being down is a
  worse outage than a bill.
- Set the ceiling from real usage plus generous headroom; the goal is catching
  runaway abuse, not throttling a good day.

### G4.2 IP-level limit on password-reset request

Minor. The per-email cooldown stops repeat-mailing one address, but one IP can
spray many addresses — mail-send cost and sender-reputation damage, not account
compromise. Add `@limiter.limit(...)` to `/password-reset/request` with a
`REGISTER_RATE_LIMIT`-style constant in `app/core/rate_limit.py`, documenting the
shared-NAT reasoning the way the existing constants do.

### G4.3 Rate-limit storage — flag only, not scheduled

`rate_limit.py:50` carries a standing TODO: the limiter uses in-memory storage,
which is **per-worker and resets on every deploy**. Login brute-force protection is
therefore weaker in production than the `5/10minutes` constant implies. The fix is
`storage_uri="redis://..."`. Out of scope for launch; it should not be discovered
during an incident.

### G4.4 Acceptance

- [ ] Ceiling breach returns 503, debits no credit, and alerts the owner once.
- [ ] Tests cover: under ceiling passes, over ceiling 503s, alert fires once per day.
- [ ] Password-reset request rate limit has a test.
- [ ] `ruff check .` clean; full suite green.

---

## G5 — App-name rollout

Deferred, but mechanical once chosen. **The name must change everywhere in one
sweep** — a half-renamed app is an obvious 2.3 rejection.

| Location | What changes |
|---|---|
| `ios/project.yml` | `INFOPLIST_KEY_CFBundleDisplayName` **and** `info.properties.CFBundleDisplayName` (both currently "Fitness Tracker") |
| `ios/project.yml` | `NSHealthShareUsageDescription`, `NSHealthUpdateUsageDescription`, `NSPhotoLibraryUsageDescription` — all three say "Arise" |
| `backend/main.py` | `<title>` and body copy on `/privacy`, `/terms`, `/support` |
| `backend/app/core/config.py` | `APP_NAME` (currently "Fitness Tracker API") |
| `docs/app-store-metadata.md` | Every `{APP_NAME}` placeholder |
| App Store Connect | App name (30), subtitle (30) |
| Support/privacy email domain | See §G3.2 |

`PRODUCT_BUNDLE_IDENTIFIER`, the IAP product IDs, and `APNS_TOPIC` **must not
change** — the bundle ID is immutable once the ASC record exists, and the product
IDs are mirrored in `entitlement_service.py` and enforced by preflight.

Run `xcodegen generate` after editing `project.yml`; `Info.plist` is generated.

---

## G6 — Release procedure

1. Lock the name (§G5) and create the ASC record.
2. Bump `CFBundleShortVersionString` / `CFBundleVersion` in `ios/project.yml`
   (**not** `Info.plist` — xcodegen regenerates it). Every upload needs a unique,
   increasing `CFBundleVersion`.
3. `cd ios && xcodegen generate`
4. `bash ios/scripts/preflight-appstore.sh` — must exit 0.
5. Xcode → Product → Archive (Release), then Distribute → App Store Connect.
6. Confirm ASC shows **no** export-compliance prompt (proves the plist key took).
7. Attach all three IAPs to the version so they review together.
8. Paste demo credentials and review notes (`app-store-metadata.md` §3).
9. Upload screenshots and metadata; submit.
10. **After release**, verify on a real device against production: a push actually
    arrives (this is what the entitlements split protects), a purchase completes,
    and a scan processes. Sandbox passing does not prove production works.

---

## Sequencing

G3 and G4 are independent of everything else — do them first, they are small and
G3 unblocks preflight. G1 gates G2. G5 gates G6.

```
G3 (deploy + inbox) ─┐
G4 (ceiling + limit) ─┼─→ G6 (release)
G1 (demo account) ──→ G2 (screenshots) ─┘
G5 (name) ───────────────────────────────┘
```

In parallel and off the critical path: the Paid Applications Agreement. It blocks
all IAP including sandbox testing and takes business days. **Start it now.**
