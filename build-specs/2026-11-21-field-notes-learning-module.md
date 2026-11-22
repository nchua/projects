---
title: "Field Notes learning module"
status: reviewed
created: 2026-11-21
owner: Nick
target_repo: "nchua/field-notes"
---

# Field Notes learning module

## Summary

Build a new single-user web app, `nchua/field-notes`, that turns Field Notes digests into a durable, browsable memory. Digests land as structured items (a development, a quote, a link, a paper) with provenance. Items are grouped under resolved entities — people, companies, topics, themes, technologies, and claims — and carry cited recall cards on a spaced-repetition queue Nick can finish on his phone in a few minutes.

The app makes no AI calls. A Claude Code skill running on Nick's own machine, on his Claude subscription, reads each digest, writes the structured JSON (including the cards), and pushes it to the app. The app validates it, stores it, groups it, and schedules reviews.

## Goal

Nick stays current, then keeps what he learned. After each Friday digest he can open the app, see what was new, browse everything a person said about a company, and review a short queue. The app remembers what he has seen, what he has reviewed, and how well he recalled it. Weeks later an entity page shows what arrived since he last caught up.

**Success criteria:**

- [ ] Pasting the JSON block the bot wrote (with or without the digest's markdown beside it), or POSTing the same JSON with a bearer token, persists the digest, its items, their cards, and links back to the source.
- [ ] The same person or company spelled the same way after normalization resolves to one entity, and Nick can merge two entities by hand when the strings differ.
- [ ] He can open a person, a company, and the cross-link of the two, on a phone, and see the underlying items with their links.
- [ ] He can run a capped review session of cited recall cards. Ratings change the next due time. Reloading the next day shows the new schedule.
- [ ] When the digest markdown is supplied, an item whose excerpt does not appear in it is never auto-accepted and its cards never enter the queue until Nick accepts the item himself.
- [ ] Running the `field-notes-ingest` skill locally on a new digest file gets it into the app with no paste.
- [ ] The deployed app holds no model API key and makes no outbound AI call.

## Background and user problem

Field Notes is one of Nick's Grok Bot assistants. It keeps him current on topics he cares about: what happened, and what notable people said about it. It sends a short weekly digest, Fridays around 9am America/Los_Angeles, drawn from public X posts, web news, arXiv, blogs, and podcasts. Every item is linked. Quotes are attributed to people, with links. It tracks a list of topics and people.

Its output today is a chat message in markdown. There is no Field Notes API, no database, and no card system. This spec must not assume one.

**Decision (Nick, 2026-11-22): no model in the app; a local loop does the language work.** A deployed server cannot use a Claude subscription, and Nick does not want a per-token API key for this. Instead, Claude Code runs on his own machine under his subscription. A skill in this repo, `field-notes-ingest`, looks at the digest files the Grok bot has produced (JSON or markdown, in a local folder), turns each new one into the contract below with cards, and POSTs it to the app with the bearer token. Building the app is the heavy work (Opus). Each weekly add after that is a small, mechanical job the skill is written for Haiku to do.

The app does not depend on the loop. The same JSON can be pasted into `/import`, the Grok bot can be asked to emit it directly (the app serves a prompt for that), and a digest can be archived as markdown with hand-added items.

Two related repos exist. Read them for reuse if they are available to you. Leave their code alone. Everything needed from them is restated in this file.

**The fitness app** (`fitness-app/` in `nchua/projects`) is the only app Nick uses constantly. SwiftUI on the phone, FastAPI on Railway, SQLAlchemy 2, Alembic, Postgres, JWT via `python-jose`, pytest. Field Notes follows that backend. It does not become a screen in the fitness iOS app: workouts and weekly digests are different jobs, and this product is a web page he can open for a few minutes.

**Holocron** (`holocron/` in `nchua/projects`, also `https://github.com/nchua/holocron`) is a Python/FastAPI spaced-repetition system he does not open as a daily app. Its scheduler (`holocron/backend/app/core/fsrs.py`) uses four ratings (`forgot`, `struggled`, `got_it`, `easy`), a 0.9 retention target, and an 0.82 stability multiplier on the first schedule of an AI-written card. Unconfirmed AI output waits in an inbox. That repo has no people, companies, digest provenance, or phone review loop as first-class objects.

**speed-reader-v2** (private, Next.js) contributes concepts only: verbatim quotes, entity aliases, an installable PWA, and bearer tokens stored as SHA-256 hashes. Its stack and its closed tag vocabulary are not adopted.

**Assumptions:**

- Field Notes digests are short (a weekly chat message, not a book): at most 40 items.
- A single person uses the app. Tables still carry `user_id` so a later second user is a migration, not a rewrite.
- Nick uses an iPhone. The phone target is Safari and an iOS home-screen web app.
- "Today" and the daily review cap use America/Los_Angeles. Timestamps are stored as `timestamptz` in UTC.
- Field Notes tables live in their own Railway Postgres database. Nothing is written to the fitness database or the Holocron database.

**Prerequisites (Nick, before the build session starts):**

- An empty private GitHub repo `nchua/field-notes` exists and the build session is started on it. The implementer does not create repositories. If the session is not attached to `nchua/field-notes`, stop and say so; do not build inside `nchua/projects`.
- Nothing else. No Railway project, database, or secret is needed to build and test milestone 1.

## Scope

**In scope:**

- A new mobile-first web app with real sign-in for one allowlisted email.
- Ingestion of a digest as JSON (pasted in the app, or POSTed with a bearer token), with the digest's markdown optionally attached as the source text. A markdown-only archive path with hand-added items.
- A Claude Code skill, `field-notes-ingest`, with a small push script, and the documented local loop that runs it on Haiku.
- A ready-to-paste instruction block for the Field Notes bot that makes it emit the JSON contract, served by the app with the current watchlist filled in (the no-Claude alternative).
- A knowledge store: digests, items, sightings, entities, aliases, cards, reviews, per-entity memory.
- Entity resolution by normalized name and alias, manual merge, and suggested merges later. Faceted browse and person×company (or any pair) cross-links.
- Recall cards with citations, an FSRS queue, a daily cap, and a record of what Nick has accepted, marked known, reviewed, and caught up on.
- An installable PWA. Offline review is a later milestone.
- A README deploy runbook and `railway.toml`.

**Non-goals:**

- Any AI or model call from the deployed app: no Anthropic, OpenAI, or xAI SDK, no API key, no extraction of items from freeform markdown.
- Scheduling the loop on Nick's machine. The implementer writes the skill, the script, and the instructions; Nick sets up the schedule.
- Editing the Grok bot. The implementer writes the bot instructions as text; Nick pastes them into the bot. Wiring the bot to POST by itself is a follow-up.
- Deploying. The implementer does not create Railway projects, databases, or variables. Nick deploys from the runbook.
- Embedding this product inside the fitness iOS app, Holocron, or speed-reader-v2, or sharing any of their databases.
- RSVP reading, a knowledge-graph visualization, embeddings, multi-user sharing, a native iOS client, streaks, push notifications, and an AI-written "what changed" summary.
- Auto-merging two entities because the strings are similar. Similarity may suggest a merge. Only exact normalized match, alias match, and Nick's explicit merge join records.

## Where this app lives

This is a new app in a new repo. The fitness app, Holocron, and speed-reader-v2 stay as they are.

Reuse these parts, by porting behavior into the new repo rather than calling another service at runtime:

- The fitness backend shape: one FastAPI process, SQLAlchemy, Alembic, Railway Postgres, JWT, pytest. The phone UI is server-rendered HTML in that same process, so a review does not depend on a second app.
- The verbatim rule, as a concept: text that claims to quote the digest is trusted only when the digest contains it.
- The scheduler from Holocron, restated below as formulas. The formulas in this spec are the contract. Do not call the Holocron API.
- The inbox idea: content Nick has not confirmed stays pending.
- An installable PWA: a manifest and home-screen install first, a service worker only when offline review is built. Hashed bearer tokens (SHA-256, plaintext shown once) are the milestone 2 way to revoke an import token.

## User stories and flows

- As Nick, I want to paste Friday's digest and see it broken into linked items, so that the chat message becomes something I can come back to.
- As Nick, I want the same person and the same company to land on one page even when a later digest spells them differently, so that memory accumulates.
- As Nick, I want everything a person said about a company, so that I can review a relationship rather than a pile of weeks.
- As Nick, I want a few minutes of review on my phone, so that I actually remember the developments.
- As Nick, I want the app to show what changed since I last looked at a topic, so that old digests stay useful as the story moves.

### Flow: the local loop (the normal Friday path)

1. The Grok bot's digest lands as a file in the inbox folder on Nick's machine (`FIELD_NOTES_INBOX`).
2. On a schedule, or when Nick runs it, Claude Code starts in the `field-notes` checkout on Haiku and runs `/field-notes-ingest`.
3. For each file in the inbox, the skill fetches the watchlist, writes contract JSON with cards and the digest text as `source_markdown`, and runs the push script. The script POSTs it and prints the import response.
4. On 422 the skill reads the field errors, fixes the JSON, and tries again, at most twice. On success or `deduped` the file moves to `processed/`. A file that still fails moves to `failed/` with the error beside it.
5. Nick opens the app. Verified items are already accepted and their cards are in the queue. Anything the source check could not find is waiting in the Inbox.

### Flow: one-time bot setup (alternative to the loop)

1. Nick opens Settings and adds the people, companies, and topics he tracks to the watchlist (optional).
2. He opens `/bot-prompt`, taps Copy, and pastes the text into the Field Notes bot's instructions. From then on the bot ends each digest with one fenced `json` block.
3. When the watchlist changes he can copy the prompt again. Nothing breaks if he does not.

### Flow: paste a digest

1. Nick opens `/import` on his phone. The page has two text areas: "JSON from the bot" and "Digest text (optional)".
2. He pastes the JSON block. He may paste the whole chat message into the JSON box; the server takes the JSON object out of it (see Lenient paste). If he also pastes the digest text, it becomes the source the excerpts are checked against.
3. The server validates, stores the digest, items, entities, and cards, and redirects to `/digests/{id}`.
4. If the JSON is invalid, nothing is stored. The page shows each problem as a field path and a message (for example `items[3].speaker: required when kind is quote`) in a box he can copy back to the bot, and keeps what he pasted.
5. The digest page lists items, each pending, with its cards under it and the source text beside them when it was supplied. He accepts, marks known, or dismisses each item, or taps Accept all. Accepted items' active cards join the review queue. Known items stay in the library and their cards stay out of the queue.

### Flow: archive without JSON

1. Nick pastes only the digest text and submits. The digest is stored with zero items.
2. On the digest page he adds items by hand and writes cards on them.

### Flow: review on a phone

1. Today shows one primary button, "Review N", where N is the number of cards this session will show (at most the daily cap).
2. A card shows the question. He taps Show answer. The answer, the source link, and the digest title appear together.
3. He taps Again, Hard, Good, or Easy. The next card replaces it. Targets are at least 44px tall and sit in the thumb zone, above the safe-area inset.
4. The session ends when the queue slice is empty. Copy is "That's the session." If the cap hid more due cards, a secondary line says how many are scheduled after the cap.
5. The next day the schedule has moved: a new card rated Again is due again within hours, and a new card rated Good is not due until about two days have passed (fixture A).

### Flow: browse a cross-link

1. He opens Browse, chooses People, and taps a person.
2. The page lists items newest first, related entities, and a "New since you caught up" group when `caught_up_at` is set.
3. He taps a related company. The page is `/e/{person}?with={company}` and lists only items linked to both.
4. He taps Caught up. Items already listed leave the "new" group. A later digest that mentions the person puts new rows back in that group.

### Flow: JSON import by bearer (bot, later, or curl)

1. A client POSTs the JSON contract to `/api/imports` with `Authorization: Bearer $IMPORT_TOKEN`.
2. The server stores the digest, inserts items and cards, and links entities.
3. A second POST with the same `external_id` and the same body hash returns the existing digest and does not insert duplicates.
4. A second POST with the same `external_id` and a different body returns 409 and does not overwrite.

## Functional requirements

**Auth**

- **FR-1.** Sign-in is email plus password. It succeeds only for the email in `ALLOWED_EMAIL` (case-insensitive). Any other address is a 401 and creates no user. The address is never hardcoded. When zero users exist, the first sign-in with that email and a password of at least 12 characters creates the only account (passlib bcrypt). Later sign-ins check the hash.
- **FR-2.** Every HTML page and `/api` route requires the JWT cookie, except `GET /api/health`, `GET /signin`, `POST /signin`, everything under `/static/` (the browser fetches the manifest and icons without cookies), and `POST /api/imports` when the bearer token matches. An unauthenticated HTML request redirects to `/signin`; an unauthenticated `/api` request is 401.
- **FR-3.** Failed sign-ins are limited to 5 per 15 minutes per client IP (in-process counter; read the IP from `X-Forwarded-For` when present). The sixth is 429. A successful sign-in clears the counter.
- **FR-4.** The session cookie lasts 30 days and slides: when a valid token is more than 24 hours old, the response re-issues it. Sign out clears the cookie.
- **FR-5.** `python -m app.cli set-password` prompts for a new password (never takes it as an argument) and replaces the hash for the `ALLOWED_EMAIL` user. This is the only password reset.

**Ingestion**

- **FR-6.** A JSON import validates the whole payload against the contract first. Any schema error is 422 with `details: [{ "loc", "msg" }]` and stores nothing.
- **FR-7.** A valid import creates one digest, its items, their entity links, their cards, and one `item_sightings` row per item, in one transaction.
- **FR-8.** Import idempotency, in order: same `external_id` and same body hash returns the existing digest (`deduped: true`); same `external_id` and a different hash returns 409 `external_id_conflict` and does not overwrite; no `external_id` (or a new one) whose body hash already exists returns that existing digest with `deduped: true`. Identical content is one digest.
- **FR-9.** Source check. When the digest has `source_markdown`, each item's `excerpt_verified` is true when `match_key(excerpt)` is a substring of `match_key(source_markdown)`, else false. When the digest has no `source_markdown`, `excerpt_verified` is null. An item with `excerpt_verified = false` is stored as `pending` whatever `trust` says, and is marked "not found in digest text" in the UI. Nick accepting it is the override.
- **FR-10.** `quote_text` is kept only when `match_key(quote_text)` is a substring of `match_key(excerpt)`. A quote-kind item whose quote fails is stored as kind `development` with `quote_text` null, and counted in `quotes_demoted`.
- **FR-11.** A `url` is kept only when it parses as `http` or `https`. When the digest has `source_markdown` and the url string does not occur in it, the url is stored as null with `url_dropped = true`.
- **FR-12.** Items dedupe by `content_hash` per user. An item that hashes to an existing item (from an earlier digest, or earlier in the same payload) adds an `item_sightings` row, adds any entity links the existing item lacks, adds its cards only when the existing item has none, and does not create a second item or change the existing item's status. It is counted in `items_deduped`.
- **FR-13.** Each item may carry up to 3 cards. Each is stored with `ai_generated = true`, cites that item, and is `active` when it passes the grounding check and the item's `excerpt_verified` is not false; otherwise `pending`.
- **FR-14.** A markdown-only submission (no JSON) creates a digest with `source_markdown`, zero items, and status `empty`.
- **FR-15.** A digest page can add an item by hand (kind, headline, excerpt, optional body, url, quote, speaker, and entity name plus kind). When the digest has `source_markdown`, the excerpt must pass the FR-9 check or the request is 422. Hand-added items are stored `accepted`, `source = manual`.
- **FR-16.** Nick can write a recall card on an accepted item by hand. Hand-written cards are `active`, `ai_generated = false`, and skip the grounding check. They still cite that item.
- **FR-17.** Nick can delete a digest after a confirmation. Its sightings go. An item with no remaining sighting is deleted with its cards and their reviews. An item with another sighting survives and its `digest_id` moves to its earliest remaining sighting. The body hash is free to be imported again.
- **FR-18a.** `GET /api/watchlist` returns the watched entities as `[{ name, kind }]`, for a session or a valid bearer token.
- **FR-18b.** The repo ships the `field-notes-ingest` skill and `scripts/fn_push.py` as specified under Local ingest loop.
- **FR-18.** `/bot-prompt` renders the bot instructions in this spec as plain text with a Copy button, with the current watched entities appended as a name list.

**Entities and browse**

- **FR-19.** Entity resolution is exact: one lookup of the normalized name in `entity_aliases`, scoped to user and kind. A person and a company with the same string stay two rows. Fuzzy string similarity never links or merges on its own.
- **FR-20.** Manual merge of entity A into B (same kind, both unmerged): delete A's `item_entities` rows that would duplicate B's, repoint the rest and A's aliases onto B, set `A.merged_into_id = B`, delete A's `entity_memory` row and recompute B's, keep `B.watched = A.watched OR B.watched`. A's name remains an alias of B. `/e/{A's slug}` redirects to B's page.
- **FR-21.** Browse lists unmerged entities by kind that have at least one accepted or known item, or are watched. Counts are of accepted and known items only.
- **FR-22.** An entity page lists its accepted and known items as a timeline (newest `occurred_on`, falling back to `created_at`). An item with more than one sighting shows "mentioned again" with the later digest titles.
- **FR-23.** `/e/{slug}?with={otherSlug}` lists items linked to both entities. When one kind is `person` and the other is `company` or `topic`, the page offers a "said about" narrowing: the person is `speaker` or `subject`, and the other entity is `about` or `mentioned`.
- **FR-24.** Once `caught_up_at` is set, an entity page splits items into "new since you caught up" and older items. An item is new when it has a sighting with `seen_at` after `caught_up_at`. Caught up sets that timestamp to now. A review does not set it. While `caught_up_at` is null there is no "new" group.

**Triage and review**

- **FR-25.** Each item can be set to `accepted`, `known`, or `dismissed` at any time. Known items stay browsable. Dismissed items stay stored for dedupe and disappear from browse. Accept all sets every pending item on a digest to accepted.
- **FR-26.** A card is reviewable when its status is `active` and its cited item is `accepted`. The review UI renders the answer together with the cited item's url, source name, and digest title.
- **FR-27.** The review queue uses `user_settings.timezone`. Per local day it returns at most `daily_cap` reviews (default 15), of which at most `new_card_cap` (default 5) are first reviews of a card. Both counts are measured from the `reviews` table for the local day, so reloading the queue never grants more new cards. Due previously-reviewed cards fill the slice first.
- **FR-28.** Submitting a rating writes a `reviews` row and updates the card's difficulty, stability, retrievability, `last_reviewed_at`, `next_review_at`, `review_count`, and `lapse_count` using the scheduler in this spec, in one transaction with the card row locked. A repeat of the same `Idempotency-Key` returns the first response and changes nothing.
- **FR-29.** Nick can edit a card's front and back, activate a pending card, and suspend any card.
- **FR-30.** Today lists up to five accepted, known, or pending items created after `user_settings.last_seen_at`, with "and N more" linking to the latest digest. `last_seen_at` advances only when Nick opens a digest page or taps "Got it". Loading Today changes nothing.
- **FR-31.** `/inbox` lists pending items and pending cards across digests, with the same actions as the digest page.

**PWA**

- **FR-32.** The app is a portrait PWA (`display: standalone`, start URL `/`) with 192 and 512 icons, a 180px `apple-touch-icon`, `apple-mobile-web-app-capable`, `viewport-fit=cover`, and rating controls of at least 44px. Milestone 1 has no service worker.

**Later milestones**

- **FR-33.** Milestone 2: import tokens are rows (SHA-256 hash stored, plaintext shown once, revocable in Settings). `IMPORT_TOKEN` keeps working as a bootstrap.
- **FR-34.** Milestone 2: `pg_trgm` similarity at or above 0.72 and below 1.0 between two unmerged same-kind entities creates a merge *suggestion*. Nick confirms or dismisses it. Confirmation runs FR-20.
- **FR-35.** Milestone 2: a service worker caches the app shell and the current queue payload, queues review posts in IndexedDB, and replays them with the same `Idempotency-Key`. It does not cache any response that includes `source_markdown` or `raw_json`.
- **FR-36.** Milestone 3: templated connection cards. For an accepted quote item with a `speaker` person and at least one `about` entity, and no existing connection card for that item, create one card of type `connection`: front `What did {person} say about {entity}?`, back is the item's `quote_text` verbatim. No model is involved. `ai_generated = false`.
- **FR-37.** Milestone 3: the entity page shows a memory line (review count and mean retrievability from `entity_memory`).

## Technical design

### Architecture

One FastAPI process owns the HTML UI and the JSON routes. Railway Postgres is the only store. There are no outbound network calls. The browser never receives `IMPORT_TOKEN`.

```
phone / desktop browser                 Nick's machine: Claude Code (Haiku, subscription)
        │  JWT in an httpOnly cookie           │  field-notes-ingest skill + scripts/fn_push.py
        ▼                                      ▼
FastAPI (Railway)  ◄──────── bearer ──── POST /api/imports
        │
        └── SQLAlchemy ── Railway Postgres
```

Every ingestion path (pasted form, session JSON, bearer JSON, manual item) goes through `app/services/ingest.py`. One transaction per digest.

### Data model

UUIDs for every id. `timestamptz` for instants. `date` for `occurred_on` and digest period bounds. SQLAlchemy models under `app/models/`, migrations via Alembic. Postgres `CHECK` constraints mirror the value lists below. Every foreign key to `users`, `digests`, `items`, `entities`, and `cards` cascades on delete unless noted.

**users** — `id` uuid pk, `email` text unique on `lower(email)`, `password_hash` text, `created_at`. No OAuth tables and no server-side session table.

**user_settings** — `user_id` pk, `daily_cap int not null default 15`, `new_card_cap int not null default 5`, `timezone text not null default 'America/Los_Angeles'`, `last_seen_at timestamptz null`. Created with the user.

**digests**

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid pk | |
| user_id | uuid fk | |
| external_id | text null | idempotency key from the producer |
| title | text | |
| period_start, period_end | date null | |
| received_at | timestamptz | default now() |
| channel | text | `paste`, `bearer`, `manual` |
| raw_json | text null | the JSON object text as received, after lenient extraction |
| source_markdown | text null | the human digest text |
| body_hash | text | algorithm below |
| status | text | `imported` (has items from JSON) or `empty` |
| created_at | timestamptz | |

At least one of `raw_json` and `source_markdown` is non-null (check constraint). Unique (`user_id`, `external_id`) where `external_id` is not null. Unique (`user_id`, `body_hash`).

`body_hash` is sha256 hex of `canonical + "\n" + (source_markdown or "")`, where `canonical` is `json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` of the parsed payload with the `source_markdown` key removed, or the empty string for a markdown-only digest. Whitespace and key order in the paste do not change the hash.

**items**

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid pk | |
| user_id | uuid fk | |
| digest_id | uuid fk | first sighting. No cascade; FR-17 handles deletion |
| kind | text | `development`, `quote`, `link`, `paper` |
| headline | text | |
| body | text | one to three sentences; may paraphrase the excerpt. Empty string allowed |
| excerpt | text | as submitted |
| excerpt_verified | boolean null | FR-9 |
| quote_text | text null | |
| url | text null | http or https only |
| url_dropped | boolean | default false |
| source_name | text null | publication, "X", "arXiv" |
| occurred_on | date null | when it happened |
| content_hash | text | algorithm below |
| status | text | `pending`, `accepted`, `known`, `dismissed` |
| source | text | `json` or `manual` |
| created_at | timestamptz | |

Unique (`user_id`, `content_hash`).

`content_hash` is sha256 hex of a tagged basis string. The value part is passed through NFKC, whitespace collapse, trim, and lowercase:

1. `"quote:" + quote_text` when `quote_text` survived FR-10, else
2. `"url:" + url` (trailing `/` removed) when a url survived FR-11, else
3. `"text:" + headline + "\n" + excerpt`.

Quotes hash by their words so two quotes from one article stay two items; other items hash by url so the same story in a later week is one item with two sightings.

**item_sightings** — `item_id`, `digest_id`, `seen_at timestamptz`. Unique (`item_id`, `digest_id`). The first sighting inserts a row too. `on conflict do nothing`.

**entities**

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid pk | |
| user_id | uuid fk | |
| kind | text | `person`, `company`, `topic`, `theme`, `technology`, `claim` |
| name | text | display name, ≤ 140 characters |
| slug | text | unique per user |
| watched | boolean | default false |
| merged_into_id | uuid null | self fk, no cascade. Non-null rows are hidden |
| created_at | timestamptz | |

There is no `provisional` state. An entity created by an import is the same as one created in Settings, apart from `watched`.

**entity_aliases** — `id`, `user_id`, `kind`, `entity_id` fk, `alias text`, `normalized text`. Unique (`user_id`, `kind`, `normalized`). Every entity has at least one alias row: its own name, inserted when the entity is created. This table is the only uniqueness rule for entity names.

**item_entities** — pk (`item_id`, `entity_id`, `role`). `role` is `speaker`, `subject`, `mentioned`, or `about`.

**cards**

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid pk | |
| user_id | uuid fk | |
| type | text | `recall`, `connection`. Milestone 1 writes only `recall` |
| front, back | text | each 1–600 characters |
| status | text | `pending`, `active`, `suspended` |
| ai_generated | boolean | true for cards from JSON |
| difficulty | numeric | default 0.3, stored in [0.1, 0.9] |
| stability | numeric | default 0, days |
| retrievability | numeric | default 1. Recall probability at the moment of the last review |
| last_reviewed_at | timestamptz null | |
| next_review_at | timestamptz null | null means new |
| review_count, lapse_count | int | default 0 |
| created_at | timestamptz | |

Index (`user_id`, `status`, `next_review_at`).

**card_items** — pk (`card_id`, `item_id`). Every card has exactly one row in milestone 1. The service refuses to create a card without one.

**reviews** — `id`, `user_id`, `card_id` fk, `rating` (`forgot`, `struggled`, `got_it`, `easy`), `was_new boolean` (the card's `review_count` was 0), `elapsed_ms int null`, `reviewed_at`, `difficulty_after`, `stability_after`, `interval_days`, `idempotency_key text null`. Unique (`user_id`, `idempotency_key`) where the key is not null.

**entity_memory** — pk `entity_id`. `user_id`, `last_reviewed_at null`, `caught_up_at null`, `review_count int default 0`, `mean_retrievability numeric null`. Row created on first need. Updated when a review is submitted, for every unmerged entity linked to the cited item: increment `review_count`, set `last_reviewed_at`, recompute `mean_retrievability` as the average stored `retrievability` of reviewable cards (FR-26) with `review_count > 0` whose item links to that entity. `caught_up_at` changes only via the Caught up action.

**merge_suggestions** (milestone 2) — `id`, `user_id`, `from_entity_id`, `into_entity_id`, `score numeric`, `status` (`open`, `accepted`, `dismissed`). Unique open pair.

**import_tokens** (milestone 2) — `id`, `user_id`, `label`, `token_hash`, `created_at`, `revoked_at null`.

#### Text functions

```
match_key(s):                       # for the FR-9 and FR-10 checks
  s = NFKC(s)
  replace curly single and double quotes with straight ones
  remove the characters * _ ` (markdown emphasis)
  collapse every run of whitespace to one space, trim
  return s            # case is preserved

normalize(name, kind):              # for entity resolution
  s = NFKC(name), trim, collapse internal whitespace
  replace curly quotes with straight quotes
  if kind == company:
    t = s with one trailing suffix removed, case-insensitively:
        ", Inc." / " Inc." / " Inc" / " Corp." / " Corp" / " Corporation"
        / " Ltd." / " Ltd" / " LLC" / " Co." / " Co" / " Company"
    if t is not empty: s = t
  return lowercase(s)
```

Slug is the display name lowercased, non-alphanumeric ASCII runs replaced by `-`, trimmed of `-`. If that is empty (a name with no ASCII letters or digits), use `e-` plus the first 8 hex characters of the id. On collision append `-2`, `-3`, and so on.

#### Resolution

```
resolve(user_id, name, kind):
  if name is blank after trim: return nothing   # skip the link, keep the item
  norm = normalize(name, kind)
  alias = entity_aliases where (user_id, kind, normalized = norm)
  if alias:
    e = alias.entity; follow merged_into_id until unmerged; return e
  create entity(name = trimmed surface name)
  create alias(alias = surface name, normalized = norm)
  return it
```

A second surface form that normalizes to the same key ("NVIDIA" after "Nvidia") resolves through the existing alias and adds no row.

#### JSON contract (`schema_version: 1`)

The paste form and `POST /api/imports` accept:

```json
{
  "schema_version": 1,
  "external_id": "fn-2026-11-21",
  "title": "Field Notes — Nov 21, 2026",
  "period": { "start": "2026-11-14", "end": "2026-11-21" },
  "trust": false,
  "source_markdown": "optional: the full digest text",
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
      ],
      "cards": [
        { "front": "What did Ada Example say in the sample?", "back": "\"Sample quote for the fixture.\"" }
      ]
    }
  ]
}
```

Rules, enforced with Pydantic models in `app/services/contract.py`:

- `schema_version` must be `1`. `title` is required, 1–200 characters. `external_id` is optional, ≤ 100 characters. `period` is optional; each date is ISO `YYYY-MM-DD`.
- `items` has 1–40 entries. Per item: `kind` is one of the four kinds; `headline` 1–300 characters; `excerpt` 1–2000 characters; `body` optional, ≤ 1000; `quote_text` and `speaker` are both required when `kind` is `quote`; `entities` optional, ≤ 8, each with a non-empty `name` ≤ 140, a valid `kind`, and a valid `role`; `cards` optional, ≤ 3, each `front` and `back` 1–600 characters.
- `occurred_on` that does not parse as a date is stored as null. It is not an error. Unknown keys are ignored.
- When `speaker` is present, the server links it as a `person` with role `speaker` if the `entities` array did not already.
- `trust`: when present it wins. `true` inserts items as `accepted`, `false` as `pending`. When omitted, bearer imports default to `true` and session imports default to `false`. FR-9 overrides `trust` for unverified items.
- `source_markdown` in the payload and the form's "Digest text" box mean the same thing. When both are given, the form box wins.
- The whole request body is limited to 400,000 characters (413).

#### Lenient paste

The form path, and only the form path, accepts text around the JSON. `extract_json(text)`: trim; if the text contains a fenced block (```` ```json ```` or ```` ``` ````), take the first fenced block's contents; otherwise take the substring from the first `{` to the last `}`. Parse with `json.loads`. A parse failure is shown as `invalid_json` with the parser's line and column. `POST /api/imports` requires a clean JSON body.

#### Bot instructions

`app/web/bot_prompt.py` holds this text. `/bot-prompt` renders it with the watchlist appended. Commit the same text as `docs/bot-prompt.md`.

```text
After every digest, add one fenced json code block and nothing after it. It must be valid JSON
that follows this shape exactly:

