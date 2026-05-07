"""
One-time data preparation: convert the source Excel workbook into compact
Parquet files committed alongside the Streamlit app.

Run locally before pushing to GitHub:
    python prepare_data.py path/to/UserandTimecarddata.xlsx

Output: data/userdata.parquet  and  data/timecardactuals.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from services.excel_reader import load_from_excel_only

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"


def main(excel_path: str) -> None:
    excel_path = str(Path(excel_path).resolve())
    print(f"Source: {excel_path}")

    data = load_from_excel_only(excel_path)

    DATA_DIR.mkdir(exist_ok=True)
    for sheet_key, df in data.items():
        out = DATA_DIR / f"{sheet_key}.parquet"
        # PyArrow requires uniform column types. For each object column:
        #   1. Try numeric coercion - keeps performance for numeric-mostly cols
        #   2. Otherwise cast every cell to string
        df_out = df.copy()
        for col in df_out.columns:
            if df_out[col].dtype != "object":
                continue
            coerced = pd.to_numeric(df_out[col], errors="coerce")
            non_null_orig = df_out[col].notna().sum()
            non_null_num = coerced.notna().sum()
            # If >=99% of non-null values parsed as numbers, treat the column as numeric
            if non_null_orig > 0 and non_null_num / non_null_orig >= 0.99:
                df_out[col] = coerced
            else:
                df_out[col] = df_out[col].apply(
                    lambda v: None if v is None or (isinstance(v, float) and v != v) else str(v)
                )
        df_out.to_parquet(out, compression="snappy", index=False)
        size_mb = out.stat().st_size / (1024 * 1024)
        print(f"  {sheet_key:20s} {len(df_out):>8,} rows  ->  {out.name} ({size_mb:.2f} MB)")

    print("\nDone. Commit the data/ folder.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default: look for the Excel one level above the streamlit folder
        default = HERE.parent / "UserandTimecarddata.xlsx"
        if default.exists():
            main(str(default))
        else:
            print("Usage: python prepare_data.py <path/to/UserandTimecarddata.xlsx>")
            sys.exit(1)
    else:
        main(sys.argv[1])
