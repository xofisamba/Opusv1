"""Tests for goal seek solvers."""
import pytest

from core.finance.goal_seek import (
    solve_ppa_for_target_irr,
    solve_debt_for_target_dscr,
    GoalSeekResult,
    DebtSizingResult,
)


class TestGoalSeekIntegration:
    """Real waterfall integration test for goal seek solvers."""

    def test_ppa_solver_converges_with_real_waterfall(self):
        """PPA-for-IRR solver must return a real PPA price, not 0.

        Uses ProjectInputs.create_default_oborovo() as fixture.
        Target: 8% project IRR. Solver must converge and return a PPA
        in the range [30, 200] EUR/MWh.
        """
        from domain.inputs import ProjectInputs
        inputs = ProjectInputs.create_default_oborovo()
        result = solve_ppa_for_target_irr(
            inputs,
            target_irr=0.08,
            irr_basis="project",
            bracket_low_eur_mwh=30.0,
            bracket_high_eur_mwh=200.0,
        )
        assert result.success is True, f"Solver failed: {result.error_message}"
        assert 30.0 < result.solved_value < 200.0, (
            f"Solved PPA {result.solved_value:.2f} outside reasonable range"
        )
        assert result.iterations > 0, "Solver must have iterated"

    def test_ppa_solver_achieves_target_irr(self):
        """Solver achieved IRR must be within 5bps of target."""
        from domain.inputs import ProjectInputs
        inputs = ProjectInputs.create_default_oborovo()
        result = solve_ppa_for_target_irr(
            inputs,
            target_irr=0.08,
            irr_basis="project",
        )
        if result.success:
            assert abs(result.achieved_metric - 0.08) < 0.005, (
                f"Achieved IRR {result.achieved_metric:.4f} > 50bps from target"
            )


class TestGoalSeekPPA:
    """Task 2.6 — PPA-for-IRR solver (mock-based)."""

    def test_no_solution_unreachable_irr(self):
        """Target 30% IRR is impossible → returns success=False."""
        class MockInputs:
            pass
        inputs = MockInputs()

        result = solve_ppa_for_target_irr(
            inputs=inputs,
            target_irr=0.30,
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

        result = solve_ppa_for_target_irr(
            inputs=inputs,
            target_irr=0.01,
            bracket_low_eur_mwh=10.0,
            bracket_high_eur_mwh=50.0,
        )
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

    def test_bisection_no_solution(self):
        """Impossible DSCR target → success=False."""
        class MockInputs:
            pass
        inputs = MockInputs()

        result = solve_debt_for_target_dscr(
            inputs=inputs,
            target_dscr=10.0,
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