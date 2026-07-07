# Bay Rail v2 — BART-app-inspired improvements (spec)

Six features distilled from a first-principles comparison against the official BART
mobile app, filtered by this app's actual goal (SPEC.md §0): a personal, glanceable
"am I going to be late?" board. Everything that serves agency-scale ridership was
rejected (§0.2); what survives is everything that answers *when do I leave / is my
trip disrupted / can I trust this board*.

**Design source of truth: `mockups/mockup.html`** — extended in place with all six
new treatments (at-risk transfer, last-train badge, canceled row, per-pair alert
chip, elevator advisory tag, cross-agency itinerary row). The dark departure-board
identity is non-negotiable.

- Facts marked **verified** were checked against live feeds or checked-in fixtures
  on **2026-07-06** (new captures in `tests/fixtures/bart/` — see its README).
  Items marked **⚠ VERIFY** must be re-checked during implementation; feature 4's
  marker can only be resolved at the next real service disruption and is expected
  to survive to a §13a-style amendment.
- This is a **spec + mockup phase** (same workflow as the BART expansion:
  Phase 1 = spec/mockup/fixtures, Phase 2 = build in a later session). No app code
  changes ship with this document.

---

## 0. Goals & non-goals

### 0.1 Goals (the six features)

| # | Feature | Size | Agency |
|---|---|---|---|
| 1 | Connection-at-risk flag on transfer itineraries | S | BA (+ XA via §7) |
| 2 | Per-pair alert linkage (alerts chip the affected favorite card) | M | CT (BA plumbed, banner-only) |
| 3 | Last-train-tonight badge | M | CT + BA |
| 4 | Canceled-trip rows | M | BA only |
| 5 | Elevator/escalator advisories | S (CT) / M (BA) | CT + BA |
| 6 | Cross-agency Caltrain↔BART itineraries at Millbrae | L | XA (new) |

### 0.2 Non-goals — rejected BART-app features (user decisions, 2026-07-06)

- **No push notifications for delays — REJECTED, recorded permanently.** It
  conflicts with three load-bearing architecture decisions at once: no service
  worker (SPEC.md §0/§9.8), no server-side per-user state (no accounts, no DB),
  and lazy-fetch-only upstream (SPEC.md §6). A useful delay notifier must poll
  upstream around the clock whether or not anyone has the page open — that
  breaks the 511 rate-budget model, which is sized to page-open lazy fetch —
  and needs web-push infrastructure plus stored subscription tokens. The
  glanceable board *is* this app's answer to "will I be late": you check it
  when you're about to leave.
- **No "first train tomorrow" preview.** The precise version requires knowing
  which service day tomorrow is — calendar/holiday inference, the schedule-engine
  trap SPEC.md §0 forbids. Only allowed change: sharpened *static* empty-state
  copy (§4.6). The realtime feeds remain the only source of which trains run.
- No address-to-address trip planning (favorite pairs are the product), no
  parking / Clipper / fare features, no biohazard or police reporting, no fleet
  tracker or system map, no trip sharing, no calendar integration, no train
  temperature reporting. All serve agency-scale ridership, not this board.

### 0.3 Unchanged invariants

- Caltrain 511 data path, rate budget, and all existing response fields are
  untouched; every API change below is **additive** (new fields, new enum value,
  new `agency` value). Deployed frontends keep working during rollout.
- Still no schedule *engine*: features 3 and 4 read the bundled static data only
  through realtime-supplied trip_ids or as an order-free per-pair maximum — no
  calendar.txt, no service-day-type inference anywhere (§4.3, §5.4).

---

## 1. Phasing (spec order = implementation order)

1. **Feature 1** (at-risk) — pure function change in `_stitch`, no new data.
2. **Feature 2** (alert linkage) — parser + frontend plumbing; gives feature
   5-Caltrain for free.
3. **Feature 3** (last-train badge) — static pair-max bound + badge.
4. **Feature 4** (canceled rows) — parser tag-instead-of-drop + scheduled-time
   rendering; built against the synthetic fixture.
5. **Feature 5-BART** (elevator advisories) — first BART-keyed endpoint;
   **gated on the user registering `BART_API_KEY`** (§10).
6. **Feature 6** (Millbrae cross-agency) — the largest; touches both agencies'
   pair logic, favorites, pickers.

Each lands independently; nothing later depends on an earlier one being deployed
except 5-Caltrain on 2, and 6 reusing 1's at-risk flag on its transfers.

---

## 2. Feature 1 — connection-at-risk flag (S)

### 2.1 What exists

`bart_pairs._stitch` already computes everything needed: a connection is kept when
`second._dep_epoch ≥ first._arr_epoch + min_transfer_s`, on *expected* (delay-aware)
times. SPEC-BART §12 wrongly assumed the ETD API was required for this — it is not;
the slack is sitting in the join.

### 2.2 Contract

Let `slack_s = second._dep_epoch − (first._arr_epoch + min_transfer_s)` at stitch
time, and `leg1_estimated` = the incoming leg's arrival payload carries
`estimated: true` (schedule-projected, not realtime — §5.2-2 projections, `static_ride`
fallbacks, synthesized OAK-shuttle legs, and Caltrain §8a arrivals under §7 all set it).

Emit `"at_risk": true` on the **transfer entry** (`transfers[i]`) when:

