from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from air_alerts.config import (
    METRICS_VALIDATION_REPORT_PATH,
    NATIONAL_DAY_FEATURES_PATH,
    NATIONAL_SUMMARY_METRICS_PATH,
    REGION_DAY_FEATURES_PATH,
    REGION_DAY_METRICS_PATH,
    REGION_SUMMARY_METRICS_PATH,
)
from air_alerts.metrics import (
    build_national_summary_metrics,
    build_region_day_metrics,
    build_region_summary_metrics,
    has_infinite_values,
    validate_metric_ranges,
    write_metrics_validation_report,
)
from air_alerts.storage import write_parquet_atomic


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build dashboard-ready civilian disruption metric tables."
    )
    parser.add_argument(
        "--region-day-features",
        type=Path,
        default=REGION_DAY_FEATURES_PATH,
    )
    parser.add_argument(
        "--national-day-features",
        type=Path,
        default=NATIONAL_DAY_FEATURES_PATH,
    )
    args = parser.parse_args()

    _require_file(args.region_day_features)
    _require_file(args.national_day_features)

    print("Stage: load feature tables")
    region_day_features = pl.read_parquet(args.region_day_features)
    national_day_features = pl.read_parquet(args.national_day_features)
    print(f"region_day_features rows: {region_day_features.height}")
    print(f"national_day_features rows: {national_day_features.height}")

    print("Stage: build region-day metrics")
    region_day_metrics = build_region_day_metrics(region_day_features)
    print(f"region_day_metrics rows: {region_day_metrics.height}")

    print("Stage: build region summary metrics")
    region_summary = build_region_summary_metrics(region_day_metrics)
    print(f"region_summary_metrics rows: {region_summary.height}")

    print("Stage: build national summary metrics")
    national_summary = build_national_summary_metrics(
        region_day_metrics,
        national_day_features,
    )
    print(f"national_summary_metrics rows: {national_summary.height}")

    print("Stage: validate metric ranges")
    validation = validate_metric_ranges(region_day_metrics)
    _print_validation(validation)
    summary_has_infinite = has_infinite_values(region_summary)
    national_has_infinite = has_infinite_values(national_summary)
    print(f"region_summary_metrics has infinite values: {summary_has_infinite}")
    print(f"national_summary_metrics has infinite values: {national_has_infinite}")
    _print_category_counts(region_day_metrics)
    if not validation["passed"] or summary_has_infinite or national_has_infinite:
        raise ValueError("Metric validation failed. See range summary above.")

    print("Stage: write metric tables")
    write_parquet_atomic(region_day_metrics, REGION_DAY_METRICS_PATH)
    write_parquet_atomic(region_summary, REGION_SUMMARY_METRICS_PATH)
    write_parquet_atomic(national_summary, NATIONAL_SUMMARY_METRICS_PATH)
    write_metrics_validation_report(
        region_day_metrics,
        region_summary,
        national_summary,
        METRICS_VALIDATION_REPORT_PATH,
    )

    print(f"Saved: {REGION_DAY_METRICS_PATH}")
    print(f"Saved: {REGION_SUMMARY_METRICS_PATH}")
    print(f"Saved: {NATIONAL_SUMMARY_METRICS_PATH}")
    print(f"Saved: {METRICS_VALIDATION_REPORT_PATH}")
    print("Validation status: passed")


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing required feature input: {path}. "
            "Run `uv run python scripts/build_features.py` first."
        )


def _print_validation(validation: dict) -> None:
    for metric, check in validation["checks"].items():
        print(
            f"{metric}: min={check['min']} max={check['max']} "
            f"expected={check['lower']}..{check['upper']} "
            f"passed={check['passed']}"
        )
    print(f"has infinite values: {validation['has_infinite_values']}")


def _print_category_counts(region_day_metrics: pl.DataFrame) -> None:
    for column in [
        "alert_burden_category",
        "sleep_disruption_category",
        "workday_disruption_category",
    ]:
        print(f"{column} counts:")
        for row in region_day_metrics.group_by(column).len().sort(column).iter_rows(
            named=True
        ):
            print(f"  {row[column]}: {row['len']}")


if __name__ == "__main__":
    main()
