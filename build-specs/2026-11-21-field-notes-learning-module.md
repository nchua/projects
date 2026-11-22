---
title: "Field Notes learning module"
status: draft
created: 2026-11-21
owner: Nick
target_repo: "nchua/field-notes"
---

# Field Notes learning module

## Summary

Build a new single-user web app, `nchua/field-notes`, that turns Field Notes digests into a durable, browsable memory. Digests land as structured items (a development, a quote, a link, a paper) with provenance. Items are grouped under resolved entities — people, companies, topics, themes, technologies, and claims — and become cited recall cards on a spaced-repetition queue Nick can finish on his phone in a few minutes.

## Goal

Nick stays current, then keeps what he learned. After each Friday digest he can open the app, see what was new, browse everything a person said about a company, and review a short queue. The app remembers what he has seen, what he has reviewed, and how well he recalled it. Weeks later an entity page shows what arrived since he last caught up.

**Success criteria:**

- [ ] Pasting a real Field Notes markdown digest, or POSTing the JSON contract below, persists the digest, its items, and links back to the source text.
- [ ] The same person or company spelled the same way after normalization resolves to one entity, and Nick can merge two entities by hand when the strings differ.
- [ ] He can open a person, a company, and the cross-link of the two, on a phone, and see the underlying items with their links.
- [ ] He can run a capped review session of cited recall cards. Ratings change the next due time. Reloading the next day shows the new schedule.
- [ ] An item the model invented (excerpt not present in the submitted text) is never stored.

## Background and user problem

Field Notes is one of Nick's Grok Bot assistants. It keeps him current on topics he cares about: what happened, and what notable people said about it. It sends a short weekly digest, Fridays around 9am America/Los_Angeles, drawn from public X posts, web news, arXiv, blogs, and podcasts. Every item is linked. Quotes are attributed to people, with links. It tracks a list of topics and people.

Its output today is a chat message in markdown. There is no Field Notes API, no database, and no card system. This spec must not assume one. The app has to accept digests as they exist now (markdown pasted in, or a JSON document of the same shape) and also accept a later push from the bot (webhook, then email) without a schema change.

Two related repos exist. Read them for reuse. Leave their code alone.

**Holocron** (`https://github.com/nchua/holocron`, also checked out in this monorepo at `holocron/`) is a Python/FastAPI spaced-repetition system. Its model is topic → concept → learning unit, plus an inbox and a source row. The scheduler in `holocron/backend/app/core/fsrs.py` is FSRS-4.5 with four ratings (`forgot`, `struggled`, `got_it`, `easy`), a 0.9 retention target, and an 0.82 stability multiplier on the first schedule of an AI-written card. Cards at or above 0.85 confidence auto-accept; the rest wait in an inbox (`holocron/backend/app/models/inbox.py`). The product spec (`holocron/SPEC.md`) calls for a separate Next.js frontend and a Railway Postgres. That repo does not have people, companies, digest provenance, or a phone review loop as first-class objects.

**speed-reader-v2** (`https://github.com/nchua/speed-reader-v2`, private, branded Holocron) is the app Nick actually ships. Next.js 15 App Router, TypeScript, Tailwind, Drizzle, Neon Postgres, Auth.js v5, Resend, `@anthropic-ai/sdk` pinned to the model alias `claude-sonnet-4-6` in `lib/llm/anthropic.ts`, Vitest, deployed on Railway as `holocron-web`. Domain objects are sources he has read, concepts (label + aliases), and verbatim quotes. AI tags are constrained to a fixed 19-tag vocabulary in `lib/vocabulary.ts`. There is no spaced repetition. `DESIGN.md` and the surfaces (`/read`, `/library`, atlas, `/write`) are locked. `CAPTURE_MOBILE_PWA_PLAN.md` chooses an installable PWA with no service worker in the first slice, and bearer tokens stored as SHA-256 hashes (`capture_tokens`).

**Assumptions:**

- Field Notes digests are short (a weekly chat message, not a book). One synchronous model call per paste is acceptable.
- A single person uses the app. Tables still carry `user_id` so a later second user is a migration, not a rewrite.
- Quotes and links in the digest are public. Sending a digest to Anthropic for extraction is an accepted cost of the markdown path. JSON import does not call the model.
- "Today" and the daily review cap use America/Los_Angeles. Timestamps are stored as `timestamptz` in UTC.
- The implementer creates a new private repo `nchua/field-notes` and a new Neon database. Do not write Field Notes tables into the Holocron database, and do not add this app to `nchua/projects`, `nchua/holocron`, or `nchua/speed-reader-v2`.

## Scope

**In scope:**

- A new mobile-first web app with real sign-in for one allowlisted email.
- Ingestion of a digest by pasting markdown, by POSTing JSON, and (later milestone) by webhook and inbound email. All three paths write the same tables.
- A knowledge store: digests, items, sightings, entities, aliases, cards, reviews, per-entity memory.
- Entity resolution by normalized name and alias, manual merge, and suggested merges later. Faceted browse and person×company (or any pair) cross-links.
- Recall cards with citations, an FSRS queue, a daily cap, and a record of what Nick has accepted, marked known, reviewed, and caught up on.
- An installable PWA. Offline review is a later milestone.

**Non-goals:**

- Changing the Field Notes Grok bot to emit JSON. The app defines the contract; a follow-up can teach the bot to POST it. Until then Nick pastes markdown.
- Embedding this product inside Holocron or speed-reader-v2, sharing their database, or importing their 19-tag vocabulary as a closed set.
- RSVP reading, a knowledge-graph visualization, embeddings, multi-user sharing, native iOS, streaks, and push notifications.
- Auto-merging two entities because the strings are similar. Similarity may suggest a merge. Only exact normalized match, alias match, and Nick's explicit merge join records.

## Where this app lives

This is a new app in a new repo. Holocron and speed-reader-v2 stay as they are.

Holocron already schedules concept cards, and speed-reader-v2 already stores things Nick has read in full. Field Notes is a third loop: a short weekly current-events digest, grouped by who said what about which company, reviewed for a few minutes on a phone. Holocron's topic → concept → card model has nowhere to put a speaker, a company, and a second digest that mentions the same quote. speed-reader-v2's schema, locked visual system, and closed tag list are built for long-form reading; a digest inbox and an entity browser would fight both.

