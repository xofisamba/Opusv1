"""Equity structure — Blueprint §2.3.

Multi-sponsor equity model with distribution waterfall.
All classes are frozen/immutable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import date
from collections import defaultdict

from domain.returns.xirr import xirr
from domain.returns.xnpv import xnpv

DistributionPolicy = Literal["pro_rata", "waterfall", "preferred_return"]


@dataclass(frozen=True)
class Sponsor:
    """Single equity sponsor."""
    sponsor_id: str
    name: str
    equity_pct: float          # 0.0 to 1.0
    shl_pct: float            # Shareholder loan participation %
    shl_rate: float           # SHL interest rate
    equity_invested_keur: float = 0.0
    shl_invested_keur: float = 0.0
    preferred_return_rate: float = 0.08
    is_gp: bool = False

    def __post_init__(self):
        if not 0 <= self.equity_pct <= 1:
            raise ValueError(f"Sponsor {self.sponsor_id}: equity_pct must be 0-1")


@dataclass(frozen=True)
class EquityStructure:
    """Multi-sponsor equity structure.

    Corresponds to Blueprint §2.3 schema.
    """
    sponsors: tuple[Sponsor, ...]
    total_share_capital_keur: float
    total_share_premium_keur: float
    total_shl_keur: float
    distribution_policy: DistributionPolicy
    preferred_return_rate: float  # e.g., 0.08 = 8%
    catchup_threshold: float  # DSCR threshold for catch-up

    def __post_init__(self):
        total_equity = sum(s.equity_pct for s in self.sponsors)
        if abs(total_equity - 1.0) > 0.001:
            raise ValueError(f"equity_pct must sum to 1.0, got {total_equity:.4f}")

    @property
    def total_equity_keur(self) -> float:
        return self.total_share_capital_keur + self.total_share_premium_keur

    def sponsor_by_id(self, sponsor_id: str) -> Optional[Sponsor]:
        for s in self.sponsors:
            if s.sponsor_id == sponsor_id:
                return s
        return None

    def equity_for_sponsor(self, sponsor_id: str, total_equity_keur: float) -> float:
        sponsor = self.sponsor_by_id(sponsor_id)
        if sponsor is None:
            return 0.0
        return total_equity_keur * sponsor.equity_pct


def create_single_sponsor_equity(
    share_capital_keur: float,
    share_premium_keur: float = 0.0,
    shl_amount_keur: float = 0.0,
    shl_rate: float = 0.08,
) -> EquityStructure:
    """Create a single-sponsor equity structure (default case)."""
    return EquityStructure(
        sponsors=(
            Sponsor(
                sponsor_id="SP-001", name="Sponsor",
                equity_pct=1.0, shl_pct=1.0, shl_rate=shl_rate,
                equity_invested_keur=share_capital_keur + share_premium_keur,
                shl_invested_keur=shl_amount_keur,
            ),
        ),
        total_share_capital_keur=share_capital_keur,
        total_share_premium_keur=share_premium_keur,
        total_shl_keur=shl_amount_keur,
        distribution_policy="pro_rata",
        preferred_return_rate=shl_rate,
        catchup_threshold=1.15,
    )


# ---------------------------------------------------------------------------
# Distribution waterfall functions
# ---------------------------------------------------------------------------

def distribute_pro_rata(
    distributions: list[float],
    sponsors: list[Sponsor],
) -> dict[str, list[float]]:
    """Pro-rata distribution: each sponsor gets total × equity_pct.

    Args:
        distributions: Annual FCF available for distribution (kEUR per year)
        sponsors: List of Sponsor dataclass instances

    Returns:
        dict mapping sponsor_id → list of annual distributions (kEUR)
    """
    result: dict[str, list[float]] = {s.sponsor_id: [] for s in sponsors}
    for yr_idx, total_dist in enumerate(distributions):
        for sponsor in sponsors:
            amount = total_dist * sponsor.equity_pct
            result[sponsor.sponsor_id].append(amount)
    return result


def distribute_preferred_return(
    distributions: list[float],
    sponsors: list[Sponsor],
) -> dict[str, list[float]]:
    """Distribute with accumulated preferred return.

    Per period:
    1. Compute accumulated preferred = equity × (1+rate)^years - received
    2. All distribution goes first to accrued preferred (pro-rata by equity stake)
    3. After all preferred satisfied, remainder pro-rata by equity_pct
    """
    if not distributions or not sponsors:
        return {s.sponsor_id: [0.0] * len(distributions) for s in sponsors}

    n_years = len(distributions)
    result: dict[str, list[float]] = {s.sponsor_id: [0.0] * n_years for s in sponsors}
    cumulative_received: dict[str, float] = {s.sponsor_id: 0.0 for s in sponsors}
    year_counter: dict[str, float] = {s.sponsor_id: 0.0 for s in sponsors}

    for yr_idx in range(n_years):
        dist = distributions[yr_idx]
        if dist <= 0:
            continue

        # Compute accumulated preferred for each sponsor
        accrued: dict[str, float] = {}
        for sponsor in sponsors:
            total_invested = sponsor.equity_invested_keur + sponsor.shl_invested_keur
            if total_invested > 0:
                accrued[sponsor.sponsor_id] = (
                    total_invested * (1 + sponsor.preferred_return_rate) ** year_counter[sponsor.sponsor_id]
                    - cumulative_received[sponsor.sponsor_id]
                )
            else:
                accrued[sponsor.sponsor_id] = 0.0

        total_accrued = sum(accrued.values())

        if total_accrued > 0:
            # Distribution goes to accrued preferred (pro-rata by equity stake)
            for sponsor in sponsors:
                share = accrued[sponsor.sponsor_id] / total_accrued * dist
                received = min(share, accrued[sponsor.sponsor_id])
                result[sponsor.sponsor_id][yr_idx] = received
                cumulative_received[sponsor.sponsor_id] += received
        else:
            # After preferred satisfied: pro-rata by equity_pct
            for sponsor in sponsors:
                amount = dist * sponsor.equity_pct
                result[sponsor.sponsor_id][yr_idx] = amount
                cumulative_received[sponsor.sponsor_id] += amount

        for sponsor in sponsors:
            year_counter[sponsor.sponsor_id] += 1

    return result


def distribute_waterfall_tiers(
    distributions: list[float],
    sponsors: list[Sponsor],
    hurdle_rate: float,
    catchup_threshold: float,
    gp_carry_pct: float,
    gp_sponsor_id: str,
) -> dict[str, list[float]]:
    """Classic PE waterfall with 4 tiers.

    Tier 1 — Return of capital: pro-rata by equity stake
    Tier 2 — Preferred return: hurdle_rate on remaining capital
    Tier 3 — GP catch-up: GP receives 100% until GP carry = catchup_threshold
    Tier 4 — Residual: gp_carry_pct to GP, rest to LP pro-rata
    """
    if not distributions or not sponsors:
        return {s.sponsor_id: [0.0] * len(distributions) for s in sponsors}

    n_years = len(distributions)
    result: dict[str, list[float]] = {s.sponsor_id: [0.0] * n_years for s in sponsors}

    # Capital returned tracker per sponsor
    capital_remaining: dict[str, float] = {
        s.sponsor_id: s.equity_invested_keur + s.shl_invested_keur for s in sponsors
    }
    preferred_accrued: dict[str, float] = {s.sponsor_id: 0.0 for s in sponsors}
    gp_caught_up = False

    for yr_idx, dist in enumerate(distributions):
        if dist <= 0:
            continue

        remaining = dist
        total_equity = sum(s.equity_invested_keur + s.shl_invested_keur for s in sponsors)

        # ---- Tier 1: Return of capital (pro-rata by equity stake) ----
        if total_equity > 0:
            for sponsor in sponsors:
                share = (sponsor.equity_invested_keur + sponsor.shl_invested_keur) / total_equity
                tier1 = min(remaining, dist * share)
                returned = min(tier1, capital_remaining[sponsor.sponsor_id])
                result[sponsor.sponsor_id][yr_idx] += returned
                capital_remaining[sponsor.sponsor_id] -= returned
                remaining -= returned

        if remaining <= 0:
            continue

        # ---- Tier 2: Preferred return (pro-rata by equity stake) ----
        for sponsor in sponsors:
            preferred = (
                (sponsor.equity_invested_keur + sponsor.shl_invested_keur)
                * hurdle_rate
            )
            accrued = preferred - preferred_accrued[sponsor.sponsor_id]
            if accrued > 0:
                share = (sponsor.equity_invested_keur + sponsor.shl_invested_keur) / total_equity
                allocated = min(remaining, dist * share)
                received = min(allocated, accrued)
                result[sponsor.sponsor_id][yr_idx] += received
                preferred_accrued[sponsor.sponsor_id] += received
                remaining -= received

        if remaining <= 0:
            continue

        # ---- Tier 3: GP catch-up (GP gets 100% until catchup_threshold) ----
        gp = next((s for s in sponsors if s.sponsor_id == gp_sponsor_id), None)
        if gp and not gp_caught_up:
            target_carry = total_equity * catchup_threshold
            current_carry = sum(
                result[s.sponsor_id][yr_idx] - (s.equity_invested_keur + s.shl_invested_keur)
                for s in sponsors
                if result[s.sponsor_id][yr_idx] > (s.equity_invested_keur + s.shl_invested_keur)
            )
            catch_up_needed = max(0, target_carry - current_carry)
            gp_share = min(remaining, catch_up_needed)
            result[gp_sponsor_id][yr_idx] += gp_share
            remaining -= gp_share
            if catch_up_needed <= 0:
                gp_caught_up = True

        if remaining <= 0:
            continue

        # ---- Tier 4: Residual split ----
        if gp and gp_caught_up:
            gp_amount = remaining * gp_carry_pct
            result[gp_sponsor_id][yr_idx] += gp_amount
            remaining -= gp_amount

        # Remaining to LP sponsors (non-GP) pro-rata
        lp_sponsors = [s for s in sponsors if not s.is_gp]
        if lp_sponsors and remaining > 0:
            lp_total = sum(s.equity_invested_keur + s.shl_invested_keur for s in lp_sponsors)
            if lp_total > 0:
                for sponsor in lp_sponsors:
                    share = (sponsor.equity_invested_keur + sponsor.shl_invested_keur) / lp_total
                    result[sponsor.sponsor_id][yr_idx] += remaining * share
            else:
                # Fallback: pro-rata among all sponsors
                for sponsor in sponsors:
                    share = (sponsor.equity_invested_keur + sponsor.shl_invested_keur) / total_equity
                    result[sponsor.sponsor_id][yr_idx] += remaining * share

    return result


# ---------------------------------------------------------------------------
# Per-sponsor results
# ---------------------------------------------------------------------------

@dataclass
class SponsorResult:
    sponsor_id: str
    name: str
    equity_invested_keur: float
    shl_invested_keur: float
    total_invested_keur: float
    total_distributions_keur: float
    equity_irr: float
    moic: float
    payback_year: Optional[int]


def compute_sponsor_results(
    distributions_dict: dict[str, list[float]],
    sponsors: list[Sponsor],
    discount_rate: float = 0.08,
) -> list[SponsorResult]:
    """Compute IRR, MOIC, and payback year per sponsor.

    IRR uses xirr from domain.returns.xirr.
    MOIC = total_distributions / total_invested.
    Payback = first year where cumulative distributions >= invested.
    """
    results = []
    for sponsor in sponsors:
        dist_list = distributions_dict.get(sponsor.sponsor_id, [])
        if not dist_list:
            continue

        total_invested = sponsor.equity_invested_keur + sponsor.shl_invested_keur
        total_dist = sum(dist_list)

        # MOIC
        moic = total_dist / total_invested if total_invested > 0 else 0.0

        # Payback year
        payback = None
        cum_dist = 0.0
        for yr_idx, d in enumerate(dist_list):
            cum_dist += d
            if cum_dist >= total_invested:
                payback = yr_idx + 1
                break

        # IRR via xirr
        equity_irr = 0.0
        if total_invested > 0 and total_dist > 0:
            try:
                # Build cash flow: negative invested at t=0, then distributions
                cashflows = [-total_invested] + dist_list
                equity_irr = xirr(cashflows, discount_rate)
            except Exception:
                equity_irr = 0.0

        results.append(SponsorResult(
            sponsor_id=sponsor.sponsor_id,
            name=sponsor.name,
            equity_invested_keur=sponsor.equity_invested_keur,
            shl_invested_keur=sponsor.shl_invested_keur,
            total_invested_keur=total_invested,
            total_distributions_keur=total_dist,
            equity_irr=equity_irr,
            moic=moic,
            payback_year=payback,
        ))

    return results
