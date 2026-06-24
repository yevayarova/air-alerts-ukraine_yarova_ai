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

Build descriptive time-series diagnostics:

```bash
uv run python scripts/build_timeseries.py
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
- `data/processed/region_day_timeseries.parquet`
- `data/processed/region_timeseries_summary.parquet`
- `data/processed/national_day_features.parquet`
- `reports/metrics_validation.md`

It does not load raw source files or rebuild the pipeline at app startup. This
keeps the app lightweight for a future Hugging Face Streamlit Space: the GitHub
refresh pipeline can rebuild processed Parquet artifacts, then the Space can
serve the public dashboard from those committed or synced outputs.

## Metric Semantics

Daily feature tables keep two alert-count fields:

- `raw_alert_record_count` counts cleaned source records intersecting a region-date.
- `merged_alert_episode_count` counts non-overlapping alert episodes after records
  are merged within a region-date.

`alert_count` is retained as a compatibility alias for
`merged_alert_episode_count`. The Alert Burden Index uses merged episodes, not raw
source record counts, so overlapping administrative records do not inflate the
count component. ABI components are min-max normalized over the currently
processed region-day table; after a data refresh, historical ABI values can be
rescaled if new minima or maxima are observed.

Kyiv-local dashboard hours use a 24-hour wall-clock display grid. Daylight saving
transition days are documented as a limitation because repeated or skipped local
clock hours are not modeled as separate dashboard buckets.

## Time-Series Diagnostics

The time-series layer is descriptive historical diagnostics for non-stationary
civilian alert burden:

- `data/processed/region_day_timeseries.parquet` adds rolling means and rolling
  volatility for alert minutes and ABI.
- `data/processed/region_timeseries_summary.parquet` summarizes early/middle/late
  period comparisons, latest-vs-previous 30-day changes, conservative
  change-point dates, volatility labels, trend labels, and statistical-shift labels.
- `reports/timeseries_validation.md` documents output coverage, null counts,
  label rules, examples, and limitations.

Volatility describes instability of civilian planning conditions. Change points
identify statistical shifts in historical burden series, not causes. These
diagnostics are not forecasts and are not designed for real-time decisions.

## Scope

This repository supports historical burden analysis for civilian resilience
planning. It is descriptive only and is not designed for forecasting, military
activity analysis, movement inference, or real-time decision-making.
