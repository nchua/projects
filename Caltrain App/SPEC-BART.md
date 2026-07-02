# BART Expansion — Build Spec (v1)

Extend the Caltrain Commute Helper so BART station pairs sit alongside Caltrain pairs in
the same app: same dark departure-board UI, same favorites flow, same "leave by" hints —
so you never need to worry about being late on BART either.

**Design source of truth: `mockups/mockup.html`** — updated with a BART pair card, the
agency toggle in the add-pair row, and the needs-transfer empty state (all in the same
file as the approved Caltrain design).

- Facts about BART data sources in this document were **verified against the live feeds
  on 2026-07-02**. Raw captures live in `tests/fixtures/bart/` (see its README for the
  exact capture commands and what each fixture proves). Items marked **⚠ VERIFY** must
  be re-checked during implementation.

---

## 0. Goals & non-goals (v1)

Goals:

- BART favorites: pick any two BART stations, see the next direct trains with realtime
  departure, realtime (or schedule-projected) arrival, delay badge, and line color.
- BART service alerts in the same banner row as Caltrain alerts.
- Leave-by hints for BART cards when a BART station is the nearest station.
- Zero change to the Caltrain data path — the 511 client, its rate budget, and all
  existing endpoints keep working exactly as they do today.

Non-goals (v1):

- **No transfer itineraries.** 201 of the 1,225 BART station pairs share no line
  (verified from GTFS — e.g. Walnut Creek → Dublin/Pleasanton). v1 shows direct trains
  only, with an honest "needs a transfer" empty state (§9.3). Single-transfer routing is
  a designed-for v1.1 (GTFS `transfers.txt` exists in the BART feed) but out of scope.
- No BART fare info, platform numbers, or train-length/crowding display (the legacy ETD
  API has these — noted as a future enhancement in §12).
- No push notifications, accounts, or service worker — unchanged from the base app.
- Still no schedule *engine*: realtime supplies which trains run; static GTFS is only a
  per-trip lookup keyed by realtime-supplied trip_ids, exactly like the Caltrain §8a
  pattern.

---

## 1. Data-source decision (the load-bearing choice)

Three candidate sources were evaluated; the third wins decisively.

### 1.1 ~~511.org `agency=BA`~~ — REJECTED

Same API the app already uses for Caltrain, so it's tempting — but:

- **The 60 req/hr key budget is already spoken for.** Caltrain StopMonitoring at 60s TTL
  can demand up to 60 calls/hr on its own; the rolling guard trips at 55. Adding a second
  agency's StopMonitoring at any useful TTL pushes worst-case demand to ~132/hr against
  the same key — both agencies would degrade to stale data for long stretches, exactly
  what the current design exists to avoid.
- Unverifiable here: 511 requires the key for every call, so `agency=BA` response shape,
  join-key behavior, and horizon could not be captured. (511's Caltrain TripUpdates was
  already proven next-stop-only; no reason to expect BA is richer.)
- BART's native feeds make the whole problem moot — see 1.3.

### 1.2 ~~BART legacy ETD API as the primary source~~ — REJECTED (kept as future extra)

`https://api.bart.gov/api/etd.aspx?cmd=etd&orig=ALL&key=…&json=y` — one call returns
realtime estimates for all 49 stations (verified; fixture `etd_all.json`). Rich display
data: platform number, car length, hex line color, `cancelflag`, per-train delay.

Fatal flaw: **estimates carry no trip id** — they're minutes-countdowns grouped by
destination. There is no join key to resolve *arrival time at your destination*, which
is the core of the pair card. Also caps at ~3 estimates per destination grouping.
Keep for v1.1+ display extras (platform, train length); it needs a (free, instant)
personal key at https://api.bart.gov/api/register.aspx — the shared demo key
`MW9S-E7SL-26DU-VV8V` is fine for exploration only.

### 1.3 BART GTFS-Realtime TripUpdates + bundled static GTFS — **CHOSEN**

`https://api.bart.gov/gtfsrt/tripupdate.aspx` (GTFS-RT protobuf). All facts verified
live 2026-07-02 (fixture `tripupdate.pb`, 85 trip entities, captured 22:03 UTC):