```
slack_s < TRANSFER_AT_RISK_SLACK_S                      (120)
or (leg1_estimated and slack_s < TRANSFER_AT_RISK_ESTIMATED_SLACK_S)   (300)
```

- The field is additive and **absent when false** (same convention as
  `legs`/`transfers` being absent on direct rows).
- Deliberate deviation from the session sketch ("flag whenever leg-1 arrival is
  estimated"): an estimated arrival with 20 minutes of slack is not at risk —
  flagging it would train the user to ignore the flag. Estimation instead
  *widens* the slack threshold to 300 s, because projected arrivals carry error
  the realtime ones don't.
- At-risk itineraries are still itineraries: they cleared min-transfer, they are
  ranked and Pareto-pruned exactly as today. The flag warns; it never filters.
  (An infeasible connection is already excluded by `_stitch`; `at_risk` covers
  the window just above the minimum.)
- Multi-transfer itineraries (OAK shuttle, §7's BA-side transfers): the rule is
  applied per transfer independently; any transfer can flag.

### 2.3 Frontend

On the `"change at West Oakland · 5 min wait"` line: when the transfer has
`at_risk`, append **"· tight connection"** in amber (mockup shows the treatment,
including on a cross-agency row). No layout change, no extra row height.

### 2.4 Tests (Phase 2)

- Synthesized fixture: slack 60 s → flagged; slack 180 s realtime → not flagged;
  slack 180 s with estimated leg-1 arrival → flagged; slack 400 s estimated → not.
- Existing WCRK→DUBL fixture itinerary asserts presence/absence end-to-end.
- Pruning unchanged: an at-risk itinerary that Pareto-dominates is still kept.

---

## 3. Feature 2 — per-pair alert linkage (M)

### 3.1 Evidence (verified in checked-in fixtures)

- **Caltrain**: 511 servicealerts carries stop-scoped informed entities. In
  `tests/fixtures/servicealerts.json`, the Millbrae elevator alert has
  `"InformedEntities": [{"AgencyId": "CT", "StopId": "70061"},
  {"AgencyId": "CT", "StopId": "MIL-03-NB"}]` — key casing is PascalCase
  (`InformedEntities`/`AgencyId`/`StopId`), consistent with the feed's other
  casing quirks; read snake_case (`informed_entity`/`stop_id`) defensively like
  the rest of the parser. `70061` is Millbrae's NB platform code in
  `data/stations.json` — **StopIds join directly to favorite pairs.**
- **BART**: `alerts.pb` `informed_entity` is agency-only (verified empty of stop
  references) — BART GTFS-RT alerts stay global-banner. The station-name-substring
  heuristic (grep the description for station names) is **rejected**: fragile
  against prose like "between Millbrae, SFO and Daly City" where the alert spans a
  segment, and it would silently mis-scope.

### 3.2 Backend contract

- `departures.parse_alerts` (CT) emits a new `"stops"` field per alert: the list
  of `StopId` strings from informed entities (deduped, order-preserving; entities
  without a StopId contribute nothing). Non-platform ids like `MIL-03-NB` are
  passed through verbatim — the frontend matches against known platform codes, so
  unknowns are inert.
- `bart_pairs.parse_alerts` (BA) emits `"stops"` with the same shape, populated
  from `informed_entity` stop_ids plumbed through `bart.parse_alerts_feed` —
  empty today (verified), but the plumbing keeps one uniform alert shape and
  starts working the day BART populates the field.
- Alerts with no stop scope: `"stops": []` (present, empty — alerts differ from
  row fields here because the frontend always branches on it).

### 3.3 Frontend contract

- Per favorite card, a **match set** of codes:
  - `ct` pair → `{origin.stop_nb, origin.stop_sb, destination.stop_nb,
    destination.stop_sb}` (platform codes already served by `/api/stations`).
  - `ba` pair → `{origin.abbr, destination.abbr}`.
  - `xa` pair (§7) → the union of both ends' sets **plus the Millbrae transfer
    codes** (`70061`, `70062`, `MLBR`) — the rider passes through Millbrae on
    every xa trip, so a Millbrae-scoped alert (e.g. an elevator outage) is part
    of that pair's story even though Millbrae is neither endpoint.
- An alert whose `stops` intersects a card's match set renders as a compact
  **alert chip** in that card's head (amber text + warning glyph, mockup shows
  it): chip text = the alert header, middle-truncated to one line. Chips are not
  dismissible (they are the signal, and they disappear with the alert).
- A stop-scoped alert that chips onto **≥ 1 card is suppressed from the global
  banner** — the chip is the better surface and double-showing is noise. A
  stop-scoped alert matching *no* favorite stays in the banner (visibility is
  never lost). Unscoped alerts (`stops: []`) behave exactly as today.
- Session-dismiss by id applies to banners only, unchanged.

### 3.4 Tests

- Fixture alert with StopId `70061` chips a `millbrae→san_francisco` card
  (either direction — the match set covers both platforms) and is absent from
  the banner; the same alert with no matching favorite appears in the banner.
- BART alert from `alerts.pb` → `stops: []`, banner-only, byte-identical
  header/description to today.

---

## 4. Feature 3 — last-train-tonight badge (M)

### 4.1 Why feed exhaustion is not the signal

The 511 window is ≈ 90 minutes (SPEC.md §5.3) and BART's feed holds only assigned
trips (max observed horizon 126 min — fixture README): both feeds "run out" all
day long. The existing *"That's every upcoming train in the live feed right now."*
footer covers exhaustion; the badge must mean strictly more: **no later train
exists tonight.**

### 4.2 The calendar-free bound

For a pair, define the **static pair-max**: the maximum origin departure
time-of-day over **all** bundled trips serving origin-before-destination — every
day type pooled, no calendar lookup. A trip departing at (or within ε of) that
maximum is the last train on *some* day, and no bundled trip on *any* day departs
later. Consequences, stated and accepted:

- **Never a false positive** on the badge's own terms: nothing in the bundle
  departs later than the max.
- **Under-triggers on weekends**: if Sunday's true last train leaves 30 min
  before the weekday max, Sunday night shows no badge. Acceptable — a missing
  badge costs nothing; a wrong badge costs a stranded user.

Computed 2026-07-06 from the checked-in bundles (record for regression — these
move only when the data files are regenerated):

| Pair | Bundled trips serving it | Static pair-max (origin dep) |
|---|---|---|
| San Carlos → San Francisco (CT) | 110 | **25:51** (1:51 AM) |
| San Francisco → San Carlos (CT) | 109 | **24:05** (12:05 AM) |
| Embarcadero → Walnut Creek (BA) | 562 | **24:32** |
| Walnut Creek → Embarcadero (BA) | 563 | **24:29** |
| Millbrae → Embarcadero (BA) | 326 | **20:54** |
| Embarcadero → Millbrae (BA) | 329 | **25:10** |

Two findings fall out:

1. **Most pair-maxima are past-midnight GTFS times (24:xx–26:xx)** — comparisons
   MUST happen in service-day seconds, not wall-clock mod 24 h (§4.3).
2. The MLBR→EMBR max of 20:54 is real: late-evening SF-bound service from
   Millbrae runs via the SFO transfer, not direct. The badge logic is
   direct-rows-only (§4.5) and simply never fires for that pair late at night —
   correct, since the pair keeps producing (transfer) itineraries.

### 4.3 Service-day seconds (the cutover rule)

To compare a realtime departure against a `24:xx` static max:

```
t = seconds-since-PT-midnight of the row's aimed departure (zoneinfo, DST-safe)
service_s = t + 86400 if t < SERVICE_DAY_CUTOVER_S else t        (cutover = 3 h)
```

**Verified safe 2026-07-06**: zero stop events in either bundle fall in
[03:00, 04:00) or beyond 27:00 — the 3 AM cutover cannot misclassify any bundled
trip. This is clock arithmetic on the row's own timestamp; it infers nothing
about day types. Compare on **aimed** time (fallback: effective): a 20-minute-late
last train is still the last train, and aimed is what the static max describes.

### 4.4 Contract

On a direct-rows response, set `"last_train": true` on the **final row** when ALL
of:

1. `len(rows) < limit` — the feed itself shows nothing after it (reuses the
   exhaustion condition the footer already keys on);
2. the final row's aimed departure in service-day seconds ≥
   `pair_max_s − LAST_TRAIN_EPSILON_S` (300 — absorbs realtime jitter, the
   arrival-as-departure proxy below, and minor schedule drift);
3. the row's trip is **known to the bundle** — post-GTFS-rotation degrade
   (`static_ride` fallbacks, unknown Caltrain trips) suppresses the badge, same
   honesty rule as everywhere else.

Pair-max sources: Caltrain — `data/trip_arrivals.json`, using the origin's
arrival-seconds as the departure proxy (the file stores arrivals only; ε covers
the dwell). BART — `data/bart_trips.json`, `first_arrival + pattern_offset[origin]`
over patterns serving origin-before-destination. Compute lazily with a per-pair
LRU cache; the bundles are immutable per process.

- Condition 1 means a night with exactly-`limit` trains left shows no badge until
  a refresh drops the count below the limit; the show-more expander (limit 10)
  makes this window short in practice. Accepted.
- v2 scope: **direct rows only, both agencies.** Transfer/cross-agency itinerary
  last-train semantics ("last feasible connection tonight") are deferred — the
  bound would need per-leg maxima joined through the transfer window, and a wrong
  badge there strands someone at a transfer platform.
- `"last_train"` is additive, absent when false, and at most one row per response
  carries it.

### 4.5 Frontend

Amber-tinted tag **"Last train tonight"** on the flagged row, rendered under the
type/line pill line (mockup shows placement and the amber treatment — it reuses
the LED-amber accent, not the red late-treatment).

### 4.6 Empty-state copy (the allowed remnant of "first train tomorrow")

Static copy only, sharpened per agency:

- CT: *"No upcoming trains for this pair right now. Caltrain's first weekday
  trains leave around 4–5 AM; weekend and South County service is sparse — this
  is often normal."*
- BA: *"No upcoming trains for this pair right now. BART runs roughly 4 AM
  (6 AM Saturday, 8 AM Sunday) to midnight — overnight emptiness is normal."*

The frontend MAY pick phrasing using the client's local weekday (pure
`Date`-based wording choice, explicitly best-effort: holidays render weekday
copy and that is fine for static prose). It must NOT compute or display a
specific "first train at HH:MM" — that is the forbidden calendar engine.

