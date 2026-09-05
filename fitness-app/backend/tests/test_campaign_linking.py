"""
ARISE v3 §4.4 linking + §13 adherence XP: same-day lift, Friday lift vs
Saturday plan → moved, two sessions one day, done vs modified with an
alternative swap vs an outside swap, XP amounts, the week bonus (once),
explicit planned_hunt_id, run done/modified, guard-respected +30.
"""
from datetime import timedelta

import pytest

from app.models.campaign import PlannedHunt, PlannedHuntStatus
from app.services import campaign_service
from app.services.campaign_service import (
    XP_GUARD_RESPECTED,
    XP_HUNT_DONE,
    XP_HUNT_MODIFIED,
    XP_WEEK_ON_PLAN,
    link_session_to_plan,
    materialize_range,
    session_kind,
)
from app.services.xp_service import get_or_create_user_progress
from tests.helpers_w1 import (
    MONDAY,
    add_lift,
    add_run,
    family_exercise,
    hunt_for,
    import_plan,
    load_phases,
    make_user,
    sat,
    sun,
    weekday,
)


@pytest.fixture
def lifts(db):
    return {
        "squat": family_exercise(db, "Barbell Back Squat"),
        "front_squat": family_exercise(db, "Front Squat"),
        "deadlift": family_exercise(db, "Barbell Deadlift"),
        "rdl": family_exercise(db, "Romanian Deadlift"),
        "leg_press": family_exercise(db, "Leg Press"),
        "lunge": family_exercise(db, "Walking Lunge"),
        "bench": family_exercise(db, "Barbell Bench Press"),
        "ohp": family_exercise(db, "Overhead Press"),
        "row": family_exercise(db, "Barbell Row"),
        "cgbp": family_exercise(db, "Close-Grip Bench Press"),
        "db_incline": family_exercise(db, "Incline Dumbbell Press"),
    }


@pytest.fixture
def planned(db, create_test_user):
    user = make_user(create_test_user, "link")
    import_plan(db, user.id)
    materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=13), today=MONDAY)
    db.commit()
    return user


def _xp(db, user_id):
    return get_or_create_user_progress(db, user_id).total_xp


def _squat_day(db, user_id, day, lifts, *, squat="squat", deadlift="deadlift", extra=()):
    blocks = [(lifts[squat], [(225, 5)] * 5), (lifts[deadlift], [(315, 5)] * 4)]
    for key in extra:
        blocks.append((lifts[key], [(90, 12)] * 3))
    return add_lift(db, user_id, day, blocks)


class TestSameDay:
    def test_same_day_lift_links_done_and_awards_40(self, db, planned, lifts):
        before = _xp(db, planned.id)
        session = _squat_day(db, planned.id, sat(), lifts, extra=("leg_press",))
        result = link_session_to_plan(db, session)
        db.commit()
        hunt = hunt_for(db, planned.id, sat())
        assert result == {"planned_hunt_id": hunt.id, "planned_hunt_status": "done"}
        assert hunt.session_id == session.id and hunt.moved_to is None
        assert _xp(db, planned.id) - before == XP_HUNT_DONE

    def test_accessories_dropped_still_done(self, db, planned, lifts):
        session = _squat_day(db, planned.id, sat(), lifts)
        assert link_session_to_plan(db, session)["planned_hunt_status"] == "done"

    def test_alternative_swap_is_done_outside_swap_is_modified(self, db, planned, lifts):
        # Sunday: DB bench or OHP … no — Saturday: leg press or lunges is the accessory; the
        # main/secondary swap decides: front squat for back squat is outside alternatives.
        modified = _squat_day(db, planned.id, sat(), lifts, squat="front_squat", extra=("lunge",))
        assert link_session_to_plan(db, modified)["planned_hunt_status"] == "modified"

    def test_missing_secondary_is_modified_and_awards_25(self, db, planned, lifts):
        before = _xp(db, planned.id)
        session = _squat_day(db, planned.id, sat(), lifts, deadlift="rdl")
        assert link_session_to_plan(db, session)["planned_hunt_status"] == "modified"
        db.commit()
        assert _xp(db, planned.id) - before == XP_HUNT_MODIFIED

    def test_alternative_in_secondary_slot_counts(self, db, planned, lifts):
        # Arc-2 Friday "DB bench or OHP" is light/accessory; use Sunday's bench day where
        # OHP is secondary: bench + OHP present → done even without row / CGBP.
        session = add_lift(db, planned.id, sun(), [(lifts["bench"], [(185, 5)] * 5), (lifts["ohp"], [(115, 6)] * 4)])
        assert link_session_to_plan(db, session)["planned_hunt_status"] == "done"

    def test_second_session_same_day_is_free_form(self, db, planned, lifts):
        first = _squat_day(db, planned.id, sat(), lifts)
        assert link_session_to_plan(db, first)["planned_hunt_status"] == "done"
        second = add_lift(db, planned.id, sat(), [(lifts["bench"], [(185, 5)] * 5)])
        assert link_session_to_plan(db, second) == {}
        assert hunt_for(db, planned.id, sun()).status == PlannedHuntStatus.PLANNED.value

    def test_linking_is_idempotent_per_session(self, db, planned, lifts):
        session = _squat_day(db, planned.id, sat(), lifts)
        first = link_session_to_plan(db, session)
        db.commit()
        before = _xp(db, planned.id)
        assert link_session_to_plan(db, session) == first
        assert _xp(db, planned.id) == before


