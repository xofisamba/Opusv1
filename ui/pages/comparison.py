"""Comparison page - Compare multiple project configurations."""
import streamlit as st
import pandas as pd

from domain.presets import get_preset_projects, create_trebinje_solar, create_krnovo_wind


def render_comparison(inputs, engine) -> None:
    st.header("📊 Project Comparison")
    
    st.markdown("""
    **Compare up to 3 projects side-by-side:**
    - **Oborovo Solar** - Current project from session
    - **Trebinje Solar** - 53.63 MWp solar in Bosnia  
    - **Krnovo Wind** - 60 MW wind in Bosnia
    """)
    
    st.divider()
    
    # Get preset projects
    presets = get_preset_projects()
    
    # Build comparison table
    projects = [
        ("Oborovo Solar", inputs),
        ("Trebinje Solar", presets["Trebinje Solar"]),
        ("Krnovo Wind", presets["Krnovo Wind"]),
    ]
    
    comparison_data = []
    
    for name, proj in projects:
        if proj is None:
            proj = inputs  # Current session state for Oborovo
        
        # Calculate key metrics
        total_capex = proj.capex.total_capex
        cap_mw = proj.technical.capacity_mw
        hours = proj.technical.operating_hours_p50
        tariff = proj.revenue.ppa_base_tariff
        gearing = proj.financing.gearing_ratio
        dscr = proj.financing.target_dscr
        tenor = proj.financing.senior_tenor_years
        
        # Revenue Y1
        gen_y1 = cap_mw * hours * 0.99 / 1000  # MWh
        rev_y1 = gen_y1 * tariff
        
        # OPEX Y1
        opex_y1 = sum(item.y1_amount_keur for item in proj.opex)
        
        # EBITDA
        ebitda_y1 = rev_y1 - opex_y1
        
        # Debt & Equity
        debt = total_capex * gearing
        equity = total_capex - debt
        
        # LCOE (simplified)
        opex_total = sum(item.y1_amount_keur * (1.02 ** i) for i in range(30) for item in proj.opex) / 30
        lcoe = (total_capex + opex_total * 15) / (cap_mw * hours * 29.5) if hours > 0 else 0
        
        comparison_data.append({
            "Project": name,
            "Technology": "Solar" if "Solar" in name else "Wind",
            "Capacity (MWp)": f"{cap_mw:.1f}",
            "P50 Yield (hrs)": f"{hours:.0f}",
            "PPA Tariff (€/MWh)": f"{tariff:.0f}",
            "Total CAPEX (k€)": f"{total_capex:,.0f}",
            "CAPEX/MW (k€)": f"{total_capex / cap_mw:,.0f}",
            "Revenue Y1 (k€)": f"{rev_y1:,.0f}",
            "OPEX Y1 (k€)": f"{opex_y1:,.0f}",
            "EBITDA Y1 (k€)": f"{ebitda_y1:,.0f}",
            "EBITDA Margin": f"{ebitda_y1 / rev_y1 * 100:.0f}%" if rev_y1 > 0 else "—",
            "Gearing": f"{gearing:.0%}",
            "Debt (k€)": f"{debt:,.0f}",
            "Equity (k€)": f"{equity:,.0f}",
            "Target DSCR": f"{dscr:.2f}x",
            "Debt Tenor": f"{tenor}y",
            "LCOE (€/MWh)": f"{lcoe:.1f}" if lcoe > 0 else "—",
        })
    
    df = pd.DataFrame(comparison_data)
    
    st.subheader("📋 Key Metrics Comparison")
    st.table(df.set_index("Project"))
    
    st.divider()
    
    # Charts
    st.subheader("📊 Visual Comparison")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write("**Capacity (MWp)**")
        cap_data = pd.DataFrame({
            "Project": [d["Project"] for d in comparison_data],
            "MWp": [float(d["Capacity (MWp)"]) for d in comparison_data],
        }).set_index("Project")
        st.bar_chart(cap_data)
    
    with col2:
        st.write("**Total CAPEX (k€)**")
        capex_data = pd.DataFrame({
            "Project": [d["Project"] for d in comparison_data],
            "k€": [float(d["Total CAPEX (k€)"].replace(",", "")) for d in comparison_data],
        }).set_index("Project")
        st.bar_chart(capex_data)
    
    with col3:
        st.write("**EBITDA Y1 (k€)**")
        ebitda_data = pd.DataFrame({
            "Project": [d["Project"] for d in comparison_data],
            "k€": [float(d["EBITDA Y1 (k€)"].replace(",", "")) for d in comparison_data],
        }).set_index("Project")
        st.bar_chart(ebitda_data)
    
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Revenue Y1 (k€)**")
        rev_data = pd.DataFrame({
            "Project": [d["Project"] for d in comparison_data],
            "k€": [float(d["Revenue Y1 (k€)"].replace(",", "")) for d in comparison_data],
        }).set_index("Project")
        st.bar_chart(rev_data)
    
    with col2:
        st.write("**LCOE (€/MWh)**")
        lcoe_data = pd.DataFrame({
            "Project": [d["Project"] for d in comparison_data],
            "€/MWh": [float(d["LCOE (€/MWh)"]) if d["LCOE (€/MWh)"] not in ("—", "N/A") else 0 for d in comparison_data],
        }).set_index("Project")
        st.bar_chart(lcoe_data)
    
    st.divider()
    
    # Financing comparison
    st.subheader("🏦 Financing Comparison")
    
    fin_data = []
    for d in comparison_data:
        fin_data.append({
            "Project": d["Project"],
            "Gearing": d["Gearing"],
            "Debt (k€)": d["Debt (k€)"],
            "Equity (k€)": d["Equity (k€)"],
            "DSCR": d["Target DSCR"],
            "Tenor": d["Debt Tenor"],
        })
    
    st.table(pd.DataFrame(fin_data).set_index("Project"))
    
    st.divider()
    
    # Technology breakdown
    st.subheader("⚡ Technology Metrics")
    
    tech_data = []
    for d in comparison_data:
        cap = float(d["Capacity (MWp)"])
        hours = float(d["P50 Yield (hrs)"])
        tariff = float(d["PPA Tariff (€/MWh)"])
        
        tech_data.append({
            "Project": d["Project"],
            "Technology": d["Technology"],
            "Capacity": d["Capacity (MWp)"],
            "Yield Hours": d["P50 Yield (hrs)"],
            "Tariff": d["PPA Tariff (€/MWh)"],
            "Gen Y1 (GWh)": f"{cap * hours / 1000:.1f}",
            "Revenue/MW": f"{float(d['Revenue Y1 (k€)'].replace(',', '')) / cap / 1000:.1f}k€/MW",
        })
    
    st.table(pd.DataFrame(tech_data).set_index("Project"))
    
    st.divider()
    
    # Load project button
    st.subheader("💾 Load Project for Editing")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📂 Load Oborovo", width="stretch"):
            st.info("Oborovo Solar is your current project. Go to 📁 Projects tab to load it.")
    
    with col2:
        if st.button("📂 Load Trebinje Solar", width="stretch"):
            trebinje = create_trebinje_solar()
            st.session_state.inputs = trebinje
            st.success("✅ Loaded Trebinje Solar! Go to Dashboard and click '🔄 Update Model'.")
    
    with col3:
        if st.button("📂 Load Krnovo Wind", width="stretch"):
            krnovo = create_krnovo_wind()
            st.session_state.inputs = krnovo
            st.success("✅ Loaded Krnovo Wind! Go to Dashboard and click '🔄 Update Model'.")