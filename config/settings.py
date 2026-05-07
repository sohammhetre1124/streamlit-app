"""
Runtime configuration – mirrors backend/src/config/index.js exactly.
All values live in st.session_state['settings'] so changes persist across reruns.
"""
import json
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class CapacityHorizonConfig:
    mode: str = 'auto'          # 'auto' | 'date' | 'period'
    date: Optional[str] = None  # ISO date, e.g. '2026-06-30'
    period: Optional[str] = None  # Quarter string, e.g. '2026-QTR-2'


@dataclass
class Settings:
    capacity_horizon: CapacityHorizonConfig = field(
        default_factory=CapacityHorizonConfig)
    standard_hours_per_day: Dict[str, float] = field(default_factory=lambda: {
        'default': 8,
        'United States': 8,
        'United States of America': 8,
    })
    admin_percentage: Dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    #  Lookup helpers                                                      #
    # ------------------------------------------------------------------ #
    def get_standard_hours_for_country(self, country: Optional[str]) -> float:
        """Case-insensitive lookup with fallback to 'default' then 8."""
        if country:
            trimmed = str(country).strip()
            if trimmed in self.standard_hours_per_day:
                return self.standard_hours_per_day[trimmed]
            lower = trimmed.lower()
            for key, val in self.standard_hours_per_day.items():
                if key.lower() == lower:
                    return val
        return self.standard_hours_per_day.get('default', 8)

    def get_effective_admin_pct(self, division: str, auto_pct: float) -> float:
        """Return override admin % for the division, else the auto-calculated value."""
        if division in self.admin_percentage:
            return self.admin_percentage[division]
        return auto_pct

    # ------------------------------------------------------------------ #
    #  Serialisation for caching                                          #
    # ------------------------------------------------------------------ #
    def to_cache_key(self) -> str:
        """Stable string key so @st.cache_data can detect settings changes."""
        return json.dumps({
            'h_mode': self.capacity_horizon.mode,
            'h_date': self.capacity_horizon.date,
            'h_period': self.capacity_horizon.period,
            'std': sorted(self.standard_hours_per_day.items()),
            'adm': sorted(self.admin_percentage.items()),
        }, sort_keys=True)

    def update_from_dict(self, patch: dict) -> None:
        """Apply a partial update (mirrors config.update() in Node.js)."""
        if not patch:
            return

        ch = patch.get('capacity_horizon', {})
        if 'mode' in ch:
            self.capacity_horizon.mode = ch['mode']
        if 'date' in ch:
            self.capacity_horizon.date = ch['date'] or None
        if 'period' in ch:
            self.capacity_horizon.period = ch['period'] or None

        if 'standard_hours_per_day' in patch:
            raw = patch['standard_hours_per_day']
            normalized = {}
            for k, v in raw.items():
                try:
                    n = float(v)
                    if n > 0:
                        normalized[str(k).strip()] = n
                except (TypeError, ValueError):
                    pass
            if 'default' not in normalized:
                normalized['default'] = 8
            self.standard_hours_per_day = normalized

        if 'admin_percentage' in patch:
            next_adm = {}
            for k, v in patch['admin_percentage'].items():
                if v in ('', None):
                    continue
                try:
                    n = float(v)
                    next_adm[str(k).strip()] = max(0.0, min(100.0, n))
                except (TypeError, ValueError):
                    pass
            self.admin_percentage = next_adm


def get_default_settings() -> Settings:
    return Settings()
