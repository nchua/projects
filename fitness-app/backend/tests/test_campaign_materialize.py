"""
ARISE v3 §4.4 / §5.2 — materialization (lazy, idempotent, past → skipped),
the arc ramp (week 1, deload week 4, week 8, first week of arc 2), the long
run progression, overrides, and the Coach applier primitives.
"""
from datetime import date, timedelta

import pytest

from app.models.campaign import PlannedHunt, PlannedHuntStatus
from app.services import campaign_service
from app.services.campaign_service import (
    apply_change_reps,
    apply_deload_now,
    apply_extend_arc,
    apply_set_progression,
    apply_set_week_miles,
    apply_swap_days,
    long_run_miles_for_week,
    materialize_range,
    next_planned_hunt_with_family,
    template_families,
    week_context,
    week_target_miles,
)
from tests.helpers_w1 import MONDAY, import_plan, load_phases, make_user, sat, weekday


def _week(n: int) -> date:
    return MONDAY + timedelta(weeks=n)


class TestRamp:
    @pytest.fixture
    def campaign(self, db, create_test_user):
        user = make_user(create_test_user, "ramp")
        campaign, _ = import_plan(db, user.id)
        return campaign

    def test_week_targets_match_the_pwa_ramp(self, db, campaign):
        # arc 1: 7 → 13 across 8 weeks, ×0.75 every 4th week
        assert week_target_miles(db, campaign, _week(0)) == 7.0
        assert week_target_miles(db, campaign, _week(3)) == pytest.approx(round((7 + 6 * 3 / 7) * 0.75, 1))
        assert week_target_miles(db, campaign, _week(7)) == pytest.approx(round(13 * 0.75, 1))
        assert week_target_miles(db, campaign, _week(6)) == pytest.approx(round(7 + 6 * 6 / 7, 1))
        # first week of arc 2 starts at that arc's min
        assert week_target_miles(db, campaign, _week(8)) == 13.0
        assert week_target_miles(db, campaign, _week(16)) == 19.0
        # before the campaign / after it
        assert week_target_miles(db, campaign, _week(-1)) is None
        assert week_target_miles(db, campaign, _week(24)) is None

    def test_week_context(self, campaign):
        ctx = week_context(campaign, _week(3) + timedelta(days=5))
        assert (ctx["arc_index"], ctx["week_in_arc"], ctx["campaign_week"], ctx["deload"]) == (0, 3, 4, True)
        ctx = week_context(campaign, _week(8))
        assert (ctx["arc_index"], ctx["week_in_arc"], ctx["campaign_week"]) == (1, 0, 9)
        assert week_context(campaign, MONDAY - timedelta(days=1)) is None
        assert week_context(campaign, _week(24)) is None

    def test_long_run_progression(self, campaign):
        assert long_run_miles_for_week(campaign, _week(0)) == 3.0
        assert long_run_miles_for_week(campaign, _week(7)) == pytest.approx(round(4.5 * 0.75, 1))
        assert long_run_miles_for_week(campaign, _week(6)) == pytest.approx(round(3 + 1.5 * 6 / 7, 1))
        assert long_run_miles_for_week(campaign, _week(8)) == 4.5        # arc 2 starts at arc 1's long run
        assert long_run_miles_for_week(campaign, _week(15)) == pytest.approx(round(6 * 0.75, 1))
        assert long_run_miles_for_week(campaign, _week(7), include_deload=False) == 4.5

    def test_overrides_win(self, db, campaign):
        campaign.overrides = {"week_miles": {_week(0).isoformat(): 5.5}, "deload_weeks": [_week(1).isoformat()]}
        assert week_target_miles(db, campaign, _week(0)) == 5.5
        assert week_context(campaign, _week(1))["deload"] is True
        assert week_target_miles(db, campaign, _week(1)) == pytest.approx(round((7 + 6 / 7) * 0.75, 1))


