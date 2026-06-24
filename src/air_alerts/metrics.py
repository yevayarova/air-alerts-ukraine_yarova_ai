from __future__ import annotations

from datetime import datetime, timezone
from math import ceil, isfinite
from pathlib import Path
from typing import Iterable

import polars as pl

from air_alerts.config import (
    METRICS_VALIDATION_REPORT_PATH,
    NATIONAL_DAY_FEATURES_PATH,
    NATIONAL_SUMMARY_METRICS_PATH,
    PROJECT_ROOT,
    REGION_DAY_FEATURES_PATH,
    REGION_DAY_METRICS_PATH,
    REGION_SUMMARY_METRICS_PATH,
)

DAY_MINUTES = 24 * 60
DEFAULT_SLEEP_WINDOW_MINUTES = 9 * 60
DEFAULT_WORK_WINDOW_MINUTES = 9 * 60
ALLOWED_CATEGORIES = {"low", "medium", "high"}


def minmax_normalize(values: Iterable[float | int | None]) -> list[float]:
    clean_values = [_finite_or_zero(value) for value in values]
    if not clean_values:
        return []

    minimum = min(clean_values)
    maximum = max(clean_values)
    if maximum == minimum:
        return [0.0 for _ in clean_values]

    return [(value - minimum) / (maximum - minimum) for value in clean_values]


