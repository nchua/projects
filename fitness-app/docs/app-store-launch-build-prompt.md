# App Store Launch — Build Session Prompt

> Paste into the next Claude Code session from `/Users/nickchua/Desktop/AI`:
>
> **"Read `fitness-app/docs/app-store-launch-build-prompt.md` and execute it end to end.
> Stop only at the points marked ASK."**
>
> Written 2026-09-06 against `app-store-launch-spec.md`. Scope is small — two backend
> deliverables plus a handoff to the user for capture and ASC work. Sequential, no
> subagents; the work does not fan out.

---

## 0. Mission

Execute gates **G1** and **G4** from `fitness-app/docs/app-store-launch-spec.md`, then
hand the user everything they need for **G2** (screenshots) and the App Store Connect
steps. G3 is already done and deployed.

Sources of truth, in precedence order:

1. `app-store-launch-spec.md` — the gate definitions and acceptance criteria.
2. `app-store-launch.md` — the phased checklist and status table.
3. The code — when a spec `file:line` anchor is stale, trust the code and note the drift.

**Do not** do App Store Connect work, sign agreements, invent an app name, or rename
"Shadow Monarch". Those are the user's, and two of them are deliberately deferred.

**Do not** implement StoreKit JWS verification or Redis-backed rate limiting. Both are
explicit non-goals in spec §Scope; the reasoning is written there.

---

## 1. Session start — do all of these before writing code

1. `git pull`. Confirm `git log --oneline -5` includes `f404bc4` (the spec) or later.
   **Another session works in this monorepo concurrently.** Before every commit, run
   `git diff --cached --stat` and commit with an explicit pathspec:
   `git commit -- <paths>`. A bare `git commit` sweeps in their staged files.
   (memory: `feedback_shared_repo_pathspec_commits`)
2. Single alembic head: `cd fitness-app/backend && venv/bin/alembic heads`. If there is
   more than one, stop and reconcile — a multi-head fails the Railway deploy while the
   old instance keeps serving, which masks the failure.
   (memory: `feedback_railway_alembic_multi_head`)
3. Green baseline: `venv/bin/python -m pytest tests/ -n auto -q`. Expect **1021 passed,
   1 skipped** as of 2026-09-06 — treat it as a floor, not an exact match, since the
   concurrent control-plane workstream adds and removes tests. Use the absolute venv path.
   (memory: `project_fitness_backend_python_env`)
4. `bash fitness-app/ios/scripts/preflight-appstore.sh` — expect **0 issues, 0 warnings**.
   If a public URL now 404s, the backend was redeployed badly; fix that first.
5. Re-verify the anchors G1/G4 depend on, because they drift:
   - `app/api/screenshot.py` `_assert_daily_cap` and the `ScreenshotUsage` query
   - `app/core/config.py` the `PURCHASE_MAX_*` / `DAILY_SCREENSHOT_LIMIT` Field pattern
   - `app/services/email_service.py` `send_owner_alert(subject, body)`
   - `app/services/entitlement_service.py` the unlimited-grant path
   - `backend/scripts/grant_owner_unlimited_scans.py` — the script conventions to copy

---

## 2. G4 — global Anthropic spend ceiling  *(do this first: small, self-contained)*

Spec §G4.1 and §G4.2. **Read §G4's preamble before starting** — it documents what is
already protected, so you do not add redundant guards. Every existing control is
per-user; the gap is aggregate spend.

### G4.1 Ceiling

- Add `ANTHROPIC_DAILY_CALL_CEILING: int` to `Settings` following the `PURCHASE_MAX_*`
  pattern. Pick a default well above current real usage — this catches runaway abuse,
  it does not throttle a good day.
- Enforce **before** the Anthropic request in both `/screenshot/process` and
  `/screenshot/process/batch`. Batch must count all N screenshots, not one.
- Sum `ScreenshotUsage.screenshots_count` since UTC midnight **without** the `user_id`
  filter. Same table `_assert_daily_cap` reads — no new table, no new writes.
- Over ceiling → **503**, no credit debited, message matching the existing no-credit
  path at `screenshot.py:375`.
- `send_owner_alert` on the first breach of a day, via `BackgroundTasks` (SendGrid
  blocks; keep it off the event loop, as `verify-purchase` does).
- **Alert before the ceiling, not only at it.** A ceiling you learn about by being down
  is a worse outage than a bill. Warn at a threshold below the cap.

### G4.2 Password-reset IP limit

Add `@limiter.limit(...)` to `/password-reset/request` with a new constant in
`app/core/rate_limit.py`. Document the shared-NAT reasoning in a comment the way
`LOGIN_RATE_LIMIT` and `REGISTER_RATE_LIMIT` already do. This is about mail-send cost
and sender reputation, not account compromise — the per-email cooldown already handles
that. Size it accordingly.

