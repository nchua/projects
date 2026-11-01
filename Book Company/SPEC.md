# Serialized AI Children's Books — Book Generation Pipeline Spec

**Status:** v0.1 draft, 2026-11-01. Phase 0 session 1 (scaffold, working S0) and session 2 (stage contract, Claude provider, S3–S6 text pipeline with judge loop and mechanical checks, `book flags`, minimal `book eval`) done 2026-11-01, tested against a fake LLM; the first real model runs are still to do (they need `ANTHROPIC_API_KEY`). Session 3 code (image adapters for Gemini, FLUX.2 and OpenAI, S7 prompt rendering, `book bakeoff` plan/execute/judge/report/pin) is built and tested against fakes, 2026-11-01. The bake-off itself has not run: it needs fixture sheets, provider keys and the owner's budget sign-off. Next: run the bake-off, then session 4 (§10.1).
**Scope:** how one personalized, serialized picture book gets made, from intake to a print-ready PDF.
Printing, fulfillment, the web app, payments and marketing are framed (§1.4, §9, §10.5) but are out of scope for the pipeline build.

## How to read this file

- `§n.m` numbers are stable. Reference them in commits and prompts ("per SPEC §3.8").
- `[D#]` is a decision with its rationale (§2). Reopen one by editing it, never by silently diverging.
- `[OPEN-#]` is a question for the owner (§11). `[VERIFY-#]` is a claim or number to confirm against a live source before relying on it (§12).
- A session building a phase starts at §10 for the acceptance criteria, then reads only the pipeline stages in §3 it touches. `grep -n "\[D\|\[OPEN\|\[VERIFY" SPEC.md` lists every decision and open item.

## 0. Vision

A subscription that mails a child a new hardcover episode of *their own* ongoing adventure every month. The child is the hero, drawn to look like them. A companion character, a persistent world and running threads carry across books. Parents choose which value each episode teaches, and the story shows it through action instead of stating it. The hard part is not generating *a* book. It is generating book 7 so that it feels like the same series, the same kid, the same illustrator, and is still good enough that a parent reads it aloud twice.

---

## 1. Product definition

### 1.1 What a book is

A 32-page, full-colour, square hardcover picture book, 8.5 × 8.5 in trim `[OPEN-2]`. Each book is one **episode** in a **series** that belongs to one child. A **season** is six episodes that complete one big goal.

| Pages | Content |
|---|---|
| 1 | "This book belongs to ___" and half title |
| 2–3 | Title spread: series title, episode number and title, hero + companion |
| 4–5 | Cast or recap spread. Episode 1: "Meet …". Episode 2+: "Last time …" in ≤ 60 words |
| 6–29 | 12 story spreads (the story proper) |
| 30 | "Next time…" teaser: one illustration, two lines |
| 31 | For grown-ups: three talk-about-it questions tied to the episode's value |
| 32 | Colophon: series, episode, style name, generation date |

Cover: front (hero and companion, episode title), spine (series name, episode number), back (one-paragraph blurb). Spine width comes from the printer's calculator `[VERIFY-3]`.

### 1.2 Reader bands

| Band | Age | Words per book | Per spread | Traits |
|---|---|---|---|---|
| A | 2–4 | 150–350 | 1–2 short sentences | refrain, naming, simple cause and effect |
| **B** (Phase 0 default) | 4–6 | 400–750 | 2–4 sentences | rule of three, try-fail-try, value shown in action |
| C | 6–8 | 750–1,300 | 4–7 sentences, light dialogue | subplots, mild mystery, wordplay |

Phase 0 builds band B only. A and C are template variants added once B passes its gates (§10).

> Session 1 note (2026-11-01): sentence-length caps per band and the band A/C body sizes in `craft/band_rules.yaml` are v0 proposals (marked there), not spec numbers; tune them with §6.3.

### 1.3 Personalization levels

| Level | What the parent supplies | What changes |
|---|---|---|
| L0 | name, pronouns, age | always on; text and cast |
| L1 | written appearance (no photos) | appearance card → character sheet (§5.3) |
| L2 | 3–5 photos of the child | appearance card extracted by vision model → sheet (§5.1) |
| L3 | photos or descriptions of family and pets | cameo characters with their own sheets (§5.5) |
| L4 | value per episode, companion choice, optional life-event note, exclusions | plot, lesson pattern, cast, tie-ins (§4.7) |

### 1.4 Cadence

The owner's framing is "every two weeks or monthly". Recommendation `[D12]`: one printed episode per month, with an optional digital mini-episode (four spreads, PDF or in-app) at the two-week mark. Reasons: cost of goods (§9) makes a biweekly hardcover roughly double the price per child, and a six-episode season at monthly cadence is a satisfying half-year arc. `[OPEN-1]`

### 1.5 Values catalog v0

The catalog is data (`craft/values_catalog.yaml`), so adding a value is one entry. Each value carries a story pattern and a shown-not-told test the judge applies (§6).

| Value | Story pattern | Shown-not-told test |
|---|---|---|
| Perseverance | try → fail → change approach → try (three attempts) | the hero changes *method*; nobody says "never give up" |
| Friendship & kindness | rupture → costly kind act → repair | the friend's reaction carries the meaning |
| Courage / trying new things | fear → one small step → surprise | fear is described in the body, not labelled "brave" |
| Honesty | tempting shortcut → confession → trust restored | the confession costs something small and real |
| Sharing & generosity | scarcity → choice → shared joy | the hero gives up something they wanted |
| Patience | waiting → noticing → payoff | the waiting itself reveals something |
| Curiosity | question → investigation → discovery | the hero asks, looks, tests |
| Big feelings | storm → naming → tool → calm | a concrete calming tool a child can copy |
| Teamwork | solo failure → combined strengths | companion's skill and hero's skill are both required |
| Responsibility | job neglected → consequence → making it right | the fix is the hero's own work |

### 1.6 Why this is different

Legacy personalized books (Wonderbly, Hooray Heroes) are templated: fixed stories with name and appearance swaps. The 2026 AI entrants found in research (Bookestry, Little Hero Book, DreamStories.ai, Storique, Kabook, ToonyStory, CreateStory) sell one-off photo-likeness books or credit subscriptions. None found makes an **ongoing series with a persistent world, companion and continuity** the product. The continuity engine (§4) plus value control is the differentiator. Likeness is table stakes.

---

## 2. Decisions