- **No API key. No signup. No published rate limit.** (Stay polite anyway — §6.)
- **Full remaining-stop lists per trip** — median 14 `StopTimeUpdate`s, max 25 — with
  epoch arrival AND departure times plus per-stop `delay` seconds. This is the thing
  511's Caltrain TripUpdates couldn't do, and it makes the origin→destination join
  *realtime at both ends* for most pairs.
- **Includes trips that haven't started yet** (56 of 85 entities had a first stop more
  than 2 min out). Depth verified at Embarcadero: 43 future departures in one snapshot,
  reaching ~2 h ahead. Plenty for a "next 4–10 trains" card.
- `trip_id`s match BART's static GTFS `trips.txt` (75/85 in the capture; the other 10
  are eBART shuttle segments — §5.4). `stop_id`s are platform-level (`M16-1`) and 99/99
  resolved to static `stops.txt` platforms, each carrying `parent_station` (`EMBR`).
- **Truncation quirk (the one gap):** each trip's RT stop list is a contiguous suffix of
  its static stop sequence that usually ends **one stop short of the terminal** (58/75
  in the capture; 13 more end 2–3 short — the eBART tail, §5.4). Same class of problem
  as Caltrain's missing terminal arrivals, solved the same way: a bundled static lookup
  keyed by realtime trip_id (§5.3), except *simpler* — no service-date anchoring is
  needed at all, because RT gives epochs and the projection only needs the static
  *delta* between two stops of the same trip.

Static GTFS: `https://www.bart.gov/dev/schedules/google_transit.zip` — **both this URL
and the GTFS-RT endpoints redirect (301/307); always follow redirects.** Feed verified
2026-07-02: `feed_version 72`, valid 2026-01-12 → 2026-08-07, 50 parent stations, 237
platforms, 5,307 trips, 12 rail routes (6 lines × 2 directions) + 2 bus-bridge routes.

Alerts: `https://api.bart.gov/gtfsrt/alerts.aspx` (same protobuf dependency). Verified:
`header_text` is a useless generic "BART.gov Alert" — **the real message is in
`description_text`**; `active_period` and `informed_entity` were empty/unpopulated;
`cause`/`effect` are UNKNOWN. The feed carries evergreen promo noise (a "Tap and Ride"
ad posted as an alert, expiring 2037 per the legacy `bsa.aspx` mirror). Handling: §7.4.

---

## 2. Architecture (delta)

```
Browser (same PWA)
   │ same-origin fetch
   ▼
FastAPI on Railway
   ├── transit511.py ──► api.511.org        (Caltrain — UNCHANGED, keyed, 60/hr budget)
   └── bart.py ────────► api.bart.gov/gtfsrt (BART — no key, protobuf, own politeness cap)
```

- Same lazy-fetch philosophy: upstream is hit only when a frontend request arrives and
  the TTL cache is expired. No background polling.
- The two upstreams have **independent budgets** — a BART fetch never spends 511 quota
  and vice versa.
- New Python dependency: `gtfs-realtime-bindings>=1.0` (pulls in `protobuf`). Protobuf
  parsing is CPU-trivial at this size (40 KB feed); fetch stays async via httpx.

---

## 3. Project layout (new/changed files)

```
Caltrain App/
├── SPEC-BART.md                 # this file
├── app/
│   ├── upstream.py              # NEW: generic TTL cache + stampede lock + serve-stale,
│   │                            #      extracted from transit511.py (§6.1)
│   ├── transit511.py            # thinned: keeps 511 specifics, delegates caching
│   ├── bart.py                  # NEW: GTFS-RT fetch/parse client (§6.2)
│   ├── bart_pairs.py            # NEW: pure pair-join over parsed RT (§5) — mirrors departures.py
│   └── bart_stations.py         # NEW: loads data/bart_*.json, lookups (§4)
├── data/
│   ├── bart_stations.json       # NEW: 50 stations + platform→parent map (§4.1)
│   └── bart_trips.json          # NEW: pattern-deduped trip index, ~154 KB (§4.2)
├── scripts/
│   └── generate_bart_data.py    # NEW: regenerates both from BART GTFS (§4.3)
├── tests/
│   ├── fixtures/bart/           # captured 2026-07-02 — see its README.md
│   └── test_bart_*.py
└── requirements.txt             # + gtfs-realtime-bindings
```

Frontend files change in place (§9); no new frontend files.

---

## 4. Bundled data

### 4.1 `data/bart_stations.json`

