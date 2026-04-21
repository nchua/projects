# Speed-Reader → Learning System with Mind-Map

**Product brief — integration layer between Speed-Reader (RSVP), Holocron (SRS), and a knowledge graph view.**

---

## 1. Product Thesis

Speed-reading without retention is just fast forgetting. This integration turns each RSVP session into a durable knowledge artifact: at the end of a read, the user gets a tight summary, a small set of tags, and pulled quotes — and over weeks, those artifacts accrue into a navigable mind-map of what they have actually consumed. The Holocron handoff converts the highest-signal artifacts into spaced-repetition cards, closing the loop from "I read it once" to "I remember it." If it works, the user reads more deliberately, abandons low-value sources earlier (the graph makes thin clusters obvious), and stops re-reading articles they already half-know.

## 2. User Loop

```
                    +--------------------------------------+
                    |                                      |
                    v                                      |
   [Ingest]  -->  [RSVP Read]  -->  [Finish & Summarize]  -+
   paste/url        speed                |                  |
   pdf/epub         WPM                  v                  |
                                   [Tag + Quotes]           |
                                         |                  |
                                         v                  |
                                   [localStorage]           |
                                    library entry           |
                                    /         \             |
                                   v           v            |
                          [Mind-Map View]   [Send to        |
                           force/radial/    Holocron] ----> |
                           timeline             |           |
                              |                 v           |
                              |          [SRS Reviews] -----+ (re-encounter
                              |                              prompts re-read)
                              v
                        [Cluster gaps]
                        suggest next ingest
```

Feedback edges that matter: (a) Holocron review failures should resurface the source in the library with a "needs re-read" badge; (b) the mind-map should suggest adjacent ingest targets when a cluster is dense but shallow.

## 3. The Five Viewpoints, Reconciled

### 3.1 Learning Scientist

Adding an LLM-generated summary at the end of an RSVP session is a double-edged intervention. The retention literature is unambiguous that *generation* — producing a summary, a question, a paraphrase — beats re-reading by a wide margin. If the system hands the user a finished summary the moment they finish reading, it satisfies a felt need ("I want closure") while quietly substituting machine cognition for the user's own retrieval effort. That is the failure mode to avoid. RSVP already taxes working memory: the eye is pinned, sub-vocalization is suppressed, and there is no opportunity to pause and consolidate. So the moment after reading is precisely when active recall is most valuable — and most fragile.

The right pattern is *generation first, AI second*. When the user hits "Finish reading," prompt them with a 20-second free-recall box ("What were the 2-3 ideas worth keeping?") *before* showing the AI summary. The AI output then functions as feedback, not as the artifact of record. For card creation, default to AI-suggested cards going to a low-confidence inbox (Holocron already does this), and reserve "auto-promote to deck" for cards the user explicitly stars or edits. Manual card creation should remain one click away for anything the user already knows is a keeper.

**Recommendation:** Insert a mandatory ~15-second free-recall step between "Finish reading" and the rendered AI summary. Send AI-generated cards to the Holocron inbox by default; only user-edited or user-starred cards skip the inbox. Track recall-vs-AI overlap as a private metric — if they diverge often, the source was probably misread, not the model wrong.

### 3.2 Information Architect

Three entity types are doing different work and must not be conflated: **Source** (the article/PDF/URL the user read), **Concept** (an atomic idea that can recur across many sources — "compound interest," "RSVP saccade suppression"), and **Quote** (a verbatim span anchored to one source). Tags applied to a Source are noisy by nature ("productivity," "AI"); tags applied to a Concept are the actual knowledge graph. Most personal-knowledge systems fail because they only have Sources and free-form tags, which produces a tag soup where everything is "interesting" and nothing connects.

