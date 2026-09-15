# ARISE Owner Console v2 — The Admin's Workbench

> **Status:** v2.3 — W4 (data & API) shipped 2026-09-13, W5 (Hunters · Overview · Change plan) 2026-09-14,
> W6 (Detail · Settings · Audit/Catalog · phone lane) 2026-09-15; what remains is the §7.3 cut list. Supersedes §10 of
> `docs/arise-control-plane-spec.md` (v1.5) for the *console*; everything else in that spec —
> identity, sessions, step-up, audit, entitlements, purge, the JWS verification — stays in force
> and is referenced, not restated. Council record for v1:
> `plans/COUNCIL_SUMMARY_admin-control-plane_2026-09-05.md`. Build target: a later session
> (W4–W6 of the control plane).
>
> **Why a v2:** the W3 console shipped the *machinery* (login, drawers, step-up, audit toasts,
> phone lane) on top of the v1 information architecture, and the owner's first real use showed
> the IA is a dashboard, not a workbench: the Overview tiles are dead ends, the Hunters table is
> ids and stats rather than people and plans, "plan" exists nowhere as a thing you can see or
> change in one place, and the numbers the owner wants to adjust (free scans, caps) are
> read-only. v2 keeps the machinery and redoes the surface around the admin's jobs.
>
> **Decisions carried over and not re-opened (v1 §20):** `users.is_admin` via bootstrap only;
> the 15-minute admin token in JS memory; `token_version` revocation; step-up password + reason
> for the destructive tier; same-transaction append-only audit; `user_entitlements` +
> `products` with `scan_balances.has_unlimited` as the cached single-writer flag; explicit
> `PURGE_ORDER` and the opt-in sweep; no impersonation; static files on one `StaticFiles`
> mount; desktop-first with a scoped phone lane.
>
> **Mockup:** `docs/mockups/admin-console-v2-mockup.html` (four screens: Hunters + Change
> plan drawer, Hunter detail, Overview launchpad, Settings; example data).
>
> **Chunks:** 1 Jobs, principles, plan & status model · 2 Screens and navigation · 3 Actions
> and drawers · 4 API and data changes · 5 Phases, tests, cut list.

---

## 1. Jobs to be done, ranked by frequency

Written from the owner's seat, with the trigger that starts each job. The ranking drives the
IA: the top four must be reachable in one click from anywhere, the rest in two.

| # | Job | Trigger | Today | v2 |
|---|---|---|---|---|
| 1 | **Find a person** by username or email and see their plan, credits and status at a glance | a text message ("my scans stopped working") | search box → table row shows id-first columns; plan is implied by a credits/∞ cell | search matches username *and* email; the row shows **name · email · plan · credits · status · last active**; ⌘K jump-to-user |
| 2 | **Change someone's plan** — put a friend on Unlimited, take it away, or top up credits | a favour, a refund, a bug apology | two drawers on the detail page (Grant/Revoke unlimited, ± Credits) | one **Change plan** drawer on the row *and* on the detail: pick the target plan, see the before → after, confirm |
| 3 | **See who is actually using the app** | curiosity, a launch week, deciding who to message | Overview tiles; the Hunters "Active 30 d" chip | Hunters default view = Active, sorted by last active; tiles are links into that view |
| 4 | **Adjust the free tier and the caps** for everyone | a cost scare, a promo, a launch | Railway env vars + redeploy | **Settings** screen edits `free_monthly`, `daily_limit`, `cooldown_seconds`, the purchase caps and the Anthropic ceiling, audited, live on the next request |
| 5 | **Clean up junk accounts** (bots, test signups, abandoned installs) | the purge-eligible count climbs | Attention row → dry-run sweep → apply | Hunters filter **Purge-eligible** → select rows → **Purge selected** (dry run → apply) |
| 6 | **Answer "did they pay?"** | a support question, a chargeback email | Purchases card on the detail | same card, first-class: verified badge, environment, amount, and the plan it produced |
| 7 | **See what I did last week** | "did I already grant that?" | Audit screen | Audit unchanged plus an **Activity** strip on each hunter's detail |
| 8 | **Repair one person's data** (family backfill, reseed achievements, reimport a campaign) | a bug report | Data health card, Campaign card | folded into a collapsed **Diagnostics** section on the detail; fleet-wide versions stay on Overview › Maintenance |
| 9 | **Turn a product on or off** | App Store review, a pricing change | Catalog | unchanged (already a table with an edit drawer) |
| 10 | **Flip a kill switch** (screenshot processing, sweep, JWS required) | an incident | Railway | Settings › Switches, audited, with the env var as the fallback |

Not jobs (and therefore not screens): watching charts, reading a user's workouts, messaging
users, refunds (App Store owns them), promo codes, cohorts.

---

## 2. Principles

1. **Every number is a link.** A count on Overview is a saved filter on Hunters; a count on a
   detail card is the list it summarises. Nothing on the console is display-only unless it is
   genuinely terminal (a timestamp, an id).
2. **The table is the product.** Hunters is the home screen in practice. It must answer jobs
   1, 3 and 5 without leaving it: search, filters as URL state, sortable columns, row actions,
   bulk selection. The detail page exists for the one-person jobs (2, 6, 7, 8).
3. **One concept per column.** "Plan" is one word with four values, computed on the server.
   "Status" is one word with four values. The console never asks the owner to infer either from
   a flag plus a balance plus a date.
4. **Change the thing where you see it.** Plan is changed from the plan chip. Credits from the
   credits cell. Settings from the settings row. No "go to the detail page to do that".
5. **Same guardrails, fewer drawers.** The v1 tiering stays exactly as is (reason for every
   mutation; step-up password for the destructive tier; typed email for purge; dry run before
   any bulk apply). The *number* of distinct drawers goes down because plan change is one
   action, not three.
6. **Operational first, diagnostic second.** Progress, Preview, Data health, Campaign and
   Integrations move below the fold into a collapsed section. They are still one click away;
   they no longer compete with Scans and Plan for the top of the page.
7. **Nothing new on the phone that is not already a job.** The phone lane keeps jobs 1, 2, 3
   and 7 (find, change plan, see active, see audit). Bulk purge and Settings stay desktop-only.

---

## 3. The plan model (derived, server-side)

There is no `plan` column. `plan` is computed by one function,
`entitlement_service.plan_for(db, user_id) -> Plan`, from the rows that already exist, and
returned on every user row and detail. It is the single definition the table, the chips, the
drawer and the audit `before/after` all use.

### 3.1 Values

| Plan | Definition (evaluated in this order) | Chip |
|---|---|---|
| **Unlimited** | an active `scans.unlimited = true` entitlement row (v1 §6.1 active rule: unrevoked and unexpired) | green `∞ UNLIMITED`, with a source tag: `purchase` / `admin` / `backfill` |
| **Override** | not Unlimited, and at least one active row among `scans.free_monthly`, `scans.daily_limit`, `scans.cooldown_seconds` | amber `OVERRIDE`, with the overridden keys |
| **Credits** | not Unlimited, no override, and `scan_balances.scan_credits > effective free_monthly` — i.e. they hold *purchased* credits beyond the free grant | blue `CREDITS · n` |
| **Free** | everything else (including "no balance row yet") | dim `FREE · n / free_monthly` |

