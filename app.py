"""
Division Report Dashboard – Streamlit entry point.
Run with:  streamlit run app.py
This is a full port of the Node.js + React prototype with all features preserved.
"""
import os
import sys
from pathlib import Path

# Make sure local packages are importable when running from the streamlit/ folder
_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import streamlit as st

from config.settings import Settings, get_default_settings
from services.excel_reader import load_excel_data
from services.data_aggregator import DataAggregator
from services.data_validation import DataValidationService
from services.export_service import generate_excel_export
from views.analytics_view import render_analytics_view
from views.overview_view import render_overview_view
from views.validation_view import render_validation_view
from views.assumptions_view import render_assumptions_view
from utils.date_utils import get_period_label, sort_periods

# ---------------------------------------------------------------------------
#  Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Division Report Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
#  Data location.
#
#  In deployment we ship pre-built Parquet files under <streamlit>/data/.
#  In local dev we fall back to the source Excel one folder up (or alongside).
#  EXCEL_PATH is only used as the cache-key — the actual read is decided by
#  services.excel_reader.load_excel_data().
# ---------------------------------------------------------------------------
def _resolve_data_source() -> str:
    parquet_dir = _HERE / "data"
    if parquet_dir.exists() and any(parquet_dir.glob("*.parquet")):
        return str(parquet_dir)  # logical key for cache
    for candidate in (_HERE / "UserandTimecarddata.xlsx",
                      _HERE.parent / "UserandTimecarddata.xlsx"):
        if candidate.exists():
            return str(candidate)
    # Last resort – return the parquet dir even if missing; reader will warn.
    return str(parquet_dir)


EXCEL_PATH = _resolve_data_source()

# ---------------------------------------------------------------------------
#  Session-state initialisation
# ---------------------------------------------------------------------------
def _init_state() -> None:
    if 'settings' not in st.session_state:
        st.session_state['settings'] = get_default_settings()
    if 'display_mode' not in st.session_state:
        st.session_state['display_mode'] = 'hours'   # 'hours' | 'ftes'
    if 'show_labels' not in st.session_state:
        st.session_state['show_labels'] = True
    if 'layout_cols' not in st.session_state:
        st.session_state['layout_cols'] = 2
    if 'show_distribution' not in st.session_state:
        st.session_state['show_distribution'] = False
    if 'filters' not in st.session_state:
        st.session_state['filters'] = {
            'division': [],
            'resource_type': [],
            'resource_name': [],
            'period': [],
        }
    if 'groq_api_key' not in st.session_state:
        st.session_state['groq_api_key'] = ''
    if 'validation_result' not in st.session_state:
        st.session_state['validation_result'] = None
    if 'validator_obj' not in st.session_state:
        st.session_state['validator_obj'] = None


# ---------------------------------------------------------------------------
#  Cached data loading & processing
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading Excel file…")
def _cached_load_excel(path: str):
    return load_excel_data(path)


@st.cache_data(show_spinner="Processing data…")
def _cached_process(
    excel_path: str,
    settings_key: str,
    horizon_mode: str,
    horizon_date,
    horizon_period,
    std_hours_json: str,
    admin_pct_json: str,
):
    """
    Heavy computation cached by settings hash.
    Returns dict with all pre-computed DataFrames and stats.
    """
    import json

    raw_data = _cached_load_excel(excel_path)

    # Reconstruct Settings from cache-key components
    settings = get_default_settings()
    settings.capacity_horizon.mode = horizon_mode
    settings.capacity_horizon.date = horizon_date
    settings.capacity_horizon.period = horizon_period
    if std_hours_json:
        try:
            settings.standard_hours_per_day = json.loads(std_hours_json)
        except Exception:
            pass
    if admin_pct_json:
        try:
            settings.admin_percentage = json.loads(admin_pct_json)
        except Exception:
            pass

    agg = DataAggregator(raw_data, settings)
    agg.apply_filters()
    detail_df = agg.build_detail_data()
    aggregated_df = agg.aggregate_data()
    admin_stats = agg.get_12month_admin_stats_by_division()
    horizon_info = agg.get_capacity_horizon_info()
    filter_opts = agg.get_filter_options()

    return {
        'aggregated_df': aggregated_df,
        'detail_df': detail_df,
        'admin_stats': admin_stats,
        'horizon_info': horizon_info,
        'filter_opts': filter_opts,
        'raw_data': raw_data,
    }


