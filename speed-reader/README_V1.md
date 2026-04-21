# Speed-Reader v1 — Operator Notes

This document is the operator guide for the v1 knowledge-bank integration. If you just want to know what to click, see `REVIEW_ME.md`.

---

## What shipped

- **`/api/summarize`** — Vercel serverless function. Takes article text, returns `{ summary, tags[], key_quotes[] }` via Claude Sonnet 4.6 structured tool-use. Verbatim-quote validation drops any returned quote that isn't an exact substring of the submitted text.
- **Finish-reading flow** — a new button on the reader appears at ≥80% progress or when playback ends. Opens a modal with: free-recall textarea → disclosure (first-time) → Summarize → Save to library.
- **`/library.html`** — two-tab page (List / Atlas). List shows reading cards with one-tap PNG export (`html2canvas`). Atlas is gated: below 15 sources it shows a progress-ring counter; at ≥15 it renders a minimal radial concept graph.
- **localStorage-only** — all reader content stays on the device. The only thing that leaves is the article text going to Anthropic for summarization, and only when the user explicitly clicks Summarize.

---

## How to test locally

```bash
cd /Users/nickchua/Desktop/AI/speed-reader
npm install                          # pulls @anthropic-ai/sdk
export ANTHROPIC_API_KEY=sk-ant-...  # or put in .env.local
npx vercel dev                       # serves on http://localhost:3000
```

1. Open `http://localhost:3000/`
2. Paste any article into the textarea and click play
3. Read through to ≥80% (or let it finish) — a "Finish reading" button appears in the controls bar
4. Click it → write 1-2 sentences of free recall → click "Summarize with AI"
5. First-time only: a disclosure modal appears. Click "Don't show again" or "Continue"
6. Watch the loading state, then see summary + tags + key quotes
7. Click "Save to library" → redirects to `/library.html#saved-{id}`
8. Try the Export button on a card
9. Click the Atlas tab → see the "unlocks at 15 sources" progress ring
10. To test the unlocked state without reading 15 articles, in DevTools console:
    ```js
    // pollutes localStorage with test data
    const lib = await import('/js/library.js');
    for (let i = 0; i < 16; i++) {
      await lib.save({
        title: `Test article ${i}`,
        text: `fake text body ${i}`,
        summary: `Summary for article ${i}.`,
        tags: [`concept-${i % 5}`, `theme-${i % 3}`],
        key_quotes: [`fake text body ${i}`],
        wpm: 400, source_type: 'text',
      });
    }
    location.reload();
    ```

---

## Operator notes

### Vercel plan assumption
`vercel.json` sets `maxDuration: 60` on `/api/summarize`. This requires **Vercel Pro**. On the Hobby plan the timeout caps at 10s — summaries of ~20k-token articles will fail. If you're on Hobby and can't upgrade yet:
- Option A: lower `MAX_CHARS` in `api/summarize.js` from 30000 to ~8000 so the model finishes within 10s
- Option B: upgrade to Pro ($20/mo). Recommended once you're relying on the flow daily.

### Anthropic API key
- The function reads `ANTHROPIC_API_KEY` from the Vercel env (`vercel env add ANTHROPIC_API_KEY production`)
- No BYOK (bring-your-own-key) UI in v1 — decided against it for first-use friction. Revisit if a non-you human ever uses this.
- **You own the bill.** The rate-limit is in-memory per IP and doesn't survive cold starts. Any casual load will bypass it. If you ever share this URL, put Vercel auth or an allowlist in front of `/api/summarize` before it goes viral.

### Cost estimate
At Sonnet 4.6 public pricing (roughly 3 USD per M input tokens, 15 USD per M output tokens):
- Avg article: ~5k input + ~500 output tokens, on the order of two cents per summary
- 50 articles/week: roughly one dollar per week, four per month
- 200 articles/week: roughly four per week, sixteen per month
Prompt caching on the system prompt reduces input cost slightly after the first call of each ~5-min window.

### Privacy posture
- `/api/summarize` never logs request bodies — only token counts and error messages
- Anthropic's default API retention is 30 days (for abuse monitoring); content is not used for training
- Nothing beyond the summarize call leaves the device. Library stays in `localStorage` (~5MB ceiling; fine for ~500 sources with summaries but no full text)

### What's NOT in v1, and why
- **Holocron integration** — deferred per council. Validate you actually use the Finish flow before bridging to SRS.
- **Full polished radial atlas** — gated at N≥15 sources. The mockup at `mockups/mindmap-radial.html` is the visual target; `js/atlas.js` ships the simplified v1 render.
- **App-open quote primer** — requires ≥5 starred quotes. `library.starQuote()` is in place; UI to star quotes comes in v1.1.
- **BYOK settings screen** — phase 2 if a second user ever touches this.
- **Cross-device sync** — phase 3. Would re-introduce server storage and break the privacy story.
- **Kindle / YouTube / Gmail ingestion** — listed in `mockups/IDEAS.md`. All phase 2+.

---

## How to roll back

Every v1 file is new except for two that were modified (`index.html`, `js/main.js`, `package.json`, `vercel.json`). To revert to the prior working state:

```bash
# Remove new files
rm api/summarize.js
rm js/library.js js/ui-finish.js js/library-page.js js/atlas.js
rm styles/finish.css styles/library.css
rm library.html README_V1.md REVIEW_ME.md

# Revert modified files (uncommitted)
git checkout -- index.html js/main.js package.json vercel.json

# Or, if already committed, revert to the commit before v1
git log --oneline       # find the "v1" commit SHA
git revert <sha>
```

Everything else (existing reader, URL extract, paste/upload, localStorage-based progress) is untouched and continues to work.

---

## Files added or changed in v1

**New:**
- `api/summarize.js` — Anthropic-backed summarizer
- `js/library.js` — localStorage knowledge-bank layer
- `js/ui-finish.js` — Finish-reading flow controller
- `js/library-page.js` — library page controller (List/Atlas tabs, detail panel)
- `js/atlas.js` — minimal radial renderer for unlocked atlas
- `library.html` — library + atlas page
- `styles/finish.css` — Finish modal styles
- `styles/library.css` — library page styles
- `README_V1.md` — this file
- `REVIEW_ME.md` — user-facing review note

**Modified:**
- `index.html` — Finish button + Library link + modal templates
- `js/main.js` — wire up Finish flow at onEnd / ≥80% progress
- `package.json` — `@anthropic-ai/sdk` dependency
- `vercel.json` — `maxDuration: 60` for `api/summarize.js`

---

## Known caveats

- Rate-limit is best-effort (module-scope Map, resets on cold start). Real rate-limit needs an external store like Vercel KV or Upstash — out of scope for solo v1.
- `html2canvas` screenshots don't perfectly render CSS filters/backdrop-filter — the exported PNG may look subtly different from the on-screen card. Acceptable trade-off for a zero-backend solution.
- The atlas tab's minimal radial (`js/atlas.js`) doesn't have the orrery flourishes from `mockups/mindmap-radial.html` (rotor ticks, breathing halo, cardinal points). Those come in v1.1 once there's data to stress-test the layout.
- Mobile layout has been designed tap-safe per global CLAUDE.md but has not been tested on a physical device.
- No end-to-end tests — only smoke-level verification via `vercel dev`. Given this is a frontend-only app with no business-critical side effects, deferring test infra to phase 2 per global CLAUDE.md "no extraneous features" rule.
