"""Equity structure — Blueprint §2.3.

Multi-sponsor equity model.
All classes are frozen/immutable.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

DistributionPolicy = Literal["pro_rata", "waterfall", "preferred_return"]


@dataclass(frozen=True)
class Sponsor:
    """Single equity sponsor."""
    sponsor_id: str
    name: str
    equity_pct: float  # 0.0 to 1.0
    shl_pct: float  # Shareholder loan participation %
    shl_rate: float  # SHL interest rate

    def __post_init__(self):
        if not 0 <= self.equity_pct <= 1:
            raise ValueError(f"Sponsor {self.sponsor_id}: equity_pct must be 0-1, got {self.equity_pct}")
        if not 0 <= self.shl_pct <= 1:
            raise ValueError(f"Sponsor {self.sponsor_id}: shl_pct must be 0-1, got {self.shl_pct}")


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
        # Validate equity percentages sum to ~1.0
        total_equity = sum(s.equity_pct for s in self.sponsors)
        if abs(total_equity - 1.0) > 0.001:
            raise ValueError(
                f"Sponsor equity_pct must sum to 1.0, got {total_equity:.4f}"
            )
        # Validate SHL percentages sum to ~1.0
        total_shl = sum(s.shl_pct for s in self.sponsors)
        if abs(total_shl - 1.0) > 0.001:
            raise ValueError(
                f"Sponsor shl_pct must sum to 1.0, got {total_shl:.4f}"
            )

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
                sponsor_id="SP-001",
                name="Sponsor",
                equity_pct=1.0,
                shl_pct=1.0,
                shl_rate=shl_rate,
            ),
        ),
        total_share_capital_keur=share_capital_keur,
        total_share_premium_keur=share_premium_keur,
        total_shl_keur=shl_amount_keur,
        distribution_policy="pro_rata",
        preferred_return_rate=shl_rate,
        catchup_threshold=1.15,
    )
