# BART fixtures — captured live 2026-07-02 ~22:03 UTC (3:03 PM PT, Thursday)

Raw bytes from BART's public feeds, captured during the SPEC-BART.md exploration.
These back the verified facts in that spec and feed the Phase-2 unit tests.
No API key was needed for the GTFS-RT feeds; the JSON endpoints used BART's public
demo key (`MW9S-E7SL-26DU-VV8V` — exploration only; register a personal key before
shipping anything that calls `api.bart.gov/api/*` in production).

## Capture commands

```bash
# GTFS-Realtime (protobuf, no key). Both endpoints 301-redirect http→https: use -L.
curl -sSL "http://api.bart.gov/gtfsrt/tripupdate.aspx" -o tripupdate.pb
curl -sSL "http://api.bart.gov/gtfsrt/alerts.aspx"     -o alerts.pb

# Legacy JSON API (demo key)
curl -sS --compressed "https://api.bart.gov/api/etd.aspx?cmd=etd&orig=ALL&key=MW9S-E7SL-26DU-VV8V&json=y" -o etd_all.json
curl -sS --compressed "https://api.bart.gov/api/stn.aspx?cmd=stns&key=MW9S-E7SL-26DU-VV8V&json=y"          -o stations_api.json
```

Static GTFS referenced by the spec (not checked in — 1.1 MB zip, regenerable):
`https://www.bart.gov/dev/schedules/google_transit.zip` (307-redirects; follow it).
At capture time: `feed_version 72`, valid 2026-01-12 → 2026-08-07.

## What each fixture proves (measured against static GTFS v72)

### `tripupdate.pb` — the load-bearing capture
- 85 trip entities; stop_time_update counts min 1 / median 14 / max 25 —
  **full remaining-stop lists**, unlike 511's next-stop-only Caltrain TripUpdates.
- Every STU has arrival+departure epoch times and a per-stop `delay` (e.g. 866 s on a
  Green-line trip mid-disruption).
- 99/99 distinct RT stop_ids resolve to GTFS platforms (`M16-1` style), each with a
  `parent_station` (`EMBR` style).
- 75/85 trip_ids exist in static `trips.txt`. The other 10 (`656`–`671`, 1–2 STUs
  each, stops E20/E30 = PCTR/ANTC) are eBART shuttle segments — see SPEC-BART §5.4.
- Truncation: each matched trip's RT list is a contiguous suffix of its static stop
  sequence ending short of the terminal — 58 trips 1 stop short, 10 two short,
  3 three short, 3 non-contiguous edge cases. Terminal arrivals therefore need the
  bundled-pattern delta projection (SPEC-BART §5.2 rule 2).
- Depth: 43 future departures at Embarcadero alone; last-STU horizon min 0 / median 53
  / max 126 minutes ahead; 56 entities were trips that hadn't departed yet.
- Yellow-N through-trips end at PITT/NCON in RT — the Antioch tail is only covered by
  the shuttle trips above.

### `alerts.pb`
- 2 entities. `header_text` is a generic "BART.gov Alert" — real text lives in
  `description_text`. `active_period` and `informed_entity` unpopulated;
  cause/effect UNKNOWN. One entity is evergreen promo noise (fare-payment ad).

### `etd_all.json` (legacy ETD, rejected as primary source — SPEC-BART §1.2)
- One call covers all 49 stations. Estimates carry platform, direction, car length,
  line color, delay, cancelflag — but **no trip id**, hence no pair join.

### `stations_api.json`
- 50 stations with GTFS-matching coordinates; matches static parent stations 1:1.

## Re-capturing

Only needed if the GTFS feed version rotates (check `feed_info.txt`) or a test needs a
disruption-era snapshot. Keep raw bytes verbatim — tests should parse these files
exactly as fetched.
