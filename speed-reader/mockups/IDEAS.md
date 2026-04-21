# Ideas — Uses You May Have Missed

> Cross-cutting feature ideas for the speed-reader → knowledge system. Each has a 1-sentence "why" and a priority (H/M/L). Priority is judged on **value × proximity to MVP** — H = ship within 2 phases of MVP; M = clear win, lower urgency; L = explore later or only if free.

---

### High priority

1. **Quote-replay RSVP** — H
   Re-speed-read just the highlighted quotes from a saved note (not the whole source).
   *Why:* The quotes are the conclusions; replaying them is the cheapest possible review and reuses the existing RSVP engine. Closes the read→review loop without leaving the app.

2. **Auto-tag from concept graph** — H
   Suggested tags come from the user's *existing* concept nodes first; LLM only proposes new tags when nothing fits well.
   *Why:* Free-form LLM tagging causes drift ("attention-residue" / "attentional-residue" / "task-switching-cost"). Anchoring to the existing graph keeps the structure tight as it grows.

3. **"Related reads" surfacing on open** — H
   When the user starts a new source, show 2-3 past notes that share predicted tags — primes attention before reading.
   *Why:* Pre-activation is a documented retention booster (the brain's "expected next" prediction). Free win and the data is already there.

4. **Kindle highlights import (`My Clippings.txt`)** — H
   Drop the file in, parse it, create one note per book with quotes already populated.
   *Why:* Trivial parser, huge instant value. Many users have years of Kindle highlights gathering dust.

5. **RPE for reading (1-10 post-read rating)** — H
   Quick slider after each session: how hard was that to follow? Feeds into WPM auto-tuning + "you should re-read this" flags.
   *Why:* Mirrors the workout app's session-RPE pattern the user already has muscle memory for. Solves the "I sped through it but absorbed nothing" problem with one tap.

---

### Medium priority

6. **Weekly "knowledge diff" email** — M
   Sunday digest: concepts added, concepts strengthened (more notes attached), unread queue size, longest-orphan concept.
   *Why:* Forces a reflection moment, surfaces gaps. Same delivery channel as the Holocron weekly review the user already gets.

7. **Cross-source contradictions** — M
   When two notes under the same concept make opposing claims (LLM-detected at summarize time), flag with a "⚠ conflicts with [note]" badge.
   *Why:* Holding contradictions explicitly is how synthesis happens. Currently they sit invisible across separate notes.

8. **Gmail newsletter auto-ingest** — M
   Re-use the `holocron-refresh` Gmail pipeline, but route extracted articles to the speed-reader queue instead of straight to SRS.
   *Why:* User already has the OAuth + label setup. Closes the "I subscribe but never read" loop. Phase-2 because newsletters → reading queue → summarize is a longer chain than MVP.

9. **YouTube transcript ingestion** — M
   `yt-dlp --write-auto-sub` → strip timestamps → speed-read the transcript at 500 wpm.
   *Why:* Long-form podcasts/interviews become 15-minute reads. Especially valuable for content where the visuals don't matter.

10. **Reading-queue prioritizer** — M
    Rank unread items by how well they fill gaps in the concept graph (predicted tags vs. orphan/under-connected concepts).
    *Why:* Most reading queues degrade into FIFO chaos. A graph-aware ranker turns the queue from a guilt pile into a study plan.

11. **"Orphan concepts" surface** — M
    Concepts with only 1 source attached → candidates for deeper reading. Display in library sidebar.
    *Why:* Identifies single-source beliefs (epistemically risky). Cheap to compute from existing data.

---

### Low priority

12. **Public share mode** — L
    Export a single concept subgraph as a standalone shareable HTML page (portfolio / learning-in-public).
    *Why:* Nice for personal branding, but doesn't strengthen the user's own learning loop. Build only if the concept-graph view starts generating screenshot-worthy moments.

13. **"Re-derive my graph" button** — L
    Re-run summarization + tagging with the latest model on all stored notes (or a date range), in case the prompt or taxonomy improved.
    *Why:* Useful insurance against early-MVP tag drift, but expensive. Defer until taxonomy stabilizes — which is itself a phase-2 problem.

14. **Voice-mode RSVP** — L
    TTS reading with a visualized "current word" — for walks, commutes.
    *Why:* Different modality, different mental model. Genuinely useful but a separate product surface; wait for signal that core loop is sticky first.
