# Division Report Dashboard

Workforce capacity & allocation analysis for Bausch + Lomb, built in Streamlit.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app reads pre-built Parquet files from `data/`. To rebuild them from a
source Excel workbook:

```bash
python prepare_data.py path/to/UserandTimecarddata.xlsx
```

## Deploy on Streamlit Community Cloud

1. Push this folder to GitHub.
2. On https://share.streamlit.io click **New app** and select this repo.
3. Set **Main file path** to `app.py`.
4. Deploy.

The `data/` folder ships with the repo, so no upload is required at runtime.

## Tabs

- **Analytics** – per-division load vs capacity charts with drill-down
- **Overview** – stacked bar across all divisions
- **Validation** – data-quality rules and AI-powered Q&A (paste a Groq API key in the sidebar)
- **Assumptions** – business assumptions reference, exportable to CSV/Excel