Reuse these parts, by porting behavior into the new repo rather than calling either service at runtime:

- The stack shape of speed-reader-v2: one Next.js app, Drizzle, Neon, Auth.js magic link, Anthropic tool use, Vitest, Railway. One process, so a phone session does not depend on a second API.
- The verbatim-substring gate from `speed-reader-v2/lib/llm/anthropic.ts`: model output that claims to be a quote is kept only when the source text contains it.
- The FSRS-4.5 scheduler from `holocron/backend/app/core/fsrs.py`, ported to TypeScript. The formulas in this spec are the contract.
- The inbox idea: model output Nick has not confirmed stays pending. The threshold and the objects differ, and are defined below.
- The PWA slice from `CAPTURE_MOBILE_PWA_PLAN.md`: a manifest and home-screen install first, a service worker only when offline review is built, and that worker never caches raw digest bodies.

## User stories and flows

- As Nick, I want to paste Friday's digest and see it broken into linked items, so that the chat message becomes something I can come back to.
- As Nick, I want the same person and the same company to land on one page even when a later digest spells them differently, so that memory accumulates.
- As Nick, I want everything a person said about a company, so that I can review a relationship rather than a pile of weeks.
- As Nick, I want a few minutes of review on my phone, so that I actually remember the developments.
- As Nick, I want the app to show what changed since I last looked at a topic, so that old digests stay useful as the story moves.

### Flow: paste a digest

1. Nick opens `/import` on his phone, pastes the markdown, and submits.
2. The server stores the raw text, calls the extractor once, and drops any item whose excerpt is not a verbatim substring of that text.
3. `/digests/[id]` shows the raw text beside the extracted items. Each item is pending.
4. He accepts, marks known, or dismisses each item (or accepts all). Accepted items get recall cards. Known items stay in the library and generate no cards.
5. If extraction returns nothing usable, the raw digest remains, and he can add an item by hand.

### Flow: review on a phone

1. Today shows one primary button, "Review N", where N is the number of cards this session will show (at most the daily cap).
2. A card shows the question. He taps Show answer. The answer, the source link, and the digest title appear together.
3. He taps Again, Hard, Good, or Easy. The next card replaces it. Targets are at least 44px tall and sit in the thumb zone, above the safe-area inset.
4. The session ends when the queue slice is empty. Copy is "That's the session." If the cap hid more due cards, a secondary line says how many are scheduled after the cap.
5. The next day, cards he marked Again or Hard are due again; cards he marked Good or Easy are not, unless the interval has elapsed.

### Flow: browse a cross-link

1. He opens Browse, chooses People, and taps a person.
2. The page lists items newest first, related entities, and a "New since you caught up" group when `caught_up_at` is set.
3. He taps a related company. The page is `/e/{person}?with={company}` and lists only items linked to both.
4. He taps Caught up. Items already listed leave the "new" group. A later digest that mentions the person puts new rows back in that group.

### Flow: JSON import (bot, later or via curl)

1. A client POSTs the JSON contract to `/api/imports` with `Authorization: Bearer $IMPORT_TOKEN`.
2. The server stores the raw JSON, inserts items without a model call, and links entities.
3. A second POST with the same `external_id` and the same body hash returns the existing digest and does not insert duplicates.
4. A second POST with the same `external_id` and a different body returns 409 and does not overwrite.

## Functional requirements

- **FR-1.** Sign-in succeeds only for the email in `ALLOWED_EMAIL` (case-insensitive). Any other address is rejected on the Auth.js `signIn` callback. The address is never hardcoded.
- **FR-2.** Every data route and page requires a session, except `GET /api/health` and `POST /api/imports` when the bearer token matches. Middleware checks only that a session cookie exists. Server code calls `requireUser()` and is the real gate.
- **FR-3.** Pasting markdown creates a digest row whose `raw_body` is the exact submitted string, then runs extraction.
- **FR-4.** A JSON import creates the digest and items and does not call Anthropic.
- **FR-5.** Import idempotency, in order: same `external_id` and same body hash returns the existing digest (`deduped: true`) and does not call the model; same `external_id` and a different hash returns 409 and does not overwrite; no `external_id` (or a new one) whose body hash already exists returns that existing digest, `deduped: true`, and does not call the model. Identical content is one digest.
- **FR-6.** An extracted item is stored only when `excerpt` is a substring of `raw_body`. Items that fail are counted as dropped and are not inserted.
- **FR-7.** `quote_text` is stored only when it is a substring of `excerpt`. A `url` is stored only when it is a substring of `raw_body`; otherwise the url is null and `url_dropped` is true. A quote-kind item whose quote fails the check is stored as `development` if the excerpt survived, and dropped otherwise.
- **FR-8.** Items dedupe by `content_hash` per user. A later digest that hashes to an existing item adds an `item_sightings` row and does not create a second item.
- **FR-9.** Entity resolution is exact: normalized name or alias, scoped to user and kind. A person and a company with the same string stay two rows. Fuzzy string similarity never links or merges on its own.
- **FR-10.** Manual merge of entity A into B (same kind) repoints `item_entities` and aliases onto B, stores A's name as an alias of B, sets `A.merged_into_id = B`, and hides A from browse.
- **FR-11.** Browse lists entities by kind. An entity page lists its accepted and known items as a timeline (newest `occurred_on`, falling back to `created_at`).
- **FR-12.** `/e/{slug}?with={otherSlug}` lists items linked to both entities. When one kind is `person` and the other is `company` or `topic`, the page offers a "said about" narrowing: the person is `speaker` or `subject`, and the other entity is `about` or `mentioned`.
- **FR-13.** Each pending item can be set to `accepted`, `known`, or `dismissed`. Accepted items are eligible for cards. Known items stay browsable and get no cards. Dismissed items stay stored for dedupe and disappear from browse.
- **FR-14.** Generated cards are type `recall`, cite at least one real item id, and become `active` only when they pass the grounding check in this spec. Failures stay `pending`. The review UI renders the answer together with the cited item's url and digest title.
- **FR-15.** The review queue uses timezone `America/Los_Angeles`. It returns at most `daily_cap` cards per local day (default 15), of which at most `new_card_cap` (default 5) have `review_count = 0`. Due previously-reviewed cards fill the rest first.
- **FR-16.** Submitting a rating writes a `reviews` row and updates the card's difficulty, stability, retrievability, `next_review_at`, `review_count`, and `lapse_count` using the scheduler in this spec.
- **FR-17.** Once `caught_up_at` is set, an entity page splits items into "new since you caught up" and older items. An item is new when it was created after `caught_up_at` or has a sighting with `seen_at` after `caught_up_at`. Caught up sets that timestamp to now. A review does not set it.
- **FR-18.** Today lists up to five accepted or known items created after `user_settings.last_seen_at`, then sets `last_seen_at` to now.
- **FR-19.** The app is a portrait PWA (`display: standalone`, start URL `/`) with 192 and 512 icons, `viewport-fit: cover`, and rating controls of at least 44px. Milestone 1 has no service worker.
- **FR-20.** A digest page can add an item by hand (kind, headline, excerpt, optional url, optional quote, optional entity name and kind). The excerpt must be a substring of `raw_body` or the request is rejected with 422.
- **FR-21.** Each model call writes an `agent_runs` row with kind, model id, token counts, duration, and status. The row does not contain the prompt, the raw digest, or item text.
- **FR-22.** Milestone 2: `POST /api/ingest/webhook` accepts the same markdown and JSON bodies, authenticated by a shared secret, and is the target for inbound email.
- **FR-23.** Milestone 2: `pg_trgm` similarity at or above 0.72 creates a merge *suggestion*. Nick confirms or dismisses it. Confirmation runs the same merge as FR-10.
- **FR-24.** Milestone 2: a service worker caches the app shell and the current queue payload, queues review posts in IndexedDB, and replays them with the same `Idempotency-Key`. It does not cache digest bodies or any response that includes `raw_body`.
- **FR-25.** Milestone 3: connection cards ("What did {person} say about {entity}?") and a short "what changed" paragraph for an entity. Every sentence in that paragraph cites an item id, and the paragraph is subject to the same grounding check as card backs.
- **FR-26.** Nick can write a recall card on an accepted item by hand. Hand-written cards are `active`, `ai_generated = false`, and skip the grounding check. They still cite that item.