- **[D1] No training or fine-tuning on published children's books in Phases 0–3.** The owner's first instinct was to ingest a corpus and train. Three reasons not to start there: (a) legal exposure, since in-copyright books are not ours to train on and the 2025 author class actions over book training data show how live that risk is, and a model trained on them can reproduce protected text; (b) small capability gain, since frontier models already know picture-book structure, pacing and tropes, and the real gap is *direction and evaluation*; (c) a better flywheel, since every approved book plus the editor's edits is proprietary preference data we own and can fine-tune on later (Phase 4+) if quality plateaus. Instead we write a **Craft Guide** (`craft/craft_guide.md`) that distills structure, page-turn mechanics, refrains, the rule of three and ending patterns, plus structural templates and a judge rubric. Public-domain books (US: published before 1931 `[VERIFY-1]`) may be analyzed for structure. Nothing in copyright is ingested.
- **[D2] Likeness lives in a Character Sheet, not in photos.** Photos are used once: vision model → structured appearance card → parent edits → stylized turnaround sheet → parent picks one → photos deleted by default. Every later image references the sheet. Reasons: sheet-to-illustration consistency is tractable while photo-to-illustration on every spread is not; privacy (§7.3); and provider policy, since research shows image providers filter photorealistic children and may decline prompts that reference a real child's photo `[VERIFY-2]`.
- **[D3] Illustrated, never photorealistic.** Picture books are illustrated anyway. Photoreal children are uncanny, policy-fraught and deepfake-adjacent.
- **[D4] No text inside generated images.** We typeset. Models still botch lettering, and typesetting gives us readable fonts for early readers, control of line breaks, and translations later.
- **[D5] Style locked per series.** A style bible (named attributes, palette, line, lighting) plus 3–5 anchor images passed as style references, with provider and model pinned per series. A model upgrade requires a re-anchor test before any live series moves.
- **[D6] Every episode stands alone and rewards continuity.** A child joining at episode 4 enjoys it. A child who read 1–3 gets callbacks. Mechanisms: recap spread, teaser, continuity ledger (§4).
- **[D7] One wide image per spread.** Roughly 2:1, with the illustration brief reserving a text-safe area on the side the plan names. Fallback is two single-page images if the chosen model cannot hold the aspect ratio.
- **[D8] A human editor approves every book in Phases 0–2.** Automation is earned by a measured intervention rate (§6.5), not assumed.
- **[D9] Provider-agnostic image layer; a bake-off picks the model.** Shortlist and protocol in §8.3. Pinned per series (see D5).
- **[D10] Values are shown through action.** Moral paragraphs are banned and an anti-slop list is enforced mechanically (§6.3). This is the most common failure of AI children's stories and the first thing a parent notices.
- **[D11] Stack: Python 3.12, Pydantic, Typer CLI, file-based artifacts per book, Claude for text and vision, WeasyPrint for PDF.** Matches the owner's existing stack and API key. No web app, database or queue until Phase 3.
- **[D12] Monthly print cadence, optional biweekly digital mini-episode.** See §1.4.
- **[D13] Every series has one non-human companion** chosen at intake from a menu of about eight archetypes (dragon, robot, fox, cloud, owl, …) and named by the child. It supplies humor, a second voice, and an illustration anchor whose consistency does not depend on photos.

---

## 3. Pipeline

### 3.1 Principles

- Every stage is a function from artifacts on disk to artifacts on disk. Stages are idempotent and re-runnable from any point: `book run --episode 3 --from S5 --to S11`.
- Each stage appends to `manifest.json`: stage, status, model, provider, cost in USD, attempts, timestamps.
- Prompts are versioned files in `craft/`, never inline strings. Every model call logs prompt hash and response under `logs/` so a run can be replayed and used in evals (§6.7).
- A failed gate writes a flag, not an exception. `book flags` lists them; the editor fixes with a manual control (edit the card, edit the text, pick a candidate, regenerate one spread) instead of rerunning everything.

> Session 1 note (2026-11-01): "appends" is read as upsert by stage: a re-run replaces that stage's record, increments `attempts` and sums `cost_usd` (`bookgen/manifest.py`). S0's §3.2 gate (schema valid, consent set) is checked before anything is written and raises, since there is no series yet to flag against.

