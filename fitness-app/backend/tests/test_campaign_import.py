"""
ARISE v3 §4.3 — campaign import: the data.js item parser (every distinct
string in the real file), the full import (3 arcs × 7 templates), the API's
409 / replace semantics and objective seeding, and the script's loader.
"""
from datetime import date, timedelta

import pytest

from app.models.campaign import Campaign, CampaignStatus, HuntTemplate, PlannedHunt
from app.models.goal import Goal
from app.services import campaign_service
from app.services.campaign_service import (
    arc_weeks_from_label,
    parse_item,
    parse_phases,
    parse_run_spec,
    resolve_family,
)
from app.services.exercise_family_defs import FAMILY_DEFS
from tests.helpers_w1 import MONDAY, family_exercise, import_plan, load_phases, make_user

# Every distinct [name, spec] pair in the owner's plan, with the item it must parse to.
EXPECTED_ITEMS = {
    ("Easy pace run", "2–2.5 mi"): {"run": "easy", "miles": [2.0, 2.5]},
    ("Easy pace run", "2.5–3 mi"): {"run": "easy", "miles": [2.5, 3.0]},
    ("Easy pace run", "2–3 mi"): {"run": "easy", "miles": [2.0, 3.0]},
    ("Easy pace run", "3–3.5 mi"): {"run": "easy", "miles": [3.0, 3.5]},
    ("Long run", "3 → 4.5 mi (build weekly)"): {"run": "long", "miles": "arc"},
    ("Long run", "5 → 6 mi (build weekly)"): {"run": "long", "miles": "arc"},
    ("Long run", "6.5 → 7+ mi"): {"run": "long", "miles": "arc"},
    ("Easy shakeout run", "2 mi"): {"run": "shakeout", "miles": [2.0, 2.0]},
    ("Core circuit", "10 min"): {"note": "Core circuit — 10 min"},
    ("Light accessory only", "15–20 min"): {"note": "Light accessory only — 15–20 min"},
    ("DB incline press", "3×12"): {"family": "incline_db_bench_press", "sets": 3, "reps": [12, 12], "increment_lb": 2.5},
    ("Lateral raises", "3×15"): {"family": "lateral_raise", "sets": 3, "reps": [15, 15], "increment_lb": 2.5},
    ("Barbell row or pull-ups", "3×10"): {"family": "barbell_row", "alternatives": ["pull_up"], "sets": 3, "reps": [10, 10]},
    ("Curls / triceps", "3×12"): {"family": "db_curl", "alternatives": ["tricep_pushdown"], "sets": 3, "reps": [12, 12]},
    ("Back Squat", "5×5"): {"family": "back_squat", "sets": 5, "reps": [5, 5], "increment_lb": 5.0},
    ("Deadlift", "4×5"): {"family": "deadlift", "sets": 4, "reps": [5, 5], "increment_lb": 5.0},
    ("Leg press or lunges", "3×12"): {"family": "leg_press", "alternatives": ["lunge"], "sets": 3, "reps": [12, 12]},
    ("Hanging leg raise", "3×12"): {"family": "hanging_leg_raise", "sets": 3, "reps": [12, 12]},
    ("Bench Press", "5×5"): {"family": "bench_press", "sets": 5, "reps": [5, 5]},
    ("Overhead Press", "4×6"): {"family": "overhead_press", "sets": 4, "reps": [6, 6]},
    ("Barbell Row", "4×8"): {"family": "barbell_row", "sets": 4, "reps": [8, 8]},
    ("Close-grip bench", "3×10"): {"family": "close_grip_bench", "sets": 3, "reps": [10, 10]},
    ("DB bench or OHP", "3×10"): {"family": "db_bench_press", "alternatives": ["overhead_press"], "sets": 3, "reps": [10, 10]},
    ("Lat pulldown", "3×12"): {"family": "lat_pulldown", "sets": 3, "reps": [12, 12]},
}


def _all_pairs():
    pairs = {}
    for phase in load_phases():
        for day in phase["days"]:
            for name, spec in day["items"]:
                pairs.setdefault((name, spec), (day["type"], day["items"].index([name, spec])))
    return pairs


