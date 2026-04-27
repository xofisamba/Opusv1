# Phase 5 Backlog

## Prioritet 1 — Kalibracijski dug

### Oborovo Initial Debt gap: 41,199 vs 42,852 kEUR (-3.9%)
- **Hipoteza**: model koristi `gearing_ratio` bez korekcije za IDC (interest during construction)
- **Akcija**: reverse-engineer Excel debt sizing — provjeri da li Excel dodaje idc_keur prije debt calculation
- **ili**: provjeri da li model koristi `sculpt_capex` umjesto `total_capex` u gearing izračunu

### TUHO IRR residual gap: 9.29% vs 9.47% (-0.18pp)
- **Status**: Prihvatljiv — unutar ±0.2pp tolerancije
- **Hipoteza**: Excel koristi `total_capex` umjesto `equity_investment` za neki drugi izračun ili ima terminal value
- **Akcija**: Ako bude potrebno, istražiti DSRA release timing i terminal CF u Excelu

---

## Prioritet 2 — Novi feature

### Hybrid LP dispatch engine (Sprint 4B originalni plan)
- 12-representative-week LP optimizacija za BESS
-Integracija s postojećim BESS modelom
- Clamp dispatch kod konvergentnosti

### SHL amortizacijski raspored (nije bullet repayment)
- Trenutno: SHL repaid as bullet at maturity (last period)
- Excel možda koristi drugačiji raspored (pro-rata ili other)
- Akcija: provjeri TUHO Excel SHL repayment schedule

### Floating rate hedging (swap simulation)
- Hedged portion: 80% (hedge_coverage=0.8)
- Model ne simulira swap cash flows (fixed vs floating)
- Akcija: dodati swap simulation u waterfall

### Mezzanine debt tranche
- Trenutno: samo senior + SHL
- Za neke projekte postoji i mezzanine (subordinated debt)
- Akcija: dodati treću debt tranche ako projekt to zahtijeva

---

## Prioritet 3 — Enterprise

### REST API (FastAPI)
- Expose waterfall endpoint za externe klijente
- Auth: JWT token based
- Rate limiting

### Multi-user / auth
- User management
- Project sharing
- Role-based access (admin, editor, viewer)

### Portfolio IRR (više projekata)
- Aggregate IRR across multiple projects
- Weighted average cost of capital
- Cross-project capital reallocation

### Docker + CI/CD
- Docker image za deployment
- GitHub Actions za automated tests
- Streamlit cloud deployment

---

## Done in Phase 4A-4C

- [x] TUHO Revenue kalibracija (+CO2 +balancing, availability=1.0)
- [x] Oborovo Revenue kalibracija (availability=0.9801)
- [x] TUHO Fixed DS amortizacija (DSCR 1.16 → 1.46)
- [x] TUHO Equity IRR fix (SHL excluded from equity_investment)
