"""
Overview view – replicates the React OverviewChart component.
Stacked bar chart showing all divisions combined per quarter,
with capacity and adjusted-capacity lines.
"""
from __future__ import annotations

from typing import Dict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.date_utils import get_period_label, sort_periods, is_period_complete, is_period_in_progress
from utils.chart_utils import get_division_color


def _build_overview_chart(
    aggregated_df: pd.DataFrame,
    admin_stats: Dict,
    settings,
    display_mode: str,
    show_labels: bool,
) -> go.Figure:
    if aggregated_df.empty:
        return go.Figure()

    periods = sort_periods(aggregated_df['period'].unique().tolist())
    x_labels = [get_period_label(p) for p in periods]
    divisions = sorted(aggregated_df['division'].unique().tolist())

    fig = go.Figure()

    # Stacked bars per division
    for div_idx, division in enumerate(divisions):
        div_data = aggregated_df[aggregated_df['division'] == division]
        color = get_division_color(division, div_idx)

        y_vals = []
        for p in periods:
            period_rows = div_data[div_data['period'] == p]
            if display_mode == 'ftes':
                y_vals.append(period_rows['load_ftes'].sum())
            else:
                y_vals.append(period_rows['total_load_hours'].sum())

        fig.add_trace(go.Bar(
            x=x_labels,
            y=y_vals,
            name=division,
            marker_color=color,
            hovertemplate=f'<b>{division}</b><br>%{{x}}<br>Value: %{{y:.2f}}<extra></extra>',
        ))

    # Total capacity line (sum across all divisions)
    y_total_cap = []
    y_total_adj_cap = []

    for p in periods:
        period_rows = aggregated_df[aggregated_df['period'] == p]
        if display_mode == 'ftes':
            total_cap = period_rows['capacity_ftes'].sum()
        else:
            total_cap = period_rows['total_standard_hours'].sum()

        # Adjusted: per-division admin %
        adj_cap = 0.0
        for division in divisions:
            div_rows = period_rows[period_rows['division'] == division]
            if display_mode == 'ftes':
                div_cap = div_rows['capacity_ftes'].sum()
            else:
                div_cap = div_rows['total_standard_hours'].sum()
            auto_pct = (admin_stats.get(division) or {}).get('auto_admin_pct', 0.0)
            eff_pct = settings.get_effective_admin_pct(division, auto_pct)
            adj_cap += div_cap * (1 - eff_pct / 100)

        y_total_cap.append(total_cap)
        y_total_adj_cap.append(adj_cap)

    fig.add_trace(go.Scatter(
        x=x_labels,
        y=y_total_cap,
        name='Total Capacity',
        mode='lines+markers',
        line=dict(color='#27AE60', width=2),
        marker=dict(size=7),
        hovertemplate='<b>%{x}</b><br>Capacity: %{y:.2f}<extra></extra>',
    ))

    fig.add_trace(go.Scatter(
        x=x_labels,
        y=y_total_adj_cap,
        name='Total Adj. Capacity',
        mode='lines+markers',
        line=dict(color='#8E44AD', width=2, dash='dash'),
        marker=dict(size=7),
        hovertemplate='<b>%{x}</b><br>Adj. Capacity: %{y:.2f}<extra></extra>',
    ))

    y_label = 'FTEs' if display_mode == 'ftes' else 'Hours'
    fig.update_layout(
        barmode='stack',
        height=450,
        margin=dict(l=50, r=20, t=30, b=60),
        legend=dict(
            orientation='h', yanchor='bottom', y=-0.35, xanchor='center', x=0.5,
            font=dict(size=11),
        ),
        xaxis_title='Period',
        yaxis_title=y_label,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(gridcolor='rgba(128,128,128,0.3)'),
        xaxis=dict(gridcolor='rgba(128,128,128,0.3)'),
    )
    return fig


def _build_summary_table(
    aggregated_df: pd.DataFrame,
    admin_stats: Dict,
    settings,
    display_mode: str,
) -> pd.DataFrame:
    """Period-wise summary table across all divisions."""
    periods = sort_periods(aggregated_df['period'].unique().tolist())
    rows = []

    for p in periods:
        period_rows = aggregated_df[aggregated_df['period'] == p]
        total_load = (period_rows['load_ftes'].sum() if display_mode == 'ftes'
                      else period_rows['total_load_hours'].sum())
        total_cap = (period_rows['capacity_ftes'].sum() if display_mode == 'ftes'
                     else period_rows['total_standard_hours'].sum())

        adj_cap = 0.0
        for division in period_rows['division'].unique():
            div_rows = period_rows[period_rows['division'] == division]
            div_cap = (div_rows['capacity_ftes'].sum() if display_mode == 'ftes'
                       else div_rows['total_standard_hours'].sum())
            auto_pct = (admin_stats.get(division) or {}).get('auto_admin_pct', 0.0)
            eff_pct = settings.get_effective_admin_pct(division, auto_pct)
            adj_cap += div_cap * (1 - eff_pct / 100)

        utilisation = round(total_load / total_cap * 100, 1) if total_cap > 0 else 0.0
        unit = 'FTEs' if display_mode == 'ftes' else 'Hrs'

        rows.append({
            'Period': get_period_label(p),
            f'Load ({unit})': round(total_load, 2),
            f'Capacity ({unit})': round(total_cap, 2),
            f'Adj. Capacity ({unit})': round(adj_cap, 2),
            'Utilisation %': utilisation,
            'Status': 'Over' if total_load > total_cap else 'Under',
        })

    return pd.DataFrame(rows)


def render_overview_view(
    aggregated_df: pd.DataFrame,
    admin_stats: Dict,
    settings,
    filters: Dict,
    display_mode: str,
    show_labels: bool,
) -> None:
    if aggregated_df is None or aggregated_df.empty:
        st.info("No data available.")
        return

    # Apply filters
    df = aggregated_df.copy()
    for col, key in [('division', 'division'), ('resource_type', 'resource_type'), ('period', 'period')]:
        val = filters.get(key)
        if val and val != 'All' and val != []:
            if isinstance(val, list):
                df = df[df[col].isin(val)]
            else:
                df = df[df[col] == val]

    if df.empty:
        st.info("No data matches the current filters.")
        return

    st.subheader("All Divisions – Overview")

    # Main stacked chart
    fig = _build_overview_chart(df, admin_stats, settings, display_mode, show_labels)
    st.plotly_chart(fig, use_container_width=True, key="overview_chart")

    # Summary table
    st.subheader("Period Summary")
    summary_df = _build_summary_table(df, admin_stats, settings, display_mode)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # Division breakdown table
    with st.expander("Division Breakdown by Period", expanded=False):
        periods = sort_periods(df['period'].unique().tolist())
        divisions = sorted(df['division'].unique().tolist())
        pivot_rows = []
        for division in divisions:
            row = {'Division': division}
            for p in periods:
                val = df[(df['division'] == division) & (df['period'] == p)]
                if display_mode == 'ftes':
                    row[get_period_label(p)] = round(val['load_ftes'].sum(), 2)
                else:
                    row[get_period_label(p)] = round(val['total_load_hours'].sum(), 2)
            pivot_rows.append(row)
        pivot_df = pd.DataFrame(pivot_rows)
        st.dataframe(pivot_df, use_container_width=True, hide_index=True)