Notes:
- Unlimited beats Override so an unlimited friend who also has a custom daily cap reads as
  Unlimited; the cap still applies and shows on the detail as a secondary line.
- "Credits" is a judgment call: the free grant refills monthly, so a balance *at or below*
  the free allotment is still the Free plan. Purchased credits are what make it a paid state.
  The threshold is the user's *effective* free monthly (override-aware), not the global default.
- `plan_source` accompanies Unlimited (`purchase` when the active row has a
  `purchase_record_id`, else `admin_grant` / `backfill` — the row's `source`).

### 3.2 What "upgrade" and "downgrade" mean

**Purchased credits belong to the hunter.** No plan change ever removes credits: someone who
bought a pack keeps it on every tier, and the balance only goes down by scanning. The
**Change plan** action (chunk 3) therefore has three targets, not four — `Free` is never a
target, it is what you land on when Unlimited is removed and no purchased credits remain.
Each target maps to existing v1 mutations, in one transaction with one audit row
(`user.plan_change`, before/after = the two `Plan` snapshots):

| Target | Server operations | Resulting plan | Tier |
|---|---|---|---|
| **Unlimited** | `grant(scans.unlimited, true, source=admin_grant, expires_at?)` — expiry defaults to *Never*, 30 / 90 days one click away | Unlimited | standard (reason) |
| **Top up credits** | `adjust_credits(+n)` with the idempotency key; `n` chosen in the drawer | Credits (or Unlimited if they already have it — the credits wait underneath) | standard; step-up when `n > 50` (v1 rule) |
| **Remove Unlimited** | `revoke` the active unlimited row(s). Purchase-sourced rows get the v1 guard line ("survives Restore Purchases"). Credits untouched. | Credits if purchased credits remain, else Free | **destructive** (step-up) |
| any ↔ **Override** | Set limits / Reset to defaults (v1) — a separate drawer reachable from the Override chip; not part of Change plan | Override / underlying | standard |

Removing credits is possible only through **Adjust credits** (a negative delta, for a refund
or a mistaken top-up), never through Change plan; the v1 rule applies (step-up above 50) and
the drawer says whose credits they are. Change plan never touches `products` or
`purchase_records`. It never writes `has_unlimited` directly (`sync_unlimited_flag` remains the
only writer).

### 3.3 Status model (derived, server-side)

| Status | Definition | Chip |
|---|---|---|
| **Active** | not deleted, and `last_active ≥ now − 30 d` | green |
| **Inactive** | not deleted, and `last_active < now − 30 d` (or never active) | dim |
| **Deleted** | `is_deleted`, inside the `PURGE_GRACE_DAYS` window | amber, with "purges in n d" |
| **Purge-eligible** | `is_deleted` and `deleted_at ≤ now − PURGE_GRACE_DAYS` (v1 §8.2) | red |

`last_active` is new on the row: `max(last_workout local_date, last screenshot usage, last
login)` — v1 only had `last_workout_date`. The 30-day threshold is the v1 "Active 30 d" window
made explicit and is a Settings value (`inactive_after_days`, default 30), so the owner can move
it without a deploy.

`is_admin` stays a separate boolean chip (`ADMIN`) — it is not a status.

### 3.4 Where the models surface

| Surface | Shows |
|---|---|
| Hunters row | `plan` chip (+ credits number), `status` chip, `last_active` |
| Hunter header | both chips, the plan source, the expiry if any |
| Overview tiles | counts *by plan* and *by status* — each a link to the filtered table |
| Audit `before/after` for `user.plan_change` | the two `Plan` snapshots (`plan`, `plan_source`, `scan_credits`, `expires_at`) |
| Phone lane | the same chips on the list rows and the header |

---

*End of chunk 1. Chunk 2 — Screens and navigation — specifies Overview as a launchpad, the
Hunters table (columns, filters, sort, search, bulk selection, saved views), the reduced Hunter
detail, editable Settings, and the phone lane.*

---

## 4. Screens and navigation

### 4.1 Shell

Desktop (≥ 1024 px): the v1 shell stays — 220-px left rail (wordmark, nav, session countdown,
admin email), content area, 420-px push drawer. Two additions:

- **⌘K / Ctrl-K jump-to-user.** A palette over the rail's search box: type a username, email
  or id fragment; results are the top 8 rows from `GET /admin/users?q=`; Enter opens the
  hunter, ⇧Enter opens **Change plan** on that hunter without leaving the current screen. This
  is job 1 and job 2 from anywhere.
- **Nav order by job frequency:** Hunters · Overview · Audit · Settings · Catalog. Hunters is
  the default route (`#/` → `#/hunters`); Overview is no longer the landing screen.

Phone (< 768 px): bottom tabs Hunters · Overview · Audit (Settings and Catalog answer "desktop
only", as v1). The ⌘K palette is the search field at the top of Hunters.

### 4.2 Overview — a launchpad

The screen keeps its stat tiles but every tile is a link into a filtered Hunters view, and the
tiles are re-cut by the plan and status models (§3) instead of raw counters.

| Tile | Number | Sub-line | Opens |
|---|---|---|---|
| **Active** | status = Active | "of *n* not deleted · *m* new this week" | `#/hunters?status=active` |
| **Inactive** | status = Inactive | "no activity in *inactive_after_days* d" | `#/hunters?status=inactive` |
| **Unlimited** | plan = Unlimited | "*p* purchase · *a* granted · *b* backfill" | `#/hunters?plan=unlimited` |
| **Credits** | plan = Credits | "*c* purchased credits outstanding" | `#/hunters?plan=credits` |
| **Deleted** | status = Deleted | "purge in ≤ *PURGE_GRACE_DAYS* d" | `#/hunters?status=deleted` |
| **Purge-eligible** | status = Purge-eligible | "past the grace window" | `#/hunters?status=purge_eligible` |
| **Scans · 4 wk** | screenshots | "*x* free · *y* paid · *z* unlimited" | `#/hunters?sort=scans_4wk&order=desc` |
| **Sessions · this week** | sessions | ISO week · hunters | `#/hunters?status=active&sort=last_active` |

Below the tiles:

- **Attention** (v1) keeps its rows, but each row is a link (purge-eligible → the filtered
  table; exercises without family → Overview › Maintenance with the backfill drawer open;
  drift → the affected hunters). Rows with nothing to do are hidden, not shown as "No … drift".
- **Maintenance** (new, replaces the fleet actions that were hidden inside Attention): three
  buttons — Backfill exercise families (dry run → apply), Re-seed achievements, Purge sweep
  (dry run → apply). Same drawers as v1 `FLEET_SPECS`.
- **Recent audit** (v1): last 10 rows, each a link to the target.

Gone from Overview: the WHOOP / push-device counts (they live on Settings › Integrations as
read-only lines) and the "13 credits across 2 balances" phrasing (replaced by the Credits tile).

### 4.3 Hunters — the home screen

**Columns** (desktop), in this order; the first four are always visible, the rest hide
progressively below 1280 px:

| Column | Source | Sortable | Notes |
|---|---|---|---|
| **Hunter** | `username` (bold) over `email` (muted) | `email` | one cell, two lines; the row is one click target → detail. Admin chip inline. |
| **Plan** | `plan` chip + credits number (§3.1) | `plan` | click → **Change plan** drawer for that row (no navigation) |
| **Status** | `status` chip (§3.3) | `status` | Deleted / Purge-eligible show "n d" |
| **Last active** | `last_active` relative ("3 d ago") with the absolute date on hover | `last_active` (default, desc) | |
| Scans · 4 wk | `scans_4wk` | yes | |
| Sessions | `session_count` | yes | |
| Rank | `rank · level` | `level` | |
| Joined | `created_at` | yes | |
| ⋯ | row menu | — | Change plan · Adjust credits · Set limits · Soft-delete / Restore · Copy id · Open in new tab |

**Filters** are chips above the table and are *URL state* (`#/hunters?status=…&plan=…&q=…`),
so every tile, every Attention row and the browser back button land on a reproducible view:

- **Status**: Active · Inactive · Deleted · Purge-eligible (multi-select; default = Active +
  Inactive, i.e. "not deleted").
- **Plan**: Free · Credits · Unlimited · Override (multi-select; default = all).
- **Joined**: last 7 d · 30 d · 90 d · any.
- **Search**: username / email / id substring (the existing `q`), debounced 250 ms.
- **Saved views** (client-side, `localStorage`, per browser): the current filter + sort +
  visible columns under a name; three ship pre-seeded — *Paying* (plan = Unlimited ∪ Credits),
  *Cleanup* (status = Purge-eligible), *New this month* (joined ≤ 30 d). Server-side saved
  views are a v3 item.

**Sort**: click a header; the arrow shows direction; `sort` / `order` are URL state. New
sort keys the API must support: `plan`, `status`, `last_active`, `scans_4wk`, `level`,
`created_at`, `email` (chunk 4).

**Bulk selection**: a checkbox column (desktop only). Selecting rows reveals a sticky action
bar: **Change plan…**, **Soft-delete**, **Restore**, **Purge…** (only when every selected row
is Purge-eligible), **Export CSV** (the visible columns of the selected rows; client-side).
Bulk actions run through the same drawers with a row list at the top and a per-row result
list at the end (chunk 3). Bulk is capped at 100 rows per apply.

**Row density**: 44-px rows on desktop (v1's rule already), 56-px on the phone with Hunter ·
Plan · Status stacked.

**Empty and loading states**: skeleton rows (v1 `loadScreen`), and an empty state that names
the active filters with a one-click "Clear filters".

### 4.4 Hunter detail — four operational cards, then diagnostics

**Header** (full width): rank-lettered avatar, username, email (click to copy), id (short,
click to copy), joined + age; chips: `plan` (click → Change plan), `status`, `ADMIN`,
`WHOOP` when connected. Right-aligned primary actions: **Change plan**, **⋯** (Adjust credits ·
Set limits · Soft-delete / Restore · Copy id).

**Operational cards** (two columns on ≥ 1024 px, one on the phone), sized so all four are
visible without scrolling on a 13-inch laptop:

| Left | Right |
|---|---|
| **PLAN** — current plan with source and expiry; the override keys if any (override · default columns as v1); the last plan change (who, when, reason) from the audit. Actions: **Change plan**, **Set limits**, **Reset to defaults** | **ACCOUNT** — status with the purge countdown, email, username, created, last active (workout / scan / login, whichever is latest, and which), token version, admin lockout state. Actions: **Soft-delete** / **Restore**, **Purge** (desktop, deleted only) |
| **SCANS** — credits, effective free monthly and its reset date, used 7 d / 4 wk, daily cap and cooldown in effect, today's count vs the cap. Actions: **Adjust credits** (− / +) | **PURCHASES** — one row per receipt: product, kind, credits or ∞, date, `verified · env` / `unverified` badge (shipped 2026-09-12), transaction id (short, copy), and the entitlement it produced (link to the Plan card's history). Read-only. |

**Diagnostics** (collapsed by default, one full-width section, remembers open/closed per
browser): the v1 Progress, Campaign (with Import / Replace), Integrations, Data health (with
this hunter's Backfill), Preview. Content and actions unchanged from v1 §10.3; only their
position changes.

**Activity** (full width, below Diagnostics): the audit rows for this target (v1 "Audit · this
hunter") extended with the hunter's *own* recent actions the audit does not record — last 5
sessions and last 5 scans as one merged, dated list. Read-only. Answers "is this person alive"
without opening Usage.

**Gone from the detail page**: nothing is removed; the Danger Zone card is folded into
ACCOUNT's actions, and Purge keeps its typed-email drawer.

### 4.5 Settings — editable, audited

Settings becomes three groups of editable fields, each row showing **current · default ·
source** (`console` when an `app_settings` row exists, `env` when the Railway var applies,
`code` when neither). Editing is a drawer with the before → after diff, a reason, and — for the
kill switches and the purge grace — step-up. Every edit writes one audit row
(`settings.update`, before/after = the changed keys) and takes effect on the next request (no
redeploy; chunk 4 defines the read path and cache).

| Group | Keys (v1 `Settings` names) | Tier |
|---|---|---|
| **Scanner** | `FREE_MONTHLY_SCANS`, `DAILY_SCREENSHOT_LIMIT`, `COOLDOWN_SECONDS`, `PURCHASE_MAX_CREDITS_PER_DAY`, `PURCHASE_MAX_VERIFICATIONS_PER_DAY`, `ANTHROPIC_DAILY_CALL_CEILING`, `ANTHROPIC_DAILY_CALL_WARN_PERCENT` | standard (reason) |
| **Accounts** | `inactive_after_days` (new, §3.3), `PURGE_GRACE_DAYS` | `PURGE_GRACE_DAYS` is destructive (it changes who is purge-eligible; must match `/privacy`) |
| **Switches** | `SCREENSHOT_PROCESSING_ENABLED`, `PURGE_SWEEP_ENABLED`, `PURCHASE_REQUIRE_JWS`, `PURCHASE_ALLOWED_ENVIRONMENTS` | destructive (step-up); the JWS flip drawer shows the count of unverified rows in the last 30 d as a warning |

Per-user overrides (Set limits) win over these globals, as in v1 §6.1: resolution is
per-user row → `app_settings` → env → code default.

Read-only lines at the bottom: **Integrations** (WHOOP app configured?, APNs topic /
sandbox, SendGrid configured?, Sentry on?), **Build** (git sha, deploy time from Railway env),
**Admin** (bootstrap email, token TTL, lockout thresholds). These remain env-only on purpose:
changing them is a deploy-time decision.

### 4.6 Audit and Catalog — small fixes only

- Audit: the `target` cell links to the hunter or product; the `action` filter is a select
  populated from the actions seen; a **Mine** chip (actor = me). Otherwise v1.
- Catalog: unchanged except the table gains a **Sold** column (purchase count, verified count)
  so a product deactivation drawer can say what it affects.

### 4.7 Phone lane

Jobs 1, 2, 3, 7 only. Hunters: search + Status/Plan chips, rows with Hunter · Plan · Status;
tapping the plan chip opens Change plan as a bottom sheet (v1 sheet engine); tapping the row
opens the detail with PLAN and SCANS first, ACCOUNT next, Purchases, then Diagnostics collapsed.
Overview: the tiles (still links) and Attention. Audit: the list. No bulk selection, no
Settings, no Purge.

---

*End of chunk 2. Chunk 3 — Actions and drawers — specifies the Change plan drawer (single and
bulk), Adjust credits, Set limits, the Settings edit drawer, bulk soft-delete / restore / purge
with dry-run, the confirm and result patterns, and the exact tier of each action.*

---

## 5. Actions and drawers

The v1 drawer engine (`*Spec(detail)` factories: fields / diff / validate / `password: true |
fn(v)` / confirmLabel / submit / onSuccess; `dryRun{run, render, canApply}` for two-step
actions; the engine owns reason, typed-email and password inputs, the gate, the error line,
the toast with the audit id) is kept as is. v2 adds four specs, retires two, and gives every
spec a **bulk mode** — the same drawer with a row list on top and a per-row result list at the
end.

### 5.1 The action registry

| Action | Where it opens from | Tier | Server (chunk 4) | Audit action |
|---|---|---|---|---|
| **Change plan** | plan chip (row, header), row menu, bulk bar, ⌘K ⇧Enter | standard; **step-up** when any target is *Remove Unlimited* | `POST /admin/users/{id}/plan` · bulk `POST /admin/users/plan` | `user.plan_change` |
| **Adjust credits** | Scans card, row menu | standard; **step-up** when `|delta| > 50` (v1) | `POST /admin/users/{id}/credits` (v1, unchanged; Idempotency-Key) | `user.credits` (v1) |
| **Set limits / Reset** | Plan card, Override chip | standard | v1 entitlement grant / revoke routes | `entitlement.grant` / `.revoke` (v1) |
| **Soft-delete** / **Restore** | Account card, row menu, bulk bar | **step-up** (v1) | v1 routes · bulk `POST /admin/users/state` | `user.delete` / `user.restore` (v1) |
| **Purge** | Account card (deleted only), bulk bar (all rows purge-eligible) | **step-up + typed email**; bulk = typed count | v1 route · bulk `POST /admin/users/purge` (dry run → apply) | `user.purge` (v1) |
| **Edit setting** | Settings row | standard (Scanner, `inactive_after_days`); **step-up** (`PURGE_GRACE_DAYS`, every Switch) | `PATCH /admin/settings/{key}` | `settings.update` |
| Backfill families · Re-seed · Sweep | Overview › Maintenance, Diagnostics | v1 (dry run → apply; sweep apply is step-up) | v1 | v1 |
| Product edit / new | Catalog | v1 | v1 | v1 |

Retired: **Grant unlimited** and **Revoke unlimited** as separate drawers (both are Change
plan targets). Credits adjust stays because "top up 20" is the most frequent single action
and deserves a two-field drawer.

### 5.2 Change plan

**Header:** "Change plan" · the hunter (username · email) or "*n* hunters · a, b, c, +*k*".

**Targets** (radio list; each row shows the target, what it does in one line, and how many of
the selected hunters already hold it — those are skipped, never re-applied):

1. **Unlimited** — "grant scans.unlimited". Field: **Expires** (Never · 30 d · 90 d · custom
   date; default Never). A hunter already Unlimited is skipped *unless* the new expiry differs,
   in which case the drawer says "extend / shorten" and the server revokes + re-grants in one
   transaction.
2. **Top up credits** — "add purchased credits". Field: **Credits** (number, default 20,
   step 1, presets 20 · 50). Applies to everyone selected, including Unlimited hunters (the
   credits wait underneath).
3. **Remove Unlimited** — "revoke the grant · purchased credits stay". Only enabled when at
   least one selected hunter is Unlimited; purchase-sourced rows get the v1 guard line
   ("survives Restore Purchases — the hunter loses what they paid for until you grant again").
   Step-up.

**Diff block** (always visible before Confirm): one line per hunter, `before → after` in plan
terms (`credits · 42 → unlimited · admin · exp 2026-10-13`), or `unchanged (skipped: already
unlimited)`. The Confirm label counts only the rows that will change: "Apply to 3 hunters".

**Reason** (required, ≥ 3 chars, v1). **Password** appears only for target 3.

**Result:** single → toast "Plan changed · audit 7c1a" and the row/header re-renders; bulk →
the drawer stays open with a per-row list (✓ changed · – skipped · ✕ failed: reason) and one
**Done** button; the audit toast links the *first* audit id and the Audit screen filter
`request_id` groups the batch.

### 5.3 Adjust credits (v1 drawer, two amendments)

- The delta field shows the hunter's **purchased** credits beside it ("42 purchased · 3 free")
  so a negative delta is visibly bounded; the server refuses a delta that would take the balance
  below zero (v1 409) and the drawer pre-validates the same.
- A line under the field: "Purchased credits are the hunter's. Remove them only for a refund or
  a mistaken top-up." Step-up above 50 as in v1.

### 5.4 Bulk mode (shared by Change plan, Soft-delete, Restore, Purge)

- Opens from the sticky bulk bar with the selected ids (max **100**; the bar says "100 of 143
  selected — narrow the filter" beyond that and disables the actions).
- The drawer lists the rows (username · email · current plan/status), then the action's own
  fields, then the diff, then reason (+ password / typed count).
- **Purge (bulk)** is two-step: dry run (`POST /admin/users/purge` with `dry_run: true`)
  renders the per-user table counts exactly as the v1 sweep does; Apply requires the password
  and the **typed row count** ("type 12 to confirm") instead of the typed email; only rows whose
  status is Purge-eligible are accepted — the server 422s any other id.
- **Partial failure:** the server applies each row in its own transaction and returns
  `{applied: [...], skipped: [...], failed: [{id, error}]}`; the drawer shows the three groups.
  Nothing is rolled back for a sibling's failure (decision 4). One audit row per applied user,
  all sharing the batch's `X-Request-ID`.
- **Soft-delete / Restore (bulk):** skipped rows are the ones already in the target state;
  Restore bumps `token_version` per user as in v1.

### 5.5 Edit setting

Opens from a Settings row. Shows **key**, the human label, **current** (with its source
chip), **default**, and one typed input (number / seconds / boolean switch / comma list for
`PURCHASE_ALLOWED_ENVIRONMENTS`). The diff block shows `current → new` and the source that will
apply after the edit (`console`). Reason required. Step-up for `PURGE_GRACE_DAYS` and every
Switch. Two switches carry a live warning line in the drawer:

- **Require signed receipts** (`PURCHASE_REQUIRE_JWS`): "*n* purchases in the last 30 d arrived
  unsigned — those builds will fail to buy until updated." (from `purchase_records.verified`).
- **Purge sweep on deploy** (`PURGE_SWEEP_ENABLED`): "*n* accounts are purge-eligible right now
  and will be purged on the next deploy." (the Overview count).

**Reset to default** is a second button in the same drawer: deletes the `app_settings` row so
the env/code value applies again; audited as `settings.update` with `after = null`.

### 5.6 Confirm and result patterns (unchanged from v1, restated for the build)

- Every drawer: fields → diff → reason → (password | typed confirmation) → Confirm; Enter
  never bypasses a disabled Confirm; the error line sits above Confirm; a 401 probes
  `GET /admin/me` once (live token ⇒ "Incorrect password", dead token ⇒ Login, reason kept).
- Every success: toast with the audit id (or an `auditLookup` by target), then the screen
  re-renders from a fresh fetch — never from the drawer's own optimistic state.
- Two-step actions (dry run → apply) keep the dry-run output on screen while Apply runs.

### 5.7 Phone lane actions

Change plan (all three targets, step-up included — decision 6) and Adjust credits as bottom
sheets from the plan chip / Scans card; Soft-delete / Restore from the Account card. No bulk
bar, no Purge, no Settings edits. Sheet fields are 44-px targets; the diff block collapses to
one line per hunter.

---

*End of chunk 3. Chunk 4 — API and data changes — specifies `plan_for` / `status_for`, the new
row fields and sort keys, the three bulk routes, the `app_settings` table, its resolution and
read path, `users.last_login_at`, the migrations, the schemas, and what stays frozen.*

---

## 6. API and data changes

The v1 "admin API frozen" rule is lifted for exactly what this section lists. Everything not
listed stays as shipped (auth, session, step-up, audit, products, purge order, usage, campaign
import, maintenance, JWS verification).

### 6.1 Derived models (services)

- `entitlement_service.plan_for(db, user_id) -> Plan` and
  `plans_for(db, user_ids) -> Dict[str, Plan]` — the batch form is what the list uses
  (three queries per page: active `scans.*` entitlements for the ids, balances, effective
  free monthly), never N+1. `Plan` is a frozen dataclass: `plan` (`free | credits |
  unlimited | override`), `plan_source` (`purchase | admin_grant | backfill | None`),
  `expires_at`, `scan_credits`, `purchased_credits` (= `max(0, credits − effective
  free_monthly)`), `free_monthly`, `override_keys`.
- `admin_read_service.status_for(user, last_active, now) -> Status` (`active | inactive |
  deleted | purge_eligible`) using `settings_service.get("inactive_after_days")` and
  `PURGE_GRACE_DAYS`.
- `last_active` = `max(last workout local_date, last screenshot_usage, users.last_login_at)`
  with `last_active_kind` (`workout | scan | login`) — one correlated subquery each, batched
  per page.

### 6.2 `GET /admin/users` (list)

New query params: `status` (csv of the four statuses; default `active,inactive`), `plan`
(csv of the four plans; default all), `joined_days` (7 | 30 | 90), `sort` gains `plan`,
`status`, `last_active` (default), `scans_4wk`, `level`, `created_at`, `email`. The v1
`deleted` / `unlimited` / `active_days` params keep working (mapped onto `status` / `plan`)
so nothing breaks, but the console stops sending them.

`AdminUserRow` gains: `plan`, `plan_source`, `plan_expires_at`, `purchased_credits`,
`free_monthly`, `status`, `last_active`, `last_active_kind`, `scans_4wk`. `has_unlimited` and
`scan_credits` stay (mirrors elsewhere read them). Sorting by `plan` / `status` is done in SQL
over a CASE expression that reproduces §3 (the derived value must sort the same as it
displays — a test asserts equality against `plans_for` for a seeded page).

### 6.3 `GET /admin/users/{id}` (detail)

`AdminUserDetailResponse` gains three blocks and one list; nothing is removed:

- `plan: AdminPlanBlock` — the `Plan` fields + `last_change` (`{at, actor, action, reason,
  audit_id}` from the newest `user.plan_change | user.credits | entitlement.*` audit row).
- `account: AdminAccountBlock` — `status`, `purge_at`, `last_active`, `last_active_kind`,
  `last_login_at`, `token_version`, `admin_locked_until`.
- `scans: AdminScansBlock` — `scan_credits`, `purchased_credits`, `free_monthly`,
  `free_scans_reset_at`, `used_7d`, `used_4wk`, `today_count`, `daily_limit`,
  `cooldown_seconds`.
- `activity: List[AdminActivityRow]` — the last 20 of: audit rows for this target (v1
  `recent_audit`, kept), sessions, screenshot usages, logins (`last_login_at` only — one
  row); `{at, kind, summary, actor, audit_id?}`, newest first.

### 6.4 New mutation routes (all on `mutation_router`, all audited, all in `MUTATIONS`)

| Route | Body | Response | Rules |
|---|---|---|---|
| `POST /users/{id}/plan` | `PlanChangeRequest(OptionalStepUpBody){target: unlimited \| topup \| remove_unlimited, expires_at?, credits?, reason}` | `PlanChangeResponse{user_id, before: Plan, after: Plan, skipped: bool, audit_id}` | `topup` requires `credits ≥ 1`, step-up when `> 50`; `remove_unlimited` requires step-up; `unlimited` on an already-unlimited user with the same expiry → `skipped=true`, no audit row; different expiry → revoke + grant in one transaction. Never writes `has_unlimited` (goes through `grant` / `revoke` → `sync_unlimited_flag`). |
| `POST /users/plan` | `BulkPlanChangeRequest{user_ids: List[str] (1–100), …same fields}` | `BulkResult{applied: [PlanChangeResponse], skipped: [{user_id, why}], failed: [{user_id, error}]}` | one transaction **per user**; a failure is recorded and the loop continues; every audit row carries the request's `X-Request-ID` |
| `POST /users/state` | `BulkStateRequest(StepUpBody){user_ids, action: delete \| restore, reason}` | `BulkResult` | per-user transaction; already-in-state → skipped; restore bumps `token_version` (v1) |
| `POST /users/purge` | `BulkPurgeRequest(DryRunBody){user_ids, dry_run=true, password?, confirm_count?, reason}` | dry run: `[{user_id, tables}]`; apply: `BulkResult` | every id must be `purge_eligible` else **422** naming the first offender; apply needs password + `confirm_count == len(user_ids)`; reuses `purge_service.purge_user` per id |
| `GET /settings` | — | `[SettingRow{key, label, group, type, value, default, source: console \| env \| code, tier, warning?}]` | `warning` carries the live counts for the two dangerous switches (§5.5) |
| `PATCH /settings/{key}` | `SettingUpdateRequest(OptionalStepUpBody){value: Any \| null, reason}` | `SettingRow` | `null` = reset (delete the row); key must be in `SETTINGS_REGISTRY`; value validated by the registry type; step-up for `PURGE_GRACE_DAYS` and every switch |

Audit actions added: `user.plan_change` (before/after = the two `Plan` snapshots),
`settings.update` (before/after = `{key: value}`; `after = null` on reset). Both go through
`audit()` in the same transaction as the change (v1 §5).

### 6.5 `app_settings` and the resolver

Table `app_settings` (`key` PK string, `value` JSON, `updated_at`, `updated_by`). A
`SETTINGS_REGISTRY` in `app/core/settings_registry.py` lists every editable key with `label`,
`group`, `type` (`int | seconds | bool | csv`), `tier`, `min/max`, and the `Settings`
attribute it shadows. `settings_service.get(db, key)` resolves **`app_settings` → env / code
(`settings.<KEY>`)** and is one indexed primary-key read per call (decision 8: no cache).

Read sites that move to the resolver (grep-verified 2026-09-13): `purge_service`
(`PURGE_GRACE_DAYS` ×2, `PURGE_SWEEP_ENABLED` ×2 — the startup sweep reads it inside the
lifespan where a session exists), `entitlement_service.default_scan_limits`
(`FREE_MONTHLY_SCANS`, `DAILY_SCREENSHOT_LIMIT`, `COOLDOWN_SECONDS`), `screenshot.py`
(`SCREENSHOT_PROCESSING_ENABLED`, `ANTHROPIC_DAILY_CALL_*`), `scan_balance.py`
(`PURCHASE_MAX_*`, `PURCHASE_REQUIRE_JWS`, `PURCHASE_ALLOWED_ENVIRONMENTS`), and the new
`inactive_after_days`. Per-user entitlement overrides still win over all of these (v1 §6.1).
Tests that monkeypatch `settings.X` keep working because the resolver falls through to
`settings` when no row exists.

### 6.6 `users.last_login_at`

Set in `POST /auth/login` (success) and `POST /auth/refresh`; nullable; backfilled from
nothing (existing users read `null` until their next login, and `last_active` falls back to
workouts / scans).

### 6.7 Migrations

One revision `console_v2` chained from `purchase_verification`: create `app_settings`; add
`users.last_login_at`. Inspector-guarded, SQLite batch mode, no data changes. `CHAIN` in
`test_admin_migrations.py` extended; head assertions in `test_v3_migrations.py` and
`test_quest_drop_migration.py` updated.

### 6.8 Schemas and mirrors

All new schemas extend `UTCModel` and are explicit allow-lists. No iOS mirror exists for any
admin schema; `contract-mirror-check` is not triggered unless an iOS file changes. `admin.js`
is the only consumer.

---

## 7. Build phases, tests, cut list

### 7.1 Phases (one session each, each ends green and deployed)

| Phase | Ships | Exit criterion |
|---|---|---|
| **W4 — data & API** | §6 entirely: `plan_for` / `plans_for` / `status_for`, `last_active`, list params + sort keys, detail blocks + activity, the four mutation routes, `GET/PATCH /settings`, registry + resolver + moved read sites, `console_v2` migration, `MUTATIONS` cases, tests | `GET /admin/users?status=purge_eligible&plan=free` returns rows with `plan` / `status`; `POST /users/{id}/plan` moves a seeded user Free → Unlimited → Credits(top-up) → remove → Credits with the right audit rows; `PATCH /settings/FREE_MONTHLY_SCANS` changes the next `GET /scan-balance` for a fresh user without a restart; prod check after deploy |
| **W5 — Hunters, Overview, Change plan** | `#/` → Hunters; the table (§4.3) with filters as URL state, sort, columns, bulk bar, saved views (localStorage), CSV; ⌘K; Overview tiles as links + Attention + Maintenance (§4.2); Change plan drawer single + bulk (§5.2, §5.4); Adjust credits amendments (§5.3); bulk soft-delete / restore / purge | from Overview › Purge-eligible → select 3 → Purge dry run → apply, in the browser; Change plan from a row chip without leaving the table; phone: search → plan chip → sheet → apply |
| **W6 — Detail, Settings, phone** | Hunter detail (§4.4) with the four cards, Diagnostics collapsed, Activity; Settings editable (§4.5, §5.5) incl. warnings and Reset; Audit / Catalog fixes (§4.6); phone lane (§4.7) | the four cards fit a 13-inch laptop without scrolling; flipping `PURCHASE_REQUIRE_JWS` from Settings shows the unsigned count and writes `settings.update`; phone lane drives jobs 1, 2, 3, 7 |

Each phase: `/evaluate --against docs/admin-console-v2-spec.md` (point it at the phase's
section), fix every Error, `/simplify`, pathspec commit, push, `deploy-watch`, one prod check.

### 7.2 Tests (additions to the v1 registry)

| File | Cases |
|---|---|
| `test_plan_model.py` (new) | `plan_for` on: no rows → free; credits ≤ free → free; credits > free → credits; active override → override; unlimited + override → unlimited with source; expired unlimited → underlying; `purchased_credits` math with a per-user free_monthly override; `status_for` boundaries at `inactive_after_days` and `PURGE_GRACE_DAYS` |
| `test_admin_users.py` | list `status` / `plan` / `joined_days` filters; each new sort key; SQL sort order equals `plans_for` order for a seeded page; v1 params still map; detail has the three blocks + activity newest-first; no secret keys |
| `test_admin_plan.py` (new) | single: each target, skipped, extend/shorten, step-up on remove and on top-up > 50, purchase-sourced guard survives restore-purchases; bulk: applied/skipped/failed groups, per-user transaction (one failure leaves the others committed), cap 101 → 422, shared request id on every audit row |
| `test_admin_bulk_state.py` (new) | delete/restore skip-in-state, token_version bump, step-up |
| `test_admin_purge.py` | bulk: non-eligible id → 422 naming it; dry run tables; apply needs password + `confirm_count`; audit rows survive |
| `test_admin_settings.py` (new) | registry types and bounds; resolver order (row → env → code); `PATCH` then a fresh `GET /scan-balance` sees the new free monthly; reset deletes the row; step-up keys; `warning` counts; every moved read site covered by one test that sets a row and observes the behaviour (grace, sweep gate, screenshot switch, JWS required) |
| `test_admin_ui.py` | still green; adds: default route is `#/hunters`; no inline handlers in the new code; filter state round-trips through the hash |
| `helpers_admin.MUTATIONS` | one `MutationCase` per new route (registry-completeness test fails until then) |

### 7.3 Cut list

| Item | Bucket | Trigger |
|---|---|---|
| Server-side saved views | v3 | a second admin, or a view worth sharing across devices |
| Charts (scans / sessions over time) | v3 | the first pricing decision that needs a trend, not a count |
| Server-side CSV export | v3 | a page larger than the 200-row limit needs exporting |
| Activity beyond the last 20 rows / pagination | v3 | a support case that needs older history (Usage still has it) |
| Promo codes, cohorts, messaging | never (for now) | more than a handful of users |
| In-console editing of env-only settings (admin, APNs, WHOOP, Sentry) | never | deploy-time decisions |
| Per-user notes | v3 | the first time a reason in the audit log is not enough |

### 7.4 Revision log

- **v2.0 (2026-09-13):** drafted in five chunks after the owner's first real use of the W3
  console (Overview tiles not clickable; "plan" nowhere; free-tier numbers read-only). Owner
  decisions: plan is derived server-side; settings become editable via `app_settings`;
  **purchased credits are never removed by a plan change**; Unlimited expiry defaults to Never;
  Adjust credits stays its own drawer; bulk applies per-user with partial failure reported;
  100-row bulk cap; phone lane includes step-up downgrades; `users.last_login_at`; resolver
  reads per request, no cache; one bulk route per action; every listed setting editable;
  W4 → W5 → W6 phasing; vanilla JS stays. Mockup: `docs/mockups/admin-console-v2-mockup.html`.

- **v2.1 (2026-09-13, W4 build):** §6 shipped in full — `entitlement_service.plan_for` /
  `plans_for` (three queries per page, asserted by a query-count test) and the frozen `Plan`;
  `admin_read_service.status_for` + the batched `last_active` / `last_active_kind` (workout ·
  scan · login); `GET /admin/users` `status` / `plan` / `joined_days` and the sort keys `plan` /
  `status` / `last_active` / `scans_4wk` / `level` / `created_at` / `email` over CASE twins of
  the Python models (a test asserts SQL order == `plans_for` / `status_for` on a seeded page);
  the detail's `plan` / `account` / `scans` blocks and `activity`; `POST /users/{id}/plan`,
  bulk `POST /users/plan` / `/users/state` / `/users/purge`, `GET /settings`, `PATCH
  /settings/{key}`; `SETTINGS_REGISTRY` + `settings_service` resolver with every §6.5 read site
  moved; `users.last_login_at` stamped on login and refresh; migration `console_v2` (head).
  Amendments forced by the code or the `/evaluate` pass, none re-opening a decision:
  - **Change plan never revokes a row the hunter may have paid for at standard tier.**
    `target=unlimited` on a hunter already unlimited by `purchase` or `backfill` is `skipped`
    (`why = "already unlimited by purchase"`); extend / shorten (revoke + re-grant in one
    transaction) applies to `admin_grant` rows only. Only `remove_unlimited` (step-up) revokes
    them. A past `expires_at` is 422.
  - `POST /users/{id}/plan` accepts an optional `Idempotency-Key`, replayed from the audit row
    exactly as credits adjust (`replayed: true`; a different body is 422) so a retried top-up
    cannot credit twice. The bulk routes take none (one request is one batch).
  - Bulk purge answers **one shape** for both legs — `BulkPurgeResponse{dry_run, preview:
    [{user_id, tables}], applied: [PurgeResponse], skipped, failed}` — instead of two; every id
    is checked for eligibility on the dry run too (422 naming the first offender, unknown id
    included). Any per-user failure is recorded and the loop continues.
  - `status_for(user, last_active, now, thresholds)` takes a `StatusThresholds`
    (`inactive_after_days`, `grace_days`) resolved once per page, not a settings read per row.
    `last_active` is a **day** (`date`), the granularity the 30-day rule needs.
  - The Plan card's `last_change` scans `user.plan_change | credits.adjust | entitlement.*`
    (the v1 action is `credits.adjust`, not `user.credits`).
  - `joined_days` accepts 1–3650 (the chips send 7 / 30 / 90); `q` also matches an id
    substring; `sort=created` stays as an alias of `created_at`; the default `status` is
    `active,inactive` so the v1 `test_sort_and_paging` now asks for every status explicitly.
  - Settings: `PATCH` with the value already in force from the console, or a reset with no row,
    is 409; an unknown key is 404; the `settings.update` audit `before` / `after` carry a
    `source` beside `{key: value}`; a stored row the registry no longer accepts is logged and
    the env / code value applies (the scanner never 500s on one bad row). `inactive_after_days`
    is the one key with no `Settings` attribute (code default 30 in the registry).
  - The purge sweep is scheduled unconditionally off SQLite and reads `PURGE_SWEEP_ENABLED`
    through the resolver **when it fires**, so a console flip arms the next boot without a
    redeploy; `purge_service.eligible_filter` / `purge_eligible_at` / `purge_eligible_cutoff`
    and `entitlement_service.default_scan_limits` now take `db`.
  - `Plan.scan_credits` is `null` for a hunter with no balance row (the Free chip shows the
    grant it would seed). `plan_source` is `purchase` when the active row cites a receipt.
  - `/auth/refresh` stamps `last_login_at` only when the stamp is over an hour old (it is read
    at day granularity; iOS refreshes often). `/auth/login` always stamps.
  - The Hunters list computes the plan / status / last-active twins once per user in a
    `_derived` subquery and counts with a filters-only query; `PlanChangeRequest` is the one
    Change-plan schema (the bulk request extends it); the bulk loop lives in
    `app/services/bulk.py` and serves plan, state and purge alike; the startup sweep exposes
    `startup_sweep(db)` as its test seam.
  Postgres note: the SQL plan twin casts the JSON `value` to text (`= 'true'`) and to integer
  (free-monthly override) via the I/O conversion cast; tests run on SQLite, so the W4 prod check
  exercises `GET /admin/users?sort=plan` and `?plan=override` (§7.1).

- **v2.2 (2026-09-14, W5 build):** §4.1–§4.3, §4.2, §5.2–§5.4 shipped in `app/admin_ui/`
  (`admin.js` / `admin.css` / `index.html`, no backend change): `#/` → Hunters; nav Hunters ·
  Overview · Audit · Settings · Catalog; the Hunters filter + sort state lives in the hash through
  one pure `parseHuntersState` / `serializeHuntersState` pair (`test_admin_ui` runs it under
  node); the table per §4.3 with 44-px rows, progressive hiding below 1280 px, sortable headers,
  Status / Plan / Joined chip groups, the 250 ms search, saved views (three seeded), checkbox
  column + sticky bulk bar with the 100-row cap and client-side CSV; ⌘K palette (Enter → detail,
  ⇧Enter → Change plan); Overview as eight linked tiles + Attention (hidden at zero) +
  Maintenance + Recent audit; Change plan single + bulk, Adjust credits amendments, bulk
  soft-delete / restore / purge (dry run → typed count + password). Drove on a scratch SQLite:
  Cleanup view → select 3 → purge dry run → apply; Free → Unlimited → skipped → Remove with
  step-up from a row chip; bulk Unlimited with a purchase-sourced row skipped; the phone lane
  (search → plan chip → sheet → apply). Amendments and follow-ups forced by the console, none
  re-opening a decision:
  - `test_admin_ui` no longer forbids `localStorage` outright: saved views (§4.3) need it, so
    every use must sit on a line naming `VIEWS_KEY` and none may mention the token. Views store
    filter + sort; the "visible columns" part of a view waits for a column chooser (W6 or v3).
  - The client skips the rows its own diff says will not change (already unlimited by purchase
    / backfill, same expiry, not unlimited for Remove) and sends the bulk route only the rest;
    the server's `skipped` group is still rendered when it disagrees. Bulk mode generalized the
    v1 typed-email unlock into `spec.typed` (the purge count) and added a keep-open result phase.
  - Change plan from a row chip, the palette and the bulk bar reads `AdminUserRow` alone (no
    detail fetch); Adjust credits / Set limits / Soft-delete / Restore from the row menu fetch
    the detail first (they are v1 detail drawers). The Deleted chip's "n d" is computed from
    `deleted_at` + `PURGE_GRACE_DAYS` read once per session from `GET /admin/settings`, which
    also feeds the Inactive tile's day count.
  - Grant / Revoke unlimited drawers are gone; the detail's Scans card and header plan chip open
    Change plan (the W6 detail rewrite keeps that). The drift hint points at Change plan.
  - **W6 backend follow-ups (the API lacks the shape, written down instead of added mid-W5):**
    the Unlimited tile's purchase · granted · backfill split and the Credits tile's outstanding
    purchased credits are summed client-side from a 200-row `GET /admin/users?plan=…` page (the
    tile says "first 200 of n" past that) → add `by_plan_source` and `purchased_credits_total`
    to `FleetUsageResponse`; the Scans tile's "x free · y paid · z unlimited" split is not on the
    API → `scans_4wk_by_plan` on the same response (the tile shows screenshots · 4 wk meanwhile);
    the audit toast cannot group a batch by `request_id` because `GET /admin/audit` has no such
    filter → add `request_id`; the row plan chip cannot list override keys because
    `AdminUserRow` has no `override_keys` (the detail header does) → optional row field; the
    Sessions column is not sortable because `UserSort` has no `session_count` key (§4.3 says
    "yes") → add it.
  - Select-all takes the current page (50 rows); the 100-row cap binds across pages on the
    Cleanup view exactly as §5.4 intends. Phone: the rail box is the Hunters search field; the
    palette is desktop-only; no bulk bar, no Purge on the phone (as §4.7).

- **v2.3 (2026-09-15, W6 build):** §4.4–§4.7 and §5.5 shipped in `app/admin_ui/` plus the v2.2
  backend follow-ups (no migration; alembic head stays `console_v2`). Hunter detail: header with
  click-to-copy email / id, joined + age, plan (→ Change plan) · status · ADMIN · WHOOP chips,
  Change plan + ⋯ (Adjust credits · Set limits · Soft-delete / Restore · Copy id); the four cards
  PLAN · SCANS (left) and ACCOUNT · PURCHASES (right) read `detail.plan` / `scans` / `account` /
  `balance.purchases` (the Danger Zone folded into ACCOUNT; Purge keeps the typed-email drawer and
  is desktop-only); Diagnostics is one `<details>` (Progress · Campaign · Integrations · Data health
  · Preview, v1 content) collapsed by default and remembered per browser under `DIAG_KEY`; Activity
  renders `detail.activity` (20 rows, newest first, kind chips). Measured on the drive: the four
  cards bottom out at 599 px on a 1440-px viewport (criterion: < 900). Settings: three registry
  groups with current · default · source chip · Edit / Flip…; `editSettingSpec(row)` types the input
  by `row.type`, shows `current → new` + `source → console`, step-up when `row.tier = destructive`,
  the `row.warning` line live for `PURCHASE_REQUIRE_JWS` / `PURGE_SWEEP_ENABLED`, Reset to default as
  a mode of the same drawer (`PATCH value: null`, offered only when `source = console`), toast
  "Setting saved · audit …" and a re-fetch; Integrations · Build · Admin cards from the new `env`
  block. Audit: target links hunter or catalog, action select = registry ∪ the page, Mine chip,
  `request_id` filter; Catalog: Sold column and the deactivation line. Phone lane per §4.7 / §5.7.
  Drove on a scratch SQLite: JWS flip → warning + `settings.update` → Reset clears it; `FREE_MONTHLY_SCANS`
  3 → 7 and a fresh `GET /scan-balance` answered 7; bulk Unlimited for 3 → the toast's request-id
  link lists exactly the 3 rows; Mine toggles the actor filter; phone jobs 1, 2, 3, 7 (search → row →
  detail; plan chip → Change plan sheet; Scans → Adjust credits sheet; ACCOUNT → Restore applied).
  Amendments forced by the build, none re-opening a decision:
  - `GET /admin/settings` answers `SettingsResponse{items: [SettingRow], env}` instead of the bare
    list — the read-only lines needed a home and a second route would have been one more mint per
    screen. `env` is booleans and public names only (`whoop_configured`, `apns_configured` +
    `apns_topic` / `apns_sandbox`, `sendgrid_configured`, `sentry_enabled`; `git_sha` / `git_branch`
    / `environment` from the Railway vars and `started_at` = process boot, which on Railway is the
    deploy time — Railway exposes no deploy timestamp; `bootstrap_email`, `token_ttl_minutes`,
    `lockout_threshold` / `lockout_minutes`, `step_up_failures_to_revoke`). `assert_no_secret_keys`
    pins the names and a test plants a marker secret and asserts it never crosses the wire.
  - The v2.2 follow-ups as shipped: `FleetUsageResponse.by_plan_source {purchase, admin_grant,
    backfill}`, `purchased_credits_total` (every live hunter, Unlimited included — the credits wait
    underneath), `scans_4wk_by_plan {free, credits, unlimited, override}` (28 days, the scanning
    hunter's plan by `plans_for`, so a deleted hunter's scans count under whatever plan its rows
    derive); `GET /admin/audit?request_id=` (exact); `AdminUserRow.override_keys` (always sent, empty
    list when none — the row chip lists them); `UserSort` `session_count` (COALESCE 0, the Sessions
    header sorts); `ProductResponse.sold` / `sold_verified` from `purchase_records`. The Overview
    tiles read the rollups instead of two 200-row pages; the Scans tile's big number is the sum of
    the by-plan split (28 days) rather than four ISO weeks.
  - Bulk batches send `X-Request-ID` = a uuid the drawer minted (`rid`), so the toast's audit link
    and `latestAuditId` group the batch by `request_id` instead of by action; single actions keep
    the target lookup. The Audit table's Request cell links the same filter.
  - `SettingRow` gained `allowed` (the registry's csv allow-list) and `min` / `max` (the int /
    seconds bounds) so the drawer validates from the row rather than from a client copy; a csv
    value is a comma-separated **string** end to end (the registry's `coerce` shape) — the
    `/simplify` pass caught the drawer treating it as an array.
  - QA: `/evaluate` (independent subagent) B+, PASS WITH WARNINGS, contract mirror clean field by
    field; its one Error — a detail's Change plan read the Hunters-table snapshot (`state.rows`)
    instead of the fresh detail — is fixed by dropping the snapshot on every non-list route. Its
    index warning (`admin_audit_log.request_id` is unindexed and the bulk toast now filters on it)
    is a v3 migration, not a W6 change. `/simplify` (four reviewers): dead week helpers and CSS
    removed, `actBtn` / `shortKey` / `applyThresholds` / `csvTokens` shared, `whoop_service` /
    `notification_service.is_configured()` reused by the env block, `Counter`-based rollups, the
    Overview down to eight requests (deleted / purge-eligible come from the usage rollup, `weeks=1`).
    Skipped on purpose: server-side tile counts and a SQL twin for `by_plan_source` (v3 with the
    index), a `state.screen` container (the router reset is the smallest correct change), the
    duplicate Change plan button (§4.4 lists it in both the header and the PLAN card), dropping
    `recent_audit` (§6.3 keeps it).
  - `rowMenu(u, detail)` serves both the table row and the detail header (the header omits Change
    plan — the primary button — and Open in new tab). The Hunters phone lane hides the audit
    filters and the Overview's Maintenance / Recent-actions cards (`dk`), as §4.7 lists only the
    tiles + Attention and "the list".
  - `test_admin_ui`'s storage rule now allows `DIAG_KEY` beside `VIEWS_KEY` (token still forbidden)
    and pins the settings drawer strings, the detail blocks, the request-id wiring and the phone
    card order in the CSS.
