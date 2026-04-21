# Council — Next Steps for the Reading + Knowledge Product

> Input: a working RSVP reader (Vercel, `localStorage`, paste/PDF/EPUB/TXT/MD/URL), a polished-but-unbuilt mind-map mockup (`mindmap-radial.html`), the five-voice `PRODUCT_BRIEF.md`, a concrete MVP slice, and 14 prioritized ideas. Zero MVP code written. Solo dev, evenings and weekends, already owns Holocron (FastAPI + Postgres SRS) and an Anthropic key.
>
> This document is not a restatement of the brief. The brief answered "what would a good MVP look like?" This council answers a sharper question: **given the brief exists, what is the smallest sequence of moves that gets the user to a product they use on day 60, and where is the brief itself wrong?**

---

## 1. Product Strategist

The MVP's thesis — "speed-reading without retention is fast forgetting" — sounds correct and is almost certainly wrong as a motivator for *this* user on *this* week. Retention pays off in weeks 4-12, if at all, and only at volume. On day 1, what the user feels is: "I sped through a 4,000-word piece in six minutes and I'm not sure I absorbed it." The real job-to-be-done is **closure after a fast read**, not knowledge-graph construction. The brief conflates the two and builds toward the bigger one.

This matters because the MVP scope bundles two different things. The Finish-reading + summary + library list ships in a weekend and pays off on day 1. The mind-map is a speculative payoff requiring twenty-plus finished reads with tag overlap before it visually rewards anything. Shipped together, the user opens `/library` for three weeks and sees a half-empty graph. Sparse graphs become social proof against themselves. Contrarian below argues for less; I argue for **the same features, sequenced and gated so the graph only renders when it has earned its pixels.**

The sharpest single action this week is narrower than the brief's MVP: **ship the Finish-reading → free-recall → AI-summary → save-to-library flow, with the library as a reverse-chronological list only, no graph view at all.** That's roughly 60% of the brief's MVP and answers the core question — "will I use this enough to care about a mind-map?" — within ten finished reads. Shipping the graph too early forces the user to enjoy building the pipeline more than using the tool, the solo-dev failure mode the Pragmatist names next.

**Recommendation:** Cut the force-directed graph from the v1 ship. Build the Finish-reading → free-recall → summary → list flow this weekend. Add a visible counter on the library list that says "Mind-map unlocks at 15 sources" or similar. The graph only renders once there are enough nodes for it to feel alive, which doubles as an engagement mechanic. Ship the graph in week 3 or 4, after the behavioral data (is the user actually finishing reads?) tells you whether the bigger investment is warranted.

---

## 2. Solo-Dev Pragmatist Engineer

The Strategist is right about sequencing but polite about why. The single-biggest implementation risk is not summarization quality, not cost, not graph rendering. It is **the boundary between the RSVP session and the post-read flow — specifically, how reliably you detect "the user finished the article" without being annoying.** Look at the code: `js/main.js` has `player.onEnd`, but end-of-text is one of three real completion states. The others are "paused near the end and went back home" and "got interrupted, came back later." The reader persists progress via `storage.updateEntryProgress`, but there is no `finished_at` concept anywhere. Building a finish-modal assumes a clean moment exists. It doesn't. You will spend an evening on "when does the Finish button become available, and what happens if the user closes the tab mid-summarize" — and you will get it wrong once in production, which means leaked summarize calls, each one a real dollar of Anthropic spend.

The second risk is boring: **`/api/summarize` timeout on Vercel.** Sonnet 4.6 with 20k input tokens can take 15-30 seconds. Hobby-tier serverless functions have a 10-second default (60s on Pro). The brief doesn't mention this. The architecture doc says "cap input at ~30k chars" but says nothing about `vercel.json` duration config. One-line fix (`"functions": { "api/summarize.js": { "maxDuration": 60 } }`) that won't be caught until the first real summarize — which is the user's first summarize, the moment the product forms an impression. Ship the config correctly from day 1.

Third — and the Contrarian has a real point here — is **attention-switching between builder and user.** Summarize endpoint: six hours. Library page: another six. Mind-map: easily twenty, because d3-force with mobile interaction polish is a long tail of small bugs. During that twenty-hour slog the user is not using their own speed-reader. Stickiness atrophies while surface area grows. You avoid this by shipping every increment as a separate route so the existing reader stays live. Do not break `index.html` or `js/main.js` for more than one evening at a time.

