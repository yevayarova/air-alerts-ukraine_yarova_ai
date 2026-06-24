from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from air_alerts.config import (
    ALERTS_CLEAN_PATH,
    FEATURE_VALIDATION_REPORT_PATH,
    NATIONAL_DAY_FEATURES_PATH,
    REGION_DAY_FEATURES_PATH,
    REGION_HOUR_FEATURES_PATH,
)
from air_alerts.features import (
    build_national_day_features,
    build_region_day_features,
    build_region_hour_features,
    profile_alerts,
    validate_feature_ranges,
    write_feature_validation_report,
)
from air_alerts.storage import write_parquet_atomic


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build dashboard-ready historical alert burden feature tables."
    )
    parser.add_argument("--input", type=Path, default=ALERTS_CLEAN_PATH)
    args = parser.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(
            f"Missing clean alerts input: {args.input}. "
            "Run `uv run python scripts/build_clean_intervals.py` first."
        )

    print("Stage: load clean alert intervals")
    alerts = pl.read_parquet(args.input)
    profile = profile_alerts(alerts)
    _print_input_profile(profile)

    print("Stage: build region-hour features")
    region_hour = build_region_hour_features(alerts)
    print(f"region_hour rows: {region_hour.height}")

    print("Stage: build region-day features")
    region_day = build_region_day_features(alerts, region_hour)
    print(f"region_day rows: {region_day.height}")

    print("Stage: build national-day features")
    national_day = build_national_day_features(region_hour, region_day)
    print(f"national_day rows: {national_day.height}")

    print("Stage: validate feature ranges")
    validation = validate_feature_ranges(region_hour, region_day, national_day)
    _print_validation(validation)
    if not validation["passed"]:
        raise ValueError("Feature validation failed. See range summary above.")

    print("Stage: write processed feature tables")
    write_parquet_atomic(region_hour, REGION_HOUR_FEATURES_PATH)
    write_parquet_atomic(region_day, REGION_DAY_FEATURES_PATH)
    write_parquet_atomic(national_day, NATIONAL_DAY_FEATURES_PATH)
    write_feature_validation_report(
        alerts,
        region_hour,
        region_day,
        national_day,
        FEATURE_VALIDATION_REPORT_PATH,
    )

    print(f"Saved: {REGION_HOUR_FEATURES_PATH}")
    print(f"Saved: {REGION_DAY_FEATURES_PATH}")
    print(f"Saved: {NATIONAL_DAY_FEATURES_PATH}")
    print(f"Saved: {FEATURE_VALIDATION_REPORT_PATH}")
    print("Validation status: passed")


def _print_input_profile(profile: dict) -> None:
    print(f"input rows: {profile['row_count']}")
    print(f"region count: {profile['region_count']}")
    print(f"coverage start: {profile['coverage_start']}")
    print(f"coverage end: {profile['coverage_end']}")
    print(f"missing ended_at_utc values: {profile['missing_ended_at_utc']}")
    print(f"zero or negative durations: {profile['zero_or_negative_durations']}")
    print(f"timestamps timezone-aware: {profile['timestamps_timezone_aware']}")
    print(f"duplicate alert_id values: {profile['duplicate_alert_ids']}")
    print("regions:")
    for region in profile["region_names"]:
        print(f"  - {region}")


def _print_validation(validation: dict) -> None:
    for metric, check in validation["checks"].items():
        print(
            f"{metric}: min={check['min']} max={check['max']} "
            f"expected={check['lower']}..{check['upper']} "
            f"passed={check['passed']}"
        )


if __name__ == "__main__":
    main()
