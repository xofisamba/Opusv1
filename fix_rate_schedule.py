"""Surgical fix: add rate_schedule to all waterfall calls in app.py."""
import re

content = open('src/app.py').read()

# ============================================================
# 1. Add import at top
# ============================================================
OLD_IMPORT = "from utils.cache import cached_run_waterfall_v3  # v3: proper hash_funcs"
NEW_IMPORT = """from utils.cache import cached_run_waterfall_v3  # v3: proper hash_funcs
from utils.rate_curve import build_rate_schedule, apply_rate_shock"""

if OLD_IMPORT in content:
    content = content.replace(OLD_IMPORT, NEW_IMPORT)
    print("Added import")
else:
    print("WARNING: Could not find import")

# ============================================================
# 2. Replace pattern for waterfall calls in each tab
# Each call looks like:
#   with st.spinner("..."):
#       result = cached_run_waterfall_v3(
#           ...kwargs...
#       )
#   # Comment that follows
#
# We need to insert rate_schedule build before the cached call
# and add rate_schedule=rate_schedule to the call.
# ============================================================

# For P90 sizing block (scenario section) - handle separately
# For regular tabs (PL, BS, CF, Waterfall) - use pattern

TAB_BLOCKS = {
    "P&L": {
        "spinner": 'with st.spinner("Calculating P&L..."):',
        "comment_after": "# Determine depreciation params",
        "gearing": True,
    },
    "BS": {
        "spinner": 'with st.spinner("Calculating Balance Sheet..."):',
        "comment_after": "# Determine depreciation params",
        "gearing": True,
    },
    "CF": {
        "spinner": 'with st.spinner("Calculating Cash Flow..."):',
        "comment_after": "# Determine depreciation params",
        "gearing": True,
    },
    "Waterfall": {
        "spinner": 'with st.spinner("Calculating waterfall..."):',
        "comment_after": "# KPI Strip",
        "gearing": False,
    },
}

for tab_name, tab_info in TAB_BLOCKS.items():
    spinner = tab_info["spinner"]
    comment_after = tab_info["comment_after"]
    has_gearing = tab_info["gearing"]

    # Build the rate_schedule block
    rate_schedule_block = """
                rate_schedule = build_rate_schedule(
                    base_rate_type=debt_config.senior.base_rate_type,
                    tenor_periods=tenor_periods,
                    periods_per_year=2,
                    base_rate_override=debt_config.senior.base_rate if debt_config.senior.base_rate_type == "FIXED" else None,
                    floating_share=debt_config.senior.floating_share,
                    fixed_share=debt_config.senior.fixed_share,
                    hedge_coverage=debt_config.senior.hedged_share,
                    margin_bps=debt_config.senior.margin_bps,
                    base_rate_floor=debt_config.senior.base_rate_floor,
                )
                shock_bps = st.session_state.get("sensitivity_shocks", {}).get("rate", 0)
                if shock_bps > 0:
                    rate_schedule = apply_rate_shock(rate_schedule, int(shock_bps))
"""

    if has_gearing:
        old_call = f'''{spinner}
                result = cached_run_waterfall_v3(
                    inputs=inputs, engine=engine,
                    rate_per_period=rate, tenor_periods=tenor_periods,
                    target_dscr=debt_config.senior.target_dscr,
                    lockup_dscr=debt_config.senior.min_dscr_lockup,
                    tax_rate=tax_config.corporate_tax_rate,
                    dsra_months=debt_config.senior.dsra_months,
                    shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                    shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                    discount_rate_project=0.0641, discount_rate_equity=0.0965,
                    gearing_ratio=inputs.financing.gearing_ratio,
                )
            
            {comment_after}'''

        new_call = f'''{spinner}
                {rate_schedule_block}
                result = cached_run_waterfall_v3(
                    inputs=inputs, engine=engine,
                    rate_per_period=rate, tenor_periods=tenor_periods,
                    target_dscr=debt_config.senior.target_dscr,
                    lockup_dscr=debt_config.senior.min_dscr_lockup,
                    tax_rate=tax_config.corporate_tax_rate,
                    dsra_months=debt_config.senior.dsra_months,
                    shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                    shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                    discount_rate_project=0.0641, discount_rate_equity=0.0965,
                    gearing_ratio=inputs.financing.gearing_ratio,
                    rate_schedule=rate_schedule,
                )
            
            {comment_after}'''
    else:
        old_call = f'''{spinner}
                result = cached_run_waterfall_v3(
                    inputs=inputs,
                    engine=engine,
                    rate_per_period=rate,
                    tenor_periods=tenor_periods,
                    target_dscr=debt_config.senior.target_dscr,
                    lockup_dscr=debt_config.senior.min_dscr_lockup,
                    tax_rate=tax_config.corporate_tax_rate,
                    dsra_months=debt_config.senior.dsra_months,
                    shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                    shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                    discount_rate_project=0.0641,
                    discount_rate_equity=0.0965,
                )
            
            {comment_after}'''

        new_call = f'''{spinner}
                {rate_schedule_block}
                result = cached_run_waterfall_v3(
                    inputs=inputs,
                    engine=engine,
                    rate_per_period=rate,
                    tenor_periods=tenor_periods,
                    target_dscr=debt_config.senior.target_dscr,
                    lockup_dscr=debt_config.senior.min_dscr_lockup,
                    tax_rate=tax_config.corporate_tax_rate,
                    dsra_months=debt_config.senior.dsra_months,
                    shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                    shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                    discount_rate_project=0.0641,
                    discount_rate_equity=0.0965,
                    rate_schedule=rate_schedule,
                )
            
            {comment_after}'''

    if old_call in content:
        content = content.replace(old_call, new_call)
        print(f"Fixed {tab_name} tab")
    else:
        print(f"WARNING: Could not find {tab_name} block")

