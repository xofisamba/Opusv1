"""Project finance input models - immutable dataclasses matching Excel structure.

All classes use @dataclass(frozen=True) for immutability.
Each field documents the corresponding Excel cell reference.
"""
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class PeriodFrequency(Enum):
    """Period frequency matching Excel Inputs!D18."""
    SEMESTRIAL = "Semestrial"
    ANNUAL = "Annual"
    QUARTERLY = "Quarterly"


class YieldScenario(Enum):
    """Yield scenario selection matching Excel Inputs!D52."""
    P50 = "P_50"
    P90_10Y = "P90-10y"
    P99_1Y = "P99-1y"


@dataclass(frozen=True)
class ProjectInfo:
    """Basic project metadata. Corresponds to Excel Inputs sheet rows 2-18."""
    name: str                       # Inputs!D2 - Project name
    company: str                   # Inputs!D3 - Company name
    code: str                      # Inputs!D4 - Project code
    country_iso: str                # Inputs!D5 - Country code (e.g., "HR")
    financial_close: date           # Inputs!D9 - Financial close date
    construction_months: int       # Inputs!D10 - Construction duration in months
    cod_date: date                  # Inputs!D11 - Commercial operation date
    horizon_years: int             # Inputs!D14 - Investment horizon in years
    period_frequency: PeriodFrequency  # Inputs!D18 - "Semestrial", "Annual", etc.


