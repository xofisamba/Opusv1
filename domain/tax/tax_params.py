"""Tax parameters by jurisdiction.

Supports: HR, BA, RS, SI, MK, EU_generic
Includes: Corporate tax, loss carryforward, ATAD, thin cap, WHT, DTT
"""
from dataclasses import dataclass
from typing import Optional
from enum import Enum


# =============================================================================
# JURISDICTION CONSTANTS
# =============================================================================
class Jurisdiction(Enum):
    HR = "HR"  # Croatia
    BA = "BA"  # Bosnia
    RS = "RS"  # Serbia
    SI = "SI"  # Slovenia
    MK = "MK"  # North Macedonia
    EU_GENERIC = "EU_generic"


# =============================================================================
# TAX PARAMETERS
# =============================================================================
@dataclass(frozen=True)
class TaxParams:
    """Tax parameters for project finance model.
    
    Covers corporate tax, loss carryforward, ATAD, thin cap rules, WHT, DTT.
    Jurisdiction-specific defaults are provided via factory methods.
    """
    # Jurisdiction
    jurisdiction: str = "HR"
    
    # Corporate tax rate
    corporate_tax_rate: float = 0.10  # 10% for HR
    
    # Depreciation
    depreciation_method: str = "straight_line"  # "straight_line" | "declining_balance"
    useful_life_solar_years: int = 25  # Solar: 25-30 years
    useful_life_wind_years: int = 20  # Wind: 20-25 years
    useful_life_bess_years: int = 10  # BESS: 10-15 years (to first replacement)
    accelerated_depreciation: bool = False
    
    # ATAD (Anti-Tax Avoidance Directive) - EU standard
    atad_applies: bool = True  # True for HR, SI; False for BA, RS, MK
    atad_ebitda_limit: float = 0.30  # 30% EBITDA interest limit
    atad_min_threshold_keur: float = 3000.0  # Minimum threshold (3M EUR)
    atad_carryforward_years: int = 0  # 0 = unlimited in EU
    
    # Loss carryforward
    loss_carryforward_years: int = 5  # HR=5, BA=5, RS=5, SI=unlimited, MK=3
    loss_carryforward_cap_pct: float = 1.0  # % of current profit that can be covered
    
    # Thin capitalization
    thin_cap_enabled: bool = True
    thin_cap_ratio: float = 4.0  # D/E ratio limit (3:1 or 4:1)
    thin_cap_safe_harbor_keur: float = 0.0  # Amount below which thin cap doesn't apply
    
    # Withholding taxes
    wht_dividends: float = 0.05  # WHT on dividends
    wht_interest: float = 0.0  # WHT on interest (varies by DTT)
    wht_royalties: float = 0.0  # WHT on royalties
    
    # DTT (Double Tax Treaty) - for foreign sponsor
    dtt_country: str = ""  # Residence country of sponsor
    dtt_dividends_rate: float = 0.05  # DTT reduced rate on dividends
    dtt_interest_rate: float = 0.0  # DTT reduced rate on interest
    
    # Tax holidays and incentives
    tax_holiday_years: int = 0  # Years of tax holiday (where applicable)
    investment_allowance_pct: float = 0.0  # % of CAPEX deductible from tax base
    green_energy_tax_credit: float = 0.0  # Green energy tax credit (EUR/kW)
    
    # Local taxes
    property_tax_pct_of_capex: float = 0.0  # Annual property tax (% of CAPEX)
    land_use_fee_keur_per_ha: float = 0.0  # Land use fee per hectare
    grid_access_annual_keur: float = 0.0  # Annual grid access fee
    
    # VAT
    vat_rate: float = 0.25  # HR=25%, BA=17%, RS=20%, SI=22%, MK=18%
    vat_on_capex_recoverable: bool = True  # PDV on CAPEX is recoverable
    
    # SHL interest cap (for foreign sovereign - thin cap adjustment)
    shl_cap_applies: bool = True
    shl_interest_cap_rate: float = 0.0  # Max deductible SHL interest rate
    
    def taxable_income(self, ebitda: float, interest: float, depreciation: float) -> float:
        """Calculate taxable income.
        
        Args:
            ebitda: EBITDA in kEUR
            interest: Total interest expense in kEUR
            depreciation: Depreciation charge in kEUR
        
        Returns:
            Taxable profit in kEUR
        """
        # Apply ATAD limit on interest
        deductible_interest = interest
        if self.atad_applies:
            atad_limit = ebitda * self.atad_ebitda_limit
            if interest > atad_limit and ebitda > self.atad_min_threshold_keur:
                deductible_interest = atad_limit
        
        profit = ebitda - deductible_interest - depreciation
        return max(0.0, profit)
    
    def tax_liability(self, taxable_profit: float) -> float:
        """Calculate tax on taxable profit.
        
        Args:
            taxable_profit: Taxable profit in kEUR
        
        Returns:
            Tax liability in kEUR
        """
        return taxable_profit * self.corporate_tax_rate
    
    def validate_configuration(self) -> list[str]:
        """Validate tax configuration.
        
        Returns:
            List of validation errors. Empty = valid.
        """
        errors = []
        
        if self.corporate_tax_rate < 0 or self.corporate_tax_rate > 1:
            errors.append("Corporate tax rate must be between 0 and 1 (0% to 100%)")
        
        if self.loss_carryforward_years < 0:
            errors.append("Loss carryforward years cannot be negative")
        
        if self.thin_cap_ratio <= 0:
            errors.append("Thin cap ratio must be positive")
        
        if self.vat_rate < 0 or self.vat_rate > 1:
            errors.append("VAT rate must be between 0 and 1")
        
        return errors
    
    # Factory methods for jurisdiction defaults
    @staticmethod
    def create_hr_defaults() -> "TaxParams":
        """Croatian tax parameters."""
        return TaxParams(
            jurisdiction="HR",
            corporate_tax_rate=0.10,
            loss_carryforward_years=5,
            atad_applies=True,
            atad_ebitda_limit=0.30,
            atad_min_threshold_keur=3000.0,
            atad_carryforward_years=0,  # Unlimited
            thin_cap_enabled=True,
            thin_cap_ratio=4.0,  # 4:1 D/E
            wht_dividends=0.05,
            wht_interest=0.0,  # DTT with many countries
            vat_rate=0.25,
            vat_on_capex_recoverable=True,
            property_tax_pct_of_capex=0.001,  # ~0.1% annual
        )
    
    @staticmethod
    def create_ba_defaults() -> "TaxParams":
        """Bosnia and Herzegovina tax parameters."""
        return TaxParams(
            jurisdiction="BA",
            corporate_tax_rate=0.10,
            loss_carryforward_years=5,
            atad_applies=False,  # Not EU
            thin_cap_enabled=True,
            thin_cap_ratio=4.0,
            wht_dividends=0.05,
            wht_interest=0.0,
            vat_rate=0.17,
            vat_on_capex_recoverable=False,
        )
    
    @staticmethod
    def create_rs_defaults() -> "TaxParams":
        """Serbia tax parameters."""
        return TaxParams(
            jurisdiction="RS",
            corporate_tax_rate=0.15,  # 15%
            loss_carryforward_years=5,
            atad_applies=False,
            thin_cap_enabled=True,
            thin_cap_ratio=4.0,
            wht_dividends=0.10,  # Higher WHT
            wht_interest=0.0,
            vat_rate=0.20,
            vat_on_capex_recoverable=True,
        )
    
    @staticmethod
    def create_si_defaults() -> "TaxParams":
        """Slovenia tax parameters."""
        return TaxParams(
            jurisdiction="SI",
            corporate_tax_rate=0.19,  # 19%
            loss_carryforward_years=0,  # Unlimited
            atad_applies=True,
            atad_ebitda_limit=0.30,
            atad_min_threshold_keur=3000.0,
            thin_cap_enabled=True,
            thin_cap_ratio=4.0,
            wht_dividends=0.05,
            wht_interest=0.0,
            vat_rate=0.22,
            vat_on_capex_recoverable=True,
        )
    
    @staticmethod
    def create_mk_defaults() -> "TaxParams":
        """North Macedonia tax parameters."""
        return TaxParams(
            jurisdiction="MK",
            corporate_tax_rate=0.10,
            loss_carryforward_years=3,
            atad_applies=False,
            thin_cap_enabled=True,
            thin_cap_ratio=4.0,
            wht_dividends=0.05,
            wht_interest=0.0,
            vat_rate=0.18,
            vat_on_capex_recoverable=True,
            tax_holiday_years=0,  # Some incentives available
        )
    
    @staticmethod
    def create_for_jurisdiction(jurisdiction: str) -> "TaxParams":
        """Factory method for jurisdiction.
        
        Args:
            jurisdiction: "HR", "BA", "RS", "SI", "MK", or "EU_generic"
        
        Returns:
            TaxParams with defaults for jurisdiction
        """
        jurisdiction = jurisdiction.upper()
        
        if jurisdiction == "HR":
            return TaxParams.create_hr_defaults()
        elif jurisdiction == "BA":
            return TaxParams.create_ba_defaults()
        elif jurisdiction == "RS":
            return TaxParams.create_rs_defaults()
        elif jurisdiction == "SI":
            return TaxParams.create_si_defaults()
        elif jurisdiction == "MK":
            return TaxParams.create_mk_defaults()
        else:
            # EU_generic fallback to HR defaults
            return TaxParams.create_hr_defaults()


