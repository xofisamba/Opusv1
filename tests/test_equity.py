"""Tests for multi-sponsor equity distribution waterfall (Task 3.3)."""
import pytest
from core.domain.equity import (
    Sponsor,
    SponsorResult,
    distribute_pro_rata,
    distribute_preferred_return,
    distribute_waterfall_tiers,
    compute_sponsor_results,
)


class TestProRata:
    def test_simple_60_40_split(self):
        sponsors = [
            Sponsor("s1", "Investor 1", equity_pct=0.60, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=6000, shl_invested_keur=0),
            Sponsor("s2", "Investor 2", equity_pct=0.40, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=4000, shl_invested_keur=0),
        ]
        distributions = [0.0, 0.0, 1000.0, 2000.0]

        result = distribute_pro_rata(distributions, sponsors)

        assert abs(result["s1"][2] - 600.0) < 0.01, "Investor 1 yr3 gets 60% of 1000"
        assert abs(result["s1"][3] - 1200.0) < 0.01, "Investor 1 yr4 gets 60% of 2000"
        assert abs(result["s2"][2] - 400.0) < 0.01, "Investor 2 yr3 gets 40% of 1000"
        assert abs(result["s2"][3] - 800.0) < 0.01, "Investor 2 yr4 gets 40% of 2000"

    def test_zero_distribution(self):
        sponsors = [
            Sponsor("s1", "Investor 1", equity_pct=1.0, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=5000, shl_invested_keur=0),
        ]
        result = distribute_pro_rata([0.0, 0.0], sponsors)
        assert result["s1"] == [0.0, 0.0]

    def test_total_sum_equals_input(self):
        sponsors = [
            Sponsor("s1", "Investor 1", equity_pct=0.60, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=6000, shl_invested_keur=0),
            Sponsor("s2", "Investor 2", equity_pct=0.40, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=4000, shl_invested_keur=0),
        ]
        total_dist = [1000.0, 2000.0, 3000.0]
        result = distribute_pro_rata(total_dist, sponsors)

        for yr_idx in range(len(total_dist)):
            total = result["s1"][yr_idx] + result["s2"][yr_idx]
            assert abs(total - total_dist[yr_idx]) < 1.0, (
                f"Year {yr_idx}: sum {total} != {total_dist[yr_idx]}"
            )


class TestPreferredReturn:
    def test_accumulated_preferred_grows(self):
        sponsors = [
            Sponsor("s1", "Investor 1", equity_pct=1.0, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=10000, shl_invested_keur=0,
                   preferred_return_rate=0.08),
        ]
        # 2 years zero, then 15,000 kEUR in year 3
        distributions = [0.0, 0.0, 15000.0]
        result = distribute_preferred_return(distributions, sponsors)

        # Year 3: accumulated preferred = 10000*(1.08)^2 = 11,664
        # All 15,000 goes to s1 (single sponsor, preferred applies)
        assert abs(result["s1"][2] - 15000.0) < 0.01, f"Expected 15000, got {result['s1'][2]}"

    def test_multi_sponsor_preferred_split(self):
        sponsors = [
            Sponsor("s1", "Investor 1", equity_pct=0.60, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=6000, shl_invested_keur=0,
                   preferred_return_rate=0.08),
            Sponsor("s2", "Investor 2", equity_pct=0.40, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=4000, shl_invested_keur=0,
                   preferred_return_rate=0.08),
        ]
        # Year 1: dist=0
        # Year 2: dist=12,000, year_counter=1
        #   accrued s1 = 6000*1.08 - 0 = 6,480; s2 = 4000*1.08 = 4,320
        #   total_accrued = 10,800 → first 10,800 to preferred
        #   Remaining 1,200: pro-rata by equity_pct
        #   s1 receives: 6480 + 1200*0.60 = 7200; s2: 4320 + 1200*0.40 = 4800
        distributions = [0.0, 12000.0]
        result = distribute_preferred_return(distributions, sponsors)

        s1_share = result["s1"][1]
        s2_share = result["s2"][1]
        assert abs(s1_share + s2_share - 12000.0) < 1.0, (
            f"Total {s1_share+s2_share} != 12000"
        )
        # s1/s2 ratio should be approximately 60/40
        assert abs(s1_share / s2_share - 1.5) < 0.05, (
            f"s1/s2 ratio {s1_share/s2_share:.2f} != 1.5 (60/40)"
        )


class TestTieredWaterfall:
    def test_gp_catchup_threshold(self):
        sponsors = [
            Sponsor("gp", "GP", equity_pct=0.20, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=1000, shl_invested_keur=0,
                   preferred_return_rate=0.08, is_gp=True),
            Sponsor("lp", "LP", equity_pct=0.80, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=4000, shl_invested_keur=0,
                   preferred_return_rate=0.08, is_gp=False),
        ]
        distributions = [50000.0]
        result = distribute_waterfall_tiers(
            distributions, sponsors,
            hurdle_rate=0.08,
            catchup_threshold=0.20,
            gp_carry_pct=0.20,
            gp_sponsor_id="gp",
        )
        total = result["gp"][0] + result["lp"][0]
        assert abs(total - 50000.0) < 1.0, f"Total {total} != 50000"

    def test_zero_distribution(self):
        sponsors = [
            Sponsor("s1", "Investor 1", equity_pct=1.0, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=5000, shl_invested_keur=0, is_gp=True),
        ]
        result = distribute_waterfall_tiers(
            [0.0, 0.0], sponsors,
            hurdle_rate=0.08,
            catchup_threshold=0.20,
            gp_carry_pct=0.20,
            gp_sponsor_id="s1",
        )
        assert result["s1"] == [0.0, 0.0]


class TestComputeSponsorResults:
    def test_moic_and_payback(self):
        sponsors = [
            Sponsor("s1", "Investor 1", equity_pct=1.0, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=10000, shl_invested_keur=0),
        ]
        # 2000 kEUR per year for 5 years → MOIC = 1.0
        distributions = [2000.0] * 5
        result_dict = distribute_pro_rata(distributions, sponsors)
        results = compute_sponsor_results(result_dict, sponsors, discount_rate=0.08)

        assert len(results) == 1
        r = results[0]
        assert r.sponsor_id == "s1"
        assert abs(r.total_invested_keur - 10000.0) < 0.01
        assert abs(r.moic - 1.0) < 0.01
        assert r.payback_year == 5

    def test_multi_sponsor_different_invested_amounts(self):
        sponsors = [
            Sponsor("s1", "Investor 1", equity_pct=0.60, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=6000, shl_invested_keur=0),
            Sponsor("s2", "Investor 2", equity_pct=0.40, shl_pct=0.0, shl_rate=0.08,
                   equity_invested_keur=4000, shl_invested_keur=0),
        ]
        distributions = [1000.0] * 5
        result_dict = distribute_pro_rata(distributions, sponsors)
        results = compute_sponsor_results(result_dict, sponsors, discount_rate=0.08)

        r1 = next(r for r in results if r.sponsor_id == "s1")
        r2 = next(r for r in results if r.sponsor_id == "s2")
        assert abs(r1.total_invested_keur - 6000.0) < 0.01
        assert abs(r2.total_invested_keur - 4000.0) < 0.01
