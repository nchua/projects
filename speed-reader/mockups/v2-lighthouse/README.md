# v2 Lighthouse — W6.J1 / W6.J2 (lite)

Per-surface Lighthouse reports for v2.0 surfaces. Reports live as
`<slug>.report.html`. Generated via `npm run lighthouse:report` in the v2 repo
(see `speed-reader-v2/OPS.md::lighthouse`).

## Score floor (§7 perf budget)

| Surface | Performance | Accessibility | Best Practices |
|---|---|---|---|
| `/signin`, `/library`, `/library?tab=atlas`, `/me`, `/settings`, `/read` | ≥ 90 | ≥ 95 | ≥ 90 |
| `/write` (Tiptap) | ≥ 85 | ≥ 95 | ≥ 90 |

## Latest run — 2026-04-26 · prod build, localhost:3002

| Surface | Performance | A11y | BP | TTI | Status |
|---|---:|---:|---:|---:|---|
| `signin` | **100** | 100 | 100 | 579ms | ✅ pass |
| `library-list` | — | — | — | — | ⏸ skipped (auth fixture deferred) |
| `library-atlas` | — | — | — | — | ⏸ skipped (auth fixture deferred) |
| `write` | — | — | — | — | ⏸ skipped (auth fixture deferred) |
| `me` | — | — | — | — | ⏸ skipped (auth fixture deferred) |
| `settings` | — | — | — | — | ⏸ skipped (auth fixture deferred) |
| `read` | — | — | — | — | ⏸ skipped (auth fixture deferred) |

`signin` scored a perfect 100 across all three measured categories on the
first audit; TTI well under the §7 F1 budget of 1.8s.

## Open Question — auth-walled surfaces

The 6 auth-walled surfaces require either:

1. A real signed-in session cookie (Google OAuth or magic link) exported as
   `LIGHTHOUSE_AUTH_COOKIE` before running the audit, OR
2. A dev-only `/api/dev/auth-fixture` endpoint that mints a session cookie
   on demand for a fixed test user.

Option 1 is documented in `speed-reader-v2/OPS.md`. Option 2 is the
spec-canonical fixture but is deferred — the audits aren't meaningful
against an empty Postgres anyway, and seeded data is part of the post-deploy
verification path (per `mockups/v2-atlas-screenshots/CHECKLIST.md`).

**Remediation Job for v2.1:** wire `app/api/dev/auth-fixture/route.ts` (404
in production, mints a session for `SEED_USER_EMAIL` in dev) plus a seed
script that lands ≥30 sources / ≥3 writings so the atlas + library audits
have realistic content to measure.
