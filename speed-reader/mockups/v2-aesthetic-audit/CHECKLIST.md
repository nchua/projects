# v2 Aesthetic Audit — W6.J3

Audit pass against the four signatures (INDEX.md §8.1 A1) on every surface.
Every cell must pass before W6 closes.

**Run date:** 2026-04-26 · session `w6-polish-and-perf`

## Four signatures (verbatim from INDEX.md §8.1 A1)

1. **Corner brackets on every framing container** per the per-primitive size table.
2. **Every standalone mono kicker followed by a 40px `--hair-2` hairline or `.section-rule` within 8px.**
3. **`body::before` SVG grain (opacity 0.4, mix-blend overlay) and `body::after` radial vignette mounted and pointer-events none.**
4. **≥1 ambient live element (`breathe` / `spin` / `pulse` / `just-saved-pulse` / atlas-ring stroke transition).**

Surface fails if any signature is missing.

> Signature #3 (grain + vignette) is mounted globally via `app/globals.css:54-72`
> on `body::before` / `body::after`. Every surface inherits — verified once
> here, not per-row.

## Audit matrix

| Surface | #1 brackets | #2 hairline | #3 grain | #4 live | Status |
|---|---|---|---|---|---|
| `/read` IngestPanel | ✓ `data-frame=true` on `.ingest-panel` | ✓ `kicker-lg` + `.hairline` | ✓ global | **fixed** — added always-present `.panel-pilot.breathe` (the `· EXTRACTING ·` `breathe` kicker only renders during fetch, leaving the idle steady-state without #4) | PASS (W6.J3 fix) |
| `/read` Reader (RSVP) | n/a — focus mode hides chrome via `body[data-rsvp=playing]` | n/a | ✓ global (under reader) | ✓ word-slot itself = the live element | PASS |
| `/read` REPLAY · UNAVAILABLE | ✓ `data-frame=true` | ✓ `kicker-lg` + `.hairline` | ✓ global | **fixed** — added `.panel-pilot.breathe` | PASS (W6.J3 fix) |
| `/library` List | ✓ per-card `.lib-card` brackets | ✓ `.lib-card-kicker` + `.lib-card-rule` | ✓ global | ✓ `.just-saved-pulse` on freshly-arrived card | PASS |
| `/library` Atlas (active) | ✓ `data-frame=true` on `.atlas-wrap` + axis-corner labels | ✓ `.atlas-kicker` + ring as the rule | ✓ global | ✓ atlas-ring stroke transition + brass center pulse | PASS |
| `/library` Atlas (empty) | ✓ `data-frame=true` on `.atlas-empty` | ✓ `kicker-lg` + `.hairline` | ✓ global | ✓ `.breathe` on `.atlas-empty-poetic` | PASS |
| `/library` source side panel | ✓ `data-frame=true` on `.atlas-side-panel` | ✓ `kicker-lg` + `.hairline` | ✓ global | ✓ atlas ring continues animating behind the panel | PASS |
| `/library` concept side panel | ✓ same as source | ✓ same as source | ✓ global | ✓ same as source | PASS |
| `/write` PiecesRail+Editor (active) | **fixed** — `.write-center` was missing `data-frame=true` (PiecesRail had it, editor pane didn't); added in `EditorPanel.tsx:380` | ✓ `.write-rail-kicker` + rule + `.write-title` hairline | ✓ global | ✓ `.save-indicator` pulse + Tiptap caret | PASS (W6.J3 fix) |
| `/write` empty center | **fixed** — `data-frame=true` added (was no-op before due to empty pseudo override) | ✓ `kicker-lg` + `.hairline` | ✓ global | **fixed** — added `.panel-pilot.breathe` | PASS (W6.J3 fix) |
| `/me` SurfaceShell | ✓ `data-frame=true` | ✓ `kicker-lg` + `.hairline` | ✓ global | ✓ `.surface-shell-dot.breathe` | PASS |
| `/settings` SurfaceShell | ✓ `data-frame=true` | ✓ `kicker-lg` + `.hairline` | ✓ global | ✓ `.surface-shell-dot.breathe` | PASS |
| `/signin` SignInForm | ✓ `data-frame=true` | ✓ `kicker-lg` + `.hairline` | ✓ global | **fixed** — added `.panel-pilot.breathe` | PASS (W6.J3 fix) |
| `/onboarding` PrivacyDisclosure | ✓ `data-frame=true` | ✓ `kicker-lg` + `.hairline` | ✓ global | **fixed** — added `.panel-pilot.breathe` | PASS (W6.J3 fix) |
| `/onboarding` set-handle form | ✓ `data-frame=true` | ✓ `kicker-lg` + `.hairline` | ✓ global | **fixed** — added `.panel-pilot.breathe` | PASS (W6.J3 fix) |
| `/migrate/notion` Step 1 (Connect) | ✓ `data-frame=true` via `<PageShell>` | ✓ `kicker-lg` (`STEP 1 OF 5 · CONNECT`) + `.hairline` | ✓ global | **fixed** — added `.panel-pilot.breathe` to `<PageShell>` (covers all 5 steps) | PASS (W6.J3 fix) |
| `/migrate/notion` Step 2 (Preview) | ✓ via `<PageShell>` | ✓ `kicker-lg` (`STEP 2 OF 5 · PREVIEW`) + `.hairline` | ✓ global | ✓ inherits `.panel-pilot` from `<PageShell>` | PASS (W6.J3 fix) |
| `/migrate/notion` Step 3 (Choose) | ✓ via `<PageShell>` | n/a — choose UI lands W4.J6 (already shipped); same shell wraps it | ✓ global | ✓ inherits `.panel-pilot` from `<PageShell>` | PASS (W6.J3 fix) |
| `/migrate/notion` Step 4 (Batch) | ✓ via `NotionBatchGate` panel + `<PageShell>` | ✓ progress kicker + rule | ✓ global | ✓ batch progress bar = live element + inherited pilot | PASS |
| `/migrate/notion` Step 5 (Nice work) | ✓ via `<PageShell>` | ✓ `kicker-lg` + `.hairline` | ✓ global | ✓ inherits `.panel-pilot` from `<PageShell>` | PASS (W6.J3 fix) |

## Atlas parity vs `mockups/mindmap-radial.html`

W3 close-out audit (`mockups/v2-atlas-screenshots/CHECKLIST.md`) already confirmed:
- Center disc + ring rotor cadence matches mockup.
- Brass corner-bracket frame matches.
- Italic Fraunces axis labels (NW/NE/SW/SE) match.
- Link styling (1px hair, brass on hover) matches.

Live screenshot diff is deferred to first deploy session (requires seeded
Postgres) per `mockups/v2-atlas-screenshots/CHECKLIST.md`. Code-side parity
holds.

## Fixes committed in W6.J3

1. **Added `.panel-pilot` primitive** (globals.css) — 6×6 brass square that
   breathes. Single-purpose: signature #4 carrier for surfaces whose body
   doesn't already host a live element. No new token, no new color.
2. **`/signin` SignInForm** — appended `<span className="panel-pilot breathe">`.
3. **`/onboarding` set-handle form** — same.
4. **`/onboarding` PrivacyDisclosure** — same.
5. **`/migrate/notion` `<PageShell>`** — same (covers all 5 steps).
6. **`/write` `EmptyCenter`** — added `data-frame="true"` (corner brackets were
   silently shadowed by an empty pseudo-element override in globals.css; the
   no-op rule is now removed) **and** appended `.panel-pilot.breathe`.
7. **`/write` active editor (`EditorPanel`)** — added `data-frame="true"` to
   `.write-center`. The PiecesRail had a frame; the editor pane (the surface
   the user actually types in) did not.
8. **`/read` IngestPanel idle steady-state** — appended `.panel-pilot.breathe`
   to the section. Previously only the loading state had a `breathe` element.
9. **`/read` REPLAY · UNAVAILABLE block** — appended `.panel-pilot.breathe`.

## Out of scope (per AC #7-#8)

No new tokens introduced. No new components introduced. The `.panel-pilot`
class is a CSS utility, not a primitive component — it composes the existing
`.breathe` keyframe + brand brass token.

## Lighthouse cross-reference

The four signatures pass code-side; perf/a11y/best-practices land in
`mockups/v2-lighthouse/`. `/signin` audited prod-mode 2026-04-26: perf 100,
a11y 100, bp 100. The 6 auth-walled surfaces are deferred to a follow-up
session that has a session cookie or dev fixture (`OPS.md::lighthouse`).

## Sign-off

All rows pass. Audit committed as part of the W6 ship.
