from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

from air_alerts.features import (
    DST_LIMITATION_NOTE,
    build_national_day_features,
    build_region_day_features,
    build_region_hour_features,
    longest_alert_free_window,
    overlap_minutes,
    validate_feature_ranges,
    write_feature_validation_report,
)

KYIV = ZoneInfo("Europe/Kyiv")


def test_overlap_inside_window() -> None:
    start = datetime(2022, 1, 1, 10, 15)
    end = datetime(2022, 1, 1, 10, 45)
    window_start = datetime(2022, 1, 1, 10)
    window_end = datetime(2022, 1, 1, 11)

    assert overlap_minutes(start, end, window_start, window_end) == 30


def test_overlap_outside_window() -> None:
    assert (
        overlap_minutes(
            datetime(2022, 1, 1, 8),
            datetime(2022, 1, 1, 9),
            datetime(2022, 1, 1, 10),
            datetime(2022, 1, 1, 11),
        )
        == 0
    )


def test_partial_overlap_at_beginning_of_window() -> None:
    assert (
        overlap_minutes(
            datetime(2022, 1, 1, 9, 30),
            datetime(2022, 1, 1, 10, 30),
            datetime(2022, 1, 1, 10),
            datetime(2022, 1, 1, 11),
        )
        == 30
    )


def test_partial_overlap_at_end_of_window() -> None:
    assert (
        overlap_minutes(
            datetime(2022, 1, 1, 10, 30),
            datetime(2022, 1, 1, 11, 30),
            datetime(2022, 1, 1, 10),
            datetime(2022, 1, 1, 11),
        )
        == 30
    )


def test_cross_midnight_overlap() -> None:
    assert (
        overlap_minutes(
            datetime(2022, 1, 1, 23, 30),
            datetime(2022, 1, 2),
            datetime(2022, 1, 1, 23),
            datetime(2022, 1, 2),
        )
        == 30
    )


def test_no_negative_overlap() -> None:
    assert (
        overlap_minutes(
            datetime(2022, 1, 1, 12),
            datetime(2022, 1, 1, 11),
            datetime(2022, 1, 1, 10),
            datetime(2022, 1, 1, 11),
        )
        == 0
    )


def test_longest_alert_free_window_with_no_alerts_returns_1440() -> None:
    day_start = datetime.combine(datetime(2022, 1, 1).date(), time.min)
    day_end = day_start + timedelta(days=1)

    assert longest_alert_free_window([], day_start, day_end) == 1440


def test_longest_alert_free_window_with_full_day_alert_returns_zero() -> None:
    day_start = datetime.combine(datetime(2022, 1, 1).date(), time.min)
    day_end = day_start + timedelta(days=1)

    assert longest_alert_free_window([(day_start, day_end)], day_start, day_end) == 0


def test_overlapping_intervals_do_not_double_count_daily_minutes() -> None:
    alerts = _alerts_frame(
        [
            ("Kyiv City", _kyiv_to_utc(2022, 1, 1, 0, 0), _kyiv_to_utc(2022, 1, 1, 1, 0)),
            ("Kyiv City", _kyiv_to_utc(2022, 1, 1, 0, 30), _kyiv_to_utc(2022, 1, 1, 1, 30)),
        ]
    )

    region_hour = build_region_hour_features(alerts)
    region_day = build_region_day_features(alerts, region_hour)

    assert region_day.select("alert_minutes_total").item() == 90
    row = region_day.row(0, named=True)
    assert row["raw_alert_record_count"] == 2
    assert row["merged_alert_episode_count"] == 1
    assert row["alert_count"] == 1


def test_administrative_duplicate_records_do_not_inflate_merged_episode_count() -> None:
    start = _kyiv_to_utc(2022, 1, 1, 4, 0)
    end = _kyiv_to_utc(2022, 1, 1, 5, 0)
    alerts = _alerts_frame(
        [
            ("Kyiv City", start, end),
            ("Kyiv City", start, end),
        ]
    )

    region_hour = build_region_hour_features(alerts)
    region_day = build_region_day_features(alerts, region_hour)

    row = region_day.row(0, named=True)
    assert row["alert_minutes_total"] == 60
    assert row["raw_alert_record_count"] == 2
    assert row["merged_alert_episode_count"] == 1
    assert row["alert_count"] == 1


def test_cross_midnight_intervals_split_correctly_by_local_date() -> None:
    alerts = _alerts_frame(
        [
            (
                "Kyiv City",
                _kyiv_to_utc(2022, 1, 1, 23, 30),
                _kyiv_to_utc(2022, 1, 2, 0, 30),
            ),
        ]
    )

    region_hour = build_region_hour_features(alerts)
    region_day = build_region_day_features(alerts, region_hour)
    rows = {row["date"]: row for row in region_day.iter_rows(named=True)}

    assert rows[date(2022, 1, 1)]["alert_minutes_total"] == 30
    assert rows[date(2022, 1, 2)]["alert_minutes_total"] == 30
    assert rows[date(2022, 1, 1)]["merged_alert_episode_count"] == 1
    assert rows[date(2022, 1, 2)]["merged_alert_episode_count"] == 1


