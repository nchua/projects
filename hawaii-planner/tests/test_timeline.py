"""Unit tests for the pure timeline computation."""
from app.services.timeline import TimelineStop, compute_timeline, fmt_min

MATRIX = {
    frozenset(["WAI", "NS"]): (60, ["H1_PM"]),
    frozenset(["WAI", "EAST"]): (25, []),
    frozenset(["EAST", "NS"]): (80, []),
}


def lookup(a: str, b: str) -> tuple[int, list[str]]:
    if a == b:
        return 10, []
    return MATRIX[frozenset([a, b])]


def run(stops, start=510, end=1290, weekday=None):  # 08:30 - 21:30
    return compute_timeline(
        start_min=start, end_min=end, weekday=weekday, stops=stops, drive_lookup=lookup
    )


def stop(id="s1", region="NS", duration=90, **kwargs) -> TimelineStop:
    return TimelineStop(
        id=id, title=id, region_id=region, duration_min=duration, **kwargs
    )


def test_empty_day():
    result = run([])
    assert result["items"] == []
    assert result["return_leg"] is None
    assert result["total_drive_minutes"] == 0
    assert result["day_ends_at_min"] == 510
    assert result["warnings"] == []


def test_cascade_with_buffer_and_same_region_hop():
    result = run([stop("a", "NS", 90), stop("b", "NS", 60)])
    first, second = result["items"]
    # Hotel (WAI) -> NS: 60 matrix + 10 buffer
    assert first["drive_minutes"] == 70
    assert first["start_min"] == 580
    assert first["end_min"] == 670
    # Same-region hop: diagonal 10 + 10 buffer
    assert second["drive_minutes"] == 20
    assert second["start_min"] == 690
    # Return NS -> WAI: 70 again
    assert result["return_leg"]["drive_minutes"] == 70
    assert result["return_leg"]["arrive_hotel_min"] == 750 + 70
    assert result["total_drive_minutes"] == 70 + 20 + 70


def test_drive_flags_surface_on_legs():
    result = run([stop("a", "NS")])
    assert result["items"][0]["drive_flags"] == ["H1_PM"]


def test_pinned_feasible_emits_leave_by_and_free_gap():
    # Arrive would be 510 + 35 = 545; pin at 600 -> 55 free, leave_by 565
    result = run([stop("a", "EAST", 60, fixed_start_min=600)])
    item = result["items"][0]
    assert item["start_min"] == 600
    assert item["leave_by_min"] == 565
    assert item["free_gap_min"] == 55
    assert item["warnings"] == []


def test_pinned_late_warns_infeasible():
    late_pin = 520  # cannot make it: earliest arrival 545
    result = run([stop("a", "EAST", 60, fixed_start_min=late_pin)])
    item = result["items"][0]
    warnings = [warning["code"] for warning in item["warnings"]]
    assert warnings == ["infeasible_arrival"]
    assert item["warnings"][0]["late_minutes"] == 25
    assert item["start_min"] == late_pin  # pin holds; humans resolve


def test_overpacked_via_return_leg():
    result = run([stop("a", "NS", 90)], end=700)
    assert [warning["code"] for warning in result["warnings"]] == ["overpacked"]


def test_closed_day_warning_only_with_date():
    closed = stop("a", "EAST", 60, closed_days=frozenset({"mon", "tue"}))
    with_date = run([closed], weekday="mon")
    without_date = run([closed], weekday=None)
    assert [w["code"] for w in with_date["items"][0]["warnings"]] == ["closed_on_day"]
    assert without_date["items"][0]["warnings"] == []


def test_drive_override_replaces_matrix_and_buffer():
    result = run([stop("a", "NS", 90, drive_override_min=45)])
    assert result["items"][0]["drive_minutes"] == 45
    assert result["items"][0]["start_min"] == 555


def test_free_text_stop_inherits_previous_region():
    result = run([stop("a", "NS", 90), stop("b", None, 30)])
    second = result["items"][1]
    assert second["region_id"] == "NS"
    assert second["drive_minutes"] == 20  # same-region hop
    # Return leg computed from inherited NS
    assert result["return_leg"]["from_region_id"] == "NS"


def test_fmt_min_wraps_past_midnight():
    assert fmt_min(510) == "08:30"
    assert fmt_min(1470) == "00:30"