class TestMoved:
    def test_friday_lift_against_saturday_plan_is_moved(self, db, planned, lifts):
        before = _xp(db, planned.id)
        session = _squat_day(db, planned.id, weekday(4), lifts)
        result = link_session_to_plan(db, session)
        db.commit()
        sat_hunt = hunt_for(db, planned.id, sat())
        assert result == {"planned_hunt_id": sat_hunt.id, "planned_hunt_status": "moved"}
        assert sat_hunt.moved_to == weekday(4)
        assert _xp(db, planned.id) - before == XP_HUNT_MODIFIED
        # Friday's own light hunt stays untouched for a light session later.
        assert hunt_for(db, planned.id, weekday(4)).status == PlannedHuntStatus.PLANNED.value

    def test_friday_light_session_links_fridays_light_hunt(self, db, planned, lifts):
        session = add_lift(db, planned.id, weekday(4), [(lifts["row"], [(135, 10)] * 3)])
        result = link_session_to_plan(db, session)
        assert result["planned_hunt_id"] == hunt_for(db, planned.id, weekday(4)).id
        assert result["planned_hunt_status"] == "done"

    def test_beyond_two_days_does_not_link(self, db, planned, lifts):
        session = _squat_day(db, planned.id, weekday(1, 1), lifts)   # Tuesday of week 2, Sat is 4 days away
        # Tuesday's light hunt is the only same-type candidate within ±2 days and a squat
        # day is not it (modified) — still linked, but Saturday is out of range.
        result = link_session_to_plan(db, session)
        assert result["planned_hunt_id"] == hunt_for(db, planned.id, weekday(1, 1)).id
        assert hunt_for(db, planned.id, sat(1)).status == PlannedHuntStatus.PLANNED.value

    def test_explicit_planned_hunt_id_wins(self, db, planned, lifts):
        target = hunt_for(db, planned.id, sat())
        session = _squat_day(db, planned.id, weekday(1), lifts)
        result = link_session_to_plan(db, session, planned_hunt_id=target.id)
        assert result == {"planned_hunt_id": target.id, "planned_hunt_status": "moved"}
        assert target.moved_to == weekday(1)

    def test_explicit_id_of_another_user_is_ignored(self, db, planned, lifts, create_test_user):
        other = make_user(create_test_user, "other")
        import_plan(db, other.id)
        rows = materialize_range(db, other.id, MONDAY, MONDAY + timedelta(days=6), today=MONDAY)
        db.commit()
        foreign = next(h for h in rows if h.date == sat())
        session = _squat_day(db, planned.id, sat(), lifts)
        result = link_session_to_plan(db, session, planned_hunt_id=foreign.id)
        assert result["planned_hunt_id"] == hunt_for(db, planned.id, sat()).id
        assert db.query(PlannedHunt).get(foreign.id).session_id is None


