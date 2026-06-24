# Air Alerts Ukraine

Refreshable analytics for historical Ukrainian air raid alert burden and civilian
disruption. The project is framed around civilian resilience: measuring when and
where alerts affected daily life, sleep windows, and workday continuity.

## Milestone 1 Data Refresh

Download or validate the raw source snapshot:

```bash
uv run python scripts/download_data.py --source vadimkin
```

Replace the local raw snapshot with a fresh GitHub ZIP snapshot:

```bash
uv run python scripts/download_data.py --source vadimkin --force
```

Inspect the raw schemas and write the refresh inventory:

```bash
uv run python scripts/inspect_raw_data.py
```

Build the clean historical alert interval table:

```bash
uv run python scripts/build_clean_intervals.py
```

Build dashboard-ready feature tables:

```bash
uv run python scripts/build_features.py
```

Build dashboard-ready civilian disruption metrics:

```bash
uv run python scripts/build_metrics.py
```

Run the Streamlit dashboard locally:

```bash
uv run streamlit run app/streamlit_app.py
```

The raw downloaded snapshot stays under
`data/raw/ukrainian-air-raid-sirens-dataset/` and is ignored by git. Source
metadata and expected-file checks are recorded in `data/raw/manifest.json`.
Processed Parquet outputs in `data/processed/` are dashboard-ready artifacts and
may be committed when refreshed.

## Dashboard

The Streamlit dashboard reads only processed data products:

- `data/processed/region_day_metrics.parquet`
- `data/processed/region_summary_metrics.parquet`
- `data/processed/national_summary_metrics.parquet`
- `data/processed/national_day_features.parquet`
- `reports/metrics_validation.md`

It does not load raw source files or rebuild the pipeline at app startup. This
keeps the app lightweight for a future Hugging Face Streamlit Space: the GitHub
refresh pipeline can rebuild processed Parquet artifacts, then the Space can
serve the public dashboard from those committed or synced outputs.

## Scope

This repository supports historical burden analysis for civilian resilience
planning. It does not provide operational forecasts, target selection, route
inference, or tactical recommendations.