Free-form tags should be allowed at ingest (low friction, captures the user's vocabulary) but the system should *suggest existing concepts first* and only mint a new concept when the user opts in. This is the Zettelkasten/Obsidian lesson: atomic notes (Concepts) are the durable unit; source notes (Sources) are the bibliography that points at them. The mind-map's nodes should be Concepts, not Sources — Sources are edges and evidence. A canonical schema for this MVP: `Source { id, title, url, read_at, wpm, summary, quotes[], concept_ids[] }`, `Concept { id, label, aliases[], source_ids[] }`, `Quote { id, source_id, text, concept_ids[] }`.

**Recommendation:** Constrain tags to a growing concept vocabulary with fuzzy-match suggestions; allow new concept creation but require one extra click. Render the mind-map on Concepts with Sources as evidence on edge hover. Defer the full Zettelkasten "atomic note" pattern (each concept gets its own writable note) to phase 2 — for MVP, a Concept is just a labeled node with backlinks.

### 3.3 Data / ML Engineer

Summarization and tag extraction at ~50 articles/week is a trivial-cost workload if the prompt is structured well. A single Claude Sonnet 4 call with the article text returning a strict JSON schema (`{summary, tags, key_quotes}`) will run roughly 4-8k input tokens and ~400 output tokens per article. At public Sonnet pricing that is on the order of a few cents per article and well under $5/month at the stated volume. Haiku is tempting for cost but tag quality and quote selection degrade noticeably on long-form input; Sonnet is the right default. Use a single prompt with explicit JSON output schema, a small few-shot block (one good example), and `tool_use` or a JSON-mode equivalent for reliable parsing.

The real risks are not cost but quality and consistency. Hallucinated tags ("blockchain" on an article that never mentions it) and summaries-by-headline (the model summarizes the title and intro because the body got truncated by a context-window or extraction failure) are both common. Mitigations: (a) cap input at a known token budget and chunk-summarize for long PDFs with a final reduce step; (b) constrain tag suggestions by passing the user's existing concept vocabulary into the prompt as a preferred list; (c) extract quotes by asking for verbatim spans and then *verifying they exist in the source text* before storing — a one-line string-contains check kills the hallucination class entirely. Embeddings for the mind-map similarity edges can wait — for MVP, tag co-occurrence is a cheap and surprisingly good proxy. When embeddings do come in, Voyage or OpenAI `text-embedding-3-small` over the API is fine; local embeddings (e.g., `bge-small`) are only worth the operational cost if the privacy posture demands it.

**Recommendation:** Sonnet 4 with strict JSON output, existing-concept vocabulary injected into the prompt, and verbatim-quote validation post-generation. No embeddings in MVP — derive graph edges from shared tags. Cache by content hash so re-finishing the same article is free.

### 3.4 Frontend / Data-Viz

Three layouts were mocked: force-directed, radial, and timeline. Each earns its place only if it answers a different question. **Force-directed** answers "what is this corpus actually about?" — clusters surface naturally and the user notices a dense cluster they did not realize they had been reading around. It is the right *exploration* view but a poor *daily* view because it re-flows on every change and has no stable spatial memory. **Radial** (concept-at-center, sources as spokes) answers "what do I know about X?" — it is the right *drill-down* view, reached by clicking a node in the force graph or searching a concept. **Timeline** answers "what have I read recently and how does it relate to last month?" — it is the right *journaling* view and probably the most-used surface for someone reading 50 things a week.

The daily-use interaction is timeline-default: open `/library`, see the last week banded by day with concept-colored dots, click any dot for the source card with summary + quotes + "send to Holocron" button. Force-directed is a tab away and meant for Sunday-afternoon "what am I actually learning" sessions. Radial appears inline when the user clicks a Concept anywhere. Critical interactions across all three: hover shows source title and summary preview; click opens the source card in a side panel without losing graph state; keyboard navigation (`j`/`k` between nodes) for the speed-reader audience that already prefers keyboard.

**Recommendation:** Ship force-directed for MVP (matches the plan's wording and is the most demoable single view). Make timeline the default landing view in phase 2 once enough data exists to make timeline meaningful. Radial as a modal triggered from concept clicks in any view.

### 3.5 Privacy / Security

Speed-Reader today touches no server-stored user data — `api/extract.js` is a stateless URL fetcher and everything else lives in `localStorage`. Adding summarization breaks that posture in exactly one place: full article text is sent to Anthropic's API. That is a real change and should be named explicitly in the UI, not buried. Anthropic's commercial terms cover non-training-on-API-data, which mitigates the worst-case ("my reading history fine-tunes a model") but does not eliminate the in-flight and at-rest exposure during processing. For a solo user reading public articles this is a reasonable trade; for someone reading internal company docs through this tool, it is not.

Concrete controls: (1) a per-source "summarize" button rather than auto-summarize, so the user makes an explicit decision per article; (2) a global toggle "always summarize on finish" defaulted off; (3) a visible "this will send the article text to Anthropic" disclosure on the Finish button the first time and in settings always; (4) no telemetry, no analytics, no error reporting that includes article content. The `/api/summarize` Vercel function should be a thin pass-through — no logging of request bodies, no DB write, just call Anthropic and return JSON. Phase 2 considerations: a "local-only" mode using a small on-device model (WebLLM/Transformers.js) for users who want zero egress, accepting lower quality. Storage stays in `localStorage` for MVP as the user specified — this is the strongest single privacy property the product has and worth preserving until there is a concrete reason to break it (cross-device sync is the likely trigger).

**Recommendation:** Explicit per-finish summarize action (no auto), one-time disclosure modal, no server-side logging of article content, `localStorage`-only storage for MVP. Treat any future move to backend storage as a privacy-relevant decision requiring its own user-facing explanation.

## 4. Feature Priority Matrix

| Feature | Effort | Value | Phase |
|---|---|---|---|
| `Finish reading` button on RSVP view | S | H | MVP |
| `/api/summarize` Vercel function (Sonnet, JSON out) | S | H | MVP |
| Free-recall prompt before AI summary | S | H | MVP |
| localStorage library schema (Source/Concept/Quote) | S | H | MVP |
| `/library.html` with source list + summary cards | M | H | MVP |
| Force-directed mind-map (tag co-occurrence edges) | M | M | MVP |
| Verbatim-quote validation post-LLM | S | H | MVP |
| Existing-concept vocabulary injection into prompt | S | M | MVP |
| Per-finish privacy disclosure + settings toggle | S | H | MVP |
| Holocron handoff (`POST /api/v1/learning-units`) | M | H | Phase 2 |
| Radial concept drill-down view | M | M | Phase 2 |
| Timeline view as default library landing | M | H | Phase 2 |
| Card-failure → "needs re-read" badge on source | M | M | Phase 2 |
| Embedding-based similarity edges (Voyage/OpenAI) | M | M | Phase 2 |
| Long-document chunk + reduce summarization | M | M | Phase 2 |
| Cross-device sync (encrypted blob, opt-in) | L | M | Phase 3 |
| Local-only WebLLM summarization mode | L | L | Phase 3 |
| Concept notes (Zettelkasten atomic) | L | M | Phase 3 |

## 5. Open Questions

1. Free-recall prompt: hard requirement (cannot skip) or soft default with a "skip" link? Hard is better pedagogically; soft is better for adoption.
2. Should the Holocron inbox receive *every* finished read's candidate cards, or only ones the user explicitly sends? Volume matters — 50/week × 5 cards is 250 inbox items.
3. Tag namespace: shared with Holocron's concept namespace from day one, or separate vocabularies that get reconciled later? Reconciliation is painful; sharing requires Holocron API on the critical path.
4. Should the mind-map render Sources as nodes too (alongside Concepts), or strictly Concepts-only with Sources hidden behind hover? The latter is cleaner; the former is more honest about the corpus.
5. PDF/EPUB content often exceeds a single-call context budget — chunk-and-reduce in MVP, or punt long docs until phase 2?
6. Anthropic API key: user-supplied (BYOK in settings) or platform-supplied via Vercel env var? BYOK keeps cost off the user's hosting bill and reinforces the privacy story, but adds onboarding friction.
7. When a user re-reads a source, do we re-summarize or show the cached summary? Caching is cheap and consistent; re-summarizing might catch things they noticed this time but not last.
8. Is "abandoning" a source first-class (a tracked outcome) or invisible (just no Finish click)? Tracking abandonment is a strong signal for the suggest-next-ingest feature later.

## 6. MVP Slice

**Scope:** One sitting. No Holocron integration. No backend storage. No multi-source ingestion beyond what speed-reader already supports.

### Endpoint contract

`POST /api/summarize`

Request:
```json
{
  "text": "string (article body, max ~30k chars)",
  "title": "string (optional)",
  "known_concepts": ["string"]
}
```

Response (200):
```json
{
  "summary": "string (3-5 sentences)",
  "tags": ["string", "..."],
  "key_quotes": ["string (verbatim from text)", "..."]
}
```

Errors: `400` invalid body, `413` text too large, `502` upstream Anthropic failure. No request-body logging. No persistence server-side.

### localStorage schema

Key: `speedreader.library.v1`

```json
{
  "sources": [
    {
      "id": "uuid",
      "title": "string",
      "url": "string|null",
      "ingested_at": "iso8601",
      "finished_at": "iso8601|null",
      "wpm": 450,
      "char_count": 12345,
      "user_recall": "string|null",
      "summary": "string|null",
      "tags": ["string"],
      "key_quotes": ["string"]
    }
  ],
  "concepts": [
    { "id": "uuid", "label": "string", "source_ids": ["uuid"] }
  ]
}
```

Concepts are derived from tags on first appearance: when a tag string is new, mint a Concept with that label; otherwise attach the existing Concept's `id` to the source.

### UI changes

- **RSVP view:** add a `Finish reading` button visible when playback reaches end-of-text or when the user clicks pause near the end. Clicking opens a modal: free-recall textarea (autofocus, 15-second visible timer but not enforced), then a `Summarize with AI` button that POSTs to `/api/summarize` and renders results inline. A `Save to library` button persists the source.
- **First-time disclosure modal:** "Clicking Summarize sends the article text to Anthropic's API. Nothing is stored on a server. [Don't show again] [Cancel] [Continue]."
- **New page `/library.html`:** two tabs — `List` (default; reverse-chrono cards with title, summary, tag chips, quote count) and `Map` (force-directed graph using d3-force or cytoscape.js; nodes are Concepts sized by source-count, edges are tag co-occurrence weighted by shared-source count; click node opens a side panel listing sources for that concept).
- **Header link** from the existing reader page to `/library`.

### Out of MVP (explicit)

- Holocron POST. No card generation, no card UI.
- Backend storage of any kind (no SQLite, no Postgres, no KV).
- Embeddings, semantic similarity edges.
- Radial and timeline views.
- Long-document chunking — cap at ~30k chars, error gracefully above that.
- Cross-device sync.
- Re-read tracking, abandonment tracking, suggest-next-ingest.
- Tag editing UI beyond accepting/rejecting AI suggestions at finish-time.

### Acceptance criteria

1. User can paste an article, speed-read it, click `Finish reading`, type a free-recall, click `Summarize`, and within ~10 seconds see a summary, 3-7 tags, and 2-5 verbatim quotes.
2. Every returned quote is a substring of the submitted text (verified server-side; offending quotes dropped before response).
3. Saving the source persists it to `localStorage` and it appears at the top of `/library` on reload.
4. `/library` Map tab renders a force-directed graph for any library with ≥2 sources sharing ≥1 tag; clicking a concept node shows the sources behind it.
5. Page reload preserves all library state. Clearing browser storage clears the library (no orphaned server state).
6. `/api/summarize` does not persist or log request bodies (verified by code inspection of the Vercel function).
7. First summarize of a session triggers the disclosure modal; subsequent ones do not, unless user re-enabled it in settings.