def _get_processed_data(settings: Settings):
    """Helper to call _cached_process with unpacked settings params."""
    import json
    return _cached_process(
        excel_path=EXCEL_PATH,
        settings_key=settings.to_cache_key(),
        horizon_mode=settings.capacity_horizon.mode,
        horizon_date=settings.capacity_horizon.date,
        horizon_period=settings.capacity_horizon.period,
        std_hours_json=json.dumps(settings.standard_hours_per_day, sort_keys=True),
        admin_pct_json=json.dumps(settings.admin_percentage, sort_keys=True),
    )


# ---------------------------------------------------------------------------
#  Sidebar – Settings panel
# ---------------------------------------------------------------------------

def _render_settings_sidebar(settings: Settings, filter_opts: dict) -> bool:
    """Render settings expander; returns True if settings were saved."""
    with st.sidebar.expander("⚙️ Settings", expanded=False):
        st.markdown("**Capacity Horizon**")
        h_mode = st.radio(
            "Mode",
            options=['auto', 'date', 'period'],
            index=['auto', 'date', 'period'].index(settings.capacity_horizon.mode),
            key='s_h_mode',
            horizontal=True,
        )

        h_date, h_period = None, None
        if h_mode == 'date':
            from datetime import date
            default_date = date(2026, 6, 30)
            if settings.capacity_horizon.date:
                try:
                    default_date = date.fromisoformat(settings.capacity_horizon.date)
                except ValueError:
                    pass
            picked = st.date_input("Date", value=default_date, key='s_h_date')
            h_date = picked.isoformat() if picked else None
        elif h_mode == 'period':
            periods = filter_opts.get('periods', [])
            idx = 0
            if settings.capacity_horizon.period in periods:
                idx = periods.index(settings.capacity_horizon.period)
            h_period = st.selectbox(
                "Period",
                options=periods,
                index=idx,
                key='s_h_period',
                format_func=get_period_label,
            )

        st.markdown("---")
        st.markdown("**Standard Hours Per Day**")
        std_rows = list(settings.standard_hours_per_day.items())
        updated_std = {}
        for country, hours in std_rows:
            col1, col2 = st.columns([2, 1])
            with col1:
                st.caption(country)
            with col2:
                new_h = st.number_input(
                    f"h_{country}",
                    value=float(hours),
                    min_value=1.0, max_value=24.0, step=0.5,
                    label_visibility='collapsed',
                    key=f's_std_{country}',
                )
                updated_std[country] = new_h

        st.markdown("---")
        st.markdown("**Groq API Key** (for AI-powered Q&A)")
        groq_key = st.text_input(
            "Groq API Key",
            value=st.session_state.get('groq_api_key', ''),
            type='password',
            key='s_groq_key',
        )
        st.session_state['groq_api_key'] = groq_key

        st.markdown("---")
        if st.button("Save & Apply", key="s_save", type="primary"):
            settings.capacity_horizon.mode = h_mode
            settings.capacity_horizon.date = h_date
            settings.capacity_horizon.period = h_period
            settings.standard_hours_per_day = updated_std
            _cached_process.clear()  # invalidate cache
            return True
    return False


# ---------------------------------------------------------------------------
#  Sidebar – Display options
# ---------------------------------------------------------------------------

