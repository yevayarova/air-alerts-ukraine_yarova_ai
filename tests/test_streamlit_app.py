from __future__ import annotations

from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import polars as pl
import pytest

APP_PATH = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
PROJECT_ROOT = APP_PATH.parents[1]
README_PATH = PROJECT_ROOT / "README.md"
METHODOLOGY_PATH = PROJECT_ROOT / "reports" / "methodology.md"
HF_DOCS_PATH = PROJECT_ROOT / "docs" / "HUGGINGFACE_SPACE.md"
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"
APP_SPEC = spec_from_file_location("streamlit_app", APP_PATH)
assert APP_SPEC is not None
assert APP_SPEC.loader is not None
streamlit_app = module_from_spec(APP_SPEC)
sys.modules[APP_SPEC.name] = streamlit_app
APP_SPEC.loader.exec_module(streamlit_app)

add_rolling_average = streamlit_app.add_rolling_average
available_regions = streamlit_app.available_regions
filter_region_day = streamlit_app.filter_region_day
filter_timeseries_region_day = streamlit_app.filter_timeseries_region_day
format_minutes_as_hours = streamlit_app.format_minutes_as_hours
format_minutes_per_day = streamlit_app.format_minutes_per_day
format_signed_minutes_per_day = streamlit_app.format_signed_minutes_per_day
has_required_timeseries_columns = streamlit_app.has_required_timeseries_columns
has_required_timeseries_summary_columns = (
    streamlit_app.has_required_timeseries_summary_columns
)
has_columns = streamlit_app.has_columns
missing_columns = streamlit_app.missing_columns
prepare_stability_ranking = streamlit_app.prepare_stability_ranking
public_shift_label = streamlit_app.public_shift_label
public_trend_label = streamlit_app.public_trend_label
read_optional_parquet = streamlit_app._read_optional_parquet
shift_date_rows = streamlit_app.shift_date_rows
stability_metric_config = streamlit_app.stability_metric_config


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


def test_time_series_column_helpers() -> None:
    data = pl.DataFrame(
        {
            "region_name": ["Kyiv City"],
            "date": [date(2022, 1, 1)],
            "alert_minutes_total": [60.0],
            "alert_burden_index": [0.2],
            "sleep_disruption_index": [0.1],
            "workday_disruption_index": [0.0],
        }
    )
    summary = pl.DataFrame(
        {
            "region": ["Kyiv City"],
            "latest_30d_alert_minutes_mean": [120.0],
            "previous_30d_alert_minutes_mean": [60.0],
            "latest_vs_previous_30d_delta": [60.0],
            "std_alert_minutes": [15.0],
            "volatility_label": ["low"],
            "trend_label": ["worsening"],
            "regime_shift_label": ["possible statistical shift"],
            "n_change_points": [1],
            "change_point_dates": ["2022-01-01"],
        }
    )

    assert has_required_timeseries_columns(data) is True
    assert has_required_timeseries_columns(data.drop("alert_burden_index")) is False
    assert has_required_timeseries_summary_columns(summary) is True


def test_filter_timeseries_region_day_filters_selected_region_and_dates() -> None:
    data = pl.DataFrame(
        {
            "region_name": ["Kyiv City", "Kyiv City", "Lvivska oblast"],
            "date": [date(2022, 1, 1), date(2022, 1, 2), date(2022, 1, 2)],
            "alert_minutes_total": [60.0, 90.0, 30.0],
            "alert_burden_index": [0.1, 0.2, 0.3],
            "sleep_disruption_index": [0.0, 0.1, 0.2],
            "workday_disruption_index": [0.0, 0.1, 0.2],
        }
    )

    filtered = filter_timeseries_region_day(
        data,
        "Kyiv City",
        (date(2022, 1, 2), date(2022, 1, 2)),
    )

    assert filtered.select("region_name", "date").to_dicts() == [
        {"region_name": "Kyiv City", "date": date(2022, 1, 2)}
    ]


def test_public_label_mapping_avoids_internal_trend_language() -> None:
    assert public_trend_label("worsening") == "historically increased"
    assert public_trend_label("stable") == "historically stable"
    assert public_trend_label("mixed") == "mixed historical pattern"
    assert public_trend_label("improving") == "historically decreased"
    assert "worsening" not in public_trend_label("worsening")


