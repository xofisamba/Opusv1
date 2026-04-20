"""Excel Parity page - Compare model outputs to Excel."""
import streamlit as st
import os

from io_.excel_integration import (
    parse_oborovo_excel,
    compare_to_excel,
    print_parity_report,
)


def render_excel_parity(inputs, engine) -> None:
    st.header("📊 Excel Parity Report")
    
    s = st.session_state
    
    st.markdown("""
    **Purpose:** Compare Python model outputs to actual Excel (Oborovo.xlsm) values.
    
    **Workflow:**
    1. Upload or specify path to Oborovo.xlsm
    2. Run comparison
    3. Review metrics that deviate from Excel
    """)
    
    st.divider()
    
    # File input
    col1, col2 = st.columns([2, 1])
    
    with col1:
        excel_path = st.text_input(
            "Excel File Path",
            value="/root/.openclaw/workspace/Oborovo.xlsm",
            help="Path to Oborovo.xlsm file"
        )
    
    with col2:
        st.write("")  # Spacer
        tolerance = st.slider("Tolerance (%)", 0.1, 10.0, 1.0, step=0.1)
    
    st.divider()
    
    # Parse Excel section
    st.subheader("📥 Parse Excel")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📂 Parse Excel File", type="primary", use_container_width=True):
            if os.path.exists(excel_path):
                with st.spinner("Parsing Excel file..."):
                    excel_inputs = parse_oborovo_excel(excel_path)
                    
                    if excel_inputs:
                        st.session_state.excel_inputs = excel_inputs
                        st.success("✅ Excel parsed successfully!")
                        
                        # Display parsed values
                        st.write("**Parsed Values:**")
                        st.write(f"- Capacity: {excel_inputs.technical.capacity_mw:.2f} MWp")
                        st.write(f"- Total CAPEX: {excel_inputs.capex.total_capex:,.0f} k€")
                        st.write(f"- PPA Tariff: {excel_inputs.revenue.ppa_base_tariff:.0f} €/MWh")
                        st.write(f"- Gearing: {excel_inputs.financing.gearing_ratio:.0%}")
                        st.write(f"- Target DSCR: {excel_inputs.financing.target_dscr:.2f}x")
                    else:
                        st.error("❌ Failed to parse Excel file")
            else:
                st.warning(f"⚠️ File not found: {excel_path}")
    
    with col2:
        if st.button("📊 Generate Baseline", use_container_width=True):
            if hasattr(st.session_state, 'excel_inputs'):
                from io_.excel_integration import generate_baseline_json
                
                output_path = "/root/.openclaw/workspace/oborovo_model/tests/fixtures/oborovo_baseline.json"
                
                # Create directory if needed
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                generate_baseline_json(st.session_state.excel_inputs, output_path)
                st.success(f"✅ Baseline saved to {output_path}")
            else:
                st.warning("Parse Excel first")
    
    st.divider()
    
    # Compare section
    st.subheader("📊 Compare Model vs Excel")
    
    if hasattr(st.session_state, 'excel_inputs'):
        if st.button("🔍 Run Comparison", type="primary", use_container_width=True):
            with st.spinner("Comparing..."):
                report = compare_to_excel(
                    inputs,
                    excel_path,
                    tolerance_pct=tolerance,
                )
                
                st.session_state.parity_report = report
        
        if hasattr(st.session_state, 'parity_report'):
            report = st.session_state.parity_report
            
            st.divider()
            
            # Summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Metrics", f"{report.total_metrics}")
            with col2:
                st.metric("Within Tolerance", f"{report.metrics_within_tolerance}")
            with col3:
                st.metric("Max Deviation", f"{report.max_deviation_pct:.2f}%")
            
            st.divider()
            
            # Results table
            st.subheader("📋 Detailed Results")
            
            import pandas as pd
            
            data = []
            for r in report.results:
                data.append({
                    "Metric": r.metric_name,
                    "Excel": f"{r.excel_value:,.2f}",
                    "Python": f"{r.python_value:,.2f}",
                    "Diff": f"{r.difference:+,.2f}",
                    "Diff %": f"{r.difference_pct:.2f}%",
                    "Status": "✅" if r.within_tolerance else "❌",
                })
            
            df = pd.DataFrame(data)
            st.table(df.set_index("Metric"))
            
            st.divider()
            
            # Text report
            with st.expander("📄 Full Text Report"):
                st.text(print_parity_report(report))
    else:
        st.info("📂 Parse Excel file first to enable comparison")
    
    st.divider()
    
    # Quick check - compare current values to baseline
    st.subheader("🔬 Quick Baseline Check")
    
    baseline_path = "/root/.openclaw/workspace/oborovo_model/tests/fixtures/oborovo_baseline.json"
    
    if os.path.exists(baseline_path):
        if st.button("📊 Compare to Baseline", type="primary", use_container_width=True):
            import json
            
            with open(baseline_path, "r") as f:
                baseline = json.load(f)
            
            # Compare key metrics
            checks = []
            
            # CAPEX
            capex_diff = abs(inputs.capex.total_capex - baseline["capex"]["total_capex_keur"]) / baseline["capex"]["total_capex_keur"] * 100
            checks.append(("Total CAPEX", baseline["capex"]["total_capex_keur"], inputs.capex.total_capex, capex_diff))
            
            # Capacity
            cap_diff = abs(inputs.technical.capacity_mw - baseline["technical"]["capacity_mw"]) / baseline["technical"]["capacity_mw"] * 100
            checks.append(("Capacity", baseline["technical"]["capacity_mw"], inputs.technical.capacity_mw, cap_diff))
            
            # PPA Tariff
            tariff_diff = abs(inputs.revenue.ppa_base_tariff - baseline["revenue"]["ppa_base_tariff"]) / baseline["revenue"]["ppa_base_tariff"] * 100
            checks.append(("PPA Tariff", baseline["revenue"]["ppa_base_tariff"], inputs.revenue.ppa_base_tariff, tariff_diff))
            
            # Gearing
            gear_diff = abs(inputs.financing.gearing_ratio - baseline["financing"]["gearing_ratio"]) / baseline["financing"]["gearing_ratio"] * 100
            checks.append(("Gearing", baseline["financing"]["gearing_ratio"], inputs.financing.gearing_ratio, gear_diff))
            
            # Display
            data = []
            for name, baseline_val, current_val, diff_pct in checks:
                data.append({
                    "Metric": name,
                    "Baseline": f"{baseline_val:,.2f}",
                    "Current": f"{current_val:,.2f}",
                    "Diff %": f"{diff_pct:.2f}%",
                    "Status": "✅" if diff_pct <= tolerance else "❌",
                })
            
            df = pd.DataFrame(data)
            st.table(df.set_index("Metric"))
            
            all_ok = all(row[3]["Status"] == "✅" for row in data)
            if all_ok:
                st.success("✅ All metrics within tolerance!")
            else:
                st.warning("⚠️ Some metrics deviate from baseline")
    else:
        st.info(f"Baseline file not found: {baseline_path}")