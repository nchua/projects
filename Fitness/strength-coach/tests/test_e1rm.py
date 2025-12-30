"""Tests for e1RM estimation functions."""

import pytest
from decimal import Decimal

from strength_coach.analytics.e1rm import (
    E1RMFormula,
    estimate_e1rm,
    estimate_e1rm_multi,
    calculate_set_e1rm,
    is_reliable_estimate,
    get_percentage_of_1rm,
    estimate_reps_at_weight,
)
from strength_coach.models import SetRecord, WeightUnit


class TestEstimateE1RM:
    """Tests for estimate_e1rm function."""

    def test_epley_formula_basic(self):
        """e1RM = weight * (1 + reps/30)"""
        result = estimate_e1rm(Decimal("225"), 5, E1RMFormula.EPLEY)
        expected = Decimal("262.5")  # 225 * (1 + 5/30) = 225 * 1.1667 = 262.5
        assert result == expected

    def test_brzycki_formula_basic(self):
        """e1RM = weight * 36 / (37 - reps)"""
        result = estimate_e1rm(Decimal("225"), 5, E1RMFormula.BRZYCKI)
        # 225 * 36 / (37 - 5) = 225 * 36 / 32 = 253.125
        assert abs(result - Decimal("253.1")) < Decimal("0.1")

    def test_single_rep_returns_weight(self):
        """1 rep should return the weight itself."""
        result = estimate_e1rm(Decimal("315"), 1, E1RMFormula.EPLEY)
        assert result == Decimal("315")

    def test_high_reps_returns_zero(self):
        """Reps > 12 should return 0 (unreliable)."""
        result = estimate_e1rm(Decimal("135"), 15, E1RMFormula.EPLEY)
        assert result == Decimal("0")

    def test_zero_reps_returns_zero(self):
        """0 reps should return 0."""
        result = estimate_e1rm(Decimal("225"), 0, E1RMFormula.EPLEY)
        assert result == Decimal("0")

    def test_negative_reps_returns_zero(self):
        """Negative reps should return 0."""
        result = estimate_e1rm(Decimal("225"), -5, E1RMFormula.EPLEY)
        assert result == Decimal("0")

    def test_different_formulas_give_different_results(self):
        """Different formulas should give slightly different results."""
        epley = estimate_e1rm(Decimal("200"), 8, E1RMFormula.EPLEY)
        brzycki = estimate_e1rm(Decimal("200"), 8, E1RMFormula.BRZYCKI)
        # Results should be different but within 10% of each other
        assert epley != brzycki
        diff = abs(epley - brzycki)
        assert diff < epley * Decimal("0.1")

    def test_boundary_at_12_reps(self):
        """12 reps should still return valid estimate."""
        result = estimate_e1rm(Decimal("135"), 12, E1RMFormula.EPLEY)
        assert result > Decimal("0")

    def test_boundary_at_13_reps(self):
        """13 reps should return 0."""
        result = estimate_e1rm(Decimal("135"), 13, E1RMFormula.EPLEY)
        assert result == Decimal("0")


class TestEstimateE1RMMulti:
    """Tests for estimate_e1rm_multi function."""

    def test_default_formulas(self):
        """Default should use Epley and Brzycki."""
        results = estimate_e1rm_multi(Decimal("225"), 5)
        assert E1RMFormula.EPLEY in results
        assert E1RMFormula.BRZYCKI in results
        assert len(results) == 2

    def test_custom_formulas(self):
        """Should use specified formulas."""
        formulas = [E1RMFormula.EPLEY, E1RMFormula.LOMBARDI, E1RMFormula.WATHAN]
        results = estimate_e1rm_multi(Decimal("225"), 5, formulas)
        assert len(results) == 3
        assert E1RMFormula.EPLEY in results
        assert E1RMFormula.LOMBARDI in results
        assert E1RMFormula.WATHAN in results


class TestCalculateSetE1RM:
    """Tests for calculate_set_e1rm function."""

    def test_basic_set(self):
        """Should calculate e1RM for a set."""
        set_record = SetRecord(
            reps=5,
            weight=Decimal("225"),
            weight_unit=WeightUnit.LB,
        )
        results = calculate_set_e1rm(set_record)
        assert "default" in results
        assert "epley" in results
        assert "brzycki" in results
        assert results["default"] == results["epley"]

    def test_kg_set_converts_to_lb(self):
        """Should handle kg weights correctly."""
        set_record = SetRecord(
            reps=5,
            weight=Decimal("100"),  # 100 kg
            weight_unit=WeightUnit.KG,
        )
        results = calculate_set_e1rm(set_record)
        # 100 kg ~= 220 lb, so e1RM should be > 220
        assert results["default"] > Decimal("220")


class TestIsReliableEstimate:
    """Tests for is_reliable_estimate function."""

    def test_reliable_range(self):
        """Reps 1-12 should be reliable."""
        for reps in range(1, 13):
            assert is_reliable_estimate(reps) is True

    def test_unreliable_high_reps(self):
        """Reps > 12 should be unreliable."""
        assert is_reliable_estimate(13) is False
        assert is_reliable_estimate(20) is False

    def test_unreliable_zero_reps(self):
        """0 reps should be unreliable."""
        assert is_reliable_estimate(0) is False


class TestGetPercentageOf1RM:
    """Tests for get_percentage_of_1rm function."""

    def test_single_rep_is_100(self):
        """1 rep should be 100%."""
        assert get_percentage_of_1rm(1) == 100.0

    def test_known_percentages(self):
        """Check some known values."""
        assert get_percentage_of_1rm(5) == 87.0
        assert get_percentage_of_1rm(10) == 75.0

    def test_high_reps_default(self):
        """High reps should return default."""
        assert get_percentage_of_1rm(20) == 65.0


class TestEstimateRepsAtWeight:
    """Tests for estimate_reps_at_weight function."""

    def test_at_1rm_returns_1(self):
        """At 1RM weight, should return 1 rep."""
        result = estimate_reps_at_weight(Decimal("315"), Decimal("315"))
        assert result == 1

    def test_at_lower_weight(self):
        """At lower weight, should return more reps."""
        result = estimate_reps_at_weight(Decimal("315"), Decimal("225"))
        assert result > 5  # Should be able to do several reps at ~70%

    def test_above_1rm_returns_1(self):
        """Above 1RM should still return 1."""
        result = estimate_reps_at_weight(Decimal("300"), Decimal("315"))
        assert result == 1

    def test_zero_weight_returns_0(self):
        """Zero target weight should return 0."""
        result = estimate_reps_at_weight(Decimal("315"), Decimal("0"))
        assert result == 0
