"""
Excel reader – mirrors backend/src/services/excel-reader.js.
Reads Userdata and Timecardactuals sheets from the Excel file using openpyxl,
with pickle-based caching keyed on the file's last-modified time.
"""
import os
import pickle
import hashlib
from pathlib import Path
from typing import Dict

import pandas as pd
import openpyxl


_REQUIRED_SHEETS = ['Userdata', 'Timecardactuals']


_EXCEL_EPOCH = __import__('datetime').date(1899, 12, 30)


def _cell_value(cell_val):
    """
    Normalise a cell value coming from openpyxl:
      - Excel error strings (#N/A, #REF! …) -> None
      - datetime / date objects -> Excel serial integer
        (openpyxl returns date-formatted cells as datetime when data_only=True)
      - everything else -> as-is
    """
    if cell_val is None:
        return None
    # openpyxl represents formula errors as strings like '#N/A', '#REF!' etc.
    if isinstance(cell_val, str) and cell_val.startswith('#'):
        return None  # treat Excel errors as missing

    # Convert datetime / date -> Excel serial so downstream code stays consistent
    # with the Node.js backend which always works with serial numbers.
    import datetime as _dt
    if isinstance(cell_val, _dt.datetime):
        return (cell_val.date() - _EXCEL_EPOCH).days
    if isinstance(cell_val, _dt.date):
        return (cell_val - _EXCEL_EPOCH).days

    return cell_val


def _read_sheet_to_df(ws) -> pd.DataFrame:
    """Convert an openpyxl worksheet to a DataFrame."""
    rows = list(ws.values)
    if not rows:
        return pd.DataFrame()
    headers = [
        (str(h).strip() if h is not None else f'col_{i}')
        for i, h in enumerate(rows[0])
    ]
    records = []
    for row in rows[1:]:
        record = {}
        for i, val in enumerate(row):
            if i < len(headers):
                record[headers[i]] = _cell_value(val)
        records.append(record)
    return pd.DataFrame(records)


def _load_parquet_data(parquet_dir: Path) -> Dict[str, pd.DataFrame]:
    """Load pre-prepared sheets from Parquet files in `parquet_dir`."""
    data: Dict[str, pd.DataFrame] = {}
    for sheet_name in _REQUIRED_SHEETS:
        key = sheet_name.lower()
        f = parquet_dir / f"{key}.parquet"
        if f.exists():
            data[key] = pd.read_parquet(f)
            print(f"  {sheet_name}: {len(data[key]):,} rows  (parquet)")
        else:
            print(f"  WARNING: Parquet '{f.name}' not found - using empty DataFrame")
            data[key] = pd.DataFrame()
    return data


def load_from_excel_only(file_path: str) -> Dict[str, pd.DataFrame]:
    """
    Always read directly from the Excel file (with pickle cache).
    Used by prepare_data.py to avoid the parquet shortcut.
    """
    return _read_excel_with_cache(file_path)


def load_excel_data(file_path: str) -> Dict[str, pd.DataFrame]:
    """
    Load Userdata and Timecardactuals sheets.

    Resolution order:
      1. Pre-prepared Parquet files in <streamlit>/data/  (deployment path)
      2. Pickle cache next to the Excel file               (local dev)
      3. The Excel file itself                              (cold start)
    """
    parquet_dir = Path(__file__).resolve().parent.parent / 'data'
    if parquet_dir.exists() and any(parquet_dir.glob('*.parquet')):
        print(f"Loading prepared data from: {parquet_dir}")
        return _load_parquet_data(parquet_dir)
    return _read_excel_with_cache(str(file_path))


def _read_excel_with_cache(file_path: str) -> Dict[str, pd.DataFrame]:
    """Read Excel directly with pickle-cache backed by mtime."""
    cache_path = Path(file_path).parent / '.excel-cache.pkl'

    # Try cache first
    try:
        if cache_path.exists():
            file_mtime = os.path.getmtime(file_path)
            with open(cache_path, 'rb') as f:
                cached = pickle.load(f)
            if cached.get('mtime') == file_mtime:
                ud = cached['data']['userdata']
                tc = cached['data']['timecardactuals']
                print(f"Loaded from cache: {cache_path}")
                print(f"  Userdata:         {len(ud):,} rows")
                print(f"  Timecardactuals:  {len(tc):,} rows")
                return cached['data']
    except Exception as e:
        print(f"Cache read failed ({e}), re-reading Excel…")

    print(f"Loading Excel file: {file_path}")
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)

    data: Dict[str, pd.DataFrame] = {}
    for sheet_name in _REQUIRED_SHEETS:
        key = sheet_name.lower()
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            df = _read_sheet_to_df(ws)
            data[key] = df
            print(f"  {sheet_name}: {len(df):,} rows")
        else:
            print(f"  WARNING: Sheet '{sheet_name}' not found – using empty DataFrame")
            data[key] = pd.DataFrame()

    wb.close()

    # Write cache
    try:
        file_mtime = os.path.getmtime(file_path)
        with open(cache_path, 'wb') as f:
            pickle.dump({'mtime': file_mtime, 'data': data}, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"Cache saved: {cache_path}")
    except Exception as e:
        print(f"Cache save failed: {e}")

    return data