def test_feature_report_documents_dst_wall_clock_limitation(tmp_path: Path) -> None:
    alerts = _alerts_frame(
        [
            (
                "Kyiv City",
                _kyiv_to_utc(2022, 3, 27, 1, 30),
                _kyiv_to_utc(2022, 3, 27, 3, 30),
            ),
        ]
    )
    region_hour = build_region_hour_features(alerts)
    region_day = build_region_day_features(alerts, region_hour)
    national_day = build_national_day_features(region_hour, region_day)
    output_path = tmp_path / "feature_validation.md"

    write_feature_validation_report(alerts, region_hour, region_day, national_day, output_path)

    assert DST_LIMITATION_NOTE in output_path.read_text(encoding="utf-8")


def test_alert_minutes_in_hour_bounded_between_0_and_60() -> None:
    region_hour, _, _ = _feature_tables_for_bounds()

    assert region_hour.select(
        pl.col("alert_minutes_in_hour").min().alias("min"),
        pl.col("alert_minutes_in_hour").max().alias("max"),
    ).row(0) == (0.0, 60.0)


def test_alert_minutes_total_bounded_between_0_and_1440() -> None:
    _, region_day, _ = _feature_tables_for_bounds()

    result = region_day.select(
        pl.col("alert_minutes_total").min().alias("min"),
        pl.col("alert_minutes_total").max().alias("max"),
    ).row(0)
    assert result[0] >= 0
    assert result[1] <= 1440


def test_alert_minutes_night_bounded_between_0_and_540() -> None:
    _, region_day, _ = _feature_tables_for_bounds()

    result = region_day.select(
        pl.col("alert_minutes_night").min().alias("min"),
        pl.col("alert_minutes_night").max().alias("max"),
    ).row(0)
    assert result[0] >= 0
    assert result[1] <= 540


def test_alert_minutes_workday_bounded_between_0_and_540() -> None:
    _, region_day, _ = _feature_tables_for_bounds()

    result = region_day.select(
        pl.col("alert_minutes_workday").min().alias("min"),
        pl.col("alert_minutes_workday").max().alias("max"),
    ).row(0)
    assert result[0] >= 0
    assert result[1] <= 540


def test_share_day_under_alert_bounded_between_0_and_1() -> None:
    _, region_day, _ = _feature_tables_for_bounds()

    result = region_day.select(
        pl.col("share_day_under_alert").min().alias("min"),
        pl.col("share_day_under_alert").max().alias("max"),
    ).row(0)
    assert result[0] >= 0
    assert result[1] <= 1


def test_national_alert_burden_index_bounded_between_0_and_1() -> None:
    region_hour, region_day, national_day = _feature_tables_for_bounds()
    validation = validate_feature_ranges(region_hour, region_day, national_day)

    assert validation["checks"]["national_alert_burden_index"]["min"] >= 0
    assert validation["checks"]["national_alert_burden_index"]["max"] <= 1
    assert validation["passed"] is True


def _feature_tables_for_bounds() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    alerts = _alerts_frame(
        [
            ("Kyiv City", _kyiv_to_utc(2022, 1, 3, 0, 0), _kyiv_to_utc(2022, 1, 3, 23, 0)),
            ("Kyiv City", _kyiv_to_utc(2022, 1, 3, 22, 0), _kyiv_to_utc(2022, 1, 4, 1, 0)),
            (
                "Lvivska oblast",
                _kyiv_to_utc(2022, 1, 3, 9, 0),
                _kyiv_to_utc(2022, 1, 3, 18, 0),
            ),
        ]
    )
    region_hour = build_region_hour_features(alerts)
    region_day = build_region_day_features(alerts, region_hour)
    national_day = build_national_day_features(region_hour, region_day)
    return region_hour, region_day, national_day


def _alerts_frame(
    rows: list[tuple[str, datetime, datetime]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "alert_id": list(range(1, len(rows) + 1)),
            "region": [row[0] for row in rows],
            "started_at_utc": [row[1] for row in rows],
            "finished_at_utc": [row[2] for row in rows],
            "duration_seconds": [
                int((row[2] - row[1]).total_seconds()) for row in rows
            ],
            "duration_minutes": [
                (row[2] - row[1]).total_seconds() / 60 for row in rows
            ],
        }
    )


def _kyiv_to_utc(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=KYIV).astimezone(
        timezone.utc
    )
