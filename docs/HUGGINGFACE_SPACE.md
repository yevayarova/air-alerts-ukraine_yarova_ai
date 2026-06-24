# Hugging Face Space Deployment

This repository is ready to run as a Hugging Face Streamlit Space.

## Space Settings

- SDK: Streamlit
- App file: `app/streamlit_app.py`
- Runtime dependencies: `requirements.txt`
- Data source for the app: committed processed Parquet files in `data/processed/`

The README front matter contains the Space metadata, including `sdk: streamlit`
and `app_file: app/streamlit_app.py`.

## Local Smoke Check

```bash
streamlit run app/streamlit_app.py
```

The app should load from processed files only. It should not download raw data,
run the pipeline, or run tests during startup.

## Data Refresh Model

The public Space serves the latest processed artifacts committed or synced to the
repository:

- `data/processed/region_day_metrics.parquet`
- `data/processed/region_summary_metrics.parquet`
- `data/processed/national_summary_metrics.parquet`
- `data/processed/national_day_features.parquet`
- `data/processed/region_day_timeseries.parquet`
- `data/processed/region_timeseries_summary.parquet`
- `reports/metrics_validation.md`
- `reports/timeseries_validation.md`

Refreshing those artifacts remains an admin workflow outside Space startup. A
future scheduled pipeline can rebuild processed data in GitHub Actions and sync
the outputs to the Space.

## Safety Boundary

The dashboard presents historical civilian disruption analytics only. Time-series
signals describe past statistical patterns in alert burden. They do not explain
causes, provide forecasts, or support real-time decisions.