```json
{
  "generated_at": "2026-07-02",
  "source": "https://www.bart.gov/dev/schedules/google_transit.zip",
  "feed_version": "72",
  "stations": [
    { "id": "embarcadero", "abbr": "EMBR", "name": "Embarcadero",
      "lat": 37.792874, "lon": -122.397020, "lines": ["Yellow", "Red", "Green", "Blue"] }
  ],
  "platforms": { "M16-1": "EMBR", "M16-2": "EMBR" }
}
```

- `id`: lowercase slug of the name (same convention as Caltrain ids). `abbr` is BART's
  4-char code (`EMBR`) = GTFS `parent_station` = GTFS `zone_id`.
- `lat`/`lon`: parent-station coords from `stops.txt` (`location_type == 1`; 50 of them,
  verified — matches the legacy `stn.aspx` list exactly).
- `lines`: the set of line names whose trips serve this station, derived from
  `stop_times.txt` × `trips.txt` × route map (§4.4). Used ONLY for the needs-transfer
  empty state (§9.3) — the actual pair join is trip-authoritative.
- `platforms`: platform `stop_id` → parent abbr, for resolving RT `stop_id`s. 237
  platform entries. (RT uses ids like `A10-1`, `M16-2`; parents like `LAKE`, `EMBR`.
  GTFS also contains oddballs like `MLBR_1`, `EMBR_1` — map them by `parent_station`
  like everything else; unknown RT stop_ids at runtime are skipped, never fatal.)
- **No NB/SB platform pairs and no `order` field** — BART is a branching network, not a
  line. Direction falls out of the trip join (§5.1) and is never inferred.

### 4.2 `data/bart_trips.json` — pattern-deduped trip index

Naive `{trip_id: {parent: arrival_seconds}}` for 5,307 trips is ~1.2 MB. Trips are
highly patterned: **89 distinct stop patterns** cover all of them (measured on feed
v72). So:

```json
{
  "generated_at": "2026-07-02",
  "feed_version": "72",
  "patterns": [ [["ANTC", 0], ["PCTR", 420], ["PITT", 900], "…"] ],
  "trips":    { "1842065": [17, 51300, "2"] }
}
```

- `patterns[i]` = ordered `[parent_abbr, seconds_offset_from_first_arrival]` pairs.
- `trips[trip_id]` = `[pattern_index, first_arrival_seconds_after_midnight, route_id]`.
- Measured size: **~154 KB** (29 KB gzipped). Checked in, like Caltrain's
  `trip_arrivals.json` (77 KB).
- `first_arrival_seconds` may exceed 86400 (3,243 stop_times rows have `24:xx+` clock
  times in feed v72) — **irrelevant to v1 lookups**, which only ever use *offsets
  between two stops of the same pattern* (§5.3). No service-date anchoring, no noon−12h
  trick, no calendar logic anywhere. (Keep the absolute start only so a future
  scheduled-fallback could use it; nothing in v1 reads it. **⚠ VERIFY at review: no
  code path anchors these to a date.**)

### 4.3 `scripts/generate_bart_data.py`

1. Download the GTFS zip (**follow redirects** — the URL 307s).
2. `stops.txt`: parents = `location_type == 1` → stations; every other stop with a
   `parent_station` → the `platforms` map. Slugify names for `id`.
3. `stop_times.txt` sorted by `(trip_id, stop_sequence)`, mapped to parents; build
   patterns + trips per §4.2. Exclude `BB-*` (bus bridge) route trips.
4. Derive per-station `lines` (§4.4) and station `lines` arrays.
5. Emit both files. Print pattern/trip/station counts for eyeballing; refuse to write
   if station count ≠ 50 without `--force` (schema-drift tripwire).

Re-run when BART changes schedules (feed v72 expires **2026-08-07** — expect a re-run in
early August; unknown trip_ids degrade gracefully in the meantime, §5.3).

### 4.4 Route → line map (GTFS `routes.txt`, feed v72 — verified)

| route_id | Line | GTFS hex | Dark-theme hex (mockup token) |
|---|---|---|---|
| 1, 2 | Yellow | `FFFF33` | `--b-yellow: #ffe14d` |
| 3, 4 | Orange | `FF9933` | `--b-orange: #ffa64d` |
| 5, 6 | Green | `339933` | `--b-green: #55c975` |
| 7, 8 | Red | `FF0000` | `--b-red: #ff7070` |
| 11, 12 | Blue | `0099CC` | `--b-blue: #4db8e8` |
| 19, 20 | Grey (OAK shuttle) | `B0BEC7` | `--b-grey: #b0bec7` |
| BB-A, BB-B | Bus Bridge | `000000` | excluded from data |

