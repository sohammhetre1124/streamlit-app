"""
Assumptions view – replicates the React AssumptionsPanel component.
Groups all 21 assumptions by category with expandable sections and export buttons.
"""
from __future__ import annotations

import streamlit as st

from config.assumptions import get_assumptions, get_assumptions_by_category
from services.export_service import generate_assumptions_csv, generate_assumptions_excel


def render_assumptions_view() -> None:
    st.subheader("Business Assumptions")
    st.caption(
        "All assumptions used in this analysis. "
        "These document the business rules, data definitions, and calculation methods."
    )

    # Export buttons
    col1, col2 = st.columns([1, 1])
    with col1:
        assumptions = get_assumptions()
        csv_data = generate_assumptions_csv(assumptions)
        st.download_button(
            label="Export as CSV",
            data=csv_data,
            file_name="assumptions.csv",
            mime="text/csv",
            key="dl_assumptions_csv",
        )
    with col2:
        xlsx_buf = generate_assumptions_excel(assumptions)
        st.download_button(
            label="Export as Excel",
            data=xlsx_buf,
            file_name="assumptions.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_assumptions_xlsx",
        )

    st.divider()

    grouped = get_assumptions_by_category()

    for category, items in grouped.items():
        with st.expander(f"**{category}** ({len(items)} assumption{'s' if len(items) > 1 else ''})",
                         expanded=False):
            for a in items:
                st.markdown(f"### {a['assumption']}")
                st.markdown(f"**Description:** {a['description']}")
                st.markdown(f"**Business Impact:** {a['businessImpact']}")
                st.divider()
