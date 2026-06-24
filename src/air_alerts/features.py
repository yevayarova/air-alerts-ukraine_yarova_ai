from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

import polars as pl

from air_alerts.config import (
    ALERTS_CLEAN_PATH,
    DEFAULT_SLEEP_END_HOUR,
    DEFAULT_SLEEP_START_HOUR,
    DEFAULT_WORK_END_HOUR,
    DEFAULT_WORK_START_HOUR,
    FEATURE_VALIDATION_REPORT_PATH,
    KYIV_TZ,
    NATIONAL_DAY_FEATURES_PATH,
    PROJECT_ROOT,
    REGION_DAY_FEATURES_PATH,
    REGION_HOUR_FEATURES_PATH,
)

KYIV_ZONE = ZoneInfo(KYIV_TZ)
DAY_MINUTES = 24 * 60
SLEEP_WINDOW_MINUTES = 9 * 60
WORK_WINDOW_MINUTES = 9 * 60
DST_LIMITATION_NOTE = (
    "Kyiv-local timestamps are represented as wall-clock hours for dashboard "
    "aggregation. Daylight saving transition days are kept on a 24-hour display "
    "grid, so repeated or skipped local clock hours are not modeled as separate "
    "dashboard buckets."
)


@dataclass(frozen=True)
class AlertRecord:
    alert_id: int | None
    region_name: str
    started_at_local: datetime
    finished_at_local: datetime
    duration_minutes: float


def overlap_minutes(
    start: datetime,
    end: datetime,
    window_start: datetime,
    window_end: datetime,
) -> float:
    if end <= start or window_end <= window_start:
        return 0.0

    overlap_start = max(start, window_start)
    overlap_end = min(end, window_end)
    if overlap_end <= overlap_start:
        return 0.0

    return (overlap_end - overlap_start).total_seconds() / 60


def build_region_hour_features(alerts: pl.DataFrame) -> pl.DataFrame:
    records = _prepare_alert_records(alerts)
    if not records:
        return _empty_region_hour()

    region_names = sorted({record.region_name for record in records})
    region_ids = _region_ids(region_names)
    start_date, end_date = _observed_date_range(records)
    merged_by_region = _merged_intervals_by_region(records)
    minutes_by_region_hour = _minutes_by_region_hour(merged_by_region)
    hours = list(_hour_range(start_date, end_date))

    columns = {
        "region_id": [],
        "region_name": [],
        "datetime_hour": [],
        "date": [],
        "alert_minutes_in_hour": [],
        "is_alert_active": [],
        "hour": [],
        "weekday": [],
        "month": [],
        "is_night": [],
        "is_work_hour": [],
    }

    for region_name in region_names:
        region_id = region_ids[region_name]
        for datetime_hour in hours:
            alert_minutes = min(
                60.0,
                max(0.0, minutes_by_region_hour.get((region_name, datetime_hour), 0.0)),
            )
            weekday = datetime_hour.weekday()
            hour = datetime_hour.hour
            columns["region_id"].append(region_id)
            columns["region_name"].append(region_name)
            columns["datetime_hour"].append(datetime_hour)
            columns["date"].append(datetime_hour.date())
            columns["alert_minutes_in_hour"].append(alert_minutes)
            columns["is_alert_active"].append(alert_minutes > 0)
            columns["hour"].append(hour)
            columns["weekday"].append(weekday)
            columns["month"].append(datetime_hour.month)
            columns["is_night"].append(_is_night_hour(hour))
            columns["is_work_hour"].append(_is_work_hour(weekday, hour))

    return pl.DataFrame(columns)


