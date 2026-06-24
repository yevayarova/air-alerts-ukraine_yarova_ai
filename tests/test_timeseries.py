from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from air_alerts.metrics import has_infinite_values
from air_alerts.timeseries import (
    REQUIRED_SUMMARY_COLUMNS,
    ROLLING_COLUMNS,
    build_region_day_timeseries,
    build_region_timeseries_summary,
    detect_change_points,
    regime_shift_label,
    validate_timeseries_outputs,
)


def test_rolling_means_are_computed_in_region_date_order() -> None:
    data = _region_day_metrics(
        [
            ("Kyiv City", date(2022, 1, 2), 20.0, 0.2),
            ("Kyiv City", date(2022, 1, 1), 10.0, 0.1),
            ("Kyiv City", date(2022, 1, 3), 30.0, 0.3),
        ]
    )

    timeseries = build_region_day_timeseries(data)

    assert timeseries["alert_minutes_7d_mean"].to_list() == [10.0, 15.0, 20.0]
    assert timeseries["abi_7d_mean"].to_list() == pytest.approx([0.1, 0.15, 0.2])


def test_rolling_values_do_not_leak_across_regions() -> None:
    data = _region_day_metrics(
        [
            ("Kyiv City", date(2022, 1, 1), 10.0, 0.1),
            ("Kyiv City", date(2022, 1, 2), 20.0, 0.2),
            ("Lvivska oblast", date(2022, 1, 1), 100.0, 0.9),
        ]
    )

    timeseries = build_region_day_timeseries(data)
    lviv_first = timeseries.filter(pl.col("region_name") == "Lvivska oblast").row(
        0,
        named=True,
    )

    assert lviv_first["alert_minutes_7d_mean"] == 100.0
    assert lviv_first["abi_7d_mean"] == 0.9


def test_short_series_does_not_crash() -> None:
    data = _region_day_metrics(
        [
            ("Kyiv City", date(2022, 1, 1), 10.0, 0.1),
            ("Kyiv City", date(2022, 1, 2), 20.0, 0.2),
        ]
    )

    timeseries = build_region_day_timeseries(data)
    summary = build_region_timeseries_summary(timeseries)

    assert timeseries.height == 2
    assert summary.height == 1


def test_all_zero_series_returns_safe_labels() -> None:
    data = _region_day_metrics(
        [
            ("Kyiv City", date(2022, 1, 1) + timedelta(days=index), 0.0, 0.0)
            for index in range(40)
        ]
    )

    summary = build_region_timeseries_summary(build_region_day_timeseries(data))
    row = summary.row(0, named=True)

    assert row["volatility_label"] == "low"
    assert row["trend_label"] == "stable"
    assert row["regime_shift_label"] == "no clear statistical shift"
    assert row["n_change_points"] == 0


def test_outputs_have_no_infinite_values() -> None:
    timeseries = build_region_day_timeseries(_basic_multi_region_metrics())
    summary = build_region_timeseries_summary(timeseries)

    assert has_infinite_values(timeseries) is False
    assert has_infinite_values(summary) is False


def test_required_schema_exists() -> None:
    input_data = _basic_multi_region_metrics()
    timeseries = build_region_day_timeseries(input_data)
    summary = build_region_timeseries_summary(timeseries)
    validation = validate_timeseries_outputs(timeseries, summary, input_data.height)

    assert set(ROLLING_COLUMNS) <= set(timeseries.columns)
    assert REQUIRED_SUMMARY_COLUMNS <= set(summary.columns)
    assert validation["passed"] is True


def test_change_point_output_is_deterministic_for_clear_step_change() -> None:
    start = date(2022, 1, 1)
    dates = [start + timedelta(days=index) for index in range(90)]
    values = [0.0] * 45 + [300.0] * 45

    change_points = detect_change_points(values, dates)

    assert change_points == [date(2022, 2, 15)]


def test_change_point_detection_does_not_force_shift_for_stable_nonzero_series() -> None:
    start = date(2022, 1, 1)
    dates = [start + timedelta(days=index) for index in range(90)]
    values = [100.0 if index % 2 == 0 else 105.0 for index in range(90)]

    assert detect_change_points(values, dates) == []


def test_regime_shift_labels_use_cautious_statistical_language() -> None:
    assert regime_shift_label(0) == "no clear statistical shift"
    assert regime_shift_label(1) == "possible statistical shift"
    assert regime_shift_label(2) == "repeated statistical shifts"


def _basic_multi_region_metrics() -> pl.DataFrame:
    start = date(2022, 1, 1)
    rows = []
    for index in range(60):
        rows.append(("Kyiv City", start + timedelta(days=index), float(index), index / 100))
        rows.append(
            (
                "Lvivska oblast",
                start + timedelta(days=index),
                float(120 - index),
                (120 - index) / 200,
            )
        )
    return _region_day_metrics(rows)


def _region_day_metrics(
    rows: list[tuple[str, date, float, float]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "region_name": [row[0] for row in rows],
            "date": [row[1] for row in rows],
            "alert_minutes_total": [row[2] for row in rows],
            "alert_burden_index": [row[3] for row in rows],
        }
    )