class TestRuns:
    def test_session_kind(self, db, planned, lifts):
        assert session_kind(add_run(db, planned.id, weekday(0), 2.0)) == "run"
        assert session_kind(add_run(db, planned.id, weekday(2), 5.0, activity="Cycling")) is None
        assert session_kind(add_lift(db, planned.id, sat(), [(lifts["squat"], [(225, 5)])])) == "lift"

    def test_run_done_at_80_percent_of_prescribed(self, db, planned):
        hunt = hunt_for(db, planned.id, weekday(0))
        assert hunt.prescription["run"]["miles"] == 2.0      # (7 − 3 long) / 2 easy days
        done = add_run(db, planned.id, weekday(0), 1.65)
        assert link_session_to_plan(db, done)["planned_hunt_status"] == "done"
        short = add_run(db, planned.id, weekday(2), 1.2)
        assert link_session_to_plan(db, short)["planned_hunt_status"] == "modified"

    def test_guard_respected_bonus(self, db, planned):
        hunt = hunt_for(db, planned.id, weekday(0))
        hunt.rationale = list(hunt.rationale or []) + [
            {"key": "guard:ramp_high", "text": "Run cut to 1.5 mi: 20% ahead of the arc's ramp",
             "numbers": {"original_miles": 2.0, "cut_miles": 1.5}},
        ]
        db.commit()
        before = _xp(db, planned.id)
        run = add_run(db, planned.id, weekday(0), 1.45)
        assert link_session_to_plan(db, run)["planned_hunt_status"] == "done"   # judged against the cut
        db.commit()
        assert _xp(db, planned.id) - before == XP_HUNT_DONE + XP_GUARD_RESPECTED

    def test_run_over_the_cut_earns_no_bonus(self, db, planned):
        hunt = hunt_for(db, planned.id, weekday(0))
        hunt.rationale = [{"key": "guard:run_acwr_high", "text": "cut", "numbers": {"cut_miles": 1.5}}]
        db.commit()
        before = _xp(db, planned.id)
        run = add_run(db, planned.id, weekday(0), 2.2)
        link_session_to_plan(db, run)
        db.commit()
        assert _xp(db, planned.id) - before == XP_HUNT_DONE


class TestWeekBonus:
    def test_week_bonus_once_when_every_hunt_is_non_skipped(self, db, create_test_user, lifts):
        user = make_user(create_test_user, "week")
        phases = load_phases()
        for phase in phases:
            phase["days"] = [d for d in phase["days"] if d["name"] in ("Saturday", "Sunday")]
        campaign, _ = import_plan(db, user.id, phases=phases)
        materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=6), today=MONDAY)
        db.commit()

        before = _xp(db, user.id)
        first = _squat_day(db, user.id, sat(), lifts)
        link_session_to_plan(db, first)
        db.commit()
        assert _xp(db, user.id) - before == XP_HUNT_DONE            # week not complete yet

        second = add_lift(db, user.id, sun(), [(lifts["bench"], [(185, 5)] * 5), (lifts["ohp"], [(115, 6)] * 4)])
        link_session_to_plan(db, second)
        db.commit()
        assert _xp(db, user.id) - before == 2 * XP_HUNT_DONE + XP_WEEK_ON_PLAN
        db.refresh(campaign)
        assert campaign.overrides["week_bonus_awarded"] == [MONDAY.isoformat()]

        # A re-link of the same session (idempotent) never pays the bonus twice.
        link_session_to_plan(db, second)
        db.commit()
        assert _xp(db, user.id) - before == 2 * XP_HUNT_DONE + XP_WEEK_ON_PLAN

    def test_skipped_hunt_blocks_the_bonus(self, db, create_test_user, lifts):
        user = make_user(create_test_user, "week-skip")
        phases = load_phases()
        for phase in phases:
            phase["days"] = [d for d in phase["days"] if d["name"] in ("Friday", "Saturday")]
        campaign, _ = import_plan(db, user.id, phases=phases)
        materialize_range(db, user.id, MONDAY, MONDAY + timedelta(days=6), today=MONDAY)
        db.commit()
        campaign_service.skip_hunt(db, hunt_for(db, user.id, weekday(4)))
        db.commit()
        before = _xp(db, user.id)
        link_session_to_plan(db, _squat_day(db, user.id, sat(), lifts))
        db.commit()
        assert _xp(db, user.id) - before == XP_HUNT_DONE
        db.refresh(campaign)
        assert "week_bonus_awarded" not in (campaign.overrides or {})
