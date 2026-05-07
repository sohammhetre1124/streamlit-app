"""
Data aggregator – Python translation of backend/src/services/data-aggregator.js.
All business logic (filtering, detail-row generation, FTE aggregation,
admin-% calculation, capacity-horizon resolution) is faithfully reproduced.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from config.settings import Settings
from utils.date_utils import (
    excel_serial_to_date,
    date_to_excel_serial,
    extract_period,
    period_end_serial,
    sort_periods,
)

_VALID_COUNTRIES = {'united states', 'united states of america'}
_EXCLUDED_DIVISIONS = {'safety vigilance', 'executive'}
_EXCLUDED_ACTIVITIES = {'admin', 'leave'}


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------

def _to_str(val) -> str:
    if val is None:
        return ''
    return str(val).strip()


def _to_upper(val) -> str:
    return _to_str(val).upper()


def _to_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _is_numeric(val) -> bool:
    if val is None:
        return False
    try:
        f = float(val)
        return f == f  # NaN != NaN, so NaN returns False
    except (TypeError, ValueError):
        return False


def _period_end_serial_from_str(period: str) -> Optional[int]:
    return period_end_serial(period)


# ---------------------------------------------------------------------------
#  Main aggregator class
# ---------------------------------------------------------------------------

class DataAggregator:
    """
    Wraps raw Excel DataFrames and exposes the same interface as the Node.js
    DataAggregator class.
    """

    def __init__(self, raw_data: Dict[str, pd.DataFrame], settings: Settings):
        self.raw_userdata: pd.DataFrame = raw_data.get('userdata', pd.DataFrame())
        self.raw_timecards: pd.DataFrame = raw_data.get('timecardactuals', pd.DataFrame())
        self.settings = settings

        # Will be populated by apply_filters()
        self.filtered_userdata: pd.DataFrame = pd.DataFrame()
        self.filtered_timecards: pd.DataFrame = pd.DataFrame()
        self.admin_leave_timecards: pd.DataFrame = pd.DataFrame()

        # Will be populated by build_detail_data()
        self._detail_cache: Optional[pd.DataFrame] = None
        self._capacity_horizon_serial: Optional[int] = None
        self._capacity_horizon_source: Optional[str] = None

        # Will be populated by aggregate_data()
        self._aggregated_cache: Optional[pd.DataFrame] = None

        # Admin stats cache
        self._admin_stats_cache: Optional[Dict] = None

    # ------------------------------------------------------------------ #
    #  Step 1 – Filtering                                                  #
    # ------------------------------------------------------------------ #

    def apply_filters(self) -> None:
        """Apply geography and division filters – mirrors applyFilters() in JS."""
        ud = self.raw_userdata.copy()
        tc = self.raw_timecards.copy()

        # --- filter Userdata: geography + division ---
        def ud_keep(row) -> bool:
            div = _to_str(row.get('Division', ''))
            country = _to_str(row.get('Location (Entra)', ''))
            if div.lower() in _EXCLUDED_DIVISIONS:
                return False
            if country.lower() not in _VALID_COUNTRIES:
                return False
            if not div:
                return False
            return True

        mask = ud.apply(ud_keep, axis=1)
        self.filtered_userdata = ud[mask].reset_index(drop=True)

        n_raw_ud = len(ud)
        n_filt_ud = len(self.filtered_userdata)
        print(f"Userdata filtered: {n_raw_ud:,} -> {n_filt_ud:,}")

        # Build valid user id set (Name column = email, upper-cased)
        valid_ids = set(
            _to_upper(r.get('Name', ''))
            for _, r in self.filtered_userdata.iterrows()
            if _to_upper(r.get('Name', ''))
        )

        # --- filter Timecardactuals ---
        def tc_user_ok(email_upper: str) -> bool:
            return email_upper in valid_ids

        tc['_email_upper'] = tc.get('resource_email', pd.Series(dtype=str)).apply(
            lambda v: _to_upper(v))
        tc['_activity'] = tc.get('Activity Type 2', pd.Series(dtype=str)).apply(
            lambda v: _to_str(v))

        valid_user_mask = tc['_email_upper'].isin(valid_ids)
        is_admin_leave = tc['_activity'].str.lower().isin({'admin', 'leave'})

        self.filtered_timecards = tc[valid_user_mask & ~is_admin_leave].drop(
            columns=['_email_upper', '_activity']).reset_index(drop=True)
        self.admin_leave_timecards = tc[valid_user_mask & is_admin_leave].drop(
            columns=['_email_upper', '_activity']).reset_index(drop=True)

        n_raw_tc = len(tc)
        n_filt_tc = len(self.filtered_timecards)
        n_admin = len(self.admin_leave_timecards)
        print(f"Timecardactuals filtered: {n_raw_tc:,} -> {n_filt_tc:,}")
        print(f"Admin/Leave timecards kept: {n_admin:,}")

    # ------------------------------------------------------------------ #
    #  Step 2 – User map                                                   #
    # ------------------------------------------------------------------ #

    def _build_user_map(self) -> Dict[str, Dict]:
        """
        Build a dict:  USER_EMAIL_UPPER -> {division, resource_type,
                                            resource_name, country,
                                            standard_hours_per_day}
        Uses filtered_userdata as source.
        """
        user_map: Dict[str, Dict] = {}
        for _, row in self.filtered_userdata.iterrows():
            uid = _to_upper(row.get('Name', ''))
            if not uid:
                continue
            division = _to_str(row.get('Division', ''))
            if not division or division.lower() in _EXCLUDED_DIVISIONS:
                continue
            resource_type = _to_str(row.get('Resource Work Types', '')) or 'Unknown'
            resource_name = _to_str(row.get('Description', '')) or 'Unknown'
            country = _to_str(row.get('Location (Entra)', ''))
            std_hours = self.settings.get_standard_hours_for_country(country)
            user_map[uid] = {
                'division': division,
                'resource_type': resource_type,
                'resource_name': resource_name,
                'country': country,
                'standard_hours_per_day': std_hours,
            }
        return user_map

    # ------------------------------------------------------------------ #
    #  Step 3 – Capacity-horizon resolution                                #
    # ------------------------------------------------------------------ #

    def _resolve_capacity_horizon(
            self,
            user_activity_map: Dict[str, Dict]) -> Tuple[int, str]:
        """
        Resolve the capacity horizon Excel serial, returning (serial, source).
        Priority: config date > config period > auto (end of latest quarter).
        Mirrors _resolveCapacityHorizon() in JS.
        """
        cfg = self.settings.capacity_horizon

        # 1. Explicit ISO date
        if cfg.date:
            try:
                from datetime import date as _date
                import datetime
                d = datetime.date.fromisoformat(cfg.date)
                serial = date_to_excel_serial(d)
                if serial:
                    return serial, 'config-date'
            except ValueError:
                pass

        # 2. Explicit period
        if cfg.period:
            serial = _period_end_serial_from_str(cfg.period)
            if serial:
                return serial, 'config-period'

        # 3. Auto: end of latest quarter in data
        latest_period: Optional[str] = None
        for activity in user_activity_map.values():
            p = extract_period(activity.get('max_date'))
            if p and (latest_period is None or p > latest_period):
                latest_period = p

        if latest_period:
            serial = _period_end_serial_from_str(latest_period)
            if serial:
                return serial, 'auto'

        return 0, 'auto'

    # ------------------------------------------------------------------ #
    #  Step 4 – Detail data                                                #
    # ------------------------------------------------------------------ #

    def build_detail_data(self) -> pd.DataFrame:
        """
        Generate one row per (resource × working day) within each resource's
        active employment window.  Mirrors getDetailData() in JS exactly.
        """
        if self._detail_cache is not None:
            return self._detail_cache

        tc = self.filtered_timecards
        user_map = self._build_user_map()

        # ------------------------------------------------------------------
        # Build timecard lookup: (email_upper, date_serial) -> {load, project_types}
        # ------------------------------------------------------------------
        tc_map: Dict[Tuple[str, int], Dict] = {}
        user_activity_map: Dict[str, Dict] = {}

        for _, row in tc.iterrows():
            uid = _to_upper(row.get('resource_email', ''))
            if not uid:
                continue
            tc_date = row.get('tc_date')
            if not _is_numeric(tc_date):
                continue
            tc_date = int(float(tc_date))

            load = _to_float(row.get('load', 0))
            project_type = _to_str(row.get('project_type', '')) or 'Unknown'
            onboard = row.get('onboard_date')
            offboard = row.get('offboard_date')

            # Update tc_map
            key = (uid, tc_date)
            if key in tc_map:
                tc_map[key]['load_hours'] += load
                tc_map[key]['project_types'].add(project_type)
            else:
                tc_map[key] = {'load_hours': load, 'project_types': {project_type}}

            # Update user activity map
            onboard_val = int(float(onboard)) if _is_numeric(onboard) else None
            offboard_val = int(float(offboard)) if _is_numeric(offboard) else None

            if uid not in user_activity_map:
                user_activity_map[uid] = {
                    'min_date': tc_date,
                    'max_date': tc_date,
                    'onboard_date': onboard_val,
                    'offboard_date': offboard_val,
                }
            else:
                act = user_activity_map[uid]
                if tc_date < act['min_date']:
                    act['min_date'] = tc_date
                if tc_date > act['max_date']:
                    act['max_date'] = tc_date
                if act['onboard_date'] is None and onboard_val is not None:
                    act['onboard_date'] = onboard_val
                if act['offboard_date'] is None and offboard_val is not None:
                    act['offboard_date'] = offboard_val

        if not user_activity_map:
            self._detail_cache = pd.DataFrame()
            return self._detail_cache

        # ------------------------------------------------------------------
        # Resolve capacity horizon
        # ------------------------------------------------------------------
        horizon_serial, horizon_source = self._resolve_capacity_horizon(user_activity_map)
        self._capacity_horizon_serial = horizon_serial
        self._capacity_horizon_source = horizon_source

        if horizon_serial:
            h_date = excel_serial_to_date(horizon_serial)
            print(f"Capacity horizon: {h_date} (source: {horizon_source})")

        # Global data start = earliest tc_date across all users
        global_start = min(
            act['min_date'] for act in user_activity_map.values()
            if act['min_date'] is not None
        ) if user_activity_map else None

        if global_start:
            gs_date = excel_serial_to_date(global_start)
            print(f"Capacity start: {gs_date} (earliest date in data)")

        # ------------------------------------------------------------------
        # Generate detail rows for each user
        # ------------------------------------------------------------------
        records: List[Dict] = []

        for uid, info in user_map.items():
            activity = user_activity_map.get(uid)
            if not activity:
                continue

            onboard = activity['onboard_date']
            offboard = activity['offboard_date']

            # Effective window start (same logic as JS)
            if onboard is not None and global_start is not None:
                eff_start = max(onboard, global_start)
            elif onboard is not None:
                eff_start = onboard
            elif global_start is not None:
                eff_start = global_start
            else:
                eff_start = activity['min_date']

            # Effective window end (same logic as JS)
            if offboard is not None:
                eff_end = offboard
            elif horizon_serial:
                eff_end = max(activity['max_date'], horizon_serial)
            else:
                eff_end = activity['max_date']

            start_date = excel_serial_to_date(eff_start)
            end_date = excel_serial_to_date(eff_end)
            if start_date is None or end_date is None or start_date > end_date:
                continue

            std_hours = info['standard_hours_per_day']

            # Iterate through Mon-Fri working days in [start_date, end_date]
            current = start_date
            while current <= end_date:
                if current.weekday() < 5:  # Mon=0 … Fri=4
                    day_serial = date_to_excel_serial(current)

                    # Check user is active on this date
                    if onboard is not None and day_serial < onboard:
                        current += timedelta(days=1)
                        continue
                    if offboard is not None and day_serial > offboard:
                        current += timedelta(days=1)
                        continue

                    period = extract_period(day_serial)
                    if period:
                        tc_entry = tc_map.get((uid, day_serial))
                        load_hours = tc_entry['load_hours'] if tc_entry else 0.0
                        if tc_entry and tc_entry['project_types']:
                            project_type = sorted(tc_entry['project_types'])[0]
                        else:
                            project_type = 'Unknown'

                        records.append({
                            'date': day_serial,
                            'period': period,
                            'user_id': uid,
                            'division': info['division'],
                            'resource_type': info['resource_type'],
                            'resource_name': info['resource_name'],
                            'country': info['country'],
                            'project_type': project_type,
                            'load_hours': round(load_hours, 4),
                            'load_ftes': round(load_hours / std_hours, 4) if std_hours > 0 else 0.0,
                            'capacity_ftes': 1,
                            'is_overallocated': load_hours > std_hours,
                            'standard_hours_per_day': std_hours,
                        })
                current += timedelta(days=1)

        detail_df = pd.DataFrame(records)
        self._detail_cache = detail_df
        return detail_df

    # ------------------------------------------------------------------ #
    #  Step 5 – Aggregation                                                #
    # ------------------------------------------------------------------ #

    def aggregate_data(self) -> pd.DataFrame:
        """
        Aggregate detail rows by (division, resource_type, period).
        Mirrors aggregateData() in JS.
        """
        if self._aggregated_cache is not None:
            return self._aggregated_cache

        detail = self.build_detail_data()
        if detail.empty:
            self._aggregated_cache = pd.DataFrame()
            return self._aggregated_cache

        group_keys = ['division', 'resource_type', 'period']

        agg = (
            detail.groupby(group_keys, as_index=False)
            .agg(
                total_load_hours=('load_hours', 'sum'),
                total_standard_hours=('standard_hours_per_day', 'sum'),
                resource_count=('user_id', 'nunique'),
            )
        )

        # FTE formulas (same as JS)
        # loadFTE = (totalLoadHours * resourceCount) / totalStandardHours
        # capacityFTE = resourceCount (1 FTE per resource per day, summed per period)
        def calc_load_fte(row):
            if row['total_standard_hours'] > 0:
                return round(
                    row['total_load_hours'] * row['resource_count']
                    / row['total_standard_hours'], 2)
            return 0.0

        agg['load_ftes'] = agg.apply(calc_load_fte, axis=1)
        agg['capacity_ftes'] = agg['resource_count']
        agg['is_overallocated'] = agg['total_load_hours'] > agg['total_standard_hours']
        agg['total_load_hours'] = agg['total_load_hours'].round(2)
        agg['total_standard_hours'] = agg['total_standard_hours'].round(2)

        print(
            f"Data aggregated: {len(agg):,} unique combinations "
            f"from {len(detail):,} detail rows"
        )
        self._aggregated_cache = agg
        return agg

    # ------------------------------------------------------------------ #
    #  Admin % stats                                                       #
    # ------------------------------------------------------------------ #

    def get_admin_stats_by_division(self) -> Dict[str, Dict]:
        """
        Per-division admin stats using all data.
        Returns {division: {admin_leave_hours, capacity_hours, auto_admin_pct}}
        Mirrors getAdminStatsByDivision() in JS.
        """
        if self._admin_stats_cache is not None:
            return self._admin_stats_cache

        user_map = self._build_user_map()
        detail = self.build_detail_data()

        # Sum admin/leave hours by division
        admin_hours: Dict[str, float] = {}
        for _, row in self.admin_leave_timecards.iterrows():
            uid = _to_upper(row.get('resource_email', ''))
            info = user_map.get(uid)
            if not info:
                continue
            div = info['division']
            hours = _to_float(row.get('load', 0))
            admin_hours[div] = admin_hours.get(div, 0.0) + hours

        # Sum capacity hours by division from detail
        cap_hours: Dict[str, float] = {}
        if not detail.empty:
            for div, grp in detail.groupby('division'):
                cap_hours[div] = grp['standard_hours_per_day'].sum()

        stats: Dict[str, Dict] = {}
        all_divs = set(admin_hours.keys()) | set(cap_hours.keys())
        for div in all_divs:
            al = round(admin_hours.get(div, 0.0), 2)
            cap = round(cap_hours.get(div, 0.0), 2)
            pct = round((al / cap * 100), 1) if cap > 0 else 0.0
            stats[div] = {
                'admin_leave_hours': al,
                'capacity_hours': cap,
                'auto_admin_pct': pct,
            }

        self._admin_stats_cache = stats
        return stats

    def get_12month_admin_stats_by_division(self) -> Dict[str, Dict]:
        """
        Rolling 12-month admin % per division (365 days before capacity horizon).
        Mirrors getAdmin12MonthStatsByDivision() in JS.
        """
        horizon = self._capacity_horizon_serial
        if not horizon:
            return self.get_admin_stats_by_division()

        user_map = self._build_user_map()
        detail = self.build_detail_data()

        window_start = horizon - 365

        # Admin/leave hours in window
        admin_hours: Dict[str, float] = {}
        for _, row in self.admin_leave_timecards.iterrows():
            tc_date = row.get('tc_date')
            if not _is_numeric(tc_date):
                continue
            tc_date_int = int(float(tc_date))
            if tc_date_int < window_start or tc_date_int > horizon:
                continue
            uid = _to_upper(row.get('resource_email', ''))
            info = user_map.get(uid)
            if not info:
                continue
            div = info['division']
            hours = _to_float(row.get('load', 0))
            admin_hours[div] = admin_hours.get(div, 0.0) + hours

        # Capacity hours in window from detail
        cap_hours: Dict[str, float] = {}
        if not detail.empty:
            in_window = detail[(detail['date'] >= window_start) &
                               (detail['date'] <= horizon)]
            for div, grp in in_window.groupby('division'):
                cap_hours[div] = grp['standard_hours_per_day'].sum()

        stats: Dict[str, Dict] = {}
        all_divs = set(admin_hours.keys()) | set(cap_hours.keys())
        for div in all_divs:
            al = round(admin_hours.get(div, 0.0), 2)
            cap = round(cap_hours.get(div, 0.0), 2)
            pct = round((al / cap * 100), 1) if cap > 0 else 0.0
            stats[div] = {
                'admin_leave_hours': al,
                'capacity_hours': cap,
                'auto_admin_pct': pct,
            }
        return stats

    # ------------------------------------------------------------------ #
    #  Filter helpers                                                      #
    # ------------------------------------------------------------------ #

    def get_filter_options(self) -> Dict[str, List[str]]:
        """Return distinct filter values from aggregated data."""
        agg = self.aggregate_data()
        if agg.empty:
            return {'divisions': [], 'resource_types': [], 'periods': []}
        return {
            'divisions': sorted(agg['division'].dropna().unique().tolist()),
            'resource_types': sorted(agg['resource_type'].dropna().unique().tolist()),
            'periods': sort_periods(agg['period'].dropna().unique().tolist()),
        }

    def get_resource_types_for_division(self, divisions: list) -> List[str]:
        """Return resource types available for the given division(s)."""
        agg = self.aggregate_data()
        if agg.empty:
            return []
        if not divisions:
            return sorted(agg['resource_type'].dropna().unique().tolist())
        filtered = agg[agg['division'].isin(divisions)]
        return sorted(filtered['resource_type'].dropna().unique().tolist())

    def get_resource_names_for_filter(
            self,
            divisions: list,
            resource_types: list) -> List[str]:
        """Return resource names for given division(s) and resource type(s)."""
        detail = self.build_detail_data()
        if detail.empty:
            return []
        mask = pd.Series([True] * len(detail), index=detail.index)
        if divisions:
            mask &= detail['division'].isin(divisions)
        if resource_types:
            mask &= detail['resource_type'].isin(resource_types)
        return sorted(detail[mask]['resource_name'].dropna().unique().tolist())

    def filter_aggregated_data(self, filters: Dict) -> pd.DataFrame:
        """Filter aggregated data by division / resource_type / period."""
        agg = self.aggregate_data()
        if agg.empty:
            return agg

        df = agg.copy()
        for col, key in [('division', 'division'),
                         ('resource_type', 'resource_type'),
                         ('period', 'period')]:
            val = filters.get(key)
            if val and val != 'All' and val != []:
                if isinstance(val, list):
                    df = df[df[col].isin(val)]
                else:
                    df = df[df[col] == val]
        return df

    def filter_detail_data(self, filters: Dict) -> pd.DataFrame:
        """Filter detail data by division / resource_type / resource_name / period."""
        detail = self.build_detail_data()
        if detail.empty:
            return detail

        df = detail.copy()
        for col, key in [('division', 'division'),
                         ('resource_type', 'resource_type'),
                         ('resource_name', 'resource_name'),
                         ('period', 'period')]:
            val = filters.get(key)
            if val and val != 'All' and val != []:
                if isinstance(val, list):
                    df = df[df[col].isin(val)]
                else:
                    df = df[df[col] == val]
        return df

    def get_distribution_data(self, filters: Dict) -> pd.DataFrame:
        """
        Return hours by project_type for the given filters.
        Mirrors the /api/distribution endpoint.
        """
        detail = self.filter_detail_data(filters)
        if detail.empty:
            return pd.DataFrame(columns=['project_type', 'hours', 'percentage'])

        grp = (
            detail.groupby('project_type', as_index=False)['load_hours']
            .sum()
            .rename(columns={'load_hours': 'hours'})
        )
        total = grp['hours'].sum()
        grp['percentage'] = (grp['hours'] / total * 100).round(1) if total > 0 else 0
        return grp.sort_values('hours', ascending=False).reset_index(drop=True)

    def get_capacity_horizon_info(self) -> Dict:
        """Return info about the resolved capacity horizon."""
        if not self._capacity_horizon_serial:
            return {'serial': None, 'iso_date': None, 'source': None}
        d = excel_serial_to_date(self._capacity_horizon_serial)
        return {
            'serial': self._capacity_horizon_serial,
            'iso_date': d.isoformat() if d else None,
            'source': self._capacity_horizon_source,
        }