## Technical design

### Architecture

One Next.js 15 App Router process owns the UI, the route handlers, and the model calls. Neon Postgres is the only store. The browser never receives `IMPORT_TOKEN` or the Anthropic key.

```
phone / desktop browser
        │  session cookie
        ▼
Next.js (Railway)  ── bearer ──  POST /api/imports   (bot or curl)
        │
        ├── Drizzle ── Neon Postgres
        └── Anthropic messages.create (markdown extraction and card generation only)
```

Markdown paste and JSON import share `lib/import/ingest.ts`. The markdown path runs the extractor first and then feeds the validated items into the same inserter the JSON path uses. Webhook and email, when built, call that same function.

Extraction and card generation are synchronous in milestone 1. A weekly digest is one short call. The request returns when the digest row and items are committed. Card generation runs when items are accepted, in the accept request, batched per digest.

### Data model

UUIDs for every id. `timestamptz` for instants. `date` for `occurred_on` and digest period bounds. Drizzle schema in `lib/schema.ts`, migrations via `drizzle-kit`. Postgres `CHECK` constraints mirror the unions below.

**users, accounts, sessions, verification_tokens** — Auth.js v5 Drizzle adapter tables. `users.email` is unique on `lower(email)`.

**user_settings** — `user_id` pk, `daily_cap int not null default 15`, `new_card_cap int not null default 5`, `timezone text not null default 'America/Los_Angeles'`, `last_seen_at timestamptz null`.

**digests**

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid pk | |
| user_id | uuid fk | cascade delete |
| external_id | text null | idempotency key from the producer |
| title | text | |
| period_start, period_end | date null | |
| received_at | timestamptz | default now() |
| channel | text | `paste`, `json`, `webhook`, `email` |
| raw_format | text | `markdown` or `json` |
| raw_body | text | exact submitted payload |
| body_hash | text | sha256 hex of `raw_body` |
| status | text | `extracted`, `empty`, `failed` |
| created_at | timestamptz | |

Unique (`user_id`, `external_id`) where `external_id` is not null.

**items**

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid pk | |
| user_id | uuid fk | |
| digest_id | uuid fk | first sighting |
| kind | text | `development`, `quote`, `link`, `paper` |
| headline | text | |
| body | text | one to three sentences; may paraphrase the excerpt |
| excerpt | text | verbatim span of `raw_body` |
| quote_text | text null | verbatim span of `excerpt` |
| url | text null | |
| url_dropped | boolean | default false |
| source_name | text null | publication, "X", "arXiv" |
| occurred_on | date null | when it happened |
| content_hash | text | algorithm below |
| status | text | `pending`, `accepted`, `known`, `dismissed` |
| extractor | text | `llm`, `json`, `manual` |
| created_at | timestamptz | |

Unique (`user_id`, `content_hash`).

`content_hash` is sha256 hex of a basis string, after NFKC, collapsed whitespace, trim, and lowercase:

1. `url` if present, else
2. `quote_text` if present, else
3. `headline + "\n" + excerpt`.

**item_sightings** — `item_id`, `digest_id`, `seen_at timestamptz`. Unique (`item_id`, `digest_id`). The first sighting inserts a row too, so a timeline query is one table. `on conflict do nothing`.

**entities**

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid pk | |
| user_id | uuid fk | |
| kind | text | `person`, `company`, `topic`, `theme`, `technology`, `claim` |
| name | text | display name. For a claim, the proposition, ≤ 140 characters |
| slug | text | unique per user on `lower(slug)` |
| watched | boolean | default false. Watched names are preferred by the extractor |
| status | text | `confirmed` or `provisional` |
| merged_into_id | uuid null | self fk. Non-null rows are hidden |
| created_at | timestamptz | |

Unique (`user_id`, `kind`, `lower(name)`) where `merged_into_id` is null.

**entity_aliases** — `id`, `user_id`, `kind`, `entity_id` fk, `alias text`, `normalized text`. Unique (`user_id`, `kind`, `normalized`). `normalized` is the match key from the function below.

