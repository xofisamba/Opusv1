"""Regulatory parameters by jurisdiction.

Covers: permits, grid connection, curtailment, balancing, REC, carbon, subsidies.
"""
from dataclasses import dataclass
from typing import Optional


# =============================================================================
# REGULATORY PARAMS
# =============================================================================
@dataclass(frozen=True)
class RegulatoryParams:
    """Regulatory and market parameters for project finance.
    
    Covers permits, grid, curtailment, balancing, REC, carbon, subsidies.
    Jurisdiction-specific defaults via factory methods.
    """
    # Jurisdiction
    jurisdiction: str = "HR"
    
    # =============================================================================
    # PERMITS AND TIMELINES
    # =============================================================================
    permitting_timeline_months: int = 24  # Total permit duration
    grid_connection_timeline_months: int = 18  # Grid connection timeline
    construction_permit_timeline_months: int = 6  # Construction permit
    
    # =============================================================================
    # GRID CONNECTION
    # =============================================================================
    grid_connection_type: str = "distribution"  # "direct_transmission" | "distribution" | "submarine"
    grid_congestion_risk: str = "low"  # "low" | "medium" | "high"
    grid_upgrade_required: bool = False
    grid_upgrade_cost_keur: float = 0.0  # Grid upgrade cost if required
    
    # =============================================================================
    # CURTAILMENT
    # =============================================================================
    mandatory_curtailment_pct: float = 0.0  # Mandatory curtailment (%)
    curtailment_compensation: bool = True  # Does grid operator pay for curtailment?
    curtailment_compensation_pct: float = 1.0  # % of lost revenue compensated (0.7-1.0 typical)
    
    # =============================================================================
    # BALANCING
    # =============================================================================
    balancing_responsibility: str = "aggregator"  # "generator" | "aggregator" | "supplier"
    balancing_zone: str = "HOPS"  # TSO zone (HOPS for HR)
    balancing_cost_pct_of_revenue: float = 0.025  # 2.5% typical
    
    # =============================================================================
    # RENEWABLE ENERGY CERTIFICATES (GO/REC)
    # =============================================================================
    rec_enabled: bool = True  # GO (Guarantees of Origin) enabled
    rec_price_eur_mwh: float = 0.5  # Market price for GO (EUR/MWh)
    rec_policy_stability: str = "stable"  # "stable" | "uncertain" | "phasing_out"
    
    # =============================================================================
    # CARBON CREDITS
    # =============================================================================
    carbon_credit_enabled: bool = False  # CDM, JI or EU ETS eligibility
    carbon_price_eur_tco2: float = 0.0  # Carbon price (EUR/tCO2)
    
    # =============================================================================
    # SUBSIDIES AND GRANTS
    # =============================================================================
    capital_grant_pct: float = 0.0  # % of CAPEX as grant (EU funds)
    capital_grant_keur: float = 0.0  # Absolute grant amount
    production_subsidy_eur_mwh: float = 0.0  # Subsidy per MWh produced
    subsidy_term_years: int = 0  # Duration of subsidy
    
    # =============================================================================
    # GRID ACCESS FEES
    # =============================================================================
    grid_access_fee_keur_per_mw: float = 0.0  # Annual fee per MW
    transmission_fee_eur_mwh: float = 0.0  # Transmission fee per MWh
    distribution_fee_eur_mwh: float = 0.0  # Distribution fee per MWh
    
    # =============================================================================
    # ENVIRONMENTAL COMPLIANCE
    # =============================================================================
    environmental_impact_assessment_required: bool = True
    eia_timeline_months: int = 12
    biodiversity_offset_cost_keur: float = 0.0
    decommissioning_bond_keur: float = 0.0  # Bond for decommissioning
    
    def validate_configuration(self) -> list[str]:
        """Validate regulatory configuration."""
        errors = []
        
        if self.mandatory_curtailment_pct < 0 or self.mandatory_curtailment_pct > 1:
            errors.append("Mandatory curtailment must be between 0 and 1 (0% to 100%)")
        
        if self.curtailment_compensation_pct < 0 or self.curtailment_compensation_pct > 1:
            errors.append("Curtailment compensation must be between 0 and 1")
        
        if self.capital_grant_pct < 0 or self.capital_grant_pct > 1:
            errors.append("Capital grant % must be between 0 and 1")
        
        return errors
    
    def curtailment_cost_mwh(self, energy_mwh: float, price_eur_mwh: float) -> float:
        """Calculate curtailment cost per year.
        
        Args:
            energy_mwh: Total energy production (MWh)
            price_eur_mwh: Average electricity price (EUR/MWh)
        
        Returns:
            Cur tailment cost in kEUR
        """
        lost_energy = energy_mwh * self.mandatory_curtailment_pct
        lost_revenue = lost_energy * price_eur_mwh
        
        if self.curtailment_compensation:
            return lost_revenue * (1 - self.curtailment_compensation_pct) / 1000
        else:
            return lost_revenue / 1000
    
    def rec_revenue_keur(self, generation_mwh: float) -> float:
        """Calculate REC (Guarantees of Origin) revenue.
        
        Args:
            generation_mwh: Total generation in MWh
        
        Returns:
            REC revenue in kEUR
        """
        if not self.rec_enabled:
            return 0.0
        return generation_mwh * self.rec_price_eur_mwh / 1000
    
    # Factory methods for jurisdiction
    @staticmethod
    def create_hr_defaults() -> "RegulatoryParams":
        """Croatian regulatory parameters."""
        return RegulatoryParams(
            jurisdiction="HR",
            permitting_timeline_months=24,
            grid_connection_timeline_months=18,
            grid_connection_type="distribution",
            grid_congestion_risk="medium",  # Some grid congestion in HR
            balancing_responsibility="aggregator",
            balancing_zone="HOPS",
            balancing_cost_pct_of_revenue=0.025,
            rec_enabled=True,
            rec_price_eur_mwh=0.5,  # GO market price
            rec_policy_stability="stable",
            carbon_credit_enabled=False,  # No CERs for HR
            grid_access_fee_keur_per_mw=3.0,  # Annual grid fee
            transmission_fee_eur_mwh=2.0,
            distribution_fee_eur_mwh=1.5,
            environmental_impact_assessment_required=True,
            eia_timeline_months=12,
        )
    
    @staticmethod
    def create_ba_defaults() -> "RegulatoryParams":
        """Bosnia regulatory parameters."""
        return RegulatoryParams(
            jurisdiction="BA",
            permitting_timeline_months=30,
            grid_connection_timeline_months=24,
            grid_connection_type="distribution",
            grid_congestion_risk="high",  # Grid constraints in BA
            balancing_responsibility="generator",
            balancing_zone="NOSBIH",
            balancing_cost_pct_of_revenue=0.035,  # Higher balancing cost
            rec_enabled=False,  # No GO system in BA yet
            carbon_credit_enabled=False,
            environmental_impact_assessment_required=True,
            eia_timeline_months=14,
        )
    
    @staticmethod
    def create_rs_defaults() -> "RegulatoryParams":
        """Serbia regulatory parameters."""
        return RegulatoryParams(
            jurisdiction="RS",
            permitting_timeline_months=24,
            grid_connection_timeline_months=18,
            grid_connection_type="distribution",
            grid_congestion_risk="medium",
            balancing_responsibility="aggregator",
            balancing_zone="EMS",
            balancing_cost_pct_of_revenue=0.030,
            rec_enabled=True,
            rec_price_eur_mwh=0.3,  # Lower GO price
            rec_policy_stability="uncertain",
            carbon_credit_enabled=True,  # Can issue CERs
            carbon_price_eur_tco2=25.0,  # EUR 25/tCO2
            grid_access_fee_keur_per_mw=2.0,
            environmental_impact_assessment_required=True,
        )
    
    @staticmethod
    def create_si_defaults() -> "RegulatoryParams":
        """Slovenia regulatory parameters."""
        return RegulatoryParams(
            jurisdiction="SI",
            permitting_timeline_months=18,
            grid_connection_timeline_months=12,
            grid_connection_type="distribution",
            grid_congestion_risk="low",
            balancing_responsibility="aggregator",
            balancing_zone="ELES",
            balancing_cost_pct_of_revenue=0.020,
            rec_enabled=True,
            rec_price_eur_mwh=1.0,  # Higher GO price in EU
            rec_policy_stability="stable",
            carbon_credit_enabled=True,
            carbon_price_eur_tco2=80.0,  # EU ETS price
            grid_access_fee_keur_per_mw=4.0,
            environmental_impact_assessment_required=True,
            eia_timeline_months=10,
        )
    
    @staticmethod
    def create_mk_defaults() -> "RegulatoryParams":
        """North Macedonia regulatory parameters."""
        return RegulatoryParams(
            jurisdiction="MK",
            permitting_timeline_months=26,
            grid_connection_timeline_months=20,
            grid_connection_type="distribution",
            grid_congestion_risk="medium",
            balancing_responsibility="generator",
            balancing_zone="MEPSO",
            balancing_cost_pct_of_revenue=0.030,
            rec_enabled=True,
            rec_price_eur_mwh=0.2,  # Lower GO price
            rec_policy_stability="phasing_out",  # Transitional
            carbon_credit_enabled=False,
            environmental_impact_assessment_required=True,
            eia_timeline_months=12,
        )
    
    @staticmethod
    def create_for_jurisdiction(jurisdiction: str) -> "RegulatoryParams":
        """Factory method for jurisdiction.
        
        Args:
            jurisdiction: "HR", "BA", "RS", "SI", "MK", or "EU_generic"
        
        Returns:
            RegulatoryParams with defaults
        """
        jurisdiction = jurisdiction.upper()
        
        if jurisdiction == "HR":
            return RegulatoryParams.create_hr_defaults()
        elif jurisdiction == "BA":
            return RegulatoryParams.create_ba_defaults()
        elif jurisdiction == "RS":
            return RegulatoryParams.create_rs_defaults()
        elif jurisdiction == "SI":
            return RegulatoryParams.create_si_defaults()
        elif jurisdiction == "MK":
            return RegulatoryParams.create_mk_defaults()
        else:
            return RegulatoryParams.create_hr_defaults()


__all__ = ["RegulatoryParams"]