Odd route_id = one direction, even = the other ("Yellow-N"/"Yellow-S" in GTFS
`route_short_name`) — collapse both to the line name for display; direction is implied
by the pair itself. Unknown route_id at runtime → line `"BART"`, neutral pill color.

**Display label per departure: line + terminus derived from the pattern's last stop**
("Yellow · to Antioch") — NOT GTFS `trip_headsign`, which is rider-hostile
("SFO / SF / Antioch", "OAK Airport / SF / Daly City"; verified in feed v72).

---

## 5. Pair logic (`app/bart_pairs.py` — pure functions, unit-testable)

Given the parsed RT feed (a plain dict/list structure produced by `bart.py`, so these
functions never see protobuf objects) plus origin/destination station records:

### 5.1 The join — simpler than Caltrain's

1. Index the feed: `{trip_id: {parent_abbr: stu}}` where `stu` carries
   `{arrival_epoch, departure_epoch, delay_s}` and parent comes from the bundled
   `platforms` map. Unknown stop_id → skip that STU.
2. A trip serves the pair iff it has an STU at the origin parent with effective
   departure ≥ now − 30 s grace **and** a resolvable arrival at the destination parent
   **strictly later than** that departure. The "later than" check IS the direction
   filter — no NB/SB inference, no order field, and wrong-direction trains fall out
   naturally. (This also handles same-line-both-directions stations like the SFO/MLBR
   wye correctly, where compass direction would lie. **⚠ VERIFY with a live SFIA↔MLBR
   pair during implementation.**)
3. Sort by effective departure, take `limit` (same 4 default / 10 max).

### 5.2 Arrival resolution, in priority order

1. **RT STU at the destination parent** → realtime arrival (`expected` = epoch;
   `aimed` = epoch − delay). Most non-terminal destinations get this — fully realtime
   at both ends, better than the Caltrain path ever gets.
2. **Destination beyond the RT truncation** (terminal, usually): look the trip up in
   `bart_trips.json`. If the trip's pattern contains the destination *after* the
   origin: `arrival_epoch = last_RT_stu.arrival_epoch + (pattern_offset[dest] −
   pattern_offset[last_RT_stop])`, marked `"estimated": true`. Delta-based — no
   dates, no DST, no 24:xx handling.
3. **Pattern does not contain the destination** (e.g. a Yellow SFO short-turn that
   never reaches Millbrae) → exclude the row. Trip-pattern-authoritative, exactly like
   Caltrain's express-skip filter.
4. **trip_id unknown to the bundle** (GTFS revision rotated, or eBART shuttles §5.4)
   → include only if the destination parent appeared in the RT STUs (then it's case 1);
   otherwise exclude. Never crash on unknown trips.

### 5.3 Delay & status

- `delay_seconds` = the origin STU's `delay` field (verified populated per stop, e.g.
  866 s on a Green-line visit in the capture). `aimed = expected − delay`.
- Same thresholds and vocabulary as Caltrain: `late` ≥ 120 s, else `on_time`;
  `scheduled` only if the feed ever omits times (**⚠ VERIFY**: not observed — every
  captured STU had times; keep the branch defensively).
- BART cancellations: GTFS-RT `schedule_relationship` on the trip/STU (**⚠ VERIFY**
  values in a disrupted-service capture; the legacy ETD `cancelflag` suggests
  cancellations do surface somewhere). If a trip is marked CANCELED, drop it.

### 5.4 eBART / far-East-County caveat (verified)

RT Yellow-line through-trips end at Pittsburg/Bay Point (`C80`) or North Concord —
the Antioch extension (PCTR, ANTC) is realtime-covered only by separate shuttle trips
with trip_ids (`656`–`671` in the capture) that don't exist in static GTFS. Effect:

- Pairs INTO Antioch/Pittsburg Center resolve via rule 5.2(2) — schedule-projected from
  the through-trip's pattern (static patterns DO run through to ANTC). Honest but
  estimated; the delay used is the last known mainline delay.