**item_entities** — pk (`item_id`, `entity_id`, `role`). `role` is `speaker`, `subject`, `mentioned`, or `about`. `confidence numeric(3,2) null` (JSON and manual imports use `1.00`).

**cards**

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid pk | |
| user_id | uuid fk | |
| type | text | `recall` in milestone 1. `cloze` and `connection` exist in the check so milestone 3 does not rebuild the table; milestone 1 writes only `recall` |
| front, back | text | |
| status | text | `pending`, `active`, `suspended` |
| confidence | numeric(3,2) | |
| ai_generated | boolean | |
| difficulty | numeric | default 0.3, stored in [0.1, 0.9] |
| stability | numeric | default 0, days |
| retrievability | numeric | default 1 |
| last_reviewed_at | timestamptz null | |
| next_review_at | timestamptz null | null means "new, eligible now" once `active` |
| review_count, lapse_count | int | default 0 |
| created_at | timestamptz | |

Index (`user_id`, `status`, `next_review_at`).

**card_items** — pk (`card_id`, `item_id`). A card insert with zero rows is rejected.

**reviews** — `id`, `user_id`, `card_id` fk, `rating` (`forgot`, `struggled`, `got_it`, `easy`), `elapsed_ms int null`, `reviewed_at`, `difficulty_after`, `stability_after`, `interval_days`, `idempotency_key text null`. Unique (`user_id`, `idempotency_key`) where the key is not null.

**entity_memory** — pk `entity_id`. `user_id`, `last_reviewed_at null`, `caught_up_at null`, `review_count int default 0`, `mean_retrievability numeric null`. Updated when a review is submitted, for every entity linked to a cited item: increment `review_count`, set `last_reviewed_at`, recompute `mean_retrievability` as the average `retrievability` of `active` cards that cite an accepted item linked to that entity. `caught_up_at` changes only via the Caught up action.

**agent_runs** — `id`, `user_id`, `kind` (`extract`, `cards`), `digest_id uuid null`, `model text`, `status` (`done`, `failed`), `tokens_in int null`, `tokens_out int null`, `duration_ms int null`, `error text null`, `created_at`. No prompt and no digest text.

**merge_suggestions** (milestone 2) — `id`, `user_id`, `from_entity_id`, `into_entity_id`, `score numeric`, `status` (`open`, `accepted`, `dismissed`). Unique open pair.

#### Normalization

```
normalize(name, kind):
  s = NFKC(name).trim(), collapse internal whitespace
  replace curly quotes with straight quotes
  if kind == company:
    strip a trailing ", Inc" / "Inc." / "Corp" / "Corporation" / "Ltd" / "LLC" / "Co" / "Company"
  return lowercase(s)
```

Slug is the display name in kebab case. On collision append `-2`, `-3`, and so on.

#### Resolution

```
resolve(userId, name, kind):
  norm = normalize(name, kind)
  if an alias exists for (userId, kind, norm) on an unmerged entity: return it
  if an unmerged entity has (userId, kind, lower(name) == norm):
    add an alias when the surface form differs
    return it
  create a provisional entity with the surface name
  return it
```

Watched entities are inserted as `confirmed`. The extractor receives up to 150 watched `{name, kind}` pairs and is told to reuse a watched name when it is the same real-world thing, and not merely a related topic.

#### JSON contract (`schema_version: 1`)

`POST /api/imports` and, later, the webhook accept:

```json
{
  "schema_version": 1,
  "external_id": "fn-2026-11-21",
  "title": "Field Notes — Nov 21, 2026",
  "period": { "start": "2026-11-14", "end": "2026-11-21" },
  "trust": true,
  "items": [
    {
      "kind": "quote",
      "headline": "Example headline",
      "body": "One sentence on why it matters.",
      "excerpt": "Example headline. \"Sample quote for the fixture.\"",
      "quote_text": "Sample quote for the fixture.",
      "speaker": "Ada Example",
      "url": "https://example.com/post",
      "source_name": "Example",
      "occurred_on": "2026-11-20",
      "entities": [
        { "name": "Ada Example", "kind": "person", "role": "speaker" },
        { "name": "Example Co", "kind": "company", "role": "about" }
      ]
    }
  ]
}
```

Rules: `schema_version` other than `1` is 400. `items` length 1–40. `excerpt` must occur inside the raw JSON string of the request body (store the body before parsing mutates it). When `trust` is present it wins: `true` inserts items as `accepted`, `false` as `pending`. When it is omitted, bearer imports default to `true` and session-cookie imports default to `false`. `speaker` is required when `kind` is `quote`; the server also links that speaker as a `person` with role `speaker` if the entities array omitted them.

Recommended markdown shape, not validated (the model reads whatever Nick pastes):

```markdown
# Field Notes — 2026-11-21

Period: 2026-11-14 to 2026-11-21

## Topic name

### Headline
One short paragraph.
Source: [Publication](https://example.com)

> "Verbatim quote." — Person Name
> [link](https://example.com)
```

#### Extraction tool

One Anthropic tool, `emit_digest_items`, `tool_choice` forced. Model id `claude-sonnet-4-6` (the same alias speed-reader-v2 uses). `max_tokens` 4096.

Input: the raw markdown, plus the watched-entity list. System instructions: copy `excerpt`, `quote_text`, and `url` from the digest; invent nothing; fewer items is the correct outcome when unsure; prefer a watched name for the same real-world thing; at most 40 items; a quote item includes a speaker.

Output items use the same fields as the JSON item, without `trust`. Then run FR-6 and FR-7. Markdown-origin items are stored `pending` / `extractor = llm`.

#### Card generation tool

`emit_cards`, forced, `max_tokens` 2048. Input is the accepted items only: `id`, `headline`, `excerpt`, `quote_text`, `url`, entity names. At most 2 cards per item and 40 per call.

Each card: `{ "item_id", "front", "back" }`. `front` is a question answerable from that item's excerpt alone. `back` is one or two sentences. Drop cards whose `item_id` was not in the input.

