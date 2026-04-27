# v2.1 Backlog

Carryover items from W1–W6 deferred to v2.1. P2/P3 bug-bash entries land
here as well (per W6.J4 AC #3).

## From W6 — explicit deferrals

### Lighthouse — auth-walled surface audits
- **Source:** W6.J1 ACs #1, #2, #3, #4, #5, #6, #7
- **Status:** Public-surface (`/signin`) audited prod-mode 2026-04-26 at
  perf 100 / a11y 100 / bp 100 / TTI 579ms. The 6 auth-walled surfaces
  (`/library`, `/library?tab=atlas`, `/write`, `/me`, `/settings`, `/read`)
  are unaudited because the runner needs a session cookie.
- **Remediation:** Wire `app/api/dev/auth-fixture/route.ts` (404 in prod;
  mints a session for `SEED_USER_EMAIL` in dev) plus a seed script that lands
  ≥30 sources / ≥3 writings so atlas + library audits have content to
  measure. Then re-run `npm run lighthouse:report` and commit reports.
- **Where the deferral is documented:** `mockups/v2-lighthouse/README.md` +
  `speed-reader-v2/OPS.md::lighthouse`.

### Perf budget GitHub Actions CI gate
- **Source:** W6.J2 ACs #1 (PRs trigger workflow), #3 (PR comment with
  metrics), #8 (2 retries on infra failure)
- **Status:** Replaced with a local `npm run lighthouse:ci` script per
  `~/.claude/CLAUDE.md::No Extraneous Features` (solo dev, Railway
  auto-deploy, no PR workflow). Local script asserts §7 budgets in `warn` /
  `block` modes (AC #2, #4, #5 fulfilled).
- **Remediation:** If/when v2.1 onboards a second contributor or moves to a
  PR-based workflow, port the `scripts/lighthouse-run.ts` logic to a GH
  Actions workflow at `.github/workflows/ci-lighthouse.yml`. The script's
  `LIGHTHOUSE_GATE_MODE=block` mode is the hard-block W7+ requirement and is
  ready to flip.

### W5.J5 autosave hard-kill ceiling
- **Source:** W5 handoff `Blockers / Open Questions`
- **Status:** Pure 800ms-debounced autosave with no max-wait — continuous
  typing of >800ms-without-pause can lose state if browser is force-killed
  mid-stream. Spec accepts "worst case: last 800ms" but implementation goes
  beyond that in the continuous-typing edge case.
- **Remediation:** Add a max-wait ceiling (force-PATCH every 5s of dirty
  state) to `lib/write/autosave-queue.ts`.

### W4.J5 cost calibration drift
- **Source:** Carried since `w4j5-demo-bugs-and-direct-nav-overhaul`
- **Status:** Migration preview over-estimated cost by 34% on the live demo;
  `lib/migrate/cost.ts:28` `TYPICAL_OUTPUT_TOKENS` is the lever.
- **Remediation:** Calibrate against a few real batches once the user has
  actual usage data, tighten the constant.

### Shared `jsonError` migration
- **Source:** W5 handoff
- **Status:** `lib/api/json-error.ts` is used by the 5 W5 routes; existing
  `app/api/summarize/route.ts` and `app/api/migrate/notion/*/route.ts` still
  carry their own local copies (with the 3-arg `extra` shape that the new
  helper supports).
- **Remediation:** Single-pass migration across the older routes. Pure
  cleanup, no behavior change.

## From W6 — bug-bash P2/P3 punts

_(empty — populate from `mockups/v2-bug-bash.md` triage when week-5
personal-usage window completes.)_

| # | Source | Severity | Description | Repro |
|---|---|---|---|---|
| — | — | — | — | — |

## Aesthetic deferrals

### Atlas screenshot diff vs `mockups/mindmap-radial.html`
- **Source:** W3.J7 AC #4 / W6.J3 AC #3
- **Status:** Code-side parity verified
  (`mockups/v2-atlas-screenshots/CHECKLIST.md`). Live screenshot diff
  requires seeded Postgres.
- **Remediation:** Run after first deploy with seeded data; capture the 6
  reference screenshots (default-centering, hover-state, sparse N=1,
  panel-source, panel-concept, deep-linked) under
  `mockups/v2-atlas-screenshots/`.