> Session 2 note (2026-11-01): stages follow one contract (`bookgen/stages/base.py`): each declares `CADENCE` and optional `inputs`/`check`/`outputs`, and `run` returns its gate checks. The runner owns the skip test (DONE or FLAGGED, outputs present, and the SHA-256 of every declared input unchanged since the run, so an upstream rerun or an editor's edit makes later stages stale; `--force` reruns per-episode stages but never the once-per-series bible), the input gate before any write (`StageInputError`, exit 2), start/finish, FAILED on an exception, flags from failed checks, and per-stage cost. Every check, passed or failed, is kept in `StageRecord.checks`. A flagged stage does not block later stages; flags block at S12. Rerunning a stage resolves its earlier open flags. `book flags --resolve N` is the editor's clear.

### 3.2 Stage map

| Stage | Name | Runs | Model | Gate |
|---|---|---|---|---|
| S0 | Intake | once per family | none | schema valid, consent flags set |
| S1 | Appearance card | once per person | Claude vision | parent reviews and edits |
| S2 | Character sheet | once per person per style | image model + vision judge | parent picks one of 4–6 |
| S3 | Series bible + style anchors | once per series (episode 1) | Claude | coherence judge, human read |
| S4 | Episode plan | per episode | Claude, structured output | plan judge |
| S5 | Manuscript | per episode | Claude writer + Claude judge | rubric ≥ bar, mechanical checks |
| S6 | Illustration briefs | per episode | Claude | brief lint |
| S7 | Image generation | per spread, 3 candidates | image model | none (S8 judges) |
| S8 | Image QA and pick | per spread | Claude vision | identity + composition ≥ bar, else regen ≤ 3 |
| S9 | Upscale | per chosen image | Real-ESRGAN or provider | sharpness and artifact diff |
| S10 | Layout | per episode | WeasyPrint | text fits, no gutter collisions |
| S11 | Preflight | per episode | code | page count, size, DPI, fonts, safe zones |
| S12 | Editor review | per episode | human | rubric scored, status approved |
| S13 | Ledger update | per approved episode | Claude extraction | diff shown and accepted |
| S14 | Order and ship | per approved episode | print API (Phase 3+) | out of scope here |

### 3.3 Stage details

**S0 Intake.** In: parent form (Phase 0: a hand-written `family/profile.json`). Out: `FamilyProfile` with children, parents, pets, companion choice, value priorities, exclusions, locale, consent flags.

> Session 1 note (2026-11-01): Phase 0 L1 appearance cards are hand-written in the intake JSON (`appearance_cards`); S0 moves each to `characters/<id>/appearance.json` and S1 should skip people who already have one. S0 also writes `series/style.json` (and refuses to change it, D5) and an empty `series/ledger.json`, and creates `characters/` folders for the children, the companion (id = its given name, slugged) and, only with `consent.family_cameos`, parents and pets. It refuses a profile whose hero is outside the Phase 0 band (siblings are cameos `[OPEN-4]`, so their band doesn't gate). Re-runs never overwrite an existing `appearance.json`, which may hold the parent's S1 edits.

**S1 Appearance card.** In: 3–5 photos per person, or a written description for L1. Out: `characters/<id>/appearance.json`. Claude vision with structured output fills the card: hair (colour, texture, length, style), skin tone as an id from a fixed 10-swatch reference palette (never free text), eyes, glasses or assistive devices, distinctive features, height class relative to the companion, and three suggested signature outfits. Gate: the parent reviews and edits the card and picks the signature outfit. This is the manual control that makes the rest of the identity pipeline trustworthy.

**S2 Character sheet.** In: appearance card, style bible, photos as references only where the provider permits `[VERIFY-2]`. Out: 4–6 candidate turnaround sheets (front, three-quarter, side, four expressions, signature outfit) → parent picks → `characters/<id>/sheet.png` plus `sheet_crops/` for reference passing. Vision judge checks each candidate against the card before the parent sees it. The companion gets a sheet from its archetype plus the child's colour and name choices. Cameo characters get sheets the same way.

**S3 Series bible.** Episode 1 only. In: profile, cards, companion, value priorities, parent notes. Out: `series/bible.json`: world (name, 5–8 locations with one-line descriptions), cast (hero, companion, 2–3 recurring side characters, family cameos), tone and humor register, naming conventions, the season (goal, six episode loglines, finale shape), forbidden list from parent exclusions, style id. Also `series/style_anchors/*.png`: 3–5 images of key locations in the chosen style, which become style references for every later image.

> Session 2 note (2026-11-01): S3 writes `bible.json` only; style anchors are images and wait for session 3. Code checks exact names, pronouns, cameo consent and exactly one home location. The Sonnet coherence judge checks the rest. The human read is always raised as the flag `bible_human_read`. Parent exclusions are merged into `forbidden` by code. `CastMember.pronouns` and `Location.is_home` were added. S3 creates `characters/<id>/` for side cast. There is no parent-notes input in Phase 0.

**S4 Episode plan.** In: bible, ledger, this episode's value, life-event note, band. Out: `epNN/plan.json`: title, logline, value and pattern (from the catalog), structure template (§4.4), 12 beats (spread, setting, characters present, action, emotional beat, page-turn hook, text-safe side), the beat where the value lands (9–11), recap text, teaser text, three grown-up questions. Gate: the plan judge checks 12 beats, pattern present, continuity against the ledger, no setting repeated from the previous episode, scare level within band, and that the story reads without the recap (§4.5).

> Session 2 note (2026-11-01): code checks the countable rules: pattern copied from the catalog, value at 9–11, value not repeated this season, recap ≤ 60, ledger summary ≤ 120, cast and settings from the bible, template rotation. "No setting repeated" exempts the hero's home (`is_home`). The judge reads the plan with the recap removed (§4.5). With no `--value`, the first parent priority not yet covered is used. There is no life-event input in Phase 0.

**S5 Manuscript.** In: plan, Craft Guide, band rules, ledger (names, voices). Out: `epNN/manuscript.json`: text per spread plus read-aloud notes (emphasis, sound words). Loop: writer drafts → judge critiques against the rubric in a separate call → writer revises → at most two rounds → mechanical checks (word counts per band, banned phrases, readability, exact name spellings, pronouns). Gate: judge ≥ bar and mechanical checks pass, else flag.

> Session 2 note (2026-11-01): "at most two rounds" is read as draft → critique, then (revise → critique) at most twice, so the final text always has a score to gate on. The loop stops early when the rubric bar and every mechanical check pass. Failed mechanical checks go into each revise with the judge's notes. The judge sees only the finished text. All rounds are kept in `epNN/critique.json`. `Manuscript.word_count` is derived, and spreads must be 1..12 in order.

**S6 Illustration briefs.** In: manuscript, plan, bible, sheets, style bible. Out: `epNN/briefs.json`, one per spread plus cover, recap and teaser: scene in concrete nouns, characters present with pose and expression, shot (wide, medium, close), text-safe area, palette and time of day, continuity props (the lantern from episode 2), negatives. Gate: lint, every present character has a sheet, text-safe side matches the plan.

> Session 2 note (2026-11-01): until sheets exist (session 3), "has a sheet" means `characters/<id>/sheet.png` or at least the folder. `IllustrationBrief.text_side` was added so "matches the plan" is an equality test. Lint also checks that all 15 slots appear exactly once, that each story spread's characters match the plan, that no scene asks for readable text, and that the negatives rule text out (D4).

**S7 Image generation.** In: brief, sheet crops for every present character, 2–3 style anchors. Out: `epNN/images/sNN_cK.png`, three candidates per spread, seed and prompt hash logged. Runs through the `ImageProvider` adapter (§8.3).

**S8 Image QA and pick.** In: candidates, sheets, brief. Out: `epNN/qa_images.json`, chosen `sNN.png`. Vision judge scores each candidate: identity match per character (0–3), correct character count, expression matches the beat, no letters or text, anatomy (hands, eyes, limbs), text-safe area actually quiet, nothing scary or inappropriate for the band, no face across the gutter line. Best candidate wins if ≥ bar. Otherwise regenerate with the judge's notes folded into the prompt, up to three rounds, then flag for the editor.

**S9 Upscale.** In: chosen images. Out: `epNN/print/sNN.png` at trim plus bleed. For 8.5 × 8.5 in with 0.125 in bleed per side a spread is 17.25 × 8.75 in, 5175 × 2625 px at 300 DPI `[VERIFY-3]`. Tool: Real-ESRGAN locally or the provider's upscaler. Gate: sharpness check and a vision diff against the source to catch invented detail.

**S10 Layout.** In: manuscript, print images, cover image, templates. Out: `book_print.pdf` (interior with bleed), `cover_print.pdf` (wraparound with spine), `book_preview.pdf` (screen, no bleed, spreads as single pages). Jinja2 HTML/CSS → WeasyPrint with `@page` size and bleed. Text rules: band B body 20–24 pt, body font Andika (SIL Open Font License, designed for beginning readers), a display face for titles, text inside the safe zone and never across the gutter, auto-fit shrinks at most 10% before flagging overflow.

**S11 Preflight.** Out: `preflight.json`. Checks: 32 pages, page size with bleed, effective image DPI ≥ 300, fonts embedded, colour profile per printer spec (sRGB if the printer converts, CMYK otherwise `[VERIFY-3]`), text in safe zone, no empty spreads, spine width matches the printer's calculator. Any failure blocks S12.

**S12 Editor review.** The human reads the preview, scores the rubric (§6.1), edits text directly in `manuscript.json` where needed, and reruns from S10 (text) or S7 for a single spread (`--spread 7`). Out: `review.md`, status `approved`.

**S13 Ledger update.** In: approved manuscript and plan. Out: updated `series/ledger.json` (§4.3). Claude extracts new facts, threads, gags and the next hook; the diff is shown before it is accepted.

**S14 Order and ship.** Phase 3+: print API order with the two PDFs. Phase 0: manual upload to a print-on-demand portal to validate the physical result.

### 3.4 Artifact layout

```
series/<series_id>/
  family/profile.json
  characters/<person_id>/{appearance.json, sheet.png, sheet_crops/, candidates/}
  series/{bible.json, ledger.json, style.json, style_anchors/}
  ep01/
    plan.json  manuscript.json  briefs.json
    images/  qa_images.json  print/
    book_print.pdf  cover_print.pdf  book_preview.pdf
    preflight.json  review.md  manifest.json  metrics.json  flags.json
    logs/
```

> Session 1 note (2026-11-01): the nested `series/<series_id>/series/` folder is kept as written. S0's manifest record goes in `ep01/manifest.json`, since §8.5's Manifest covers S0..S13 per episode. Flags live in `Manifest.flags`; `flags.json` is left for `book flags` to export.

---

## 4. Serialization engine

### 4.1 Objects

**Series** is bound to one child and lives for years. **Season** is six episodes that complete one goal. **Episode** is one book. **Ledger** is the continuity memory, updated only from approved manuscripts.

### 4.2 Season arc

The season goal has six parts (six pieces of the Moon Map, six friends to invite to the Sky Festival). Episodes 1–5 each gain one part and teach one value. Episode 6 is the finale: the hero uses all five lessons, and the plan must include a payoff spread with callbacks to each. A new season starts a new goal in the same world. The world may expand and the band may step up at a season boundary as the child ages (§4.6).

### 4.3 Ledger schema

```
facts[]            established world rules and names, each with the episode that set it
cast_state[]       per character: appearance ref, voice tics, relationship to hero, last seen
locations_visited[]
objects[]          named props and where they are now
running_gags[]     with usage count, so the planner reuses sparingly
lessons_covered[]  {episode, value}
open_threads[]     unresolved hooks the planner may pick up
last_summary       ≤ 120 words, feeds the recap spread
next_hook          one line, feeds the teaser and the next plan
child_age_at_last  drives band and sheet refresh
```

> Session 2 note (2026-11-01): the ≤ 120 limit is a QA flag (`bookgen/qa/limits.py`), not a model validator, so an over-long ledger can still be loaded and flagged.

### 4.4 Continuity rules the plan judge enforces

- Names and appearance are immutable. Companion voice tics are stable.
- Objects persist where the ledger left them.
- No value repeats within a season. No setting repeats in consecutive episodes.
- The structure template rotates across `craft/structure_templates.yaml`: quest, mystery, mishap-and-fix, big day, visitor, journey. The same template never runs twice in a row.
- Scare level and vocabulary stay within the band.

### 4.5 Standalone rule

The recap spread is ≤ 60 words. The plan judge reads the plan with the recap removed and must still follow it. Callbacks are rewards, never prerequisites.

> Session 2 note (2026-11-01): the recap limit is likewise a flag raised in S4, not a validator.

### 4.6 Aging up

The child's age is updated at every episode. Band changes only at a season boundary. A new sheet is generated yearly, or on request, using the old sheet as a reference so the character reads as the same child, older.

### 4.7 Parent inputs per episode

All optional: the value for this episode (otherwise the engine rotates through the family's priority list), a life-event note of ≤ 200 characters ("started swimming lessons" becomes a tie-in), exclusions. The default path needs zero parent input. The subscription must run on autopilot.

---

## 5. Personalization and identity

### 5.1 Photo path (L2)

```
photos ──S1──▶ appearance card ──parent edits──▶ S2 candidate sheets ──parent picks──▶ sheet.png
                                                                                        │
photos deleted by default ◀─────────────────────────────────────────────────────────────┘
```

The sheet is the identity from then on. Photos never enter a per-spread prompt.

### 5.2 Appearance card

Structured fields only, so the card is editable, diffable and respectful: hair colour, texture, length and style; skin tone as a palette id from a fixed 10-swatch reference; eye colour; glasses; assistive devices (hearing aids, mobility aids) and distinctive features, because representation is the whole point of a book about *this* child; signature outfit chosen by the parent from three suggestions; height class relative to the companion. No free-text physical description reaches an image prompt without passing through these fields.

### 5.3 No-photo path (L1)

The parent fills the card by hand. S2 generates six candidates and the parent picks. In an illustrated style this already lands close enough that most children recognize themselves. This is also the Phase 0 path (fixture family, no real photos) and the fallback if a provider refuses photo references `[VERIFY-2]`.

### 5.4 Reference passing at generation time

Each S7 call receives sheet crops (face front, three-quarter, full body) for every character present plus two or three style anchors. How many references a provider accepts, and how well it holds several characters at once, is a bake-off criterion (§8.3). Research as of 2026-11-01 puts Gemini image models at up to 14 references and FLUX.2 at 8–10 via API, but the figures were inconsistent between sources `[VERIFY-4]`.

> Session 3 note (2026-11-01): `stages/s07_generate.select_references` picks one image per present character first (the front crop, else the whole sheet), then up to three style anchors, then further crops, capped at the provider's `max_references`. `render_prompt` (template `craft/prompts/image.md`) names each character with their role, and takes looks from the appearance card where there is one, otherwise from the bible description. It always appends the no-text negative (D4) and not-photoreal (D3).

### 5.5 Family and pet cameos (L3)

Each person or pet gets a card and sheet. Cameos appear in at most three spreads per episode by default. Any adult can opt out of their own likeness and be written in by name only.

### 5.6 Photo policy

- 3–5 photos per person. The uploader attests they are the parent or guardian of every child pictured. Other children must be cropped out or the upload is rejected.
- Retention default: delete after sheet approval. Explicit opt-in to retain for the yearly re-sheet (§4.6).
- Encrypted at rest. Sent only to providers whose API terms exclude training on inputs `[VERIFY-5]`. An audit log records what was sent where.

---

## 6. Quality bar and evaluation

### 6.1 Rubric (0–3 per item)

| # | Item | 3 looks like |
|---|---|---|
| 1 | Page-turn hooks | every spread ends with a reason to turn |
| 2 | Specificity | concrete nouns and sensory detail, no "magical forest" without a particular tree |
| 3 | Read-aloud rhythm | sentences land when spoken; sound words and refrain used on purpose |
| 4 | Hero agency | the child solves it; not an adult, not magic, not the companion alone |
| 5 | Value shown, not told | passes the catalog's shown-not-told test; no moral paragraph |
| 6 | Delight | at least two genuinely funny or surprising beats |
| 7 | Ending lands | the resolution echoes the setup; the final spread is quiet |
| 8 | Band fit | vocabulary, sentence length and scare level within band |
| 9 | Continuity | no contradiction with the ledger; callbacks are correct |
| 10 | Illustration identity | every character matches its sheet across all spreads |
| 11 | Illustration composition | text-safe area holds, nothing important in the gutter |

Pass rule for Phase 0: no item scores 0, mean ≥ 2.3. Tune after ten books.

### 6.2 Judge setup

Generator and evaluator are separated. The critique call uses a different model (Sonnet 5.5 against the Opus 5.5 writer), never sees the writer's reasoning, and takes its rubric from `craft/judge_rubric.yaml`. It returns per-item scores and specific fix notes the writer can act on. In Phases 0–2 the human editor scores the same rubric; agreement between judge and editor is tracked, with a Phase 3 target of 80% of items within one point.

### 6.3 Mechanical checks (code, not models)

- Banned phrases from `craft/banned_phrases.txt`. Seed list: "little did they know", "a world of", "heart filled with", "that's when … realized", "learned that", "the importance of", "magical adventure", "filled with wonder", "beamed with pride", "twinkled", "and so".
- Adjective density ≤ 1 per 8 words. Exclamation marks ≤ 1 per spread. Sentence length caps per band.
- Names spelled exactly as in the profile. Pronouns consistent. Parent terms as the family set them.

> Session 2 note (2026-11-01): the checks live in `bookgen/qa/mechanical.py`. Adjective density uses the lexicon in `craft/adjectives.txt` (no POS tagger). `...` in a banned phrase matches at most eight words, within one sentence. Parent terms are checked against a fixed list of generic words. A pronoun check passes only when someone present in the beat uses that pronoun. The seed phrase "and so" also catches "and so did"; the editor overrides those.

### 6.4 Readability

Per band: Flesch-Kincaid grade range (band B ≤ 2.5), mean sentence length, and the share of words on a band-appropriate frequency list `[VERIFY-6]`. Proper nouns are excluded from the statistics.

> Session 2 note (2026-11-01): Flesch-Kincaid uses a vowel-group syllable estimate and excludes cast and family names. `max_fk_grade` per band was added to `band_rules.yaml` (B = 2.5 from here; A and C are proposals). The frequency-list share isn't measured yet `[VERIFY-6]`.

### 6.5 Metrics per book

Written to `metrics.json` and rolled up across books: judge mean, editor mean, regenerations per spread, flagged spreads, words changed by the editor, cost by stage, wall time by stage, first-pass rate (books that needed no manual fix). The intervention rate decides when a stage may run unattended (§10).

### 6.6 Illustration consistency score

The vision judge compares every chosen spread to the sheet and scores identity 0–3 per character. A book passes at minimum ≥ 2 and mean ≥ 2.5. From Phase 1 the same check runs on random spread pairs across episodes of a series.

### 6.7 Eval set

`evals/core/`: ten fixture families × three values. Runs on every change to a craft file, prompt or model and reports deltas in judge mean, mechanical failures and cost. No craft change ships without the eval.

> Session 2 note (2026-11-01): the minimal runner (`book eval --suite evals/core`, `bookgen/evals.py`) runs S0 and S3–S5 per family × value and writes `evals/core/results/<stamp>.json` (committed). It reports judge mean, mechanical failures, plan flags, cost and changed prompt versions against the previous results file. Phase 0 has one family × three values; generated artifacts go to the gitignored `evals/core/runs/`.

---

## 7. Safety, privacy and legal

### 7.1 Content rules

Hard: no violence, weapons, death or abandonment; peril is mild and resolved within the spread for band B; no real-world danger modelled approvingly; an adult is present wherever a real child would need one; the companion never undermines parents; no body or food shaming; no romance. Soft: the family's exclusions list. A classifier pass runs on text at S5 and on images at S8.

### 7.2 Likeness and consent

Only enrolled people appear. Requests to include a friend or classmate are declined unless that child's guardian enrolls them. Requests for trademarked characters are declined with an in-world alternative (a snow queen, not Elsa).

### 7.3 Children's data

Photos of minors are treated as sensitive data: minimization, deletion by default, encryption, provider terms checked (§5.6). The service is sold to parents but handles children's data, so children's privacy law applies (COPPA in the US, GDPR and the UK regime where relevant). Counsel reviews the privacy policy and consent flow before any public launch `[OPEN-9]`. Phases 0–2 use only the owner's data and that of consenting friends.

### 7.4 Intellectual property

Style prompts describe attributes, never living artists' names. Fonts are under the SIL Open Font License or commercially licensed. US Copyright Office guidance treats purely AI-generated material as unprotectable, so our protectable layer is the human-authored Craft Guide, bibles, edits and layout `[VERIFY-7]`. This affects enforcement, not viability.

### 7.5 Provider policy risk

Research found that image providers filter photorealistic depictions of children and may decline prompts involving children at all. The stylized sheet (D2, D3) reduces the risk but does not remove it. The bake-off must run a "child hero in 20 scenes" policy test per provider and record refusals. The fallback is open weights (FLUX.2 dev or similar) self-hosted with our own safety layer `[VERIFY-2]`.

---

## 8. Technical design

### 8.1 Stack

Python 3.12, Pydantic v2 models, Typer CLI, Jinja2 + WeasyPrint for PDF, Pillow, Real-ESRGAN (local) or a provider upscaler, pytest. Claude via the `anthropic` SDK for all text and vision work. Image generation behind an `ImageProvider` protocol. Phase 0 storage is the filesystem layout in §3.4; SQLite or Postgres arrives with the web app in Phase 3.

> Session 1 note (2026-11-01): `requires-python >=3.12` and ruff targets 3.12, but this Mac has no 3.12, so the local venv runs 3.13. It lives in `venv/`, not `.venv/`: dot-folders on this Desktop get the macOS hidden flag, and Python 3.13 skips hidden `.pth` files, which breaks the editable install. Craft enums are built from `craft/` at import (`bookgen/craft.py`).

### 8.2 Repo layout

```
Book Company/
  SPEC.md
  bookgen/                 # package name is a placeholder [OPEN-8]
    models.py              # Pydantic types (§8.5)
    cli.py                 # Typer commands (§8.7)
    stages/                # one module per stage, s01_appearance.py … s13_ledger.py
    providers/             # llm.py (Claude), images/{base.py, gemini.py, flux.py, openai.py, ideogram.py}
    layout/                # templates/*.html, styles/*.css, fonts/
    qa/                    # mechanical checks, readability, judge wrappers
  craft/                   # versioned prompt assets (§8.8)
  evals/core/              # fixture families and the eval runner (§6.7)
  examples/family_demo.json
  series/                  # generated artifacts, gitignored
  docs/bakeoff-<date>.md
  tests/
```

### 8.3 Image providers and the bake-off

Candidates as of 2026-11-01. Versions, reference limits and prices move monthly, so re-check before the bake-off `[VERIFY-4]`.

| Provider | Why it is on the list | Watch for |
|---|---|---|
| Google Gemini image models ("Nano Banana", "Nano Banana Pro") | strongest multi-reference consistency in 2026 reviews, up to 14 references, up to 4K output | policy on children, per-image cost at high resolution |
| Black Forest Labs FLUX.2 (Pro via API; dev open weights) | won a May 2026 multi-reference consistency test; open weights allow self-hosting and a per-family LoRA later | reference count via API, self-host cost |
| OpenAI gpt-image-2 (edits endpoint with reference files) | strong prompt adherence and composition | weaker character consistency in the same tests |
| Ideogram 3 character reference | locks a face from a single reference | $0.05–0.11 per image, fewer references |
| Higgsfield | owner mentioned it | video-first platform, not a fit for print stills; parked |

Bake-off protocol (`book bakeoff`): three fixture character sheets × twenty scenes (varied pose, distance, lighting, two-character shots with the companion) × two aspect ratios, three candidates each. Score with the vision judge and a human on identity hold, style hold, brief adherence, no-text, refusals, latency and cost. Write `docs/bakeoff-<date>.md` and pin the winner per series. Budget `[OPEN-11]`.

> Session 3 note (2026-11-01): the adapters are `bookgen/providers/images/{gemini,flux,openai}.py` over REST, with request shapes read from the providers' docs on 2026-11-01. Default models (env-overridable): `gemini-3-pro-image` (Nano Banana Pro, via the Interactions API), `flux-2-pro`, and `gpt-image-2.5-sunburst` (the gpt-image-2 named above has been superseded). Keys come from `GEMINI_API_KEY`, `BFL_API_KEY` and `OPENAI_API_KEY`. The per-image prices in each adapter's `capabilities()` are list-price estimates `[VERIFY-4]`. Three behaviours are still `[VERIFY]` on the first live call: whether FLUX accepts base64 reference images (its docs show URLs), how Gemini reports a safety block (treated as a refusal when a 200 carries no image), and OpenAI's reference cap. `book bakeoff` runs in steps: a dry-run plan and estimate, then `--execute` (resumable, with a hard cap from `BOOKGEN_MAX_IMAGE_COST_USD`, default $150), then `--judge` (the Sonnet vision judge), then `--report` (writes `docs/bakeoff-<date>.md`), then `--pin PROVIDER --series ID --out RUN` (writes the model that run actually used into the series `style.json`). A job that errored is retried on resume. Any candidates it finished are kept and counted toward the cap. Judging bills as Claude calls under `BOOKGEN_MAX_COST_USD`, separately from the image cap. Images sent to the judge are downscaled to 1568 px. Scenes live in `examples/bakeoff/scenes.yaml`: 20 scenes × 2 aspects (2:1 spread, 1:1 page) × 3 candidates. Sheets go in `examples/sheets/<id>/`, which is not committed. A full three-provider run comes to about $47 at list price.

### 8.4 LLM roles

| Role | Model | Notes |
|---|---|---|
| plan, draft, revise, briefs, bible | `claude-opus-5-5` | adaptive thinking on by default; structured outputs for every JSON artifact |
| judge, critique, extraction, image QA | `claude-sonnet-5-5` | separate model from the writer (§6.2); vision for S1, S8, S9 |
| mechanical checks | code | banned phrases, counts, readability |

Published rates at the time of writing: Opus 5.5 $4 in / $20 out per million tokens, Sonnet 5.5 $2 / $10, Haiku 5.5 $0.10 / $0.50. Keep the Craft Guide and bible first in every prompt so prompt caching covers them. Use the server-side refusal fallback the SDK offers so a safety-classifier refusal on an innocent children's prompt retries rather than fails.

> Session 2 note (2026-11-01): the client is `bookgen/providers/llm.py`. It calls `beta.messages.parse` with a structured output per artifact, `fallbacks="default"` (beta `server-side-fallback-2026-07-01`), and the Craft Guide and bible as cached system blocks ahead of the role prompt (`craft/prompts/`, versioned). Effort is `medium` for the writer, `high` for draft and revise, and `high` for the judge. Invalid output gets one corrective retry. Each call is logged to `epNN/logs/`. A hard per-run cap comes from `BOOKGEN_MAX_COST_USD` (default $5), checked against each call's worst case before it is sent.

### 8.5 Data model (Pydantic)

```
FamilyProfile     id, parents[], children[], pets[], companion_choice, value_priorities[], exclusions[], locale, consent
ChildProfile      id, name, pronouns, birth_month, band
AppearanceCard    person_id, hair{colour,texture,length,style}, skin_tone_id, eyes, glasses, assistive_devices[], features[], signature_outfit, height_class
CharacterSheet    person_id, style_id, paths{front,three_quarter,side,expressions[]}, provider, model, seed, approved_at
StyleBible        id, name, attributes[], palette[], line, lighting, anchor_images[], provider, model, pinned_at
SeriesBible       series_id, world{name,locations[]}, cast[], tone, naming, season{goal,loglines[6]}, forbidden[], style_id
Ledger            see §4.3
EpisodePlan       episode, title, logline, value, pattern, template, beats[12]{spread,setting,characters[],action,emotion,hook,text_side}, value_lands_at, recap, teaser, grownup_questions[3]
Manuscript        episode, spreads[]{spread,text,read_aloud_notes}, word_count, stats
IllustrationBrief spread, scene, characters[]{id,pose,expression}, shot, text_safe_area, palette_notes, continuity_props[], negatives[]
ImageCandidate    spread, k, path, provider, model, seed, prompt_hash, qa: QAResult
QAResult          identity{char_id: 0–3}, count_ok, expression_ok, no_text, anatomy_ok, text_area_quiet, safe, gutter_ok, notes
Review            episode, scores{item: 0–3}, edits[], approved_by, approved_at
Manifest          episode, stages{S0..S13: {status,model,provider,cost_usd,attempts,started,finished}}, flags[]
```

> Session 1 note (2026-11-01): small additions in `bookgen/models.py`: `FamilyProfile.appearance_cards` (L1 only, not kept in profile.json), `AppearanceCard.outfit_suggestions` (S1's three), `skin_tone_id` as an int 1–10, `IllustrationBrief.spread` may be `cover`/`recap`/`teaser`, `Flag.resolved`, `Season.finale` (from S3). `CompanionChoice` is {archetype, name, colour} per S2. `ConsentFlags` is a v0 shape for counsel to review `[OPEN-9]`.

### 8.6 ImageProvider protocol

```
generate(prompt, references: list[Image], aspect: str, n: int, seed: int | None) -> list[ImageResult]
edit(image, prompt, references) -> ImageResult        # for targeted spread fixes
upscale(image, factor) -> Image                       # optional per provider
capabilities() -> {max_references, aspects, max_px, supports_edit}
```

Adapters never see craft text. The brief-to-prompt rendering lives in `stages/s07_generate.py` so a provider swap is one file.

> Session 1 note (2026-11-01): images cross the protocol as file paths (artifacts live on disk, §3.1), and results carry `cost_usd` and `refused`.

> Session 3 note (2026-11-01): `generate` and `edit` take an `out` path prefix, and candidate k is written to `<out>_c<k>.png`. `ImageResult` gains `refusal_reason` and `latency_s`, and `path` is `None` when the image was refused. `ProviderCapabilities` gains `usd_per_image`. A refusal is a result, never an exception. Exceeding `max_references` raises rather than silently dropping references.

### 8.7 CLI surface

```
book init-series --family examples/family_demo.json --style gouache-warm --companion dragon
book sheet      --series demo --character maya                  # S1–S2
book plan       --series demo --episode 1 --value perseverance  # S3 on first run, then S4
book write      --series demo --episode 1                       # S5–S6
book illustrate --series demo --episode 1 [--spread 7]          # S7–S9
book layout     --series demo --episode 1                       # S10–S11
book review     --series demo --episode 1                       # opens preview, records rubric scores
book approve    --series demo --episode 1                       # S12–S13
book run        --series demo --episode 1 --from S5 --to S11
book flags      --series demo --episode 1
book bakeoff    --providers gemini,flux,openai --sheets examples/sheets/
book eval       --suite evals/core
```

> Session 1 note (2026-11-01): `init-series` also takes an optional `--series` (defaults to the family id). `run --from S0` is refused, since S0 needs intake inputs (session 2: now via S0's input gate, exit 2). `--character` and `--value` reach stages as `StageContext.character` / `.value`. Unbuilt stages print `not implemented (SPEC §3.3 S#)` and exit 1.

### 8.8 Craft assets

All prompts are files, versioned in git, so changes are reviewable and evaluable:
`craft/craft_guide.md` (structure, page turns, refrains, endings), `craft/values_catalog.yaml` (§1.5), `craft/structure_templates.yaml` (§4.4), `craft/band_rules.yaml` (§1.2), `craft/banned_phrases.txt` (§6.3), `craft/judge_rubric.yaml` (§6.1), `craft/style_bibles/*.yaml` (3–5 launch styles `[OPEN-12]`), `craft/companions.yaml` (D13 archetypes).

---

## 9. Cost per book

Estimates for planning only. Every line is `[VERIFY-8]`.

| Item | Estimate (USD) | Basis |
|---|---|---|
| LLM: plan, draft, two critique rounds, briefs, ledger | 1.50–3.00 | ~90k Opus input + 20k output, ~300k Sonnet input incl. vision QA on ~55 images |
| Images: 15 finals × 3 candidates + ~20% regens ≈ 55 generations | 3–10 | $0.04–0.20 per image depending on provider and resolution |
| Upscale | 0–1 | free locally, cents via API |
| Print: 32-page 8.5 × 8.5 hardcover, print on demand | 12–22 | get quotes: Lulu, RPI (Blurb's engine, self-service API), Peecho, Gelato. RPI notes hardcovers add 0.25 in to final dimensions |
| Shipping, US domestic | 5–10 | |
| **Total cost of goods** | **≈ 22–46** | |

One-time per series: character sheets (~20 generations per person), style anchors, bible. Competitors price single AI likeness books at roughly $30–60 and digital-only subscriptions at $6–20 per month, which is why D12 favours monthly print. The bake-off itself is a few hundred images, well under $150 at list prices.

---

## 10. Phased plan and acceptance criteria

Each phase ends with a short write-up in `docs/` and the eval set re-run. Later phases are sketched only.

### 10.1 Phase 0: one book you would hand to a child

Fixture family (fictional, no photos, L1 path), band B, one value, style pinned after a small bake-off. Run S3–S11 end to end from the CLI, review in S12, order one physical copy by hand.

Done when:
- `book run --episode 1 --from S3 --to S11` produces `book_print.pdf`, `cover_print.pdf`, `book_preview.pdf` and a passing `preflight.json` without manual intervention.
- Editor rubric mean ≥ 2.3 with no zeros. At most three manual spread regenerations.
- Illustration identity minimum ≥ 2 across the 15 images.
- `metrics.json` records cost and wall time per stage; total generation cost ≤ $15.
- The printed copy arrives and the owner confirms the physical quality is acceptable (colour, text size, gutter).

Suggested session breakdown, one chunk per session so progress is visible:
1. Scaffold the package, Pydantic models, manifest, CLI skeleton, `craft/` v0 (guide, catalog, banned phrases, rubric, band rules), fixture family. No model calls yet.
2. S3–S6 text pipeline on the fixture, judge loop, mechanical checks, minimal eval runner.
3. Image adapters, `book bakeoff`, run it, pin a provider and style. Write `docs/bakeoff-<date>.md`.
4. S7–S9 generation and QA, then S10–S11 layout and preflight. First PDF. Order a copy.
5. S12 review loop, S13 ledger, metrics, flags. Phase 0 write-up.

### 10.2 Phase 1: three episodes of one series

Episodes 2 and 3 for the Phase 0 series with the ledger live. Done when: no contradictions found by a continuity audit prompt over the three manuscripts; cross-episode identity check (§6.6) passes; recap and teaser read correctly in sequence; a reader given episode 3 alone follows it.

### 10.3 Phase 2: real faces

Three consenting families from the owner's circle, L2 path with the full consent and deletion flow. Done when: parents rate likeness ≥ 4 of 5 on the chosen sheet; provider policy behaviour on real-photo references is documented per provider `[VERIFY-2]`; photos are verifiably deleted after approval.

### 10.4 Phase 3: repeatable

Ten families × two episodes. Done when: ≤ 20% of books need any manual fix; judge–editor agreement ≥ 80% (§6.2); cost and wall time per book within the §9 band; the stages that passed unattended across all 20 books are listed as automation-ready.

### 10.5 Later, out of scope for this spec

Web intake and sheet-approval UI, payments and subscription scheduling, print API integration and fulfillment (S14), digital reader for the mini-episode, marketing and ads, fine-tuning on our own approved corpus (D1), bands A and C, additional languages.

---

## 11. Open questions for the owner

- `[OPEN-1]` Cadence: monthly print plus biweekly digital mini-episode (recommended), or biweekly print?
- `[OPEN-2]` Format: 8.5 × 8.5 in hardcover (recommended), 8 × 10 in, or a softcover option?
- `[OPEN-3]` Launch band: B (4–6) only, as assumed?
- `[OPEN-4]` Siblings: one series per child with siblings as cameos (recommended), or a shared duo series?
- `[OPEN-5]` Languages: English only through Phase 3?
- `[OPEN-6]` May parents edit the text before print? Recommended yes, light edits followed by a re-judge.
- `[OPEN-7]` Is a digital companion deliverable (PDF or app) in scope for Phase 3?
- `[OPEN-8]` Company, product and package names.
- `[OPEN-9]` Launch geography, and when to engage counsel on children's data (§7.3).
- `[OPEN-10]` Who is the Phase 0–2 human editor? Assumed to be the owner.
- `[OPEN-11]` Bake-off API budget. Assumed ≤ $150.
- `[OPEN-12]` The three to five launch illustration styles.

> Session 1 note (2026-11-01): the recommended default was taken for every OPEN item. The package is `bookgen` (OPEN-8), and the one launch style is `gouache-warm` (OPEN-12).

## 12. Verify before relying on it

- `[VERIFY-1]` US public-domain cutoff year for structural analysis (believed: works published before 1931).
- `[VERIFY-2]` Each image provider's behaviour on child subjects and real-photo references. Test it, do not just read the policy.
- `[VERIFY-3]` Target printer's specs: bleed, DPI, PDF flavour, colour profile, spine calculator, hardcover dimension change.
- `[VERIFY-4]` Current image model versions, reference limits and per-image prices.
- `[VERIFY-5]` Provider data-use terms (no training on API inputs) for every provider that receives photos.
- `[VERIFY-6]` Which word-frequency list to use per band for §6.4.
- `[VERIFY-7]` Current US Copyright Office guidance on AI-generated works.
- `[VERIFY-8]` Every number in §9, by quote.

### Research notes (2026-11-01)

Character consistency: 2026 reviews rank Gemini image models and FLUX.2 highest for multi-reference work, with gpt-image weaker on consistency and Ideogram strong on single-photo face lock.
[magichour.ai](https://magichour.ai/blog/best-ai-image-generators-for-character-consistency), [techstackups.com (May 2026 comparison)](https://techstackups.com/comparisons/gemini-vs-openai-vs-flux-vs-runway-character-consistency-may-2026/), [fast.io](https://fast.io/resources/best-ai-character-generators-2026/).
Provider policy on children: Google's Vertex AI person-generation setting can allow minors but filters photorealistic children; smaller platforms allow fictional children and warn of cautious refusals. No provider statement covering real-child photo references was found.
[Google Cloud Vertex AI safety settings](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/configure-responsible-ai-safety-settings), [Blaze.ai guidelines](https://help.blaze.ai/en/articles/14433618-image-generation-guidelines-restrictions).
Print on demand: RPI Print offers a self-service API with no setup fee, US drop-ship, hardcover adds 0.25 in; Peecho has a print API; IngramSpark changed print costs in February 2026.
[RPI self-service API](https://beta.rpiprint.com/products-services/print-apis/self-service), [Peecho case study](https://peecho.com/case-studies/bookbildr), [IngramSpark price change](https://help.ingramspark.com/hc/en-us/articles/41657495062029-Changes-in-Print-Cost-Market-Access-Fee-and-More).
Competitors: Bookestry, Little Hero Book (26-page hardcovers, April 2026), DreamStories.ai, Storique ($59 one-time), ToonyStory ($19.99/month family plan), Kabook, CreateStory ($5.99/month).
[NBC Palm Springs on Bookestry](https://www.nbcpalmsprings.com/talking-with-thalia/2026/09/08/talking-with-thalia-turning-family-memories-into-personalized-storybooks), [Little Hero Book](https://peerpush.com/p/little-hero-book), [Storique](https://peerpush.com/p/storiqueai-ai-powered-childrens-book), [ToonyStory](https://apps.apple.com/app/id6761269037), [CreateStory](https://www.stork.ai/en/createstory-ai).

## Glossary

**Series** one child's ongoing adventure. **Season** six episodes, one goal. **Episode** one printed book. **Spread** two facing pages, one illustration. **Companion** the series' non-human sidekick (D13). **Appearance card** structured description of a person (§5.2). **Character sheet** the approved turnaround illustration that defines a character (D2). **Style bible** the locked look of a series (D5). **Series bible** world, cast and season plan (S3). **Ledger** continuity memory (§4.3). **Craft Guide** our written picture-book craft knowledge (D1). **Band** reader age group (§1.2). **Gate** a check a stage must pass before the next runs.
