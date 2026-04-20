"""CAPEX page."""
import streamlit as st
from domain.capex.spending_profile import spending_profile_summary


def render_capex_page(inputs, engine):
    st.header("🏗️ CAPEX Structure")
    
    capex = inputs.capex
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Hard CAPEX", f"{capex.hard_capex_keur:,.0f} k€")
    with col2:
        st.metric("IDC", f"{capex.idc_keur:,.0f} k€")
    with col3:
        st.metric("Fees & Other", f"{capex.commitment_fees_keur + capex.bank_fees_keur:,.0f} k€")
    with col4:
        st.metric("Total CAPEX", f"{capex.total_capex:,.0f} k€")
    
    st.divider()
    
    # CAPEX breakdown
    st.subheader("Hard CAPEX Items")
    
    items_data = [
        ("EPC Contract", capex.epc_contract.amount_keur),
        ("Production Units", capex.production_units.amount_keur),
        ("Grid Connection", capex.grid_connection.amount_keur),
        ("Project Rights", capex.project_rights.amount_keur),
        ("Contingencies", capex.contingencies.amount_keur),
        ("Construction Mgmt", capex.construction_mgmt_a.amount_keur + capex.construction_mgmt_b.amount_keur),
        ("Commissioning", capex.commissioning.amount_keur),
        ("Other", capex.epc_other.amount_keur + capex.ops_prep.amount_keur + 
                 capex.lease_tax.amount_keur + capex.insurances.amount_keur +
                 capex.audit_legal.amount_keur + capex.taxes.amount_keur +
                 capex.project_acquisition.amount_keur),
    ]
    
    total_hard = sum(x[1] for x in items_data)
    
    data = []
    for name, amount in items_data:
        pct = amount / total_hard * 100 if total_hard > 0 else 0
        data.append({
            "Item": name,
            "Amount (k€)": f"{amount:,.0f}",
            "Share": f"{pct:.1f}%",
        })
    
    st.table(data)
    
    st.divider()
    
    # Spending profile
    st.subheader("Spending Profile by Year")
    
    items = [
        capex.epc_contract, capex.production_units, capex.epc_other,
        capex.grid_connection, capex.contingencies, capex.project_rights
    ]
    
    profile = spending_profile_summary(items)
    
    data = []
    for year in range(5):
        amount = profile.get(year, 0)
        data.append({
            "Year": f"Y{year}" if year > 0 else "Y0",
            "CAPEX (k€)": f"{amount:,.0f}",
        })
    
    st.table(data)