def build_region_day_features(
    alerts: pl.DataFrame,
    region_hour: pl.DataFrame,
) -> pl.DataFrame:
    records = _prepare_alert_records(alerts)
    if region_hour.is_empty():
        return _empty_region_day()

    daily_minutes = (
        region_hour.group_by(["region_id", "region_name", "date"])
        .agg(
            pl.col("alert_minutes_in_hour")
            .sum()
            .clip(0, DAY_MINUTES)
            .alias("alert_minutes_total"),
            pl.when(pl.col("is_night"))
            .then(pl.col("alert_minutes_in_hour"))
            .otherwise(0.0)
            .sum()
            .clip(0, SLEEP_WINDOW_MINUTES)
            .alias("alert_minutes_night"),
            pl.when(pl.col("is_work_hour"))
            .then(pl.col("alert_minutes_in_hour"))
            .otherwise(0.0)
            .sum()
            .clip(0, WORK_WINDOW_MINUTES)
            .alias("alert_minutes_workday"),
        )
        .sort(["region_name", "date"])
    )

    alert_stats = _daily_alert_stats(records)
    merged_day_intervals = _merged_day_intervals(records)

    rows = []
    for row in daily_minutes.iter_rows(named=True):
        key = (row["region_name"], row["date"])
        stats = alert_stats.get(key, _blank_day_stats())
        merged_intervals = merged_day_intervals.get(key, [])
        merged_episode_count = len(merged_intervals)
        day_start = datetime.combine(row["date"], time.min)
        day_end = day_start + timedelta(days=1)
        alert_minutes_total = float(row["alert_minutes_total"])
        alert_minutes_night = float(row["alert_minutes_night"])
        alert_minutes_workday = float(row["alert_minutes_workday"])
        rows.append(
            {
                "region_id": row["region_id"],
                "region_name": row["region_name"],
                "date": row["date"],
                "alert_count": merged_episode_count,
                "raw_alert_record_count": stats["raw_alert_record_count"],
                "merged_alert_episode_count": merged_episode_count,
                "alert_minutes_total": alert_minutes_total,
                "alert_minutes_night": alert_minutes_night,
                "alert_minutes_workday": alert_minutes_workday,
                "max_alert_duration": stats["max_alert_duration"],
                "median_alert_duration": stats["median_alert_duration"],
                "longest_alert_free_window_minutes": longest_alert_free_window(
                    merged_intervals,
                    day_start,
                    day_end,
                ),
                "share_day_under_alert": alert_minutes_total / DAY_MINUTES,
                "sleep_window_interrupted": alert_minutes_night > 0,
                "workday_interrupted": alert_minutes_workday > 0,
                "first_alert_time": stats["first_alert_time"],
                "last_alert_time": stats["last_alert_time"],
            }
        )

    return pl.DataFrame(rows).sort(["region_name", "date"])


def build_national_day_features(
    region_hour: pl.DataFrame,
    region_day: pl.DataFrame,
) -> pl.DataFrame:
    if region_hour.is_empty() or region_day.is_empty():
        return _empty_national_day()

    daily = (
        region_day.group_by("date")
        .agg(
            (pl.col("alert_minutes_total") > 0)
            .sum()
            .alias("regions_with_alerts_count"),
            pl.col("alert_minutes_total")
            .sum()
            .alias("total_alert_minutes_all_regions"),
        )
        .sort("date")
    )

    simultaneous = (
        region_hour.group_by(["date", "datetime_hour"])
        .agg(pl.col("is_alert_active").sum().alias("active_regions"))
        .group_by("date")
        .agg(
            pl.col("active_regions")
            .max()
            .alias("max_regions_simultaneously_alerted")
        )
    )

    national = daily.join(simultaneous, on="date", how="left")
    max_daily_total = national.select(
        pl.col("total_alert_minutes_all_regions").max()
    ).item()
    if max_daily_total is None or max_daily_total == 0:
        return national.with_columns(pl.lit(0.0).alias("national_alert_burden_index"))

    return national.with_columns(
        (
            pl.col("total_alert_minutes_all_regions") / float(max_daily_total)
        ).clip(0, 1).alias("national_alert_burden_index")
    )