def safe_divide(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    result = numerator / denominator
    return result if isfinite(result) else None


def categorize_metric(value: float | int | None) -> str:
    if value is None:
        return "low"
    if value < 0.33:
        return "low"
    if value < 0.66:
        return "medium"
    return "high"


def gini(values: Iterable[float | int | None]) -> float:
    clean_values = sorted(max(0.0, _finite_or_zero(value)) for value in values)
    if not clean_values:
        return 0.0

    total = sum(clean_values)
    if total == 0 or clean_values[0] == clean_values[-1]:
        return 0.0

    count = len(clean_values)
    weighted_sum = sum(
        (2 * index - count - 1) * value
        for index, value in enumerate(clean_values, start=1)
    )
    return min(1.0, max(0.0, weighted_sum / (count * total)))


def compute_alert_burden_index(region_day: pl.DataFrame) -> pl.DataFrame:
    alert_minutes = _normalized_expression(region_day, pl.col("alert_minutes_total"))
    alert_count = _normalized_expression(region_day, _alert_episode_count_expr(region_day))
    max_duration = _normalized_expression(
        region_day,
        pl.col("max_alert_duration").fill_null(0),
    )
    recovery_disruption = _normalized_expression(
        region_day,
        1 - (pl.col("longest_alert_free_window_minutes").fill_null(DAY_MINUTES) / DAY_MINUTES),
    )
    values = [
        min(
            1.0,
            max(
                0.0,
                0.50 * minutes
                + 0.20 * count
                + 0.20 * duration
                + 0.10 * recovery,
            ),
        )
        for minutes, count, duration, recovery in zip(
            alert_minutes,
            alert_count,
            max_duration,
            recovery_disruption,
            strict=True,
        )
    ]
    return region_day.with_columns(pl.Series("alert_burden_index", values))


def compute_sleep_disruption_index(region_day: pl.DataFrame) -> pl.DataFrame:
    return region_day.with_columns(
        (pl.col("alert_minutes_night") / DEFAULT_SLEEP_WINDOW_MINUTES)
        .clip(0, 1)
        .alias("sleep_disruption_index")
    )


def compute_workday_disruption_index(region_day: pl.DataFrame) -> pl.DataFrame:
    return region_day.with_columns(
        (pl.col("alert_minutes_workday") / DEFAULT_WORK_WINDOW_MINUTES)
        .clip(0, 1)
        .alias("workday_disruption_index")
    )


def compute_recovery_metrics(region_day: pl.DataFrame) -> pl.DataFrame:
    return region_day.with_columns(
        (pl.col("longest_alert_free_window_minutes") / DAY_MINUTES)
        .clip(0, 1)
        .alias("alert_free_window_share"),
        (pl.col("longest_alert_free_window_minutes") < 8 * 60).alias(
            "low_recovery_day"
        ),
    )


def compute_daily_inequality_metrics(region_day_metrics: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for date_value, day_df in region_day_metrics.partition_by(
        "date",
        as_dict=True,
    ).items():
        if isinstance(date_value, tuple):
            date_value = date_value[0]

        alert_minutes = day_df["alert_minutes_total"].to_list()
        burden_index = day_df["alert_burden_index"].to_list()
        rows.append(
            {
                "date": date_value,
                "gini_alert_minutes_total": gini(alert_minutes),
                "gini_alert_burden_index": gini(burden_index),
                "top_bottom_alert_minutes_ratio": _top_bottom_ratio(alert_minutes),
            }
        )
    return pl.DataFrame(rows).sort("date")


def build_region_day_metrics(region_day_features: pl.DataFrame) -> pl.DataFrame:
    metrics = compute_alert_burden_index(region_day_features)
    metrics = compute_sleep_disruption_index(metrics)
    metrics = compute_workday_disruption_index(metrics)
    metrics = compute_recovery_metrics(metrics)
    metrics = metrics.with_columns(
        pl.Series(
            "alert_burden_category",
            [categorize_metric(value) for value in metrics["alert_burden_index"]],
        ),
        pl.Series(
            "sleep_disruption_category",
            [categorize_metric(value) for value in metrics["sleep_disruption_index"]],
        ),
        pl.Series(
            "workday_disruption_category",
            [categorize_metric(value) for value in metrics["workday_disruption_index"]],
        ),
    )
    daily_inequality = compute_daily_inequality_metrics(metrics)
    return metrics.join(daily_inequality, on="date", how="left").sort(
        ["region_name", "date"]
    )


def build_region_summary_metrics(region_day_metrics: pl.DataFrame) -> pl.DataFrame:
    return (
        region_day_metrics.group_by(["region_id", "region_name"])
        .agg(
            pl.col("date").min().alias("date_start"),
            pl.col("date").max().alias("date_end"),
            pl.len().alias("days_count"),
            pl.col("alert_minutes_total").sum().alias("total_alert_minutes"),
            pl.col("alert_minutes_total").mean().alias("mean_daily_alert_minutes"),
            pl.col("alert_minutes_total").median().alias("median_daily_alert_minutes"),
            pl.col("alert_minutes_total").max().alias("max_daily_alert_minutes"),
            pl.col("alert_count").sum().alias("total_alert_count"),
            pl.col("alert_count").mean().alias("mean_daily_alert_count"),
            pl.col("alert_minutes_night").sum().alias("total_night_alert_minutes"),
            pl.col("sleep_disruption_index").mean().alias(
                "mean_sleep_disruption_index"
            ),
            (pl.col("sleep_disruption_category") == "high")
            .sum()
            .alias("high_sleep_disruption_days"),
            pl.col("alert_minutes_workday").sum().alias(
                "total_workday_alert_minutes"
            ),
            pl.col("workday_disruption_index").mean().alias(
                "mean_workday_disruption_index"
            ),
            (pl.col("workday_disruption_category") == "high")
            .sum()
            .alias("high_workday_disruption_days"),
            pl.col("alert_burden_index").mean().alias("mean_alert_burden_index"),
            (pl.col("alert_burden_category") == "high")
            .sum()
            .alias("high_alert_burden_days"),
            pl.col("longest_alert_free_window_minutes")
            .mean()
            .alias("mean_longest_alert_free_window_minutes"),
            pl.col("low_recovery_day").sum().alias("low_recovery_days"),
            (pl.col("alert_minutes_total") > 0).sum().alias("days_with_any_alert"),
        )
        .with_columns(
            (
                pl.col("days_with_any_alert") / pl.col("days_count")
            ).alias("share_days_with_any_alert")
        )
        .sort("region_name")
    )


def build_national_summary_metrics(
    region_day_metrics: pl.DataFrame,
    national_day_features: pl.DataFrame,
) -> pl.DataFrame:
    inequality = (
        region_day_metrics.group_by("date")
        .agg(
            pl.col("gini_alert_minutes_total")
            .first()
            .alias("gini_alert_minutes_total"),
            pl.col("gini_alert_burden_index").first().alias(
                "gini_alert_burden_index"
            ),
        )
        .sort("date")
    )
    national = national_day_features.join(inequality, on="date", how="left")
    return national.select(
        pl.col("date").min().alias("date_start"),
        pl.col("date").max().alias("date_end"),
        pl.len().alias("days_count"),
        pl.col("total_alert_minutes_all_regions")
        .sum()
        .alias("total_alert_minutes_all_regions"),
        pl.col("total_alert_minutes_all_regions")
        .mean()
        .alias("mean_daily_total_alert_minutes_all_regions"),
        pl.col("total_alert_minutes_all_regions")
        .max()
        .alias("max_daily_total_alert_minutes_all_regions"),
        pl.col("regions_with_alerts_count")
        .mean()
        .alias("mean_regions_with_alerts_count"),
        pl.col("regions_with_alerts_count")
        .max()
        .alias("max_regions_with_alerts_count"),
        pl.col("national_alert_burden_index")
        .mean()
        .alias("mean_national_alert_burden_index"),
        pl.col("max_regions_simultaneously_alerted")
        .max()
        .alias("max_regions_simultaneously_alerted_observed"),
        pl.col("gini_alert_minutes_total")
        .mean()
        .alias("mean_gini_alert_minutes_total"),
        pl.col("gini_alert_burden_index").mean().alias(
            "mean_gini_alert_burden_index"
        ),
    )


def validate_metric_ranges(region_day_metrics: pl.DataFrame) -> dict:
    checks = {
        "alert_burden_index": _range_check(
            region_day_metrics,
            "alert_burden_index",
            0,
            1,
        ),
        "sleep_disruption_index": _range_check(
            region_day_metrics,
            "sleep_disruption_index",
            0,
            1,
        ),
        "workday_disruption_index": _range_check(
            region_day_metrics,
            "workday_disruption_index",
            0,
            1,
        ),
        "alert_free_window_share": _range_check(
            region_day_metrics,
            "alert_free_window_share",
            0,
            1,
        ),
        "gini_alert_minutes_total": _range_check(
            region_day_metrics,
            "gini_alert_minutes_total",
            0,
            1,
        ),
        "gini_alert_burden_index": _range_check(
            region_day_metrics,
            "gini_alert_burden_index",
            0,
            1,
        ),
    }
    category_checks = {
        column: set(region_day_metrics[column].drop_nulls().unique().to_list())
        <= ALLOWED_CATEGORIES
        for column in [
            "alert_burden_category",
            "sleep_disruption_category",
            "workday_disruption_category",
        ]
    }
    return {
        "passed": all(check["passed"] for check in checks.values())
        and all(category_checks.values())
        and not has_infinite_values(region_day_metrics),
        "checks": checks,
        "category_checks": category_checks,
        "has_infinite_values": has_infinite_values(region_day_metrics),
    }


def write_metrics_validation_report(
    region_day_metrics: pl.DataFrame,
    region_summary: pl.DataFrame,
    national_summary: pl.DataFrame,
    output_path: str | Path = METRICS_VALIDATION_REPORT_PATH,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    validation = validate_metric_ranges(region_day_metrics)
    checks = validation["checks"]
    profile = _metrics_profile(region_day_metrics)
    category_counts = _category_counts(region_day_metrics)

    report = f"""# Milestone 4 Metrics Validation

Generated at UTC: {datetime.now(timezone.utc).isoformat()}

## Inputs

- `{_display_path(REGION_DAY_FEATURES_PATH)}`: {region_day_metrics.height} rows after metric build
- `{_display_path(NATIONAL_DAY_FEATURES_PATH)}`: {national_summary["days_count"][0]} national-day rows summarized

## Outputs

- `{_display_path(REGION_DAY_METRICS_PATH)}`: {region_day_metrics.height} rows
- `{_display_path(REGION_SUMMARY_METRICS_PATH)}`: {region_summary.height} rows
- `{_display_path(NATIONAL_SUMMARY_METRICS_PATH)}`: {national_summary.height} rows

## Coverage

- Date start: {profile["date_start"]}
- Date end: {profile["date_end"]}
- Regions: {profile["region_count"]}

## Metric Formulas

- Alert Burden Index: 0.50 * normalized(alert_minutes_total) + 0.20 * normalized(merged_alert_episode_count) + 0.20 * normalized(max_alert_duration) + 0.10 * normalized(1 - longest_alert_free_window_minutes / 1440).
- ABI uses `merged_alert_episode_count`, not raw source record count, so overlapping administrative records do not inflate the count component.
- Min-max normalization is computed over the observed region-day table at build time. A future refresh can rescale historical ABI values if new minima or maxima enter the dataset.
- Sleep Disruption Index: alert_minutes_night / 540.
- Work/Study Disruption Index: alert_minutes_workday / 540.
- Alert-free recovery: alert_free_window_share = longest_alert_free_window_minutes / 1440; low_recovery_day is true when the longest alert-free window is less than 8 hours.
- Regional inequality: daily Gini values across regions for alert minutes and ABI; top-bottom ratio compares mean top 20% alert minutes with mean bottom 20%.

## Metric Range Checks

| Metric | Min | Max | Expected range | Passed |
| --- | ---: | ---: | --- | --- |
{_range_markdown_row("alert_burden_index", checks)}
{_range_markdown_row("sleep_disruption_index", checks)}
{_range_markdown_row("workday_disruption_index", checks)}
{_range_markdown_row("alert_free_window_share", checks)}
{_range_markdown_row("gini_alert_minutes_total", checks)}
{_range_markdown_row("gini_alert_burden_index", checks)}

Validation passed: {validation["passed"]}

## Category Counts

### Alert Burden Category

{_category_markdown(category_counts["alert_burden_category"])}

### Sleep Disruption Category

{_category_markdown(category_counts["sleep_disruption_category"])}

### Workday Disruption Category

{_category_markdown(category_counts["workday_disruption_category"])}

## Top Regions

### Mean Alert Burden Index

{_top_regions_markdown(region_summary, "mean_alert_burden_index")}

### Mean Sleep Disruption Index

{_top_regions_markdown(region_summary, "mean_sleep_disruption_index")}

### Mean Workday Disruption Index

{_top_regions_markdown(region_summary, "mean_workday_disruption_index")}

## Safety Note

These metrics measure historical civilian alert burden and disruption. They are descriptive only and are not designed for forecasting or real-time decision-making.

## Known Limitations

- Metric weights are analytic design choices and should be interpreted as descriptive indicators.
- ABI values are refresh-relative because min-max normalization is rebuilt from the current processed dataset.
- Sleep/work windows are default assumptions and may not match every person or institution.
- Sleep disruption is based on calendar-day Kyiv-local night hours, not individual sleep episodes.
- Region-level aggregation may hide within-region variation.
- Metrics are descriptive, not causal.
- High burden should not be read as a future danger signal.
"""
    output_path.write_text(report, encoding="utf-8")


def has_infinite_values(df: pl.DataFrame) -> bool:
    float_columns = [
        name
        for name, dtype in df.schema.items()
        if dtype in {pl.Float32, pl.Float64}
    ]
    if not float_columns:
        return False

    counts = df.select(pl.col(float_columns).is_infinite().sum()).row(0)
    return any(count > 0 for count in counts)


def _normalized_expression(region_day: pl.DataFrame, expr: pl.Expr) -> list[float]:
    return minmax_normalize(
        region_day.select(expr.alias("_value")).to_series().to_list()
    )


def _alert_episode_count_expr(region_day: pl.DataFrame) -> pl.Expr:
    if "merged_alert_episode_count" in region_day.columns:
        return pl.col("merged_alert_episode_count")
    return pl.col("alert_count")


def _top_bottom_ratio(values: list[float | int | None]) -> float | None:
    clean_values = sorted(max(0.0, _finite_or_zero(value)) for value in values)
    if not clean_values:
        return None

    group_size = max(1, ceil(len(clean_values) * 0.20))
    bottom_mean = sum(clean_values[:group_size]) / group_size
    top_mean = sum(clean_values[-group_size:]) / group_size
    if bottom_mean == 0 and top_mean > 0:
        return None
    if bottom_mean == 0 and top_mean == 0:
        return 1.0
    return safe_divide(top_mean, bottom_mean)


def _finite_or_zero(value: float | int | None) -> float:
    if value is None:
        return 0.0
    numeric_value = float(value)
    return numeric_value if isfinite(numeric_value) else 0.0


def _range_check(df: pl.DataFrame, column: str, lower: float, upper: float) -> dict:
    result = df.select(
        pl.col(column).min().alias("min"),
        pl.col(column).max().alias("max"),
    ).row(0, named=True)
    minimum = result["min"]
    maximum = result["max"]
    passed = (
        minimum is None
        or maximum is None
        or (minimum >= lower and maximum <= upper)
    )
    return {
        "min": minimum,
        "max": maximum,
        "lower": lower,
        "upper": upper,
        "passed": passed,
    }


def _metrics_profile(region_day_metrics: pl.DataFrame) -> dict:
    row = region_day_metrics.select(
        pl.col("date").min().alias("date_start"),
        pl.col("date").max().alias("date_end"),
        pl.col("region_name").n_unique().alias("region_count"),
    ).row(0, named=True)
    return row


def _category_counts(region_day_metrics: pl.DataFrame) -> dict[str, dict[str, int]]:
    output = {}
    for column in [
        "alert_burden_category",
        "sleep_disruption_category",
        "workday_disruption_category",
    ]:
        rows = region_day_metrics.group_by(column).len().sort(column).iter_rows()
        output[column] = {category: count for category, count in rows}
    return output


def _range_markdown_row(metric: str, checks: dict) -> str:
    check = checks[metric]
    return (
        f"| {metric} | {_format_value(check['min'])} | "
        f"{_format_value(check['max'])} | {check['lower']} to {check['upper']} | "
        f"{check['passed']} |"
    )


def _category_markdown(counts: dict[str, int]) -> str:
    return "\n".join(
        f"- {category}: {counts.get(category, 0)}"
        for category in ["low", "medium", "high"]
    )


def _top_regions_markdown(region_summary: pl.DataFrame, column: str) -> str:
    rows = (
        region_summary.sort(column, descending=True)
        .select("region_name", column)
        .head(10)
        .iter_rows()
    )
    return "\n".join(
        f"- {region_name}: {value:.4f}" for region_name, value in rows
    )


def _format_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