**Recommendation:** Before any feature work: (1) add a 60-second `maxDuration` to `vercel.json` for the summarize function from the first commit; (2) add a `finished_at` field to the localStorage schema this week as a standalone refactor, independent of the finish-flow — this de-risks the finish-modal work by separating schema migration from feature work; (3) keep the library at `/library.html` as a new page rather than modifying `index.html`'s sidebar panel, so the existing reader stays exactly as it is today throughout the build.

---

## 3. Habit / Behavior Designer

The Strategist's bet on closure is close but incomplete. Closure is a one-shot dopamine hit; it gets you day 2. The question nobody in the brief is asking: **what pulls the user back on day 14, after the summarize novelty wears off, and on day 60, when the mind-map has density but the user has built a reading habit elsewhere?** The brief's implicit answer is "the mind-map will be beautiful." That's a designer's answer, not a behavioral one. Beautiful things get looked at once. Daily-opened things have a *cheap action with a visible result* at the top of the flow, every time. Speed-reader has that — paste-and-go is a ten-second loop. The post-read flow has closure. But there is no reason to return *between* reads. No stream. No unread-queue indicator. No re-encounter surface. The product is one-and-done per article.

The habit mechanic I'd propose that isn't in the plan is a **daily quote primer at app open.** When the user lands on `index.html`, before they paste anything, show a past `key_quote` pulled at random, rendered in the same RSVP style (single-word pulse, 350wpm) — a three-to-five-second replay of something they've already absorbed. Not a list, not a graph; a *re-encounter surface* using the existing RSVP engine on stored quotes. It creates a primitive: opening the app does something for me before I ask it to. It's also a spaced-repetition teaser without being a full SRS — if Holocron integration never ships, the memory layer still has felt presence. The Learning Scientist is right that generation beats re-reading; re-exposure to quotes at RSVP speed is not generation but it is the cheapest possible cue, and cues are what retrieval requires. Idea #1 in `IDEAS.md` (Quote-replay RSVP) is adjacent but framed as user-initiated; I'm proposing the automatic, app-open variant.

The Strategist will push back that this adds scope; the Pragmatist will note it requires library content to exist. Both are right. It's not v1 — it's v2, shipped the day after the library has five sources. One evening: pick a random quote on home-screen mount, render it with the existing player, fade out after one pass. The insight is that the app's own open-state is the habit trigger, not the user deciding "time to review." That's the difference between a tool that lives in the tab and a tool the user has to remember to use.

**Recommendation:** After shipping the Strategist's v1 (Finish → recall → summary → list), the next increment is not the mind-map. It's the app-open quote primer: on `index.html` load, if the library has any `key_quotes`, pulse one through the RSVP engine for 3-5 seconds before the paste textarea gets focus. This makes re-encounter the default state of opening the app, costs one evening, and is the thing the brief is missing.

---

## 4. Personal-Tool Distribution

The unfair advantage is already in the codebase. The RSVP reader's single-word pulse with pivot-letter highlight is distinctive enough that a screenshot conveys the product in two seconds. The mind-map mockup extends this (orrery aesthetic, Fraunces, JetBrains Mono) into territory that screenshots cleanly. The distribution question for a solo tool isn't "how do I get users" — it's **"what single visible artifact, when shown to one friend, gets a 'wait, how did you make that' response?"** For Readwise it was the daily review email. For Obsidian it was the graph view, full stop — the graph is the reason Obsidian beat Roam in mindshare, even though Roam's linking was more sophisticated. The graph is the meme.

Here's my disagreement with the Strategist: he wants to cut the graph from v1 to avoid the empty-state problem. Half-right. The v1 graph doesn't need to be a full mind-map — it needs to be **the minimum shape that's screenshot-bait**. A single concept's radial with 6-8 sources around it — `mindmap-radial.html` already exists — looks impressive at five sources; it doesn't need twenty. The empty-graph problem is a force-directed-specific failure. Radial views with a concept at the center look deliberate and intentional at any density. The brief's Frontend voice picked force-directed; for distribution purposes, radial is the better v1 surface because it works at N=3.

The shareable artifact I'd build: **after a read is summarized, the user gets a "reading card"** — an image-exportable panel with the title, 3-sentence summary, top two quotes in Fraunces serif, tag chips, and a small radial showing how this source connects to one or two prior reads. Designed to be screenshot-posted to X/Signal/iMessage. Looks like a Readwise review but per-piece. Visible proof the user read something and thought about it. The mind-map comes later as a second artifact. The reading card is first because it's per-source — every summarize event is a potential share moment, whereas the full graph is shareable maybe monthly.

