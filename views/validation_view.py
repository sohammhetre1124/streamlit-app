"""
Validation view – replicates the React ValidationView component.
Shows KPI cards, rules table, metrics tables, issues table, and Q&A section.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services.data_validation import DataValidationService


# ---------------------------------------------------------------------------
#  KPI metric cards
# ---------------------------------------------------------------------------

def _render_kpi_cards(validation: Dict) -> None:
    kpis = validation.get('kpis', {})
    metrics = validation.get('metrics', {})
    summary = validation.get('summary', {})

    status = summary.get('status', 'UNKNOWN')
    status_color = '#27AE60' if status == 'VALID' else '#E74C3C'

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Resources", f"{kpis.get('totalResources', 0):,}")
    with col2:
        pct = kpis.get('validRecordPct', 0)
        st.metric("Valid Records", f"{pct:.1f}%",
                  delta=f"{pct - 100:.1f}%" if pct < 100 else None,
                  delta_color='inverse')
    with col3:
        issues = kpis.get('issuesFound', 0)
        st.metric("Issues Found", f"{issues:,}",
                  delta=f"{-issues} issues" if issues > 0 else "Clean",
                  delta_color='inverse')
    with col4:
        active = metrics.get('activeResources', 0)
        inactive = metrics.get('inactiveResources', 0)
        st.metric("Active / Inactive", f"{active} / {inactive}")

    # Status banner
    reasons = (validation.get('summary') or {}).get('invalidationReasons') or []
    if status == 'VALID':
        st.success("Data is **VALID** for further analysis.")
    else:
        reason_text = ' · '.join(r.get('reason', '') for r in reasons)
        st.error(f"Data is **NOT VALID** for further analysis. {reason_text}")


# ---------------------------------------------------------------------------
#  Rules table
# ---------------------------------------------------------------------------

def _render_rules(validation: Dict) -> None:
    st.subheader("Validation Rules")
    rules = validation.get('rules', [])
    if not rules:
        st.info("No rules data available.")
        return

    for rule in rules:
        status = rule.get('status', 'UNKNOWN')
        icon = '✅' if status == 'PASS' else '❌'
        count = rule.get('violationCount', 0)
        label = rule.get('label', rule.get('id', ''))

        with st.expander(f"{icon} {label}  ({count} violations)", expanded=(status == 'FAIL')):
            defn = rule.get('definition') or {}
            if defn.get('description'):
                st.caption(defn['description'])

            sample = rule.get('sample', [])
            if sample:
                st.markdown("**Sample violations:**")
                # Flatten sample to a simple table
                rows = []
                for item in sample[:10]:
                    if isinstance(item, dict):
                        rows.append({
                            'Resource Key': item.get('resourceKey') or item.get('resourceEmail') or '',
                            'Resource Name': item.get('resourceName') or item.get('name') or '',
                            'Division': item.get('division') or '',
                            'Detail': (', '.join(str(v) for v in item.get('divisions', [])))
                                      or item.get('message') or '',
                        })
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No violations.")


# ---------------------------------------------------------------------------
#  Metrics tables
# ---------------------------------------------------------------------------

def _render_metrics(validation: Dict) -> None:
    st.subheader("Data Metrics")
    metrics = validation.get('metrics', {})
    analytics = validation.get('analytics', {})

    tab1, tab2, tab3, tab4 = st.tabs(
        ["By Location", "By Division", "Timesheet Coverage", "Capacity Foundation"])

    with tab1:
        by_loc = metrics.get('totalDistinctResourcesByLocation', {})
        if by_loc:
            df = pd.DataFrame(
                [{'Location': k, 'Resources': v} for k, v in by_loc.items()]
            ).sort_values('Resources', ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No location data.")

    with tab2:
        by_div = metrics.get('totalResourcesPerDivision', {})
        div_status = analytics.get('resourcesByDivisionAndStatus', {})
        if by_div:
            rows = []
            for div, total in sorted(by_div.items(), key=lambda x: -x[1]):
                s = div_status.get(div, {})
                rows.append({
                    'Division': div,
                    'Total': total,
                    'Active': s.get('Active', 0),
                    'Inactive': s.get('Inactive', 0),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No division data.")

    with tab3:
        meeting = metrics.get('resourcesAppearingInTimesheets', 0)
        missing = metrics.get('resourcesNotAppearingInTimesheets', 0)
        total = meeting + missing
        col1, col2, col3 = st.columns(3)
        col1.metric("Meeting 40h/week", meeting)
        col2.metric("Not meeting 40h/week", missing)
        col3.metric("Coverage", f"{meeting / total * 100:.1f}%" if total else "N/A")

    with tab4:
        cap = metrics.get('capacityFoundation', {})
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Resources (Proxy)", cap.get('totalResourcesProxyForCapacity', 0))
        col2.metric("With Onboarding Date", cap.get('resourcesWithOnboardingDate', 0))
        col3.metric("Missing Onboarding Date", cap.get('resourcesMissingOnboardingDate', 0))


# ---------------------------------------------------------------------------
#  Issues table
# ---------------------------------------------------------------------------

def _render_issues_table(validation: Dict) -> None:
    st.subheader("Data Quality Issues")
    issues = validation.get('issues', [])
    breakdown = validation.get('violationTypeBreakdown', {})

    if not issues:
        st.success("No data quality issues found.")
        return

    # Filter by violation type
    types = ['All'] + sorted(breakdown.keys())
    selected_type = st.selectbox(
        f"Filter by violation type ({len(issues):,} total issues)",
        options=types,
        key='issue_type_filter',
    )

    filtered = issues if selected_type == 'All' else [
        i for i in issues if i.get('type') == selected_type
    ]

    rows = []
    for issue in filtered[:200]:
        rows.append({
            'Type': issue.get('type', ''),
            'Sheet': issue.get('sheet', ''),
            'Row #': issue.get('rowNumber') or '',
            'Resource Key': issue.get('resourceKey', ''),
            'Message': issue.get('message', ''),
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True, height=350)
        if len(filtered) > 200:
            st.caption(f"Showing first 200 of {len(filtered):,} issues.")
    else:
        st.info("No issues for this filter.")


# ---------------------------------------------------------------------------
#  Resource inventory
# ---------------------------------------------------------------------------

def _render_resource_inventory(validation: Dict) -> None:
    inventory = (validation.get('analytics') or {}).get('resourceInventory', [])
    if not inventory:
        return

    with st.expander(f"Resource Inventory ({len(inventory):,} resources)", expanded=False):
        search = st.text_input("Search inventory", key="inv_search")
        rows = [
            {
                'Resource Name': r.get('resourceName', ''),
                'Division': r.get('division', ''),
                'Location': r.get('location', ''),
                'Work Type': r.get('resourceWorkType', ''),
                'Status': r.get('status', ''),
                'Timecard Rows': r.get('timecardCount', 0),
                'Meets 40h': '✓' if r.get('meetsFortyHourWeekThreshold') else '✗',
                'Issues': r.get('issueCount', 0),
            }
            for r in inventory
        ]
        df = pd.DataFrame(rows)
        if search:
            mask = (
                df['Resource Name'].str.contains(search, case=False, na=False) |
                df['Division'].str.contains(search, case=False, na=False)
            )
            df = df[mask]
        st.dataframe(df, use_container_width=True, hide_index=True, height=350)


# ---------------------------------------------------------------------------
#  Q&A section
# ---------------------------------------------------------------------------

def _render_qa_section(validation: Dict, validator: DataValidationService) -> None:
    st.subheader("Ask a Question about the Data")

    suggested = [
        "How many total resources are there?",
        "Are there any duplicate resources?",
        "Do any resources belong to multiple divisions?",
        "Which division has the most issues?",
        "How many resources are not appearing in timesheets?",
    ]

    # Suggested question buttons
    st.caption("Suggested questions:")
    cols = st.columns(len(suggested))
    chosen_suggested = None
    for i, q in enumerate(suggested):
        if cols[i].button(q[:40] + '…' if len(q) > 40 else q,
                          key=f"sugg_{i}", use_container_width=True):
            chosen_suggested = q

    groq_key = st.session_state.get('groq_api_key', '')

    question = st.text_area(
        "Or type your question here:",
        value=chosen_suggested or st.session_state.get('_qa_question', ''),
        key='qa_question_input',
        height=80,
    )
    if chosen_suggested:
        st.session_state['_qa_question'] = chosen_suggested

    if st.button("Ask", key="qa_ask_btn", type="primary"):
        if question.strip():
            with st.spinner("Answering…"):
                answer = validator.ask_with_groq(question, validation, groq_key)
            st.info(f"**Answer:** {answer}")
        else:
            st.warning("Please enter a question.")


# ---------------------------------------------------------------------------
#  Main renderer
# ---------------------------------------------------------------------------

def render_validation_view(
    validation: Optional[Dict],
    validator: Optional[DataValidationService],
) -> None:
    if validation is None:
        st.info("Validation data not yet computed.")
        if st.button("Run Validation", key="run_validation_btn"):
            st.rerun()
        return

    _render_kpi_cards(validation)
    st.divider()
    _render_rules(validation)
    st.divider()
    _render_metrics(validation)
    st.divider()
    _render_issues_table(validation)
    st.divider()
    _render_resource_inventory(validation)
    st.divider()
    if validator:
        _render_qa_section(validation, validator)
