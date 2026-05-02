# SPEC_V2_NEXT.md — Post-Ship Audit & v2.1 Re-baseline

**Status:** Council-derived spec. Generated 2026-05-02 from a fresh-eye audit (Engineer + Designer + PM) of the v2.0 codebase as it stands at commit `47417b0`.
**Authority:** Supersedes SPEC_V2 §6, §9, §11 for v2.1 planning. Does NOT supersede SPEC_V2 §0–§5 (vision, surfaces, architecture, aesthetic) — those remain locked.
**Inputs:** Three council audits — Senior Staff Engineer (codebase), Product Designer (visual + interaction), PM (execution vs spec).
**Pivot to internalize:** Holocron is now a **personal tool**. No invite distribution. No "inner circle." This kills one weekend of v2.1 scope and re-shapes the rest.

---

## 0. TL;DR

1. **v2.0 shipped clean.** 14 of 15 ACs Met or appropriately Voided. One Partial (autosave hard-kill ceiling, AC #5) is a real data-loss risk and should close this week.
2. **The personal-only pivot kills ~1 weekend of planned v2.1 scope** (public profile in entirety) and reduces another (sharing UI, briefs distribution).
3. **The biggest tech-debt finding is a data-loss bug shipped in W2:** the Reader's recall step captures user input that is never persisted to `sources.user_recall`. Either wire it or remove the column + step.
4. **Three places where multiple agents independently flagged the same thing** become forcing functions: `<HoloPanel>` extraction (Eng + Designer), v2.1-leak in placeholder copy (Eng + Designer + PM), autosave max-wait (Eng + PM).
5. **Recommended next move: SOAK first, build second.** Land one short cleanup session this week, then don't write spec for v2.1 until §14 Day-30 self-check (fires 2026-05-26).
6. **v2.1 re-baselined from 5 weekends to 3** (Gmail ingest → "I'm stuck" → weekly briefs + autonomy). Public profile killed entirely.

---

## 1. v2.0 Acceptance Audit

| # | AC | Verdict | Notes |
|---|---|---|---|
| 1 | Sign-in ≤30s, four navigable shells | **Met** | W1 |
| 2 | Reader parity (paste/PDF/EPUB/TXT/MD/URL/Twitter, RSVP, Finish) | **Met** | W2 |
| 3 | Atlas parity + ≥30 ghost concepts post-ingest | **Met** (live screenshot diff still pending) | W3 + W4 |
| 4 | Per-user data isolation | **Met** | `requireOnboarded()` + verified W7 incognito |
| 5 | Writing surface lossless | **Partial** | Pure-debounce 800ms, no max-wait. **Real data-loss in continuous-typing edge case.** Close this. |
| 6 | No source body / draft text in logs | **Met** | Verified by code-grep |
| 7 | §7 perf budgets, Lighthouse green | **Partial** | Public `/signin` audited. 6 auth-walled surfaces unaudited. v2.1 backlog. |
| 8 | No data loss; daily pg_dump | **Unknown** | Daily pg_dump verification not visible in commits. Cheap to verify. |
| 9 | v1.x untouched | **Met** | Separate repo + URL |
| 10 | Aesthetic continuity, 4 signatures on every primitive | **Met** (with two surfaces drifting — see §3) | W6 polish |
| 11 | Demoable in 90s | **Voided** (W7.J4 dropped per pivot) | |
| 12 | 3 friends onboarded | **Voided** (per pivot) | |
| 13 | Privacy disclosure, `privacy_ack_at` populated | **Met** | W1 |
| 14 | Notion ingest idempotent | **Met** | W4.J5 ON CONFLICT |
| 15 | Tiptap-light scope locked | **Met** | Hard rule held; no slash menu, no toolbar, no popover |

**Cut-list compliance (SPEC §12):** Clean. One small deviation: W7's "SETTINGS in global nav" widens chrome past §3.1's 4-link nav set. Acceptable (discoverability fix), but flag in spec.

---

## 2. Findings — Engineering

### 2.1 Real bugs (priority-ordered)

#### P0 — `recall` data-loss bug
The Reader's "free-recall before AI summary" step is the headline interaction of the Finish flow. `components/Reader/FinishModal.tsx:50` captures recall to local state; `requestSummary` (`FinishModal.tsx:79–137`) never sends it. The `sources.user_recall` column (`lib/schema.ts:202`) is populated by nothing.

**Action:** wire recall through the summarize POST → `summarizeAndPersist`, OR delete the column + step. **Don't keep both half-wired.** Recommend wiring (the recall step is in the spec for a reason).

#### P0 — Autosave has no max-wait ceiling
Already in v2.1 backlog, but reclassify: this is **the only AC #5 gap** and continuous-typing for >800ms-without-pause loses state on force-kill. **Action:** add `force-PATCH every 5s of dirty state` to `lib/write/autosave-queue.ts`.

#### P1 — `getActiveNotionConnection` returns OLDEST connection
`lib/notion/connection.ts:40` uses `orderBy(notionConnections.createdAt)` ascending. After revoke + reconnect across workspaces, the migration loop uses the stale row.
**Action:** `desc(notionConnections.createdAt)` — one-character fix.

#### P1 — `isInviteActive` ↔ `findActiveInviteToken` disagree on null `expires_at`
`lib/share-tokens.ts:25–28` says null → active; `lib/share-tokens.ts:38–49` excludes null via `gt(expiresAt, now)`. Mint always populates `expiresAt` so it's not biting today, but a future migration or admin insert is a landmine.
**Action:** pick one semantic. Recommend "null → active" everywhere and add a migration test.

#### P1 — No request-body size limit on `/api/writings/[id]` PATCH
Body jsonb is unbounded. Title is clamped (256 chars) but body is not. Same gap on `/api/share-tokens` POST and `/api/extract` POST.
**Action:** centralize a `MAX_BODY_BYTES` (start at 2MB) in a `withAuth(parse)` route helper. See §2.3.

#### P2 — Duplicate cookie constants
`middleware.ts:25–26` redefines `INVITE_COOKIE_NAME` + `INVITE_COOKIE_MAX_AGE_S` instead of importing from `lib/share-tokens.ts`. Edge runtime can import constants — only DB-touching helpers are Node-only.
**Action:** extract `lib/share-tokens-edge.ts` (constants only).

#### P2 — Local `isSourceType` shadows canonical export
`app/api/summarize/route.ts:111–113` reimplements `lib/schema.ts:79–81`'s `isSourceType`.
**Action:** import from schema. 5-minute fix.

#### P2 — `db.batch(ops as any)` repeated 4× with the same eslint-disable
`lib/ingest/summarize-core.ts:298,387`, `app/api/writings/[id]/route.ts:199`, `app/api/sources/[id]/route.ts:240`.
**Action:** `export function batch(ops: unknown[]) { return db.batch(ops as any); }` in `lib/db.ts`.

#### P2 — `jsonError` migration incomplete
`/api/extract` and `/api/sources/[id]/text` still open-code `NextResponse.json({error},...)`. Already in v2.1 backlog.

#### P3 — `CARD_LIMIT = 200` with kicker promising pagination
`app/library/page.tsx:24` + `:168` ("OLDER SOURCES PAGINATE NEXT"). Pagination doesn't exist. With Notion's 70 imports + ongoing usage, hits 200 within a year of personal use.
**Action:** either build cursor-pagination (1–2 hour task) OR change kicker to "first 200 — older fall off." Don't lie in copy.

### 2.2 Cross-cutting refactors worth doing

1. **`withAuth(handler)` route factory.** Every `/api` route opens with the same 3 lines (`auth()`, 401, parse JSON). Extract once → 15 lines saved per route + body-size limits become a one-line addition.
2. **`<HoloPanel>` primitive** (also flagged by Designer, see §3.4) — single biggest hardening move. Eliminates the entire class of "shipped a panel without a pilot" drift.
3. **`tsconfig.json` → `noUncheckedIndexedAccess: true`.** Catches `existing[0].id` (`/api/summarize/route.ts:161`) and similar — correct today but unenforced.
4. **Typed `RunInputs` discriminated union** for `agent_runs.input` JSONB shape — paves Gmail ingest's add cleanly.
5. **Scrub the v2.1 references from user-facing copy.** `app/log/page.tsx:11`, `components/Atlas/AtlasTab.tsx:22` ("CAP RAISES IN v2.1"), `app/settings/page.tsx:17`, `app/me/page.tsx`, schema comments, ~10 more sites. Now permanent fossils.

### 2.3 Risks worth knowing
- Anthropic model alias `"claude-sonnet-4-6"` in `lib/llm/anthropic.ts:12` is not a versioned snapshot ID. Verify it's a live alias on the account; consider pinning `claude-sonnet-4-6-YYYYMMDD` for stability over years.
- Autosave retry loop caps at 10 attempts × 60s = 10 minutes silently. After that, no UI signal that retry gave up. For a daily-use tool this matters — consider surfacing "saved locally, refresh when online" at attempt 10.
- No global error boundary. A render error in `EditorPanel`, `AtlasInteractive`, or `Reader` takes the whole page to Next's default. For a thinking tool, per-surface error boundaries that preserve the autosave queue would matter.

### 2.4 Things that should NOT change
- **Tiptap-light scope** + the prebuild allowlist guard. SPEC §13 risk #1.
- **Two-phase concept upsert** in `summarize-core.ts:178–219` — the comment correctly identifies a real concurrency bug it prevents. The extra round-trip is paying for correctness.
- **In-memory rate limiter** in `/api/summarize/route.ts:73–102`. Per-instance buckets are exactly right at solo-tool scale; don't preemptively add Upstash.

---

## 3. Findings — Aesthetic / Interaction

### 3.1 Surfaces that hit the bar
Landing, `/signin`, `/onboarding` + `PrivacyDisclosure`, `/invite/[token]` (W7), `/settings/sharing` (W7), `/library` list + radial atlas, `/migrate/notion`, `/read` ingest panel + Reader. **The atlas remains the gold standard** — corner annotations TL/TR/BL/BR, `spin-slow` rotor, `breathe` halo, just-saved + just-imported pulses, dashed cross-links.

### 3.2 Surfaces missing signatures or with regressions

| Surface | Issue | Severity |
|---|---|---|
| `/me`, `/settings` index, `/log` | Still `SurfaceShell` placeholders with copy referencing v2.1 / weekend 9 / "agent autonomy in v2.1." Per pivot, these references are voided — placeholders now leak old roadmap into prod. | **fix-soon** |
| `components/Library/LibraryError.tsx` | Missing signature #4 (no `panel-pilot`/`breathe`). "OFFLINE" shell sits dead-static. | **fix-soon** |
| `/library` list-view header | No ambient live element on chrome itself; signature #4 only on empty-state dot or `just-saved-pulse` (fires once after save). | **nice-to-have** |
| `/write` empty-center hint | Pilot present (good) but `+ NEW PIECE` is a `<p className="meta">`, not a button — reads tappable but isn't. False affordance. | **fix-soon** |
| `/write` `EditorPanel` resolved-saved state | `breathe` lives on `SAVING…` only. Once kicker resolves to `SAVED`, motion lapses — surface goes dead in the most common state. | **fix-soon** |
| Reader paused on first token | Empty state shows static `NO TEXT`. A single `breathe` dot at bottom rail tick would carry signature #4 across pre-roll. | **nice-to-have** |

### 3.3 Hard-rule slips

- `app/globals.css:1713` — `.atlas-panel-body::-webkit-scrollbar-thumb { border-radius: 3px; }` violates "no border-radius >2px." **One-character fix.**
- `app/globals.css:49,223,700,785,1172,1350,1672` — six near-identical 180deg `linear-gradient(#100e09 → #0c0a07)` calls use raw hex. Closed-palette family but should be tokenized as `--panel-grad`.
- `components/Auth/AuthForm.tsx:73` and `app/onboarding/OnboardingForm.tsx:144` — `borderRadius: 2` (no unit). Trivial inconsistency.

### 3.4 Component / primitive opportunities

`components/ui/` is nearly empty (only `Toast.tsx`). Six recurring patterns deserve extraction:

1. **`<HoloPanel kicker title pilot? frame?>`** — the `holo-panel + data-frame="true" + kicker-lg + hairline + optional panel-pilot` shape repeats verbatim across 13+ surfaces (`SurfaceShell`, `SignInForm`, `OnboardingForm`, `PrivacyDisclosure`, `IngestPanel`, `EmptyLibrary`, `LibraryError`, `EmptyAtlas`, all 3 invite variants, both migrate steps, the `/write` empty-center, `replay-error`). Inline duplication is exactly why `LibraryError` shipped without the pilot. **This is the highest-leverage primitive.**
2. **`<Kicker size="lg" hairline>`** — appears 15+ times.
3. **`<MonoCTA variant="mono"|"replay">`** — already an `AuthForm` `submitVariant`; lift it.
4. **`<InlineError kicker>{detail}</InlineError>`** — `holo-error` + alert role pattern.
5. **`<PanelPilot />`** — five-character JSX wrapping `<span className="panel-pilot breathe" aria-hidden />`. Easy to forget `aria-hidden`.
6. **`<TwoColRow kicker>{body}</TwoColRow>`** — 80px-grid kicker+body row.

### 3.5 Mobile + accessibility
- Reader, `/library` list+atlas, `/write`, all panels handle viewport collapse explicitly. Atlas <720px hides TR + BL annotations to avoid stomping the SVG — well-considered.
- Focus-visible ring is right-angled brass; consistent.
- `aria-live="polite"` correctly applied to toasts, save indicator, sharing minted block, atlas writings loading.
- **Verify on a real iOS device:** momentum scroll inside `.atlas-panel-body` and `.wizard-choose-list` (no `-webkit-overflow-scrolling`).

---

## 4. Findings — Product

### 4.1 What the personal-only pivot kills

| Item | Action |
|---|---|
| **Public profile (W9 in entirety)** — `/u/{slug}`, `?concept=` deep-link annotations, satori OG cards, profile tabs, About page, per-content `is_public` toggles | **KILL.** Drop from spec. |
| **`friend_links` UI** — schema can stay (cheap) but no `/u/{slug}/friends` view ships | **KILL UI; keep schema.** |
| **Sharing tab investment** — `/settings/sharing` works, leave it. Don't invest more. | **Freeze.** |
| **`share_tokens.target_kind` enum values** for `atlas`/`source`/`writing`/`concept` | **Leave.** Cost is zero; preserves option to text a friend a single concept page someday. |
| **Notion export (v2.2 §8.3)** — was distribution-shaped | **KILL** until/unless Nick wants per-source bidirectional Notion sync for his own use, which is a different feature. |
| **Holocron promotion of starred quotes** (v2.2) | **KILL** — was always usage-gated; with personal-only the gate is much higher. |
| **AC #11 (90s recording verification path)** | **Voided.** Mark closed in spec. |
| **v1.x → v2 redirect plan** | **Already shelved.** Stay killed. |

### 4.2 Phase gate replacement (post-pivot)

Original v2.1 gate ("≥2 of 3 invited friends return + atlas crossed 50 concepts") is dead. Replace with:

> **New v2.1 advance gate:** at least **3 of 5** SPEC §14 Day-30 questions answer yes, AND at least one of these is a yes:
> - "Did I open `/write` for non-test reasons? Did I write anything substantive?"
> - "Did the bookmark live in pinned tabs, or did I forget?"
>
> AND atlas ≥50 concepts (kept — corpus-density readiness for Gmail + "I'm stuck" retrieval).

Day-60 and Day-90 gates from §14 stay as-is. They're already self-check shaped.

### 4.3 v2.1 re-baselined

| Old | New | Recommendation |
|---|---|---|
| W8: Inngest + agent log | folded into W8 | Activity log appears with first agent (Gmail ingest). Don't ship as standalone. |
| W9: Public profile | **KILLED** | Personal-only pivot voids entire weekend |
| W10: Gmail ingestion | **W8** (promoted) | Highest personal-utility — Nick already routes newsletters via Gmail label. Same muscle, better surface. Earns its weekend. |
| W11: "I'm stuck" / give-me-ideas | **W9** | The recursive-memory loop (writing pulls from atlas) is the spec's thesis (§2.2). Without this, /write is a journaling textarea with rich text. |
| W12: Weekly briefs + autonomy panel | **W10, scope-down** | Skip Web Push (Brex IT risk + personal-only = bell icon enough). Brief lands in `/write` as Sunday-morning self-feed. Autonomy panel simpler — only Nick uses it. |

**Net: 3 weekends instead of 5.** Activity log folds into Gmail weekend (it's where the first real `agent_runs` rows come from).

### 4.4 What didn't ship that should
- **AC #5 (autosave hard-kill)** — Partial → close it.
- **AC #8 (daily pg_dump verification)** — Unknown → verify and document in OPS.md.
- **Atlas screenshot diff vs `mindmap-radial.html`** — pending since W3, code-side parity verified, live screenshot needs Postgres seeded with 30+ concepts. Worth a 20-min pass once Notion migration has run.

---

## 5. Recommended Next Move

**SOAK first, build second.**

The thesis (§2.1): *"every read feeds an atlas, and the atlas feeds my writing."* The post-pivot question is: **does that loop run for Nick?** §14 Day-30 is designed exactly to answer this and requires *use*, not building.

SPEC §11 phase-gate anti-pattern is explicit: *"shipping v2.1 before v2.0's adoption signal — don't."*

### 5.1 Two sessions, two timelines

#### Session N (now, ~2 hours) — Cleanup that closes real gaps

Single-agent execution. Order matters; each item depends only on a fresh code base:

1. **Wire or remove the recall data-loss bug** (P0) — `FinishModal.tsx:79–137` send recall to `/api/summarize`; `summarizeAndPersist` writes to `sources.user_recall`. Recommend wiring (spec §3.1 has it).
2. **Add autosave max-wait** (P0) — `lib/write/autosave-queue.ts`, force-PATCH every 5s of dirty state. Closes AC #5.
3. **Fix `getActiveNotionConnection` ordering** (P1) — `lib/notion/connection.ts:40`, `desc()` not `asc()`.
4. **Fix `LibraryError` missing pilot** (Designer fix-soon) — one-line `<PanelPilot />`.
5. **Fix scrollbar `border-radius: 3px`** (hard-rule slip) — `app/globals.css:1713`.
6. **Update v2.1-leak copy** in `/me`, `/settings`, `/log`, atlas tab cap message — drop "weekend 9," "v2.1," "Eight sections" verbiage. Replace with stable phrasing or hide from nav.
7. **Verify daily pg_dump** (AC #8) and document in OPS.md.

Stop there. Don't take on §2.2 cross-cutting refactors yet — they pay back across weekends, not in one session.

#### Session N+1 (after 2026-05-26, post-Day-30) — Re-spec v2.1

Inputs: §14 Day-30 answers + this doc. Output: a 3-weekend v2.1 plan replacing SPEC_V2 §6 / §9. If Day-30 fails the gate (<3/5 yes), polish-only month per §14 pass/fail matrix.

### 5.2 Things to NOT do this session

- ❌ Don't extract `<HoloPanel>` yet — it's the highest-leverage refactor but lives most naturally at the start of the v2.1 re-spec session, when the next surface needs it.
- ❌ Don't build pagination for `/library` — change the kicker copy if it bothers you, defer pagination until atlas crosses ~150 sources.
- ❌ Don't chase the `jsonError` migration, AuthPanel extraction, or lockfile regen — all real, all small, all live in the next session.
- ❌ Don't start v2.1 (Gmail ingest, "I'm stuck") before Day-30 fires.

---

## 6. v2.1 Re-baselined Spec (sketch — to be expanded post-Day-30)

### W8 — Gmail ingestion + activity log skeleton
- Inngest worker on Railway + `agent_runs` writing pattern
- `gmail.readonly` OAuth + per-user `gmail_subscriptions` row
- 5-min cron poll with `historyId` cursor, label filter `holocron/ingest`
- Email body extract via existing `api/extract.js` + heuristic for "click-to-read" links
- Save as `Source` with `source_type='gmail'`, default `status: 'queued'`
- Per-sender reputation (`auto_finish` / `queue` / `mute`)
- `/log` page — minimal timeline showing Gmail ingests with input/output diff and undo
- **Demo:** newsletter arrives → log shows ingest → source appears in queue

### W9 — "I'm stuck" / give-me-ideas
- pgvector backfill for sources/writings/quotes/concepts (`embeddings` table)
- `suggest_stuck` Route Handler (sync, SSE-streamed)
- Tiptap `@`-mention popover (Concepts + Sources)
- Right rail companion panel in `/write`
- Floating "I'm stuck" button → opens companion + runs ranker
- Aggregate `reasoning` + per-item `why_this`
- **Demo:** mid-paragraph, click "I'm stuck", relevant material in <2s

### W10 — Weekly briefs + autonomy panel + v2.1 ship
- `brief_weekly` Inngest cron (Sunday 9pm)
- Brief generated as a `Writing` row with `kind='brief'`, `is_public=false`
- Settings → Agent Autonomy panel (per-job sliders)
- Bell icon notification center (skip Web Push — Brex IT risk + personal-only doesn't need it)
- **Demo:** Sunday brief lands in `/write` as a new piece + bell icon shows badge

**Cut from original v2.1:** public profile, OG cards, per-content public defaults, Web Push.

---

## 7. Spec status

This document is a planning artifact, not a build document. It supersedes SPEC_V2 §6 / §9 / §11 for v2.1 planning and supplements SPEC_V2 with a cleanup punch-list (§5.1 above).

**SPEC_V2.md remains the authority for §0–§5 (vision, surfaces, architecture, aesthetic).** Do not touch those sections.

**v2.1 backlog (`v2-1-backlog.md`)** is now subsumed by §2.1 + §5.1 above. Items not closed in Session N (jsonError migration, AuthPanel extraction, lockfile regen on Linux, lighthouse for auth-walled surfaces, W4.J5 cost calibration) carry forward into the v2.1 re-spec session.

**Author:** council-derived (Engineer + Designer + PM agents), 2026-05-02.
