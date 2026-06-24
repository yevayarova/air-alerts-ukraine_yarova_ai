from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Iterable

import numpy as np
import polars as pl
import ruptures as rpt

from air_alerts.config import (
    PROJECT_ROOT,
    REGION_DAY_METRICS_PATH,
    REGION_DAY_TIMESERIES_PATH,
    REGION_TIMESERIES_SUMMARY_PATH,
    TIMESERIES_VALIDATION_REPORT_PATH,
)
from air_alerts.metrics import has_infinite_values

ROLLING_COLUMNS = [
    "alert_minutes_7d_mean",
    "alert_minutes_14d_mean",
    "alert_minutes_30d_mean",
    "abi_7d_mean",
    "abi_14d_mean",
    "abi_30d_mean",
    "alert_minutes_14d_std",
    "alert_minutes_30d_std",
    "abi_14d_std",
    "abi_30d_std",
]
REQUIRED_REGION_DAY_COLUMNS = {
    "region_name",
    "date",
    "alert_minutes_total",
    "alert_burden_index",
}
REQUIRED_SUMMARY_COLUMNS = {
    "region",
    "n_days",
    "mean_alert_minutes",
    "std_alert_minutes",
    "latest_30d_alert_minutes_mean",
    "previous_30d_alert_minutes_mean",
    "latest_vs_previous_30d_delta",
    "early_mean_alert_minutes",
    "middle_mean_alert_minutes",
    "late_mean_alert_minutes",
    "late_vs_early_alert_minutes_ratio",
    "early_mean_abi",
    "middle_mean_abi",
    "late_mean_abi",
    "late_vs_early_abi_delta",
    "n_change_points",
    "change_point_dates",
    "volatility_label",
    "trend_label",
    "regime_shift_label",
}
LABELS = {"low", "medium", "high"}
TREND_LABELS = {"improving", "stable", "worsening", "mixed"}
REGIME_SHIFT_LABELS = {
    "no clear statistical shift",
    "possible statistical shift",
    "repeated statistical shifts",
}


def build_region_day_timeseries(region_day_metrics: pl.DataFrame) -> pl.DataFrame:
    _require_columns(region_day_metrics, REQUIRED_REGION_DAY_COLUMNS, "region_day_metrics")
    return (
        region_day_metrics.sort(["region_name", "date"])
        .with_columns(
            pl.col("alert_minutes_total")
            .rolling_mean(window_size=7, min_samples=1)
            .over("region_name")
            .alias("alert_minutes_7d_mean"),
            pl.col("alert_minutes_total")
            .rolling_mean(window_size=14, min_samples=1)
            .over("region_name")
            .alias("alert_minutes_14d_mean"),
            pl.col("alert_minutes_total")
            .rolling_mean(window_size=30, min_samples=1)
            .over("region_name")
            .alias("alert_minutes_30d_mean"),
            pl.col("alert_burden_index")
            .rolling_mean(window_size=7, min_samples=1)
            .over("region_name")
            .alias("abi_7d_mean"),
            pl.col("alert_burden_index")
            .rolling_mean(window_size=14, min_samples=1)
            .over("region_name")
            .alias("abi_14d_mean"),
            pl.col("alert_burden_index")
            .rolling_mean(window_size=30, min_samples=1)
            .over("region_name")
            .alias("abi_30d_mean"),
            pl.col("alert_minutes_total")
            .rolling_std(window_size=14, min_samples=2)
            .over("region_name")
            .fill_null(0.0)
            .alias("alert_minutes_14d_std"),
            pl.col("alert_minutes_total")
            .rolling_std(window_size=30, min_samples=2)
            .over("region_name")
            .fill_null(0.0)
            .alias("alert_minutes_30d_std"),
            pl.col("alert_burden_index")
            .rolling_std(window_size=14, min_samples=2)
            .over("region_name")
            .fill_null(0.0)
            .alias("abi_14d_std"),
            pl.col("alert_burden_index")
            .rolling_std(window_size=30, min_samples=2)
            .over("region_name")
            .fill_null(0.0)
            .alias("abi_30d_std"),
        )
    )