class TestMaterialize:
    def test_creates_rows_stamps_week_and_target_and_is_idempotent(self, db, create_test_user):
        user = make_user(create_test_user, "mat")
        import_plan(db, user.id)
        first = materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=13), today=MONDAY)
        db.commit()
        assert len(first) == 14
        assert all(h.status == PlannedHuntStatus.PLANNED.value for h in first)
        assert {h.week_start for h in first} == {MONDAY, MONDAY + timedelta(days=7)}
        assert {h.week_target_miles for h in first} == {7.0, round(7 + 6 / 7, 1)}
        assert all(h.prescription and h.prescription_version == 1 and h.generated_at for h in first)
        again = materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=13), today=MONDAY)
        db.commit()
        assert db.query(PlannedHunt).filter(PlannedHunt.user_id == user.id).count() == 14
        assert [h.id for h in again] == [h.id for h in first]
        assert all(h.prescription_version == 1 for h in again)   # unchanged base → no version bump

    def test_rest_weekday_without_template_yields_no_row(self, db, create_test_user):
        user = make_user(create_test_user, "rest")
        phases = load_phases()
        for phase in phases:
            phase["days"] = [d for d in phase["days"] if d["name"] != "Wednesday"]
        import_plan(db, user.id, phases=phases)
        rows = materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=6), today=MONDAY)
        db.commit()
        assert len(rows) == 6
        assert campaign_service.hunt_on(db, user.id, weekday(2)) is None

    def test_past_planned_flip_to_skipped(self, db, create_test_user):
        user = make_user(create_test_user, "skip")
        import_plan(db, user.id)
        materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=6), today=MONDAY)
        db.commit()
        rows = materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=6), today=weekday(3))
        db.commit()
        statuses = {h.date: h.status for h in rows}
        assert all(statuses[weekday(i)] == PlannedHuntStatus.SKIPPED.value for i in range(3))
        assert all(statuses[weekday(i)] == PlannedHuntStatus.PLANNED.value for i in range(3, 7))

    def test_no_campaign_materializes_nothing(self, db, create_test_user):
        user = make_user(create_test_user, "none")
        assert materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=6)) == []

    def test_template_families_and_next_hunt_with_family(self, db, create_test_user):
        user = make_user(create_test_user, "fam")
        campaign, _ = import_plan(db, user.id)
        sat_tmpl = next(t for t in campaign.arcs[0].templates if t.weekday == 5)
        assert template_families(sat_tmpl) == {
            "main": ["back_squat"], "secondary": ["deadlift"], "accessory": ["leg_press", "hanging_leg_raise"],
        }
        hunt = next_planned_hunt_with_family(db, user.id, "bench_press", MONDAY)
        db.commit()
        assert hunt is not None and hunt.date == weekday(6)
        assert next_planned_hunt_with_family(db, user.id, "back_squat", sat()).date == sat(1)