**Recommendation:** v1 ships the Finish-flow with a reading-card output as the primary result format, not a prose page. Card is 1080x1350 (Instagram-story ratio), includes title, summary, top quotes, tag chips, a minimal 3-6 node radial showing concept overlap with prior reads, and a tiny "made with [speed-reader url]" footer. `html2canvas` handles the export in-browser. This replaces the brief's list-card UI for v1; the list view becomes a grid of these cards. Distribution is not an afterthought — it is the v1 layout choice.

---

## 5. Contrarian

Everyone above is building. I'm trying to talk you out of it. The brief's premise — "speed-reading without retention is fast forgetting" — quietly assumes you're speed-reading enough to need retention. Look at your own localStorage on the deployed app. How many saved sources are there? How many did you read this week? Last week? If the answer is "a handful," the memory-bank layer is a solution in search of a usage pattern that hasn't been established. The speed-reader ships. It works. Four weekends on summarization, library UI, force-directed graph, radial view, and Holocron integration will not compound that value. Every hour spent on the memory bank is an hour not spent on the one thing that validates the thesis: **reading more articles through the existing tool.**

The Strategist says the MVP answers the thesis question. It doesn't. The thesis question is "does speed-reading make retention worse, and would this user benefit from a retention layer?" Answerable without new code. Read twenty articles through the existing reader over two weeks. Keep a `.txt` file with a one-line takeaway per article. If you *couldn't* write the takeaways, build the summary layer. If you could, summarization is a luxury and the real problem is "I don't read enough," which no graph fixes. The Habit Designer asks whether you open it on day 60 but proposes new features to drive that; I'm proposing you first check if you open it on day 60 with the product you already have.

The second contrarian move the Pragmatist half-endorsed: **the scariest bug in personal-tool building is that the act of building replaces the act of using.** You built a speed-reader. You aren't using it enough. A summary layer, a library, and a graph won't fix that; they'll give you six weekends of the feeling of progress. Holocron exists. It's a retention layer. It's tested. If retention is actually the bottleneck, the correct action isn't another retention layer inside the speed-reader — it's manually copying interesting quotes from the speed-reader into Holocron as cards for two weeks to see if the bridge is worth automating. You'll almost certainly find you didn't copy anything over, because reading-to-card friction was never the bottleneck — the bottleneck is that most of what you read isn't worth remembering. Which the mind-map won't surface until it has fifty nodes, by which point you'll have spent fifty evenings building it.

**Recommendation:** Do nothing for two weeks. Read twenty articles through the existing reader. Keep a plain `.txt` file called `takeaways.txt` on your desktop with one line per article. At the end of two weeks, look at the file. If the file is empty, the problem is volume, not retention, and the brief's premise is wrong. If the file has twenty lines that you wrote yourself, the brief is solving an already-solved problem. Only if the file has five or ten and you can see you're dropping the rest does the memory-bank layer have a justified reason to exist — and even then, build only the summary-to-list flow, skipping the graph entirely until month 3.

---

## Synthesis — Next Steps, Ranked

The council disagrees on one thing: whether to build anything this month (Contrarian: no; everyone else: yes, but less than the brief says). The disagreement is productive because it forces a cheap pre-commit test into step 1. The voices converge on a sequence strictly tighter than `PRODUCT_BRIEF.md`'s MVP: fewer surfaces, sequenced gates, distribution baked into v1 rather than deferred.

### 1. Two-week usage check before any feature work — 1 hour setup, 2 weeks elapsed

Create a `takeaways.txt` on the desktop. For two weeks, every article read through the existing reader gets one line of free-recall written manually. **Argued by:** Contrarian. **Pushed back by:** Strategist (delays UI-driven validation). **Why step 1:** one-hour investment; downside of skipping is up to four weekends on a wrongly-motivated product. The asymmetry makes it a free option. If the user already knows they read 5+ pieces a week and the takeaways would be non-empty, skip to step 2.

### 2. Ship Finish → free-recall → summarize → list, no graph — 1 weekend