@dataclass(frozen=True)
class CapexItem:
    """Single CAPEX line item with spending profile.
    
    Corresponds to Excel Inputs rows 23-44.
    Each item has an amount and spending profile across periods.
    
    Example:
        EPC Contract: 26,430 k€ → Y0:0%, Y1:8.3%, Y2:8.3% ... (12 month linear)
        Project Rights: 3,024.5 k€ → Y0:100%, rest: 0%
    """
    name: str                      # Item description
    amount_keur: float             # Total amount in kEUR
    y0_share: float = 0.0          # % paid in Y0 (construction year 0)
    spending_profile: tuple[float, ...] = ()  # Shares for Y1, Y2, Y3, Y4
    
    @property
    def total_spending_shares(self) -> float:
        """Sum of all spending shares (y0 + profile). Should equal 1.0."""
        return self.y0_share + sum(self.spending_profile)

    def __post_init__(self):
        """Validate spending shares sum to approximately 1.0."""
        total = self.total_spending_shares
        if total > 0 and abs(total - 1.0) > 0.01:
            raise ValueError(
                f'{self.name}: spending shares sum to {total:.4f}, expected 1.0. '
                f'Check spending_profile or y0_share values.'
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


@dataclass(frozen=True)
class CapexStructure:
    """Complete CAPEX structure with 22 items from Oborovo Excel.
    
    Corresponds to Excel Inputs rows 23-44 (22 CAPEX categories).
    
    Items marked as "dynamic" are computed iteratively:
    - IDC: Solved via fixed-point iteration (circular with debt)
    - Commitment Fees: Based on undrawn debt during construction
    - Reserve Accounts: DSRA, J-DSRA, MRA funded at financial close
    """
    # === Hard CAPEX items ===
    epc_contract: CapexItem        # Inputs!C23 - EPC Contract (26,430 k€)
    production_units: CapexItem    # Inputs!C24 - Production Units (10,912.7 k€)
    epc_other: CapexItem           # Inputs!C25 - Other EPC (3,200 k€)
    grid_connection: CapexItem     # Inputs!C26 - Grid Connection (1,800 k€)
    ops_prep: CapexItem            # Inputs!C27 - Operations Preparation (500 k€)
    insurances: CapexItem          # Inputs!C28 - Insurances (400 k€)
    lease_tax: CapexItem           # Inputs!C29 - Lease & Property Tax (200 k€)
    construction_mgmt_a: CapexItem  # Inputs!C30 - Construction Management A
    commissioning: CapexItem       # Inputs!C31 - Commissioning (300 k€)
    audit_legal: CapexItem         # Inputs!C32 - Audit & Legal (200 k€)
    construction_mgmt_b: CapexItem  # Inputs!C33 - Construction Management B
    contingencies: CapexItem       # Inputs!C34 - Contingencies (1,986.4 k€)
    taxes: CapexItem               # Inputs!C35 - Taxes & Duties (150 k€)
    project_acquisition: CapexItem  # Inputs!C36 - Project Acquisition (1,000 k€)
    project_rights: CapexItem      # Inputs!C37 - Project Rights (3,024.5 k€)
    # === Dynamic items (computed, not direct input) ===
    idc_keur: float = 0.0          # Interest During Construction (computed)
    commitment_fees_keur: float = 0.0  # Commitment fees on undrawn debt
    bank_fees_keur: float = 0.0   # Bank fees (upfront)
    other_financial_keur: float = 0.0  # Other financial costs
    vat_costs_keur: float = 0.0    # VAT costs spread over Y0-Y3
    reserve_accounts_keur: float = 0.0  # Initial reserve account funding
    
    @property
    def hard_capex_keur(self) -> float:
        """Sum of all hard CAPEX items (excluding dynamic items)."""
        items = [
            self.epc_contract, self.production_units, self.epc_other,
            self.grid_connection, self.ops_prep, self.insurances,
            self.lease_tax, self.construction_mgmt_a, self.commissioning,
            self.audit_legal, self.construction_mgmt_b, self.contingencies,
            self.taxes, self.project_acquisition, self.project_rights,
        ]
        return sum(item.amount_keur for item in items)

    @property
    def hard_capex(self) -> float:
        """Alias for hard_capex_keur for backward compatibility."""
        return self.hard_capex_keur
    
    @property
    def total_capex_before_idc(self) -> float:
        """Total CAPEX excluding IDC."""
        return self.hard_capex_keur + self.commitment_fees_keur + \
               self.bank_fees_keur + self.other_financial_keur + \
               self.vat_costs_keur + self.reserve_accounts_keur
    
    @property
    def total_capex(self) -> float:
        """Total CAPEX including IDC."""
        return self.total_capex_before_idc + self.idc_keur


@dataclass(frozen=True)
class OpexItem:
    """Single OPEX line item with individual escalation.
    
    Corresponds to Excel Inputs rows 146-161 (15 OPEX categories).
    Each item has Y1 amount and annual escalation rate.
    
    Example:
        Technical Management: 198 k€ Y1, 2% annual index
        Power Expenses: 126.86 k€ Y1, 0% index (flat)
    """
    name: str                      # Item description
    y1_amount_keur: float         # Amount in kEUR for Year 1
    annual_inflation: float = 0.02  # Annual escalation rate (0.02 = 2%)
    step_changes: tuple[tuple[int, float], ...] = field(default_factory=lambda: ())
    # e.g. ((3, 185.64),) means Y3 OPEX is hardcoded to 185.64 k€

    def amount_at_year(self, year: int) -> float:
        """Return OPEX amount for a given year with escalation.
        
        Args:
            year: 1-based year index (1=Y1, 2=Y2, etc.)
        
        Returns:
            Amount in kEUR for that year
        """
        # Check for step change
        for step_year, amount in self.step_changes:
            if year == step_year:
                return amount
        # Apply escalation from Y1
        result = self.y1_amount_keur * (1 + self.annual_inflation) ** (year - 1)
        return max(0.0, result)  # Guard against negative OPEX from negative inflation


@dataclass(frozen=True)
class TechnicalParams:
    """Technical parameters for the project.
    
    Corresponds to Excel Inputs rows 51-68.
    """
    capacity_mw: float             # Inputs!D51 - Installed capacity (75.26 MW)
    yield_scenario: str            # Inputs!D52 - "P_50", "P90-10y", etc.
    operating_hours_p50: float = 0.0    # Inputs!D64 - P50 yield hours (1,494)
    operating_hours_p90_1y: float | None = None  # P90-1y hours (single year exceedance)
    operating_hours_p90_10y: float = 0.0  # Inputs!D68 - P90-10y hours (1,410)
    operating_hours_p99_1y: float | None = None  # P99-1y hours (scenario engine)
    pv_degradation: float = 0.004  # Inputs!D56 - Annual degradation (0.4%)
    bess_degradation: float = 0.003  # Inputs!D57 - BESS degradation (0.3%)
    plant_availability: float = 0.99  # Inputs!D58 - Plant availability (99%)
    grid_availability: float = 0.99   # Inputs!D59 - Grid availability (99%)
    bess_enabled: bool = False     # Inputs!D140 - BESS enabled flag
    
    @property
    def combined_availability(self) -> float:
        """Combined plant × grid availability (98% for Oborovo)."""
        return self.plant_availability * self.grid_availability


@dataclass(frozen=True)
class RevenueParams:
    """Revenue parameters including PPA and market pricing.
    
    Corresponds to Excel Inputs rows 78-141.
    """
    ppa_base_tariff: float         # Inputs!D78 - Base PPA tariff (57 €/MWh)
    ppa_term_years: int           # Inputs!D81 - PPA term in years (12)
    ppa_index: float = 0.02        # Inputs!D83 - PPA annual index (2%)
    ppa_production_share: float = 1.0  # Inputs!D80 - Share of production in PPA
    market_scenario: str = "Central"  # Inputs!B103 - Market scenario name
    market_prices_curve: tuple[float, ...] = ()  # Inputs row 107 - Market price curve
    market_inflation: float = 0.02  # Inputs!B129 - Market price inflation (2%)
    balancing_cost_pv: float = 0.025  # Inputs!D114 - Balancing cost % (2.5%)
    balancing_cost_bess: float = 0.025  # Inputs!D115 - BESS balancing cost
    co2_enabled: bool = False      # Inputs!D139 - CO2 certificates enabled
    co2_price_eur: float = 1.5     # Inputs!E141 - CO2 price (1.5 €/ton)
    
    def tariff_at_year(self, year: int) -> float:
        """Return PPA tariff in year with escalation.
        
        Args:
            year: 1-based year index (1=Y1, 2=Y2, etc.)
        
        Returns:
            Tariff in €/MWh
        """
        return self.ppa_base_tariff * (1 + self.ppa_index) ** (year - 1)
    
    def market_price_at_year(self, year: int) -> float:
        """Return market price in year.
        
        Args:
            year: 1-based year index
        
        Returns:
            Market price in €/MWh
        """
        idx = year - 1
        if idx < len(self.market_prices_curve):
            return self.market_prices_curve[idx]
        # Extrapolate with market inflation
        if self.market_prices_curve:
            base = self.market_prices_curve[-1]
            return base * (1 + self.market_inflation) ** (idx - len(self.market_prices_curve) + 1)
        return self.ppa_base_tariff  # Fallback


@dataclass(frozen=True)
class FinancingParams:
    """Financing parameters including debt and equity structure.
    
    Corresponds to Excel Inputs rows 168-349.
    """
    # Equity structure
    share_capital_keur: float = 500.0   # Inputs!D312 - Share capital (500 k€)
    share_premium_keur: float = 0.0     # Inputs!D313 - Share premium
    shl_amount_keur: float = 13547.2     # Inputs!D325 - Shareholder loan (13,547.2 k€)
    shl_rate: float = 0.08              # Inputs!F328 - SHL interest rate (8%)
    
    # Debt structure
    gearing_ratio: float = 0.7524       # Inputs!D168 - Gearing ratio (75.24%)
    senior_debt_amount_keur: float = 0.0  # Inputs!D192 - Senior debt (computed)
    senior_tenor_years: int = 14        # Inputs!D196 - Senior debt tenor (14 years)
    base_rate: float = 0.03             # Inputs!D202 - Base rate (3%)
    margin_bps: int = 265               # Inputs!D203 - Margin in basis points (265)
    floating_share: float = 0.2         # Inputs!B39 - Floating rate share (20%)
    fixed_share: float = 0.8            # Inputs!B40 - Fixed rate share (80%)
    hedge_coverage: float = 0.8         # Inputs!D230 - Hedge coverage (80%)
    
    # Fees
    commitment_fee: float = 0.0105      # Inputs!D214 - Commitment fee (1.05%)
    arrangement_fee: float = 0.0        # Inputs!D218 - Arrangement fee
    structuring_fee: float = 0.01       # Inputs!D217 - Structuring fee (1%)
    
    # Covenants
    target_dscr: float = 1.15           # Inputs!D221 - Target DSCR (1.15x)
    lockup_dscr: float = 1.10           # Inputs!D223 - Lockup DSCR threshold (1.10x)
    min_llcr: float = 1.15             # Inputs!D224 - Minimum LLCR (1.15x)
    
    # Reserve accounts
    dsra_months: int = 6               # Inputs!D348 - DSRA funding months (6)
    
    @property
    def all_in_rate(self) -> float:
        """All-in interest rate (base + margin)."""
        return self.base_rate + self.margin_bps / 10000
    
    @property
    def total_equity_shl_keur(self) -> float:
        """Total equity + shareholder loan."""
        return self.share_capital_keur + self.share_premium_keur + self.shl_amount_keur


@dataclass(frozen=True)
class TaxParams:
    """Tax parameters including corporate tax and loss carryforward.
    
    Corresponds to Excel Inputs rows 403-426.
    """
    corporate_rate: float = 0.10       # Inputs!D403 - Corporate tax rate (10%)
    loss_carryforward_years: int = 5   # Inputs!D407 - Loss carryforward years (5)
    loss_carryforward_cap: float = 1.0  # Inputs!D408 - Cap as % of profit (100%)
    legal_reserve_cap: float = 0.10    # Inputs!D410 - Legal reserve cap (% of capital)
    
    # Thin cap / ATAD
    thin_cap_enabled: bool = False     # Inputs!D414 - Thin cap enabled
    thin_cap_de_ratio: float = 0.8     # Inputs!D415 - DE/equity ratio threshold
    atad_ebitda_limit: float = 0.30    # ATAD EBITDA interest limit (30%)
    atad_min_interest_keur: float = 3000.0  # ATAD minimum interest threshold
    
    # Withholding taxes
    wht_sponsor_dividends: float = 0.05  # Inputs!D426 - WHT on dividends (5%)
    wht_sponsor_shl_interest: float = 0.0  # Inputs!D423 - WHT on SHL interest (0%)
    
    # SHL interest cap (for foreign sovereign)
    shl_cap_applies: bool = True       # Inputs!D412 - SHL interest cap applies


@dataclass(frozen=True)
class ProjectInputs:
    """Complete project inputs combining all parameter classes.
    
    This is the root input structure for the entire model.
    All values are frozen after construction (immutable).
    """
    info: ProjectInfo
    technical: TechnicalParams
    capex: CapexStructure
    opex: tuple[OpexItem, ...]  # 15 OPEX items
    revenue: RevenueParams
    financing: FinancingParams
    tax: TaxParams
    
    @classmethod
    def create_default_oborovo(cls) -> "ProjectInputs":
        """Create default Oborovo project inputs matching Excel.
        
        Returns:
            ProjectInputs with Oborovo-specific defaults.
        """
        # CAPEX items (from Oborovo Excel Inputs rows 23-37)
        epc_contract = CapexItem(
            name="EPC Contract",
            amount_keur=26430.0,
            y0_share=0.0,
            spending_profile=(0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083),
        )
        production_units = CapexItem(
            name="Production Units",
            amount_keur=10912.7,
            y0_share=0.0,
            spending_profile=(0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083, 0.083),
        )
        epc_other = CapexItem(name="Other EPC", amount_keur=3200.0, y0_share=0.0, spending_profile=(0.5, 0.5))
        grid_connection = CapexItem(name="Grid Connection", amount_keur=1800.0, y0_share=0.5, spending_profile=(0.5,))
        ops_prep = CapexItem(name="Operations Preparation", amount_keur=500.0, y0_share=0.5, spending_profile=(0.5,))
        insurances = CapexItem(name="Insurances", amount_keur=400.0, y0_share=1.0)
        lease_tax = CapexItem(name="Lease & Property Tax", amount_keur=200.0, y0_share=1.0)
        construction_mgmt_a = CapexItem(name="Construction Management A", amount_keur=800.0, y0_share=0.5, spending_profile=(0.5,))
        commissioning = CapexItem(name="Commissioning", amount_keur=300.0, y0_share=0.5, spending_profile=(0.5,))
        audit_legal = CapexItem(name="Audit & Legal", amount_keur=200.0, y0_share=0.5, spending_profile=(0.5,))
        construction_mgmt_b = CapexItem(name="Construction Management B", amount_keur=400.0, y0_share=0.5, spending_profile=(0.5,))
        contingencies = CapexItem(name="Contingencies", amount_keur=1986.4, y0_share=1.0)
        taxes = CapexItem(name="Taxes & Duties", amount_keur=150.0, y0_share=1.0)
        project_acquisition = CapexItem(name="Project Acquisition", amount_keur=1000.0, y0_share=0.5, spending_profile=(0.5,))
        project_rights = CapexItem(name="Project Rights", amount_keur=3024.5, y0_share=1.0)
        
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
            idc_keur=1086.0,  # IDC from Oborovo Excel
            commitment_fees_keur=188.6,  # Commitment fees
            bank_fees_keur=477.3,  # Bank fees
            vat_costs_keur=216.1,  # VAT costs spread
            reserve_accounts_keur=2239.1,  # Initial DSRA funding
        )
        
        # OPEX items (from Oborovo Excel Inputs rows 146-161)
        opex_items = (
            OpexItem(name="Technical Management", y1_amount_keur=198.0, annual_inflation=0.02),
            OpexItem(name="Infrastructure Maintenance", y1_amount_keur=244.0, annual_inflation=0.02,
                    step_changes=((3, 185.64),)),  # Step down in Y3
            OpexItem(name="Maintain Site", y1_amount_keur=45.2, annual_inflation=0.02),
            OpexItem(name="Clean Material", y1_amount_keur=40.0, annual_inflation=0.02),
            OpexItem(name="Security", y1_amount_keur=30.1, annual_inflation=0.02),
            OpexItem(name="Insurance", y1_amount_keur=255.0, annual_inflation=0.02),
            OpexItem(name="Lease & Property Tax", y1_amount_keur=208.08, annual_inflation=0.02),
            OpexItem(name="Power Expenses", y1_amount_keur=126.86, annual_inflation=0.0),  # Flat
            OpexItem(name="Fees", y1_amount_keur=95.6, annual_inflation=0.0),  # Flat
            OpexItem(name="Audit&Accounting&Legal", y1_amount_keur=24.0, annual_inflation=0.02),
            OpexItem(name="Bank Fees", y1_amount_keur=20.0, annual_inflation=0.02),
            OpexItem(name="Environmental&Social", y1_amount_keur=15.0, annual_inflation=0.02,
                    step_changes=((3, 5.2),)),  # Step down in Y3
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
        
        # Market price curve (Central scenario, from Excel Inputs row 107)
        # Values in €/MWh for years 1-30
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
            opex=opex_items,
            revenue=revenue,
            financing=financing,
            tax=tax,
        )

# =============================================================================
# Cache utilities (for @st.cache_data hash_funcs)
# =============================================================================

def hash_inputs_for_cache(inputs: "ProjectInputs") -> tuple:
    """Deterministic hash for frozen ProjectInputs.
    
    Used for @st.cache_data hash_funcs parameter.
    
    Args:
        inputs: ProjectInputs instance (must be frozen)
    
    Returns:
        Tuple of values for hashing
    """
    return (
        inputs.info.financial_close,
        inputs.technical.capacity_mw,
        inputs.financing.gearing_ratio,
        inputs.financing.all_in_rate,
        inputs.revenue.ppa_base_tariff,
        inputs.revenue.ppa_term_years,
        inputs.capex.total_capex,
        inputs.tax.corporate_rate,
    )
