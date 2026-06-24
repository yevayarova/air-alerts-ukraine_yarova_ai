# Methodology

## Purpose

This project is a refreshable data product for historical Ukrainian air raid
alert burden and civilian disruption. It is intended for resilience-oriented
analysis by civilians, journalists, researchers, NGOs, and planners.

The dashboard describes past alert burden, night-window alert exposure,
work/study-window alert exposure, regional inequality, and stability/change in
historical burden. It does not provide forecasts, causal explanations, or
real-time decision support.

## Data Pipeline

The raw layer is downloaded from the upstream Ukrainian air raid sirens dataset
with `scripts/download_data.py`. The raw dataset itself is reproducible and is
not committed; raw source metadata is recorded in `data/raw/manifest.json`.

The clean interval layer converts source records into a processed alert interval
table at `data/processed/alerts_clean.parquet`. Cleaning standardizes timestamps,
regions, source fields, and durations so later layers can rebuild from a stable
processed input.

## Feature Layer

The feature layer builds dashboard-ready historical tables:

- `region_hour_features.parquet`
- `region_day_features.parquet`
- `national_day_features.parquet`

Hourly and daily features are clipped to relevant local windows and avoid
minute-level expansion. Overlapping alert intervals in the same region are
merged before alert minutes are counted, preventing overlapping source records
from inflating total alert minutes.

Semantic hardening separated two count concepts:

- `raw_alert_record_count`: cleaned source records intersecting a region-date
- `merged_alert_episode_count`: merged non-overlapping alert episodes on a
  region-date

`alert_count` is retained as a compatibility alias for
`merged_alert_episode_count`.

## Metric Layer

The metric layer creates:

- `region_day_metrics.parquet`
- `region_summary_metrics.parquet`
- `national_summary_metrics.parquet`

The Alert Burden Index combines normalized daily alert minutes, merged alert
episode count, maximum alert duration, and recovery-window disruption. ABI is a
descriptive index, not a probability.

The Sleep Disruption Index measures the share of the default Kyiv-local
night-window under alert. The Work/Study Disruption Index measures the share of
the default weekday work/study window under alert.

Regional inequality is summarized with daily Gini-style metrics across regions.
These compare distribution of historical burden across regions and are not
selected-region-specific.

## Time-Series Diagnostics

The time-series layer creates:

- `region_day_timeseries.parquet`
- `region_timeseries_summary.parquet`

It adds rolling means and rolling volatility for alert minutes and ABI, plus
regional summaries comparing early, middle, and late periods. Conservative
change-point detection marks statistical changes in historical daily alert
minutes.

Public labels are intentionally cautious:

- `worsening` is shown as `historically increased`
- `stable` is shown as `historically stable`
- `mixed` is shown as `mixed historical pattern`
- repeated change points are shown as `repeated statistical shifts`

These labels describe historical patterns only. They do not explain why a shift
happened and are not forecasts.

## Dashboard Logic

The Streamlit dashboard reads committed processed Parquet files and validation
reports only. It does not download raw data or rebuild the pipeline during app
startup. This keeps the public app lightweight for Hugging Face Spaces.

The public interface is organized into:

- Overview
- Regional Burden
- Human Disruption
- Regional Inequality
- Stability & Change
- Methodology & Limits

## Safety Framing

The project is civilian resilience analytics. It summarizes historical
disruption from alert exposure and avoids real-time decision support. Statistical
signals in the dashboard are descriptive and should not be read as warnings or
causal explanations.

## Limitations

- Sleep and work/study windows are default assumptions and may not match every
  person or institution.
- Kyiv-local dashboard hours use a 24-hour display grid; daylight saving
  transition days are documented as a limitation.
- Region-level aggregation can hide within-region variation.
- ABI uses min-max normalization over the current processed dataset, so values
  can rescale after refreshes.
- Time-series thresholds are rule-based and not externally calibrated.
- Change points identify statistical shifts in the historical series, not
  reasons for shifts.

## Why The Final Version Is Stronger

The final version is stronger than the initial pipeline because it separates raw
record counts from merged alert episodes, uses merged episodes in ABI, documents
refresh-relative normalization, adds golden tests for overlap and zero-alert
cases, integrates Stability & Change into the public dashboard, and prepares the
repository for Hugging Face Spaces deployment.
