# "Oahu Trip" — Family Vacation Planner — SPEC

> **For the executing session:** This is the approved, council-produced spec (4-agent council + cross-review, 2026-08-15; all conflicts resolved, product calls user-confirmed). Build it phase by phase per the Execution Plan at the bottom. The companion council summary lives at `plans/COUNCIL_SUMMARY_hawaii-planner_2026-08-15.md` (repo root) for `/evaluate --against council`.

## Context

Nick's family (5 travelers: Nick, Erica, Ellyn, and two parents) is going to Oahu **Aug 26–31, 2026**, staying at the Aston Waikiki Beach Tower with one shared rental car. This app is a collaborative planner — great on phones and desktop — for realistic day-by-day schedules with drive times, geographically grouped activities, and a restaurant suggestion/voting board with Yelp link-outs.

**Time-to-useful is the driving constraint:** the trip is days away; the family should be voting on restaurants (Phase 2) well before the itinerary builder (Phase 3) is done.

## Locked decisions (user-confirmed)

- Oahu only; home base Aston Waikiki Beach Tower (Waikiki); one car → single shared itinerary track.
- **Trip days to seed:** Wed 8/26 ("Arrival — land ~9pm"), Thu 8/27, Fri 8/28, Sat 8/29, Sun 8/30 (note "Nick flies out 10pm"), Mon 8/31 ("Last day — 4 travelers, flights home").
- Access: shared link + name picker, no accounts or logins; **unguessable token** protects the API (see Auth).
- Voting: 👍 interested (unlimited, 1pt) / ⭐ must-go (3pts), **3 stars per person per board** (restaurants board, activities board), server-enforced.
- Stack: FastAPI + Postgres + SQLAlchemy + Alembic; vanilla JS/HTML frontend served by the same app (no build step); Railway.
- Travel times: curated static 9-region drive-time matrix + Google Maps link-outs; Yelp link-outs on restaurants.
- App name: **"Oahu Trip"**. Directory: **`hawaii-planner/`** (no spaces — Railway chokes on spaces per Caltrain SPEC precedent; the older empty `Hawaii Trip/` dir is NOT used).

## Architecture

**Repo patterns to mirror** (read these before building):
- `fitness-app/backend/app/core/config.py` — BaseSettings, SQLite-local default / `DATABASE_URL` override, Railway prod guard
- `fitness-app/backend/app/core/database.py` — mirror verbatim (engine w/ pool_pre_ping, SessionLocal, Base, get_db)
- `fitness-app/backend/alembic/env.py` + `alembic.ini` — Alembic wiring; models roster in `app/models/__init__.py` for autogenerate
- `fitness-app/backend/railway.toml` — migrations in startCommand, no create_all fallback
- `Caltrain App/app/main.py:304` — `app.mount("/", StaticFiles(directory=...frontend, html=True))` AFTER api routes; `{"error": {code, message}}` handler shape
- `Caltrain App/frontend/app.js` — textContent-only rendering, single state + render(), visibilitychange-aware polling

**Directory layout:**
```
hawaii-planner/
├── railway.toml          # nixpacks; startCommand = "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT"
├── requirements.txt      # fastapi, uvicorn, sqlalchemy, alembic, psycopg2-binary, pydantic-settings (pinned, from fitness list minus auth/AI deps)
├── alembic.ini / alembic/
├── app/
│   ├── main.py           # routers → static mount; health at /api/health
│   ├── core/{config,database}.py
│   ├── models/           # member, region, drive_time, idea, vote, trip_day, schedule_item, app_state
│   ├── schemas/          # pydantic request/response pairs per domain
│   ├── api/              # members, ideas, votes, days, items, bootstrap
│   ├── services/timeline.py   # pure function, unit-tested
│   └── seed.py           # idempotent upserts; safe on every boot
├── seed/                 # regions.json, drive_times.json, activities.json, restaurants.json, day_templates.json
├── frontend/
│   ├── index.html  style.css
│   └── js/{main,api,state}.js + views/{schedule,ideas,eats}.js
└── tests/                # timeline, vote budget, api
```

### Data model

String UUID PKs + created_at/updated_at (fitness pattern) except reference tables (slug PKs). All times are Hawaii-local wall-clock (`Date`/`Time` columns, zero timezone math — one-TZ trip).