class TestParser:
    def test_every_distinct_string_in_data_js_is_covered(self):
        assert set(_all_pairs()) == set(EXPECTED_ITEMS), "data.js changed — update EXPECTED_ITEMS"

    @pytest.mark.parametrize("pair", sorted(EXPECTED_ITEMS), ids=lambda p: f"{p[0]} {p[1]}")
    def test_item_parses_to_expected_shape(self, pair):
        day_type, _ = _all_pairs()[pair]
        item, warning = parse_item(pair[0], pair[1], day_type=day_type, lift_index=0)
        assert warning is None
        assert not item.get("unparsed")
        for key, value in EXPECTED_ITEMS[pair].items():
            assert item[key] == value, (pair, key, item)
        if "family" in item:
            assert item["family"] in FAMILY_DEFS
            for alt in item.get("alternatives", []):
                assert alt in FAMILY_DEFS

    def test_roles_progression_and_rpe_cap_on_a_lift_day(self):
        main, _ = parse_item("Back Squat", "5×5", day_type="lift", lift_index=0)
        secondary, _ = parse_item("Deadlift", "4×5", day_type="lift", lift_index=1)
        accessory, _ = parse_item("Leg press or lunges", "3×12", day_type="lift", lift_index=2)
        row, _ = parse_item("Barbell Row", "4×8", day_type="lift", lift_index=2)
        assert (main["role"], main["progression"], main["rpe_cap"]) == ("main", "linear", 8)
        assert (secondary["role"], secondary["progression"], secondary["rpe_cap"]) == ("secondary", "linear", 9)
        assert (accessory["role"], accessory["progression"]) == ("accessory", "double")
        assert row["progression"] == "double"          # accessory role regardless of rep count

    def test_light_day_items_are_all_accessory(self):
        item, _ = parse_item("DB incline press", "3×12", day_type="light", lift_index=0)
        assert item["role"] == "accessory"
        assert item["progression"] == "double"
        assert item["rpe_cap"] == 9

    def test_secondary_with_high_reps_is_double(self):
        item, _ = parse_item("Overhead Press", "4×8", day_type="lift", lift_index=1)
        assert (item["role"], item["progression"]) == ("secondary", "double")

    def test_rep_range_parses(self):
        item, _ = parse_item("Leg press", "3×10-12", day_type="lift", lift_index=2)
        assert item["reps"] == [10, 12]

    def test_unresolvable_name_becomes_flagged_note(self):
        item, warning = parse_item("Mystery machine", "3×10", day_type="lift", lift_index=0)
        assert item == {"note": "Mystery machine — 3×10", "unparsed": True}
        assert "unresolved" in warning

    def test_unparseable_spec_is_flagged(self):
        item, warning = parse_item("Back Squat", "lots", day_type="lift", lift_index=0)
        assert item["unparsed"] is True
        assert "could not parse" in warning

    def test_unresolved_alternative_is_dropped_with_warning(self):
        item, warning = parse_item("Back Squat or hoverboard", "5×5", day_type="lift", lift_index=0)
        assert item["family"] == "back_squat"
        assert "alternatives" not in item
        assert "hoverboard" in warning

    def test_resolve_family_prefers_seed_index_then_synonyms(self):
        assert resolve_family("Barbell Row") == "barbell_row"      # seed canonical
        assert resolve_family("pull-ups") == "pull_up"              # seed alias
        assert resolve_family("Close-grip bench") == "close_grip_bench"   # synonyms table
        assert resolve_family("nothing here") is None

    def test_run_spec_kinds(self):
        assert parse_run_spec("Easy pace run", "2 mi") == {"run": "easy", "miles": [2.0, 2.0]}
        assert parse_run_spec("Long run", "6.5 → 7+ mi") == {"run": "long", "miles": "arc"}
        assert parse_run_spec("Easy shakeout run", "2 mi")["run"] == "shakeout"
        assert parse_run_spec("Long run", "banana") is None

    def test_arc_weeks_from_label(self):
        assert arc_weeks_from_label("Months 1–2") == 8
        assert arc_weeks_from_label("Months 3-4") == 8
        assert arc_weeks_from_label("Months 1–3") == 12
        assert arc_weeks_from_label("Base") == 8
        assert arc_weeks_from_label(None) == 8

    def test_parse_phases_full_plan_zero_warnings(self):
        arcs, warnings = parse_phases(load_phases())
        assert warnings == []
        assert [a["weeks"] for a in arcs] == [8, 8, 8]
        assert [(a["run_miles_min"], a["run_miles_max"], a["long_run_miles"]) for a in arcs] == [
            (7, 13, 4.5), (13, 19, 6), (19, 25, 7),
        ]
        for arc in arcs:
            assert len(arc["templates"]) == 7
            assert sorted(t["weekday"] for t in arc["templates"]) == list(range(7))
        tue = next(t for t in arcs[0]["templates"] if t["weekday"] == 1)
        assert tue["location_tag"] == "WFH"
        assert tue["title"] == "Optional Light Work"
        sat = next(t for t in arcs[0]["templates"] if t["weekday"] == 5)
        assert [i["role"] for i in sat["items"]] == ["main", "secondary", "accessory", "accessory"]
        assert sat["load_hint"] == 100