Grounding check, on the back text: take the set of words of length ≥ 4 in `headline + excerpt + quote_text`, lowercased. The back must have at least 40% of its own length≥4 words in that set, and at least one such overlapping word. Pass → `status = active`, `confidence = 0.90`. Fail → `status = pending`, `confidence = 0.50`. `ai_generated = true`. First-schedule stability uses the 0.82 factor.

The review screen shows `back`, then the cited url, source name, and digest title. The back is not the citation by itself.

#### Scheduler

Port these functions exactly. `difficulty` is stored in `[0.1, 0.9]`. Stability updates that refer to the FSRS 1–9 scale multiply stored difficulty by 10, matching `holocron/backend/app/core/fsrs.py`.

Weights: `w0=0.4`, `w1=0.6`, `w2=2.4`, `w3=5.8`, `w4=4.93`, `w5=0.94`, `w6=0.86`, `w7=0.01`, `w8=1.49`, `w9=0.14`, `w10=0.94`, `w11=2.18`, `w12=0.05`, `w13=0.34`, `w14=1.26`, `w15=0.29`, `w16=0.2`.

Grades: `forgot=1`, `struggled=2`, `got_it=3`, `easy=4`. Target retention `0.9`. `AI_CARD_STABILITY_FACTOR = 0.82`.

- `initial_difficulty(grade) = clamp((w4 - (grade - 3) * w5) / 10, 0.1, 0.9)`
- `initial_stability(grade) = w[grade - 1]`
- `retrievability(stability, elapsedDays) = (1 + elapsedDays / (9 * stability)) ** -1`, or 0 when stability ≤ 0
- `next_difficulty(d, grade) = clamp(w6 * initial_difficulty(grade) + (1 - w6) * (d - w7 * (grade - 3)), 0.1, 0.9)`
- On success (`grade ≥ 2`): `hard = w9` when grade is 2, else 1. `growth = exp(w8) * (11 - d * 10) * stability ** (-w10) * (exp(w11 * (1 - R)) - 1) * hard + 1`. New stability = `max(0.1, stability * growth)`.
- On failure (`grade = 1`): `new = w12 * (d * 10) ** (-w13) * ((stability + 1) ** w14 - 1) * exp(w15 * (1 - R))`. New stability = `max(w16, min(new, stability))`.
- `intervalDays = clamp(9 * stability * (0.9 ** -1 - 1), 1/1440, 365)`
- `next_review_at = now + intervalDays`

When `review_count == 0` or `stability <= 0`, ignore the stored difficulty and stability and use the initial formulas. If `ai_generated`, multiply that initial stability by 0.82. Otherwise compute elapsed days from `last_reviewed_at`, then the success or failure update. Persist difficulty, stability, and retrievability rounded to 4 decimal places, and `interval_days` rounded to 2.

`lapse_count` increments when the rating is `forgot`.

Fixture `now` is irrelevant to the four numbers. Tests assert the rounded tuple `(difficulty, stability, retrievability, interval_days)`:

| Case | rating | review_count | d in | s in | elapsed days | ai | d | s | R | interval |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | got_it | 0 | 0 | 0 | 0 | true | 0.493 | 1.968 | 1.0 | 1.97 |
| B | forgot | 0 | 0 | 0 | 0 | true | 0.681 | 0.328 | 1.0 | 0.33 |
| C | easy | 0 | 0 | 0 | 0 | false | 0.399 | 5.8 | 1.0 | 5.8 |
| D | got_it | 1 | 0.493 | 1.968 | 2 | true | 0.493 | 8.9118 | 0.8985 | 8.91 |
| E | forgot | 1 | 0.493 | 1.968 | 2 | true | 0.6575 | 0.2 | 0.8985 | 0.2 |
| F | struggled | 1 | 0.493 | 1.968 | 2 | true | 0.5752 | 2.8084 | 0.8985 | 2.81 |

#### Queue

Local day bounds come from `user_settings.timezone`.

```
reviewed_today = reviews where reviewed_at is in the local day
remaining = max(0, daily_cap - count(reviewed_today))
due = active cards where next_review_at is null or next_review_at <= now()
order due by (review_count = 0) ascending, then next_review_at nulls first, then created_at
take due cards with review_count > 0 first, up to `remaining`
then new cards (review_count = 0), up to min(new_card_cap, remaining - taken)
```

#### Cost and hallucination controls

- Markdown import: one extract call. Accept: one card call per digest batch, not per item.
- Skip the model entirely for JSON imports and for a body hash that was already extracted.
- Reject `raw_body` over 80,000 characters with 413.
- At most 10 model calls per user per rolling hour; the 11th returns 429 and leaves any already-stored raw digest in place with `status = failed` and a retry affordance.
- Do not log `raw_body`, prompts, URLs, or token secrets. `agent_runs.error` is a short sanitized message.
- The digest page always shows raw text next to items, so a bad extraction is visible.
- Pending cards and pending items share `/inbox`.

A weekly digest is a few thousand tokens. At Sonnet prices that is cents per week. The caps above are the control; do not add a second judge model.

### APIs and interfaces

Cookie session unless noted. JSON in and out. Errors: `{ "error": "short code" }` with 400, 401, 404, 409, 413, 422, or 429.