def build_region_timeseries_summary(region_day_timeseries: pl.DataFrame) -> pl.DataFrame:
    _require_columns(region_day_timeseries, REQUIRED_REGION_DAY_COLUMNS, "region_day_timeseries")
    rows = []
    for region, region_df in region_day_timeseries.partition_by(
        "region_name",
        as_dict=True,
    ).items():
        if isinstance(region, tuple):
            region = region[0]
        region_df = region_df.sort("date")
        alert_minutes = _finite_values(region_df["alert_minutes_total"].to_list())
        abi_values = _finite_values(region_df["alert_burden_index"].to_list())
        dates = region_df["date"].to_list()
        period = _period_comparison(alert_minutes, abi_values)
        latest, previous = _latest_previous_means(alert_minutes)
        change_points = detect_change_points(alert_minutes, dates)
        std_alert_minutes = _sample_std(alert_minutes)
        late_vs_early_ratio = _late_vs_early_ratio(
            period["early_mean_alert_minutes"],
            period["late_mean_alert_minutes"],
        )
        late_vs_early_abi_delta = (
            period["late_mean_abi"] - period["early_mean_abi"]
        )

        rows.append(
            {
                "region": region,
                "n_days": len(alert_minutes),
                "mean_alert_minutes": _mean(alert_minutes),
                "std_alert_minutes": std_alert_minutes,
                "latest_30d_alert_minutes_mean": latest,
                "previous_30d_alert_minutes_mean": previous,
                "latest_vs_previous_30d_delta": latest - previous,
                "early_mean_alert_minutes": period["early_mean_alert_minutes"],
                "middle_mean_alert_minutes": period["middle_mean_alert_minutes"],
                "late_mean_alert_minutes": period["late_mean_alert_minutes"],
                "late_vs_early_alert_minutes_ratio": late_vs_early_ratio,
                "early_mean_abi": period["early_mean_abi"],
                "middle_mean_abi": period["middle_mean_abi"],
                "late_mean_abi": period["late_mean_abi"],
                "late_vs_early_abi_delta": late_vs_early_abi_delta,
                "n_change_points": len(change_points),
                "change_point_dates": ";".join(value.isoformat() for value in change_points),
                "volatility_label": volatility_label(std_alert_minutes),
                "trend_label": trend_label(
                    period["early_mean_alert_minutes"],
                    period["late_mean_alert_minutes"],
                    period["early_mean_abi"],
                    period["late_mean_abi"],
                ),
                "regime_shift_label": regime_shift_label(len(change_points)),
            }
        )
    return pl.DataFrame(rows).sort("region")