### 4.7 Tests

- Pinned pair-max numbers above as regression tests against the checked-in
  bundles (they fail loudly when the bundle rotates, which is the point).
- Synthesized feeds: last row at max − 2 min → badge; at max − 10 min → none;
  rows == limit → none; unknown trip_id → none; a 00:30 AM departure (service_s
  = 24:30) badges against a 24:32 max.
- Cutover unit test: 02:59 AM maps to 26:59, 03:01 AM maps to 03:01.

---

## 5. Feature 4 — canceled-trip rows (BART only) (M)

### 5.1 Evidence and the honest caveat

`app/bart.py` currently **drops** `schedule_relationship == CANCELED` trips at
parse time (and SKIPPED stops). Zero CANCELED entities exist in any live capture
— BART's cancellation shape has never been observed. The legacy ETD API's
`cancelflag` proves cancellations surface *somewhere*; whether the GTFS-RT feed
marks them, and whether canceled trips keep their StopTimeUpdates, is
**⚠ VERIFY at the next real disruption** (this marker is *expected* to survive
Phase 2 and be resolved by a §13a-style amendment with a live capture).
Until then: build against the synthetic fixture
`tests/fixtures/bart/tripupdate_canceled_synthetic.pb` (see the fixtures README
for its four entities: canceled-without-STUs, canceled-with-STUs, normal,
canceled-unknown-trip).

