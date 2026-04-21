# Review me (v1)

Built while you were asleep. The speed-reader now has a knowledge bank attached.

## What got built

- **Finish-reading flow**: checkmark button appears in the reader at ≥80% progress or when playback ends. Opens a modal with free-recall → first-time disclosure → AI summarize → save. Auto-pauses the player. Esc closes.
- **`/api/summarize`**: Vercel function (Claude Sonnet 4.6, tool-use JSON, verbatim-quote validation, 20 req/min IP rate-limit, prompt caching on the system prompt).
- **`/library`**: new page with **List** (reading cards, per-card PNG export via html2canvas) + **Atlas** (progress-ring counter locked at 15 sources; minimal radial at unlock). Saved-card pulse highlight after Finish.
- **`js/library.js`**: localStorage layer at key `speedreader.library.v1` with content-hash dedup (re-reads update `last_read_at`, don't re-summarize).
- `README_V1.md` has operator notes, cost estimate, rollback steps.

## What to click first

1. `npm install` in `/Users/nickchua/Desktop/AI/speed-reader/`, then set `ANTHROPIC_API_KEY` and run `npx vercel dev`.
2. Open `http://localhost:3000/`. Notice the small `library →` in the top-right.
3. Paste any article and play. Let it reach the end or pause near the end — a ✓ appears in the controls.
4. Click ✓. Write a line of recall. Click **Summarize with AI**. Accept the disclosure. Click **Save to library**.
5. You'll land on `/library#saved-{id}` with a brass pulse on the new card.
6. Click the Export button on a card. A PNG downloads.
7. Click the **Atlas** tab. See the 1/15 progress ring.

## Fixed before commit

- Deep-link pulse was broken if your last-active tab was Atlas (flagged by /evaluate as the only user-visible bug). Now `#saved-...` always lands on List.
- `/library.html` path changed to `/library` throughout (cleanUrls).
- Atlas empty-state text no longer relied on an invalid SVG `text-transform` attribute.
- Removed 7 dead DOM refs + 1 unreachable switch case in `js/ui-finish.js`.
- `openConceptPanel` was re-parsing localStorage N times per click — now one read.

## Open questions that need your input

Two from the council's `COUNCIL_NEXT_STEPS.md` that materially affect next steps:

1. **Vercel plan**: `vercel.json` assumes Pro (`maxDuration: 60`). If you're on Hobby, long summaries will 10s-timeout. Verify the plan or lower `MAX_CHARS` in `api/summarize.js` from 30000 to ~8000 as a stopgap.
2. **Anthropic key rotation**: it's a platform-owned key via `ANTHROPIC_API_KEY` env var. The in-memory rate limit (20/min/IP) resets on cold start and doesn't protect against determined abuse. If you ever share this URL, put Vercel auth or an allowlist in front of `/api/summarize` first.

Council open questions 3 (re-read policy) and 4 (Holocron integration) are deferred per phase-2 scope; not blocking.

## Honest caveats

- Tested via code review + syntax checks (`node --check` passes on all 6 JS modules). **Not** tested with `vercel dev` running — I didn't have a live Anthropic key to round-trip.
- Mobile layout follows the tap-safe rules (event delegation, touch-action, ≥44px, `:active` feedback) but has not been loaded on a physical phone.
- Atlas radial unlocks at 15 sources — you're at 0, so the unlocked path is untested in-flow. The gate state (locked progress ring) renders correctly.
- Screenshots via html2canvas may render the card slightly differently than on screen (backdrop-filter and some CSS filters don't transfer cleanly).

## Quality gate scores

- `/evaluate`: **A−** (0 Critical, 2 Error initially → both fixed, 5 Warning acceptable for v1, 6 Info)
- `/simplify`: 4 findings across reuse/quality/efficiency → 4 fixed
- Lint: no-op (JS-only project; no ruff to run)

Commit is clean. Pushed to `origin/main` — Vercel will auto-deploy. If deploy fails, see `README_V1.md` "How to roll back".