{
  "schema_version": 1,
  "external_id": "fn-YYYY-MM-DD",            // the digest date
  "title": "Field Notes — <Mon D, YYYY>",
  "period": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" },
  "items": [
    {
      "kind": "development" | "quote" | "link" | "paper",
      "headline": "short headline",
      "body": "one sentence on why it matters",
      "excerpt": "copied word for word from the digest above",
      "quote_text": "the quoted words only (quote items)",
      "speaker": "full name of the person quoted (quote items)",
      "url": "the link from the digest",
      "source_name": "publication, X, arXiv, ...",
      "occurred_on": "YYYY-MM-DD",
      "entities": [ { "name": "...", "kind": "person" | "company" | "topic" | "theme" | "technology" | "claim",
                      "role": "speaker" | "subject" | "about" | "mentioned" } ],
      "cards": [ { "front": "a question", "back": "the answer, one or two sentences" } ]
    }
  ]
}

Rules:
- One item per development, quote, link, or paper in the digest. At most 40.
- "excerpt" must be copied exactly from the digest text you just wrote. Do not reword it.
- "quote_text" must appear inside "excerpt". A quote item always has "speaker".
- "url" must be a link that appears in the digest. Do not invent links.
- Entities: always list the people and companies involved. Add a topic, theme, or technology only
  when the item is centrally about it. Use full names ("Jensen Huang", not "Jensen"). Use the same
  spelling every week.
