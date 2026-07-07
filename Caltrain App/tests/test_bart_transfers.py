"""Transfer itineraries: stitching, delay propagation, pruning, OAK shuttle
(SPEC-BART §5.5, §11 Step 1)."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from app import bart_pairs, bart_stations
from tests.test_bart_pairs import arr_epoch, dep_epoch, find_trip, make_stu, platform_of, rows_for


def now_at(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def test_walnut_creek_to_dublin_transfers_at_west_oakland(bart_feed):
    rows = rows_for(bart_feed, "walnut_creek", "dublin_pleasanton")
    assert rows
    for row in rows:
        assert [leg["line"] for leg in row["legs"]] == ["Yellow", "Blue"]
        assert [xfer["station"] for xfer in row["transfers"]] == ["west_oakland"]
        assert row["transfers"][0]["wait_minutes"] >= 0
        # top-level mirrors leg 1's origin and the last leg's arrival (§7.2)
        assert row["departure"] == row["legs"][0]["departure"]
        assert row["arrival"] == row["legs"][-1]["arrival"]
        assert row["status"] == row["legs"][0]["status"]
        assert row["legs"][0]["from"] == "walnut_creek"
        assert row["legs"][0]["to"] == "west_oakland"
        assert row["legs"][1]["to"] == "dublin_pleasanton"


def test_direct_pairs_never_return_transfer_rows(bart_feed):
    for row in rows_for(bart_feed, "embarcadero", "walnut_creek", limit=10):
        assert "legs" not in row


def _serves(trip_id: str, from_abbr: str, to_abbr: str) -> bool:
    pattern = bart_stations.trip_pattern(trip_id)
    if pattern is None:
        return False
    origin, destination = pattern.get(from_abbr), pattern.get(to_abbr)
    return origin is not None and destination is not None and destination[0] > origin[0]


def _wcrk_dubl_synthetic(leg2_departures: list[int], leg1_arr: int = 2000, leg1_delay: int = 0):
    """A minimal WCRK→DUBL world: one Yellow leg to WOAK, Blue legs onward.

    All STUs use the same WOAK platform, and a same-platform pair is never in
    the bundled transfer table → the 180 s default applies (§5.5-3).
    """
    yellow = find_trip("WCRK", "WOAK")
    blues = [tid for tid in bart_stations.TRIPS if _serves(tid, "WOAK", "DUBL")]
    assert len(blues) >= len(leg2_departures)
    woak_platform = platform_of("WOAK")
    assert bart_stations.transfer_min_s(woak_platform, woak_platform, -1) == -1
    trips = [
        {"trip_id": yellow, "stops": [
            make_stu("WCRK", None, 1000, delay=leg1_delay),
            make_stu("WOAK", leg1_arr, leg1_arr + 20, delay=leg1_delay, stop_id=woak_platform),
        ]},
    ]
    for blue, dep in zip(blues, leg2_departures):
        trips.append({"trip_id": blue, "stops": [
            make_stu("WOAK", dep - 20, dep, stop_id=woak_platform),
            make_stu("DUBL", dep + 1500, None),
        ]})
    return {"trips": trips}


def test_min_transfer_default_applies_when_platform_pair_unknown():
    # same-platform "transfer" pair is never in the bundled table → 180 s
    feed = _wcrk_dubl_synthetic(leg2_departures=[2100, 2400])
    [row] = rows_for(feed, "walnut_creek", "dublin_pleasanton", now=now_at(900), limit=4)
    # 2100 is only 100 s after the 2000 arrival — infeasible; 2400 clears 180 s
    assert dep_epoch(row["legs"][1]) == 2400
    assert row["transfers"][0]["wait_minutes"] == round((2400 - 2000) / 60)


def test_min_transfer_uses_bundled_table_when_pair_present():
    # find a directed platform pair BART publishes with a sub-default minimum
    pair = next(
        (from_p, to_p, seconds)
        for from_p, targets in bart_stations.TRANSFERS.items()
        for to_p, seconds in targets.items()
        if seconds < 180 and from_p != to_p
        and bart_stations.parent_of_platform(from_p) == bart_stations.parent_of_platform(to_p)
    )
    from_platform, to_platform, min_s = pair
    at_abbr = bart_stations.parent_of_platform(from_platform)

    leg1 = {"legs": [{"trip": "a"}], "transfers": [], "_dep_epoch": 1000,
            "_arr_epoch": 2000, "_dep_platform": None, "_arr_platform": from_platform}
    # departs sooner than the 180 s default allows, but the table allows it
    leg2 = {"legs": [{"trip": "b"}], "transfers": [], "_dep_epoch": 2000 + min_s + 10,
            "_arr_epoch": 4000, "_dep_platform": to_platform, "_arr_platform": None}
    station = bart_stations.by_abbr(at_abbr)
    stitched = bart_pairs._stitch([leg1], [leg2], station)
    assert len(stitched) == 1
    assert stitched[0]["_arr_epoch"] == 4000


def test_late_leg1_rolls_to_next_feasible_connection():
    on_time = _wcrk_dubl_synthetic(leg2_departures=[2200, 3400], leg1_arr=2000)
    [row] = rows_for(on_time, "walnut_creek", "dublin_pleasanton", now=now_at(900), limit=4)
    assert row["transfers"][0]["wait_minutes"] == round((2200 - 2000) / 60)

    delayed = _wcrk_dubl_synthetic(leg2_departures=[2200, 3400], leg1_arr=3000, leg1_delay=1000)
    [row] = rows_for(delayed, "walnut_creek", "dublin_pleasanton", now=now_at(900), limit=4)
    # expected (not aimed) arrival drives the connection: 2200 is now infeasible
    assert row["transfers"][0]["wait_minutes"] == round((3400 - 3000) / 60)
    assert row["status"] == "late"
    assert row["delay_seconds"] == 1000


def test_delay_propagation_on_the_captured_feed(bart_feed):
    [first, *_] = rows_for(bart_feed, "walnut_creek", "dublin_pleasanton")
    leg1_trip = first["legs"][0]["trip"]
    original_leg2_dep = dep_epoch(first["legs"][1])

    delayed = copy.deepcopy(bart_feed)
    for trip in delayed["trips"]:
        if trip["trip_id"] != leg1_trip:
            continue
        for stu in trip["stops"]:
            if bart_stations.parent_of_platform(stu["stop_id"]) == "WOAK":
                for event in (stu["arrival"], stu["departure"]):
                    if event:
                        event["time"] += 900
                        event["delay"] = (event["delay"] or 0) + 900

    rows = rows_for(delayed, "walnut_creek", "dublin_pleasanton", limit=10)
    same_leg1 = [row for row in rows if row["legs"][0]["trip"] == leg1_trip]
    for row in same_leg1:
        assert dep_epoch(row["legs"][1]) > original_leg2_dep


def test_dominated_itineraries_are_pruned():
    itineraries = [
        {"legs": [], "transfers": [], "_dep_epoch": 100, "_arr_epoch": 3000,
         "_dep_platform": None, "_arr_platform": None},
        {"legs": [], "transfers": [], "_dep_epoch": 200, "_arr_epoch": 3000,
         "_dep_platform": None, "_arr_platform": None},  # dominates the first
        {"legs": [], "transfers": [], "_dep_epoch": 150, "_arr_epoch": 2500,
         "_dep_platform": None, "_arr_platform": None},  # dominates the first too
    ]
    kept = bart_pairs._prune_dominated(itineraries)
    assert [(i["_dep_epoch"], i["_arr_epoch"]) for i in kept] == [(150, 2500), (200, 3000)]


# --- OAK airport shuttle (never in GTFS-RT; synthesized) ----------------------


def test_oakl_to_coliseum_synthesizes_headway_rows(bart_feed):
    rows = rows_for(bart_feed, "oakland_international_airport", "coliseum")
    assert rows
    headway = bart_stations.OAK_SHUTTLE["headway_s"]
    for row in rows:
        assert row["line"] == "Grey"
        assert row["status"] == "scheduled"
        assert row["arrival"]["estimated"] is True
        assert "legs" not in row
    gaps = [dep_epoch(b) - dep_epoch(a) for a, b in zip(rows, rows[1:])]
    assert all(gap == headway for gap in gaps)


def test_embarcadero_to_oakl_stitches_grey_at_coliseum(bart_feed):
    rows = rows_for(bart_feed, "embarcadero", "oakland_international_airport")
    assert rows
    for row in rows:
        assert row["legs"][-1]["line"] == "Grey"
        assert row["transfers"][-1]["station"] == "coliseum"
        assert len(row["legs"]) <= 3
        assert arr_epoch(row) > dep_epoch(row)


def test_distant_origin_to_oakl_reaches_beyond_the_shuttle_ladder(bart_feed):
    # ANTC→OAKL: first legs arrive at Coliseum well over an hour out — the
    # synthesized shuttle must anchor at each connection's arrival, not `now`
    rows = rows_for(bart_feed, "antioch", "oakland_international_airport", limit=10)
    assert rows
    for row in rows:
        assert row["legs"][-1]["line"] == "Grey"
        assert row["transfers"][-1]["station"] == "coliseum"
        assert len(row["legs"]) <= 3
        # the shuttle leg departs after its connection arrives, with a sane wait
        assert 0 <= row["transfers"][-1]["wait_minutes"] <= 15


# --- connection-at-risk flag (SPEC-V2 §2) ------------------------------------


def test_tight_connection_is_flagged_at_risk():
    # default min-transfer is 180 s; a 2200 departure against a 2000 arrival
    # leaves 20 s of slack — feasible but flagged
    feed = _wcrk_dubl_synthetic(leg2_departures=[2200])
    [row] = rows_for(feed, "walnut_creek", "dublin_pleasanton", now=now_at(900), limit=4)
    assert row["transfers"][0]["at_risk"] is True


def test_comfortable_realtime_connection_is_not_flagged():
    # 2400 departure → 220 s slack over the 180 s minimum, realtime leg 1
    feed = _wcrk_dubl_synthetic(leg2_departures=[2400])
    [row] = rows_for(feed, "walnut_creek", "dublin_pleasanton", now=now_at(900), limit=4)
    assert "at_risk" not in row["transfers"][0]


def _stitch_with_leg1_arrival(arrival_payload: dict | None, leg2_dep: int):
    station = bart_stations.by_abbr("WOAK")
    first = {
        "legs": [{"trip": "a", "arrival": arrival_payload}],
        "transfers": [],
        "_dep_epoch": 1000, "_arr_epoch": 2000,
        "_dep_platform": None, "_arr_platform": None,
    }
    second = {
        "legs": [{"trip": "b", "arrival": {"aimed": None, "expected": None}}],
        "transfers": [],
        "_dep_epoch": leg2_dep, "_arr_epoch": leg2_dep + 1000,
        "_dep_platform": None, "_arr_platform": None,
    }
    [stitched] = bart_pairs._stitch([first], [second], station)
    return stitched["transfers"][0]


def test_estimated_leg1_arrival_widens_the_at_risk_band():
    estimated = {"aimed": None, "expected": None, "estimated": True}
    # 2400 dep → 220 s slack: fine for realtime, at risk when leg 1 is estimated
    assert "at_risk" not in _stitch_with_leg1_arrival({"aimed": None, "expected": None}, 2400)
    assert _stitch_with_leg1_arrival(estimated, 2400)["at_risk"] is True
    # 2600 dep → 420 s slack: comfortable even for an estimated arrival
    assert "at_risk" not in _stitch_with_leg1_arrival(estimated, 2600)


def test_at_risk_itinerary_is_still_ranked_and_kept():
    # the flag warns, it never filters (§2.2): a tight itinerary that wins on
    # arrival is returned, flagged
    feed = _wcrk_dubl_synthetic(leg2_departures=[2200, 3400])
    [row] = rows_for(feed, "walnut_creek", "dublin_pleasanton", now=now_at(900), limit=4)
    assert dep_epoch(row["legs"][1]) == 2200
    assert row["transfers"][0]["at_risk"] is True


def test_oakl_to_walnut_creek_allows_three_legs(bart_feed):
    rows = rows_for(bart_feed, "oakland_international_airport", "walnut_creek")
    assert rows
    for row in rows:
        assert row["legs"][0]["line"] == "Grey"
        assert 2 <= len(row["legs"]) <= 3
        assert len(row["transfers"]) == len(row["legs"]) - 1
        # itinerary times strictly progress across legs
        epochs = [dep_epoch(leg) for leg in row["legs"]]
        assert epochs == sorted(epochs)
