"""Projektne konstante za Oborovo Solar PV financijski model.

Služi kao single source of truth za sve magic numbers u projektu.
"""
from decimal import Decimal

# === Tehničke konstante ===
DEFAULT_PV_DEGRADATION: float = 0.004        # 0.4% godišnje
DEFAULT_BESS_DEGRADATION: float = 0.003      # 0.3% godišnje
DEFAULT_PLANT_AVAILABILITY: float = 0.99     # 99%
DEFAULT_GRID_AVAILABILITY: float = 0.99      # 99%

# === Oborovo kapacitet ===
OBOROVO_CAPACITY_MW: float = 75.26
OBOROVO_P50_HOURS: float = 1494.0
OBOROVO_P90_HOURS: float = 1410.0
OBOROVO_CAPEX_PER_MW: float = 800_000       # EUR/MW za Solar
OBOROVO_WIND_CAPEX_PER_MW: float = 1_100_000  # EUR/MW za Wind

# === Financijske konstante ===
DEFAULT_PPA_INDEX: float = 0.02              # 2% godišnje
DEFAULT_MARKET_INFLATION: float = 0.02       # 2% godišnje
DEFAULT_CORPORATE_TAX: float = 0.10          # 10% (HR)

# === OPEX po MW ===
SOLAR_OPEX_PER_MW: float = 15_000           # EUR/kW
WIND_OPEX_PER_MW: float = 35_000             # EUR/kW

# === BESS konstante ===
DEFAULT_BESS_ROUNDTRIP_EFF: float = 0.85
DEFAULT_BESS_CYCLE_LIFE: int = 5000
DEFAULT_BESS_DEGRADATION_RATE: float = 0.02

# === DSCR/LLCR parametri ===
DEFAULT_TARGET_DSCR: float = 1.15
DEFAULT_LOCKUP_DSCR: float = 1.10
DEFAULT_MIN_LLCR: float = 1.15

# === UI slider granice ===
MIN_CAPACITY_MW: float = 1.0
MAX_CAPACITY_MW: float = 500.0
MIN_TARIFF_EUR: float = 10.0
MAX_TARIFF_EUR: float = 200.0
MIN_GEARING: float = 0.0
MAX_GEARING: float = 0.95
MIN_HORIZON_YEARS: int = 10
MAX_HORIZON_YEARS: int = 40