def detect_change_points(
    values: list[float | int | None],
    dates: list,
    max_change_points: int = 3,
) -> list:
    clean_values = _finite_values(values)
    if len(clean_values) != len(dates) or len(clean_values) < 12:
        return []
    if max(clean_values) == 0 or _sample_std(clean_values) < 1e-9:
        return []

    min_size = max(3, min(30, len(clean_values) // 6))
    candidate_count = min(max_change_points, max(1, len(clean_values) // min_size - 1))
    signal = np.array(clean_values, dtype=float).reshape(-1, 1)
    try:
        candidates = rpt.Binseg(model="l2", min_size=min_size).fit(signal).predict(
            n_bkps=candidate_count
        )
    except rpt.exceptions.BadSegmentationParameters:
        return []

    boundaries = [0, *sorted(point for point in candidates if point < len(clean_values)), len(clean_values)]
    output = []
    for index, point in enumerate(boundaries[1:-1], start=1):
        left = clean_values[boundaries[index - 1] : point]
        right = clean_values[point : boundaries[index + 1]]
        if _is_material_shift(left, right, clean_values):
            output.append(dates[point])
    return output[:max_change_points]


def volatility_label(std_alert_minutes: float | int | None) -> str:
    value = _finite_or_zero(std_alert_minutes)
    if value < 60:
        return "low"
    if value < 180:
        return "medium"
    return "high"


def trend_label(
    early_mean_alert_minutes: float,
    late_mean_alert_minutes: float,
    early_mean_abi: float,
    late_mean_abi: float,
) -> str:
    minutes_delta = late_mean_alert_minutes - early_mean_alert_minutes
    abi_delta = late_mean_abi - early_mean_abi
    if abs(minutes_delta) < 30 and abs(abi_delta) < 0.03:
        return "stable"
    if minutes_delta >= 30 and abi_delta >= 0.03:
        return "worsening"
    if minutes_delta <= -30 and abi_delta <= -0.03:
        return "improving"
    return "mixed"


def regime_shift_label(n_change_points: int) -> str:
    if n_change_points <= 0:
        return "no clear statistical shift"
    if n_change_points >= 2:
        return "repeated statistical shifts"
    return "possible statistical shift"


def validate_timeseries_outputs(
    region_day_timeseries: pl.DataFrame,
    region_summary: pl.DataFrame,
    input_row_count: int,
) -> dict:
    missing_timeseries = sorted(
        (REQUIRED_REGION_DAY_COLUMNS | set(ROLLING_COLUMNS))
        - set(region_day_timeseries.columns)
    )
    missing_summary = sorted(REQUIRED_SUMMARY_COLUMNS - set(region_summary.columns))
    label_checks = {
        "volatility_label": _labels_are_valid(region_summary, "volatility_label", LABELS),
        "trend_label": _labels_are_valid(region_summary, "trend_label", TREND_LABELS),
        "regime_shift_label": _labels_are_valid(
            region_summary,
            "regime_shift_label",
            REGIME_SHIFT_LABELS,
        ),
    }
    return {
        "passed": (
            not missing_timeseries
            and not missing_summary
            and region_day_timeseries.height == input_row_count
            and not has_infinite_values(region_day_timeseries)
            and not has_infinite_values(region_summary)
            and all(label_checks.values())
        ),
        "missing_timeseries_columns": missing_timeseries,
        "missing_summary_columns": missing_summary,
        "row_count_matches_input": region_day_timeseries.height == input_row_count,
        "timeseries_has_infinite_values": has_infinite_values(region_day_timeseries),
        "summary_has_infinite_values": has_infinite_values(region_summary),
        "label_checks": label_checks,
    }


def write_timeseries_validation_report(
    region_day_timeseries: pl.DataFrame,
    region_summary: pl.DataFrame,
    output_path: str | Path = TIMESERIES_VALIDATION_REPORT_PATH,
) -> None:
    validation = validate_timeseries_outputs(
        region_day_timeseries,
        region_summary,
        region_day_timeseries.height,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = f"""# Milestone 6 Time-Series Diagnostics Validation

Generated at UTC: {datetime.now(timezone.utc).isoformat()}

## Input

- `{_display_path(REGION_DAY_METRICS_PATH)}` rows: {region_day_timeseries.height}

## Outputs

- `{_display_path(REGION_DAY_TIMESERIES_PATH)}` rows: {region_day_timeseries.height}
- `{_display_path(REGION_TIMESERIES_SUMMARY_PATH)}` rows: {region_summary.height}

## Coverage

- Date start: {_column_min(region_day_timeseries, "date")}
- Date end: {_column_max(region_day_timeseries, "date")}
- Regions covered: {region_summary.height}

## Columns Created

{_bullet_list(ROLLING_COLUMNS)}

Summary diagnostics include period means, latest-vs-previous 30-day deltas, conservative change-point dates, volatility labels, trend labels, and statistical-shift labels.

## Rolling Null Counts

{_null_count_markdown(region_day_timeseries, ROLLING_COLUMNS)}

## Label Rules

- Volatility: low when daily alert-minute standard deviation is under 60 minutes, medium from 60 to under 180, high at 180 or above.
- Trend: stable when late-vs-early changes are small; worsening or improving when both alert minutes and ABI move in the same direction; mixed otherwise.
- Statistical shift flag: no clear statistical shift when no material change point is detected, possible statistical shift for one material change point, repeated statistical shifts for multiple material points.

## Example High-Volatility Regions

{_example_regions(region_summary, "volatility_label", {"high"})}

## Example Statistical Shift Flags

{_example_regions(region_summary, "regime_shift_label", {"possible statistical shift", "repeated statistical shifts"})}

## Validation

- Missing time-series columns: {validation["missing_timeseries_columns"]}
- Missing summary columns: {validation["missing_summary_columns"]}
- Row count matches input: {validation["row_count_matches_input"]}
- Time-series has infinite values: {validation["timeseries_has_infinite_values"]}
- Summary has infinite values: {validation["summary_has_infinite_values"]}
- Label checks: {validation["label_checks"]}
- Validation passed: {validation["passed"]}

## Safety Note

These diagnostics describe historical civilian alert burden, instability, and statistical changes in past time series. They are not forecasts and are not designed for real-time decision-making.

## Known Limitations

- Descriptive only.
- No causal claims.
- Not for forecasting or real-time decisions.
- Change points identify statistical shifts, not reasons for shifts.
- Region-level aggregation may hide within-region variation.
"""
    output_path.write_text(report, encoding="utf-8")


def _period_comparison(alert_minutes: list[float], abi_values: list[float]) -> dict:
    alert_periods = _split_into_thirds(alert_minutes)
    abi_periods = _split_into_thirds(abi_values)
    return {
        "early_mean_alert_minutes": _mean(alert_periods[0]),
        "middle_mean_alert_minutes": _mean(alert_periods[1]),
        "late_mean_alert_minutes": _mean(alert_periods[2]),
        "early_mean_abi": _mean(abi_periods[0]),
        "middle_mean_abi": _mean(abi_periods[1]),
        "late_mean_abi": _mean(abi_periods[2]),
    }


def _split_into_thirds(values: list[float]) -> tuple[list[float], list[float], list[float]]:
    if len(values) < 3:
        return values, values, values
    first_end = max(1, len(values) // 3)
    second_end = max(first_end + 1, (2 * len(values)) // 3)
    return values[:first_end], values[first_end:second_end], values[second_end:]


def _latest_previous_means(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    latest = values[-30:]
    previous = values[-60:-30] if len(values) > 30 else latest
    return _mean(latest), _mean(previous)


def _late_vs_early_ratio(early: float, late: float) -> float | None:
    if early == 0 and late == 0:
        return 1.0
    if early == 0 and late > 0:
        return None
    return late / early


def _is_material_shift(left: list[float], right: list[float], full_series: list[float]) -> bool:
    if not left or not right:
        return False
    threshold = max(60.0, 0.5 * _sample_std(full_series))
    return abs(_mean(right) - _mean(left)) >= threshold


def _finite_values(values: Iterable[float | int | None]) -> list[float]:
    return [_finite_or_zero(value) for value in values]


def _finite_or_zero(value: float | int | None) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    return numeric if isfinite(numeric) else 0.0


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(np.std(np.array(values, dtype=float), ddof=1))


def _require_columns(df: pl.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns in {label}: {missing}")


def _labels_are_valid(df: pl.DataFrame, column: str, allowed: set[str]) -> bool:
    if column not in df.columns:
        return False
    return set(df[column].drop_nulls().unique().to_list()) <= allowed


def _column_min(df: pl.DataFrame, column: str) -> object:
    if df.is_empty() or column not in df.columns:
        return None
    return df.select(pl.col(column).min()).item()


def _column_max(df: pl.DataFrame, column: str) -> object:
    if df.is_empty() or column not in df.columns:
        return None
    return df.select(pl.col(column).max()).item()


def _bullet_list(values: list[str]) -> str:
    return "\n".join(f"- `{value}`" for value in values)


def _null_count_markdown(df: pl.DataFrame, columns: list[str]) -> str:
    rows = []
    for column in columns:
        count = df.select(pl.col(column).null_count()).item() if column in df.columns else None
        rows.append(f"- `{column}`: {count}")
    return "\n".join(rows)


def _example_regions(df: pl.DataFrame, column: str, values: set[str]) -> str:
    if df.is_empty() or column not in df.columns:
        return "- none"
    rows = (
        df.filter(pl.col(column).is_in(values))
        .sort(["std_alert_minutes", "mean_alert_minutes"], descending=[True, True])
        .select("region", column, "mean_alert_minutes", "std_alert_minutes")
        .head(10)
        .iter_rows(named=True)
    )
    lines = [
        (
            f"- {row['region']}: {row[column]}, "
            f"mean={row['mean_alert_minutes']:.1f}, std={row['std_alert_minutes']:.1f}"
        )
        for row in rows
    ]
    return "\n".join(lines) if lines else "- none"


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
