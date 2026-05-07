"""
Date utility functions for Excel serial date conversion and period handling.
Mirrors the UTC-based date logic from the Node.js backend exactly.
"""
from datetime import date, datetime, timedelta
from typing import Optional

# Excel epoch: Dec 30, 1899 (accounts for Excel's intentional leap-year bug)
_EXCEL_EPOCH = date(1899, 12, 30)


def excel_serial_to_date(serial) -> Optional[date]:
    """Convert an Excel serial date number to a Python date."""
    if serial is None:
        return None
    try:
        s = int(float(serial))
        if s < 0 or s > 2958465:  # sanity range: up to year 9999
            return None
        return _EXCEL_EPOCH + timedelta(days=s)
    except (TypeError, ValueError, OverflowError):
        return None


def date_to_excel_serial(d) -> Optional[int]:
    """Convert a Python date or datetime to Excel serial number."""
    if d is None:
        return None
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date):
        return (d - _EXCEL_EPOCH).days
    return None


def extract_period(serial) -> Optional[str]:
    """Extract quarter period string (e.g. '2025-QTR-3') from an Excel serial date."""
    d = excel_serial_to_date(serial)
    if d is None:
        return None
    q = (d.month - 1) // 3 + 1
    return f"{d.year}-QTR-{q}"


def period_end_date(period: str) -> Optional[date]:
    """Return the last calendar day of a quarter period string like '2025-QTR-3'."""
    try:
        parts = period.split('-')
        year = int(parts[0])
        q = int(parts[2])
        end_month = q * 3
        if end_month == 12:
            return date(year, 12, 31)
        return date(year, end_month + 1, 1) - timedelta(days=1)
    except (IndexError, ValueError):
        return None


def period_start_date(period: str) -> Optional[date]:
    """Return the first calendar day of a quarter period string."""
    try:
        parts = period.split('-')
        year = int(parts[0])
        q = int(parts[2])
        start_month = (q - 1) * 3 + 1
        return date(year, start_month, 1)
    except (IndexError, ValueError):
        return None


def period_end_serial(period: str) -> Optional[int]:
    """Return Excel serial for the last day of a quarter period."""
    d = period_end_date(period)
    return date_to_excel_serial(d) if d else None


def period_start_serial(period: str) -> Optional[int]:
    """Return Excel serial for the first day of a quarter period."""
    d = period_start_date(period)
    return date_to_excel_serial(d) if d else None


def get_period_label(period: str) -> str:
    """Convert '2025-QTR-3' to 'Q3 2025'."""
    try:
        parts = period.split('-')
        return f"Q{parts[2]} {parts[0]}"
    except (IndexError, AttributeError):
        return period or ''


def sort_periods(periods) -> list:
    """Sort period strings chronologically (they sort correctly as strings)."""
    return sorted(p for p in periods if p)


def get_month_label(year: int, month: int) -> str:
    """Return a short month label like 'Jul 2025'."""
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return f"{month_names[month - 1]} {year}"


def is_period_complete(period: str) -> bool:
    """Return True if the period's end date is strictly in the past."""
    end = period_end_date(period)
    if end is None:
        return False
    return end < date.today()


def is_period_in_progress(period: str) -> bool:
    """Return True if today falls within this period."""
    start = period_start_date(period)
    end = period_end_date(period)
    if start is None or end is None:
        return False
    today = date.today()
    return start <= today <= end
