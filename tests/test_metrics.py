from __future__ import annotations

from datetime import date, datetime
from math import isfinite

import polars as pl

from air_alerts.metrics import (
    categorize_metric,
    compute_daily_inequality_metrics,
    gini,
    has_infinite_values,
    minmax_normalize,
    safe_divide,
    build_national_summary_metrics,
    build_region_day_metrics,
    build_region_summary_metrics,
    validate_metric_ranges,
)


def test_minmax_normalize_returns_values_between_0_and_1() -> None:
    values = minmax_normalize([10, 20, 30])

    assert values == [0.0, 0.5, 1.0]


def test_minmax_normalize_handles_constant_input_without_division_by_zero() -> None:
    assert minmax_normalize([5, 5, 5]) == [0.0, 0.0, 0.0]


def test_safe_divide_handles_zero_denominator() -> None:
    assert safe_divide(10, 0) is None
    assert safe_divide(10, 2) == 5


def test_categorize_metric_returns_low_medium_high_correctly() -> None:
    assert categorize_metric(0.0) == "low"
    assert categorize_metric(0.33) == "medium"
    assert categorize_metric(0.66) == "high"


def test_gini_returns_zero_for_equal_values() -> None:
    assert gini([3, 3, 3]) == 0


def test_gini_returns_zero_when_all_values_are_zero() -> None:
    assert gini([0, 0, 0]) == 0


def test_gini_returns_positive_value_for_unequal_values() -> None:
    assert gini([0, 0, 10]) > 0


def test_alert_burden_index_is_bounded_between_0_and_1() -> None:
    metrics = build_region_day_metrics(_region_day_features())
    result = metrics.select(
        pl.col("alert_burden_index").min().alias("min"),
        pl.col("alert_burden_index").max().alias("max"),
    ).row(0)

    assert result[0] >= 0
    assert result[1] <= 1


def test_alert_burden_index_uses_merged_episode_count_not_raw_records() -> None:
    data = pl.DataFrame(
        {
            "region_id": [1, 2],
            "region_name": ["Kyiv City", "Lvivska oblast"],
            "date": [date(2022, 1, 1), date(2022, 1, 1)],
            "alert_count": [1, 1],
            "raw_alert_record_count": [1, 100],
            "merged_alert_episode_count": [1, 1],
            "alert_minutes_total": [60.0, 60.0],
            "alert_minutes_night": [0.0, 0.0],
            "alert_minutes_workday": [0.0, 0.0],
            "max_alert_duration": [60.0, 60.0],
            "median_alert_duration": [60.0, 60.0],
            "longest_alert_free_window_minutes": [1380.0, 1380.0],
            "share_day_under_alert": [60.0 / 1440.0, 60.0 / 1440.0],
            "sleep_window_interrupted": [False, False],
            "workday_interrupted": [False, False],
            "first_alert_time": [datetime(2022, 1, 1, 1), datetime(2022, 1, 1, 1)],
            "last_alert_time": [datetime(2022, 1, 1, 2), datetime(2022, 1, 1, 2)],
        }
    )

    metrics = build_region_day_metrics(data)

    assert metrics["alert_burden_index"].to_list() == [0.0, 0.0]


def test_sleep_disruption_index_is_bounded_between_0_and_1() -> None:
    metrics = build_region_day_metrics(_region_day_features())
    result = metrics.select(
        pl.col("sleep_disruption_index").min().alias("min"),
        pl.col("sleep_disruption_index").max().alias("max"),
    ).row(0)

    assert result[0] >= 0
    assert result[1] <= 1


def test_workday_disruption_index_is_bounded_between_0_and_1() -> None:
    metrics = build_region_day_metrics(_region_day_features())
    result = metrics.select(
        pl.col("workday_disruption_index").min().alias("min"),
        pl.col("workday_disruption_index").max().alias("max"),
    ).row(0)

    assert result[0] >= 0
    assert result[1] <= 1


def test_alert_free_window_share_is_bounded_between_0_and_1() -> None:
    metrics = build_region_day_metrics(_region_day_features())
    result = metrics.select(
        pl.col("alert_free_window_share").min().alias("min"),
        pl.col("alert_free_window_share").max().alias("max"),
    ).row(0)

    assert result[0] >= 0
    assert result[1] <= 1