- **Member**: name (unique, case-insensitive), color (avatar chip). Claimed via name picker; id stored in localStorage `hawaii:member:v1`.
- **Region** (slug PK, seeded): `WAI` (home base) HNL PRL EAST WINDS WINDN NS CEN KOOL; name, sort_order, **tour_order** (clockwise island loop WAI→HNL→PRL→CEN→NS→WINDN→WINDS→EAST→KOOL — powers bulk-add ordering).
- **DriveTime** (seeded): symmetric upper-triangle — region_a ≤ region_b check constraint, 45 rows incl. diagonal=10; minutes (typical midday); **flags** CSV (`H1_AM,H1_PM,NS_WKND,HANAUMA_AM_WKND`). Flags are display-only caution chips, NEVER added to minutes (if flags ever feed arithmetic, the matrix must become directional first — do not "upgrade" casually).
- **Idea**: title, kind enum(activity|restaurant), region FK, duration_min (default 90 activity / 75 restaurant), yelp_url nullable (UI auto-generates a "Search Yelp" link when absent), maps_url nullable (fallback: client builds `https://www.google.com/maps/dir/?api=1&destination=<title, Oahu HI>`), notes, **recommended_by** nullable text ("Erica's mom's friends" / "Nick's parents"), **reservation_rule** text, **closed_days** CSV weekday tokens ("mon,tue"), **difficulty**, **best_time**, **meal_tags** CSV (breakfast|lunch|dinner|treat), created_by_member FK nullable (seed rows: null, with recommended_by set).
- **Vote**: unique (idea_id, member_id), **value enum(interested|must_go)**. Score: interested=1, must_go=3. Budget: max 3 must_go per member per board (board = idea.kind), enforced in the vote transaction; 4th → 409 `{error: {code: "must_go_budget_exceeded", current_must_go_idea_ids: [...]}}` so the UI offers the swap sheet.
- **TripDay**: **date nullable** (unique; multiple NULLs fine), label, start_time (default 08:30), **end_time** (default 21:30), notes.
- **ScheduleItem**: day FK cascade, idea FK nullable XOR free_text_title (check constraint), optional free_text_region (defaults to previous stop's region), position, duration_override_min, fixed_start_time (pins reservations), **drive_override_min** (replaces matrix+buffer for the inbound leg; column in v1, UI stepper in polish), notes. **No stored computed times** — timeline always derived.
- **AppState**: single row `version` bigint; every mutating endpoint bumps it → powers polling.

### API

All under `/api` (StaticFiles owns `/`). Attribution via `X-Member-Id` header. **Auth: `X-Trip-Token` header checked by middleware on all /api routes except `/api/health`, against `LINK_TOKEN` env var.** Shared URL is `https://<app>/?k=<token>`; frontend stores the token in localStorage and sends the header; static assets are public but data-free.

- `GET /api/health` → `{status: "ok"}`
- `GET /api/bootstrap` — one-shot render payload: `{version, members[], regions[], drive_times[], days[{...day, items[<computed timeline>], warnings[]}], ideas[{...idea, score, votes: [{member_id, value}], scheduled_day_ids[]}]}`
- `GET /api/version` → `{version}` — poll every 10s while `document.visibilityState === "visible"`, pause hidden, refetch bootstrap on change + immediately on visibilitychange→visible
- `POST /api/members {name}` — idempotent case-insensitive claim (200 existing / 201 created); `GET /api/members`
- Ideas: `POST /api/ideas`, `PATCH /api/ideas/{id}`, `DELETE` (cascades votes + schedule items; UI confirms if scheduled)
- Votes: `PUT /api/ideas/{id}/vote {value: "interested"|"must_go"}` upsert/re-select; `DELETE` clears — both idempotent
- Days: `POST /api/days`, `PATCH /api/days/{id}` (label/start_time/end_time/date/notes), `DELETE`
- Schedule: `POST /api/days/{id}/items {idea_id | free_text_title, position?, duration_override_min?, fixed_start_time?}`; `PATCH /api/items/{id}` (overrides, move between days); `DELETE /api/items/{id}`; `PUT /api/days/{id}/order {item_ids}` — atomic full-order rewrite; **`POST /api/days/{id}/items/bulk {idea_ids}`** — appends ordered by region.tour_order, ties by score desc (powers cluster "Plan this day" + day templates)
- Every mutation returns `{version, day: <full recomputed timeline>}` (or the affected resource) — client re-renders from the response, no follow-up fetch.

### Timeline algorithm

`app/services/timeline.py` — pure function, backend-authoritative, computed at read time (bootstrap + every mutation response), never persisted.

1. `cursor = day.start_time`; `prev_region = WAI` (first leg = hotel → first stop).
2. Per item in position order: `drive = matrix(prev_region, item_region) + TRANSITION_BUFFER_MIN (10)`; same-region hop = diagonal 10 + 10 = 20. `drive_override_min` replaces the whole matrix+buffer figure.
3. Pinned items (`fixed_start_time`): start = pin; emit `leave_by` (= pin − drive; labeled "leave hotel by X" when first item) and `slack_minutes` when early; `infeasible_arrival` warning when `cursor + drive > pin` ("arriving ~N min late" — warn, never block). Gaps before a pin render as visible free-time blocks.
4. Unpinned: `start = cursor + drive`. `end = start + (duration_override or idea.duration_min or 90)`. Advance cursor/prev_region.
5. Per-leg output includes drive_minutes + matched DriveTime flags (UI: amber dashed segment "🚗 50 min ⚠ rush hour").
6. **Return leg** after the last item: last region → WAI, `arrive_hotel_at`; **overpacked warning** when it exceeds day.end_time.
7. **closed_on_day warning** when day.date is set and its weekday ∈ idea.closed_days (skip silently when date null).
8. Day outputs: `total_drive_minutes` (always displayed — one car makes drive load THE scarce resource), `day_ends_at`, warnings.

### Sync

10s version polling (visible only) + refetch-on-focus; last-write-wins; the atomic order endpoint makes concurrent reorders converge. No SSE/websockets — 5 users, planning cadence.

## UX

- **3 tabs: Itinerary | Ideas | Food** + header you-chip (identity, switch person, trip-dates admin). Mobile <720px: bottom tab bar (icon+label always, 56px rows, safe-area inset, dot badge = new-since-last-look). Desktop ≥720px: same destinations as top nav. Hash routing `#/day/3`, `#/ideas`, `#/food` (token stays pre-hash in the URL).
- **Name picker**: full-screen on first visit — 5 big 56px buttons (Nick, Erica, Ellyn, Mom, Dad; display names editable) + "I'm someone else" → name field. localStorage; "Aloha, Nick! Your name is remembered on this phone." toast; switch via you-chip. Names are never locked (shared iPads).
- **Itinerary spine** (signature element): vertical route line — filled dots + solid segments = stops; dashed segments with 🚗 + minutes = drive legs. Day begins with a home-base row (leaves at start_time, ✎ to edit) and ends with computed **"Back at hotel ~X PM"**. 📌 marks pinned rows; ⚠ amber rows for tight arrivals/closed days. Day strip = horizontally scrolling chips with dominant-region color dots. Empty day → "Browse the Idea Pool" / "+ Add a stop" / **"Or start from a day plan ▸"** (sheet of 7 seeded archetypes → preview stop list → "Use this plan" instantiates via bulk endpoint, linking matching pool ideas; read-only templates, no editor).
- **Add stop** bottom sheet: from Idea Pool / from Food Board / type new (name, region chips, duration stepper in 15-min steps, optional pin-a-time, notes).
- **Reorder without drag-drop**: ••• overflow per stop (Move up · Move down · Move to another day… · Edit · Remove · Directions; Remove offers "send back to Idea Pool") + a "Reorder" mode compacting cards to rows with big ▲▼ (44×44), optimistic row order with "…" times until the response lands.
- **Ideas pool**: region filter chips; grouped under colored region headers with counts; **cluster banner** when ≥3 unscheduled ideas share a region ("North Shore day? Plan this day ▸" → day picker → bulk-add in tour order). Scheduled ideas stay in the pool, dimmed, with ✓ + day chip — the pool doubles as a checklist.
- **Food board**: ranked list with big rank numbers (⭐ count → 👍 count → newest). "Yelp ↗" is a first-class red-outline button on every card (absent URL → "Search Yelp ↗" using name + Honolulu). Suggest sheet: name (required), Yelp URL paste + "Find it on Yelp ↗" helper, region chips, notes. "Add to a day ▾" → day picker → meal-duration default + "Pin a time?" follow-up.
- **Reaction pill** on ALL cards (both boards): right-aligned `[👍 n][⭐ n]` — two adjacent 44px-tall toggles, single-select (star replaces thumb; tapping your active one clears), outline style filling when yours. Voter full first names in the detail sheet via tapping the count (Erica/Ellyn initials collide — never initials). 4th ⭐ → "Move your must-go?" sheet listing your current 3.
- **Metadata placement — max 2 badges per card**, everything else in the detail sheet: 🎟 Reservation badge (full reservation_rule text in the sheet + amber banner in day-picker confirmation); closed_days = disabled day-picker rows ("✕ Closed Mon") + ⚠ timeline row if violated anyway; difficulty as plain-language chip ("Hard hike" — never icon-only); best_time as meta line + non-blocking hint at scheduling.
- **Desktop itinerary cockpit** (≥1024px): three panes — week rail (~200px: date, label/dominant region, stop count) | day timeline (same component as mobile) | "Add to this day" context panel (~300px: unscheduled ideas sorted current-day-region-first + top-ranked unscheduled restaurants, inline +Add). 720–1023px: rail + timeline only. Ideas = multi-col grid on desktop; Food stays a single 640px ranked column. Same DOM components; CSS grid `grid-template-areas` switches the shell.
- **Freshness**: NEW● pills on items newer than per-device `lastSeen` (localStorage) + tab dot badges; visiting a tab updates lastSeen. Attribution "Added by Erica" and "via Erica's mom's friends" lines everywhere.
- **Visual direction — "Trail map, not travel brochure."** High-contrast light theme only (sunlit one-handed phone use; no dark mode). Tokens: sand `#FFFDF7` bg · lava `#221A14` text · ocean `#0B7285` primary/links/active · hibiscus `#D6336C` accents (NEW, ⭐) · reef-mist `#E7F1F2` fills/drive segments · driftwood `#8A7A66` secondary. Region hues (chips/left borders only, always text-labeled): WAI coral `#F76F63` · HNL amber `#E8A13C` · PRL slate `#5C7CFA` · EAST palm `#2F9E44` · WINDS aqua `#22B8CF` · WINDN seafoam `#12B886` · NS deep-ocean `#1864AB` · CEN cane `#C9A227` · KOOL sunset `#C2255C`. Type: Bricolage Grotesque (700/800) display, system-UI body, base 17px, stop names 19px semibold, `font-variant-numeric: tabular-nums` on all times. 12px card radius, 1px `#E4DCCE` borders.
- **Touch rules (non-negotiable)**: single delegated click listener per view root switching on `closest('[data-action]')`; no inline onclick; all tappables ≥44×44px (primary buttons 52–56px); `touch-action: manipulation` on html; `-webkit-tap-highlight-color` + visible `:active` state (darken ~8% + scale 0.98); no hover-revealed controls; bottom sheets mobile / centered modals ≥720px (✕ + scrim-tap close, Escape on desktop); `-webkit-appearance: none` on buttons.

## Product rules & acceptance criteria

Timeline rules are in the algorithm above. Acceptance highlights: add a restaurant in <30s on a phone; cross-device changes visible ≤20s; votes optimistic + idempotent (double-tap safe); 4th star rejected with the swap flow; all flows one-handed at 375px with no horizontal scroll; cold load <3s.

**v1.1 (after the family is using it; driven by complaints):** sunset-aware warnings (late-Aug Honolulu sunset ≈ 6:50pm — a static display line per day header is cheap if trivial), lunch-gap nudge, structured booked/needs-booking flags (v1 = reservation_rule text + notes), drag-and-drop, printable day view, per-item comments.
**Never:** live Maps API, websockets, accounts, multi-trip, ICS/push/weather/budget.

## Seed data

**Drive matrix** (typical midday minutes, symmetric; diagonal 10):

|  | HNL | PRL | EAST | WINDS | WINDN | NS | CEN | KOOL |
|--|--|--|--|--|--|--|--|--|
| **WAI** | 15 | 30 | 25 | 30 | 50 | 60 | 45 | 45 |
| **HNL** | | 15 | 30 | 25 | 40 | 50 | 35 | 35 |
| **PRL** | | | 40 | 25 | 45 | 40 | 25 | 30 |
| **EAST** | | | | 30 | 55 | 80 | 60 | 65 |
| **WINDS** | | | | | 25 | 65 | 40 | 55 |
| **WINDN** | | | | | | 60 | 50 | 75 |
| **NS** | | | | | | | 20 | 45 |
| **CEN** | | | | | | | | 35 |

Flags: `H1_AM` (6:30–8:30am townbound) on WAI/HNL↔PRL/CEN legs; `H1_PM` (3–6:30pm westbound) on WAI→PRL/CEN/KOOL/NS; `NS_WKND` on NS legs; `HANAUMA_AM_WKND` on WAI/HNL→EAST. (Flat 10-min buffer already covers "exiting Waikiki" friction.)

**Regions:** WAI Waikiki (home) · HNL Honolulu Town (Downtown/Chinatown/Ala Moana/Manoa/Tantalus) · PRL Pearl Harbor/Airport · EAST East Honolulu Coast (Kahala→Hanauma→Makapuu) · WINDS Windward South (Waimanalo/Kailua/Lanikai/Kaneohe) · WINDN Windward North (Kaaawa/Kualoa→Laie) · NS North Shore (Haleiwa→Sunset Beach) · CEN Central (Wahiawa/Dole/Waikele) · KOOL Ko Olina/Leeward.

**Activities catalog (~30; durations = on-site):** Diamond Head hike (EAST edge, 2h, 🎟 non-resident reservation at gostateparks.hawaii.gov, 30-day window, sunrise slots go fast, best early AM) · Waikiki Beach + surf lesson/outrigger (WAI 2–3h, book lesson 1–2 days ahead) · Honolulu Zoo/Waikiki Aquarium (WAI 2h) · KCC Farmers Market (EAST, Sat 7:30–11am only) · USS Arizona Memorial (PRL 1.5h, 🎟 Recreation.gov — standard 56-day window has PASSED for this trip; next-day batch daily 3pm HST or morning standby; no bags) · Pearl Harbor full site: Missouri/Bowfin/Aviation (+3–5h; Missouri = parent favorite; paid combo) · Iolani Palace (HNL 1.5h, closed Sun+Mon, book docent tour) · Chinatown food crawl (HNL 1–1.5h, lunch) · Bishop Museum (HNL 2–3h, rainy-day backup) · Tantalus/Puu Ualakaa lookout (HNL 30–45m, zero walking, sunset; gate closes ~7:45pm summer) · Manoa Falls (HNL 2h, muddy, $7 parking) · **Hanauma Bay** (EAST 3–4h, 🎟 closed Mon+Tue; online reservations open exactly 2 days ahead 7am HST, sell out in minutes, $25/pp 13+; walk-in line 6:45am; last entry ~1:30pm; earliest slot best) · Halona Blowhole + Lanai Lookout (EAST 20–30m, pull-offs, no walking) · Sandy Beach watch-only (EAST 15m — dangerous shorebreak, do not swim) · Makapuu Lighthouse trail (EAST 1.5–2h, paved 2mi RT, no shade, car break-ins — parents can go partway) · Koko Head stairs (EAST 2–3h, **difficulty: hard** — not for parents) · Sea Life Park (EAST 2–3h) · Kailua + Lanikai Beach (WINDS 2–4h, morning; **Lanikai has NO parking — park at Kailua Beach Park**) · Kailua town (WINDS 1–1.5h lunch) · Nuuanu Pali Lookout (WINDS 20–30m, $7 non-res parking, steps from car) · Byodo-In Temple (WINDS 45–60m, cash-ish admission, quiet respect) · Hoomaluhia garden drive (WINDS 45–90m, free, closes 4pm, no stopping on entrance road) · **Kualoa Ranch** (WINDN 2–3h/tour, 🎟 books out 2–4+ weeks — check availability IMMEDIATELY) · Chinaman's Hat viewpoint (WINDN 20–30m, free) · **Polynesian Cultural Center** (WINDN Laie, 4–8h, 🎟 closed Sun+Wed → only Thu/Fri/Sat this trip; opens 12:30, evening show ends ~9pm → ~10pm return) · Laie Point (WINDN 15m) · Dole Plantation (CEN 1–1.5h, mid-morning en route to NS, timebox it) · Haleiwa town + Matsumoto Shave Ice (NS 1–1.5h lunch) · Laniakea Turtle Beach (NS 20–30m, keep 10ft from turtles) · Waimea Bay + Waimea Valley (NS 1–3h; **late Aug = summer-flat, swimmable**; Valley = paid walk to swimmable falls, shuttle for parents; Bay lot fills by 10am) · Sharks Cove snorkel (NS 1.5–2h, summer AM, water shoes, rocky entry) · Sunset Beach/Pipeline (NS 30–90m golden hour) · Ko Olina Lagoons (KOOL 3–4h, calmest swim for parents, free lots fill 9–10am) · Luau — one of: Chief's/Paradise Cove (KOOL sunset oceanfront) · Ka Moana at Sea Life Park (EAST, closer) · Waikiki Starlight or Diamond Head Luau (WAI, **no-car night**) (2.5–3h, 🎟 book this week).

**Day templates (7 archetypes; description carries pacing note):**
1. **East Side Coastal Circle** (EAST→WINDS): Hanauma early slot → Halona → Sandy look → Makapuu → Kailua town lunch → Kailua Beach → Pali Lookout → home. ~90m total drive in short hops — friendliest big day for mixed mobility; needs the Hanauma T-2 reservation win.
2. **North Shore Classic Loop** (CEN→NS): depart 8am → Dole → Haleiwa lunch + shave ice → Laniakea turtles → Waimea Bay or Valley → Sharks Cove → Sunset Beach for sunset → home. ~2.5h drive — the longest driving day; front-load, keep Dole short.
3. **Pearl Harbor + Town History** (PRL→HNL): leave 7am → USS Arizona 8–9am → Missouri optional → Chinatown lunch → Iolani or Bishop → Tantalus sunset. ~60m drive, lowest physical demand.
4. **Windward Temples & Ranch** (WINDS→WINDN): Pali 9am → Byodo-In → Hoomaluhia → shrimp-truck lunch → Kualoa 1pm tour (pre-booked) → Chinaman's Hat → home. ~2h drive, gentle morning + seated afternoon.
5. **PCC / Laie Day** (WINDN): leave ~10:30 with coastal stops → PCC 12:30 open → villages → luau + evening show → home ~10pm. NOT Sun/Wed. Parents can skip the show and leave at 6.
6. **West Side Wind-Down + Luau** (KOOL): lagoons by 9:30am (parking!) → swim + resort lunch → optional Waikele outlets → sunset luau → home vs zero traffic. ~90m drive; the recovery-day-with-a-finale.
7. **Waikiki No-Car Day** (WAI): Diamond Head sunrise (rideshare) → KCC market if Sat → beach/surf lesson → Zoo/Aquarium or pool → Kuhio hula show / in-Waikiki luau. Zero drive; schedule after a big-drive day.
Sequencing rule (in template copy): interleave big-drive days (2, 5) with home-base/town days (3, 7); never stack 2 and 5 back-to-back.

**Restaurants (real family recs; recommended_by set, created_by null; dish tips → notes; dedupe Maguro Brothers + Island Vintage Coffee across sources and credit both):**
- *via Erica's mom's friends:* Liliha Bakery · Siam Garden Cafe · Hong Yun Chinese · Maguro Brothers · Yogurt Story · Fukurou · Koko Head Cafe (French Toast) · Lobster King (jja-jang-myeon/champong) · Kuro Tonkatsu · Han Gang (냉면) · Broke Da Grindz · Yoshitsune · Shiro's Simon · Don Quixote · Da Ono Hawaiian · Red Fish Poke · Island Vintage Coffee · Helena's Hawaiian Food · Tanaka of Tokyo · Giovanni's Shrimp (NS) · Tsurutontan Udon · Mitch's Sushi · 53 By the Sea · Yakitori Hachibei · Sugoi · Scratch · Ya Yas Chop House · The Signature Prime Steak & Seafood · Il Tappo · Ethel's Grill · Mahina and Sun's · Nico's Pier 38 / Fish Market · Takayuki. (Chief's Luau from this list → activities board.)
- *via Nick's parents:* Ono Seafood (#7 Spicy Ahi) · Maguro Spot · Foodland Ala Moana (poke) · Highway Inn Ala Moana (loco moco) · Ruscello at Nordstrom Ala Moana · Royal Hawaiian Hotel bakery (malasadas, not daily) · Leonard's (malasadas) · Island Vintage Coffee (açaí, Royal Hawaiian Center).
- Seed-curation task: map each to region (mostly WAI/HNL) + find Yelp URL + meal_tags.

