from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from air_alerts.config import (
    REGION_DAY_METRICS_PATH,
    REGION_DAY_TIMESERIES_PATH,
    REGION_TIMESERIES_SUMMARY_PATH,
    TIMESERIES_VALIDATION_REPORT_PATH,
)
from air_alerts.storage import write_parquet_atomic
from air_alerts.timeseries import (
    build_region_day_timeseries,
    build_region_timeseries_summary,
    validate_timeseries_outputs,
    write_timeseries_validation_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build descriptive time-series diagnostics for civilian alert burden."
    )
    parser.add_argument(
        "--region-day-metrics",
        type=Path,
        default=REGION_DAY_METRICS_PATH,
    )
    args = parser.parse_args()

    _require_file(args.region_day_metrics)

    print("Stage: load region-day metric table")
    region_day_metrics = pl.read_parquet(args.region_day_metrics)
    print(f"region_day_metrics rows: {region_day_metrics.height}")
    print(
        "date range: "
        f"{region_day_metrics.select(pl.col('date').min()).item()} to "
        f"{region_day_metrics.select(pl.col('date').max()).item()}"
    )
    print(
        "regions: "
        f"{region_day_metrics.select(pl.col('region_name').n_unique()).item()}"
    )

    print("Stage: build region-day time-series diagnostics")
    region_day_timeseries = build_region_day_timeseries(region_day_metrics)
    print(f"region_day_timeseries rows: {region_day_timeseries.height}")

    print("Stage: build region time-series summary")
    region_summary = build_region_timeseries_summary(region_day_timeseries)
    print(f"region_timeseries_summary rows: {region_summary.height}")

    print("Stage: validate time-series diagnostics")
    validation = validate_timeseries_outputs(
        region_day_timeseries,
        region_summary,
        region_day_metrics.height,
    )
    _print_validation(validation)
    if not validation["passed"]:
        raise ValueError("Time-series validation failed. See summary above.")

    _print_label_counts(region_summary)

    print("Stage: write time-series outputs")
    write_parquet_atomic(region_day_timeseries, REGION_DAY_TIMESERIES_PATH)
    write_parquet_atomic(region_summary, REGION_TIMESERIES_SUMMARY_PATH)
    write_timeseries_validation_report(
        region_day_timeseries,
        region_summary,
        TIMESERIES_VALIDATION_REPORT_PATH,
    )

    print(f"Saved: {REGION_DAY_TIMESERIES_PATH}")
    print(f"Saved: {REGION_TIMESERIES_SUMMARY_PATH}")
    print(f"Saved: {TIMESERIES_VALIDATION_REPORT_PATH}")
    print("Validation status: passed")


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing required metrics input: {path}. "
            "Run `uv run python scripts/build_metrics.py` first."
        )


def _print_validation(validation: dict) -> None:
    print(f"missing time-series columns: {validation['missing_timeseries_columns']}")
    print(f"missing summary columns: {validation['missing_summary_columns']}")
    print(f"row count matches input: {validation['row_count_matches_input']}")
    print(
        "region_day_timeseries has infinite values: "
        f"{validation['timeseries_has_infinite_values']}"
    )
    print(
        "region_timeseries_summary has infinite values: "
        f"{validation['summary_has_infinite_values']}"
    )
    print(f"label checks: {validation['label_checks']}")


def _print_label_counts(region_summary: pl.DataFrame) -> None:
    for column in ["volatility_label", "trend_label", "regime_shift_label"]:
        print(f"{column} counts:")
        for row in region_summary.group_by(column).len().sort(column).iter_rows(
            named=True
        ):
            print(f"  {row[column]}: {row['len']}")


if __name__ == "__main__":
    main()