def longest_alert_free_window(
    intervals: list[tuple[datetime, datetime]],
    day_start: datetime,
    day_end: datetime,
) -> float:
    if day_end <= day_start:
        return 0.0

    clipped = [
        (max(start, day_start), min(end, day_end))
        for start, end in intervals
        if overlap_minutes(start, end, day_start, day_end) > 0
    ]
    if not clipped:
        return (day_end - day_start).total_seconds() / 60

    merged = _merge_intervals(clipped)
    max_gap = max(0.0, (merged[0][0] - day_start).total_seconds() / 60)
    for previous, current in zip(merged, merged[1:], strict=False):
        gap = (current[0] - previous[1]).total_seconds() / 60
        max_gap = max(max_gap, gap)
    max_gap = max(max_gap, (day_end - merged[-1][1]).total_seconds() / 60)
    return max(0.0, max_gap)


def validate_feature_ranges(
    region_hour: pl.DataFrame,
    region_day: pl.DataFrame,
    national_day: pl.DataFrame,
) -> dict:
    checks = {
        "alert_minutes_in_hour": _range_check(
            region_hour,
            "alert_minutes_in_hour",
            0,
            60,
        ),
        "alert_minutes_total": _range_check(
            region_day,
            "alert_minutes_total",
            0,
            DAY_MINUTES,
        ),
        "alert_minutes_night": _range_check(
            region_day,
            "alert_minutes_night",
            0,
            SLEEP_WINDOW_MINUTES,
        ),
        "alert_minutes_workday": _range_check(
            region_day,
            "alert_minutes_workday",
            0,
            WORK_WINDOW_MINUTES,
        ),
        "share_day_under_alert": _range_check(
            region_day,
            "share_day_under_alert",
            0,
            1,
        ),
        "national_alert_burden_index": _range_check(
            national_day,
            "national_alert_burden_index",
            0,
            1,
        ),
    }
    return {
        "passed": all(check["passed"] for check in checks.values()),
        "checks": checks,
    }


def write_feature_validation_report(
    alerts: pl.DataFrame,
    region_hour: pl.DataFrame,
    region_day: pl.DataFrame,
    national_day: pl.DataFrame,
    output_path: str | Path = FEATURE_VALIDATION_REPORT_PATH,
) -> None:
    profile = profile_alerts(alerts)
    validation = validate_feature_ranges(region_hour, region_day, national_day)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    checks = validation["checks"]
    region_lines = "\n".join(f"- {region}" for region in profile["region_names"])
    report = f"""# Milestone 3 Feature Validation

Generated at UTC: {datetime.now(timezone.utc).isoformat()}

## Input

- Input file path: `{_display_path(ALERTS_CLEAN_PATH)}`
- Input row count: {profile["row_count"]}
- Coverage start: {profile["coverage_start"]}
- Coverage end: {profile["coverage_end"]}
- Number of regions: {profile["region_count"]}
- Timestamps timezone-aware: {profile["timestamps_timezone_aware"]}

## Regions

{region_lines}

## Outputs

- `{_display_path(REGION_HOUR_FEATURES_PATH)}`: {region_hour.height} rows
- `{_display_path(REGION_DAY_FEATURES_PATH)}`: {region_day.height} rows
- `{_display_path(NATIONAL_DAY_FEATURES_PATH)}`: {national_day.height} rows

## Metric Range Checks

| Metric | Min | Max | Expected range | Passed |
| --- | ---: | ---: | --- | --- |
{_range_markdown_row("alert_minutes_in_hour", checks)}
{_range_markdown_row("alert_minutes_total", checks)}
{_range_markdown_row("alert_minutes_night", checks)}
{_range_markdown_row("alert_minutes_workday", checks)}
{_range_markdown_row("share_day_under_alert", checks)}
{_range_markdown_row("national_alert_burden_index", checks)}

Validation passed: {validation["passed"]}

## Data Quality Notes

- Missing ended_at_utc values: {profile["missing_ended_at_utc"]}
- Zero or negative durations: {profile["zero_or_negative_durations"]}
- Duplicate alert_id values: {profile["duplicate_alert_ids"]}

## Alert Count Semantics

- `raw_alert_record_count` counts cleaned source records intersecting a region-date.
- `merged_alert_episode_count` counts merged, non-overlapping alert episodes after records are combined within the same region-date.
- `alert_count` is retained as a dashboard-compatible alias of `merged_alert_episode_count`.
- Alert minutes and recovery windows are computed from merged intervals, so overlapping administrative records do not double-count minutes.

## Safety Note

These features measure historical civilian alert burden and disruption. They are descriptive only and are not designed for forecasting or real-time decision-making.

## Known Limitations

- Sleep/work windows are default assumptions and may not match every person/institution.
- Calendar-day sleep minutes combine 00:00-07:00 and 22:00-24:00 Kyiv-local hours on the same date; they are not person-level sleep episodes.
- {DST_LIMITATION_NOTE}
- Region-level aggregation may hide within-region variation.
- Feature tables are descriptive, not causal.
"""
    output_path.write_text(report, encoding="utf-8")


