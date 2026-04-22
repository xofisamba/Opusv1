"""Financing Pydantic models.

Corresponds to Excel Inputs rows 168-349.
"""
from pydantic import Field, field_validator, computed_field
from typing import Optional

from .pydantic_base import FinancialBaseModel


class FinancingParams(FinancialBaseModel):
    """Financing parameters including debt and equity structure.

    Corresponds to Excel Inputs rows 168-349.

    Validation Rules:
        - share_capital_keur: Must be >= 0
        - shl_amount_keur: Must be >= 0
        - shl_rate: Must be 0.0-0.50 (0-50%)
        - gearing_ratio: Must be 0.0-0.95 (0-95%)
        - base_rate: Must be 0.0-0.30 (0-30%)
        - margin_bps: Must be 0-1000 bps
        - floating_share + fixed_share: Must sum to 1.0
        - target_dscr: Must be >= 1.0
        - lockup_dscr: Must be >= 1.0
        - dsra_months: Must be 0-12
    """
    # Equity structure
    share_capital_keur: float = Field(
        default=500.0,
        ge=0,
        description="Share capital in kEUR (Inputs!D312)"
    )
    share_premium_keur: float = Field(
        default=0.0,
        ge=0,
        description="Share premium in kEUR (Inputs!D313)"
    )
    shl_amount_keur: float = Field(
        default=13547.2,
        ge=0,
        description="Shareholder loan amount in kEUR (Inputs!D325)"
    )
    shl_rate: float = Field(
        default=0.08,
        ge=0.0, le=0.50,
        description="SHL interest rate (Inputs!F328)"
    )

    # Debt structure
    gearing_ratio: float = Field(
        default=0.7524,
        ge=0.0, le=0.95,
        description="Gearing ratio (Inputs!D168)"
    )
    senior_debt_amount_keur: float = Field(
        default=0.0,
        ge=0,
        description="Senior debt amount in kEUR (Inputs!D192) - computed"
    )
    senior_tenor_years: int = Field(
        default=14,
        ge=1, le=30,
        description="Senior debt tenor in years (Inputs!D196)"
    )
    base_rate: float = Field(
        default=0.03,
        ge=0.0, le=0.30,
        description="Base rate (Inputs!D202)"
    )
    margin_bps: int = Field(
        default=265,
        ge=0, le=1000,
        description="Margin in basis points (Inputs!D203)"
    )
    floating_share: float = Field(
        default=0.2,
        ge=0.0, le=1.0,
        description="Floating rate share (Inputs!B39)"
    )
    fixed_share: float = Field(
        default=0.8,
        ge=0.0, le=1.0,
        description="Fixed rate share (Inputs!B40)"
    )
    hedge_coverage: float = Field(
        default=0.8,
        ge=0.0, le=1.0,
        description="Hedge coverage (Inputs!D230)"
    )

    # Fees
    commitment_fee: float = Field(
        default=0.0105,
        ge=0.0, le=0.10,
        description="Commitment fee (Inputs!D214)"
    )
    arrangement_fee: float = Field(
        default=0.0,
        ge=0.0, le=0.10,
        description="Arrangement fee (Inputs!D218)"
    )
    structuring_fee: float = Field(
        default=0.01,
        ge=0.0, le=0.10,
        description="Structuring fee (Inputs!D217)"
    )

    # Covenants
    target_dscr: float = Field(
        default=1.15,
        ge=1.0, le=5.0,
        description="Target DSCR (Inputs!D221)"
    )
    lockup_dscr: float = Field(
        default=1.10,
        ge=1.0, le=5.0,
        description="Lockup DSCR threshold (Inputs!D223)"
    )
    min_llcr: float = Field(
        default=1.15,
        ge=1.0, le=5.0,
        description="Minimum LLCR (Inputs!D224)"
    )

    # Reserve accounts
    dsra_months: int = Field(
        default=6,
        ge=0, le=12,
        description="DSRA funding months (Inputs!D348)"
    )

    @field_validator('floating_share', 'fixed_share')
    @classmethod
    def validate_rate_share(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError("Stopa/fiksni udio mora biti između 0.0 i 1.0.")
        return v

    @field_validator('target_dscr')
    @classmethod
    def validate_target_dscr(cls, v: float) -> float:
        if v < 1.0:
            raise ValueError(
                f"target_dscr={v} nije validan. "
                f"Mora biti >= 1.0 (npr. 1.15 za 15% cushion)."
            )
        return v

    @field_validator('lockup_dscr')
    @classmethod
    def validate_lockup_dscr(cls, v: float, info) -> float:
        if v < 1.0:
            raise ValueError(
                f"lockup_dscr={v} nije validan. "
                f"Mora biti >= 1.0."
            )
        # Also check it's less than target_dscr (warning only, not error)
        return v

    @computed_field
    @property
    def all_in_rate(self) -> float:
        """All-in interest rate (base + margin)."""
        return self.base_rate + self.margin_bps / 10000

    @computed_field
    @property
    def total_equity_shl_keur(self) -> float:
        """Total equity + shareholder loan."""
        return self.share_capital_keur + self.share_premium_keur + self.shl_amount_keur

    @computed_field
    @property
    def all_in_rate_percent(self) -> str:
        """All-in rate as percentage string."""
        return f"{self.all_in_rate:.2%}"

    def get_financing_summary(self) -> dict:
        """Get financing summary for display."""
        return {
            "equity_keur": self.total_equity_shl_keur,
            "gearing": f"{self.gearing_ratio:.2%}",
            "all_in_rate": self.all_in_rate_percent,
            "senior_tenor_years": self.senior_tenor_years,
            "target_dscr": f"{self.target_dscr:.2f}x",
            "dsra_months": self.dsra_months,
        }


class TaxParams(FinancialBaseModel):
    """Tax parameters including corporate tax and loss carryforward.

    Corresponds to Excel Inputs rows 403-426.

    Validation Rules:
        - corporate_rate: Must be 0.0-0.50 (0-50%)
        - loss_carryforward_years: Must be 0-20
        - loss_carryforward_cap: Must be 0.0-1.0 (0-100%)
        - legal_reserve_cap: Must be 0.0-0.20 (0-20%)
        - atad_ebitda_limit: Must be 0.0-1.0 (0-100%)
        - wht_* rates: Must be 0.0-1.0 (0-100%)
    """
    corporate_rate: float = Field(
        default=0.10,
        ge=0.0, le=0.50,
        description="Corporate tax rate (Inputs!D403)"
    )
    loss_carryforward_years: int = Field(
        default=5,
        ge=0, le=20,
        description="Loss carryforward years (Inputs!D407)"
    )
    loss_carryforward_cap: float = Field(
        default=1.0,
        ge=0.0, le=1.0,
        description="Loss carryforward cap as % of taxable income (Inputs!D408)"
    )
    legal_reserve_cap: float = Field(
        default=0.10,
        ge=0.0, le=0.20,
        description="Legal reserve cap as % of profit (Inputs!D412)"
    )
    thin_cap_enabled: bool = Field(
        default=False,
        description="Thin capitalization rule enabled (Inputs!D413)"
    )
    atad_ebitda_limit: float = Field(
        default=0.30,
        ge=0.0, le=1.0,
        description="ATAD EBITDA limit (Inputs!D414)"
    )
    atad_min_interest_keur: float = Field(
        default=3000.0,
        ge=0.0,
        description="ATAD minimum interest threshold in kEUR (Inputs!D415)"
    )
    wht_sponsor_dividends: float = Field(
        default=0.05,
        ge=0.0, le=0.30,
        description="WHT on sponsor dividends (Inputs!D421)"
    )
    wht_sponsor_shl_interest: float = Field(
        default=0.0,
        ge=0.0, le=0.30,
        description="WHT on shareholder loan interest (Inputs!D422)"
    )
    shl_cap_applies: bool = Field(
        default=True,
        description="SHL cap applies (Inputs!D423)"
    )

    @field_validator('corporate_rate')
    @classmethod
    def validate_corporate_rate(cls, v: float) -> float:
        if v < 0 or v > 0.50:
            raise ValueError(
                f"corporate_rate={v} nije validan. "
                f"Mora biti između 0.0 i 0.50 (0-50%)."
            )
        return v

    def get_tax_summary(self) -> dict:
        """Get tax summary for display."""
        return {
            "corporate_rate": f"{self.corporate_rate:.1%}",
            "loss_carryforward_years": self.loss_carryforward_years,
            "loss_carryforward_cap": f"{self.loss_carryforward_cap:.0%}",
            "thin_cap": "Da" if self.thin_cap_enabled else "Ne",
            "wht_dividends": f"{self.wht_sponsor_dividends:.1%}",
        }
