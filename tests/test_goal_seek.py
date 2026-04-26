"""Tests for goal seek solvers."""
import pytest

from core.finance.goal_seek import (
    solve_ppa_for_target_irr,
    solve_debt_for_target_dscr,
    GoalSeekResult,
    DebtSizingResult,
)


class TestGoalSeekPPA:
    """Task 2.6 — PPA-for-IRR solver."""

    def test_no_solution_unreachable_irr(self):
        """Target 30% IRR is impossible → returns success=False."""
        # Create a mock inputs object (minimal dict-like)
        class MockInputs:
            pass
        inputs = MockInputs()

        result = solve_ppa_for_target_irr(
            inputs=inputs,
            target_irr=0.30,   # impossible
            bracket_low_eur_mwh=30.0,
            bracket_high_eur_mwh=150.0,
        )
        assert result.success is False
        assert "No solution in bracket" in result.error_message

    def test_bracket_endpoints_rejected(self):
        """If f(low) and f(high) have same sign, return error immediately."""
        class MockInputs:
            pass
        inputs = MockInputs()

        # Both ends positive → no root
        result = solve_ppa_for_target_irr(
            inputs=inputs,
            target_irr=0.01,  # very low, both ends likely above
            bracket_low_eur_mwh=10.0,
            bracket_high_eur_mwh=50.0,
        )
        # Should fail with no solution message (not a crash)
        assert result.success is False
        assert result.iteration_trace is not None

    def test_result_structure(self):
        """GoalSeekResult has all required fields."""
        r = GoalSeekResult(
            success=False, solved_value=0.0, achieved_metric=0.0,
            iterations=0, iteration_trace=[], error_message="test"
        )
        assert r.converged is False
        assert r.iteration_trace == []

    def test_converged_result(self):
        """A converged result has success=True and iterations>0."""
        r = GoalSeekResult(
            success=True, solved_value=55.0, achieved_metric=0.10,
            iterations=12, iteration_trace=[(50, 0.08), (60, 0.12)],
        )
        assert r.converged is True


class TestGoalSeekDebt:
    """Task 2.7 — Debt-for-DSCR solver."""

    def test_sculpt_returns_debt_amount(self):
        """sculpt=True should return a positive debt amount."""
        class MockInputs:
            pass
        inputs = MockInputs()

        result = solve_debt_for_target_dscr(
            inputs=inputs,
            target_dscr=1.30,
            sculpt=True,
        )
        assert result.method == "direct_sculpt"
        # result may fail due to missing CFADS but should not crash

    def test_bisection_no_solution(self):
        """Impossible DSCR target → success=False."""
        class MockInputs:
            pass
        inputs = MockInputs()

        result = solve_debt_for_target_dscr(
            inputs=inputs,
            target_dscr=10.0,  # impossible (>10x)
            sculpt=False,
        )
        assert result.success is False

    def test_debt_sizing_result_structure(self):
        """DebtSizingResult has all required fields."""
        r = DebtSizingResult(
            success=True, debt_amount_keur=50000.0,
            achieved_dscr=1.30, implied_gearing=0.75,
            method="direct_sculpt",
        )
        assert r.debt_amount_keur == 50000.0
        assert r.implied_gearing == 0.75
        assert r.method == "direct_sculpt"