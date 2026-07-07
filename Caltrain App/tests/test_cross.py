"""Cross-agency Caltrain↔BART itineraries at Millbrae (SPEC-V2 §7)."""

from __future__ import annotations

from datetime import datetime, timezone

from app import bart_stations, cross, departures, schedule, stations
from app.main import app
from conftest import make_visit, payload_of
from fastapi.testclient import TestClient
from tests.test_bart_pairs import make_stu

client = TestClient(app)

PT = schedule.PACIFIC
# anchor everything on the 2026-07-06 service day, mid-afternoon
ANCHOR = int(datetime(2026, 7, 6, 12, 0, tzinfo=PT).timestamp()) - 12 * 3600
BASE = ANCHOR + 15 * 3600  # 3:00 PM PT


def iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def at(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def ct_payload(dep: int, arr: int, origin_stop: str = "70131", dest_stop: str = "70061"):
    """A Caltrain leg with realtime visits at both ends (default: San Carlos
    NB → Millbrae NB)."""
    return payload_of(
        make_visit("411", origin_stop, aimed_dep=iso(dep), expected_dep=iso(dep)),
        make_visit("411", dest_stop, aimed_arr=iso(arr), expected_arr=iso(arr)),
    )


def ba_feed(*trips) -> dict:
    return {"trips": list(trips)}


def ba_trip(from_abbr: str, to_abbr: str, dep: int, arr: int, skip: int = 0) -> dict:
    """A synthetic BA leg on a real bundled trip; skip picks a later distinct
    trip_id (index_feed keeps one entry per trip)."""
    trip_id = None
    for candidate in bart_stations.TRIPS:
        pattern = bart_stations.trip_pattern(candidate)
        origin, destination = pattern.get(from_abbr), pattern.get(to_abbr)
        if origin and destination and origin[0] < destination[0]:
            if skip == 0:
                trip_id = candidate
                break
            skip -= 1
    assert trip_id, f"no bundled trip serves {from_abbr}→{to_abbr}"
    return {
        "trip_id": trip_id,
        "stops": [make_stu(from_abbr, dep - 30, dep), make_stu(to_abbr, arr, arr + 30)],
    }


def itineraries(sm, feed, ct_id: str, ba_id: str, ct_first: bool, now: int, limit: int = 4):
    return cross.pair_itineraries(
        sm, feed, stations.get(ct_id), bart_stations.get(ba_id), ct_first, limit, now=at(now)
    )


# --- stitching -------------------------------------------------------------------


def test_ct_to_ba_stitches_at_millbrae():
    sm = ct_payload(dep=BASE + 600, arr=BASE + 1500)
    feed = ba_feed(ba_trip("MLBR", "EMBR", dep=BASE + 2400, arr=BASE + 4200))
    [row] = itineraries(sm, feed, "san_carlos", "embarcadero", True, BASE)
    assert [leg["agency"] for leg in row["legs"]] == ["ct", "ba"]
    assert row["legs"][0]["train_type"] == "Local"
    assert row["legs"][0]["from"] == "san_carlos"
    assert row["legs"][0]["to"] == "millbrae"
    assert row["legs"][1]["line"]  # BA leg renders the line pill
    assert row["transfers"] == [
        {"station": "millbrae", "station_name": "Millbrae", "wait_minutes": 15}
    ]
    # top level mirrors leg 1's origin and the last leg's arrival
    assert row["departure"] == row["legs"][0]["departure"]
    assert row["arrival"] == row["legs"][-1]["arrival"]
    assert row["status"] == row["legs"][0]["status"]
    # no top-level line/train — mixed legs mean the renderer reads legs
    assert "line" not in row and "train" not in row
    # no meta leaks
    assert not any(key.startswith("_") for leg in row["legs"] for key in leg)


def test_ba_to_ct_mirror_direction():
    feed = ba_feed(ba_trip("EMBR", "MLBR", dep=BASE + 300, arr=BASE + 1500))
    sm = ct_payload(dep=BASE + 2400, arr=BASE + 3600, origin_stop="70062", dest_stop="70132")
    [row] = itineraries(sm, feed, "san_carlos", "embarcadero", False, BASE)
    assert [leg["agency"] for leg in row["legs"]] == ["ba", "ct"]
    assert row["legs"][0]["to"] == "millbrae"
    assert row["legs"][1]["from"] == "millbrae"
    assert row["legs"][1]["to"] == "san_carlos"


def test_connection_below_the_ct_ba_minimum_rolls_to_the_next_train():
    sm = ct_payload(dep=BASE + 600, arr=BASE + 1500)
    feed = ba_feed(
        ba_trip("MLBR", "EMBR", dep=BASE + 1500 + 240, arr=BASE + 4000),  # < 300 s min
        ba_trip("MLBR", "EMBR", dep=BASE + 1500 + 900, arr=BASE + 4800, skip=1),
    )
    [row] = itineraries(sm, feed, "san_carlos", "embarcadero", True, BASE)
    assert row["transfers"][0]["wait_minutes"] == 15


def test_tight_cross_agency_connection_is_flagged_at_risk():
    sm = ct_payload(dep=BASE + 600, arr=BASE + 1500)
    feed = ba_feed(ba_trip("MLBR", "EMBR", dep=BASE + 1500 + 360, arr=BASE + 4200))
    [row] = itineraries(sm, feed, "san_carlos", "embarcadero", True, BASE)
    # 60 s of slack over the 300 s minimum → flagged (SPEC-V2 §2 via §7.3)
    assert row["transfers"][0]["at_risk"] is True


def test_estimated_ct_arrival_widens_the_at_risk_band():
    # no Millbrae visit → the CT arrival comes from the §8a schedule lookup,
    # marked estimated; a real bundled NB trip supplies the scheduled times
    trip_id, sched_arr = next(
        (tid, ANCHOR + s["70061"])
        for tid, s in schedule._DATA.items()
        if "70131" in s and "70061" in s and s["70131"] < s["70061"]
    )
    dep = ANCHOR + schedule._DATA[trip_id]["70131"]
    sm = payload_of(
        make_visit(trip_id, "70131", aimed_dep=iso(dep), expected_dep=iso(dep),
                   service_date="2026-07-06"),
    )
    feed = ba_feed(ba_trip("MLBR", "EMBR", dep=sched_arr + 300 + 200, arr=sched_arr + 4000))
    [row] = itineraries(sm, feed, "san_carlos", "embarcadero", True, dep - 300)
    assert row["legs"][0]["arrival"]["estimated"] is True
    # 200 s slack: fine for realtime, at risk under the estimated 300 s band
    assert row["transfers"][0]["at_risk"] is True


def test_ba_internal_transfer_extends_to_three_legs():
    # destination beyond Millbrae's direct reach: MLBR→WOAK (leg 2) then
    # WOAK→DUBL (leg 3) via the existing §5.5 machinery
    sm = ct_payload(dep=BASE + 600, arr=BASE + 1500)
    feed = ba_feed(
        ba_trip("MLBR", "WOAK", dep=BASE + 2400, arr=BASE + 4200),
        ba_trip("WOAK", "DUBL", dep=BASE + 4800, arr=BASE + 6600),
    )
    [row] = itineraries(sm, feed, "san_carlos", "dublin_pleasanton", True, BASE)
    assert [leg["agency"] for leg in row["legs"]] == ["ct", "ba", "ba"]
    assert [t["station"] for t in row["transfers"]] == ["millbrae", "west_oakland"]
    assert len(row["legs"]) <= 3


def test_ct_public_rows_carry_no_meta_keys():
    # byte-identity guard for the §7.4 refactor: the ct response path strips
    # the stitch meta entirely
    sm = ct_payload(dep=BASE + 600, arr=BASE + 1500)
    rows = departures.pair_departures(sm, "70131", "70061", 4, now=at(BASE))
    assert rows
    assert not any(key.startswith("_") for row in rows for key in row)


# --- endpoint validation (no upstream needed — validation precedes fetch) --------


def test_xa_requires_one_station_from_each_agency():
    resp = client.get("/api/departures?agency=xa&origin=ct:san_carlos&destination=ct:san_francisco")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_agency"


def test_xa_rejects_millbrae_endpoints_as_degenerate():
    resp = client.get("/api/departures?agency=xa&origin=ct:millbrae&destination=ba:embarcadero")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "degenerate_pair"
    resp = client.get("/api/departures?agency=xa&origin=ct:san_carlos&destination=ba:millbrae")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "degenerate_pair"


def test_xa_unknown_station_and_bad_prefix():
    resp = client.get("/api/departures?agency=xa&origin=ct:atlantis&destination=ba:embarcadero")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_station"
    resp = client.get("/api/departures?agency=xa&origin=san_carlos&destination=ba:embarcadero")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_agency"