def _render_display_options_sidebar() -> None:
    with st.sidebar.expander("🖥️ Display Options", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            dm = st.radio(
                "Values",
                options=['hours', 'ftes'],
                format_func=lambda x: 'Hours' if x == 'hours' else 'FTEs',
                index=0 if st.session_state['display_mode'] == 'hours' else 1,
                key='opt_display_mode',
                horizontal=False,
            )
            st.session_state['display_mode'] = dm
        with col2:
            lc = st.radio(
                "Layout",
                options=[1, 2],
                format_func=lambda x: f"{x} col{'s' if x > 1 else ''}",
                index=0 if st.session_state['layout_cols'] == 1 else 1,
                key='opt_layout',
                horizontal=False,
            )
            st.session_state['layout_cols'] = lc

        st.session_state['show_labels'] = st.checkbox(
            "Show chart labels",
            value=st.session_state['show_labels'],
            key='opt_labels',
        )
        st.session_state['show_distribution'] = st.checkbox(
            "Show work distribution",
            value=st.session_state['show_distribution'],
            key='opt_dist',
        )


# ---------------------------------------------------------------------------
#  Sidebar – Filters
# ---------------------------------------------------------------------------

def _render_filters_sidebar(filter_opts: dict, settings: Settings, aggregator_ref) -> None:
    with st.sidebar.expander("🔽 Filters", expanded=True):
        f = st.session_state['filters']
        divisions = filter_opts.get('divisions', [])
        all_resource_types = filter_opts.get('resource_types', [])
        all_periods = filter_opts.get('periods', [])

        # Division
        selected_div = st.multiselect(
            "Division",
            options=divisions,
            default=f.get('division', []),
            key='filt_division',
        )

        # Resource Type (cascades from division)
        if selected_div and aggregator_ref:
            available_types = aggregator_ref.get_resource_types_for_division(selected_div)
        else:
            available_types = all_resource_types

        selected_rt = st.multiselect(
            "Resource Type",
            options=available_types,
            default=[v for v in f.get('resource_type', []) if v in available_types],
            key='filt_resource_type',
        )

        # Resource Name (cascades from division + type)
        if aggregator_ref:
            available_names = aggregator_ref.get_resource_names_for_filter(
                selected_div, selected_rt)
        else:
            available_names = []

        selected_name = st.multiselect(
            "Resource Name",
            options=available_names,
            default=[v for v in f.get('resource_name', []) if v in available_names],
            key='filt_resource_name',
            disabled=not available_names,
        )

        # Period
        selected_period = st.multiselect(
            "Period",
            options=all_periods,
            default=[v for v in f.get('period', []) if v in all_periods],
            format_func=get_period_label,
            key='filt_period',
        )

        if st.button("Clear Filters", key="filt_clear"):
            st.session_state['filters'] = {
                'division': [], 'resource_type': [],
                'resource_name': [], 'period': [],
            }
            st.rerun()

        st.session_state['filters'] = {
            'division': selected_div,
            'resource_type': selected_rt,
            'resource_name': selected_name,
            'period': selected_period,
        }


# ---------------------------------------------------------------------------
#  Sidebar – Summary stats
# ---------------------------------------------------------------------------

def _render_summary_sidebar(filter_opts: dict, horizon_info: dict,
                              aggregated_df, filters: dict) -> None:
    st.sidebar.markdown("---")
    # Active filters summary
    active = {k: v for k, v in filters.items() if v}
    if active:
        st.sidebar.caption("**Active Filters:**")
        for k, v in active.items():
            if isinstance(v, list):
                st.sidebar.caption(f"  {k}: {', '.join(str(x) for x in v)}")

    if horizon_info.get('iso_date'):
        st.sidebar.metric(
            "Capacity Horizon",
            horizon_info['iso_date'],
            help=f"Source: {horizon_info.get('source', 'auto')}",
        )

    if aggregated_df is not None and not aggregated_df.empty:
        total_res = aggregated_df['resource_count'].sum() if 'resource_count' in aggregated_df.columns else 0
        st.sidebar.metric("Total Resource-Periods", f"{len(aggregated_df):,}")


# ---------------------------------------------------------------------------
#  Export buttons in sidebar
# ---------------------------------------------------------------------------

def _render_export_sidebar(aggregated_df, detail_df, filters: dict) -> None:
    st.sidebar.markdown("---")
    with st.sidebar.expander("📥 Export", expanded=False):
        if aggregated_df is not None and not aggregated_df.empty:
            buf = generate_excel_export(aggregated_df, detail_df, filters)
            st.download_button(
                label="Download Excel (Summary + Detail)",
                data=buf,
                file_name="DivisionReport.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_excel",
            )
        else:
            st.caption("No data to export.")


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------

def main() -> None:
    _init_state()

    settings: Settings = st.session_state['settings']

    # Header
    st.title("📊 Division Report Dashboard")
    st.caption("Workforce capacity & allocation analysis for Bausch + Lomb")

    # Check Excel file exists
    if not os.path.exists(EXCEL_PATH):
        st.error(
            f"Excel file not found at:\n`{EXCEL_PATH}`\n\n"
            "Please place `UserandTimecarddata.xlsx` in the parent directory of this app."
        )
        st.stop()

    # Process data
    with st.spinner("Initialising data pipeline…"):
        try:
            data = _get_processed_data(settings)
        except Exception as e:
            st.error(f"Error processing data: {e}")
            st.exception(e)
            st.stop()

    aggregated_df = data['aggregated_df']
    detail_df = data['detail_df']
    admin_stats = data['admin_stats']
    horizon_info = data['horizon_info']
    filter_opts = data['filter_opts']
    raw_data = data['raw_data']

    # Build a live aggregator for cascading filters (cached processing is frozen;
    # cascading lookups need the aggregator object)
    @st.cache_resource
    def _get_aggregator(excel_path: str, settings_key: str):
        import json
        rd = _cached_load_excel(excel_path)
        s = get_default_settings()
        agg = DataAggregator(rd, settings)
        agg.apply_filters()
        agg.build_detail_data()
        agg.aggregate_data()
        return agg

    aggregator = _get_aggregator(EXCEL_PATH, settings.to_cache_key())

    # Lazy validation (on demand)
    if st.session_state['validation_result'] is None:
        validator = DataValidationService(raw_data)
        st.session_state['validator_obj'] = validator
        # Pre-compute validation in background (fast enough on first load)
        with st.spinner("Running data validation…"):
            st.session_state['validation_result'] = validator.validate()

    validation_result = st.session_state['validation_result']
    validator_obj = st.session_state.get('validator_obj')
    if validator_obj is None and raw_data:
        validator_obj = DataValidationService(raw_data)
        st.session_state['validator_obj'] = validator_obj

    # ------------------------------------------------------------------ #
    #  Sidebar
    # ------------------------------------------------------------------ #
    st.sidebar.title("Controls")

    saved = _render_settings_sidebar(settings, filter_opts)
    if saved:
        st.rerun()

    _render_display_options_sidebar()
    _render_filters_sidebar(filter_opts, settings, aggregator)
    _render_summary_sidebar(filter_opts, horizon_info, aggregated_df,
                             st.session_state['filters'])
    _render_export_sidebar(aggregated_df, detail_df, st.session_state['filters'])

    # ------------------------------------------------------------------ #
    #  Main tabs
    # ------------------------------------------------------------------ #
    tab_analytics, tab_overview, tab_validation, tab_assumptions = st.tabs([
        "📈 Analytics",
        "🌐 Overview",
        "✅ Validation",
        "📋 Assumptions",
    ])

    display_mode: str = st.session_state['display_mode']
    show_labels: bool = st.session_state['show_labels']
    layout_cols: int = st.session_state['layout_cols']
    show_dist: bool = st.session_state['show_distribution']
    filters: dict = st.session_state['filters']

    with tab_analytics:
        render_analytics_view(
            aggregated_df=aggregated_df,
            detail_df=detail_df,
            admin_stats=admin_stats,
            settings=settings,
            filters=filters,
            display_mode=display_mode,
            show_labels=show_labels,
            layout_cols=layout_cols,
            show_distribution=show_dist,
            aggregator=aggregator,
        )

    with tab_overview:
        render_overview_view(
            aggregated_df=aggregated_df,
            admin_stats=admin_stats,
            settings=settings,
            filters=filters,
            display_mode=display_mode,
            show_labels=show_labels,
        )

    with tab_validation:
        render_validation_view(
            validation=validation_result,
            validator=validator_obj,
        )

    with tab_assumptions:
        render_assumptions_view()


if __name__ == "__main__":
    main()