def profile_alerts(alerts: pl.DataFrame) -> dict:
    row_count = alerts.height
    region_names = (
        alerts.select("region").unique().sort("region").to_series().to_list()
        if "region" in alerts.columns and row_count > 0
        else []
    )
    coverage_start = None
    coverage_end = None
    if row_count > 0 and {"started_at_utc", "finished_at_utc"} <= set(alerts.columns):
        coverage = alerts.select(
            pl.col("started_at_utc").min().alias("coverage_start"),
            pl.col("finished_at_utc").max().alias("coverage_end"),
        ).row(0, named=True)
        coverage_start = _iso_or_none(coverage["coverage_start"])
        coverage_end = _iso_or_none(coverage["coverage_end"])

    missing_ended = (
        alerts.select(pl.col("finished_at_utc").null_count()).item()
        if "finished_at_utc" in alerts.columns
        else row_count
    )
    zero_or_negative = (
        alerts.select((pl.col("duration_seconds") <= 0).sum()).item()
        if "duration_seconds" in alerts.columns
        else None
    )
    duplicate_alert_ids = (
        alerts.select((pl.len() - pl.col("alert_id").n_unique())).item()
        if "alert_id" in alerts.columns
        else None
    )

    return {
        "row_count": row_count,
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "region_count": len(region_names),
        "region_names": region_names,
        "missing_ended_at_utc": missing_ended,
        "zero_or_negative_durations": zero_or_negative,
        "timestamps_timezone_aware": _timestamps_timezone_aware(alerts),
        "duplicate_alert_ids": duplicate_alert_ids,
    }


def _prepare_alert_records(alerts: pl.DataFrame) -> list[AlertRecord]:
    required = {"region", "started_at_utc", "finished_at_utc"}
    missing = required - set(alerts.columns)
    if missing:
        raise ValueError(f"Missing required alert columns: {sorted(missing)}")

    records = []
    for row in alerts.iter_rows(named=True):
        start = row["started_at_utc"]
        end = row["finished_at_utc"]
        if start is None or end is None or end <= start:
            continue

        duration = row.get("duration_minutes")
        if duration is None:
            duration = (end - start).total_seconds() / 60
        duration_delta = timedelta(minutes=float(duration))
        local_start = _to_kyiv_wall_time(start)
        local_end = local_start + duration_delta

        records.append(
            AlertRecord(
                alert_id=row.get("alert_id"),
                region_name=row["region"],
                started_at_local=local_start,
                finished_at_local=local_end,
                duration_minutes=float(duration),
            )
        )
    return records


