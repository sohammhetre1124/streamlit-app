"""
Export service – mirrors backend/src/services/export.js.
Generates an Excel workbook (2 sheets: Summary + Detail) using xlsxwriter.
Returns a BytesIO buffer ready for st.download_button.
"""
from io import BytesIO
from typing import Dict

import pandas as pd

from utils.date_utils import excel_serial_to_date


def _matches(filter_val, item_val) -> bool:
    if filter_val is None or filter_val == 'All' or filter_val == '':
        return True
    if isinstance(filter_val, list):
        return len(filter_val) == 0 or item_val in filter_val
    return filter_val == item_val


def generate_excel_export(
    aggregated_df: pd.DataFrame,
    detail_df: pd.DataFrame,
    filters: Dict,
) -> BytesIO:
    """
    Build a two-sheet Excel file from the supplied DataFrames,
    filtered according to `filters`.  Returns a BytesIO object.
    """
    # --- filter aggregated ---
    agg = aggregated_df.copy()
    for col, key in [('division', 'division'),
                     ('resource_type', 'resource_type'),
                     ('period', 'period')]:
        fv = filters.get(key)
        if fv and fv != 'All' and fv != []:
            if isinstance(fv, list):
                agg = agg[agg[col].isin(fv)]
            else:
                agg = agg[agg[col] == fv]

    # --- filter detail ---
    det = detail_df.copy()
    for col, key in [('division', 'division'),
                     ('resource_type', 'resource_type'),
                     ('resource_name', 'resource_name'),
                     ('period', 'period')]:
        fv = filters.get(key)
        if fv and fv != 'All' and fv != []:
            if isinstance(fv, list):
                det = det[det[col].isin(fv)]
            else:
                det = det[det[col] == fv]

    # --- build sheet 1: Summary ---
    summary_rows = []
    for _, row in agg.iterrows():
        summary_rows.append({
            'Division': row.get('division', ''),
            'Resource Type': row.get('resource_type', ''),
            'Period': row.get('period', ''),
            'Total Load (Hours)': row.get('total_load_hours', 0),
            'Load (FTEs)': row.get('load_ftes', 0),
            'Capacity (FTEs)': row.get('capacity_ftes', 0),
            'Resource Count': row.get('resource_count', 0),
            'Status': 'Overallocated' if row.get('is_overallocated') else 'Underallocated',
        })
    summary_df = pd.DataFrame(summary_rows)

    # --- build sheet 2: Detail ---
    detail_rows = []
    for _, row in det.iterrows():
        date_serial = row.get('date')
        date_str = ''
        if date_serial:
            d = excel_serial_to_date(date_serial)
            if d:
                date_str = d.isoformat()
        detail_rows.append({
            'Date': date_str,
            'Period': row.get('period', ''),
            'User ID': row.get('user_id', ''),
            'Resource Name': row.get('resource_name', ''),
            'Division': row.get('division', ''),
            'Resource Type': row.get('resource_type', ''),
            'Project Type': row.get('project_type', ''),
            'Load (Hours)': row.get('load_hours', 0),
            'Load (FTEs)': row.get('load_ftes', 0),
            'Capacity (FTEs)': row.get('capacity_ftes', 0),
            'Status': 'Overallocated' if row.get('is_overallocated') else 'Underallocated',
        })
    detail_export_df = pd.DataFrame(detail_rows)

    # --- write to BytesIO ---
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        detail_export_df.to_excel(writer, sheet_name='Detail', index=False)

        # Auto-fit columns
        workbook = writer.book
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#4472C4', 'font_color': 'white'})

        for sheet_name, df in [('Summary', summary_df), ('Detail', detail_export_df)]:
            worksheet = writer.sheets[sheet_name]
            for i, col in enumerate(df.columns):
                max_len = max(len(str(col)), df[col].astype(str).str.len().max() if len(df) > 0 else 0)
                worksheet.set_column(i, i, min(max_len + 2, 40))
                worksheet.write(0, i, col, header_fmt)

    buf.seek(0)
    return buf


def generate_assumptions_csv(assumptions: list) -> str:
    """Return assumptions as a CSV string."""
    import csv
    import io
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_ALL)
    writer.writerow(['Category', 'Assumption', 'Description', 'Business Impact'])
    for a in assumptions:
        writer.writerow([
            a.get('category', ''),
            a.get('assumption', ''),
            a.get('description', ''),
            a.get('businessImpact', ''),
        ])
    return out.getvalue()


def generate_assumptions_excel(assumptions: list) -> BytesIO:
    """Return assumptions as an Excel BytesIO."""
    rows = [
        {
            'Category': a.get('category', ''),
            'Assumption': a.get('assumption', ''),
            'Description': a.get('description', ''),
            'Business Impact': a.get('businessImpact', ''),
        }
        for a in assumptions
    ]
    df = pd.DataFrame(rows)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Assumptions', index=False)
        workbook = writer.book
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#4472C4', 'font_color': 'white'})
        ws = writer.sheets['Assumptions']
        for i, col in enumerate(df.columns):
            ws.set_column(i, i, 45)
            ws.write(0, i, col, header_fmt)
    buf.seek(0)
    return buf