class TestImportService:
    def test_full_import_creates_arcs_templates_and_no_warnings(self, db, create_test_user):
        user = make_user(create_test_user, "import")
        campaign, warnings = import_plan(db, user.id)
        assert warnings == []
        assert campaign.status == CampaignStatus.ACTIVE.value
        assert campaign.start_date == MONDAY
        assert len(campaign.arcs) == 3
        assert db.query(HuntTemplate).join(campaign.arcs[0].__class__).filter(
            campaign.arcs[0].__class__.campaign_id == campaign.id
        ).count() == 21
        assert [a.deload_every_n_weeks for a in campaign.arcs] == [4, 4, 4]
        assert [a.deload_factor for a in campaign.arcs] == [0.75, 0.75, 0.75]
        assert campaign_service.campaign_end_date(campaign) == MONDAY + timedelta(weeks=24) - timedelta(days=1)

    def test_increment_comes_from_exercise_families_table(self, db, create_test_user):
        user = make_user(create_test_user, "inc")
        campaign, _ = import_plan(db, user.id)
        sat = next(t for t in campaign.arcs[0].templates if t.weekday == 5)
        squat = sat.items[0]
        assert (squat["family"], squat["increment_lb"]) == ("back_squat", 5.0)
        tue = next(t for t in campaign.arcs[0].templates if t.weekday == 1)
        assert tue.items[0]["increment_lb"] == 2.5     # dumbbell family

    def test_second_import_without_replace_raises(self, db, create_test_user):
        user = make_user(create_test_user, "dup")
        import_plan(db, user.id)
        with pytest.raises(ValueError, match="active campaign exists"):
            campaign_service.import_campaign(db, user.id, name="again", phases=load_phases(), start_date=MONDAY)

    def test_replace_completes_old_and_deletes_future_planned(self, db, create_test_user):
        user = make_user(create_test_user, "replace")
        old, _ = import_plan(db, user.id)
        campaign_service.materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=13), today=MONDAY)
        db.commit()
        assert db.query(PlannedHunt).filter(PlannedHunt.campaign_id == old.id).count() == 14
        new = campaign_service.import_campaign(
            db, user.id, name="v2", phases=load_phases(), start_date=MONDAY, replace=True
        )
        db.commit()
        assert db.query(Campaign).get(old.id).status == CampaignStatus.COMPLETED.value
        assert db.query(PlannedHunt).filter(PlannedHunt.campaign_id == old.id).count() == 0
        assert campaign_service.get_active_campaign(db, user.id).id == new.campaign.id


