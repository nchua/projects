# Architecture Sketch — Speed-Reader → Knowledge System

> Planning artifact. Concrete tech picks with rationale, distinguishing **what exists today** from **what's new**.

---

## High-level diagram

```
                        ┌─────────────────────────────────────────────┐
                        │  SOURCES                                    │
                        │  URL │ PDF │ EPUB │ paste │ (Gmail, YT) →   │
                        └──────────────────┬──────────────────────────┘
                                           │
                          existing extract pipeline
                       (api/extract.js — Readability+JSDOM)
                                           │
                                           ▼
                        ┌─────────────────────────────────────────────┐
                        │  SPEED-READER  (existing, untouched)        │
                        │  RSVP UI · WPM tuning · localStorage lib    │
                        └──────────────────┬──────────────────────────┘
                                           │  on "Finish reading"
                                           ▼
                        ┌─────────────────────────────────────────────┐  ◄── NEW
                        │  /api/summarize  (Vercel function)          │
                        │  Anthropic Sonnet 4.6 · structured output   │
                        │  → { summary, tags[], key_quotes[] }        │
                        └──────────────────┬──────────────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              ▼                            ▼                            ▼
   ┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
   │ Note store       │         │ Holocron sync    │         │ Embedding store  │
   │ localStorage     │ ◄── NEW │ POST /learning-  │ phase 2 │ MiniLM @ 384d    │ phase 2
   │ (MVP)            │         │ units            │         │ (browser, WASM)  │
   │ → IndexedDB      │         │ (existing API)   │         │                  │
   │ when >MB         │         └──────────────────┘         └──────────────────┘
   └────────┬─────────┘                                              │
            │                                                        │
            └──────────────────┬─────────────────────────────────────┘
                               ▼
                  ┌─────────────────────────────┐  ◄── NEW
                  │  /library.html              │
                  │  list view · mind-map view  │
                  │  ↺ "Speed-read again"       │
                  │  ↺ "Quote-replay RSVP"      │
                  └─────────────────────────────┘
```

---

## What exists vs. what's new

### Exists (no changes in MVP)
- `speed-reader/index.html` + `js/main.js` — RSVP reader with paste / upload / URL flows.
- `speed-reader/api/extract.js` — Vercel serverless URL extractor (Readability + JSDOM).
- `speed-reader/vercel.json` — deploy config.
- localStorage-based library (titles + raw text only, no metadata).
- Holocron API at `/api/v1/learning-units` — already accepts cards/concepts/topics.

### New (MVP scope)
- `speed-reader/api/summarize.js` — Vercel function. Input `{ text, title }`. Output `{ summary, tags[], key_quotes[] }`. Anthropic SDK call with structured tool use.
- `speed-reader/library.html` — new page. Lists notes, embeds the chosen mind-map view (force-directed for MVP).
- `speed-reader/js/library.js` — note storage layer (localStorage with versioned schema), graph derivation, d3 render.
- `speed-reader/js/finish.js` — "Finish reading" button hook in the existing reader. Calls summarize, persists, navigates to library.

