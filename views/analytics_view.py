"""
Analytics view – replicates the React Analytics tab with ChartCard components.
One Plotly chart per division showing Load bars vs Capacity/Adjusted-Capacity lines,
with period drill-down and per-resource detail tables.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.date_utils import (
    get_period_label,
    sort_periods,
    is_period_complete,
    is_period_in_progress,
    excel_serial_to_date,
    get_month_label,
)
from utils.chart_utils import get_division_color, format_fte, format_hours


# ---------------------------------------------------------------------------
#  Chart builders
# ---------------------------------------------------------------------------

def _build_division_chart(
    division: str,
    div_data: pd.DataFrame,
    admin_pct: float,
    display_mode: str,
    show_labels: bool,
    div_index: int,
) -> go.Figure:
    """Create a bar+line Plotly chart for one division, per quarter."""
    periods = sort_periods(div_data['period'].unique().tolist())

    x_labels = [get_period_label(p) for p in periods]

    if display_mode == 'ftes':
        y_load = [
            div_data[div_data['period'] == p]['load_ftes'].sum()
            for p in periods
        ]
        y_cap = [
            div_data[div_data['period'] == p]['capacity_ftes'].sum()
            for p in periods
        ]
    else:
        y_load = [
            div_data[div_data['period'] == p]['total_load_hours'].sum()
            for p in periods
        ]
        y_cap = [
            # capacity in hours = capacity_ftes × standard hours per day × working days
            # We approximate as total_standard_hours already in the data
            div_data[div_data['period'] == p]['total_standard_hours'].sum()
            for p in periods
        ]

    # Adjusted capacity = capacity × (1 – admin% / 100)
    adjust_factor = 1 - admin_pct / 100
    y_adj_cap = [v * adjust_factor for v in y_cap]

    # Colour each bar: completed = primary colour, in-progress = amber
    bar_colors = []
    for p in periods:
        if is_period_complete(p):
            bar_colors.append(get_division_color(division, div_index))
        elif is_period_in_progress(p):
            bar_colors.append('#F39C12')
        else:
            bar_colors.append('#85C1E9')  # future = light blue

    # Line modes: completed = solid, in-progress/future = dashed
    cap_line_colors, cap_dash = [], []
    for p in periods:
        if is_period_complete(p):
            cap_line_colors.append('#27AE60')
            cap_dash.append('solid')
        else:
            cap_line_colors.append('#E67E22')
            cap_dash.append('dash')

    fig = go.Figure()

    # Load bars
    text_load = [format_fte(v) if display_mode == 'ftes' else format_hours(v)
                 for v in y_load]
    fig.add_trace(go.Bar(
        x=x_labels,
        y=y_load,
        name='Actual Load',
        marker_color=bar_colors,
        text=text_load if show_labels else None,
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>Load: %{y:.2f}<extra></extra>',
    ))

    # Capacity line
    fig.add_trace(go.Scatter(
        x=x_labels,
        y=y_cap,
        name='Capacity',
        mode='lines+markers',
        line=dict(color='#27AE60', width=2),
        marker=dict(size=6),
        hovertemplate='<b>%{x}</b><br>Capacity: %{y:.2f}<extra></extra>',
    ))

    # Adjusted capacity line (dashed purple)
    fig.add_trace(go.Scatter(
        x=x_labels,
        y=y_adj_cap,
        name=f'Adj. Capacity ({admin_pct:.1f}% admin)',
        mode='lines+markers',
        line=dict(color='#8E44AD', width=2, dash='dash'),
        marker=dict(size=6),
        hovertemplate='<b>%{x}</b><br>Adj. Capacity: %{y:.2f}<extra></extra>',
    ))

    y_label = 'FTEs' if display_mode == 'ftes' else 'Hours'
    fig.update_layout(
        height=320,
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(
            orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
            font=dict(size=11),
        ),
        xaxis_title='Period',
        yaxis_title=y_label,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(gridcolor='rgba(128,128,128,0.3)'),
        xaxis=dict(gridcolor='rgba(128,128,128,0.3)'),
        showlegend=True,
    )
    return fig


def _build_monthly_chart(
    period: str,
    detail: pd.DataFrame,
    display_mode: str,
) -> go.Figure:
    """Bar chart for a selected period broken down by month."""
    detail = detail.copy()
    detail['_date'] = detail['date'].apply(excel_serial_to_date)
    detail = detail[detail['_date'].notna()]
    detail['_month'] = detail['_date'].apply(lambda d: (d.year, d.month))

    months = sorted(detail['_month'].unique())
    x_labels = [get_month_label(y, m) for y, m in months]

    if display_mode == 'ftes':
        y_load = [detail[detail['_month'] == mo]['load_ftes'].sum() for mo in months]
        y_cap = [detail[detail['_month'] == mo]['capacity_ftes'].sum() for mo in months]
    else:
        y_load = [detail[detail['_month'] == mo]['load_hours'].sum() for mo in months]
        y_cap = [detail[detail['_month'] == mo]['standard_hours_per_day'].sum() for mo in months]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x_labels, y=y_load,
        name='Actual Load', marker_color='#3498DB',
        hovertemplate='<b>%{x}</b><br>Load: %{y:.2f}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=x_labels, y=y_cap,
        name='Capacity', mode='lines+markers',
        line=dict(color='#27AE60', width=2),
        hovertemplate='<b>%{x}</b><br>Capacity: %{y:.2f}<extra></extra>',
    ))
    y_label = 'FTEs' if display_mode == 'ftes' else 'Hours'
    fig.update_layout(
        height=280,
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis_title='Month',
        yaxis_title=y_label,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(gridcolor='rgba(128,128,128,0.3)'),
        legend=dict(
            orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
            font=dict(size=11),
        ),
    )
    return fig


def _build_distribution_pie(dist_data: pd.DataFrame, title: str) -> go.Figure:
    """Pie chart for project_type distribution."""
    if dist_data.empty or dist_data['hours'].sum() == 0:
        return None
    fig = go.Figure(go.Pie(
        labels=dist_data['project_type'],
        values=dist_data['hours'],
        textinfo='label+percent',
        hovertemplate='<b>%{label}</b><br>Hours: %{value:.1f}<br>%{percent}<extra></extra>',
    ))
    fig.update_layout(
        height=280,
        margin=dict(l=10, r=10, t=30, b=10),
        title=dict(text=title, x=0.5, font=dict(size=12)),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
#  Detail table helpers
# ---------------------------------------------------------------------------

def _render_detail_table(detail: pd.DataFrame, display_mode: str, key_suffix: str = "") -> None:
    """Render a resource-level detail table with search."""
    if detail.empty:
        st.info("No detail data for current selection.")
        return

    search = st.text_input("Search by name, type, or email", key=f"det_search_{key_suffix}")

    df = detail.copy()
    df['_date_str'] = df['date'].apply(
        lambda s: excel_serial_to_date(s).isoformat() if excel_serial_to_date(s) else '')

    if search:
        mask = (
            df['resource_name'].str.contains(search, case=False, na=False) |
            df['resource_type'].str.contains(search, case=False, na=False) |
            df['user_id'].str.contains(search, case=False, na=False)
        )
        df = df[mask]

    if df.empty:
        st.warning("No rows match your search.")
        return

    show_cols = {
        'Date': '_date_str',
        'Period': 'period',
        'Resource Name': 'resource_name',
        'Resource Type': 'resource_type',
        'Project Type': 'project_type',
        'Load (h)': 'load_hours',
        'Load FTE': 'load_ftes',
        'Cap FTE': 'capacity_ftes',
        'Over?': 'is_overallocated',
    }
    display_df = df[[v for v in show_cols.values() if v in df.columns]].copy()
    display_df.columns = [k for k, v in show_cols.items() if v in df.columns]
    display_df['Load (h)'] = display_df['Load (h)'].round(2) if 'Load (h)' in display_df else display_df
    st.dataframe(display_df.head(500), use_container_width=True, height=300)
    st.caption(f"Showing {min(500, len(df)):,} of {len(df):,} rows")


# ---------------------------------------------------------------------------
#  Main view renderer
# ---------------------------------------------------------------------------

def render_analytics_view(
    aggregated_df: pd.DataFrame,
    detail_df: pd.DataFrame,
    admin_stats: Dict,
    settings,
    filters: Dict,
    display_mode: str,
    show_labels: bool,
    layout_cols: int,
    show_distribution: bool,
    aggregator,
) -> None:
    if aggregated_df is None or aggregated_df.empty:
        st.info("No data available. Check your filters or data source.")
        return

    # Apply filters to data
    filtered_agg = aggregated_df.copy()
    filtered_detail = detail_df.copy() if detail_df is not None and not detail_df.empty else pd.DataFrame()

    for col, key in [('division', 'division'), ('resource_type', 'resource_type'), ('period', 'period')]:
        val = filters.get(key)
        if val and val != 'All' and val != []:
            if isinstance(val, list):
                filtered_agg = filtered_agg[filtered_agg[col].isin(val)]
                if not filtered_detail.empty:
                    filtered_detail = filtered_detail[filtered_detail[col].isin(val)]
            else:
                filtered_agg = filtered_agg[filtered_agg[col] == val]
                if not filtered_detail.empty:
                    filtered_detail = filtered_detail[filtered_detail[col] == val]

    if filtered_agg.empty:
        st.info("No data matches the current filters.")
        return

    divisions = sorted(filtered_agg['division'].unique().tolist())
    num_cols = layout_cols if layout_cols in [1, 2] else 2
    col_list = st.columns(num_cols)

    for div_idx, division in enumerate(divisions):
        col = col_list[div_idx % num_cols]
        with col:
            div_agg = filtered_agg[filtered_agg['division'] == division].copy()
            div_detail = filtered_detail[filtered_detail['division'] == division].copy() \
                if not filtered_detail.empty else pd.DataFrame()

            # Get admin % for this division
            auto_pct = (admin_stats.get(division) or {}).get('auto_admin_pct', 0.0)
            effective_pct = settings.get_effective_admin_pct(division, auto_pct)

            # Aggregate per period for chart
            periods = sort_periods(div_agg['period'].unique().tolist())

            # Aggregate by period across resource types
            period_agg = div_agg.groupby('period', as_index=False).agg(
                total_load_hours=('total_load_hours', 'sum'),
                total_standard_hours=('total_standard_hours', 'sum'),
                load_ftes=('load_ftes', 'sum'),
                capacity_ftes=('capacity_ftes', 'sum'),
                resource_count=('resource_count', 'sum'),
            )

            # Division header
            color = get_division_color(division, div_idx)
            st.markdown(
                f'<div style="border-left: 4px solid {color}; padding-left: 10px; '
                f'margin-bottom: 8px;">'
                f'<h4 style="margin:0; color:#2C3E50;">{division}</h4>'
                f'<span style="color:#7F8C8D; font-size:0.8em;">Admin: {effective_pct:.1f}%</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Main chart
            fig = _build_division_chart(
                division=division,
                div_data=period_agg,
                admin_pct=effective_pct,
                display_mode=display_mode,
                show_labels=show_labels,
                div_index=div_idx,
            )
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{division}_{div_idx}")

            # Distribution toggle
            if show_distribution and not div_detail.empty:
                dist = aggregator.get_distribution_data({'division': [division]})
                pie_fig = _build_distribution_pie(dist, f"{division} – Work Distribution")
                if pie_fig:
                    st.plotly_chart(pie_fig, use_container_width=True,
                                   key=f"dist_{division}_{div_idx}")

            # Drill-down expander
            with st.expander(f"Drill-down: {division}", expanded=False):
                # Admin % override
                new_pct = st.number_input(
                    "Admin % override (blank = auto)",
                    min_value=0.0, max_value=100.0,
                    value=float(settings.admin_percentage.get(division, auto_pct)),
                    step=0.5,
                    key=f"admin_{division}",
                    help=f"Auto-calculated: {auto_pct:.1f}%",
                )
                if abs(new_pct - float(settings.admin_percentage.get(division, auto_pct))) > 0.01:
                    settings.admin_percentage[division] = new_pct
                    st.rerun()

                if div_detail.empty:
                    st.info("Load detail data to see drill-down.")
                else:
                    # Period selector for monthly breakdown
                    selected_period = st.selectbox(
                        "Select period for monthly breakdown",
                        options=['All'] + sort_periods(div_detail['period'].unique().tolist()),
                        key=f"period_sel_{division}",
                    )
                    monthly_detail = div_detail if selected_period == 'All' else \
                        div_detail[div_detail['period'] == selected_period]

                    monthly_fig = _build_monthly_chart(selected_period, monthly_detail, display_mode)
                    st.plotly_chart(monthly_fig, use_container_width=True,
                                   key=f"monthly_{division}_{selected_period}")

                    # Resource detail table
                    st.markdown("**Resource Detail**")
                    _render_detail_table(monthly_detail, display_mode,
                                         key_suffix=f"{division}_{selected_period}")