- Pairs OUT of PCTR/ANTC get realtime departures from the shuttle STUs but usually
  can't resolve mainline arrivals (rule 5.2(4) excludes them). v1 accepts this: the
  empty state (§9.3) covers it. Flagged as a v1.1 item (join shuttle→mainline at PITT).

---

## 6. Backend — clients & caching

### 6.1 Extract the generic cache (`app/upstream.py`)

`transit511.py`'s TTL-cache + stampede-lock + serve-last-good-stale + rolling-hour-guard
machinery is agency-agnostic. Extract it, parameterized by `(cache_key, ttl_s,
fetch_coro, call_log, guard_max)` — each upstream gets its **own** call log and guard.
transit511.py keeps its constants and quirks (BOM decode, plain-text errors) and its
public API (`get_stop_monitoring()` etc.) unchanged; existing tests must pass untouched
except for import-path details. `UpstreamNeverFetchedError` moves to `upstream.py`
(re-exported from transit511 for compatibility).

### 6.2 `app/bart.py`

- `get_trip_updates() / get_alerts() -> (parsed, fetched_at, stale)` via the shared
  cache. **TTLs: tripupdates 30 s, alerts 300 s.** (30 s is justified: no key budget to
  protect, feed is 40 KB, and BART headways make 60 s feel laggy on a platform.)
- Politeness guard: `BART_GUARD_MAX_CALLS_PER_HOUR = 150` — same mechanism, generous
  ceiling (worst continuous case: 120 TU + 12 alert calls/hr = 132 < 150; the guard is
  a runaway-bug backstop, not a budget).
- Fetch with `follow_redirects=True` (verified required), 10 s timeout, shared
  `httpx.AsyncClient`.
- Parse protobuf **immediately at fetch time** into plain dicts (trips → STUs with
  epoch ints + delay; alerts → text/period dicts) and cache the *parsed* form —
  keeps pure logic protobuf-free and caches the (tiny) parse cost too. A protobuf
  `DecodeError` counts as a fetch failure → serve stale.

### 6.3 Startup

Load `bart_stations.json` + `bart_trips.json` once at import, like `stations.py` does.
`/api/health` and station listings never touch upstream (unchanged rule).

---

## 7. API changes

All existing endpoints keep their exact current behavior with no params — **deployed
frontends and saved favorites keep working during rollout.**

### 7.1 `GET /api/stations` → gains `agency` field per station

Response becomes `{"stations": [...], "bart_stations": [...]}` — the original key
untouched (old frontend ignores the new key). BART entries: `{id, abbr, name, lat,
lon, lines}`.

### 7.2 `GET /api/departures?agency=ba&origin=embarcadero&destination=antioch&limit=4`

- New optional `agency` param: `ct` (default) | `ba`. `ct` path is byte-identical to
  today. 400 `unknown_agency` otherwise.
- `ba` response shape (deltas from the Caltrain shape):

```json
{
  "agency": "ba",
  "origin":      { "id": "embarcadero", "abbr": "EMBR", "name": "Embarcadero" },
  "destination": { "id": "antioch", "abbr": "ANTC", "name": "Antioch" },
  "needs_transfer": false,
  "as_of": "…", "stale": false,
  "departures": [
    {
      "trip": "1842065",
      "line": "Yellow",
      "line_color": "#ffe14d",
      "headsign": "to Antioch",
      "departure": { "aimed": "…", "expected": "…" },
      "arrival":   { "aimed": "…", "expected": "…", "estimated": true },
      "delay_seconds": 91,
      "status": "on_time"
    }
  ]
}
```

- No `direction` field for BART (meaningless on a network); the card shows the line
  pill + headsign instead (§9.2). `train_type`/`line_ref_raw` are Caltrain-only;
  `line`/`line_color`/`headsign` are BART-only. Common fields keep identical names and
  semantics so the frontend row renderer stays one function with a small branch.
- `needs_transfer: true` (with `departures: []`) when the stations' bundled `lines`
  sets don't intersect — the frontend renders the transfer empty state instead of the
  sparse-service one. Line-set intersection is *advisory only* (the join itself is
  trip-authoritative); a pair can intersect yet have no direct trains right now.
- The `agency` field is echoed in every departures/alerts response so the frontend
  never guesses.

### 7.3 `GET /api/alerts?agency=ba` (and `agency=all`)