**Members:** Nick, Erica, Ellyn, Mom, Dad. **Days:** the 6 dated days in Locked Decisions.

**Verify at seed time** (domain expert's low-confidence items): Hanauma parking fee, Pali $7 parking, Waimea Valley pricing.

## Deployment

1. New Railway service in the existing project, source = this repo, **Root Directory = `hawaii-planner`**, **watch paths = `hawaii-planner/**`** (Caltrain precedent — isolates deploys both directions).
2. Provision Railway Postgres; env vars: `DATABASE_URL` (reference var) + `LINK_TOKEN` (random string; the shared URL becomes `https://<app>/?k=<token>`). Local dev falls back to `sqlite:///./hawaii.db` — keep column types portable (CSV strings, not Postgres arrays — deliberate).
3. Migrations run only in startCommand (`alembic upgrade head && python -m app.seed && uvicorn ...`); seed is idempotent so matrix tweaks ship as ordinary commits.
4. After each push: verify with the `deploy-watch` skill (catches the alembic multi-head silent-failure gotcha).

## Execution plan

**Strategy: single agent, phases sequential** (tightly coupled greenfield: schema→API→timeline→frontend), with ONE parallel content-curation subagent during P0/P1 producing `seed/*.json` from this spec (pure content, zero code deps).

- **P0 — Walking skeleton:** scaffold from fitness/Caltrain patterns; FastAPI + static index; Alembic init; Railway service + Postgres + env vars; deployed health check + name picker. *Exit: live URL.*
- **P1 — Schema + seed:** all models/schemas/migration; idempotent seed from `seed/*.json`; bootstrap endpoint. *Exit: API returns seeded content.*
- **P2 — Boards + voting → SHIP LINK TO FAMILY:** Ideas + Food views, reaction pill + budget enforcement, Yelp/Maps link-outs, add/edit sheets, region grouping, freshness, polling. *Exit: family suggesting + voting — the real deadline.*
- **P3 — Itinerary builder:** timeline service (pytest FIRST — pure function), day views + spine, add/reorder/move, pins + warnings, cluster banners, day templates, desktop cockpit.
- **P4 — Polish:** drive-override stepper, empty states, detail sheets, real-phone mobile pass.

Commit per phase with pathspec discipline (`git commit -- hawaii-planner/` — concurrent sessions stage other work in this monorepo). After execution: run `/ship` (evaluate + simplify) — council-executed multi-layer work triggers the standing auto-QA rule; point `/evaluate` at `plans/COUNCIL_SUMMARY_hawaii-planner_2026-08-15.md`.

## Verification

1. `pytest` timeline: buffers, same-region hops, pins (late-arrival, leave_by, slack, free-time gaps), return leg + overpacked, closed-day warnings, drive overrides, empty day.
2. `pytest` API: vote-budget 409 + swap payload, idempotent claims/votes, atomic reorder, bulk-add tour ordering, token middleware 401s.
3. `ruff check` before every push.
4. Local run (SQLite) → browser walkthrough: name-picker → suggest → vote to the 4th star (swap sheet) → build a day → reorder → pin a lunch → hand-check recomputed times against the matrix.
5. Mobile: DevTools 375px + real iPhone against the Railway URL (tap targets, sheets, one-handed).
6. Two-device sync: vote on phone, desktop updates ≤20s.
7. `deploy-watch` green after each push.

## Booking urgency (independent of the app — act now)

- **Kualoa Ranch**: books out 2–4+ weeks; trip is ~11 days out — book immediately or accept leftovers.
- **USS Arizona**: 56-day window passed → daily next-day 3pm HST release or morning standby.
- **Hanauma Bay**: T-2 days at 7am HST, gone in minutes; only fits Thu 8/27–Sun 8/30. Set alarms.
- **Diamond Head** (non-residents): 30-day window open for all trip dates — book now.
- **PCC**: only Thu/Fri/Sat this trip. **Luaus**: book this week.
