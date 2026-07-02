# Caltrain Commute Helper — Build Spec (v1)

A personal, single-user Caltrain web app: see system delays, the next trains for favorite
station pairs (e.g., San Carlos → San Francisco), and a "leave by" hint based on walking
distance to the nearest station. Reachable from phone + desktop; pinnable to the phone
home screen as a PWA.

**Design source of truth: `mockups/mockup.html`** (dark departure-board aesthetic,
approved by the user). Match its layout, colors, and states — this spec describes
behavior; the mockup describes look and feel.

- Facts about the 511.org API in this document were verified against the live API on
  **2026-07-01**. Items marked **⚠ VERIFY** must be re-checked against captured fixtures
  during implementation (see [Verification plan](#12-verification-plan)).

---

## 0. Non-goals (v1)

- No accounts, no database — favorites live in `localStorage`.
- No service worker / offline mode (PWA manifest only, for add-to-home-screen).
- No map, no routing API — walking time is a haversine estimate.
- No static-GTFS schedule *engine* (24:xx times + calendar/holiday complexity trap).
  Realtime StopMonitoring is the only source of *which trains are running*. If a pair
  has no upcoming realtime trains, the app says so — normal on weekends / South County.
  (A narrow static *lookup* — scheduled arrival by realtime-supplied trip_id — IS in
  scope; see §8a. It involves zero calendar inference.)
- No push notifications, no multi-agency support.
  (Multi-agency is no longer a non-goal: the BART expansion is specced in
  **`SPEC-BART.md`** — verified 2026-07-02 against BART's native GTFS-Realtime feeds,
  which need no API key and don't touch the 511 rate budget.)

---

## 1. Prerequisite

A free 511.org Open Data API token: sign up at **https://511.org/open-data/token**.
The key goes in the Railway env var `TRANSIT_511_API_KEY` (never committed).

**Rate limit: 60 requests per rolling 3600 seconds, TOTAL across all endpoints per key.**
The entire backend design below exists to respect this.

---

## 2. Architecture

```
Browser (vanilla HTML/JS, PWA manifest)
   │  same-origin fetch (no CORS needed)
   ▼
FastAPI on Railway  ──  holds TRANSIT_511_API_KEY, TTL-caches upstream
   │
   ▼
api.511.org  (StopMonitoring all-stops + servicealerts, JSON)
```

- FastAPI serves both the JSON API (under `/api/*`) and the static frontend
  (`frontend/` mounted at `/`, **registered after the API routes**).
- The backend fetches upstream **lazily** — only when a frontend request arrives and the
  cache is expired. No background polling.
- All times sent to the frontend are ISO-8601 strings with explicit offset/Z. The
  frontend renders them in `America/Los_Angeles` via `Intl.DateTimeFormat`
  (Railway containers run UTC — never rely on server local time).

---

## 3. Project layout

```
Caltrain App/
├── SPEC.md                      # this file
├── mockups/
│   ├── mockup.html              # approved visual reference
│   └── preview.html             # side-by-side mobile/desktop review page
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, routes, static mount
│   ├── transit511.py            # upstream client: TTL cache, locks, rate guard, BOM decode
│   ├── departures.py            # StopMonitoring parsing + pair-join logic (pure functions)
│   ├── schedule.py              # static per-trip arrival lookup (see §8a)
│   └── stations.py              # loads data/stations.json, lookups, direction calc
├── data/
│   ├── stations.json            # checked in, 30 stations (see §4)
│   └── trip_arrivals.json       # checked in, {trip_id: {stop_code: arrival_seconds}}
├── scripts/
│   └── generate_data.py         # regenerates both data files from Trillium GTFS
├── frontend/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.webmanifest
│   └── icons/                   # icon-192.png, icon-512.png (maskable)
├── tests/
│   ├── fixtures/                # captured real 511 responses (raw bytes, BOM intact)
│   └── test_*.py
├── requirements.txt
├── railway.json                 # or Procfile
└── .env.example                 # TRANSIT_511_API_KEY=
```

`requirements.txt` (Python 3.11+):

```
fastapi>=0.115
uvicorn[standard]>=0.30
httpx>=0.27
pytest>=8
pytest-asyncio>=0.23
respx>=0.21
```

---

## 4. Stations data (`data/stations.json`)

### 4.1 Shape

```json
{
  "generated_at": "2026-07-01",
  "source": "https://data.trilliumtransit.com/gtfs/caltrain-ca-us/caltrain-ca-us.zip",
  "stations": [
    { "id": "san_francisco", "name": "San Francisco", "lat": 37.7764, "lon": -122.3945,
      "stop_nb": "70011", "stop_sb": "70012", "order": 0 },
    { "id": "san_carlos", "name": "San Carlos", "lat": 37.5079, "lon": -122.2605,
      "stop_nb": "70131", "stop_sb": "70132", "order": 12 },
    { "id": "san_jose_diridon", "name": "San Jose Diridon", "lat": 37.3297, "lon": -121.9026,
      "stop_nb": "70261", "stop_sb": "70262", "order": 25 }
  ]
}
```

- `id`: lowercase slug of the name (`[a-z0-9_]`).
- `lat`/`lon`: **parent station** coordinates from GTFS (not platform coords).
- `stop_nb` / `stop_sb`: 511 stop codes. Pattern: each station has NB code `70XX1` and
  SB code `70XX2` (verified live for SF `70011/70012`, San Carlos `70131/70132`,
  SJ Diridon `70261/70262`; the rest follow the pattern — the generator reads them from
  GTFS rather than assuming).
- `order`: derive as `(int(stop_nb) - 70011) // 10`. Codes increase southward, so order
  is monotonic north→south with SF = 0. Gaps (from excluded stations) are fine — only
  relative comparison is used.

### 4.2 Station list (2026 GTFS — expect 30 stations)

SF · 22nd Street · Bayshore · South San Francisco · San Bruno · Millbrae ·
Broadway (weekend-only) · Burlingame · San Mateo · Hayward Park · Hillsdale · Belmont ·
San Carlos · Redwood City · Menlo Park · Palo Alto · California Avenue · San Antonio ·
Mountain View · Sunnyvale · Lawrence · Santa Clara · College Park · San Jose Diridon ·
Tamien · Capitol · Blossom Hill · Morgan Hill · San Martin · Gilroy.

Notes: **no Atherton** (closed). **Exclude Stanford Stadium** (game-day only) and any
shuttle/elevator/entrance stops. Broadway appears but has weekend-only service; South
County branch (Capitol→Gilroy) is weekday-rush only — empty results for these pairs are
normal, not bugs.

### 4.3 `scripts/generate_data.py`

1. Download `https://data.trilliumtransit.com/gtfs/caltrain-ca-us/caltrain-ca-us.zip`
   (no API key needed).
2. Parse `stops.txt`. Platform stops have a numeric `stop_code` in the `70011–70322`
   range and a `parent_station`; parents have `location_type == 1`.
   **⚠ VERIFY** exact parent naming/structure in the current GTFS before trusting this.
3. Group platforms by parent; NB = code ending in `1`, SB = ending in `2`. Skip any
   station lacking both. Skip Stanford Stadium (`70181/70182`). Strip suffixes like
   " Caltrain Station" / " Station" from names.
4. Emit `data/stations.json` sorted by `order`, with parent-station lat/lon.
5. Also emit `data/trip_arrivals.json` from `stop_times.txt` (see §8a).

The script is run manually when Caltrain changes stations or schedules; its outputs are
checked in so the deployed app never needs GTFS at runtime.

---

## 5. 511.org API — endpoints and quirks (verified 2026-07-01)

### 5.1 Endpoints

| Purpose | URL |
|---|---|
| **Primary — realtime, all Caltrain stops in ONE call** | `https://api.511.org/transit/StopMonitoring?api_key=KEY&agency=CT&format=json` (omit `stopcode` entirely) |
| **Service alerts** (GTFS-RT JSON) | `https://api.511.org/transit/servicealerts?api_key=KEY&agency=CT&format=json` |
| ~~TripUpdates fallback~~ **REJECTED (verified live 2026-07-01):** each TripUpdate carries only ONE StopTimeUpdate — the trip's *next* stop. It cannot resolve terminal or beyond-horizon arrivals. Use the bundled schedule lookup (§8a) instead. | `https://api.511.org/transit/tripupdates?api_key=KEY&agency=CT&format=json` |

### 5.2 Transport quirks (all confirmed live)

- **Responses start with a UTF-8 BOM.** Decode with `resp.content.decode("utf-8-sig")`
  then `json.loads(...)`. Do **not** use `resp.json()`.
- Responses are gzipped; `httpx` handles this transparently.
- Always pass `format=json` — default is XML.
- **Error bodies are plain text**, not JSON (e.g. 401 → `The API key is not provided.`).
  Treat any non-200 as a failure; never try to JSON-parse it.
- **Top level is `ServiceDelivery` with NO `Siri` wrapper** — but accept both
  `payload["ServiceDelivery"]` and `payload["Siri"]["ServiceDelivery"]` defensively.
- `StopMonitoringDelivery` may be an object **or** a single-element list.
  `MonitoredStopVisit` may be a **single object instead of an array** when only one
  visit exists. Normalize everything with an `ensure_list(x)` helper.
- Rate limit: **60 requests / 3600s TOTAL across all endpoints per key.**
  **⚠ VERIFY** what a 429 actually looks like (headers/body) if ever observed — but the
  guard in §6 should make it unreachable.

### 5.3 StopMonitoring structure and key fields

```
ServiceDelivery                        (or Siri.ServiceDelivery — accept both)
└── StopMonitoringDelivery             (object OR 1-element list)
    └── MonitoredStopVisit             (list OR single object)
        ├── MonitoringRef              stop code (sometimes present at visit level)
        └── MonitoredVehicleJourney
            ├── LineRef                train type (see §5.4)
            ├── DirectionRef
            ├── FramedVehicleJourneyRef.DatedVehicleJourneyRef
            │                          ← TRAIN NUMBER = GTFS trip_id.
            │                            THE JOIN KEY between origin and
            │                            destination visits.
            └── MonitoredCall
                ├── StopPointRef       stop code  ⚠ VERIFY field name in the
                │                      all-stops fixture; fall back to MonitoringRef
                ├── AimedArrivalTime / ExpectedArrivalTime      (RFC3339)
                └── AimedDepartureTime / ExpectedDepartureTime  (RFC3339)
```

- **Delay = Expected − Aimed** (departure times, at the origin stop).
- `Expected*` **may be null** → render as a scheduled-only row (gray badge), never drop.
- Timestamps are RFC3339 with zone info — compare as full datetimes, **never clock
  times** (midnight-crossing trips exist and are safe under full-datetime comparison).
- **StopMonitoring omits arrival-only stops (verified live 2026-07-01):** it is a
  *departures* board, so a trip's terminal stop never appears as a visit — e.g. San
  Francisco (70011) has NO inbound visits even for trains whose `DestinationRef` is
  70011. Any pair ending at a terminal (including the flagship San Carlos → SF commute)
  must resolve arrivals via §8a.
- **Visit horizon ≈ 90 minutes (verified same capture):** a train's future visits are
  truncated ~90 min out, so even mid-route destination visits can be missing for
  later departures. Same §8a fallback applies.

### 5.4 Train types (GTFS `routes.txt`, 2026)

| Type | GTFS route color | Realtime `LineRef` code |
|---|---|---|
| Local (Weekday & Weekend variants) | `#dcddde` | `LOC` |
| Limited | `#99d7dc` | `LIM` |
| Express | `#ce202f` | `EXP` |
| South County | `#fae4a7` | `SCC` |

Normalize `LineRef` **case-insensitively by substring**, checking in this order:
`exp` → Express, `lim` → Limited, `scc`/`south` → South County, `loc` → Local (both
"Local Weekday" and "Local Weekend" → "Local"). Handles both long forms ("Limited") and
codes ("LIM"). No match → pass the raw string through. **⚠ VERIFY** the exact distinct
`LineRef` values in the captured fixture and add them to a test.

### 5.5 Behavioral gotchas

- **Holidays run the weekend schedule** — never infer schedule from day-of-week.
- **Trains can vanish from the realtime feed near their last stops** — handle missing
  entries; a lookup miss is normal, not an error.
- Weekend/South County service is sparse; an empty pair result is a valid state with its
  own UI, not a failure.

---

## 6. Backend — caching & rate-limit design (`app/transit511.py`)

Hard requirement: **never exceed the 60 req/hr key limit**, even with the page open all
day, even with multiple tabs.

1. **Lazy fetch only.** Upstream is called only from request handlers when the cache is
   expired. No background tasks, no polling loops.
2. **Per-upstream-URL TTL cache** (module-level dict):
   `{url: {"payload": dict, "fetched_at": datetime}}`.
   - StopMonitoring TTL: **60s**
   - servicealerts TTL: **300s**
3. **Stampede lock**: one `asyncio.Lock` per URL. After acquiring, re-check TTL before
   fetching (double-checked locking) so concurrent requests trigger at most one fetch.
4. **Rolling-hour guard**: a module-level `deque` of upstream call timestamps; before
   any fetch, prune entries older than 3600s; if `len >= 55`, **skip the fetch and serve
   last-good as stale**. (Worst case at continuous use: ≤60 SM + ≤12 alerts calls/hr =
   72 > 60, so the guard will trip and data degrades to stale for stretches — that is
   the intended behavior, never a 429.)
5. **Failure = serve last-good.** On timeout (10s), non-200, or JSON decode error:
   return the cached payload with `stale=True`. Only if there has **never** been a
   successful fetch, raise → endpoint returns **502**.
6. No retries in v1 (retries spend rate budget); staleness is the fallback.
7. API functions return `(payload: dict, fetched_at: datetime, stale: bool)`:
   `get_stop_monitoring()`, `get_service_alerts()`.
8. `/api/health` and `/api/stations` must **never** trigger upstream calls.

---

## 7. Backend — endpoints & response shapes

Error shape everywhere: `{"error": {"code": "...", "message": "..."}}`.

### 7.1 `GET /api/health`

Always 200, fast, no upstream calls:

```json
{
  "status": "ok",
  "upstream_calls_last_hour": 7,
  "caches": {
    "stop_monitoring": { "age_seconds": 23, "have_data": true },
    "alerts": { "age_seconds": 141, "have_data": true }
  }
}
```

### 7.2 `GET /api/stations`

Serves the bundled `data/stations.json` verbatim (`{"stations": [...]}`), loaded once at
startup. 200 always.

### 7.3 `GET /api/departures?origin=<id>&destination=<id>&limit=4`

- `origin`/`destination`: station ids from §4. 400 `unknown_station` if not found;
  400 `same_station` if equal. `limit`: 1–10, default 4.
- 502 `upstream_unavailable` only if 511 has never been successfully fetched.

```json
{
  "origin":      { "id": "san_carlos", "name": "San Carlos", "stop_code": "70131" },
  "destination": { "id": "san_francisco", "name": "San Francisco", "stop_code": "70011" },
  "direction": "NB",
  "as_of": "2026-07-01T15:12:03+00:00",
  "stale": false,
  "departures": [
    {
      "train": "417",
      "train_type": "Limited",
      "line_ref_raw": "LIM",
      "departure": { "aimed": "2026-07-01T15:14:00+00:00",
                     "expected": "2026-07-01T15:19:00+00:00" },
      "arrival":   { "aimed": "2026-07-01T15:57:00+00:00",
                     "expected": "2026-07-01T16:02:00+00:00" },
      "delay_seconds": 300,
      "status": "late"
    }
  ]
}
```

- `as_of` = when the underlying StopMonitoring payload was fetched (cache timestamp) —
  the frontend uses it for "Updated Xs ago" and the stale pill.
- `arrival` is `null` when unresolvable (times missing/unparseable, or trip unknown to
  the bundled GTFS) — frontend renders "—". Schedule-derived arrivals (§8a) carry an
  extra `"estimated": true` field; the frontend renders them identically today.
- `status`: `"late"` (realtime, `delay_seconds >= 120`), `"on_time"` (realtime,
  `< 120`), `"scheduled"` (no `Expected*` → `delay_seconds: null`).
  `LATE_THRESHOLD_SECONDS = 120` is a named constant.
- All timestamps re-serialized via parsed aware datetimes (`.isoformat()`), never passed
  through as raw strings.

### 7.4 `GET /api/alerts`

GTFS-RT service alerts, flattened:

```json
{
  "as_of": "2026-07-01T15:10:00+00:00",
  "stale": false,
  "alerts": [
    {
      "id": "alert-1234",
      "header": "Signal maintenance — Millbrae",
      "description": "Northbound trains delayed up to 15 minutes…",
      "active_period": { "start": "2026-07-01T13:00:00+00:00", "end": null }
    }
  ]
}
```

Parsing: `entity[].alert`, header/description from `*_text.translation[]` picking the
`en` (or first) entry; epoch seconds in `active_period` → ISO strings. Only include
currently-active alerts (start ≤ now ≤ end, or open-ended).
**⚠ VERIFY GTFS-RT JSON casing** — keys may be `header_text` (snake) or `headerText`
(camel); read via a helper that tries both.

### 7.5 Static frontend

`app.mount("/", StaticFiles(directory="frontend", html=True))` — registered **after**
all `/api` routes so it never shadows them.

---

## 8. Pair logic (`app/departures.py` — pure functions, unit-testable)

Given the all-stops StopMonitoring payload plus origin/destination station records:

1. **Direction**: `origin.order > destination.order` → `NB` (toward SF, order 0), else
   `SB`. Pick platform codes accordingly: NB → `stop_nb` for both ends; SB → `stop_sb`.
2. **Index the payload**: walk all visits (after `ensure_list` normalization at every
   level per §5.2) and build `{train_number: {stop_code: visit}}` where
   `train_number = MonitoredVehicleJourney.FramedVehicleJourneyRef.DatedVehicleJourneyRef`
   and `stop_code = MonitoredCall.StopPointRef` (fallback: visit-level `MonitoringRef`).
3. **Upcoming at origin**: visits at the origin platform whose effective departure
   (`Expected` if present, else `Aimed`) ≥ now − 30s grace. Sort by effective departure,
   take `limit`.
4. **Join to destination** — arrival resolution in priority order:
   1. The train's realtime visit at the destination platform →
      `AimedArrivalTime`/`ExpectedArrivalTime`. (Visit exists but times
      missing/unparseable → keep the row with `arrival: null` — **never drop it**.)
   2. No destination visit (terminal stop or beyond the ~90-min horizon, §5.3) →
      the bundled schedule lookup (§8a): if the trip's GTFS stop list *contains* the
      destination, arrival = scheduled arrival + the train's current `delay_seconds`,
      marked `"estimated": true`; if it does *not*, **exclude the row** (the
      express-skips-station filter, now schedule-authoritative).
   3. Trip unknown to the bundled GTFS (revision rotated): keep the row with
      `arrival: null` if `MonitoredVehicleJourney.DestinationRef` equals the
      destination stop code, else exclude.
5. Compute `delay_seconds`, `status`, `train_type` per §5.4/§7.3.

No day-of-week logic, no clock-time comparison — full datetimes only.

## 8a. Static per-trip arrival lookup (`app/schedule.py` + `data/trip_arrivals.json`)

Exists because neither realtime feed carries terminal arrivals (§5.1, §5.3). This is
**not** a schedule engine: trips are looked up only by trip_id + service date that the
realtime feed itself supplies, so no calendar/service-day inference ever happens.

- `data/trip_arrivals.json`: `{trip_id: {platform_stop_code: arrival_seconds}}`,
  generated by `scripts/generate_data.py` from GTFS `stop_times.txt` (70xxx stops
  only; ~260 trips, ~77 KB). Checked in alongside `stations.json`.
- GTFS trip_id == train number == `DatedVehicleJourneyRef` (verified: realtime train
  169 ↔ GTFS trip 169, terminal 70011 arr 23:16).
- GTFS times may exceed 24:00 (204 such rows) — convert to a datetime by anchoring at
  **noon − 12 h** on the service date in `America/Los_Angeles` (DST-safe), where the
  service date is the visit's `FramedVehicleJourneyRef.DataFrameRef` (fall back to the
  departure's PT date).
- Estimated expected arrival = scheduled + origin `delay_seconds`; scheduled-only rows
  get `expected: null`. Sanity guard: a schedule-derived arrival earlier than the
  aimed departure → `arrival: null` instead.
- trip_ids rotate with GTFS revisions → unknown trips degrade to `arrival: null`
  ("—" in the UI). Re-run `scripts/generate_data.py` when Caltrain changes schedules.

---

## 9. Frontend spec (`frontend/`)

Layout, colors, and all visual states: **match `mockups/mockup.html`**.
Mobile-first single column ≤640px; desktop ≥900px renders favorites as a card grid.

### 9.1 State & startup

- Favorites in `localStorage` key **`caltrain:favorites:v1`** →
  `[{"origin":"san_carlos","destination":"san_francisco"}, …]`. Cap at 6; ignore/drop
  entries whose ids aren't in `/api/stations`.
- On load: fetch `/api/stations` once (in-memory), render favorite cards (skeleton
  state), then refresh data (§9.4). First run (no favorites): show the add-pair row with
  a short hint, no cards.

### 9.2 Favorite cards

Per card (see mockup): pair title ("San Carlos → San Francisco"), direction tag (NB/SB),
per-card **swap** (reverse the pair, persist, refetch) and **remove** (✕, immediate)
buttons, and up to 4 departure rows (default; a **"Show more"** footer button expands the
card to 10 rows session-only, "Show fewer" collapses it). When the feed returns fewer
rows than the shown limit, the card footer notes *"That's every upcoming train in the
live feed right now."* — expected late at night, when the last trains of the day are the
only ones the realtime feed knows about:

- Big tabular-numeral **effective departure time** (expected, else aimed). When late,
  show struck-through scheduled time beside it.
- Train type pill (colors from §5.4 adapted to dark theme per mockup) + train number.
- Arrival at destination ("arrives 9:02 AM", or "—" when `arrival: null`).
- Delay badge: red `+N min` (late), green `On time`, gray `Scheduled`.
- **Leave-by hint** (§9.3) when applicable.

Empty pair state (verbatim tone from mockup): *"No upcoming trains for this pair right
now. Weekend and South County service is sparse — this is often normal."*
Fetch-failure state per card: "Can't reach the server" + retry button.

### 9.3 Nearest station & leave-by hints

- `navigator.geolocation.getCurrentPosition` (`maximumAge: 120000, timeout: 8000`).
  Denied/unavailable → hide the chip entirely and show no hints; never block rendering.
- Nearest station: min haversine distance over all stations.
  `walk_minutes = ceil(meters × 1.3 / 80)` (1.3 detour factor, 80 m/min).
- Chip: "Nearest station: **San Carlos** · ~7 min walk".
- **Leave-by** per departure row: `effective_departure − walk_minutes − 2 min buffer`,
  shown **only** on cards whose origin is the nearest station and `walk_minutes ≤ 30`
  (otherwise walking there isn't realistic and the hint is noise).

### 9.4 Refresh cycle

- Refresh = parallel fetch of `/api/departures` for every favorite + `/api/alerts`
  (`fetch(…, {cache: "no-store"})`).
- `setInterval` 60s, skipped while `document.hidden`.
- On `visibilitychange` → visible: refresh immediately if last refresh > 30s ago.
- Manual refresh button in the header (spins during fetch).
- Header shows "Updated just now / Xm ago" from the newest `as_of`.
- **Stale pill**: if any response has `stale: true`, show the header pill
  "Live data unavailable — showing HH:MM data" (style per mockup). Clears on the next
  non-stale response.

### 9.5 Alerts banner

Render each active alert from `/api/alerts` as a banner (amber, warning icon) above the
cards, per mockup. Dismiss (✕) hides an alert `id` for the session (in-memory only).
No alerts → section hidden.

### 9.6 Add / remove / swap flows

Add row (per mockup): origin `<select>` + swap ⇄ button + destination `<select>` + red
**Add** button. Selects list all stations north→south. Validation: origin ≠ destination,
pair not already saved, ≤6 favorites — violations flash the row, don't alert().
New card appends immediately with skeleton → data.

### 9.7 Frontend conventions — HARD REQUIREMENTS

1. **No inline `onclick`.** One delegated listener on `document.body`; handlers resolve
   the target via `e.target.closest("[data-action]")`.
2. State/ids via `data-*` attributes only.
3. `touch-action: manipulation` on all interactive elements.
4. Touch targets ≥ **44×44px**.
5. `:active` press feedback (e.g., `transform: scale(0.96)`), plus
   `-webkit-tap-highlight-color: transparent` and `-webkit-appearance: none` on
   buttons/selects.
6. **All times rendered via `Intl.DateTimeFormat("en-US", {timeZone: "America/Los_Angeles", …})`** —
   never `toLocaleTimeString()` bare, never server-local assumptions.
7. Vanilla JS, no framework, no build step. `style.css` uses custom properties matching
   the mockup's token block.

### 9.8 PWA

`manifest.webmanifest`: `name: "Caltrain Commute"`, `short_name: "Caltrain"`,
`start_url: "/"`, `display: "standalone"`, `background_color`/`theme_color` matching the
mockup background (`#0f1114`), icons 192 + 512 (`purpose: "any maskable"` — a simple
red-square "C" mark is fine, generated by any script/tool). `index.html` includes
`<meta name="theme-color">`, `apple-touch-icon`, and
`apple-mobile-web-app-capable`/`status-bar-style` metas. **No service worker in v1.**

---

## 10. Deploy (Railway)

- **Recommended: monorepo subdir** of `nchua/projects` (matches the existing fitness-app
  workflow — push to `main` auto-deploys). Create a new Railway service pointed at the
  repo with **Root Directory = `Caltrain App`**. Set **watch paths** to
  `Caltrain App/**` so fitness pushes don't rebuild this service (and vice versa).
  ⚠ If the space in the directory name gives Railway trouble, rename the folder to
  `caltrain-app` and update the root directory — do this early, before wiring the URL
  into the phone.
  (Alternative: a fresh dedicated repo — clean but adds a second push target; not
  recommended.)
- Env var: `TRANSIT_511_API_KEY` (from §1). `.env.example` documents it.
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Healthcheck path: `/api/health`

`railway.json`:

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/api/health",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

---

## 11. Constants (single module-level block, named)

| Constant | Value |
|---|---|
| `STOP_MONITORING_TTL_S` | 60 |
| `ALERTS_TTL_S` | 300 |
| `RATE_GUARD_MAX_CALLS_PER_HOUR` | 55 |
| `UPSTREAM_TIMEOUT_S` | 10 |
| `LATE_THRESHOLD_SECONDS` | 120 |
| `DEPARTURE_GRACE_S` | 30 |
| `DEFAULT_LIMIT` / max | 4 / 10 |
| `WALK_SPEED_M_PER_MIN` | 80 |
| `WALK_DETOUR_FACTOR` | 1.3 |
| `LEAVE_BUFFER_MIN` | 2 |
| `MAX_WALK_MIN_FOR_HINTS` | 30 |
| `MAX_FAVORITES` | 6 |

---

## 12. Verification plan (do these IN ORDER)

### Step 0 — capture real fixtures FIRST (before writing any parsing code)

```bash
export TRANSIT_511_API_KEY=…   # from 511.org signup
curl -s --compressed "https://api.511.org/transit/StopMonitoring?api_key=$TRANSIT_511_API_KEY&agency=CT&format=json" \
  -o tests/fixtures/stopmonitoring_all.json
curl -s --compressed "https://api.511.org/transit/servicealerts?api_key=$TRANSIT_511_API_KEY&agency=CT&format=json" \
  -o tests/fixtures/servicealerts.json
```

Save **raw bytes** (BOM intact — verify with `xxd tests/fixtures/*.json | head -1`,
expect `efbb bf`). All ⚠ VERIFY flags were **resolved against live captures on
2026-07-01** (fixtures in `tests/fixtures/`):

1. **All-stops cap/horizon** — RESOLVED: visits truncate ~90 min out AND arrival-only
   (terminal) stops are omitted entirely. TripUpdates was verified useless as a
   fallback (next-stop only) → the bundled schedule lookup (§8a) fills both gaps.
2. **Exact `LineRef` strings** — observed `"Local Weekday"` live; substring
   normalization handles LOC/LIM/EXP/SCC codes and long forms. Pinned in tests.
3. **`MonitoredCall.StopPointRef`** — CONFIRMED present in all-stops mode (visit-level
   `MonitoringRef` also present; parser accepts either).
4. **Alerts GTFS-RT JSON casing** — RESOLVED: PascalCase with lowercase exceptions
   (`Entities`, `Alert`, `ActivePeriods{Start,End}`, `HeaderText.Translations
   {Text,Language}`, lowercase `cause`/`effect`). Parser reads PascalCase and
   GTFS-spec snake_case.
5. 429 shape — never observed; any non-200 is treated as failure → stale.

### Step 1 — unit tests (pytest + respx, fixtures fed as verbatim bytes)

- BOM-prefixed bytes decode via `utf-8-sig`.
- Top-level `ServiceDelivery` with and without `Siri` wrapper.
- `MonitoredStopVisit` as single object (not list) — synthesize from fixture.
- Pair join: origin+destination resolve; arrival matches the same train number.
- Express-skip: train with no destination visit is excluded.
- Null `ExpectedDepartureTime` → `status: "scheduled"`, `delay_seconds: null`.
- Delay math: Expected − Aimed; late/on-time threshold at 120s.
- Destination visit present but times missing → row kept, `arrival: null`.
- Stale serving: mock upstream 500 after a good fetch → `stale: true`, same payload;
  upstream 500 with cold cache → 502.
- Rate guard: 55 logged calls → no upstream call attempted, stale served.
- `/api/stations` shape; unknown-station / same-station → 400s.
- Alerts parsing in both key casings; expired alerts filtered.

Run `python -m pytest` (and `ruff check .` — CI habit from the fitness repo).

### Step 2 — local end-to-end

```bash
uvicorn app.main:app --port 8000   # with TRANSIT_511_API_KEY exported
curl -s localhost:8000/api/health | python3 -m json.tool
curl -s localhost:8000/api/stations | python3 -m json.tool
curl -s "localhost:8000/api/departures?origin=san_carlos&destination=san_francisco" | python3 -m json.tool
curl -s localhost:8000/api/alerts | python3 -m json.tool
```

Then open `http://localhost:8000` in a browser: add San Carlos → San Francisco, verify
rows/badges/times (PT, not UTC), swap, remove, alerts banner, and — with location
allowed — the nearest chip + leave-by hints. Check `upstream_calls_last_hour` in
`/api/health` stays tiny while the page idles.

### Step 3 — deploy check

Push, watch Railway build, hit `/api/health` on the public URL, open on the phone,
verify touch feel + add-to-home-screen (standalone, correct icon/theme color), and
confirm times render in Pacific time.

---

## 13. Reference — verified stop codes

| Station | NB | SB |
|---|---|---|
| San Francisco | 70011 | 70012 |
| San Carlos | 70131 | 70132 |
| San Jose Diridon | 70261 | 70262 |

All others: `70XX1`/`70XX2` pattern, read from GTFS by the generator script.