Default stays `ct` (unchanged). `ba` → parsed BART alerts; `all` → both, each entry
tagged `"agency"`. The new frontend fetches `all` in one request (replacing its `ct`
call — net zero extra frontend requests per refresh).

### 7.4 BART alert parsing

- Body text from `description_text` (the `header_text` is a generic "BART.gov Alert" —
  verified). Take the first ~120 chars of the description as the banner `header`
  (sentence-boundary truncated), full text as `description`.
- `active_period` was empty in the capture → treat missing periods as always-active
  (matches the existing Caltrain parser rule).
- **Promo noise**: evergreen advisories (fixture: a fare-payment ad, type "DELAY",
  expires 2037) can't be filtered by `effect` (always UNKNOWN). v1 ships them and
  relies on the existing per-session dismiss. v1.1 option: cross-check the legacy
  `bsa.aspx` `expires` field and drop anything expiring > 90 days out.

### 7.5 `GET /api/health`

`caches` block gains `bart_trip_updates` / `bart_alerts` entries plus
`bart_upstream_calls_last_hour`. Shape of existing keys unchanged.

---

## 8. Constants (new, alongside the existing block)

| Constant | Value |
|---|---|
| `BART_TRIP_UPDATES_TTL_S` | 30 |
| `BART_ALERTS_TTL_S` | 300 |
| `BART_GUARD_MAX_CALLS_PER_HOUR` | 150 |
| `BART_UPSTREAM_TIMEOUT_S` | 10 |
| (reused) `LATE_THRESHOLD_SECONDS` | 120 |
| (reused) `DEPARTURE_GRACE_S` | 30 |

---

## 9. Frontend spec (deltas — all hard requirements from §9.7 of SPEC.md still apply)

### 9.1 Favorites storage v2

- New key **`transit:favorites:v2`** → `[{"agency":"ct","origin":"san_carlos",
  "destination":"san_francisco"}, …]`. Cap stays 6 total across both agencies.
- **One-time migration**: if v2 is absent and `caltrain:favorites:v1` exists, copy each
  entry with `agency:"ct"`, write v2, leave v1 in place (rollback safety). Ignore
  entries whose ids aren't in the (agency-appropriate) station list, as today.
- `pairKey` becomes `agency:origin:destination`.

### 9.2 Cards

- Card head: pair names as today; the direction tag slot shows **`BART`** for BART
  cards (Caltrain cards keep NB/SB). Swap and remove behave identically.
- BART departure rows (mockup has the reference rendering):
  - Same amber LED time column, same late/scheduled treatments.
  - Type-pill slot → **line pill** in the line's dark-theme color (§4.4 tokens), text
    = line name. Train-number slot → **headsign** ("to Antioch") — BART trip numbers
    mean nothing to riders.
  - Arrival, delay badge, leave-by: identical logic and rendering. `estimated: true`
    arrivals render identically (same as Caltrain today).
- Feed-exhausted footer note and show-more expander work unchanged (BART's feed depth
  means the note should be rare outside late night).

### 9.3 Empty states (BART)

- `needs_transfer: true` → *"No direct trains — this pair needs a transfer. This app
  shows single-train trips only (for now)."*
- Otherwise → *"No upcoming trains for this pair right now."* (BART runs ~4 AM–midnight;
  overnight emptiness is normal. Antioch/Pittsburg Center pairs may also be sparse —
  §5.4.)

### 9.4 Add-pair row

- A segmented **Caltrain | BART** toggle above the selects (mockup shows it). Switching
  repopulates both selects: Caltrain list stays north→south; **BART list is
  alphabetical** (no linear order exists). Validation rules unchanged; the duplicate
  check includes agency.

### 9.5 Nearest station & leave-by

- Nearest = min haversine over the **union** of both agencies' stations (BART parent
  coords verified present). Chip unchanged visually.
- Leave-by hints appear on cards whose origin is the nearest station **of the matching
  agency** (`agency + id` match) — Millbrae/SFIA exist in both networks with distinct
  ids, so no cross-agency false positives. Walk-time math unchanged.

### 9.6 Alerts & refresh

- One `/api/alerts?agency=all` fetch per refresh; render BART alerts with a small
  `BART` tag in the banner, Caltrain ones untagged (as today). Session-dismiss by id
  unchanged (ids are per-agency-feed, fixture ids like `BSA_291898`).
