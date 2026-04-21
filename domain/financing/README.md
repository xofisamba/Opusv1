# Financing Module — Canonical Implementation Guide

This module handles debt scheduling, sculpting, and financial covenants.

## Active (Canonical) Functions

| Function | File | Description |
|----------|------|-------------|
| `iterative_sculpt_debt` | `sculpting_iterative.py` | ✅ Canonical — DSCR-based iterative debt sculpting |
| `IterativeSculptResult` | `sculpting_iterative.py` | ✅ Return type for iterative sculpting |
| `standard_amortization` | `schedule.py` | ✅ Active — equal principal amortization |
| `senior_debt_amount` | `schedule.py` | ✅ Active — calculate senior debt from gearing |
| `annuity_payment` | `schedule.py` | ✅ Active — annuity payment calculation |
| `balance_after_n_periods` | `schedule.py` | ✅ Active — balance at period n |
| `dscr`, `llcr`, `plcr` | `covenants.py` | ✅ Active — covenant calculation |

## Deprecated (Do Not Use in New Code)

| Function | File | Status | Notes |
|----------|------|--------|-------|
| `sculpt_debt_dscr` | `sculpting.py` | ⚠️ Deprecated | Superseded by `iterative_sculpt_debt` |
| `sculpted_amortization` | `schedule.py` | ⚠️ Deprecated | Superseded by `iterative_sculpt_debt` |
| `find_debt_for_target_dscr` | `sculpting.py` | ❌ Unused | Binary search reimplemented in `sculpting_iterative.py` |

## Usage

```python
# Recommended: iterative sculpting
from domain.financing import iterative_sculpt_debt, IterativeSculptResult

result = iterative_sculpt_debt(
    ebitda_schedule=ebitda_list,
    rate_per_period=0.0565 / 2,  # Semi-annual
    tenor_periods=24,
    target_dscr=1.15,
)
print(f"Debt: {result.debt_keur:.0f} kEUR, Avg DSCR: {result.avg_dscr:.3f}")
```

## Architecture

The financing module is used by:
- `domain/waterfall/waterfall_engine.py` — calls `iterative_sculpt_debt` for debt sizing
- `ui/pages/charts_page.py` — calls `standard_amortization` for display
- `ui/pages/outputs_page.py` — calls `senior_debt_amount` for metrics