# =============================================================================
# DTT TABLE (Double Tax Treaty rates)
# =============================================================================
@dataclass(frozen=True)
class DTTRate:
    """Double Tax Treaty rate between two countries.
    
    Used for reducing WHT on dividends, interest, royalties.
    """
    country: str  # Country code (HR, AT, DE, etc.)
    dividends: float  # Reduced WHT rate on dividends
    interest: float  # Reduced WHT rate on interest
    royalties: float  # Reduced WHT rate on royalties


# Common DTT rates for HR (example)
DTT_TABLE_HR = {
    # Country: (dividends, interest, royalties)
    "AT": (5, 0, 5),    # Austria - 5% dividends, 0% interest, 5% royalties
    "DE": (5, 0, 5),    # Germany
    "IT": (5, 0, 5),    # Italy
    "SI": (5, 0, 5),    # Slovenia
    "BA": (10, 0, 10),  # Bosnia
    "RS": (10, 0, 10),  # Serbia
    "MK": (10, 0, 10),  # Macedonia
    "LU": (5, 0, 5),    # Luxembourg - often used for funds
    "NL": (5, 0, 5),    # Netherlands
    "GB": (5, 0, 5),    # UK
    "CH": (5, 0, 5),    # Switzerland
    "FR": (5, 0, 5),    # France
    "US": (5, 0, 5),    # USA
}


def get_dtt_rate(jurisdiction: str, dtt_country: str) -> DTTRate:
    """Get DTT rate between jurisdiction and country.
    
    Args:
        jurisdiction: Home jurisdiction (HR, SI, etc.)
        dtt_country: Counterparty country for DTT
    
    Returns:
        DTTRate with applicable rates
    """
    if jurisdiction == "HR" and dtt_country in DTT_TABLE_HR:
        rates = DTT_TABLE_HR[dtt_country]
        return DTTRate(
            country=dtt_country,
            dividends=rates[0] / 100,
            interest=rates[1] / 100,
            royalties=rates[2] / 100,
        )
    
    # Default - no DTT applies, use standard WHT
    return DTTRate(
        country=dtt_country,
        dividends=0.05,  # Standard 5%
        interest=0.0,
        royalties=0.0,
    )


__all__ = [
    "TaxParams",
    "DTTRate",
    "get_dtt_rate",
    "DTT_TABLE_HR",
]