### G4.3 Tests

New `tests/test_spend_ceiling.py`:
- under ceiling → passes
- at/over ceiling → 503, **and no credit was debited** (assert the balance directly)
- batch of N counted as N, not 1
- owner alert fires once per day, not per request
- warn threshold fires before the cap
- password-reset request rate limit trips

---

## 3. G1 — App Review demo account

Spec §G1. New file `backend/scripts/seed_review_account.py`.

**Copy the conventions from `scripts/grant_owner_unlimited_scans.py`** — dotenv +
`sys.path.insert` bootstrap, `import app.models` before touching the session, a module
docstring with the run command, idempotent with a "already seeded" report.

Hard rules:
- Credentials come from `SEED_USER_EMAIL` / `SEED_USER_PASSWORD`. **No literal address
  or password anywhere in the file.** Exit non-zero with a usage message if unset.
  A hardcoded credential in this repo already caused one GitGuardian incident.
- **Never log the email or password**, matching the existing script.
- Grant `scans.unlimited` through the same entitlement path
  `grant_owner_unlimited_scans.py` uses — the only sanctioned writer of
  `scan_balances.has_unlimited` (control-plane spec §6.2). Do not set the flag directly.

Data shape is in spec §G1.2. The rule that matters:

> **Derived state must be derived.** PRs, e1RM, XP, level, and rank must fall out of the
> same code paths a real user hits. Hand-inserted rows produce an account that looks
> right on screen but is internally inconsistent — and the screenshots would then show
> numbers the app cannot reproduce.

Sessions end **yesterday**, never in the future. Weights must progress across the ~10
weeks or the trend charts are flat and the screenshots undersell the app.

### Tests

`tests/test_seed_review_account.py`: runs against the test DB, asserts idempotency
(second run changes nothing), asserts PRs and rank were *computed* rather than inserted,
and asserts the script refuses to run with missing env vars.

---

## 4. Verify, then commit

1. `ruff check .` — CI runs this gate before pytest and a local pytest run misses it.
   (memory: `feedback_backend_ci_ruff`)
2. Full suite green.
3. `bash fitness-app/ios/scripts/preflight-appstore.sh` still 0/0.
4. Commit G4 and G1 separately, with pathspecs. Push.
5. Confirm the Railway deploy reaches SUCCESS — do not assume.

---

## 5. ASK — stop here and put these to the user

**ASK 1 — the ceiling number.** Before finalizing `ANTHROPIC_DAILY_CALL_CEILING`, ask
what a survivable daily Anthropic spend is, and what current real usage looks like. Do
not guess a number that could either bankrupt or throttle them. If they don't have the
figure to hand, ship a deliberately generous default and say so explicitly.

**ASK 2 — the support inbox (spec §G3.2).** `/privacy`, `/terms`, and `/support` are
live and advertise `privacy@arise-fitness.app` and `support@arise-fitness.app`. Does
that domain exist and receive mail? A dead address on a published privacy policy is
worse than none — Apple may mail it and users certainly will. Note the coupling: if the
app name changes, the domain likely changes with it.

**ASK 3 — run the seed and capture screenshots (G2).** This needs a human. Give them:
- the exact `SEED_USER_EMAIL=... SEED_USER_PASSWORD=... venv/bin/python
  scripts/seed_review_account.py` command
- the `simctl` boot / status-bar / screenshot commands from spec §G2.1
- the 5-shot list from §G2.2
- the reminder that shot 5 needs recovery data present, or drop it rather than shipping
  an empty state

**ASK 4 — the app name.** Still deferred. It blocks creating the ASC record, so surface
it as the gating item it is. When they decide, spec §G5 is the single mechanical sweep —
and it lists what must **not** change: bundle id, IAP product ids, `APNS_TOPIC`.

---

## 6. Definition of done

- [ ] Global spend ceiling enforced on both scan endpoints, with owner alerting and a
      pre-cap warning; over-ceiling debits no credit.
- [ ] Password-reset request has an IP-level limit with a documented rationale.
- [ ] `seed_review_account.py` is idempotent, credential-free, and produces an account
      whose PRs and rank were computed by the real code paths.
- [ ] `ruff` clean; full suite green; preflight 0 issues 0 warnings.
- [ ] Both commits pushed with pathspecs; Railway deploy confirmed SUCCESS.
- [ ] The four ASKs put to the user, with the G2 commands handed over ready to run.
- [ ] `app-store-launch.md` status table updated to reflect what closed.

**Not done in this session, by design:** screenshots (needs a human), the app name,
"Shadow Monarch", the Paid Applications Agreement, IAP products in ASC, and submission.
