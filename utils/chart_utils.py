"""
Chart utility functions and shared colour schemes.
"""

# Per-division colour scheme matching the React frontend exactly
DIVISION_COLORS = {
    'Clinical Services': '#FF6B6B',
    'Medical & Scientific Affairs': '#4ECDC4',
    'Surgical': '#45B7D1',
    'Regulatory Affairs': '#FFA07A',
    'Pharma/Consumer': '#98D8C8',
    'Portfolio + Project Management': '#F7DC6F',
    'Vision Care': '#BB8FCE',
}

# Fallback colours for divisions not in the map
_FALLBACK_COLORS = [
    '#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A',
    '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52',
]


def get_division_color(division: str, index: int = 0) -> str:
    """Return the colour for a division, falling back to the palette by index."""
    return DIVISION_COLORS.get(division, _FALLBACK_COLORS[index % len(_FALLBACK_COLORS)])


def format_fte(value) -> str:
    """Format an FTE value to 1 decimal place."""
    if value is None:
        return '0.0'
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return '0.0'


def format_hours(value) -> str:
    """Format an hours value to 2 decimal places."""
    if value is None:
        return '0.00'
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return '0.00'


def format_value(value, display_mode: str) -> str:
    """Format a value according to the current display mode."""
    if display_mode == 'ftes':
        return format_fte(value)
    return format_hours(value)


# Project-type colour palette for distribution pie charts
PROJECT_TYPE_COLORS = [
    '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
    '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac',
]


def get_project_type_color(index: int) -> str:
    return PROJECT_TYPE_COLORS[index % len(PROJECT_TYPE_COLORS)]
