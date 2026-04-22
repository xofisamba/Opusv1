"""Demonstration of Pydantic validation with Streamlit error display.

This module shows how to:
1. Catch ValidationError from Pydantic models
2. Display user-friendly error messages in Streamlit
3. Export model to JSON for "Save Scenario" functionality
"""
import streamlit as st
from datetime import date
from pydantic import ValidationError

from src.core.models.project import ProjectInfo, create_project_info


def show_validation_errors(exc: ValidationError) -> None:
    """Convert Pydantic ValidationError to user-friendly Streamlit error messages.
    
    Args:
        exc: Pydantic ValidationError instance
    """
    st.error("⚠️ Neispravni podaci za projekt:") if True else None
    for error in exc.errors():
        loc = " → ".join(str(l) for l in error["loc"])
        msg = error["msg"]
        
        # Map to user-friendly HR messages
        if msg.startswith("Input should be greater than"):
            friendly_msg = "Iznos mora biti veći od nule."
        elif msg.startswith("Input should be less than"):
            friendly_msg = "Iznos mora biti manji od nule."
        elif msg.startswith("Input should be between"):
            ctx = error.get("ctx", {})
            friendly_msg = f"Vrijednost mora biti između {ctx.get('ge', 0)} i {ctx.get('le', 0)}."
        elif msg.startswith("Field required"):
            friendly_msg = f"Polje '{loc}' je obavezno."
        elif "country" in loc.lower():
            friendly_msg = "ISO kod mora biti točno 2 velika slova (npr. 'HR', 'DE')."
        elif "date" in loc.lower():
            friendly_msg = "Neispravan format datuma. Koristite YYYY-MM-DD."
        else:
            friendly_msg = msg
        
        st.error(f"  • {friendly_msg} (polje: {loc})")


def render_project_form() -> ProjectInfo | None:
    """Render project info form with Pydantic validation.
    
    Returns:
        Validated ProjectInfo instance or None if validation fails
    """
    with st.expander("📐 Project Info", expanded=True):
        name = st.text_input("Project Name", value="Oborovo Solar PV")
        company = st.text_input("Company", value="AKE Med")
        
        col1, col2 = st.columns(2)
        with col1:
            ff_date = st.date_input("Financial Close", value=date(2029, 6, 29))
        with col2:
            cod_date = st.date_input("COD Date", value=date(2030, 6, 29))
        
        col3, col4 = st.columns(2)
        with col3:
            country = st.text_input("Country ISO", value="HR", max_chars=2).upper()
        with col4:
            horizon = st.number_input("Horizon (years)", min_value=10, max_value=50, value=30)
        
        months = st.number_input("Construction (months)", min_value=1, max_value=60, value=12)
        
        freq = st.selectbox(
            "Period Frequency",
            options=["Semestrial", "Annual", "Quarterly"],
            index=0
        )

        if st.button("Validate Project", type="primary"):
            try:
                project = ProjectInfo(
                    name=name,
                    company=company,
                    country_iso=country,
                    financial_close=ff_date,
                    construction_months=months,
                    cod_date=cod_date,
                    horizon_years=horizon,
                    period_frequency=freq,
                )
                st.success("✅ Projekt je validiran!")
                return project
            except ValidationError as exc:
                show_validation_errors(exc)
                return None
    
    return None


def demo_json_export(project: ProjectInfo) -> None:
    """Demonstrate JSON export for Save Scenario functionality."""
    st.subheader("📤 JSON Export (za Save Scenario)")
    
    json_data = project.to_json_dict()
    
    col1, col2 = st.columns(2)
    with col1:
        st.json(json_data)
    with col2:
        st.code(f"await save_scenario({json_data})", language="python")


# =============================================================================
# Standalone demo app
# =============================================================================
def main():
    st.set_page_config(
        page_title="Pydantic Validation Demo",
        page_icon="🧪",
        layout="wide"
    )
    
    st.title("🧪 Pydantic Validation Demo")
    st.caption("Testiraj validaciju s korisničkim porukama")
    
    project = render_project_form()
    
    if project is not None:
        st.divider()
        demo_json_export(project)
    
    st.divider()
    st.subheader("📋 Test validacije - pokušaj unijeti nevalidne vrijednosti:")
    
    with st.expander("❌ Primjer greške - prekratak country code"):
        try:
            bad_project = ProjectInfo(
                name="Test",
                company="Test Co",
                country_iso="H",  # ❌ Should fail - only 1 char
                financial_close=date(2029, 6, 29),
                construction_months=12,
                cod_date=date(2030, 6, 29),
                horizon_years=30,
                period_frequency="Semestrial",
            )
        except ValidationError as exc:
            show_validation_errors(exc)
    
    with st.expander("❌ Primjer greške - negativan horizon"):
        try:
            bad_project = ProjectInfo(
                name="Test",
                company="Test Co",
                country_iso="HR",
                financial_close=date(2029, 6, 29),
                construction_months=12,
                cod_date=date(2030, 6, 29),
                horizon_years=5,  # ❌ Should fail - min is 10
                period_frequency="Semestrial",
            )
        except ValidationError as exc:
            show_validation_errors(exc)


if __name__ == "__main__":
    main()