def test_public_shift_label_maps_old_and_current_values_to_cautious_language() -> None:
    assert public_shift_label("strong shift") == "repeated statistical shifts"
    assert public_shift_label("possible shift") == "possible statistical shift"
    assert public_shift_label("no clear shift") == "no clear statistical shift"


def test_stability_metric_config_handles_metrics_without_rolling_columns() -> None:
    sdi = stability_metric_config("SDI")

    assert sdi["daily"] == "sleep_disruption_index"
    assert sdi["rolling_14"] is None
    assert sdi["volatility_30"] is None


def test_shift_date_rows_uses_public_labels() -> None:
    rows = shift_date_rows({"change_point_dates": "2022-01-01;2022-02-01"})

    assert rows == [
        {
            "Statistical shift date": "2022-01-01",
            "Detection series": "Daily alert minutes",
        },
        {
            "Statistical shift date": "2022-02-01",
            "Detection series": "Daily alert minutes",
        },
    ]


def test_prepare_stability_ranking_uses_public_column_names_and_labels() -> None:
    summary = pl.DataFrame(
        {
            "region": ["Kyiv City", "Lvivska oblast"],
            "latest_30d_alert_minutes_mean": [120.0, 60.0],
            "previous_30d_alert_minutes_mean": [60.0, 90.0],
            "latest_vs_previous_30d_delta": [60.0, -30.0],
            "std_alert_minutes": [20.0, 10.0],
            "volatility_label": ["low", "low"],
            "trend_label": ["worsening", "stable"],
            "regime_shift_label": [
                "repeated statistical shifts",
                "no clear statistical shift",
            ],
            "n_change_points": [2, 0],
            "change_point_dates": ["2022-01-01;2022-02-01", ""],
        }
    )

    ranking = prepare_stability_ranking(summary, "recent increase")

    assert ranking.columns == [
        "Region",
        "Latest 30-Day Mean Alert Hours",
        "Latest vs Previous 30-Day Change",
        "Volatility",
        "Historical Pattern",
        "Statistical Shift Signal",
        "Detected Shift Dates",
    ]
    assert ranking["Historical Pattern"].to_list()[0] == "historically increased"


def test_public_dashboard_text_avoids_forbidden_wording() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in [APP_PATH, README_PATH, METHODOLOGY_PATH, HF_DOCS_PATH]
    )
    forbidden = [
        "attack prediction",
        "predict attacks",
        "enemy route",
        "enemy behavior",
        "tactical",
        "tactical forecast",
        "target risk",
        "threat risk",
        "operational recommendation",
    ]

    for phrase in forbidden:
        assert phrase not in source


def test_minutes_formatters_for_stability_cards() -> None:
    assert format_minutes_per_day(90) == "1.5 h/day"
    assert format_signed_minutes_per_day(90) == "+1.5 h/day"
    assert format_signed_minutes_per_day(-30) == "-0.5 h/day"


def test_optional_time_series_parquet_loader_handles_missing_path() -> None:
    assert read_optional_parquet(None) is None


def test_readme_contains_hugging_face_space_metadata() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert readme.startswith("---\n")
    assert "sdk: streamlit" in readme
    assert "sdk_version: 1.58.0" in readme
    assert "app_file: app/streamlit_app.py" in readme


def test_requirements_contains_runtime_dependencies_only() -> None:
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()
    package_names = {line.split(">=")[0] for line in requirements if line}

    assert {
        "streamlit",
        "polars",
        "pandas",
        "pyarrow",
        "plotly",
        "numpy",
    } <= package_names
    assert "pytest" not in package_names
    assert "ruff" not in package_names


def test_public_files_do_not_contain_local_absolute_paths() -> None:
    public_paths = [
        APP_PATH,
        README_PATH,
        METHODOLOGY_PATH,
        HF_DOCS_PATH,
        REQUIREMENTS_PATH,
        PROJECT_ROOT / ".streamlit" / "config.toml",
    ]

    for path in public_paths:
        assert "/Users/" not in path.read_text(encoding="utf-8")