`/api/summarize` (Vercel, Sonnet 4.6, strict JSON tool-use, verbatim-quote validation, 60-second `maxDuration` in `vercel.json`). Finish-reading button on the RSVP view with a free-recall textarea preceding the AI output. `/library.html` as a reverse-chronological list. **No graph in this ship.** Add `finished_at` to the localStorage schema as a preparatory refactor before feature work. **Argued by:** Strategist, Pragmatist. **Pushed back by:** Distribution (wants reading-card in v1), Contrarian (wants zero code). **Why step 2:** minimum shape that answers "do I open this more now that it has a post-read flow?" Graph has no validation value until data accumulates.

### 3. Rebuild the list card as a screenshot-able reading card — 1 evening

Replace the prose list item with a designed card (1080x1350 export size, Fraunces for quotes, tag chips, minimal 3-6 node radial if ≥2 sources share a tag). Add `Export as image` via `html2canvas`. **Argued by:** Distribution. **Pushed back by:** Pragmatist (adds an evening), Strategist (wanted the radial gated on N≥15). **Why step 3:** baking it into step 2 misses the weekend deadline; doing it right after means v1 is distribution-aware before you've built anything nobody wants to look at.

### 4. App-open quote primer — 1 evening

On `index.html` open, if the library has ≥5 starred `key_quotes`, pulse one through the RSVP engine for 3-5 seconds before the paste textarea takes focus. **Argued by:** Habit Designer. **Pushed back by:** Strategist (gimmicky if quote is bad) — mitigation: star-filter, one-line schema addition. **Why step 4:** requires library content, which doesn't exist until steps 2-3 have been in use 1-2 weeks. Sequencing before data means an empty feature on app open — the exact problem Strategist raised about the graph.

### 5. Radial mind-map, gated on N≥15 sources — 1 weekend

Ship `mockups/mindmap-radial.html`'s aesthetic as the `/library.html` graph tab, gated by a "mind-map unlocks at 15 sources" counter. Below 15: counter and preview. At ≥15: radial renders with concept-at-center and source spokes. No force-directed. **Argued by:** Strategist (gated rollout), Distribution (radial over force-directed). **Pushed back by:** the brief itself, which specified force-directed — explicitly overriding based on the shareable-at-low-N argument. **Why step 5:** graph needs volume to feel alive, which step 4's habit mechanic drives. Week 4+ means it renders into a library with density, first view is a payoff not an empty state.

---

## Open Questions for the User

These are not rhetorical. Each answer materially changes what gets built above.

1. **How many articles did you speed-read through the existing tool in the last 14 days?** If the answer is <5, step 1 (the Contrarian's pre-commit test) is non-optional and probably extends to a month. If it's >15, skip step 1 and start step 2 this weekend. This is the single most important input to the sequence and only you know the number.

2. **What's your Vercel plan — hobby or pro?** Hobby has a 10-second serverless timeout; summarizing a 20k-token article will hit it. If hobby, the summarize function needs either a streaming response, a chunk-and-reduce approach from day 1, or a plan upgrade. The Pragmatist's `maxDuration: 60` fix only works on Pro. The brief doesn't mention this; it materially changes the step 2 implementation.

3. **Is the Anthropic key going to be yours via Vercel env var, or BYOK from the user in settings?** (Open question #6 in the brief, unanswered.) If yours, you own the bill and need a rate limit on `/api/summarize` from day 1 to avoid a runaway cost bug. If BYOK, onboarding friction means the first-ever use is blocked by a settings trip, which meaningfully degrades the day-1 impression. I'd default to yours-with-rate-limit for v1 because the friction cost is worse than the dollar cost at this volume, but this is your money.

4. **Do you actually want Holocron integration, or is it a fixed feature in your mental model because you already built Holocron?** The brief treats it as phase 2. The Contrarian's argument suggests the bridge may never pay off if the reading volume is low. If the honest answer is "I built Holocron, I should use it, but I haven't been actively adding cards manually for the last month," then the integration is not a feature, it's a sunk-cost pull. Worth surfacing as an explicit go/no-go before step 5.

5. **How do you want to handle re-reads of the same URL?** Open question #7 in the brief is unresolved, and it matters for step 4 (the quote primer) and step 3 (reading card export). If re-reads create new library entries, the library bloats and the quote primer over-weights recent re-reads. If re-reads attach to existing entries, you need an "I read this again on [date]" field and a policy for what happens to the summary (keep, refresh, both). The cheapest correct answer is: content-hash dedup keyed to text, so re-reads update the `last_read_at` on the existing entry without re-summarizing. But this is a schema choice that is cheaper to make once, now, than to migrate later.
