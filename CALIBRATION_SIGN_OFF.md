# OpusCore v2 — Calibration Sign-Off
**Date:** 2026-04-27 | **Branch:** opuscore/v13-sprint7 | **Commit:** bd35256

## Acceptance Criteria Status

- [x] Oborovo Y1 Revenue within 5% of 6,447 kEUR
- [x] Oborovo Y1 OpEx within 3% of 1,998 kEUR  
- [x] Oborovo Y1 EBITDA within 5% of 4,449 kEUR
- [x] TUHO Y1 OpEx within 3% of 1,339 kEUR
- [x] TUHO Total Debt within 1% of 43,359 kEUR
- [x] 338+ passed | 0 failed
- [ ] Oborovo Project IRR gap < 0.5pp from 7.96% (currently -0.52pp)
- [ ] Oborovo Equity IRR gap < 0.5pp from 10.60% (currently -0.54pp)
- [ ] Oborovo Total Debt within 1% of 42,852 kEUR (currently +1.78%)
- [ ] TUHO Y1 Revenue within 5% of 6,447 kEUR (currently +27.7%)
- [ ] TUHO Equity IRR gap < 0.5pp from 11.61% (currently -0.96pp)
- [ ] TUHO Project IRR gap < 0.5pp from 9.47% (currently -0.37pp) ✅

---

## Oborovo Solar (75.26 MW, Tariff 57 EUR/MWh, Avail 98.01%)

| Metric | Model | Excel | Gap | Status |
|--------|-------|-------|-----|--------|
| Y1 Revenue | 6,460 kEUR | 6,447 kEUR | +0.2% | ✅ |
| Y1 OpEx | 1,998 kEUR | 1,998 kEUR | 0.0% | ✅ |
| Y1 EBITDA | 4,462 kEUR | 4,449 kEUR | +0.3% | ✅ |
| Total Debt | 43,614 kEUR | 42,852 kEUR | +1.78% | ⚠️ |
| Equity IRR | 10.06% | 10.60% | -0.54pp | ⚠️ |
| Project IRR | 7.44% | 7.96% | -0.52pp | ⚠️ |
| Avg DSCR | 0.823 | 1.147 | -0.324 | ⚠️ |

**Note:** Y1 Revenue/OpEx/EBITDA all calibrated ✅. Remaining debt/IRR gaps require further investigation (Task 10-1 root cause analysis pending).

---

## TUHO Wind (35 MW, 5×7MW turbines)

| Metric | Model | Excel | Gap | Status |
|--------|-------|-------|-----|--------|
| Y1 Revenue | 8,231 kEUR | 6,447 kEUR | +27.7% | ❌ |
| Y1 OpEx | 1,339 kEUR | 1,339 kEUR | 0.0% | ✅ |
| Y1 EBITDA | 6,892 kEUR | 5,108 kEUR | +34.9% | ❌ |
| Total Debt | 43,358 kEUR | 43,359 kEUR | -0.0% | ✅ |
| Equity IRR | 10.65% | 11.61% | -0.96pp | ⚠️ |
| Project IRR | 9.10% | 9.47% | -0.37pp | ✅ |

**Root cause (TUHO Revenue):** Model uses `operating_hours_p50=4164` producing 145,740 MWh/year. Excel implies ~3,149 hours based on 110,201 MWh Y1 generation. The 27.7% revenue gap is due to generation calculation method difference (fixed hours vs capacity factor).

---

## Task 10 Summary

| Task | Description | Status |
|------|-------------|--------|
| 10-0 | Oborovo OpEx calibration (1,339 → 1,998 kEUR) | ✅ Done |
| 10-1 | TUHO Revenue root cause (generation hours mismatch) | ⚠️ Open |
| 10-2 | TUHO OpEx already correct (1,339 kEUR) | ✅ Done |
| 10-3 | Final calibration + fixture freeze | ⚠️ Partial |

---

## Remaining Calibration Work

### Oborovo (needs Sprint 11)
- **Debt (+1.78%):** Model gives 43,614 vs Excel 42,852. Root cause: model uses `sculpt_capex_keur=57,967` for gearing base vs Excel implied `56,954`. Gap = IDC amount (~1,013 kEUR).
- **Project IRR (-0.52pp):** After OpEx fix, IRR shifted from +0.66pp to -0.52pp. Needs revenue check and/or financing param adjustment.
- **Avg DSCR (-0.324):** Model 0.823 vs Excel 1.147 — large gap in debt sizing constraint.

### TUHO (needs Sprint 11)
- **Revenue (+27.7%):** `operating_hours_p50=4164` should be ~3,149 to match Excel Y1 generation of 110,201 MWh. This affects all downstream metrics.
- **Equity IRR (-0.96pp):** Will improve when generation is corrected.

---

## Test Suite Results

```
338 passed | 4 skipped | 0 failed
Branch: opuscore/v13-sprint7
Commit: bd35256
```

---

## Files Modified in Sprint 10

| File | Changes |
|------|---------|
| `domain/inputs.py` | Oborovo OpEx (198→703 kEUR), TUHO OpEx scaled (1998→1339 kEUR) |
| `tests/test_opex.py` | Updated expected values to match new OpEx |
| `tests/test_inputs.py` | Updated expected Technical Management from 198→703 kEUR |
| `tests/fixtures/oborovo_base.json` | opex_y1_keur: 1998, opex_per_mw_keur: 26.55 |
| `tests/fixtures/oborovo_baseline.json` | opex_y1_keur: 1998, opex_per_mw_keur: 26.55 |
| `tests/fixtures/oborovo_golden.json` | Added model_current_outputs section |
| `tests/fixtures/current_outputs.json` | Updated with Sprint 10 model state |

---

**Signed off:** Sprint 10 (partial) — 2026-04-27