# ============================================================
# 3. Fix P90 sizing block (scenario section)
# ============================================================
# This is before the "with st.spinner('Running P90 sizing...')" block
OLD_P90_HEADER = '''            rate = debt_config.senior.all_in_rate / 2
            tenor_periods = debt_config.senior.tenor_years * 2
            
            with st.spinner("Running P90 sizing..."):'''

NEW_P90_HEADER = '''            rate = debt_config.senior.all_in_rate / 2
            tenor_periods = debt_config.senior.tenor_years * 2
            
            # Build Euribor rate curve for this run
            shock_bps = st.session_state.get("sensitivity_shocks", {}).get("rate", 0)
            rate_schedule = build_rate_schedule(
                base_rate_type=debt_config.senior.base_rate_type,
                tenor_periods=tenor_periods,
                periods_per_year=2,
                base_rate_override=debt_config.senior.base_rate if debt_config.senior.base_rate_type == "FIXED" else None,
                floating_share=debt_config.senior.floating_share,
                fixed_share=debt_config.senior.fixed_share,
                hedge_coverage=debt_config.senior.hedged_share,
                margin_bps=debt_config.senior.margin_bps,
                base_rate_floor=debt_config.senior.base_rate_floor,
            )
            if shock_bps > 0:
                rate_schedule = apply_rate_shock(rate_schedule, int(shock_bps))
            
            with st.spinner("Running P90 sizing..."):'''

if OLD_P90_HEADER in content:
    content = content.replace(OLD_P90_HEADER, NEW_P90_HEADER)
    print("Fixed P90 header")
else:
    print("WARNING: Could not find P90 header")

# ============================================================
# 4. Add rate_schedule to P90 sizing call
# ============================================================
OLD_P90_CALL = '''                    p90_result = cached_run_waterfall_v3(
                        inputs=p90_inputs, engine=engine,
                        rate_per_period=rate, tenor_periods=tenor_periods,
                        target_dscr=debt_config.senior.target_dscr,
                        lockup_dscr=debt_config.senior.min_dscr_lockup,
                        tax_rate=inputs.tax.corporate_rate,
                        dsra_months=debt_config.senior.dsra_months,
                        shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                        shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                        discount_rate_project=0.0641, discount_rate_equity=0.0965,
                        fixed_debt_keur=None,  # Let it size for P90
                    )'''

NEW_P90_CALL = '''                    p90_result = cached_run_waterfall_v3(
                        inputs=p90_inputs, engine=engine,
                        rate_per_period=rate, tenor_periods=tenor_periods,
                        target_dscr=debt_config.senior.target_dscr,
                        lockup_dscr=debt_config.senior.min_dscr_lockup,
                        tax_rate=inputs.tax.corporate_rate,
                        dsra_months=debt_config.senior.dsra_months,
                        shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                        shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                        discount_rate_project=0.0641, discount_rate_equity=0.0965,
                        fixed_debt_keur=None,  # Let it size for P90
                        rate_schedule=rate_schedule,  # Euribor curve
                    )'''

if OLD_P90_CALL in content:
    content = content.replace(OLD_P90_CALL, NEW_P90_CALL)
    print("Fixed P90 sizing call")
else:
    print("WARNING: Could not find P90 sizing call")

# ============================================================
# 5. Add rate_schedule to run_fn closure
# ============================================================
OLD_RUN_FN = '''                    # Create partial function for scenario runs
                    def run_fn(inputs=inputs, fixed_debt_keur=fixed_debt_keur):
                        return cached_run_waterfall_v3(
                            inputs=inputs, engine=engine,
                            rate_per_period=rate, tenor_periods=tenor_periods,
                            target_dscr=debt_config.senior.target_dscr,
                            lockup_dscr=debt_config.senior.min_dscr_lockup,
                            tax_rate=inputs.tax.corporate_rate,
                            dsra_months=debt_config.senior.dsra_months,
                            shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                            shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                            discount_rate_project=0.0641, discount_rate_equity=0.0965,
                            fixed_debt_keur=fixed_debt_keur,
                        )'''

NEW_RUN_FN = '''                    # Create partial function for scenario runs
                    def run_fn(inputs=inputs, fixed_debt_keur=fixed_debt_keur):
                        return cached_run_waterfall_v3(
                            inputs=inputs, engine=engine,
                            rate_per_period=rate, tenor_periods=tenor_periods,
                            target_dscr=debt_config.senior.target_dscr,
                            lockup_dscr=debt_config.senior.min_dscr_lockup,
                            tax_rate=inputs.tax.corporate_rate,
                            dsra_months=debt_config.senior.dsra_months,
                            shl_amount=debt_config.shl.shl_keur if debt_config.shl else 0,
                            shl_rate=debt_config.shl.shl_rate if debt_config.shl else 0.06,
                            discount_rate_project=0.0641, discount_rate_equity=0.0965,
                            fixed_debt_keur=fixed_debt_keur,
                            rate_schedule=rate_schedule,  # Euribor curve
                        )'''

if OLD_RUN_FN in content:
    content = content.replace(OLD_RUN_FN, NEW_RUN_FN)
    print("Fixed run_fn closure")
else:
    print("WARNING: Could not find run_fn closure")

open('src/app.py', 'w').write(content)
print("Done writing app.py")