| Method and path | Auth | Behavior |
| --- | --- | --- |
| `GET /api/health` | none | `{ "ok": true }` |
| `POST /api/imports` | bearer or session | JSON contract. Bearer acts as the allowlisted user; 409 `no_user` if that user has never signed in. Response below. |
| `POST /api/imports/markdown` | session | `{ "markdown", "title?", "external_id?" }`. Title defaults to the first H1, else `Field Notes — {local date}`. |
| `GET /api/digests` | session | Newest first. `{ id, title, received_at, status, item_count }`. No `raw_body` in the list. |
| `GET /api/digests/:id` | session | Digest plus items (`id`, `kind`, `headline`, `status`, `url`, `excerpt`, `entities: [{ slug, name, kind, role }]`). Include `raw_body` here only. |
| `POST /api/digests/:id/items` | session | Manual item (FR-20). |
| `PATCH /api/items/:id` | session | `{ "status": "accepted" \| "known" \| "dismissed" }`. Transition into `accepted` triggers card generation for that item if it has no cards yet. |
| `POST /api/digests/:id/accept` | session | Body `{ "status": "accepted" }` sets every pending item on the digest to accepted and generates cards once for the batch. |
| `POST /api/digests/:id/extract` | session | Re-runs markdown extraction when `status` is `failed` or `empty`. 409 when the digest already has items. No model call when `raw_format` is `json`. |
| `GET /api/entities?kind=&q=` | session | Unmerged entities. Optional `q` matches name or alias, case-insensitive, limit 8 when `q` is set, else the whole kind. `{ id, name, slug, kind, watched, item_count }`. |
| `GET /api/entities/:slug?with=` | session | Entity, aliases, items (same item shape as the digest GET, including roles), related entities (top 8 by co-occurrence), and the ids of items that are new since `caught_up_at`. |
| `POST /api/entities` | session | `{ name, kind, watched? }` creates a confirmed entity. Used by Settings. |
| `POST /api/entities/merge` | session | `{ "from_id", "into_id" }`. 422 when kinds differ or ids match. |
| `POST /api/entities/:slug/caught-up` | session | Sets `caught_up_at = now()`. |
| `POST /api/cards` | session | Manual card `{ item_id, front, back }` (FR-26). |
| `GET /api/review/queue` | session | `{ cards: [{ id, front, back, type, item: { url, source_name, digest_title } }], remaining_due }`. `back` is included so milestone 2 can cache one payload; the client still hides it until Show answer. |
| `POST /api/reviews` | session | `{ card_id, rating, elapsed_ms? }` plus header `Idempotency-Key`. Replays return the original `{ next_review_at, interval_days }` without a second schedule. |
| `GET /api/inbox` | session | Pending items and pending cards. |
| `PATCH /api/cards/:id` | session | `{ "status": "active" \| "suspended" }` so Nick can promote or drop a pending card. |
| `PATCH /api/settings` | session | `{ daily_cap?, new_card_cap? }`, each clamped to 1–50. |
| `POST /api/ingest/webhook` | milestone 2 | Header `X-Field-Notes-Secret`, checked with the same hashed compare as the bearer token. Body is the JSON contract or `{ "markdown", "external_id?" }`. |

Import response:

```json
{
  "digest_id": "uuid",
  "deduped": false,
  "items_created": 12,
  "items_deduped": 2,
  "items_dropped": 1,
  "entities_created": 5,
  "entities_linked": 18
}
```

Bearer comparison builds equal-length buffers (hash both sides with sha256, then `timingSafeEqual`) so the token's length is not leaked. Never log the header.

### Key components

| Piece | Responsibility |
| --- | --- |
| `lib/auth.ts`, `lib/auth-guard.ts` | Auth.js Resend provider. `signIn` callback rejects non-allowlisted emails. `requireUser()` for pages and handlers. |
| `lib/schema.ts` | Drizzle tables and check constraints. |
| `lib/fsrs.ts` | Pure scheduler. No I/O. |
| `lib/import/normalize.ts`, `hash.ts`, `verbatim.ts` | String rules, content hash, substring gates. |
| `lib/import/resolve-entity.ts` | Exact resolution and merge. |
| `lib/import/ingest.ts` | Shared insert path for JSON, markdown, manual, and later webhook. Transaction per digest. |
| `lib/llm/extract.ts`, `lib/llm/cards.ts` | Tool calls, usage capture, no body logging. |
| `lib/review/queue.ts` | Cap math and due ordering. |
| `app/page.tsx` | Today: Review button, five new items, link to the latest digest. |
| `app/review/page.tsx` | One card, show-answer, four ratings. Keys 1–4 map to Again/Hard/Good/Easy on a keyboard. |
| `app/import/page.tsx` | Markdown textarea. A second tab pastes JSON and POSTs it through the session path. |
| `app/digests/[id]/page.tsx` | Raw text and items, accept / known / dismiss, add item. |
| `app/browse/page.tsx` | Kind tabs: People, Companies, Topics, Themes, Tech, Claims. |
| `app/e/[slug]/page.tsx` | Timeline, related entities, `?with=`, Caught up, Merge into (search by name, same kind, limit 8). |
| `app/inbox/page.tsx` | Pending items and cards. |
| `app/settings/page.tsx` | Watchlist add, caps, sign out. |
| `app/manifest.ts` | PWA manifest. |

UI is a single column under 768px. Body text at least 16px. Rating bar is sticky to the bottom with `env(safe-area-inset-bottom)`. Desktop may show the digest list beside the detail. No component library and no Holocron visual system: system font, near-black background `#111111`, light text, one accent for the primary button. This is a utility for a five-minute session.

### Files to create or change

Create them in the new repo `nchua/field-notes`. No files in `nchua/projects` change except this spec and the `build-specs/README.md` index, which are already the planning home.

| Path | Change |
| --- | --- |
| `package.json`, `tsconfig.json`, `next.config.ts`, `drizzle.config.ts`, `vitest.config.ts` | App scaffold. Node ≥ 22. |
| `.env.example` | Names only, empty values. |
| `README.md` | How to run, migrate, and deploy. Point at this spec for product behavior. |
| `lib/schema.ts` and `drizzle/` | Tables in this spec. |
| `lib/fsrs.ts`, `lib/fsrs.test.ts` | Scheduler and the six fixtures. |
| `lib/import/*`, `lib/import/*.test.ts` | Normalize, hash, verbatim, ingest idempotency. |
| `lib/llm/extract.ts`, `lib/llm/cards.ts` | Model calls. |
| `lib/auth.ts`, `lib/auth-guard.ts`, `middleware.ts` | Allowlisted magic link. Middleware is cookie-presence only. |
| `app/api/**/route.ts` | Handlers in the table above, except the webhook route (milestone 2). |
| `app/**/page.tsx` | Screens in Key components. |
| `app/manifest.ts`, `public/icon-192.png`, `public/icon-512.png` | Installable PWA. A `#111111` square with light "FN" lettering is enough. |
| `app/api/ingest/webhook/route.ts` | Milestone 2 only. |

### Constraints

