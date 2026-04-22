"""CAPEX Pydantic models.

Corresponds to Excel Inputs rows 23-44.
"""
from pydantic import Field, field_validator
from typing import Optional

from .pydantic_base import FinancialBaseModel


class CapexItem(FinancialBaseModel):
    """Single CAPEX line item with spending profile.

    Corresponds to Excel Inputs rows 23-44.
    Each item has an amount and spending profile across periods.

    Example:
        EPC Contract: 26,430 k€ → Y0:0%, Y1:8.3%, Y2:8.3% ... (12 month linear)
        Project Rights: 3,024.5 k€ → Y0:100%, rest: 0%

    Validation Rules:
        - amount_keur: Must be >= 0
        - y0_share: Must be 0.0-1.0
        - spending_profile shares must sum to approximately 1.0 (when non-empty)
    """
    name: str = Field(
        min_length=1,
        max_length=100,
        description="Item description"
    )
    amount_keur: float = Field(
        ge=0,
        description="Total amount in kEUR"
    )
    y0_share: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="Percentage paid in Y0 (construction year 0)"
    )
    spending_profile: tuple[float, ...] = Field(
        default_factory=tuple,
        description="Percentage shares for Y1, Y2, Y3, Y4..."
    )

    @field_validator('y0_share')
    @classmethod
    def validate_y0_share(cls, v: float) -> float:
        if v < 0 or v > 1:
            raise ValueError("y0_share mora biti između 0.0 i 1.0 (0%-100%).")
        return v

    @field_validator('spending_profile')
    @classmethod
    def validate_spending_profile(cls, v: tuple[float, ...]) -> tuple[float, ...]:
        for i, val in enumerate(v):
            if val < 0 or val > 1:
                raise ValueError(
                    f"spending_profile[{i}]={val} nije validan. "
                    f"Svaki share mora biti između 0.0 i 1.0."
                )
        return v

    @property
    def total_spending_shares(self) -> float:
        """Sum of all spending shares (y0 + profile). Should equal 1.0."""
        return self.y0_share + sum(self.spending_profile)

    def validate_shares_sum(self) -> None:
        """Validate spending shares sum to approximately 1.0.
        
        Raises:
            ValueError: If shares don't sum to 1.0
        """
        total = self.total_spending_shares
        if total > 0 and abs(total - 1.0) > 0.01:
            raise ValueError(
                f"{self.name}: spending shares zbroj iznosi {total:.4f}, "
                f"očekivano 1.0. Provjerite spending_profile ili y0_share."
            )

    def amount_in_period(self, period: int) -> float:
        """Return CAPEX amount for a given period.

        Args:
            period: 0=Y0, 1=Y1, 2=Y2, 3=Y3, 4=Y4+

        Returns:
            Amount in kEUR for that period
        """
        if period == 0:
            return self.amount_keur * self.y0_share
        idx = period - 1
        if idx < len(self.spending_profile):
            return self.amount_keur * self.spending_profile[idx]
        return 0.0

    def get_profile_summary(self) -> dict:
        """Get a summary dict for display."""
        return {
            "name": self.name,
            "amount_keur": self.amount_keur,
            "y0_share": f"{self.y0_share:.1%}",
            "profile_years": len(self.spending_profile),
            "profile_sum": f"{sum(self.spending_profile):.1%}",
        }


class CapexStructure(FinancialBaseModel):
    """Complete CAPEX structure with all items from Oborovo Excel.

    Corresponds to Excel Inputs rows 23-44 (22 CAPEX categories).

    Items marked as "dynamic" are computed iteratively:
    - IDC: Solved via fixed-point iteration (circular with debt)
    - Commitment Fees: Based on undrawn debt during construction
    - Reserve Accounts: DSRA, J-DSRA, MRA funded at financial close
    """
    # === Hard CAPEX items ===
    epc_contract: CapexItem = Field(description="Inputs!C23 - EPC Contract (26,430 k€)")
    production_units: CapexItem = Field(description="Inputs!C24 - Production Units (10,912.7 k€)")
    epc_other: CapexItem = Field(description="Inputs!C25 - Other EPC (3,200 k€)")
    grid_connection: CapexItem = Field(description="Inputs!C26 - Grid Connection (1,800 k€)")
    ops_prep: CapexItem = Field(description="Inputs!C27 - Operations Preparation (500 k€)")
    insurances: CapexItem = Field(description="Inputs!C28 - Insurances (400 k€)")
    lease_tax: CapexItem = Field(description="Inputs!C29 - Lease & Property Tax (200 k€)")
    construction_mgmt_a: CapexItem = Field(description="Inputs!C30 - Construction Management A (800 k€)")
    commissioning: CapexItem = Field(description="Inputs!C31 - Commissioning (300 k€)")
    audit_legal: CapexItem = Field(description="Inputs!C32 - Audit & Legal (200 k€)")
    construction_mgmt_b: CapexItem = Field(description="Inputs!C33 - Construction Management B (400 k€)")
    contingencies: CapexItem = Field(description="Inputs!C34 - Contingencies (1,986.4 k€)")
    taxes: CapexItem = Field(description="Inputs!C35 - Taxes & Duties (150 k€)")
    project_acquisition: CapexItem = Field(description="Inputs!C36 - Project Acquisition (1,000 k€)")
    project_rights: CapexItem = Field(description="Inputs!C37 - Project Rights (3,024.5 k€)")

    # === Dynamic CAPEX items (set after debt sizing) ===
    idc_keur: float = Field(
        default=0.0,
        ge=0,
        description="Interest During Construction (IDC) - computed iteratively"
    )
    commitment_fees_keur: float = Field(
        default=0.0,
        ge=0,
        description="Commitment fees on undrawn debt"
    )
    bank_fees_keur: float = Field(
        default=0.0,
        ge=0,
        description="Bank fees"
    )
    vat_costs_keur: float = Field(
        default=0.0,
        ge=0,
        description="VAT costs spread across construction"
    )
    reserve_accounts_keur: float = Field(
        default=0.0,
        ge=0,
        description="Initial DSRA funding at financial close"
    )

    def total_capex_keur(self) -> float:
        """Calculate total CAPEX including all items."""
        items = [
            self.epc_contract, self.production_units, self.epc_other,
            self.grid_connection, self.ops_prep, self.insurances,
            self.lease_tax, self.construction_mgmt_a, self.commissioning,
            self.audit_legal, self.construction_mgmt_b, self.contingencies,
            self.taxes, self.project_acquisition, self.project_rights,
        ]
        hard_total = sum(item.amount_keur for item in items)
        return hard_total + self.idc_keur + self.commitment_fees_keur + \
               self.bank_fees_keur + self.vat_costs_keur + self.reserve_accounts_keur

    def get_capex_summary(self) -> dict:
        """Get CAPEX summary for display."""
        items = [
            self.epc_contract, self.production_units, self.epc_other,
            self.grid_connection, self.ops_prep, self.insurances,
            self.lease_tax, self.construction_mgmt_a, self.commissioning,
            self.audit_legal, self.construction_mgmt_b, self.contingencies,
            self.taxes, self.project_acquisition, self.project_rights,
        ]
        return {
            "hard_capex_keur": sum(item.amount_keur for item in items),
            "idc_keur": self.idc_keur,
            "commitment_fees_keur": self.commitment_fees_keur,
            "bank_fees_keur": self.bank_fees_keur,
            "vat_costs_keur": self.vat_costs_keur,
            "reserve_accounts_keur": self.reserve_accounts_keur,
            "total_capex_keur": self.total_capex_keur(),
        }