def _merged_intervals_by_region(
    records: list[AlertRecord],
) -> dict[str, list[tuple[datetime, datetime]]]:
    intervals_by_region = defaultdict(list)
    for record in records:
        intervals_by_region[record.region_name].append(
            (record.started_at_local, record.finished_at_local)
        )
    return {
        region: _merge_intervals(intervals)
        for region, intervals in intervals_by_region.items()
    }


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []

    intervals = sorted(intervals, key=lambda item: (item[0], item[1]))
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def _minutes_by_region_hour(
    merged_by_region: dict[str, list[tuple[datetime, datetime]]],
) -> dict[tuple[str, datetime], float]:
    minutes_by_hour = defaultdict(float)
    for region_name, intervals in merged_by_region.items():
        for start, end in intervals:
            datetime_hour = _floor_hour(start)
            while datetime_hour < end:
                hour_end = datetime_hour + timedelta(hours=1)
                minutes = overlap_minutes(start, end, datetime_hour, hour_end)
                if minutes > 0:
                    minutes_by_hour[(region_name, datetime_hour)] += minutes
                datetime_hour = hour_end
    return minutes_by_hour


def _daily_alert_stats(records: list[AlertRecord]) -> dict[tuple[str, date], dict]:
    stats = defaultdict(
        lambda: {
            "raw_alert_record_count": 0,
            "durations": [],
            "first_alert_time": None,
            "last_alert_time": None,
        }
    )
    for record in records:
        for day in _intersecting_dates(record.started_at_local, record.finished_at_local):
            day_start = datetime.combine(day, time.min)
            day_end = day_start + timedelta(days=1)
            if overlap_minutes(
                record.started_at_local,
                record.finished_at_local,
                day_start,
                day_end,
            ) <= 0:
                continue

            key = (record.region_name, day)
            intersection_start = max(record.started_at_local, day_start)
            intersection_end = min(record.finished_at_local, day_end)
            stats[key]["raw_alert_record_count"] += 1
            stats[key]["durations"].append(record.duration_minutes)
            stats[key]["first_alert_time"] = _min_optional_datetime(
                stats[key]["first_alert_time"],
                intersection_start,
            )
            stats[key]["last_alert_time"] = _max_optional_datetime(
                stats[key]["last_alert_time"],
                intersection_end,
            )

    return {
        key: {
            "raw_alert_record_count": value["raw_alert_record_count"],
            "max_alert_duration": max(value["durations"]),
            "median_alert_duration": float(median(value["durations"])),
            "first_alert_time": value["first_alert_time"],
            "last_alert_time": value["last_alert_time"],
        }
        for key, value in stats.items()
    }


def _merged_day_intervals(
    records: list[AlertRecord],
) -> dict[tuple[str, date], list[tuple[datetime, datetime]]]:
    merged_by_region = _merged_intervals_by_region(records)
    intervals_by_day = defaultdict(list)
    for region_name, intervals in merged_by_region.items():
        for start, end in intervals:
            for day in _intersecting_dates(start, end):
                day_start = datetime.combine(day, time.min)
                day_end = day_start + timedelta(days=1)
                if overlap_minutes(start, end, day_start, day_end) > 0:
                    intervals_by_day[(region_name, day)].append(
                        (max(start, day_start), min(end, day_end))
                    )
    return {
        key: _merge_intervals(intervals)
        for key, intervals in intervals_by_day.items()
    }


def _intersecting_dates(start: datetime, end: datetime) -> list[date]:
    if end <= start:
        return []

    current = start.date()
    final = (end - timedelta(microseconds=1)).date()
    days = []
    while current <= final:
        days.append(current)
        current += timedelta(days=1)
    return days


def _observed_date_range(records: list[AlertRecord]) -> tuple[date, date]:
    start_date = min(record.started_at_local.date() for record in records)
    end_date = max(
        (record.finished_at_local - timedelta(microseconds=1)).date()
        for record in records
    )
    return start_date, end_date


