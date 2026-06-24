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

The raw downloaded snapshot stays under
`data/raw/ukrainian-air-raid-sirens-dataset/` and is ignored by git. Source
metadata and expected-file checks are recorded in `data/raw/manifest.json`.
Processed Parquet outputs in `data/processed/` are dashboard-ready artifacts and
may be committed when refreshed.

## Scope

This repository supports historical burden analysis for civilian resilience
planning. It does not provide operational forecasts, target selection, route
inference, or tactical recommendations.