class TestAppliers:
    @pytest.fixture
    def ready(self, db, create_test_user):
        user = make_user(create_test_user, "apply")
        campaign, _ = import_plan(db, user.id)
        materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=13), today=MONDAY)
        db.commit()
        return user, campaign

    def _squat_sets(self, db, user_id, day):
        hunt = campaign_service.hunt_on(db, user_id, day)
        squat = next(e for e in hunt.prescription["exercises"] if e["family_id"] == "back_squat")
        return hunt, [s for s in squat["sets"] if not s["is_warmup"]]

    def test_set_progression_records_override_and_touches_only_family_hunts(self, db, ready):
        user, campaign = ready
        ids = apply_set_progression(db, campaign, "back_squat", 10, today=MONDAY)
        db.commit()
        assert campaign.overrides["progression"] == {"back_squat": 10.0}
        hunts = {h.id: h for h in db.query(PlannedHunt).filter(PlannedHunt.user_id == user.id).all()}
        assert {hunts[i].date for i in ids} == {sat(0), sat(1)}
        with pytest.raises(ValueError):
            apply_set_progression(db, campaign, "back_squat", 40, today=MONDAY)
        with pytest.raises(ValueError):
            apply_set_progression(db, campaign, "not_a_family", 5, today=MONDAY)

    def test_change_reps_rewrites_the_prescription(self, db, ready):
        user, campaign = ready
        ids = apply_change_reps(db, campaign, "back_squat", 3, [8], today=MONDAY)
        db.commit()
        assert len(ids) == 2
        _, sets = self._squat_sets(db, user.id, sat(0))
        assert len(sets) == 3 and all((s["target_reps_lo"], s["target_reps_hi"]) == (8, 8) for s in sets)
        with pytest.raises(ValueError):
            apply_change_reps(db, campaign, "back_squat", 11, [5], today=MONDAY)
        with pytest.raises(ValueError):
            apply_change_reps(db, campaign, "back_squat", 3, [12, 8], today=MONDAY)

    def test_set_week_miles_updates_targets(self, db, ready):
        user, campaign = ready
        ids = apply_set_week_miles(db, campaign, MONDAY + timedelta(days=7), 5.0, today=MONDAY)
        db.commit()
        assert len(ids) == 7
        week2 = [h for h in db.query(PlannedHunt).filter(PlannedHunt.user_id == user.id).all() if h.week_start == MONDAY + timedelta(days=7)]
        assert all(h.week_target_miles == 5.0 for h in week2)
        with pytest.raises(ValueError, match="Monday"):
            apply_set_week_miles(db, campaign, MONDAY + timedelta(days=8), 5.0, today=MONDAY)
        with pytest.raises(ValueError):
            apply_set_week_miles(db, campaign, MONDAY - timedelta(days=7), 5.0, today=MONDAY)

    def test_deload_now_scopes(self, db, ready):
        user, campaign = ready
        before_hunt, before = self._squat_sets(db, user.id, sat(0))
        ids = apply_deload_now(db, campaign, MONDAY, "all", today=MONDAY)
        db.commit()
        assert len(ids) == 7
        assert campaign.overrides["last_deload_week"] == MONDAY.isoformat()
        assert campaign.overrides["deload_weeks"] == [MONDAY.isoformat()]
        assert campaign.overrides["lift_deload_weeks"] == [MONDAY.isoformat()]
        after_hunt, after = self._squat_sets(db, user.id, sat(0))
        assert len(after) == len(before) - 1                       # main lifts drop one set
        assert after_hunt.week_target_miles == pytest.approx(round(7 * 0.75, 1))
        assert any(ln["key"] == "deload:lifts" for ln in after_hunt.rationale)
        with pytest.raises(ValueError):
            apply_deload_now(db, campaign, MONDAY, "arms", today=MONDAY)

    def test_swap_days_exchanges_templates(self, db, ready):
        user, campaign = ready
        ids = apply_swap_days(db, campaign, sat(0), weekday(0), today=MONDAY)
        db.commit()
        assert len(ids) == 2
        assert campaign_service.hunt_on(db, user.id, sat(0)).template.type == "run"
        assert campaign_service.hunt_on(db, user.id, weekday(0)).template.type == "lift"
        with pytest.raises(ValueError):
            apply_swap_days(db, campaign, sat(0), sat(0), today=MONDAY)
        with pytest.raises(ValueError):
            apply_swap_days(db, campaign, MONDAY - timedelta(days=1), sat(0), today=MONDAY)

    def test_extend_arc_shifts_later_arcs(self, db, ready):
        user, campaign = ready
        apply_extend_arc(db, campaign, 2, today=MONDAY)
        db.commit()
        assert campaign.arcs[0].weeks == 10
        assert week_context(campaign, MONDAY + timedelta(weeks=9))["arc_index"] == 0
        assert week_target_miles(db, campaign, MONDAY + timedelta(weeks=10)) == 13.0
        with pytest.raises(ValueError):
            apply_extend_arc(db, campaign, 5, today=MONDAY)