class TestImportApi:
    def _body(self, **extra):
        body = {"name": "Run Base + Strength", "phases": load_phases(), "start_date": MONDAY.isoformat()}
        body.update(extra)
        return body

    def test_import_endpoint_returns_campaign_shape(self, client, auth_headers, unique_email):
        headers, _ = auth_headers(email=unique_email("imp-api"))
        resp = client.post("/campaign/import", json=self._body(client_date=MONDAY.isoformat()), headers=headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["warnings"] == []
        assert body["templates_created"] == 21
        assert len(body["arcs"]) == 3 and len(body["arcs"][0]["templates"]) == 7
        assert (body["current_arc_index"], body["week_in_arc"], body["deload_week"]) == (0, 1, False)
        assert body["week_start"] == MONDAY.isoformat()
        assert body["week_target_miles"] == 7.0
        assert body["end_date"] == (MONDAY + timedelta(weeks=24) - timedelta(days=1)).isoformat()

    def test_start_date_defaults_to_monday_of_client_week(self, client, auth_headers, unique_email):
        headers, _ = auth_headers(email=unique_email("imp-mon"))
        body = self._body(client_date=(MONDAY + timedelta(days=3)).isoformat())
        body.pop("start_date")
        resp = client.post("/campaign/import", json=body, headers=headers)
        assert resp.status_code == 201, resp.text
        assert resp.json()["start_date"] == MONDAY.isoformat()

    def test_conflict_then_replace(self, client, auth_headers, unique_email):
        headers, _ = auth_headers(email=unique_email("imp-409"))
        assert client.post("/campaign/import", json=self._body(), headers=headers).status_code == 201
        assert client.post("/campaign/import", json=self._body(), headers=headers).status_code == 409
        resp = client.post("/campaign/import", json=self._body(replace=True, name="Second"), headers=headers)
        assert resp.status_code == 201
        current = client.get("/campaign/current", headers=headers)
        assert current.status_code == 200 and current.json()["name"] == "Second"

    def test_current_404_without_campaign(self, client, auth_headers, unique_email):
        headers, _ = auth_headers(email=unique_email("imp-none"))
        assert client.get("/campaign/current", headers=headers).status_code == 404

    def test_objectives_seeded_under_campaign(self, client, db, auth_headers, unique_email):
        headers, user = auth_headers(email=unique_email("imp-obj"))
        bench = family_exercise(db, "Barbell Bench Press")
        body = self._body(objectives=[
            {"exercise_id": bench.id, "target_weight": 225, "target_reps": 1, "weight_unit": "lb", "by": "arc_end"},
            {"kind": "run", "target_miles": 12, "run_scope": "weekly", "by": "arc_end"},
            {"exercise_id": "nope", "target_weight": 100, "deadline": (date.today() + timedelta(days=30)).isoformat()},
        ])
        resp = client.post("/campaign/import", json=body, headers=headers)
        assert resp.status_code == 201, resp.text
        payload = resp.json()
        assert payload["objectives_created"] == 2
        assert any("Exercise not found" in w for w in payload["warnings"])
        goals = db.query(Goal).filter(Goal.user_id == user.id).all()
        assert {g.kind for g in goals} == {"strength", "run"}
        assert all(g.campaign_id == payload["id"] for g in goals)
        # by=arc_end → the last day of arc 1
        assert all(g.deadline == MONDAY + timedelta(weeks=8) - timedelta(days=1) for g in goals)

    def test_manual_create_and_update(self, client, auth_headers, unique_email):
        headers, _ = auth_headers(email=unique_email("imp-manual"))
        resp = client.post("/campaign", json={
            "name": "Manual", "start_date": MONDAY.isoformat(),
            "arcs": [{"name": "Base", "weeks": 4, "run_miles_min": 5, "run_miles_max": 9, "long_run_miles": 4}],
        }, headers=headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        arc_id = body["arcs"][0]["id"]
        resp = client.put(f"/campaign/{body['id']}", json={
            "name": "Manual v2", "arcs": [{"id": arc_id, "run_miles_max": 11}],
        }, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Manual v2"
        assert resp.json()["arcs"][0]["run_miles_max"] == 11
        resp = client.put(f"/campaign/{body['id']}", json={"status": "paused"}, headers=headers)
        assert resp.status_code == 200 and resp.json()["status"] == "paused"
        assert client.get("/campaign/current", headers=headers).status_code == 404
        assert client.put(f"/campaign/{body['id']}", json={"status": "bogus"}, headers=headers).status_code == 400


class TestScriptLoader:
    def test_load_phases_parses_data_js(self):
        phases = load_phases()
        assert [p["key"] for p in phases] == ["p1", "p2", "p3"]
        assert all(len(p["days"]) == 7 for p in phases)

    def test_dry_run_needs_no_credentials(self, capsys, monkeypatch):
        from scripts.import_training_calendar import main
        monkeypatch.delenv("SEED_USER_EMAIL", raising=False)
        monkeypatch.delenv("SEED_USER_PASSWORD", raising=False)
        assert main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "Loaded 3 phases" in out
        assert "Months 1–2" in out