**Caltrain is explicitly out**: 511 StopMonitoring carries no cancellation
signal (verified during the v1 exploration) — a canceled Caltrain train simply
vanishes from the feed, and inventing cancellations from absence would violate
the never-guess rule.

### 5.2 Parse contract (`app/bart.py`)

`parse_trip_updates` returns `{"trips": [...], "canceled_trips": [...]}`:

- CANCELED trips move to the new `canceled_trips` list (`{trip_id, stops}` —
  stops kept if the feed supplies them, usually empty) instead of being dropped.
- The `trips` list is **byte-identical to today** — every existing consumer
  (`index_feed`, the join, transfer stitching) is untouched and canceled trips
  can never leak into itineraries (they don't run).
- SKIPPED stop handling is unchanged (dropped). A SKIPPED stop at the rider's
  origin/destination on an otherwise-running trip is a real but rarer signal —
  out of scope for v2, noted for the future.

### 5.3 Row contract (`app/bart_pairs.py`)

A canceled trip produces a row for the pair when its bundled pattern serves
origin **strictly before** destination (the same §5.2-3 pattern-authority as
live rows). Row shape:

```json
{
  "trip": "1842225", "line": "Yellow", "line_color": "#ffe14d",
  "headsign": "to Antioch",
  "departure": { "aimed": "…", "expected": null },
  "arrival":   { "aimed": "…", "expected": null, "estimated": true },
  "delay_seconds": null,
  "status": "canceled"
}
```

- `status: "canceled"` is a new enum value (additive; old frontends fall through
  to their default badge branch harmlessly).
- Times: if the feed kept STUs (fixture entity 2), use them as `aimed` with
  `expected: null`. Otherwise (entity 1, the expected shape) render **scheduled**
  times from the bundle: `aimed = service_anchor + first_arrival +
  pattern_offset[station]`, where `service_anchor` is noon−12 h PT on the
  **inferred service day** — the PT date of `now`, shifted back one day when
  now's PT time-of-day is before the 3 AM cutover (§4.3). BART's feed populates
  neither `trip.start_date` nor `start_time` (verified 0/85 in the capture), so
  the cutover heuristic is the only anchor; it is clock arithmetic, not calendar
  inference, and the same dead-zone verification covers it.
- This is the **first code path that anchors `bart_trips.json`'s absolute
  `first_arrival_seconds` to a date** — exactly the future use SPEC-BART §4.2
  kept the field for. SPEC-BART's "nothing in v1 reads it" note stays true of v1;
  its ⚠ VERIFY is superseded by this section for the canceled path only.
- Trip unknown to the bundle (fixture entity 4): **suppress the row** — no
  scheduled times are resolvable, and a bare "something was canceled" row is
  noise. Same degrade path as everything post-GTFS-rotation.

### 5.4 Selection and ordering

- Canceled rows are **additive to the limit**: select `limit` live rows exactly
  as today, then merge in canceled rows whose scheduled departure is ≥ now −
  grace and ≤ the last shown live departure (or unbounded when live rows number
  fewer than `limit`). A canceled train must never push a live train off the
  board — the board answers "when do I actually leave".
- Cap: `MAX_CANCELED_ROWS` (3) per response, earliest first (a mass cancellation
  reads better as an alert banner than as a wall of struck-through rows).
- Merged list sorts by aimed departure. Canceled rows expire off the board once
  their scheduled departure passes, like any row.
- Direct-rows path only. A zero-direct pair in transfer mode shows no canceled
  rows in v2.

### 5.5 Frontend

Struck-through scheduled time in the big LED column (dimmed, reusing the
`.t-was` strike treatment at full size), red **CANCELED** badge in the status
column, no leave-by hint on the row (there is nothing to catch). Mockup shows
the treatment.

### 5.6 Tests

- Fixture entity 1 → row with bundle-derived times (18:03 PT dep at EMBR),
  `status: "canceled"`, interleaved before the 18:11 live row.
- Entity 2 → row uses the feed's own times; entity 4 → suppressed.
- Live rows unaffected: the fixture's normal trip resolves exactly as before.
- Limit interaction: limit=1 returns 1 live row + the canceled rows in window.
- Service-day anchor: a synthetic 24:30 canceled trip queried at 00:45 PT
  renders 12:30 AM today, not tomorrow.
- Transfer paths: canceled trips never appear in `index_feed` output (guard
  test on the new parse shape).

---

## 6. Feature 5 — elevator/escalator advisories (S Caltrain / M BART)

### 6.1 Caltrain (S — rides on feature 2)

Already flowing: 511 servicealerts carries elevator outages as ordinary alerts
with stop-scoped informed entities — the checked-in fixture's second entity IS a
Millbrae elevator outage (`StopId: "70061"`). With feature 2's `stops` plumbing,
it chips the affected favorite automatically. Delta on top:

- Tag alerts whose header or description contains "elevator" or "escalator"
  (case-insensitive) with `"type": "elevator"` (additive field, absent
  otherwise). Purely cosmetic — it drives the frontend's ELEVATOR tag, nothing
  filters on it.

### 6.2 BART (M — new keyed endpoint)

GTFS-RT alerts don't carry elevator status; the legacy BSA API does:

```
GET https://api.bart.gov/api/bsa.aspx?cmd=elev&key=$BART_API_KEY&json=y
```

**Captured 2026-07-06 (fixture `elev.json`) — live shape, with a real MLBR
outage in it:**

- XML-converted JSON: text under `#cdata-section`, attributes under `@`-keys.
- ONE `root.bsa[]` entry with `station: "BART"` (generic — NOT per-station),
  `type: "ELEVATOR"`, and a single prose description covering every outage:
  *"There are 2 elevators out of service at this time: MLBR: Station - SF/East
  Bay/SFO Airport; RICH: Station"*. `posted`/`expires` empty.
- Station scoping must therefore be **parsed from the prose**: tokenize on
  `ABBR:` markers and keep only tokens that resolve via
  `bart_stations.by_abbr` — unknown tokens are ignored, and if nothing resolves
  the advisory degrades to an unscoped (`stops: []`) banner alert, never
  dropped.
- **⚠ VERIFY**: the zero-outage response shape (uncapturable while outages
  exist — BART docs suggest a single "all elevators are in service" entry, which
  the parser must treat as no advisories), and whether `root.bsa` collapses to a
  bare object when single (same XML→JSON singleton quirk as 511 —
  `ensure_list` it regardless).

Contract:

- New fetch in `app/bart.py` through the **same `Upstream` instance** (same call
  log and 150/hr politeness guard — worst continuous case becomes 120 TU + 12
  alerts + 12 elev = 144 < 150), TTL `BART_ELEV_TTL_S` (300 s), fetched only
  when `/api/alerts` with `agency=ba|all` runs and the key is configured.
- **Key-gated degrade**: `BART_API_KEY` unset → the elevator fetch is skipped
  entirely and BART alerts are exactly today's (no error, no log spam). The
  shared demo key `MW9S-E7SL-26DU-VV8V` is **forbidden in production code**
  (fixtures README rule) — it is for exploration/captures only.
- Parsed advisories merge into the `agency=ba` alerts list as:

```json
{
  "id": "elev:MLBR,RICH",
  "type": "elevator",
  "header": "Elevators out of service at Millbrae, Richmond",
  "description": "There are 2 elevators out of service at this time: …",
  "active_period": { "start": null, "end": null },
  "stops": ["MLBR", "RICH"]
}
```

- The id is **synthetic and set-stable**: `elev:` + sorted resolved abbrs. The
  feed's own `@id` is time-derived (`07060737` ≈ MMDDHHMM) and would rotate
  every refresh, breaking session-dismiss; the synthetic id stays put while the
  same stations are out and changes (correctly un-dismissing) when the set
  changes. Header is composed from the resolved station names; the raw prose
  rides in `description`.
- A malformed/unreachable elevator response never degrades the GTFS-RT alerts:
  the merge treats the elevator source as best-effort (mirror of the
  `agency=all` one-feed-down rule).

### 6.3 Frontend

- Alerts section: advisories with `type: "elevator"` get an **ELEVATOR** tag
  rendered alongside the existing agency source tag (mockup shows `BART` +
  `ELEVATOR` stacked on one banner, and a Caltrain elevator banner with just
  `ELEVATOR`).
- Card chips: same machinery as feature 2 — BART elevator advisories carry
  parent abbrs in `stops`, matching `ba`/`xa` favorites' match sets. Chip text
  for **BART** elevator advisories is composed as *"Elevator out at {station}"*
  using the matched station's name (the shared prose blob makes a poor chip);
  Caltrain elevator alerts chip their own header per §3.3 — 511 writes those
  per-outage (*"Accessibility: Northbound Elevator out of service at
  Millbrae…"*), so the detail is worth keeping.
- `/api/health` gains a `bart_elev` cache entry (shape unchanged otherwise).

### 6.4 Tests

- `elev.json` fixture: parses to `stops: ["MLBR", "RICH"]`, synthetic id, both
  banner and chip paths; MLBR chip lands on a Millbrae BART favorite.
- Key-gated: no `BART_API_KEY` → no fetch attempted (assert the call log), alerts
  response identical to today's.
- Zero-outage and singleton-`bsa` shapes from synthesized fixtures (until the
  ⚠ VERIFY capture exists).
- Unknown-token prose → unscoped banner alert, never dropped.

---

## 7. Feature 6 — cross-agency Caltrain↔BART itineraries at Millbrae (L)

Promoted from SPEC-BART §12-1 by user decision. Millbrae is the **only** shared
station (the two systems' station records sit ~60 m apart in the bundled data),
so this is a fixed-transfer-point stitch, not a general multi-agency router.

### 7.1 Coverage (computed 2026-07-06 from the checked-in bundles)

From MLBR, 33 of the other 49 BART stations are direct (Yellow/Red corridors);
15 more resolve with one BART-internal transfer via the existing §5.5 machinery;
only OAK Airport (`OAKL`, shuttle-only appendage) is out of reach within the leg
budget. So: **any Caltrain station ↔ 48 of 49 BART stations.** OAKL cross-agency
is excluded in v2 (it would need CT + rail + rail + shuttle = 4 legs).

### 7.2 Pair definition and API

- New `agency=xa` on `/api/departures`. Origin/destination carry the frontend's
  existing option-value format: `ct:san_carlos`, `ba:embarcadero`.
- Validation (`app/main.py`): exactly one `ct:` and one `ba:` endpoint (either
  order) → else 400 `unknown_agency`/`unknown_station` as appropriate. Both ids
  must exist in their registries. **Neither endpoint may be Millbrae**
  (`ct:millbrae` or `ba:millbrae`): that pair is a plain single-agency pair in
  disguise → 400 `degenerate_pair`, message *"Board at Millbrae directly — add a
  single-agency pair instead."*
- Response: `"agency": "xa"`, origin/destination objects each tagged with their
  `"agency"`, **no `direction` field**, and `departures` entries that are always
  itineraries (`legs` + `transfers` present — there is no through train, ever).

### 7.3 Itinerary construction

Direction CT→BA (BA→CT is the mirror):

1. **CT leg**: `departures.pair_departures(origin → millbrae)` — refactored to
   carry `_dep_epoch`/`_arr_epoch` meta (§7.4). Candidates: the next
   `TRANSFER_LEG1_CANDIDATES` (10) departures.
2. **BA side**: `direct_rows(MLBR → dest)`; when the pair has no direct trips,
   the existing one-transfer machinery (§5.5) supplies BA-internal itineraries —
   this is what unlocks the 15 transfer-beyond-Millbrae stations *and* the
   late-evening SF-bound pattern (§4.2 finding: last direct MLBR→EMBR departs
   20:54; later trips run via the SFO wye transfer).
3. **Stitch** with the existing `bart_pairs._stitch` at Millbrae with
   `min_transfer_s = CT_BA_TRANSFER_MIN_S` — the CT↔BA platform pair exists in
   neither agency's `transfers.txt` (verified during planning), so this is a new
   station-level constant: **300 s ⚠ VERIFY** (estimate for the shared-complex
   walk incl. exiting/entering fare gates; verify against posted signage or a
   timed walk before Phase 2 ships). Delay propagation and feature 1's
   `at_risk` flag come free — a late Caltrain leg rolls to the next feasible
   BART departure with zero new code.
4. **Rank/prune/limit**: `_prune_dominated`, take `limit` — unchanged machinery.
5. Leg budget: CT leg is always exactly one (Caltrain is a line; every station
   reaches Millbrae directly). Total legs ≤ 3 (CT + at most 2 BA), consistent
   with the existing `MAX_LEGS` ceiling.

Top-level `departure`/`arrival`/`delay_seconds`/`status` mirror leg 1's origin
and the last leg's arrival (SPEC-BART §7.2 rule, unchanged).

**Honest-behavior note (the 90-minute horizon):** Caltrain's feed sees ≈ 90 min
ahead. CT→BA: leg-1 candidates simply thin out late in the window. BA→CT: a BART
leg landing at Millbrae more than ~90 min out finds no visible CT departures to
stitch — those itineraries are not produced. Fewer itineraries deep in the
window is the correct, honest result; the card shows what can actually be
promised. (No schedule-engine backfill.)

### 7.4 `departures.py` refactor (CT epoch meta)

`pair_departures` rows gain the same internal meta the BART rows carry:
`_dep_epoch`/`_arr_epoch` (epoch ints derived from the datetimes it already
parses; `_arr_epoch: None` when arrival is unresolvable — such rows cannot be
stitched and are skipped by `_stitch` exactly like BART rows today). Platform
meta is not needed (the CT↔BA minimum is station-level). The `ct` response path
strips meta at the same output boundary pattern as `bart_pairs.strip_meta` —
**existing `ct` responses stay byte-identical** (test-pinned).

### 7.5 Mixed-leg shape

Each leg gains an `"agency"` field (`"ct"`/`"ba"`). CT legs keep their native
fields (`train`, `train_type`, `line_ref_raw`), BA legs theirs (`trip`, `line`,
`line_color`, `headsign`); both share `from`/`to`/`departure`/`arrival`/
`delay_seconds`. The transfer entry at Millbrae uses the CT station id
(`"station": "millbrae"`, `"station_name": "Millbrae"`) — display code reads
only `station_name`, and the id ambiguity (two registries, one name) is noted
here deliberately rather than inventing a cross-agency id scheme for one
station.

`renderDepInfo` (frontend) branches per leg on `leg.agency`: CT legs render the
type pill (existing `type-*` classes), BA legs the line-color pill
(`paintLinePill`) — joined by the existing "▸", with the existing
*"change at Millbrae · N min wait"* line (+ feature 1's amber suffix when
flagged). Mockup shows the reference row: Caltrain Limited pill ▸ BART Red
pill.

### 7.6 Favorites, pickers, hints

- **Storage stays v2** (`transit:favorites:v2`), additive shape:
  `{"agency": "xa", "origin": "ct:san_carlos", "destination": "ba:embarcadero"}`
  — single-agency entries unchanged. `pairKey` already concatenates the three
  fields and stays unique. **Stated rollback caveat**: a pre-v2 frontend build
  filters unknown entries and re-saves, silently dropping `xa` favorites on
  rollback. Accepted — favorites are two taps to re-add, and bumping to a v3
  key + migration for one additive shape isn't worth the ceremony.
- **Pickers**: remove the destination-narrowing (`frontend/app.js` — the
  `fillSelect(selDest, agencyOf(...))` calls on origin-change and swap): the
  destination select now always lists both optgroups. Picking ends in different
  agencies produces an `xa` favorite. Validation additions: Millbrae-endpoint
  degenerate pairs shake the add-row (client-side pre-check mirroring the 400).
  The swap ⇄ button now swaps values verbatim between two identical selects.
- **Cards**: the dir-tag slot shows **`CT ▸ BART`** (or `BART ▸ CT`) for `xa`
  pairs. Swap reverses the pair as today.
- **Leave-by hints**: unchanged rule — shown when the nearest station matches
  the *origin* end's agency + id.
- Alert chips: match set is the union of both ends (§3.3).

### 7.7 Deferred fold-in — flagged for Phase 2 decision, not specced

session-state fast-follow #1 (ANTC/PCTR→mainline pairs render as one estimated
through-row, hiding mainline-only delays past PITT; candidate fix routes them
through the transfer machinery) touches the same `_stitch`/`direct_rows` seam
this feature refactors. **Open decision for Phase 2**: fold it into feature 6's
implementation PR (shared test scaffolding, one review of the stitch code) or
keep it a separate fast-follow. No contract is written here either way.

### 7.8 Tests

- Validation: xa with two ct ids → 400; Millbrae endpoint → 400
  `degenerate_pair`; unknown id → 400.
- Stitch on fixtures: synthesized CT payload (San Carlos→Millbrae NB rows) +
  the real BART capture → itineraries with correct wait math across the 300 s
  minimum; late CT leg rolls to the next BART departure; estimated CT arrival
  (§8a path) triggers `at_risk` under the 300 s estimated threshold.
- BA-internal-transfer leg 2 (e.g. ct:san_carlos → ba:fremont) produces 3-leg
  itineraries; OAKL destination produces none.
- `ct` and `ba` single-agency responses byte-identical to pre-refactor pins.
- Frontend: mixed pill rendering, `CT ▸ BART` tag, picker un-narrowing,
  degenerate-pair shake.

---

## 8. API deltas (consolidated — all additive)

| Surface | Change |
|---|---|
| `/api/departures` rows | `last_train: true` on at most the final row (§4); `status: "canceled"` + `expected: null` rows, BA only (§5) |
| transfer entries | `at_risk: true` when flagged (§2) |
| `/api/departures` params | `agency=xa` with `ct:`/`ba:`-prefixed origin/destination (§7); new 400 code `degenerate_pair` |
| itinerary legs | `agency: "ct"|"ba"` per leg (§7.5) |
| `/api/alerts` entries | `stops: [...]` always present (§3); `type: "elevator"` when applicable (§6); BART elevator advisories merged into `ba`/`all` with synthetic stable ids (§6.2) |
| `/api/health` | `bart_elev` cache entry (§6.3) |

Absent-when-false fields: `at_risk`, `last_train`, `type`. Always-present:
`stops` (may be empty). No existing field changes shape or meaning.

---

## 9. Constants (new, alongside the existing blocks)

| Constant | Value | Notes |
|---|---|---|
| `TRANSFER_AT_RISK_SLACK_S` | 120 | §2.2 |
| `TRANSFER_AT_RISK_ESTIMATED_SLACK_S` | 300 | §2.2, wider band for projected arrivals |
| `LAST_TRAIN_EPSILON_S` | 300 | §4.4 |
| `SERVICE_DAY_CUTOVER_S` | 10800 (3 h) | §4.3/§5.3 — dead zone verified empty |
| `MAX_CANCELED_ROWS` | 3 | §5.4 |
| `BART_ELEV_TTL_S` | 300 | §6.2 |
| `CT_BA_TRANSFER_MIN_S` | 300 **⚠ VERIFY** | §7.3 — timed walk / signage before Phase 2 ships |

---

## 10. Deploy

- **New env var: `BART_API_KEY`** — personal key, free + instant at
  https://api.bart.gov/api/register.aspx. **User action item, before Phase 2:**
  register it, add to local `.env` (gitignored) and the Railway service
  variables. Never committed; demo key never shipped. Everything else in v2
  works without it (feature 5-BART silently absent until the key exists).
- No other infra changes: same service, same watch paths, no new Python
  dependencies (the elevator endpoint is JSON over the existing httpx client).

---

## 11. Decisions log (user review, 2026-07-06)

1. **IN**: connection-at-risk flag, per-pair alert linkage, last-train-tonight
   badge, BART canceled-trip rows, elevator advisories for both agencies (user
   registers the free personal BART key), and cross-agency Caltrain↔BART
   itineraries at Millbrae — the last **promoted from SPEC-BART §12-1** to v2
   scope.
2. **OUT — push notifications for delays**: stays out permanently; rationale
   recorded in §0.2 (conflicts with no-SW / no-push / no-server-state and the
   lazy-fetch rate-budget model).
3. **OUT — "first train tomorrow" preview**: the precise version is the
   forbidden calendar engine. Only the static empty-state copy is sharpened
   (§4.6).
4. First-principles filter on the BART app's remaining features: parking
   payment, Clipper/fares, biohazard reporting, address-to-address planner,
   fleet tracker, trip sharing, temperature reporting — all rejected as
   agency-scale features that don't serve the personal board (§0.2).

---

## 12. Verification plan

### Step 0 — fixture captures (DONE 2026-07-06, live-verify-first)

- `tests/fixtures/bart/elev.json` — real capture via demo key (exploration-only
  use), with a live MLBR+RICH outage in it. Facts it resolved: single generic
  `station: "BART"` entry, prose-blob scoping with `ABBR:` markers, empty
  `posted`/`expires`, time-derived `@id` (hence the synthetic stable id, §6.2).
- `tests/fixtures/bart/tripupdate_canceled_synthetic.pb` — synthetic (zero
  CANCELED entities exist in live captures); four entities pinning the shapes
  §5 must handle; real feed-v72 trip_ids on EMBR→WCRK; regeneration recipe:
  build a `FeedMessage` with gtfs-realtime-bindings — entities: CANCELED
  trip without STUs, CANCELED with STUs, normal SCHEDULED, CANCELED with
  trip_id `9999999`; epochs anchored noon−12 h PT on the service day; details
  in the fixtures README table.
- Verified against the live 2026-07-02 `tripupdate.pb`: `start_date`/
  `start_time` unpopulated (0/85) → §5.3's cutover anchor is required, not
  optional.
- Static pair-maxima computed from the checked-in bundles and recorded in §4.2;
  the 3 AM cutover dead-zone check ([03:00, 04:00) ∪ >27:00 empty in both
  bundles) recorded in §4.3.
- `InformedEntities` casing + Millbrae `StopId: 70061` join confirmed in the
  existing `servicealerts.json` fixture (§3.1).

### Step 1 — mockup review (this phase's acceptance gate)

Open `mockups/mockup.html` in a browser: all six treatments visible (at-risk
suffix, last-train tag, canceled row, card alert chip, ELEVATOR banner tag on
both agencies, cross-agency CT▸BART row), dark-board identity intact, touch
targets ≥ 44 px, desktop grid unbroken.

### Step 2 — no-regression

No app code changes in this phase: `python -m pytest` stays green (95 tests)
and `git diff` touches only `SPEC-V2.md`, `mockups/mockup.html`,
`tests/fixtures/bart/{elev.json,tripupdate_canceled_synthetic.pb,README.md}`.

### Step 3 — Phase 2 (implementation, later session) — per-feature test lists

In §2.4, §3.4, §4.7, §5.6, §6.4, §7.8. Plus the standing rules: ruff before
push; `ct` response byte-pins around the §7.4 refactor; live cross-checks
(a real BART transfer wait, the elevator banner against bart.gov/elevators)
before calling any feature done; `BART_API_KEY` in Railway before the feature-5
deploy.

## 13. Implementation amendments (2026-07-06, Phase 2)

1. **Canceled rows stand alone when every live option is gone** (§5.4 refined).
   As written, canceled rows merged only into a non-empty live direct list —
   which hid the row in exactly the highest-stakes case, "the only train
   tonight got canceled." Implemented behavior: canceled rows for a
   direct-served pair return even with zero live rows; the transfer fallback
   runs only when there is nothing at all (live or canceled) to show. A
   genuine transfer-only pair (no pattern serves it directly) still never
   shows canceled rows.
2. **xa BART-side candidates always include the transfer machinery** (§7.3-2
   refined; live-verified 2026-07-06, 8:20 PM). "Direct rows, else transfers"
   failed in the real evening pattern: direct MLBR→EMBR trips existed in the
   feed but every one departed *before* the Caltrain leg arrived, while the
   SFO-wye transfer (a later Millbrae departure) still ran — the stitch got
   zero itineraries. Implemented behavior: the BA side offers direct rows AND
   §5.5 one-transfer itineraries as stitch candidates, directs listed first
   (a same-departure tie prefers the direct), with dominated combinations
   pruned as usual. Same-line hop-off-hop-on noise loses those ties or the
   domination pass (test-pinned).

### ⚠ VERIFY ledger (open items carried into Phase 2)

| Item | Where | How it resolves |
|---|---|---|
| Real CANCELED feed shape (STUs kept? relationship on trip or STU?) | §5.1 | Next live disruption capture → §13a-style amendment |
| Zero-outage + singleton `bsa` elevator response shapes | §6.2 | Capture on a no-outage day / synthesize until then |
| `CT_BA_TRANSFER_MIN_S` = 300 s | §7.3 | Timed walk or posted signage at Millbrae |