- Environment variables: `DATABASE_URL`, `AUTH_SECRET`, `AUTH_RESEND_KEY`, `AUTH_EMAIL_FROM`, `ALLOWED_EMAIL`, `IMPORT_TOKEN`, `ANTHROPIC_API_KEY`, `NEXT_PUBLIC_APP_URL`. Milestone 2 adds `RESEND_WEBHOOK_SECRET` if inbound email signature checks need it. Never commit values. `.env.example` lists the names.
- New Neon project and new Railway service. Do not reuse Holocron's `DATABASE_URL`.
- Match speed-reader-v2's generation: Next.js ~15.4, React 19, TypeScript strict, Tailwind, Drizzle, `@neondatabase/serverless`, `next-auth` 5, `@auth/drizzle-adapter`, `resend`, `@anthropic-ai/sdk`, Vitest. Add no further dependencies in milestone 1. Validate JSON by hand in `lib/import/schema.ts`.
- Full digest text is allowed in the database (it is the product) and in the single-digest GET for the signed-in user. It stays out of list endpoints, logs, and `agent_runs`.
- Ratings on screen are Again / Hard / Good / Easy and map to `forgot` / `struggled` / `got_it` / `easy`.
- No streaks. The home screen does not lead with an overdue count. The queue button shows how many cards this session includes.

### Edge cases and failure behavior

- Empty paste, or a model call that throws: digest row `status = failed` or `empty`, raw text kept, no partial items from a failed transaction. The page offers Retry extraction and Add item.
- Model returns an excerpt that is not in the source: item dropped, digest still `extracted` if any item survived, else `empty`.
- Same quote URL arriving in a second week: one item, two sightings. The timeline shows the later digest under "mentioned again".
- Merge target is itself merged: 422. Merge across kinds: 422.
- Review idempotency replay: same JSON as the first response, no second `reviews` row, no second FSRS update.
- Queue when nothing is due: `{ "cards": [], "remaining_due": 0 }`. Today copy: "Nothing due." with a link to the latest digest.
- Cap already spent today: same empty queue, `remaining_due` reports how many active cards are due after the cap.
- `occurred_on` unparseable: store null and keep the item.
- Entity name blank after trim: skip that entity link, keep the item.
- Bearer import before the first sign-in: 409 `no_user`.

## Tech stack and dependencies

| Layer | Choice |
| --- | --- |
| App | Next.js 15 App Router, React 19, TypeScript strict, Tailwind |
| Data | Neon Postgres, Drizzle ORM, drizzle-kit migrations |
| Auth | Auth.js v5, Resend magic link, database sessions, httpOnly cookie |
| Model | `@anthropic-ai/sdk`, model `claude-sonnet-4-6`, forced tool use |
| Tests | Vitest |
| Host | Railway for the app, Neon for Postgres |

`pg_trgm` is created in the milestone 2 migration (`CREATE EXTENSION IF NOT EXISTS pg_trgm`). Milestone 1 does not need it. No pgvector.

Deploy is a normal Next.js service on Railway. Document the env vars in the new repo's README. Production cookies are `secure` and `sameSite=lax`.

## Implementation plan

Build milestone 1 to completion and stop. It is useful with no later milestone. Milestones 2 and 3 start only after milestone 1's acceptance criteria pass.

### Milestone 1 — Library, grouping, and review

**Goal:** Nick can paste a digest or POST JSON, browse items by person and company (including a cross-link), and review cited cards on his phone. Data is still there the next day.

**Steps:**

1. Create the private repo `nchua/field-notes`, the Next.js scaffold, Neon, and Drizzle. Commit `.env.example` and a README that states the env vars and "do not log raw digests".
2. Add Auth.js magic link and the allowlist. Seed `user_settings` on first sign-in.
3. Add the schema through `agent_runs` (no `merge_suggestions` yet) and the first migration.
4. Port `lib/fsrs.ts` and land the six fixtures.
5. Implement normalize, hash, verbatim checks, entity resolution, and `ingest.ts`, with tests for idempotency, 409, dedupe, and the substring gates.
6. Implement the JSON route and the markdown route. Markdown calls `lib/llm/extract.ts`.
7. Build Today, Import, digest detail (accept / known / dismiss / add item), Browse, entity page with `?with=` and merge, Inbox, and Settings watchlist.
8. On accept, generate recall cards and run the grounding check. Build the review screen and `POST /api/reviews` with idempotency.
9. Add the manifest, icons, safe-area padding, and 44px rating targets.
10. Run the test plan below.

**Acceptance criteria:**

- [ ] FR-1 through FR-21 and FR-26 pass.
- [ ] A fixture JSON digest round-trips through `POST /api/imports` twice: the second response has `deduped: true` and the item count is unchanged.
- [ ] A markdown fixture with one real excerpt and one invented excerpt stores only the real item.
- [ ] Two items that mention "NVIDIA" and "Nvidia" share one company entity. "Nvidia" and "Nvidia Inc." share one entity. "Jensen" and "Jensen Huang" stay two entities until a manual merge, and after the merge there is one page and the old name is an alias.
- [ ] `/e/{person}?with={company}` returns only shared items.
- [ ] Scheduling a card with rating Good as the first AI review yields interval 1.97 days (fixture A). A second review is not due until that interval elapses.
- [ ] The review flow works at a 390px viewport: Show answer, then a rating, then the next card, without horizontal scroll.
- [ ] The app installs to a phone home screen and opens standalone at `/`.
- [ ] `npm test`, `npm run typecheck`, and `npm run build` pass.

### Milestone 2 — Webhook, suggestions, offline

**Goal:** The bot can push a digest without a paste, near-duplicate entities surface as suggestions, and a review started on a train finishes offline and syncs.

**Steps:**

1. Add `POST /api/ingest/webhook` using the import token header and the shared ingest function. Support markdown and JSON bodies.
2. Point inbound email at that route. Read Resend's current inbound webhook docs at implementation time, pin the field that carries the plain-text body in a comment with the doc URL, and verify `RESEND_WEBHOOK_SECRET` when it is set. Reject a bad signature with 401.
3. Add `pg_trgm` and `merge_suggestions`. Scores ≥ 0.72 and < 1.0 become open suggestions. Accept runs FR-10.
4. Add a service worker that caches the shell and the queue JSON, stores review posts in IndexedDB with the idempotency key, and replays when online. Exclude any URL that can return `raw_body`.
5. Optional: replace the single env token with hashed rows (sha256, plaintext shown once) following `capture_tokens` in speed-reader-v2, so a token can be revoked without a redeploy. Keep the env token working as a bootstrap.