- Refresh cycle, stale pill, and visibility rules unchanged. Each card's staleness
  comes from its own response; the header pill triggers if ANY response is stale, as
  today.

### 9.7 Branding

Header/manifest stay "Caltrain Commute" in this phase — renaming (e.g. "Bay Rail") is a
user decision, listed in §13. The BART tag on cards carries the disambiguation until
then.

---

## 10. Deploy

- Same Railway service, same root directory, same watch paths, same start command.
- `requirements.txt` += `gtfs-realtime-bindings>=1.0`.
- **No new env vars** (BART needs no key). `TRANSIT_511_API_KEY` untouched.
- Data files are checked in; the deployed app never downloads GTFS at runtime.

---

## 11. Verification plan

### Step 0 — fixtures: ALREADY CAPTURED (2026-07-02)

`tests/fixtures/bart/` — raw bytes, with a README recording the exact curl commands,
capture time, and the verified facts each file proves (trip-suffix truncation stats,
EMBR depth, eBART shuttle ids, alert noise, …). Re-capture during implementation only
if the feed version has rotated.

### Step 1 — unit tests (pytest, fixtures fed as verbatim bytes)

- Protobuf feed parses; entity/STU counts match the capture (85 / median 14).
- Platform→parent resolution incl. unknown stop_ids (skipped, non-fatal).
- Pair join EMBR→WCRK: realtime arrival at destination (rule 5.2-1).
- Pair join into a truncated terminal: delta projection, `estimated: true`, and the
  arrival-after-departure sanity (rule 5.2-2).
- Short-turn exclusion: trip whose pattern lacks the destination is dropped (5.2-3).
- Unknown trip_id (use `656`): included only when destination is in RT STUs (5.2-4).
- Wrong-direction exclusion falls out of arrival>departure (no direction code paths).
- `needs_transfer` for WCRK→DUBL (Yellow ∩ Blue = ∅ — verified pair).
- Delay/status thresholds on the captured 866 s Green-line delay.
- Alerts: description-as-body, generic-header override, no-period ⇒ active.
- Cache: stale-serving and politeness guard on the BART call log (mirrors existing
  511 tests); **511 tests still green after the §6.1 extraction**.
- Generator: pattern dedup round-trips (rebuild naive from patterns for 20 random
  trips and compare against stop_times).

### Step 2 — local end-to-end

```bash
uvicorn app.main:app --port 8000    # no BART key needed — works immediately
curl -s "localhost:8000/api/departures?agency=ba&origin=embarcadero&destination=walnut_creek" | python3 -m json.tool
curl -s "localhost:8000/api/departures?agency=ba&origin=embarcadero&destination=antioch" | python3 -m json.tool   # estimated arrivals
curl -s "localhost:8000/api/departures?agency=ba&origin=walnut_creek&destination=dublin_pleasanton" | python3 -m json.tool  # needs_transfer
curl -s "localhost:8000/api/alerts?agency=all" | python3 -m json.tool
```

Browser: add a BART pair via the toggle, verify line pill colors, headsign, PT times,
migration of existing favorites, and that Caltrain cards are pixel-unchanged.
Cross-check a live BART card against bart.gov/schedules real-time departures.

### Step 3 — deploy check

Push → Railway build (watch for the new dependency) → `/api/health` shows the new cache
entries → phone: add BART pair, confirm times, delay badge against the platform sign on
an actual ride. The true acceptance test: catch a Yellow-line train you didn't have to
run for.

---

## 12. Future (explicitly out of v1)

1. **Single-transfer itineraries** for the 201 no-shared-line pairs (GTFS
   `transfers.txt` + the same trip join twice; the empty state already funnels here).
2. eBART shuttle→mainline stitch at Pittsburg/Bay Point (§5.4).
3. ETD extras via a personal BART API key: platform number, car count, cancellations.
4. Promo-alert filtering via legacy `bsa.aspx` expiry (§7.4).
5. Rename/rebrand PWA once BART proves itself (§9.7).

---

## 13. Open questions for the user

1. Keep the app named "Caltrain Commute" for now, or rename with the BART launch?
2. Is Walnut Creek → Dublin-style transfer routing wanted soon (v1.1), or is
   direct-trains-only fine indefinitely?
3. 30 s BART TTL doubles BART-feed politeness cost vs 60 s — fine as specced, or match
   Caltrain's 60 s for symmetry?
