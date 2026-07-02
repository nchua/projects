"""
Unit tests for app/core/e1rm.py.

Every set the iOS app logs runs through these functions (api/workouts.py
computes e1rm on both POST and PUT), so each formula is pinned to a
hand-computed value rather than re-derived from the code.

NOTE: Brzycki at adjusted reps >= 37 is deliberately NOT tested — the
formula divides by (37 - reps), a known latent ZeroDivisionError (reps=37)
/ negative-result (reps>37) bug for high-rep sets (the schema allows
reps <= 100). Left un-asserted so a future fix isn't blocked by a test
pinning buggy behavior.
"""
import pytest

from app.core.e1rm import (
    calculate_e1rm,
    calculate_e1rm_from_rir,
    calculate_e1rm_from_rpe,
)
from app.models.user import E1RMFormula


class TestCalculateE1rm:
    @pytest.mark.parametrize(
        "formula,expected",
        [
            # Epley: 200 * (1 + 5/30)
            pytest.param(E1RMFormula.EPLEY, 233.3333333, id="epley"),
            # Brzycki: 200 * (36 / (37 - 5))
            pytest.param(E1RMFormula.BRZYCKI, 225.0, id="brzycki"),
            # Wathan: (100 * 200) / (48.8 + 53.8 * e^(-0.075 * 5))
            pytest.param(E1RMFormula.WATHAN, 233.1650106, id="wathan"),
            # Lombardi: 200 * 5^0.1
            pytest.param(E1RMFormula.LOMBARDI, 234.9237886, id="lombardi"),
        ],
    )
    def test_known_values_at_200x5(self, formula, expected):
        assert calculate_e1rm(200, 5, formula) == pytest.approx(expected)

    @pytest.mark.parametrize("formula", list(E1RMFormula))
    def test_single_rep_returns_weight(self, formula):
        """reps=1 short-circuits: the lift IS the 1RM for every formula."""
        assert calculate_e1rm(315, 1, formula) == 315

    def test_defaults_to_epley(self):
        assert calculate_e1rm(200, 5) == pytest.approx(233.3333333)


class TestRpeRirAdjustment:
    """RPE/RIR sets estimate reps left in the tank: 200x5 @ RPE 8 means 2
    reps in reserve, so the e1RM is computed as if the set were 7 reps."""

    def test_rpe_converts_to_rir_and_adjusts_reps(self):
        # RPE 8 -> RIR 2 -> adjusted reps 5 + 2 = 7 -> Epley 200 * (1 + 7/30)
        assert calculate_e1rm_from_rpe(200, 5, 8) == pytest.approx(246.6666667)

    def test_rpe_10_is_max_effort(self):
        # RPE 10 -> RIR 0: no adjustment, identical to the plain formula.
        assert calculate_e1rm_from_rpe(200, 5, 10) == pytest.approx(
            calculate_e1rm(200, 5)
        )

    def test_rir_adjusts_reps_directly(self):
        # RIR 2 -> adjusted reps 7 -> Epley 200 * (1 + 7/30)
        assert calculate_e1rm_from_rir(200, 5, 2) == pytest.approx(246.6666667)

    def test_rpe_and_rir_agree(self):
        # RPE r and RIR (10 - r) describe the same set and must agree.
        for rpe in range(6, 11):
            assert calculate_e1rm_from_rpe(200, 5, rpe) == pytest.approx(
                calculate_e1rm_from_rir(200, 5, 10 - rpe)
            )

    @pytest.mark.parametrize("formula", list(E1RMFormula))
    def test_adjustment_applies_to_every_formula(self, formula):
        # Both adjusters must delegate to calculate_e1rm with reps + RIR.
        assert calculate_e1rm_from_rpe(200, 5, 8, formula) == pytest.approx(
            calculate_e1rm(200, 7, formula)
        )
        assert calculate_e1rm_from_rir(200, 5, 2, formula) == pytest.approx(
            calculate_e1rm(200, 7, formula)
        )
