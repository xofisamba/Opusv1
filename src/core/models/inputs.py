"""Root ProjectInputs model combining all sub-models.

This is the main entry point for validated project inputs.
Corresponds to Excel Inputs sheet (rows 2-426).
"""
from pydantic import Field, computed_field
from typing import Optional

from .pydantic_base import FinancialBaseModel
from .project import ProjectInfo, PeriodFrequency, YieldScenario
from .capex import CapexItem, CapexStructure
from .opex import OpexItem
from .revenue import TechnicalParams, RevenueParams
from .financing import FinancingParams, TaxParams


class ProjectInputs(FinancialBaseModel):
    """Complete project inputs combining all parameter classes.

    This is the root input structure for the entire model.
    All values are validated on construction.

    Corresponds to Excel Inputs sheet (rows 2-426).

    Usage:
        # Create from defaults
        inputs = ProjectInputs.create_default_oborovo()

        # Validate from dict (e.g., loaded from JSON)
        inputs = ProjectInputs.model_validate(user_dict)

        # Export to JSON for Save Scenario
        json_data = inputs.to_json_dict()
    """
    info: ProjectInfo = Field(description="Basic project metadata")
    technical: TechnicalParams = Field(description="Technical parameters")
    capex: CapexStructure = Field(description="CAPEX structure with all items")
    opex: tuple[OpexItem, ...] = Field(
        default_factory=tuple,
        description="OPEX items tuple (15 items)"
    )
    revenue: RevenueParams = Field(description="Revenue parameters")
    financing: FinancingParams = Field(description="Financing parameters")
    tax: TaxParams = Field(description="Tax parameters")

    @classmethod
    def create_default_oborovo(cls) -> "ProjectInputs":
        """Create default Oborovo project inputs matching Excel.

        Returns:
            ProjectInputs with Oborovo-specific defaults.
        """
        from datetime import date

        # CAPEX items (all required for CapexStructure)
        epc_contract = CapexItem(
            name="EPC Contract",
            amount_keur=26430.0,
            y0_share=0.0,
            spending_profile=(0.083,)*12,
        )
        production_units = CapexItem(
            name="Production Units",
            amount_keur=10912.7,
            y0_share=0.0,
            spending_profile=(0.083,)*12,
        )
        epc_other = CapexItem(
            name="Other EPC",
            amount_keur=3200.0,
            y0_share=0.0,
            spending_profile=(0.5, 0.5),
        )
        grid_connection = CapexItem(
            name="Grid Connection",
            amount_keur=1800.0,
            y0_share=0.5,
            spending_profile=(0.5,),
        )
        ops_prep = CapexItem(
            name="Operations Preparation",
            amount_keur=500.0,
            y0_share=0.5,
            spending_profile=(0.5,),
        )
        insurances = CapexItem(
            name="Insurances",
            amount_keur=400.0,
            y0_share=1.0,
        )
        lease_tax = CapexItem(
            name="Lease & Property Tax",
            amount_keur=200.0,
            y0_share=1.0,
        )
        construction_mgmt_a = CapexItem(
            name="Construction Management A",
            amount_keur=800.0,
            y0_share=0.5,
            spending_profile=(0.5,),
        )
        commissioning = CapexItem(
            name="Commissioning",
            amount_keur=300.0,
            y0_share=0.5,
            spending_profile=(0.5,),
        )
        audit_legal = CapexItem(
            name="Audit & Legal",
            amount_keur=200.0,
            y0_share=0.5,
            spending_profile=(0.5,),
        )
        construction_mgmt_b = CapexItem(
            name="Construction Management B",
            amount_keur=400.0,
            y0_share=0.5,
            spending_profile=(0.5,),
        )
        contingencies = CapexItem(
            name="Contingencies",
            amount_keur=1986.4,
            y0_share=1.0,
        )
        taxes = CapexItem(
            name="Taxes & Duties",
            amount_keur=150.0,
            y0_share=1.0,
        )
        project_acquisition = CapexItem(
            name="Project Acquisition",
            amount_keur=1000.0,
            y0_share=0.5,
            spending_profile=(0.5,),
        )
        project_rights = CapexItem(
            name="Project Rights",
            amount_keur=3024.5,
            y0_share=1.0,
        )

        capex = CapexStructure(
            epc_contract=epc_contract,
            production_units=production_units,
            epc_other=epc_other,
            grid_connection=grid_connection,
            ops_prep=ops_prep,
            insurances=insurances,
            lease_tax=lease_tax,
            construction_mgmt_a=construction_mgmt_a,
            commissioning=commissioning,
            audit_legal=audit_legal,
            construction_mgmt_b=construction_mgmt_b,
            contingencies=contingencies,
            taxes=taxes,
            project_acquisition=project_acquisition,
            project_rights=project_rights,
            idc_keur=1086.0,
            commitment_fees_keur=188.6,
            bank_fees_keur=477.3,
            vat_costs_keur=216.1,
            reserve_accounts_keur=2239.1,
        )

        # OPEX items
        opex = (
            OpexItem(name="Technical Management", y1_amount_keur=198.0, annual_inflation=0.02),
            OpexItem(name="Infrastructure Maintenance", y1_amount_keur=244.0, annual_inflation=0.02,
                    step_changes=((3, 185.64),)),
            OpexItem(name="Maintain Site", y1_amount_keur=45.2, annual_inflation=0.02),
            OpexItem(name="Clean Material", y1_amount_keur=40.0, annual_inflation=0.02),
            OpexItem(name="Security", y1_amount_keur=30.1, annual_inflation=0.02),
            OpexItem(name="Insurance", y1_amount_keur=255.0, annual_inflation=0.02),
            OpexItem(name="Lease & Property Tax", y1_amount_keur=208.08, annual_inflation=0.02),
            OpexItem(name="Power Expenses", y1_amount_keur=126.86, annual_inflation=0.0),
            OpexItem(name="Fees", y1_amount_keur=95.6, annual_inflation=0.0),
            OpexItem(name="Audit&Accounting&Legal", y1_amount_keur=24.0, annual_inflation=0.02),
            OpexItem(name="Bank Fees", y1_amount_keur=20.0, annual_inflation=0.02),
            OpexItem(name="Environmental&Social", y1_amount_keur=15.0, annual_inflation=0.02,
                    step_changes=((3, 5.2),)),
            OpexItem(name="Contingencies", y1_amount_keur=52.07, annual_inflation=0.02),
            OpexItem(name="Taxes", y1_amount_keur=0.0, annual_inflation=0.0),
            OpexItem(name="Salary&Payroll", y1_amount_keur=0.0, annual_inflation=0.0),
        )

        info = ProjectInfo(
            name="Oborovo Solar PV",
            company="AKE Med",
            code="OBR-001",
            country_iso="HR",
            financial_close=date(2029, 6, 29),
            construction_months=12,
            cod_date=date(2030, 6, 29),
            horizon_years=30,
            period_frequency=PeriodFrequency.SEMESTRIAL,
        )

        technical = TechnicalParams(
            capacity_mw=75.26,
            yield_scenario="P_50",
            operating_hours_p50=1494.0,
            operating_hours_p90_10y=1410.0,
            pv_degradation=0.004,
            bess_degradation=0.003,
            plant_availability=0.99,
            grid_availability=0.99,
            bess_enabled=False,
        )

        # Market price curve (Central scenario)
        market_prices = (
            65.0, 66.3, 67.6, 69.0, 70.4, 71.8, 73.2, 74.7, 76.2, 77.7,
            79.3, 80.9, 82.5, 84.2, 85.9, 87.6, 89.4, 91.2, 93.0, 94.9,
            96.8, 98.7, 100.7, 102.7, 104.8, 106.9, 109.0, 111.2, 113.4, 115.7,
        )

        revenue = RevenueParams(
            ppa_base_tariff=57.0,
            ppa_term_years=12,
            ppa_index=0.02,
            ppa_production_share=1.0,
            market_scenario="Central",
            market_prices_curve=market_prices,
            market_inflation=0.02,
            balancing_cost_pv=0.025,
            balancing_cost_bess=0.025,
            co2_enabled=False,
            co2_price_eur=1.5,
        )

        financing = FinancingParams(
            share_capital_keur=500.0,
            share_premium_keur=0.0,
            shl_amount_keur=13547.2,
            shl_rate=0.08,
            gearing_ratio=0.7524,
            senior_tenor_years=14,
            base_rate=0.03,
            margin_bps=265,
            floating_share=0.2,
            fixed_share=0.8,
            hedge_coverage=0.8,
            commitment_fee=0.0105,
            arrangement_fee=0.0,
            structuring_fee=0.01,
            target_dscr=1.15,
            lockup_dscr=1.10,
            min_llcr=1.15,
            dsra_months=6,
        )

        tax = TaxParams(
            corporate_rate=0.10,
            loss_carryforward_years=5,
            loss_carryforward_cap=1.0,
            legal_reserve_cap=0.10,
            thin_cap_enabled=False,
            atad_ebitda_limit=0.30,
            atad_min_interest_keur=3000.0,
            wht_sponsor_dividends=0.05,
            wht_sponsor_shl_interest=0.0,
            shl_cap_applies=True,
        )

        return cls(
            info=info,
            technical=technical,
            capex=capex,
            opex=opex,
            revenue=revenue,
            financing=financing,
            tax=tax,
        )

    @computed_field
    @property
    def total_capex_keur(self) -> float:
        """Calculate total CAPEX."""
        return self.capex.total_capex_keur()

    @computed_field
    @property
    def total_opex_y1_keur(self) -> float:
        """Calculate total OPEX for Year 1."""
        return sum(item.y1_amount_keur for item in self.opex)

    def get_model_summary(self) -> dict:
        """Get complete model summary for display."""
        return {
            "project": self.info.name,
            "company": self.info.company,
            "capacity_mw": self.technical.capacity_mw,
            "total_capex_keur": self.total_capex_keur,
            "total_opex_y1_keur": self.total_opex_y1_keur,
            "ppa_tariff": f"{self.revenue.ppa_base_tariff:.1f} €/MWh",
            "gearing": f"{self.financing.gearing_ratio:.1%}",
            "all_in_rate": self.financing.all_in_rate_percent,
        }
