"""Cross-agency Caltrain↔BART itineraries at Millbrae (SPEC-V2 §7).

Millbrae is the only shared station, so this is a fixed-transfer-point stitch,
not a general multi-agency router: the Caltrain leg is always exactly one
(Caltrain is a line — every station reaches Millbrae directly) and the BART
side reuses the ordinary direct join, falling back to the §5.5 one-transfer
machinery for stations beyond Millbrae's direct reach. Delay propagation and
the at-risk flag come free from bart_pairs._stitch.

Pure functions over already-fetched payloads — no IO, unit-testable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app import bart_pairs, bart_stations, departures, stations

# The CT↔BA platform pair exists in neither agency's transfers.txt; this is a
# station-level estimate for the shared-complex walk including the fare-gate
# exit/entry between systems. ⚠ VERIFY against posted signage or a timed walk
# (SPEC-V2 §7.3) — deliberately above BART's internal 180 s default.
CT_BA_TRANSFER_MIN_S = 300

CT_MILLBRAE_ID = "millbrae"
BA_MILLBRAE_ID = "millbrae"
BA_MILLBRAE_ABBR = "MLBR"


def _ct_leg_itineraries(
    sm_payload: dict,
    ct_station: stations.Station,
    to_millbrae: bool,
    now: datetime,
) -> list[dict]:
    """The Caltrain leg as 1-leg itineraries with stitch meta. Platform meta
    stays None — the CT↔BA minimum is station-level, so _stitch falls through
    to default_min_s."""
    millbrae = stations.get(CT_MILLBRAE_ID)
    origin, destination = (ct_station, millbrae) if to_millbrae else (millbrae, ct_station)
    origin_stop, destination_stop, _direction = stations.platform_codes(origin, destination)
    itineraries = []
    for row in departures.pair_rows(
        sm_payload, origin_stop, destination_stop, bart_pairs.TRANSFER_LEG1_CANDIDATES, now
    ):
        leg = {key: value for key, value in row.items() if key != "last_train"}
        leg["agency"] = "ct"
        leg["from"] = origin.id
        leg["to"] = destination.id
        itineraries.append(
            {
                "legs": [leg],
                "transfers": [],
                "_dep_epoch": row["_dep_epoch"],
                "_arr_epoch": row["_arr_epoch"],
                "_dep_platform": None,
                "_arr_platform": None,
            }
        )
    return itineraries


def _ba_leg_itineraries(
    ba_feed: dict,
    ba_station: bart_stations.Station,
    from_millbrae: bool,
    now_epoch: int,
) -> list[dict]:
    """The BART side: direct rows from/to Millbrae PLUS the existing
    one-transfer machinery (§7.3-2, amended — SPEC-V2 §13-2). Both candidate
    sets are always offered: direct trips can exist yet all be infeasible for
    the stitch (live-verified: late evening, every direct MLBR→EMBR departure
    precedes the Caltrain arrival while the SFO-wye transfer still runs).
    Directs come first so a same-departure tie prefers them; dominated
    combinations are pruned at the top level."""
    index = bart_pairs.index_feed(ba_feed)
    millbrae = bart_stations.get(BA_MILLBRAE_ID)
    origin, destination = (millbrae, ba_station) if from_millbrae else (ba_station, millbrae)
    direct = bart_pairs.direct_rows(
        index, origin.abbr, destination.abbr, bart_pairs.TRANSFER_LEG1_CANDIDATES, now_epoch
    )
    itineraries = [
        bart_pairs._as_itinerary(row, origin.id, destination.id) for row in direct
    ] + bart_pairs._one_transfer_itineraries(index, origin, destination, now_epoch)
    for itinerary in itineraries:
        for leg in itinerary["legs"]:
            leg["agency"] = "ba"
    return itineraries


def _itinerary_payload(itinerary: dict) -> dict:
    """Public xa shape (§7.2/§7.5): top-level departure/arrival/delay/status
    mirror leg 1's origin and the last leg's arrival; no top-level line or
    train fields — mixed legs mean the renderer always reads legs."""
    legs = [bart_pairs.strip_meta(leg) for leg in itinerary["legs"]]
    first, last = legs[0], legs[-1]
    return {
        "departure": first["departure"],
        "arrival": last["arrival"],
        "delay_seconds": first["delay_seconds"],
        "status": first["status"],
        "legs": legs,
        "transfers": itinerary["transfers"],
    }


def pair_itineraries(
    sm_payload: dict,
    ba_feed: dict,
    ct_station: stations.Station,
    ba_station: bart_stations.Station,
    ct_first: bool,
    limit: int,
    now: datetime | None = None,
) -> tuple[list[dict], str | None]:
    """(itineraries, empty_reason) — itineraries are always legs+transfers
    (there is no through train, ever). ct_first: Caltrain origin → BART
    destination; else mirror.

    Honest horizon behavior (§7.3, SPEC-V2 §13-3): the live feeds see only
    30–90 minutes ahead (Caltrain's window; BART carries assigned trips
    only), so connections thin out or vanish beyond that. When the ORIGIN
    leg is demonstrably running but nothing stitches, empty_reason is
    "connection_horizon" — the frontend shows a callout instead of the
    generic no-service copy. When nothing runs at the origin either, the
    reason stays None (overnight emptiness is just emptiness).
    """
    now = now or datetime.now(timezone.utc)
    now_epoch = int(now.timestamp())
    millbrae = bart_stations.get(BA_MILLBRAE_ID)  # transfer entry: "millbrae"/"Millbrae"

    if ct_first:
        firsts = _ct_leg_itineraries(sm_payload, ct_station, to_millbrae=True, now=now)
        seconds = _ba_leg_itineraries(ba_feed, ba_station, from_millbrae=True, now_epoch=now_epoch)
    else:
        firsts = _ba_leg_itineraries(ba_feed, ba_station, from_millbrae=False, now_epoch=now_epoch)
        seconds = _ct_leg_itineraries(sm_payload, ct_station, to_millbrae=False, now=now)

    stitched = bart_pairs._stitch(firsts, seconds, millbrae, default_min_s=CT_BA_TRANSFER_MIN_S)
    pruned = bart_pairs._prune_dominated(stitched)[:limit]
    empty_reason = "connection_horizon" if firsts and not pruned else None
    return [_itinerary_payload(itinerary) for itinerary in pruned], empty_reason
