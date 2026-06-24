from __future__ import annotations

from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import polars as pl
import pytest

APP_PATH = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
APP_SPEC = spec_from_file_location("streamlit_app", APP_PATH)
assert APP_SPEC is not None
assert APP_SPEC.loader is not None
streamlit_app = module_from_spec(APP_SPEC)
sys.modules[APP_SPEC.name] = streamlit_app
APP_SPEC.loader.exec_module(streamlit_app)

add_rolling_average = streamlit_app.add_rolling_average
available_regions = streamlit_app.available_regions
filter_region_day = streamlit_app.filter_region_day
format_minutes_as_hours = streamlit_app.format_minutes_as_hours
has_columns = streamlit_app.has_columns
missing_columns = streamlit_app.missing_columns


def test_available_regions_returns_sorted_unique_names() -> None:
    data = pl.DataFrame({"region_name": ["Kyiv City", "Lvivska oblast", "Kyiv City"]})

    assert available_regions(data) == ["Kyiv City", "Lvivska oblast"]


def test_filter_region_day_filters_by_region_and_date_range() -> None:
    data = pl.DataFrame(
        {
            "region_name": ["Kyiv City", "Kyiv City", "Lvivska oblast"],
            "date": [date(2022, 1, 1), date(2022, 1, 2), date(2022, 1, 2)],
            "alert_burden_index": [0.1, 0.2, 0.3],
        }
    )

    filtered = filter_region_day(data, ["Kyiv City"], (date(2022, 1, 2), date(2022, 1, 2)))

    assert filtered.select("region_name", "date").to_dicts() == [
        {"region_name": "Kyiv City", "date": date(2022, 1, 2)}
    ]


def test_column_helpers_report_missing_columns() -> None:
    data = pl.DataFrame({"a": [1]})

    assert has_columns(data, {"a"}) is True
    assert missing_columns(data, {"a", "b"}) == ["b"]


def test_add_rolling_average_adds_region_scoped_column() -> None:
    data = pl.DataFrame(
        {
            "region_name": ["Kyiv City", "Kyiv City", "Lvivska oblast"],
            "date": [date(2022, 1, 1), date(2022, 1, 2), date(2022, 1, 1)],
            "alert_burden_index": [0.2, 0.4, 0.9],
        }
    )

    with_rolling = add_rolling_average(data, "alert_burden_index", window_days=2)

    assert "alert_burden_index_rolling" in with_rolling.columns
    assert with_rolling.filter(pl.col("region_name") == "Kyiv City")[
        "alert_burden_index_rolling"
    ].to_list() == pytest.approx([0.2, 0.3])


def test_format_minutes_as_hours() -> None:
    assert format_minutes_as_hours(120) == "2 h"
    assert format_minutes_as_hours(None) == "n/a"