- Cards: write 1 or 2 per item. The question must be answerable from that item's excerpt alone, and
  the answer must use the excerpt's own words where it can. Do not add outside facts.
- Use straight double quotes and escape any double quote inside a string as \". No comments, no
  trailing commas. (The // comment above is explanation; do not output it.)

Names I track. When an item is about the same real-world person, company, or topic, use exactly
this spelling:
<one "name (kind)" per line, from the watchlist; omit this paragraph when the watchlist is empty>
```

#### Local ingest loop

This runs on Nick's machine, never on the server. It is the only place a model touches a digest.

**`scripts/fn_push.py`** — Python standard library only (`urllib`, `json`, `argparse`), so it runs without the app's virtualenv.

- `fn_push.py watchlist` prints the JSON from `GET /api/watchlist`.
- `fn_push.py push <file.json>` POSTs the file to `/api/imports` and prints the response body. Exit 0 on 200 (including `deduped: true`), 2 on 422 (prints `details`), 3 on 409, 1 on anything else.
- Reads `FIELD_NOTES_URL` and `FIELD_NOTES_IMPORT_TOKEN` from the environment, falling back to a git-ignored `.env.local` in the repo root. Never prints the token.

**`.claude/skills/field-notes-ingest/SKILL.md`** — a project skill with `name` and `description` front matter, written as short numbered steps a small model can follow without judgment calls:

1. Inbox is `$FIELD_NOTES_INBOX`, default `~/field-notes/inbox`. Take every `.json`, `.md`, and `.txt` file directly in it, oldest first. If there are none, say so and stop.
2. Run `python scripts/fn_push.py watchlist` once.
3. For each file: read it. If it is JSON, the digest is whatever text fields it holds; if it already has `schema_version` and `items`, keep its items and only fill what is missing. Otherwise treat the file's text as the digest.
4. Write `<name>.contract.json` in a scratch folder, following the contract and the item, entity, and card rules from the bot instructions (the skill restates them in full; it does not point at another file). Set `source_markdown` to the digest text exactly as read. Set `external_id` to `fn-` plus the digest date, taken from the digest or else the file's date. Do not set `trust`.
5. Run `python scripts/fn_push.py push <name>.contract.json`.
6. Exit 0: move the original to `inbox/processed/`. Exit 2: fix exactly the fields named in `details` and push again, at most twice more. Exit 3, or still failing: move the original to `inbox/failed/` and write the last error to `<name>.error.txt` beside it.
7. Finish with one line per file: name, outcome, items created, items unverified.

The skill never edits the app's code or database and never calls any URL other than through `fn_push.py`.

**Running it.** The README documents, and the implementer checks each command against the installed Claude Code's own help before writing it down:

- By hand: open Claude Code in the checkout with Haiku selected and run `/field-notes-ingest`.
- Unattended: a scheduled job (launchd or cron) that runs Claude Code non-interactively in the checkout with the Haiku model and the prompt `/field-notes-ingest`, with the two tools it needs (file read/write in the inbox and scratch folder, and running `scripts/fn_push.py`) pre-allowed in `.claude/settings.json`.
- In an open session: `/loop 1h /field-notes-ingest`.

All three use Nick's signed-in Claude Code, so the work is covered by his subscription. No `ANTHROPIC_API_KEY` is set anywhere.

#### Card grounding check

Deterministic, no model. Words are `[a-z0-9]+` runs of length ≥ 4 after lowercasing. Let `S` be the word set of the item's `headline + " " + excerpt + " " + (quote_text or "")`, and `B` the list of words in the card's `back`. The card passes when `B` is non-empty, at least one word of `B` is in `S`, and at least 40% of the words in `B` are in `S`. Pass and `excerpt_verified` is not false → `active`. Otherwise → `pending`.

The review screen shows `back`, then the cited url, source name, and digest title. The back is not the citation by itself.

#### Scheduler

Implement these functions exactly in `app/services/fsrs.py`, as pure functions with no I/O. `difficulty` is stored in `[0.1, 0.9]`.

Weights: `w0=0.4`, `w1=0.6`, `w2=2.4`, `w3=5.8`, `w4=4.93`, `w5=0.94`, `w6=0.86`, `w7=0.01`, `w8=1.49`, `w9=0.14`, `w10=0.94`, `w11=2.18`, `w12=0.05`, `w13=0.34`, `w14=1.26`, `w15=0.29`, `w16=0.2`.

Grades: `forgot=1`, `struggled=2`, `got_it=3`, `easy=4`. Target retention `0.9`. `AI_CARD_STABILITY_FACTOR = 0.82`.

- `initial_difficulty(grade) = clamp((w4 - (grade - 3) * w5) / 10, 0.1, 0.9)`
- `initial_stability(grade) = w[grade - 1]`
- `retrievability(stability, elapsed_days) = (1 + elapsed_days / (9 * stability)) ** -1`, or 0 when stability ≤ 0
- `next_difficulty(d, grade) = clamp(w6 * initial_difficulty(grade) + (1 - w6) * (d - w7 * (grade - 3)), 0.1, 0.9)`
- `interval_days = clamp(9 * stability * (0.9 ** -1 - 1), 1/1440, 365)`
- `next_review_at = now + interval_days`

First review (`review_count == 0` or stored `stability <= 0`): ignore the stored values. `d = initial_difficulty(grade)`, `s = initial_stability(grade)`, multiplied by 0.82 when `ai_generated`. `R = 1.0`.

Later reviews, in this order:

1. `elapsed_days = (now - last_reviewed_at)` in days. `R = retrievability(stability, elapsed_days)`.
2. `d' = next_difficulty(d, grade)`. **The stability formulas below use the updated `d'`, not the stored `d`.**
3. Success (`grade ≥ 2`): `hard = w9` when grade is 2, else `1`. `growth = exp(w8) * (11 - d' * 10) * stability ** (-w10) * (exp(w11 * (1 - R)) - 1) * hard + 1`. `s' = max(0.1, stability * growth)`. There is no easy bonus.
4. Failure (`grade = 1`): `new = w12 * (d' * 10) ** (-w13) * ((stability + 1) ** w14 - 1) * exp(w15 * (1 - R))`. `s' = max(w16, min(new, stability))`.

Persist difficulty, stability, and retrievability (`R`) rounded to 4 decimal places, and `interval_days` rounded to 2. `review_count` increments on every review. `lapse_count` increments when the rating is `forgot`.

Tests assert the rounded tuple `(difficulty, stability, retrievability, interval_days)`. These values were computed from the formulas above:

| Case | rating | review_count | d in | s in | elapsed days | ai | d | s | R | interval |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | got_it | 0 | 0 | 0 | 0 | true | 0.493 | 1.968 | 1.0 | 1.97 |
| B | forgot | 0 | 0 | 0 | 0 | true | 0.681 | 0.328 | 1.0 | 0.33 |
| C | easy | 0 | 0 | 0 | 0 | false | 0.399 | 5.8 | 1.0 | 5.8 |
| D | got_it | 1 | 0.493 | 1.968 | 2 | true | 0.493 | 8.9118 | 0.8985 | 8.91 |
| E | forgot | 1 | 0.493 | 1.968 | 2 | true | 0.6575 | 0.2 | 0.8985 | 0.2 |
| F | struggled | 1 | 0.493 | 1.968 | 2 | true | 0.5752 | 2.8084 | 0.8985 | 2.81 |
| G | easy | 1 | 0.493 | 1.968 | 2 | true | 0.4108 | 9.8526 | 0.8985 | 9.85 |

Cases F and G distinguish the updated difficulty from the stored one (the stored one would give 2.9401 and 8.9118).

#### Queue

Local day bounds come from `user_settings.timezone` (`zoneinfo`).

```
reviews_today      = count(reviews with reviewed_at in the local day)
new_today          = count(of those, was_new = true)
remaining          = max(0, daily_cap - reviews_today)
new_remaining      = max(0, new_card_cap - new_today)

reviewable         = cards with status = active whose cited item is accepted
due_seen           = reviewable, review_count > 0, next_review_at <= now(),
                     ordered by next_review_at, then created_at
due_new            = reviewable, review_count = 0, ordered by created_at

slice              = first `remaining` of due_seen
slice             += first min(new_remaining, remaining - len(slice)) of due_new
remaining_due      = len(due_seen) + len(due_new) - len(slice)
```

Reviewing a card that is not in today's slice is allowed (the endpoint does not check due state); it still counts toward the caps.

### APIs and interfaces

Cookie session unless noted. JSON in and out. Errors: `{ "error": "short_code" }`, plus `details` on 422, with 400, 401, 404, 409, 413, 422, or 429.

| Method and path | Auth | Behavior |
| --- | --- | --- |
| `GET /api/health` | none | `{ "ok": true }` |
| `POST /api/imports` | bearer or session | JSON contract. Bearer acts as the allowlisted user; 409 `no_user` if that user has never signed in. Response below. |
| `POST /api/imports/markdown` | session | `{ "markdown", "title?", "external_id?" }`. Archive only (FR-14). Title defaults to the first `# ` heading, else `Field Notes — {local date}`. |
| `GET /api/digests` | session | Newest first. `{ id, title, received_at, status, item_count, pending_count }`. No source text in the list. |
| `GET /api/digests/:id` | session | Digest plus items (`id`, `kind`, `headline`, `body`, `status`, `url`, `excerpt`, `excerpt_verified`, `quote_text`, `entities: [{ slug, name, kind, role }]`, `cards: [{ id, front, back, status }]`). Includes `source_markdown` here only. |
| `DELETE /api/digests/:id` | session | FR-17. |
| `POST /api/digests/:id/items` | session | Manual item (FR-15). |
| `POST /api/digests/:id/accept` | session | Sets every pending item on the digest to accepted. |
| `PATCH /api/items/:id` | session | `{ "status": "accepted" \| "known" \| "dismissed" }`. |
| `GET /api/entities?kind=&q=` | session | Unmerged entities per FR-21. Optional `q` matches name or alias, case-insensitive, limit 8 when `q` is set (and then ignores the FR-21 visibility filter, so merge search finds everything). `{ id, name, slug, kind, watched, item_count }`. |
| `GET /api/entities/:slug?with=` | session | Entity, aliases, items (same item shape as the digest GET, plus `roles`), related entities (top 8 by co-occurrence on accepted and known items), and the ids of items that are new since `caught_up_at`. |
| `POST /api/entities` | session | `{ name, kind, watched? }`. Resolves or creates. Used by Settings. |
| `PATCH /api/entities/:slug` | session | `{ watched }`. |
| `POST /api/entities/merge` | session | `{ "from_id", "into_id" }`. 422 when kinds differ, ids match, or either is already merged. |
| `POST /api/entities/:slug/caught-up` | session | Sets `caught_up_at = now()`. |
| `POST /api/cards` | session | Manual card `{ item_id, front, back }` (FR-16). 422 when the item is not accepted. |
| `PATCH /api/cards/:id` | session | `{ status?: "active" \| "suspended", front?, back? }`. |
| `GET /api/review/queue` | session | `{ cards: [{ id, front, back, type, item: { url, source_name, digest_title } }], remaining_due }`. `back` is included so milestone 2 can cache one payload; the client hides it until Show answer. |
| `POST /api/reviews` | session | `{ card_id, rating, elapsed_ms? }` plus optional header `Idempotency-Key` (the client sends a fresh UUID per card shown). Returns `{ next_review_at, interval_days }`. 409 when the card is not reviewable. |
| `GET /api/inbox` | session | Pending items and pending cards. |
| `GET /api/watchlist` | bearer or session | `[{ name, kind }]` for watched, unmerged entities. |
| `POST /api/seen` | session | Sets `last_seen_at = now()` ("Got it"). |
| `PATCH /api/settings` | session | `{ daily_cap?, new_card_cap? }`, each 1–50, else 422. |

Import response:

```json
{
  "digest_id": "uuid",
  "deduped": false,
  "items_created": 12,
  "items_deduped": 2,
  "items_unverified": 1,
  "quotes_demoted": 0,
  "urls_dropped": 0,
  "cards_active": 20,
  "cards_pending": 3,
  "entities_created": 5,
  "entities_linked": 18
}
```

HTML routes: `GET /` (Today), `/signin`, `/import`, `/digests`, `/digests/{id}`, `/browse?kind=`, `/e/{slug}`, `/review`, `/inbox`, `/settings`, `/bot-prompt`, `POST /signout`. HTML forms post to thin handlers (for example `POST /import`, `POST /digests/{id}/items`) that call the same service functions as the API routes and redirect. Forms cannot send PATCH or DELETE; give those actions POST form handlers.

Bearer comparison hashes both sides with SHA-256 and compares the digests with `hmac.compare_digest`. When `IMPORT_TOKEN` is unset or shorter than 32 characters the bearer path is disabled and always 401. Never log the header. The session cookie is named `fieldnotes`, `httponly`, `samesite=lax`, `path=/`, `secure` when `APP_URL` starts with `https`, and holds a JWT (`HS256`, `python-jose`, signed with `JWT_SECRET_KEY`, claims `sub` = user id, `iat`, `exp`).

### Key components

| Piece | Responsibility |
| --- | --- |
| `app/core/config.py`, `database.py` | Settings from env (pydantic-settings), engine and session. |
| `app/core/security.py`, `app/api/auth.py` | Password hashing, JWT, sign-in limiter, `get_current_user` from the cookie. |
| `app/cli.py` | `set-password`. |
| `app/models/` | SQLAlchemy tables and check constraints. |
| `app/services/fsrs.py` | Pure scheduler. |
| `app/services/text.py` | `match_key`, `normalize`, slug, content hash, body hash, `extract_json`. |
| `app/services/contract.py` | Pydantic models for the JSON contract. |
| `app/services/entities.py` | Resolution and merge. |
| `app/services/ingest.py` | The one insert path. Transaction per digest. |
| `app/services/cards.py` | Grounding check, card creation. |
| `app/services/queue.py`, `review.py` | Cap math, due ordering, rating submission, `entity_memory`. |
| `app/web/bot_prompt.py` | Bot instructions text and watchlist rendering. |
| `app/web/templates/today.html` | Review button, up to five new items, link to the latest digest, "Got it". |
| `app/web/templates/review.html`, `app/web/static/review.js` | One card, show-answer, four ratings. The page fetches the JSON queue and posts ratings so the next card does not reload. Keys 1–4 map to Again/Hard/Good/Easy; space shows the answer. |
| `app/web/templates/import.html` | Two text areas, validation errors in a copyable box. |
| `app/web/templates/digest.html` | Items with their cards, source text, accept / known / dismiss, Accept all, add item, write card, delete digest. |
| `app/web/templates/browse.html` | Kind tabs: People, Companies, Topics, Themes, Tech, Claims. |
| `app/web/templates/entity.html` | Timeline, related entities, `?with=`, Caught up, Watch, Merge into (search by name, same kind). |
| `app/web/templates/inbox.html` | Pending items and cards. |
| `app/web/templates/settings.html` | Watchlist add and remove, caps, link to bot prompt, sign out. |
| `app/web/static/manifest.webmanifest` | PWA manifest. |

UI is a single column under 768px. Body text at least 16px. The rating bar is sticky to the bottom with `env(safe-area-inset-bottom)`. Desktop may show the digest list beside the detail. No component library and no Holocron or speed-reader visual system: system font, near-black background `#111111`, light text, one accent for the primary button. One CSS file. This is a utility for a five-minute session.

### Files to create or change

Create them in `nchua/field-notes`. Nothing in `nchua/projects` changes.

| Path | Change |
| --- | --- |
| `requirements.txt`, `app/main.py` | FastAPI app. Python 3.12. |
| `railway.toml`, `Procfile` | Start command below. |
| `.env.example` | Names only, empty values. |
| `README.md` | Run, test, migrate, and the deploy runbook. |
| `docs/bot-prompt.md` | The bot instructions. |
| `.claude/skills/field-notes-ingest/SKILL.md`, `.claude/settings.json` | The ingest skill and its pre-allowed tools. |
| `scripts/fn_push.py` | Push script, standard library only. |
| `.gitignore` | Includes `.env`, `.env.local`. |
| `alembic.ini`, `alembic/` | One migration for the milestone 1 tables. |
| `app/core/`, `app/models/`, `app/services/`, `app/api/`, `app/cli.py` | As in Key components. |
| `app/web/templates/`, `app/web/static/app.css`, `review.js` | Screens in Key components. |
| `app/web/static/manifest.webmanifest`, `icon-192.png`, `icon-512.png`, `apple-touch-icon.png` | A `#111111` square with light "FN" lettering is enough. Generate the PNGs once with any tool and commit them; do not add an image library to `requirements.txt`. |
| `tests/` | `conftest.py`, `test_fsrs.py`, `test_text.py`, `test_import.py`, `test_entities.py`, `test_queue.py`, `test_auth.py`, `test_pages.py`, `fixtures/digest.json`, `fixtures/digest.md`. |

### Constraints

- Environment variables: `DATABASE_URL`, `JWT_SECRET_KEY`, `ALLOWED_EMAIL`, `IMPORT_TOKEN`, `APP_URL`, and `TEST_DATABASE_URL` for tests. Never commit values. The app refuses to start when `DATABASE_URL`, `JWT_SECRET_KEY`, or `ALLOWED_EMAIL` is missing. There is no model API key.
- Fixtures and examples use placeholder people and companies and `test@example.com`. No real email address, password, or token in the repo.
- Templates use Jinja2 autoescaping everywhere. Digest text, headlines, quotes, and card text are rendered as text, never as HTML and never through `|safe`. `source_markdown` is shown in a `white-space: pre-wrap` block, not rendered as markdown. A url is rendered as a link only when its scheme is `http` or `https`, with `rel="noopener noreferrer"`.
- Full digest text is allowed in the database (it is the product) and in the single-digest GET for the signed-in user. It stays out of list endpoints and out of logs. Do not log request bodies, urls, or the Authorization header.
- Ratings on screen are Again / Hard / Good / Easy and map to `forgot` / `struggled` / `got_it` / `easy`.
- No streaks. The home screen does not lead with an overdue count. The queue button shows how many cards this session includes.

### Edge cases and failure behavior

- Invalid JSON or a schema error: nothing stored; the form re-renders with the pasted text and the error list.
- Empty submission (both boxes blank): 422 `empty`.
- Excerpt not found in the supplied digest text: item stored `pending` with `excerpt_verified = false`, cards `pending`.
- Same quote, or the same non-quote url, arriving in a second week: one item, two sightings. The timeline shows the later digest under "mentioned again". If Nick had dismissed the item it stays dismissed.
- Two items in one payload with the same hash: the second is counted in `items_deduped`.
- Every item in a payload dedupes to existing items: the digest is still stored (`imported`), with sightings and zero new items.
- Merge target is itself merged, or kinds differ: 422.
- Review idempotency replay: same JSON as the first response, no second `reviews` row, no second schedule.
- Queue when nothing is due: `{ "cards": [], "remaining_due": 0 }`. Today copy: "Nothing due." with a link to the latest digest.
- Cap already spent today: same empty queue, `remaining_due` reports how many reviewable cards are due after the cap.
- Item moved from accepted to known or dismissed: its cards leave the queue (FR-26) and keep their schedule; accepting it again brings them back.
- Entity name blank after trim: skip that entity link, keep the item.
- Bearer import before the first sign-in: 409 `no_user`.
- Deleting a digest whose items have reviews: the confirmation says how many reviewed cards will be removed.

## Tech stack and dependencies

| Layer | Choice |
| --- | --- |
| App | FastAPI, Jinja2 templates, one CSS file, one small `review.js` |
| Data | Railway Postgres, SQLAlchemy 2, Alembic |
| Auth | Email and password, bcrypt, JWT in an httpOnly cookie (`python-jose`) |
| AI | None |
| Tests | pytest against Postgres |
| Host | Railway for the app and for Postgres (Nick deploys) |

`requirements.txt`, pinned to the fitness backend's versions where it pins the library:

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy==2.0.25
alembic==1.13.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==4.0.1
python-multipart==0.0.6
pydantic==2.5.3
pydantic-settings==2.1.0
psycopg2-binary==2.9.9
jinja2
tzdata
pytest==7.4.4
httpx==0.26.0
```

Pin `jinja2` and `tzdata` to whatever resolves at build time. `bcrypt==4.0.1` is pinned because passlib 1.7.4 fails with newer bcrypt releases. `python-multipart` is needed for HTML forms. `tzdata` is needed because the Railway image may not ship the IANA zone database. Nothing else is added in milestone 1. No Anthropic SDK, no markdown library, no image library.

**Tests use Postgres, not SQLite.** This differs from the fitness backend on purpose: the schema relies on partial unique indexes, `timestamptz`, `ON CONFLICT`, and row locks. `tests/conftest.py` reads `TEST_DATABASE_URL` (default `postgresql://postgres@localhost:5432/fieldnotes_test`), creates the schema with `alembic upgrade head` once per session, and wraps each test in a transaction that rolls back. If no Postgres is reachable, start a local one (Postgres 16 is typically installed on the build machine; `pg_ctl` or the system service) before concluding tests cannot run. Do not rewrite the schema to fit SQLite.

`pg_trgm` is created in the milestone 2 migration (`CREATE EXTENSION IF NOT EXISTS pg_trgm`). No pgvector.

**Deployment (documented, not performed).** `railway.toml`:

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/api/health"
healthcheckTimeout = 100
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

The README runbook covers: create a Railway project from `nchua/field-notes`, add a Postgres service, set the five variables (generate `JWT_SECRET_KEY` and `IMPORT_TOKEN` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`), deploy, then **sign in immediately** to claim the single account, then open `/bot-prompt` and paste it into the Field Notes bot. Accept `DATABASE_URL` values that begin `postgres://` by rewriting the scheme to `postgresql://`.

## Implementation plan

Build milestone 1 to completion and stop. It is useful with no later milestone. Milestones 2 and 3 start only after milestone 1's acceptance criteria pass and Nick asks for them.

### Milestone 1 — Library, grouping, and review

**Goal:** Nick can paste the bot's JSON, browse items by person and company (including a cross-link), and review cited cards on his phone. Data is still there the next day.

**Steps:**

1. Confirm the session is on `nchua/field-notes`. Scaffold the FastAPI app, config, database session, Alembic, pytest with the Postgres fixture, `.env.example`, `railway.toml`, and `GET /api/health`.
2. Add the models and the first migration (every table except `merge_suggestions` and `import_tokens`).
3. Implement `app/services/fsrs.py` and land the seven fixtures.
4. Implement `text.py` (match key, normalize, slug, hashes, lenient extraction) with table-driven tests.
5. Add sign-in, the allowlist, the limiter, the sliding JWT cookie, sign out, and `app.cli set-password`.
6. Implement the contract models, entity resolution, the grounding check, and `ingest.py`, with tests for idempotency, 409, dedupe, the source check, quote demotion, and url rules.
7. Add the import routes (form, session JSON, bearer JSON, markdown archive), manual items, manual cards, and digest delete.
8. Implement the queue, rating submission with idempotency, and `entity_memory`.
9. Build the pages: Today, Import, digest list and detail, Browse, entity page with `?with=` and merge, Review, Inbox, Settings, bot prompt.
10. Add the manifest, icons, iOS meta tags, safe-area padding, and 44px rating targets.
11. Write `scripts/fn_push.py`, the `field-notes-ingest` skill, and `GET /api/watchlist`. Run the skill once yourself against the local server with `tests/fixtures/digest.md` in a temporary inbox.
12. Write the README (run, test, deploy runbook, local loop setup) and `docs/bot-prompt.md`.
13. Run the test plan below, including the manual pass in a 390×844 browser viewport against a locally running server.

Commit after each step. Push to the branch the session was given.

**Acceptance criteria:**

- [ ] FR-1 through FR-32 pass, including FR-18a and FR-18b.
- [ ] `tests/fixtures/digest.json` round-trips through `POST /api/imports` twice: the second response has `deduped: true` and the item count is unchanged. Re-serializing the fixture with different whitespace and key order also returns `deduped: true`.
- [ ] Importing the JSON fixture together with `tests/fixtures/digest.md`, where one item's excerpt is not in the markdown, with `trust: true`: that item is `pending` with `excerpt_verified = false`, its cards are `pending`, and every other item is `accepted`.
- [ ] The form path accepts the fixture wrapped in a fenced block with prose before and after.
- [ ] A payload missing `speaker` on a quote item returns 422 with a `details` entry naming `items[n].speaker`, and stores nothing.
- [ ] Two items that mention "NVIDIA" and "Nvidia" share one company entity. "Nvidia Inc." then "Nvidia", and "Nvidia" then "Nvidia Inc.", each share one entity. "Jensen" and "Jensen Huang" stay two entities until a manual merge; after the merge there is one page, the old name is an alias, and the old slug redirects.
- [ ] `/e/{person}?with={company}` returns only shared items.
- [ ] Two different quotes with the same url in one payload are two items.
- [ ] A first review rated Good on a JSON card yields interval 1.97 days (fixture A). The card is not in the queue again until that interval elapses.
- [ ] With `new_card_cap = 5` and 12 new cards, reviewing 5 and reloading the queue returns no new cards for the rest of the local day.
- [ ] The review flow works at a 390px viewport: Show answer, then a rating, then the next card, without horizontal scroll.
- [ ] `python scripts/fn_push.py push tests/fixtures/digest.json` against a local server imports the fixture and exits 0; run again it prints `deduped: true` and exits 0; with a quote item's `speaker` removed it exits 2 and prints the field path.
- [ ] With `tests/fixtures/digest.md` in a temporary inbox, running the skill leaves the file in `processed/`, a digest in the app with `source_markdown` set, and at least one active card.
- [ ] The manifest, icons, and `/static/app.css` load without a session cookie.
- [ ] `grep -ri "anthropic\|openai\|xai" requirements.txt app/` finds nothing.
- [ ] `pytest -q` passes against Postgres. The app boots with `uvicorn app.main:app`.

### Milestone 2 — Tokens, suggestions, offline

**Goal:** Import tokens can be revoked, near-duplicate entities surface as suggestions, and a review started on a train finishes offline and syncs.

**Steps:**

1. Add `import_tokens` with create and revoke in Settings (FR-33). Document a curl example the bot or an iOS Shortcut can use.
2. Add `pg_trgm` and `merge_suggestions`. Compute suggestions for entities created by each import. Accept runs FR-20.
3. Add a service worker that caches the shell and the queue JSON, stores review posts in IndexedDB with the idempotency key, and replays when online. Exclude any URL that can return `source_markdown` or `raw_json`.

**Acceptance criteria:**

- [ ] FR-33, FR-34, and FR-35 pass.
- [ ] A revoked token returns 401. A bearer retry with the same `external_id` and body does not double items.
- [ ] An offline rating syncs exactly once when the network returns.
- [ ] A suggestion never merges until Nick confirms it.

### Milestone 3 — Connections and memory line

**Goal:** Review can ask what a person said about a company, with the quote as the answer.

**Steps:**

1. When a quote item becomes accepted, create the templated connection card in FR-36 (one per item, for the first `about` entity). Backfill for already-accepted quote items in a migration-time script.
2. Show the memory line on the entity page (FR-37).

**Acceptance criteria:**

- [ ] FR-36 and FR-37 pass.
- [ ] A connection card's back equals the item's `quote_text` exactly.
- [ ] Accepting the same item twice does not create a second connection card.

## Testing plan

- **Automated:** `pytest -q` against Postgres (`TEST_DATABASE_URL`). No network access is needed by any test.
- **Cases:**
  - FR-9 / FR-10 / FR-11 — `match_key` table (curly quotes, markdown emphasis, line wraps); excerpt found and not found; quote not inside excerpt demoted; url with a `javascript:` scheme dropped; url absent from the digest text dropped.
  - FR-6 / FR-8 / FR-12 — schema errors store nothing; same `external_id` and hash returns `deduped`; different hash returns 409; whitespace-only differences dedupe; same quote in two digests yields one item and two sightings; in-payload collision.
  - FR-13 — grounding pass, fail, and a back with no words of length ≥ 4.
  - FR-17 — delete a digest: sole-sighting items go with cards and reviews; shared items survive and repoint.
  - FR-19 / FR-20 — normalization table (case, each company suffix in both orders, a company named only "Co", curly quotes, a non-ASCII name's slug) and merge repointing with a duplicate `item_entities` row.
  - FR-24 / FR-30 — caught-up split after a later sighting; Today does not advance `last_seen_at` on load.
  - FR-27 / FR-28 — queue caps across a UTC day boundary in America/Los_Angeles; new-card cap after reload; idempotent replay; the seven scheduler fixtures.
  - FR-1 through FR-4 — sign-in rejects a second email and creates no user; sixth failed attempt is 429; a token older than 24 hours is re-issued; bearer route returns 401 on a bad token and when `IMPORT_TOKEN` is short; `/static/` is public; an HTML page redirects to `/signin`.
  - `fn_push.py` — exit codes for 200, deduped, 422, 409, and 401 against the test app; the token never appears in its output.
  - Pages — each HTML route returns 200 for a signed-in user with fixture data, and a headline containing `<script>` is escaped.
- **Manual:** Run the server locally. At a 390×844 viewport, paste the fixture, accept two items, finish a three-card session, reload, and confirm the next due time moved. Open a person×company cross-link. Merge two entities. Confirm server logs for that session contain no digest sentence and no token. Home-screen install on a real phone is Nick's check after deploy.

## Risks

- **The loop does not run, or Haiku writes poor JSON.** The machine is asleep, Claude Code is signed out, or the small model drops a field. **Mitigation:** the app never depends on the loop (paste and manual paths remain); the skill is short numbered steps with a bounded fix-and-retry on field errors; failures land in `failed/` with the error; Nick can rerun the same file on a larger model.
- **Pasted JSON drifts or is invalid.** A chat reply may add commentary, break escaping, or omit fields. **Mitigation:** lenient paste extraction, whole-payload validation with field-path errors Nick can paste back to the bot, unknown keys ignored, and the markdown archive plus manual items as a fallback that needs no JSON.
- **The model invents an excerpt, a link, or a card fact.** **Mitigation:** the skill always sends the digest text, and when it is supplied, unverified items are held pending and absent urls are dropped; the grounding check holds cards that share too few words with the excerpt; the source link is always on the answer side. Without the digest text there is no check, and the UI says "not checked against digest text" on those digests.
- **Entity spellings vary week to week.** **Mitigation:** the bot prompt carries the watchlist spellings; exact-match only, so a variation creates a second entity rather than a wrong merge; manual merge fixes it permanently through the alias.
- **Two people share a normalized name.** **Mitigation:** no fuzzy auto-merge; kind-scoped exact match.
- **First-sign-in account claim.** Before Nick signs in, anyone who knows the allowlisted address could set the password. **Mitigation:** the runbook says to sign in immediately after the first deploy; `set-password` recovers the account.
- **Import token in a chat log or shortcut.** **Mitigation:** hashed compare, minimum length, never logged, revocable rows in milestone 2.
- **Offline cache leaks a digest.** **Mitigation:** milestone 1 has no worker; milestone 2's worker excludes source-text routes.

## Open questions

All resolved on 2026-11-22. Build as written.

- **Q1.** Repo and hosting? **Resolved (Nick):** Nick creates the empty private repo `nchua/field-notes` and starts the build session on it. Railway app plus a new Railway Postgres, not the fitness database.
- **Q2.** Which email is allowlisted? **Resolved:** whatever Nick puts in `ALLOWED_EMAIL`. No address in the source.
- **Q3.** Does the app call a model? **Resolved (Nick):** no. A local Claude Code loop on his subscription runs the `field-notes-ingest` skill, on Haiku once the app exists, and pushes JSON to the app. The app has no model key.
- **Q4.** Where do digest files come from? **Resolved:** a local inbox folder, `FIELD_NOTES_INBOX` (default `~/field-notes/inbox`), holding whatever the Grok bot wrote, JSON or markdown. Nick points the variable at the real folder.
- **Q4a.** Does the Grok bot change? **Resolved:** not required. The bot prompt stays as an optional path for getting JSON without Claude.
- **Q5.** Card voice? **Resolved:** recall questions answerable from the excerpt. Templated connection cards in milestone 3.
- **Q6.** Should a bearer import auto-accept items? **Resolved:** yes (`trust` defaults to true for bearer, false for a paste). Unverified items stay pending either way.
- **Q7.** Daily cap and timezone? **Resolved:** 15 reviews, 5 of them new, America/Los_Angeles, both caps editable within 1–50.
- **Q8.** Fuzzy auto-merge? **Resolved:** never. Milestone 2 may suggest. Nick confirms.
- **Q9.** Sign-in method? **Resolved:** email and password with a JWT cookie. No Google sign-in and no magic link.
- **Q10.** Who deploys? **Resolved (Nick):** Nick, from the README runbook. The build session creates no Railway resources.
- **Q11.** Inbound email? **Resolved:** dropped. The bearer endpoint is the push path.

## Reviewer checklist

- [x] The spec can be reviewed and implemented from this file alone.
- [x] The summary, goal, and success criteria are concrete.
- [x] Scope and non-goals are explicit.
- [x] User stories and flows cover the success path and the failure that matters.
- [x] Requirements are numbered and testable.
- [x] The design names architecture, data model, APIs, components, and files.
- [x] Constraints, edge cases, and failure behavior are specified.
- [x] Stack and dependencies match the target repo, and anything new is justified.
- [x] Milestones are ordered, and each has acceptance criteria.
- [x] The testing plan covers the requirements.
- [x] Risks are identified, and every open question is resolved or has a default.
- [x] `target_repo` is correct, and no secret values appear in the spec.

### Review notes

Reviewed 2026-11-22. Requirements were renumbered; the draft's FR numbers no longer apply.

Decisions from Nick:

- No model in the app. Removed markdown extraction, card generation, `agent_runs`, the per-hour model limit, the Anthropic SDK, and `ANTHROPIC_API_KEY`. The import JSON now carries the cards.
- The JSON is written by a local Claude Code loop on Nick's subscription, through a skill in the repo meant for Haiku. Added the skill, the push script, the watchlist endpoint, and the loop instructions. The Grok bot prompt remains as an alternative.
- Nick creates the repo; a build session cannot. Nick deploys; the build stops at tested code and a runbook.

Defects fixed:

- The draft's own JSON example failed its verbatim rule: it compared the decoded excerpt with the raw JSON text, where inner quotes are escaped. Excerpts are now checked against the digest text when supplied, with a whitespace- and quote-tolerant key, and a miss holds the item pending instead of deleting it.
- Hashing by url first collapsed two quotes from one article into one item and silently lost the second. Quotes now hash by their words.
- Entity resolution depended on arrival order ("Nvidia Inc." then "Nvidia" made two entities). Every entity now has an alias row for its normalized name, and resolution is one alias lookup.
- The new-card cap reset on every queue reload, because a reviewed card stops counting as new. It is now counted from the day's reviews.
- Today cleared its "new items" list on every page load. It now advances only on an explicit action.
- The scheduler text did not say which difficulty the stability update uses. The fixtures require the updated one; this is now stated, with a seventh fixture that would catch the other reading. All seven were recomputed.
- The flow said a card rated Hard is due the next day; by the formulas it is not. Reworded to match fixture A.
- The manifest and icons sat behind the session cookie, which breaks home-screen install. `/static/` is public.
- `provisional` entities had no defined behavior. Removed.

Added: sign-in rate limit, sliding session, `set-password`, minimum import-token length, digest delete, card editing, output escaping and url-scheme rules, an explicit dependency list (including the `bcrypt` and `tzdata` pins), Postgres for tests, `railway.toml`, and iOS home-screen tags.

## Status log

| Date | Status | Note |
| --- | --- | --- |
| 2026-11-21 | draft | Spec created. |
| 2026-11-21 | draft | Stack corrected: Nick uses the fitness app, not speed-reader-v2. Backend follows FastAPI, SQLAlchemy, Alembic, Railway Postgres, and JWT. speed-reader-v2 contributes concepts only. |
| 2026-11-22 | reviewed | Review complete. No model in the app; Nick creates the repo and deploys. See Review notes. |
| 2026-11-22 | reviewed | Added the local ingest loop: a Claude Code skill on Nick's subscription writes and pushes the JSON. |
