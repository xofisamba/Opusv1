"""Projects page - Save, load, delete project configurations."""
import streamlit as st
from datetime import datetime

from io_.project_manager import (
    PROJECTS_DIR, save_project, load_project, list_projects, delete_project
)
from domain.presets import get_preset_projects, create_trebinje_solar, create_krnovo_wind


def render_projects(inputs, engine) -> None:
    st.header("📁 Project Management")
    
    s = st.session_state
    
    # Tab layout
    tab1, tab2, tab3 = st.tabs(["💾 Save Current", "📂 Load Project", "ℹ️ About"])
    
    with tab1:
        st.subheader("💾 Save Current Project")
        
        project_name = st.text_input(
            "Project Name",
            value=f"{s.project_name}",
            help="Name for this project configuration"
        )
        project_desc = st.text_area(
            "Description (optional)",
            value=f"{s.technology} project, {s.capacity_dc:.1f} MWp",
            help="Brief description",
        )
        
        if st.button("💾 Save Project", type="primary", width="stretch"):
            if project_name:
                try:
                    filepath = save_project(inputs, project_name, project_desc)
                    st.success(f"✅ Saved: {project_name}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save: {e}")
            else:
                st.warning("Enter a project name")
        
        st.divider()
        
        # Quick save presets
        st.subheader("💾 Quick Save Presets")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📁 Save Trebinje Solar", width="stretch"):
                trebinje = create_trebinje_solar()
                filepath = save_project(trebinje, "Trebinje Solar", "53.63 MWp solar, Bosnia")
                st.success(f"✅ Saved Trebinje Solar")
        
        with col2:
            if st.button("📁 Save Krnovo Wind", width="stretch"):
                krnovo = create_krnovo_wind()
                filepath = save_project(krnovo, "Krnovo Wind", "60 MW wind, Bosnia")
                st.success(f"✅ Saved Krnovo Wind")
    
    with tab2:
        st.subheader("📂 Load Project")
        
        # Section 1: User saved projects
        st.write("**📁 Your Saved Projects**")
        
        projects = list_projects()
        
        if not projects:
            st.info("No saved projects yet. Save a project first or load a preset below.")
        else:
            for proj in projects:
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.markdown(f"**{proj['name']}**")
                        st.caption(f"📄 {proj['filename']}")
                        created = proj['created_at'][:19] if proj['created_at'] else 'Unknown'
                        st.caption(f"🕐 {created}")
                        if proj['description']:
                            st.caption(f"📝 {proj['description']}")
                    
                    with col2:
                        if st.button("Load", key=f"load_{proj['filepath']}"):
                            data = load_project(proj['filepath'])
                            if data and 'inputs' in data:
                                _apply_inputs(data['inputs'])
                                st.success(f"✅ Loaded: {proj['name']}")
                            else:
                                st.error("Invalid project file")
                    
                    with col3:
                        if st.button("🗑️", key=f"del_{proj['filepath']}"):
                            if delete_project(proj['filepath']):
                                st.warning(f"Deleted: {proj['name']}")
                                st.rerun()
                            else:
                                st.error("Failed to delete")
        
        st.divider()
        
        # Section 2: Preset projects
        st.write("**🏭 Preset Projects (Templates)**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**Oborovo Solar**")
            st.caption("53.63 MWp | Croatia")
            st.caption("P50: 1,494 hrs | 65 €/MWh")
            if st.button("📂 Load Oborovo", width="stretch"):
                st.info("Oborovo is your current project")
        
        with col2:
            st.markdown("**Trebinje Solar**")
            st.caption("53.63 MWp | Bosnia")
            st.caption("P50: 1,536 hrs | 65 €/MWh")
            if st.button("📂 Load Trebinje", width="stretch"):
                trebinje = create_trebinje_solar()
                _apply_inputs(trebinje)
                st.success("✅ Loaded Trebinje Solar")
        
        with col3:
            st.markdown("**Krnovo Wind**")
            st.caption("60 MW | Bosnia")
            st.caption("P50: 2,500 hrs | 55 €/MWh")
            if st.button("📂 Load Krnovo", width="stretch"):
                krnovo = create_krnovo_wind()
                _apply_inputs(krnovo)
                st.success("✅ Loaded Krnovo Wind")
    
    with tab3:
        st.subheader("ℹ️ About Projects")
        
        st.markdown(f"""
        **Projects folder:** `{PROJECTS_DIR}`
        
        **Project file format:**
        ```json
        {{
          "name": "My Project",
          "description": "Solar project v1",
          "created_at": "2026-04-20T14:30:00",
          "version": "1.0",
          "inputs": {{ ... }}
        }}
        ```
        """)
        
        st.divider()
        
        st.subheader("Current Configuration")
        
        config_items = [
            ("Project Name", s.project_name),
            ("Technology", s.technology),
            ("Capacity DC", f"{s.capacity_dc:.2f} MWp"),
            ("PPA Tariff", f"{s.ppa_base_tariff:.0f} €/MWh"),
            ("PPA Term", f"{s.ppa_term} years"),
            ("Gearing", f"{s.gearing_ratio:.0%}"),
            ("Target DSCR", f"{s.target_dscr:.2f}x"),
            ("Investment Horizon", f"{s.investment_horizon} years"),
        ]
        
        for label, value in config_items:
            st.markdown(f"- **{label}:** {value}")


def _apply_inputs(proj_inputs) -> None:
    """Apply ProjectInputs to session state.
    
    Note: We only update s.inputs. The sidebar will read from inputs
    on next render. We avoid setting st.session_state values directly
    because Streamlit doesn't allow modifying widget keys after instantiation.
    """
    s = st.session_state
    
    # Only update the inputs - sidebar reads from inputs, not from individual keys
    s.inputs = proj_inputs


def render_export_import(inputs, engine) -> None:
    """Export/Import functionality."""
    st.header("📤 Export / Import")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Export")
        
        export_name = st.text_input("Export filename", value="project_export.json")
        
        if st.button("📥 Export to JSON"):
            try:
                from io_.project_manager import export_to_json
                path = export_to_json(inputs, f"/root/.openclaw/workspace/{export_name}")
                st.success(f"Exported to: {path}")
            except Exception as e:
                st.error(f"Export failed: {e}")
    
    with col2:
        st.subheader("Import")
        
        uploaded = st.file_uploader("Choose JSON file", type="json")
        
        if uploaded:
            if st.button("📤 Import"):
                try:
                    import json
                    data = json.load(uploaded)
                    if 'inputs' in data:
                        st.success("Imported! Click 'Update Model' to apply.")
                    else:
                        st.warning("Invalid project file format")
                except Exception as e:
                    st.error(f"Import failed: {e}")