**Acceptance criteria:**

- [ ] FR-22, FR-23, and FR-24 pass.
- [ ] A webhook retry with the same `external_id` and body does not double items or double model calls.
- [ ] An offline rating syncs exactly once when the network returns.
- [ ] A suggestion never merges until Nick confirms it.

### Milestone 3 — Connections and topic change

**Goal:** Review can ask what a person said about a company, and an entity page can summarize what changed, with every sentence cited.

**Steps:**

1. When generating cards, also emit up to one `connection` card per (person, other entity) pair that co-occurs on a newly accepted item. Front: `What did {person} say about {entity}?` Back is grounded in the item excerpt. Same grounding rule.
2. Add `POST /api/entities/:slug/what-changed`, which sends only the excerpts of items newer than `caught_up_at` and requires each output sentence to carry an item id. Fail the grounding check → return the item list with no paragraph, rather than an uncited paragraph.
3. Show a small memory line on the entity page: review count and mean retrievability from `entity_memory`.

**Acceptance criteria:**

- [ ] FR-25 passes.
- [ ] A connection card's back fails closed (stays pending) when it introduces a name that is not in the cited excerpt.
- [ ] The what-changed paragraph renders only item ids that are in the "new since caught up" set.

## Testing plan

- **Automated:** `npm test` (Vitest), `npm run typecheck`, `npm run build`.
- **Cases:**
  - FR-6 / FR-7 — verbatim gates: excerpt missing, quote not inside excerpt, url not inside raw body, quote-kind demoted to development.
  - FR-5 / FR-8 — same `external_id` and hash returns `deduped`; different hash returns 409; same quote URL in two digests yields one item and two sightings.
  - FR-9 / FR-10 — normalization table (case, `Inc.`, curly quotes) and merge repoints links.
  - FR-14 — grounding pass and fail, including a back that cites an unknown item id.
  - FR-15 / FR-16 — queue cap in America/Los_Angeles across a UTC day boundary, and the six scheduler fixtures.
  - FR-1 — sign-in callback rejects a second email. Bearer route returns 401 on a bad token.
  - Model tests mock `@anthropic-ai/sdk`. No live API call in `npm test`.
- **Manual:** At a 390×844 viewport, paste a digest, accept two items, finish a three-card session, reload, and confirm the next due time moved. Open a person×company cross-link. Add the app to the home screen and confirm it opens without browser chrome. Confirm server logs for that session contain no digest sentence and no `IMPORT_TOKEN`.

## Risks

- **Freeform markdown extracts poorly.** Field Notes is chat prose, not a schema. **Mitigation:** verbatim gates, pending status, raw text beside items, manual add-item. The library is useful even when zero cards activate.
- **Two people share a normalized name** ("Chris" at two companies). **Mitigation:** no fuzzy auto-merge; kind-scoped exact match; manual merge is the only join. Watchlist preferred names reduce accidental new rows for people Nick already tracks.
- **A card back adds a fact that happens to share common words** and passes the 40% check. **Mitigation:** pending is available, the source link is always on screen, and milestone 3 connection cards fail closed on unknown names. Do not add a second model to police the first in milestone 1.
- **Anthropic alias `claude-sonnet-4-6` moves over time.** speed-reader-v2 already accepts that and keeps the id in one constant. **Mitigation:** one `MODEL_ID` constant, stored on each `agent_runs` row.
- **Offline cache leaks a digest.** **Mitigation:** milestone 2's worker excludes raw-body routes. Milestone 1 has no worker, so the risk is not present yet.
- **Import token in a chat log or shortcut.** **Mitigation:** compare hashes, support revocation in milestone 2, never log the header.

## Open questions

Each one has a default. The implementer follows the default. A `reviewed` spec can replace a default with Nick's answer.

- **Q1.** Repo name and hosting? **Default:** private repo `nchua/field-notes`, Railway for the app, a new Neon project for Postgres.
- **Q2.** Which email is allowlisted? **Default:** whatever Nick puts in `ALLOWED_EMAIL`. The code reads the env var and ships with no address in the source.
- **Q3.** Change the Field Notes bot to POST JSON in this same effort? **Default:** no. Ship the app. Pasting markdown is the Friday path until a follow-up spec updates the bot.
- **Q4.** Card voice? **Default:** recall questions whose answers are grounded in the excerpt, not cloze deletions, in milestone 1.
- **Q5.** Should a bearer JSON import auto-accept items? **Default:** yes (`trust: true`). Cards still pass the grounding check before they become active.
- **Q6.** Daily cap and timezone? **Default:** 15 reviews, 5 of them new, America/Los_Angeles, both caps editable in Settings within 1–50.
- **Q7.** Fuzzy auto-merge? **Default:** never. Milestone 2 may suggest. Nick confirms.
- **Q8.** Google sign-in as well as magic link? **Default:** magic link only, to keep the secret list smaller.
- **Q9.** Initial watchlist? **Default:** empty. Nick adds people and topics in Settings. Imports work before any watchlist exists.
- **Q10.** Resend inbound payload shape? **Default:** milestone 2 reads the current Resend docs and pins the plain-text field. Milestone 1 does not block on email.

## Reviewer checklist

- [ ] The spec can be reviewed and implemented from this file alone.
- [ ] The summary, goal, and success criteria are concrete.
- [ ] Scope and non-goals are explicit.
- [ ] User stories and flows cover the success path and the failure that matters.
- [ ] Requirements are numbered and testable.
- [ ] The design names architecture, data model, APIs, components, and files.
- [ ] Constraints, edge cases, and failure behavior are specified.
- [ ] Stack and dependencies match the target repo, and anything new is justified.
- [ ] Milestones are ordered, and each has acceptance criteria.
- [ ] The testing plan covers the requirements.
- [ ] Risks are identified, and every open question is resolved or has a default.
- [ ] `target_repo` is correct, and no secret values appear in the spec.

### Review notes

## Status log

| Date | Status | Note |
| --- | --- | --- |
| 2026-11-21 | draft | Spec created. |
