# Debt Sizing Hierarchy — Oborovo Model

## Overview

Debt sizing in project finance follows a **hierarchy of constraints**. The model calculates debt as the **minimum** of two independent sizing methods:

1. **Gearing (D/E constraint)** — debt as % of CAPEX
2. **Sculpting (DSCR constraint)** — debt sized so average DSCR ≈ target

The binding constraint determines the final debt amount.

---

## 1. Gearing Constraint

**Formula:**
```
Senior Debt = Total CAPEX × Gearing Ratio
```

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `gearing_ratio` | 0.75 | 75% debt / CAPEX (bank-friendly) |
| `gearing_ratio` | 0.85 | 85% debt / CAPEX (higher leverage) |

**Typical ranges:**
- 70–80% for senior secured
- 80–90% for well-structured projects with credit enhancement

**Note:** Gearing is a *soft* constraint — if sculpting produces a *lower* debt amount, sculpting wins.

---

## 2. Sculpting (DSCR-Based Sizing)

**Canonical implementation:** `domain/financing/sculpting_iterative.py`

Sculpting sizes debt so that the average DSCR across all periods equals `target_dscr`.

### Algorithm

```
Binary search on debt amount:
  while not converged:
    debt = (low + high) / 2
    for each period:
      payment = EBITDA / target_dscr
      if DSCR < lockup_dscr:
        payment = 0  # lockup blocks distribution
      interest = balance × rate
      principal = payment - interest
      balance -= principal
    avg_dscr = mean(all_period_dscrs)
    if avg_dscr > target:
      low = debt
    else:
      high = debt
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_dscr` | 1.15 | Target average DSCR (1.15–1.30x) |
| `min_dscr_lockup` | 1.10 | DSCR below this → distribution blocked |
| `tenor_years` | 14 | Debt tenor (12–18 years) |

### Sculpting vs. Gearing

| Scenario | Gearing Debt | Sculpted Debt | Final Debt |
|----------|-------------|---------------|------------|
| Conservative assumptions | 75% × CAPEX | 60% × CAPEX | **60%** (sculpting wins) |
| Aggressive assumptions | 75% × CAPEX | 80% × CAPEX | **75%** (gearing wins) |
| Base case (Oborovo) | ~42,000 kEUR | **37,017 kEUR** | **37,017 kEUR** |

**Why sculpting gives lower debt:**
- Sculpting respects the `target_dscr` constraint
- In periods with low EBITDA (early years, lockup), sculpted payment is reduced
- This extends tenor or reduces principal = lower debt

---

## 3. Lockup Mechanism

When DSCR < `min_dscr_lockup` (default 1.10×), distributions to equity are **blocked**.

**Lockup effect:**
```
if DSCR < 1.10:
    distribution = 0          # equity gets nothing
    cash_sweep = 0           # no excess cash sweep
    debt_repayment = 0       # even principal stops
```

**Why lockup matters:**
- Prevents equity extraction when project can't support debt service
- Protects lenders from DSCR covenant breach
- Cash accumulates as `cash_balance` until lockup clears

---

## 4. Interest Rate Mode

The rate mode affects **interest burden** and thus debt capacity.

### Mode: FLAT (Hedge-Equivalent)

```
all_in_rate = base_rate + margin = 2.427% + 2.65% = 5.65%
rate_schedule = [0.0565, 0.0565, ..., 0.0565]  # constant
```

**Use case:** Base case matching Excel, hedge-equivalent pricing.

### Mode: EURIBOR (Floating)

```
EURIBOR_6M curve (April 2026):
  Period 0: 2.427%
  Period 6M: 2.427%
  Period 12M: 2.550%
  ...
  Period 84M: 3.500%

all_in_rate = EURIBOR_curve + margin  # varies per period
```

**Rate schedule calculation:**
```python
build_rate_schedule(
    base_rate_type="EURIBOR_6M",
    base_rate_override=None,  # uses EURIBOR spot + forwards
    margin_bps=265,
    floating_share=0.2,
    fixed_share=0.8,
    hedge_coverage=0.8,  # 80% hedged via swap
)
```

### Impact on Debt

| Mode | Debt | Reason |
|------|------|--------|
| FLAT (5.65%) | 37,017 kEUR | Constant rate |
| EURIBOR_6M (~6.0% avg) | 24,583 kEUR | Rising curve → higher avg interest → less capacity |

---

## 5. Debt Sizing Decision Tree

```
START: Input CAPEX, EBITDA schedule
        │
        ▼
┌─────────────────────────────┐
│ Calculate Gearing Debt:      │
│ Debt_gear = CAPEX × gearing  │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ Calculate Sculpted Debt:     │
│ Binary search on debt until │
│ avg_dscr ≈ target_dscr      │
└─────────────────────────────┘
        │
        ▼
    ┌───────────────┐
    │ Debt = MIN(   │ ◄── Binding constraint
    │   Debt_gear,  │
    │   Debt_sculpt)│
    └───────────────┘
        │
        ▼
┌─────────────────────────────┐
│ Apply Lockup Filter:        │
│ Periods with DSCR < 1.10    │
│ → distribution blocked      │
└─────────────────────────────┘
        │
        ▼
    Final Debt Schedule
```

---

## 6. Parameters Quick Reference

| Parameter | Default | Range | Affects |
|-----------|---------|-------|---------|
| `gearing_ratio` | 0.75 | 0.60–0.90 | Gearing debt |
| `target_dscr` | 1.15 | 1.10–1.35 | Sculpted debt |
| `min_dscr_lockup` | 1.10 | 1.05–1.15 | Lockup threshold |
| `tenor_years` | 14 | 10–20 | Repayment period |
| `base_rate` | 2.427% | market | Interest burden |
| `margin_bps` | 265 | 150–400 | Interest burden |
| `base_rate_type` | FLAT | FLAT/EURIBOR | Rate mode |

---

## 7. Reconciliation with Excel

| Metric | Excel | Model (FLAT) | Δ |
|--------|-------|--------------|---|
| Debt | 42,852 kEUR | 37,017 kEUR | -14% |
| Project IRR | 8.836% | 8.769% | -7 bps |
| Avg DSCR | 1.044 | 1.044 | 0 |

**Why Excel debt is higher:**
- Excel uses `gearing_ratio = 85%` or different sculpting parameters
- Model uses `target_dscr = 1.15` which constrains debt more tightly
- Excel may use a simpler "sculpted = gearing" approach without binary search

**For bank presentation:** Use model with `gearing_ratio = 0.80` to match Excel debt.

---

## 8. Live EURIBOR Rates (April 2026)

| Tenor | Rate | Source |
|-------|------|--------|
| 1M | 1.968% | euribor-rates.eu |
| 3M | 2.165% | euribor-rates.eu |
| 6M | 2.427% | euribor-rates.eu |
| 12M | 2.687% | euribor-rates.eu |

**Update command:**
```bash
# Fetch latest rates
curl https://www.euribor-rates.eu/en/current-euribor-rates/
# Then update utils/rate_curve.py
```