### New (phase 2)
- Holocron sync — POST notes as `learning-unit` rows; lets the existing inbox/SRS flow take over.
- Local embeddings — MiniLM via [`@xenova/transformers`](https://github.com/xenova/transformers.js) in-browser (WASM). Concept-similarity edges in the graph.
- Multi-source ingest: Gmail newsletters (re-use `holocron-refresh` skill pipeline, but route to speed-reader queue), YouTube transcripts (`yt-dlp --write-auto-sub`), Kindle `My Clippings.txt`.
- Quote-replay RSVP — re-speed-read just the highlighted quotes.

---

## Tech picks, with rationale

| Decision | Pick | Why | Rejected |
|---|---|---|---|
| **Storage (MVP)** | `localStorage` JSON, versioned schema | Preserves zero-server-storage privacy model. ~5MB ceiling is fine for ~500 notes if quotes/summary only. | SQLite-on-Vercel (no fs), Postgres (over-engineering for solo), Vercel KV (re-introduces server storage) |
| **Storage (when MVP outgrows it)** | IndexedDB via `idb` | 50MB+ headroom, still client-side. Same privacy posture. | Sticking with localStorage past ~3MB (slow per-write JSON.parse) |
| **Summarization model** | Claude Sonnet 4.6 via Anthropic SDK | Cheap enough (~$0.003/article at 5k tokens in, 500 out), strong at structured extraction. | Opus (10× cost, marginal lift on this task), Haiku (slips on quote selection), local llama (slow on user's M-series, no win) |
| **Structured output** | Tool-use with explicit schema for `{summary, tags, key_quotes}` | Eliminates JSON-parse errors and prompt-injection-induced format drift. | JSON-mode (less reliable), regex on free-form (brittle) |
| **Caching** | Anthropic prompt caching on the system prompt + tag taxonomy | At 50 articles/week the cached prefix amortizes well. | None (re-billing taxonomy each call) |
| **Embeddings (phase 2)** | `Xenova/all-MiniLM-L6-v2` in-browser via transformers.js | Local, free, 384d is enough for ~10k personal notes. Privacy-preserving. | OpenAI/Voyage embeddings (sends every note to a third party), `text-embedding-3-large` (3072d, overkill) |
| **Mind-map render** | d3 v7 from CDN | Already chosen for mockups, no build step, mature force/radial primitives. | Cytoscape (heavier, less flexible), 3D libs (cool, not useful) |
| **SRS** | Reuse Holocron — do not rebuild | FSRS is already implemented there; cards flow into existing inbox. | Re-implementing FSRS in speed-reader (duplicates logic, two sources of truth) |
| **API surface** | Reuse Vercel `api/` folder pattern | One deploy, one CORS posture, no infra to learn. | Separate worker / Cloudflare (more moving parts) |
| **Tag schema** | Constrained vocabulary derived from existing concept nodes (phase 2) — free-form for MVP | Free-form is fine while taxonomy is small; constrained avoids tag sprawl as it grows. | Hard taxonomy from day 1 (premature), purely free-form forever (drifts) |

---

## Data shapes (MVP)

### `localStorage["sr.notes.v1"]` — array of:
```ts
{
  id: string,              // uuid
  title: string,
  source_type: "url" | "paste" | "pdf" | "epub" | "txt" | "md",
  source_url?: string,
  date_read: string,       // ISO
  wpm: number,
  rpe?: number,            // 1-10, user-rated post-read (phase 2)
  text_hash: string,       // for dedup
  summary: string,
  tags: string[],
  key_quotes: string[],
  // raw text NOT stored (privacy + size); re-fetchable from source for URLs,
  // stays in original upload otherwise
}
```

### `/api/summarize` contract
```http
POST /api/summarize
{ "text": "...", "title": "..." }

200 OK
{
  "summary": "2-3 sentence dense summary",
  "tags": ["concept-name", ...],          // 3-7 tags
  "key_quotes": ["verbatim quote", ...]   // 2-5 quotes
}

4xx / 5xx
{ "error": "..." }
```

---

## Privacy posture

- **MVP:** every text the user reads transits the new `/api/summarize` endpoint, which calls Anthropic. The Vercel function is stateless — it does not log or persist text. Anthropic API has its own retention policy (zero-data-retention available on enterprise tier; default is 30 days for abuse monitoring).
- **User-controllable toggle (recommended):** "Summarize this read" checkbox before "Finish reading." If unchecked, note is stored locally with title + first-line snippet only — same posture as today.
- **Phase 2 escape hatch:** local LLM via `webllm` for users who never want text to leave the device. Quality drop is real; surface honestly in the toggle copy.
- **Holocron sync (phase 2):** opt-in per note; explicit "Send to Holocron" button. Don't auto-sync — Holocron has its own server and DB.

---

## What this architecture deliberately does NOT add

- No auth / multi-user — solo dev.
- No CI/CD beyond Vercel auto-deploy on push.
- No new database. localStorage is the database for MVP.
- No background job queue — every action is synchronous from the user's tap.
- No analytics / telemetry.
- No mobile app — the existing speed-reader is mobile-web-friendly already.

Per global CLAUDE.md "no extraneous features": every component above is here because it directly enables the user loop, not because it's tidy.
