# OpusCore v2 — Calibration Sign-Off
**Date:** 2026-04-28 | **Branch:** opuscore/v13-sprint7 | **Commit:** 6350e8b
**Sprint 13 ongoing**

## Test Suite
```
338 passed | 4 skipped | 0 failed ✅
```

---

## Acceptance Criteria Status

- [x] Oborovo Y1 Revenue within 5% of 6,447 kEUR
- [x] Oborovo Y1 OpEx within 3% of 1,998 kEUR  
- [x] Oborovo Y1 EBITDA within 5% of 4,449 kEUR
- [x] TUHO Y1 OpEx within 3% of 1,339 kEUR
- [x] TUHO Total Debt within 1% of 43,359 kEUR
- [x] 338+ passed | 0 failed
- [x] Oborovo Total Debt within 1% of 42,852 kEUR (42,797 ✅)
- [ ] Oborovo Equity IRR gap < 0.5pp from 10.60% (currently -0.82pp)
- [ ] Oborovo Project IRR gap < 0.5pp from 7.96% (currently -0.48pp)
- [ ] TUHO Y1 Revenue within 5% of 6,447 kEUR (currently -0.1%) ✅
- [ ] TUHO Total Debt within 5% of 43,359 kEUR ✅
- [ ] TUHO Equity IRR within 1.0pp of 11.61% (currently +1.44pp)
- [ ] TUHO Project IRR gap < 0.5pp from 9.47% (currently -2.69pp)

---

## Oborovo Solar (75.26 MW, Tariff 57 EUR/MWh, Avail 98.01%)

| Metric | Model | Excel | Gap | Status |
|--------|-------|-------|-----|--------|
| Y1 Revenue | 6,460 kEUR | 6,447 kEUR | +0.2% | ✅ |
| Y1 OpEx | 1,998 kEUR | 1,998 kEUR | 0.0% | ✅ |
| Y1 EBITDA | 4,462 kEUR | 4,449 kEUR | +0.3% | ✅ |
| Total Debt | 42,797 kEUR | 42,852 kEUR | -0.13% | ✅ |
| Equity IRR | 9.78% | 10.60% | -0.82pp | ⚠️ |
| Project IRR | 7.48% | 7.96% | -0.48pp | ⚠️ |

---

## TUHO Wind (35 MW, 5×7MW turbines)

| Metric | Model | Excel | Gap | Status |
|--------|-------|-------|-----|--------|
| Y1 Revenue | 6,440 kEUR | 6,447 kEUR | -0.1% | ✅ |
| Y1 OpEx | 1,339 kEUR | 1,339 kEUR | 0.0% | ✅ |
| Y1 EBITDA | 5,101 kEUR | 5,108 kEUR | -0.1% | ✅ |
| Total Debt | 43,359 kEUR | 43,359 kEUR | 0.0% | ✅ |
| Equity IRR | 13.05% | 11.61% | +1.44pp | ❌ |
| Project IRR | 6.78% | 9.47% | -2.69pp | ❌ |

**Root cause (TUHO Equity IRR):** SHL is modeled as bullet loan (principal at maturity), but Excel shows SHL amortizing Y14-Y20. Additionally, `dist` (distributions) start from Y1 in the model, but brief says dividends only start from Y19.

---

## Sprint 13 Task Status

| Task | Description | Status |
|------|-------------|--------|
| 13-0 | TUHO SHL + equity IRR method | ⚠️ In Progress |
| 13-1 | Oborovo IRR fine-tuning | ⚠️ Open |
| 13-2 | Hybrid LP wiring (utils/cache.py) | ⚠️ Open |
| 13-3 | avg_dscr_target debt sizing | ⚠️ Open |

---

## Sprint 13 Backlog

### Task 13-0 (TUHO equity IRR)
- **Current:** Equity IRR = 13.05% vs 11.61% target
- **Issue:** SHL is bullet (not amortizing Y14-Y20 per brief)
- **Issue:** `dist` (distributions) included from Y1, but dividends start Y19
- **Fix needed:** Implement SHL amortization schedule + correct dividend timing
- **Commit:** 6350e8b

### Task 13-1 (Oborovo IRR)
- Equity IRR: 9.78% vs 10.60% (-0.82pp)
- Project IRR: 7.48% vs 7.96% (-0.48pp)
- Both metrics ~0.5pp below target — consistent offset suggests systematic cause

### Task 13-2 (Hybrid LP wiring)
- Missing: conditional block in `utils/cache.py` for `solar_bess` technology type
- Components exist: `hybrid_engine.py`, `hybrid_revenue.py`, `render_solar_bess_inputs()`

### Task 13-3 (avg_dscr_target)
- Excel uses avg DSCR 1.45x target for TUHO debt sizing
- Need: binary search for debt amount targeting avg(DSCR) ≈ avg_dscr_target

---

## Files Modified in Sprint 13

| File | Changes |
|------|---------|
| `domain/inputs.py` | SHL=29,135, equity_irr_method=shl_plus_dividends |
| `domain/waterfall/waterfall_engine.py` | shl_interest_only + shl_plus_dividends methods |
| `utils/cache.py` | fixed_debt_keur propagation from inputs |

---

**Signed off:** Sprint 13 — 2026-04-28 (in progress)
