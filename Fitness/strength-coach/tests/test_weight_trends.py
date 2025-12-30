"""Tests for weight trend analysis."""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from strength_coach.recomp.weight_trends import (
    WeightTrendAnalysis,
    analyze_weight_trends,
    calculate_rolling_average,
    detect_plateau,
    entries_to_dataframe,
    get_weight_history_summary,
)
from strength_coach.models import BodyWeightEntry, WeightUnit


def make_entries(weights: list[float], start_date: date = None) -> list[BodyWeightEntry]:
    """Helper to create body weight entries."""
    if start_date is None:
        start_date = date.today() - timedelta(days=len(weights) - 1)

    return [
        BodyWeightEntry(
            date=start_date + timedelta(days=i),
            weight=Decimal(str(w)),
            weight_unit=WeightUnit.LB,
        )
        for i, w in enumerate(weights)
    ]


class TestEntriesToDataframe:
    """Tests for entries_to_dataframe function."""

    def test_basic_conversion(self):
        """Should convert entries to DataFrame."""
        entries = make_entries([165.0, 166.0, 165.5])
        df = entries_to_dataframe(entries)

        assert len(df) == 3
        assert "date" in df.columns
        assert "weight_lb" in df.columns

    def test_empty_entries(self):
        """Empty entries should return empty DataFrame."""
        df = entries_to_dataframe([])
        assert len(df) == 0


class TestCalculateRollingAverage:
    """Tests for calculate_rolling_average function."""

    def test_7day_average(self):
        """Should calculate 7-day rolling average."""
        entries = make_entries([165.0] * 10)  # Constant weight
        df = entries_to_dataframe(entries)
        rolling = calculate_rolling_average(df, 7)

        # All averages should be 165
        assert all(abs(v - 165.0) < 0.1 for v in rolling.values)

    def test_with_variation(self):
        """Average should smooth out variation."""
        weights = [165.0, 166.0, 164.0, 167.0, 163.0, 166.0, 165.0]
        entries = make_entries(weights)
        df = entries_to_dataframe(entries)
        rolling = calculate_rolling_average(df, 7)

        # Average should be close to mean
        avg = sum(weights) / len(weights)
        assert abs(rolling.iloc[-1] - avg) < 1.0


class TestDetectPlateau:
    """Tests for detect_plateau function."""

    def test_no_plateau_with_change(self):
        """Should not detect plateau when weight is changing."""
        weights = [165.0 + i * 0.5 for i in range(20)]  # Steadily increasing
        entries = make_entries(weights)
        df = entries_to_dataframe(entries)
        rolling = calculate_rolling_average(df, 7)

        plateau_days = detect_plateau(rolling, threshold_lb=0.5, min_days=14)
        assert plateau_days == 0

    def test_plateau_detected(self):
        """Should detect plateau when weight is stable."""
        weights = [165.0] * 20  # Constant weight
        entries = make_entries(weights)
        df = entries_to_dataframe(entries)
        rolling = calculate_rolling_average(df, 7)

        plateau_days = detect_plateau(rolling, threshold_lb=0.5, min_days=14)
        assert plateau_days >= 14

    def test_insufficient_data(self):
        """Should return 0 with insufficient data."""
        weights = [165.0] * 5
        entries = make_entries(weights)
        df = entries_to_dataframe(entries)
        rolling = calculate_rolling_average(df, 7)

        plateau_days = detect_plateau(rolling, threshold_lb=0.5, min_days=14)
        assert plateau_days == 0


class TestAnalyzeWeightTrends:
    """Tests for analyze_weight_trends function."""

    def test_empty_entries(self):
        """Should handle empty entries."""
        result = analyze_weight_trends([])
        assert result.current_weight == Decimal("0")
        assert result.data_quality == "insufficient"
        assert "No weight data" in result.alerts[0]

    def test_stable_weight(self):
        """Should detect stable weight trend."""
        weights = [165.0 + (i % 3) * 0.2 for i in range(30)]  # Small fluctuation
        entries = make_entries(weights)
        result = analyze_weight_trends(entries)

        assert result.data_quality == "good"
        assert result.trend_4wk == "stable"

    def test_losing_weight(self):
        """Should detect weight loss trend."""
        weights = [170.0 - i * 0.2 for i in range(30)]  # Losing weight
        entries = make_entries(weights)
        result = analyze_weight_trends(entries)

        assert result.trend_4wk == "losing"
        assert result.weekly_change_lb < Decimal("0")

    def test_gaining_weight(self):
        """Should detect weight gain trend."""
        weights = [160.0 + i * 0.2 for i in range(30)]  # Gaining weight
        entries = make_entries(weights)
        result = analyze_weight_trends(entries)

        assert result.trend_4wk == "gaining"
        assert result.weekly_change_lb > Decimal("0")

    def test_rapid_loss_alert(self):
        """Should alert on rapid weight loss."""
        weights = [170.0 - i * 0.5 for i in range(14)]  # ~3.5 lb/week loss
        entries = make_entries(weights)
        result = analyze_weight_trends(entries)

        # Should have rapid change alert
        rapid_alerts = [a for a in result.alerts if "Rapid" in a]
        assert len(rapid_alerts) > 0

    def test_sparse_data_quality(self):
        """Should flag sparse data."""
        # Only 3 entries over 3 weeks
        entries = [
            BodyWeightEntry(
                date=date.today() - timedelta(weeks=3),
                weight=Decimal("165"),
                weight_unit=WeightUnit.LB,
            ),
            BodyWeightEntry(
                date=date.today() - timedelta(weeks=1),
                weight=Decimal("165"),
                weight_unit=WeightUnit.LB,
            ),
            BodyWeightEntry(
                date=date.today(),
                weight=Decimal("165"),
                weight_unit=WeightUnit.LB,
            ),
        ]
        result = analyze_weight_trends(entries)
        assert result.data_quality == "sparse"


class TestGetWeightHistorySummary:
    """Tests for get_weight_history_summary function."""

    def test_weekly_summary(self):
        """Should return weekly summaries."""
        weights = [165.0] * 14
        entries = make_entries(weights)
        summary = get_weight_history_summary(entries, weeks=4)

        assert len(summary) >= 2  # At least 2 weeks of data

    def test_empty_entries(self):
        """Should handle empty entries."""
        summary = get_weight_history_summary([], weeks=4)
        assert summary == []