def _hour_range(start_date: date, end_date: date) -> list[datetime]:
    current = datetime.combine(start_date, time.min)
    end = datetime.combine(end_date + timedelta(days=1), time.min)
    hours = []
    while current < end:
        hours.append(current)
        current += timedelta(hours=1)
    return hours


def _region_ids(region_names: list[str]) -> dict[str, int]:
    return {region_name: index for index, region_name in enumerate(region_names, 1)}


def _floor_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _is_night_hour(hour: int) -> bool:
    return hour >= DEFAULT_SLEEP_START_HOUR or hour < DEFAULT_SLEEP_END_HOUR


def _is_work_hour(weekday: int, hour: int) -> bool:
    return weekday < 5 and DEFAULT_WORK_START_HOUR <= hour < DEFAULT_WORK_END_HOUR


def _to_kyiv_wall_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KYIV_ZONE).replace(tzinfo=None)


def _blank_day_stats() -> dict:
    return {
        "raw_alert_record_count": 0,
        "max_alert_duration": None,
        "median_alert_duration": None,
        "first_alert_time": None,
        "last_alert_time": None,
    }


def _min_optional_datetime(left: datetime | None, right: datetime) -> datetime:
    if left is None:
        return right
    return min(left, right)


def _max_optional_datetime(left: datetime | None, right: datetime) -> datetime:
    if left is None:
        return right
    return max(left, right)


def _range_check(df: pl.DataFrame, column: str, lower: float, upper: float) -> dict:
    if df.is_empty():
        return {
            "min": None,
            "max": None,
            "lower": lower,
            "upper": upper,
            "passed": True,
        }

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


def _range_markdown_row(metric: str, checks: dict) -> str:
    check = checks[metric]
    return (
        f"| {metric} | {_format_value(check['min'])} | "
        f"{_format_value(check['max'])} | {check['lower']} to {check['upper']} | "
        f"{check['passed']} |"
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


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _timestamps_timezone_aware(alerts: pl.DataFrame) -> bool:
    start_dtype = alerts.schema.get("started_at_utc")
    end_dtype = alerts.schema.get("finished_at_utc")
    return _dtype_has_timezone(start_dtype) and _dtype_has_timezone(end_dtype)


def _dtype_has_timezone(dtype: object) -> bool:
    return "time_zone" in repr(dtype) or "UTC" in str(dtype)


def _empty_region_hour() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "region_id": pl.Int64,
            "region_name": pl.String,
            "datetime_hour": pl.Datetime,
            "date": pl.Date,
            "alert_minutes_in_hour": pl.Float64,
            "is_alert_active": pl.Boolean,
            "hour": pl.Int64,
            "weekday": pl.Int64,
            "month": pl.Int64,
            "is_night": pl.Boolean,
            "is_work_hour": pl.Boolean,
        }
    )


def _empty_region_day() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "region_id": pl.Int64,
            "region_name": pl.String,
            "date": pl.Date,
            "alert_count": pl.Int64,
            "raw_alert_record_count": pl.Int64,
            "merged_alert_episode_count": pl.Int64,
            "alert_minutes_total": pl.Float64,
            "alert_minutes_night": pl.Float64,
            "alert_minutes_workday": pl.Float64,
            "max_alert_duration": pl.Float64,
            "median_alert_duration": pl.Float64,
            "longest_alert_free_window_minutes": pl.Float64,
            "share_day_under_alert": pl.Float64,
            "sleep_window_interrupted": pl.Boolean,
            "workday_interrupted": pl.Boolean,
            "first_alert_time": pl.Datetime,
            "last_alert_time": pl.Datetime,
        }
    )


def _empty_national_day() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "date": pl.Date,
            "regions_with_alerts_count": pl.Int64,
            "total_alert_minutes_all_regions": pl.Float64,
            "max_regions_simultaneously_alerted": pl.Int64,
            "national_alert_burden_index": pl.Float64,
        }
    )