def test_daily_inequality_metrics_are_bounded_between_0_and_1_where_applicable() -> None:
    metrics = build_region_day_metrics(_region_day_features())
    inequality = compute_daily_inequality_metrics(metrics)

    assert inequality["gini_alert_minutes_total"].min() >= 0
    assert inequality["gini_alert_minutes_total"].max() <= 1
    assert inequality["gini_alert_burden_index"].min() >= 0
    assert inequality["gini_alert_burden_index"].max() <= 1


def test_category_columns_contain_only_low_medium_high() -> None:
    metrics = build_region_day_metrics(_region_day_features())
    validation = validate_metric_ranges(metrics)

    assert validation["category_checks"] == {
        "alert_burden_category": True,
        "sleep_disruption_category": True,
        "workday_disruption_category": True,
    }


def test_no_infinite_values_are_produced() -> None:
    metrics = build_region_day_metrics(_region_day_features())

    assert has_infinite_values(metrics) is False


def test_zero_alert_days_produce_valid_finite_metrics() -> None:
    metrics = build_region_day_metrics(_region_day_features())
    zero_day = metrics.filter(
        (pl.col("region_name") == "Kyiv City") & (pl.col("date") == date(2022, 1, 1))
    ).row(0, named=True)

    assert zero_day["sleep_disruption_index"] == 0
    assert zero_day["workday_disruption_index"] == 0
    assert zero_day["alert_free_window_share"] == 1
    assert zero_day["low_recovery_day"] is False
    assert isfinite(zero_day["alert_burden_index"])


def test_region_summary_has_one_row_per_region() -> None:
    metrics = build_region_day_metrics(_region_day_features())
    summary = build_region_summary_metrics(metrics)

    assert summary.height == metrics["region_name"].n_unique()


def test_national_summary_has_one_row() -> None:
    metrics = build_region_day_metrics(_region_day_features())
    summary = build_national_summary_metrics(metrics, _national_day_features())

    assert summary.height == 1


def _region_day_features() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "region_id": [1, 1, 2, 2],
            "region_name": [
                "Kyiv City",
                "Kyiv City",
                "Lvivska oblast",
                "Lvivska oblast",
            ],
            "date": [
                date(2022, 1, 1),
                date(2022, 1, 2),
                date(2022, 1, 1),
                date(2022, 1, 2),
            ],
            "alert_count": [0, 2, 1, 1],
            "raw_alert_record_count": [0, 4, 1, 2],
            "merged_alert_episode_count": [0, 2, 1, 1],
            "alert_minutes_total": [0.0, 540.0, 60.0, 1440.0],
            "alert_minutes_night": [0.0, 120.0, 60.0, 540.0],
            "alert_minutes_workday": [0.0, 240.0, 30.0, 540.0],
            "max_alert_duration": [None, 300.0, 60.0, 1440.0],
            "median_alert_duration": [None, 150.0, 60.0, 720.0],
            "longest_alert_free_window_minutes": [1440.0, 600.0, 1380.0, 0.0],
            "share_day_under_alert": [0.0, 0.375, 0.0417, 1.0],
            "sleep_window_interrupted": [False, True, True, True],
            "workday_interrupted": [False, True, True, True],
            "first_alert_time": [
                None,
                datetime(2022, 1, 2, 1),
                datetime(2022, 1, 1, 2),
                datetime(2022, 1, 2, 0),
            ],
            "last_alert_time": [
                None,
                datetime(2022, 1, 2, 5),
                datetime(2022, 1, 1, 3),
                datetime(2022, 1, 3, 0),
            ],
        }
    )


def _national_day_features() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": [date(2022, 1, 1), date(2022, 1, 2)],
            "regions_with_alerts_count": [1, 2],
            "total_alert_minutes_all_regions": [60.0, 1980.0],
            "max_regions_simultaneously_alerted": [1, 2],
            "national_alert_burden_index": [0.03, 1.0],
        }
    )
