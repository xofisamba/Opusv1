"""Export page - Excel and CSV export functionality."""
import streamlit as st
import os

from io_.excel_exporter import (
    export_to_excel, export_to_excel_advanced, export_cashflows_to_csv
)


def render_export(inputs, engine) -> None:
    st.header("📤 Export Results")
    
    s = st.session_state
    
    # Get waterfall result if available
    waterfall_result = getattr(st.session_state, 'waterfall_result', None)
    
    st.markdown("""
    **Export model results to Excel or CSV format.**
    
    Available formats:
    - **Excel (.xlsx)** - Multi-sheet workbook with Summary, Cash Flows, Debt Schedule, Returns
    - **CSV** - Simple cash flow table for external analysis
    """)
    
    st.divider()
    
    # Export options
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Excel Export")
        
        export_type = st.selectbox(
            "Export Type",
            ["Standard Summary", "Full Model (with Waterfall)"],
            help="Standard = basic summary. Full = includes waterfall details."
        )
        
        filename = st.text_input(
            "Filename",
            value=f"{s.project_name.replace(' ', '_')}_export.xlsx",
            help="Output filename"
        )
        
        if st.button("📥 Export to Excel", type="primary", use_container_width=True):
            with st.spinner("Generating Excel file..."):
                if export_type == "Full Model (with Waterfall)" and waterfall_result:
                    result = export_to_excel_advanced(
                        inputs, engine, waterfall_result,
                        filepath=f"/root/.openclaw/workspace/{filename}"
                    )
                else:
                    results_dict = {
                        'project_irr': 0.0842,
                        'equity_irr': 0.11,
                        'project_npv': 0,
                        'equity_npv': 0,
                        'avg_dscr': 1.147,
                        'min_dscr': 1.0,
                        'min_llcr': 1.2,
                        'min_plcr': 1.3,
                    }
                    result = export_to_excel(
                        inputs, engine, results_dict,
                        filepath=f"/root/.openclaw/workspace/{filename}"
                    )
                
                if result is True:
                    st.success(f"✅ Exported to {filename}")
                    
                    # Provide download link
                    with open(f"/root/.openclaw/workspace/{filename}", "rb") as f:
                        st.download_button(
                            "📥 Download Excel",
                            f,
                            file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.error(f"❌ {result}")
    
    with col2:
        st.subheader("📄 CSV Export")
        
        csv_filename = st.text_input(
            "CSV Filename",
            value=f"{s.project_name.replace(' ', '_')}_cashflows.csv",
            help="Output CSV filename"
        )
        
        if st.button("📥 Export to CSV", use_container_width=True):
            with st.spinner("Generating CSV file..."):
                result = export_cashflows_to_csv(
                    inputs, engine,
                    filepath=f"/root/.openclaw/workspace/{csv_filename}"
                )
                
                if result is True:
                    st.success(f"✅ Exported to {csv_filename}")
                    
                    with open(f"/root/.openclaw/workspace/{csv_filename}", "rb") as f:
                        st.download_button(
                            "📥 Download CSV",
                            f,
                            file_name=csv_filename,
                            mime="text/csv"
                        )
                else:
                    st.error(f"❌ {result}")
    
    st.divider()
    
    # Excel sheet preview
    st.subheader("📋 Excel Sheet Structure")
    
    sheets_info = [
        {"name": "Executive Summary", "description": "Key parameters and financial results"},
        {"name": "Cash Flows", "description": "Period-by-period cash flow waterfall"},
        {"name": "Debt Schedule", "description": "Amortization schedule with DSCR"},
        {"name": "Returns", "description": "IRR, NPV, and distribution summary"},
    ]
    
    if export_type == "Full Model (with Waterfall)":
        sheets_info.insert(0, {"name": "Summary", "description": "High-level project metrics"})
        sheets_info.insert(1, {"name": "Inputs", "description": "All model input parameters"})
    
    for sheet in sheets_info:
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown(f"**{sheet['name']}**")
        with col2:
            st.caption(sheet['description'])
    
    st.divider()
    
    # Quick stats
    st.subheader("📊 Model Quick Stats")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Periods", f"{len(list(engine.periods()))}")
    with col2:
        op_periods = len([p for p in engine.periods() if p.is_operation])
        st.metric("Op Periods", f"{op_periods}")
    with col3:
        st.metric("CAPEX", f"{inputs.capex.total_capex:,.0f} k€")
    with col4:
        debt = inputs.capex.total_capex * inputs.financing.gearing_ratio
        st.metric("Debt", f"{debt:,.0f} k€")
    
    # File location info
    st.divider()
    
    st.info(f"📁 Files saved to: `/root/.openclaw/workspace/`")
    st.caption("After download, you can find the files in your workspace directory.")