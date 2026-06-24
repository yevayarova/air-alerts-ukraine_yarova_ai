from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sys

import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from air_alerts.config import (  # noqa: E402
    METRICS_VALIDATION_REPORT_PATH,
    NATIONAL_DAY_FEATURES_PATH,
    NATIONAL_SUMMARY_METRICS_PATH,
    REGION_DAY_METRICS_PATH,
    REGION_DAY_TIMESERIES_PATH,
    REGION_SUMMARY_METRICS_PATH,
    REGION_TIMESERIES_SUMMARY_PATH,
    TIMESERIES_VALIDATION_REPORT_PATH,
)

METRIC_OPTIONS = {
    "Alert Burden Index": "alert_burden_index",
    "Sleep Disruption Index": "sleep_disruption_index",
    "Work/Study Disruption Index": "workday_disruption_index",
    "Alert minutes": "alert_minutes_total",
}

RANKING_METRICS = {
    "Alert burden": "mean_alert_burden_index",
    "Sleep disruption": "mean_sleep_disruption_index",
    "Work/study disruption": "mean_workday_disruption_index",
}

STABILITY_METRIC_OPTIONS = {
    "Alert minutes": {
        "daily": "alert_minutes_total",
        "rolling_14": "alert_minutes_14d_mean",
        "rolling_30": "alert_minutes_30d_mean",
        "volatility_14": "alert_minutes_14d_std",
        "volatility_30": "alert_minutes_30d_std",
        "label": "Alert minutes",
    },
    "ABI": {
        "daily": "alert_burden_index",
        "rolling_14": "abi_14d_mean",
        "rolling_30": "abi_30d_mean",
        "volatility_14": "abi_14d_std",
        "volatility_30": "abi_30d_std",
        "label": "Alert Burden Index",
    },
    "SDI": {
        "daily": "sleep_disruption_index",
        "rolling_14": None,
        "rolling_30": None,
        "volatility_14": None,
        "volatility_30": None,
        "label": "Sleep Disruption Index",
    },
    "WDI": {
        "daily": "workday_disruption_index",
        "rolling_14": None,
        "rolling_30": None,
        "volatility_14": None,
        "volatility_30": None,
        "label": "Work/Study Disruption Index",
    },
}

TIME_SERIES_REQUIRED_COLUMNS = {
    "region_name",
    "date",
    "alert_minutes_total",
    "alert_burden_index",
    "sleep_disruption_index",
    "workday_disruption_index",
}

TIME_SERIES_SUMMARY_REQUIRED_COLUMNS = {
    "region",
    "latest_30d_alert_minutes_mean",
    "previous_30d_alert_minutes_mean",
    "latest_vs_previous_30d_delta",
    "std_alert_minutes",
    "volatility_label",
    "trend_label",
    "regime_shift_label",
    "n_change_points",
    "change_point_dates",
}

PUBLIC_TREND_LABELS = {
    "worsening": "historically increased",
    "stable": "historically stable",
    "mixed": "mixed historical pattern",
    "improving": "historically decreased",
}

PUBLIC_SHIFT_LABELS = {
    "no clear shift": "no clear statistical shift",
    "possible shift": "possible statistical shift",
    "strong shift": "repeated statistical shifts",
    "no clear statistical shift": "no clear statistical shift",
    "possible statistical shift": "possible statistical shift",
    "repeated statistical shifts": "repeated statistical shifts",
}

STABILITY_RANKING_COLUMNS = {
    "region": "Region",
    "latest_30d_alert_minutes_mean": "Latest 30-Day Mean Alert Hours",
    "latest_vs_previous_30d_delta": "Latest vs Previous 30-Day Change",
    "volatility_label": "Volatility",
    "public_trend_label": "Historical Pattern",
    "public_shift_label": "Statistical Shift Signal",
    "n_change_points": "Detected Shift Dates",
}

REQUIRED_REGION_DAY_COLUMNS = {
    "region_name",
    "date",
    "alert_minutes_total",
    "alert_burden_index",
    "sleep_disruption_index",
    "workday_disruption_index",
    "gini_alert_minutes_total",
    "gini_alert_burden_index",
}


@dataclass(frozen=True)
class DashboardData:
    region_day: pl.DataFrame
    region_summary: pl.DataFrame
    national_summary: pl.DataFrame
    national_day: pl.DataFrame
    region_day_timeseries: pl.DataFrame | None
    region_timeseries_summary: pl.DataFrame | None
    validation_report: str
    timeseries_validation_report: str


def has_columns(df: pl.DataFrame, columns: set[str]) -> bool:
    return columns <= set(df.columns)


def missing_columns(df: pl.DataFrame, columns: set[str]) -> list[str]:
    return sorted(columns - set(df.columns))


def available_regions(region_day: pl.DataFrame) -> list[str]:
    if "region_name" not in region_day.columns or region_day.is_empty():
        return []
    return region_day.select("region_name").unique().sort("region_name").to_series().to_list()


def date_bounds(region_day: pl.DataFrame) -> tuple[date | None, date | None]:
    if "date" not in region_day.columns or region_day.is_empty():
        return None, None
    row = region_day.select(
        pl.col("date").min().alias("date_start"),
        pl.col("date").max().alias("date_end"),
    ).row(0, named=True)
    return row["date_start"], row["date_end"]


def filter_region_day(
    region_day: pl.DataFrame,
    regions: list[str],
    selected_range: tuple[date, date],
) -> pl.DataFrame:
    required = {"region_name", "date"}
    if not has_columns(region_day, required):
        return pl.DataFrame()

    start_date, end_date = selected_range
    return region_day.filter(
        pl.col("region_name").is_in(regions)
        & (pl.col("date") >= start_date)
        & (pl.col("date") <= end_date)
    )


def add_rolling_average(
    data: pl.DataFrame,
    metric: str,
    window_days: int = 14,
) -> pl.DataFrame:
    if data.is_empty() or not has_columns(data, {"region_name", "date", metric}):
        return data

    return (
        data.sort(["region_name", "date"])
        .with_columns(
            pl.col(metric)
            .rolling_mean(window_size=window_days, min_samples=1)
            .over("region_name")
            .alias(f"{metric}_rolling")
        )
    )


def format_minutes_as_hours(minutes: float | int | None) -> str:
    if minutes is None:
        return "n/a"
    return f"{minutes / 60:,.0f} h"


def format_minutes_per_day(minutes: float | int | None) -> str:
    if minutes is None:
        return "n/a"
    return f"{minutes / 60:,.1f} h/day"


def format_signed_minutes_per_day(minutes: float | int | None) -> str:
    if minutes is None:
        return "n/a"
    hours = minutes / 60
    sign = "+" if hours > 0 else ""
    return f"{sign}{hours:,.1f} h/day"


def public_trend_label(label: str | None) -> str:
    if label is None:
        return "not available"
    return PUBLIC_TREND_LABELS.get(label, "mixed historical pattern")


def public_shift_label(label: str | None) -> str:
    if label is None:
        return "not available"
    return PUBLIC_SHIFT_LABELS.get(label, "possible statistical shift")


def has_required_timeseries_columns(df: pl.DataFrame | None) -> bool:
    return df is not None and has_columns(df, TIME_SERIES_REQUIRED_COLUMNS)


def has_required_timeseries_summary_columns(df: pl.DataFrame | None) -> bool:
    return df is not None and has_columns(df, TIME_SERIES_SUMMARY_REQUIRED_COLUMNS)


def filter_timeseries_region_day(
    region_day_timeseries: pl.DataFrame,
    region: str,
    selected_range: tuple[date, date],
) -> pl.DataFrame:
    if not has_required_timeseries_columns(region_day_timeseries):
        return pl.DataFrame()
    start_date, end_date = selected_range
    return region_day_timeseries.filter(
        (pl.col("region_name") == region)
        & (pl.col("date") >= start_date)
        & (pl.col("date") <= end_date)
    ).sort("date")


def selected_region_name(selected_regions: list[str]) -> str:
    return selected_regions[0] if selected_regions else ""


def timeseries_summary_row(
    region_timeseries_summary: pl.DataFrame,
    region: str,
) -> dict:
    if not has_required_timeseries_summary_columns(region_timeseries_summary):
        return {}
    rows = region_timeseries_summary.filter(pl.col("region") == region).to_dicts()
    return rows[0] if rows else {}


def shift_date_rows(summary_row: dict) -> list[dict[str, str]]:
    raw_dates = summary_row.get("change_point_dates") or ""
    dates = [value for value in raw_dates.split(";") if value]
    return [
        {
            "Statistical shift date": value,
            "Detection series": "Daily alert minutes",
        }
        for value in dates
    ]


def stability_metric_config(label: str) -> dict:
    return STABILITY_METRIC_OPTIONS[label]


def prepare_stability_ranking(
    region_timeseries_summary: pl.DataFrame,
    ranking_mode: str,
) -> pl.DataFrame:
    if not has_required_timeseries_summary_columns(region_timeseries_summary):
        return pl.DataFrame()

    sort_columns = {
        "latest burden": ("latest_30d_alert_minutes_mean", True),
        "volatility": ("std_alert_minutes", True),
        "recent increase": ("latest_vs_previous_30d_delta", True),
    }
    sort_column, descending = sort_columns[ranking_mode]
    return (
        region_timeseries_summary.with_columns(
            (pl.col("latest_30d_alert_minutes_mean") / 60).alias(
                "latest_30d_alert_hours_mean"
            ),
            (pl.col("latest_vs_previous_30d_delta") / 60).alias(
                "latest_vs_previous_30d_hours_delta"
            ),
            pl.col("trend_label")
            .map_elements(public_trend_label, return_dtype=pl.String)
            .alias("public_trend_label"),
            pl.col("regime_shift_label")
            .map_elements(public_shift_label, return_dtype=pl.String)
            .alias("public_shift_label"),
        )
        .sort(sort_column, descending=descending)
        .head(10)
        .select(
            pl.col("region").alias(STABILITY_RANKING_COLUMNS["region"]),
            pl.col("latest_30d_alert_hours_mean").round(1).alias(
                STABILITY_RANKING_COLUMNS["latest_30d_alert_minutes_mean"]
            ),
            pl.col("latest_vs_previous_30d_hours_delta").round(1).alias(
                STABILITY_RANKING_COLUMNS["latest_vs_previous_30d_delta"]
            ),
            pl.col("volatility_label").alias(
                STABILITY_RANKING_COLUMNS["volatility_label"]
            ),
            pl.col("public_trend_label").alias(
                STABILITY_RANKING_COLUMNS["public_trend_label"]
            ),
            pl.col("public_shift_label").alias(
                STABILITY_RANKING_COLUMNS["public_shift_label"]
            ),
            pl.col("n_change_points").alias(
                STABILITY_RANKING_COLUMNS["n_change_points"]
            ),
        )
    )


def load_dashboard_data() -> DashboardData | None:
    required_files = [
        REGION_DAY_METRICS_PATH,
        REGION_SUMMARY_METRICS_PATH,
        NATIONAL_SUMMARY_METRICS_PATH,
        NATIONAL_DAY_FEATURES_PATH,
    ]
    missing_files = [path for path in required_files if not path.is_file()]
    if missing_files:
        st.warning(
            "Processed dashboard files are missing. Run "
            "`uv run python scripts/build_metrics.py` after the feature tables are built."
        )
        for path in missing_files:
            st.caption(f"Missing: `{path.as_posix()}`")
        return None

    return _load_dashboard_data_cached(
        REGION_DAY_METRICS_PATH.as_posix(),
        REGION_SUMMARY_METRICS_PATH.as_posix(),
        NATIONAL_SUMMARY_METRICS_PATH.as_posix(),
        NATIONAL_DAY_FEATURES_PATH.as_posix(),
        REGION_DAY_TIMESERIES_PATH.as_posix()
        if REGION_DAY_TIMESERIES_PATH.is_file()
        else None,
        REGION_TIMESERIES_SUMMARY_PATH.as_posix()
        if REGION_TIMESERIES_SUMMARY_PATH.is_file()
        else None,
        METRICS_VALIDATION_REPORT_PATH.as_posix(),
        TIMESERIES_VALIDATION_REPORT_PATH.as_posix(),
    )


@st.cache_data(show_spinner=False)
def _load_dashboard_data_cached(
    region_day_path: str,
    region_summary_path: str,
    national_summary_path: str,
    national_day_path: str,
    region_day_timeseries_path: str | None,
    region_timeseries_summary_path: str | None,
    validation_report_path: str,
    timeseries_validation_report_path: str,
) -> DashboardData:
    validation_path = Path(validation_report_path)
    validation_report = (
        validation_path.read_text(encoding="utf-8")
        if validation_path.is_file()
        else "Metrics validation report is not available."
    )
    timeseries_validation_path = Path(timeseries_validation_report_path)
    timeseries_validation_report = (
        timeseries_validation_path.read_text(encoding="utf-8")
        if timeseries_validation_path.is_file()
        else "Time-series validation report is not available."
    )
    return DashboardData(
        region_day=pl.read_parquet(region_day_path),
        region_summary=pl.read_parquet(region_summary_path),
        national_summary=pl.read_parquet(national_summary_path),
        national_day=pl.read_parquet(national_day_path),
        region_day_timeseries=_read_optional_parquet(region_day_timeseries_path),
        region_timeseries_summary=_read_optional_parquet(
            region_timeseries_summary_path
        ),
        validation_report=validation_report,
        timeseries_validation_report=timeseries_validation_report,
    )


def _read_optional_parquet(path: str | None) -> pl.DataFrame | None:
    if path is None:
        return None
    return pl.read_parquet(path)


def main() -> None:
    st.set_page_config(
        page_title="Ukraine Alert Burden Dashboard",
        page_icon="",
        layout="wide",
    )
    st.title("Ukraine Air Alert Burden Dashboard")
    st.caption(
        "Civilian resilience analytics from historical air raid alert data. "
        "This dashboard describes alert burden, sleep and work/study disruption, "
        "regional inequality, and stability/change over time. It is descriptive "
        "only, with no causal claims or forecasts."
    )
    st.markdown(
        "Explore how historical alerts affected civilian routines across Ukrainian "
        "regions, using processed dashboard-ready data products."
    )

    data = load_dashboard_data()
    if data is None:
        return

    if not _warn_for_missing_columns(
        data.region_day,
        REQUIRED_REGION_DAY_COLUMNS,
        "region-day metrics",
    ):
        return

    selected_regions, selected_range, metric_label, metric_column = render_sidebar(
        data.region_day
    )
    filtered = filter_region_day(data.region_day, selected_regions, selected_range)
    tabs = st.tabs(
        [
            "Overview",
            "Regional Burden",
            "Human Disruption",
            "Regional Inequality",
            "Stability & Change",
            "Methodology & Limits",
        ]
    )

    with tabs[0]:
        render_overview(data, filtered)

    with tabs[1]:
        render_regional_rankings(data.region_summary)
        render_time_series(filtered, metric_label, metric_column)

    with tabs[2]:
        render_sleep_work_section(filtered)

    with tabs[3]:
        render_inequality_section(data.region_day, selected_range)

    with tabs[4]:
        render_stability_change_section(data, selected_regions, selected_range)

    with tabs[5]:
        render_methodology(data.validation_report, data.timeseries_validation_report)


def render_sidebar(
    region_day: pl.DataFrame,
) -> tuple[list[str], tuple[date, date], str, str]:
    st.sidebar.header("Filters")
    regions = available_regions(region_day)
    if not regions:
        st.sidebar.warning("No regions are available in the metric table.")
        return [], (date.today(), date.today()), "Alert Burden Index", "alert_burden_index"

    default_region = "Kyiv City" if "Kyiv City" in regions else regions[0]
    selected_region = st.sidebar.selectbox(
        "Region",
        regions,
        index=regions.index(default_region),
    )

    start_date, end_date = date_bounds(region_day)
    if start_date is None or end_date is None:
        start_date = end_date = date.today()

    selected_dates = st.sidebar.date_input(
        "Date range",
        value=(start_date, end_date),
        min_value=start_date,
        max_value=end_date,
    )
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        selected_range = selected_dates
    else:
        selected_range = (start_date, end_date)
        st.sidebar.warning("Select both start and end dates to filter the dashboard.")

    metric_label = st.sidebar.selectbox("Metric", list(METRIC_OPTIONS))
    return [selected_region], selected_range, metric_label, METRIC_OPTIONS[metric_label]


def render_overview(data: DashboardData, filtered: pl.DataFrame) -> None:
    st.subheader("National Summary")
    national = data.national_summary.row(0, named=True) if not data.national_summary.is_empty() else {}
    region_count = (
        data.region_summary.select(pl.col("region_name").n_unique()).item()
        if has_columns(data.region_summary, {"region_name"})
        else None
    )
    metric_row = filtered.select(
        pl.col("alert_burden_index").mean().alias("mean_abi"),
        pl.col("sleep_disruption_index").mean().alias("mean_sdi"),
        pl.col("workday_disruption_index").mean().alias("mean_wdi"),
        pl.col("alert_minutes_total").sum().alias("filtered_minutes"),
    ).row(0, named=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Regions in Dataset", f"{region_count or 0}")
    col2.metric(
        "National Alert Hours",
        format_minutes_as_hours(national.get("total_alert_minutes_all_regions")),
    )
    col3.metric(
        "Mean National Burden Index",
        _format_decimal(national.get("mean_national_alert_burden_index")),
    )
    col4.metric(
        "Coverage",
        f"{national.get('date_start')} to {national.get('date_end')}" if national else "n/a",
    )

    selected_region = (
        filtered["region_name"][0]
        if not filtered.is_empty() and "region_name" in filtered.columns
        else "Selected region"
    )
    st.subheader(f"Selected-Region Metrics: {selected_region}")
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Selected Avg ABI", _format_decimal(metric_row["mean_abi"]))
    col6.metric("Selected Avg SDI", _format_decimal(metric_row["mean_sdi"]))
    col7.metric("Selected Avg WDI", _format_decimal(metric_row["mean_wdi"]))
    col8.metric(
        "Selected Alert Hours",
        format_minutes_as_hours(metric_row["filtered_minutes"]),
    )


def render_regional_rankings(region_summary: pl.DataFrame) -> None:
    st.subheader("Regional Rankings")
    required = {"region_name", *RANKING_METRICS.values()}
    if not _warn_for_missing_columns(region_summary, required, "region summary metrics"):
        return

    cols = st.columns(3)
    for column, (title, metric) in zip(cols, RANKING_METRICS.items(), strict=True):
        ranking = region_summary.sort(metric, descending=True).head(10)
        fig = px.bar(
            ranking.to_pandas(),
            x=metric,
            y="region_name",
            orientation="h",
            title=f"Top Regions by {title}",
            labels={metric: title, "region_name": "Region"},
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=420)
        column.plotly_chart(fig, width="stretch")


def render_time_series(
    filtered: pl.DataFrame,
    metric_label: str,
    metric_column: str,
) -> None:
    st.subheader("Selected Region Over Time")
    required = {"date", "region_name", metric_column, "alert_minutes_total"}
    if not _warn_for_missing_columns(filtered, required, "filtered region-day metrics"):
        return
    if filtered.is_empty():
        st.warning("No rows match the selected filters.")
        return

    region_name = filtered["region_name"][0]
    rolling = add_rolling_average(filtered, metric_column)
    rolling_column = f"{metric_column}_rolling"
    pandas_df = rolling.to_pandas()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=pandas_df["date"],
            y=pandas_df[metric_column],
            mode="lines",
            name=metric_label,
            line={"color": "#2563eb", "width": 1.5},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=pandas_df["date"],
            y=pandas_df[rolling_column],
            mode="lines",
            name="14-day rolling average",
            line={"color": "#dc2626", "width": 2.5},
        )
    )
    fig.update_layout(
        title=f"{region_name}: {metric_label}",
        xaxis_title="Date",
        yaxis_title=metric_label,
        height=420,
    )
    st.plotly_chart(fig, width="stretch")

    alert_minutes_fig = px.area(
        pandas_df,
        x="date",
        y="alert_minutes_total",
        title=f"{region_name}: Daily Alert Minutes",
        labels={"date": "Date", "alert_minutes_total": "Alert minutes"},
    )
    alert_minutes_fig.update_layout(height=320)
    st.plotly_chart(alert_minutes_fig, width="stretch")


def render_sleep_work_section(filtered: pl.DataFrame) -> None:
    st.subheader("Sleep and Work/Study Disruption")
    required = {"date", "sleep_disruption_index", "workday_disruption_index"}
    if not _warn_for_missing_columns(filtered, required, "filtered region-day metrics"):
        return
    if filtered.is_empty():
        st.warning("No rows match the selected filters.")
        return

    pandas_df = filtered.sort("date").to_pandas()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=pandas_df["date"],
            y=pandas_df["sleep_disruption_index"],
            mode="lines",
            name="Sleep Disruption Index",
            line={"color": "#7c3aed"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=pandas_df["date"],
            y=pandas_df["workday_disruption_index"],
            mode="lines",
            name="Work/Study Disruption Index",
            line={"color": "#059669"},
        )
    )
    fig.update_layout(
        title="SDI and WDI Over Time",
        xaxis_title="Date",
        yaxis_title="Index value",
        yaxis_range=[0, 1],
        height=420,
    )
    st.plotly_chart(fig, width="stretch")


def render_inequality_section(
    region_day: pl.DataFrame,
    selected_range: tuple[date, date],
) -> None:
    st.subheader("Across-Region Inequality")
    st.write(
        "Gini values range from 0 to 1; higher values mean daily alert burden was "
        "more concentrated across regions. This section uses all regions for the "
        "selected date range, independent of the selected-region filter."
    )
    required = {"date", "gini_alert_minutes_total", "gini_alert_burden_index"}
    if not _warn_for_missing_columns(region_day, required, "region-day metrics"):
        return

    start_date, end_date = selected_range
    filtered = region_day.filter(
        (pl.col("date") >= start_date) & (pl.col("date") <= end_date)
    )
    if filtered.is_empty():
        st.warning("No inequality rows match the selected date range.")
        return

    inequality = (
        filtered.group_by("date")
        .agg(
            pl.col("gini_alert_minutes_total").first().alias("gini_alert_minutes_total"),
            pl.col("gini_alert_burden_index").first().alias("gini_alert_burden_index"),
        )
        .sort("date")
    )
    pandas_df = inequality.to_pandas()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=pandas_df["date"],
            y=pandas_df["gini_alert_minutes_total"],
            mode="lines",
            name="Gini: Alert minutes",
            line={"color": "#ea580c"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=pandas_df["date"],
            y=pandas_df["gini_alert_burden_index"],
            mode="lines",
            name="Gini: ABI",
            line={"color": "#0891b2"},
        )
    )
    fig.update_layout(
        title="Daily Regional Inequality Metrics",
        xaxis_title="Date",
        yaxis_title="Gini",
        yaxis_range=[0, 1],
        height=380,
    )
    st.plotly_chart(fig, width="stretch")


def render_stability_change_section(
    data: DashboardData,
    selected_regions: list[str],
    selected_range: tuple[date, date],
) -> None:
    st.subheader("Stability & Change")
    st.write(
        "Use this section to see whether historical alert burden has been stable, "
        "increased, become more volatile, or shown statistical shifts."
    )

    if data.region_day_timeseries is None or data.region_timeseries_summary is None:
        st.warning(
            "Time-series diagnostics are not available yet. Run "
            "`uv run python scripts/build_timeseries.py` to create the processed files."
        )
        return

    if not _warn_for_missing_columns(
        data.region_day_timeseries,
        TIME_SERIES_REQUIRED_COLUMNS,
        "region-day time-series diagnostics",
    ):
        return
    if not _warn_for_missing_columns(
        data.region_timeseries_summary,
        TIME_SERIES_SUMMARY_REQUIRED_COLUMNS,
        "region time-series summary",
    ):
        return

    region = selected_region_name(selected_regions)
    if not region:
        st.warning("Select a region to view stability diagnostics.")
        return

    filtered = filter_timeseries_region_day(
        data.region_day_timeseries,
        region,
        selected_range,
    )
    summary_row = timeseries_summary_row(data.region_timeseries_summary, region)
    if filtered.is_empty() or not summary_row:
        st.warning("No time-series diagnostics match the selected filters.")
        return

    render_stability_summary_cards(summary_row)

    st.markdown(
        "**Trend:** compares daily values with rolling averages to show baseline "
        "historical burden."
    )
    metric_label = st.selectbox(
        "Stability metric",
        list(STABILITY_METRIC_OPTIONS),
        key="stability_metric",
    )
    metric_config = stability_metric_config(metric_label)
    render_stability_trend_chart(filtered, metric_config)

    st.markdown(
        "**Volatility:** shows how stable or unstable daily planning conditions "
        "were over time."
    )
    render_stability_volatility_chart(filtered, metric_config)

    st.markdown(
        "**Statistical shifts:** marks structural changes detected in the historical "
        "daily alert-minute series."
    )
    render_statistical_shift_timeline(summary_row)

    st.markdown(
        "**Cross-region comparison:** highlights where disruption was more "
        "persistent or unstable during the processed period."
    )
    render_stability_ranking(data.region_timeseries_summary)


def render_stability_summary_cards(summary_row: dict) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Latest 30-Day Mean",
        format_minutes_per_day(summary_row.get("latest_30d_alert_minutes_mean")),
    )
    col2.metric(
        "Previous 30-Day Mean",
        format_minutes_per_day(summary_row.get("previous_30d_alert_minutes_mean")),
    )
    col3.metric(
        "Latest vs Previous",
        format_signed_minutes_per_day(summary_row.get("latest_vs_previous_30d_delta")),
    )

    col4, col5, col6, col7 = st.columns(4)
    col4.metric("Volatility", str(summary_row.get("volatility_label", "n/a")).title())
    col5.metric(
        "Historical Pattern",
        public_trend_label(summary_row.get("trend_label")).title(),
    )
    col6.metric(
        "Statistical Shift Signal",
        public_shift_label(summary_row.get("regime_shift_label")).title(),
    )
    col7.metric(
        "Detected Shift Dates",
        str(summary_row.get("n_change_points", 0)),
    )


def render_stability_trend_chart(filtered: pl.DataFrame, metric_config: dict) -> None:
    daily_column = metric_config["daily"]
    if daily_column not in filtered.columns:
        st.warning("The selected metric is not available in the time-series table.")
        return

    pandas_df = filtered.sort("date").to_pandas()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=pandas_df["date"],
            y=pandas_df[daily_column],
            mode="lines",
            name=f"Daily {metric_config['label']}",
            line={"color": "#2563eb", "width": 1.2},
        )
    )
    _add_optional_line(
        fig,
        pandas_df,
        metric_config.get("rolling_14"),
        "14-day rolling mean",
        "#dc2626",
    )
    _add_optional_line(
        fig,
        pandas_df,
        metric_config.get("rolling_30"),
        "30-day rolling mean",
        "#059669",
    )
    fig.update_layout(
        title="Historical burden trend",
        xaxis_title="Date",
        yaxis_title=metric_config["label"],
        height=420,
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Rolling averages smooth daily noise and show how historical civilian "
        "disruption changed over time."
    )
    if metric_config.get("rolling_14") is None:
        st.info(
            "Rolling trend diagnostics are currently available for alert minutes "
            "and ABI. Daily SDI/WDI values are still shown."
        )


def render_stability_volatility_chart(filtered: pl.DataFrame, metric_config: dict) -> None:
    volatility_14 = metric_config.get("volatility_14")
    volatility_30 = metric_config.get("volatility_30")
    if not volatility_14 or not volatility_30:
        st.info(
            "Rolling volatility diagnostics are currently available for alert "
            "minutes and ABI."
        )
        return
    if not has_columns(filtered, {volatility_14, volatility_30, "date"}):
        st.warning("Volatility columns are missing from the time-series table.")
        return

    pandas_df = filtered.sort("date").to_pandas()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=pandas_df["date"],
            y=pandas_df[volatility_14],
            mode="lines",
            name="14-day volatility",
            line={"color": "#f97316"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=pandas_df["date"],
            y=pandas_df[volatility_30],
            mode="lines",
            name="30-day volatility",
            line={"color": "#0f766e"},
        )
    )
    fig.update_layout(
        title="Rolling volatility",
        xaxis_title="Date",
        yaxis_title=f"{metric_config['label']} variability",
        height=360,
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Higher volatility means daily routines are less stable and planning "
        "conditions are less predictable."
    )


def render_statistical_shift_timeline(summary_row: dict) -> None:
    rows = shift_date_rows(summary_row)
    if rows:
        st.dataframe(pl.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("No clear statistical shift detected by the current rule-based method.")
    st.caption(
        "These dates mark statistical changes in the historical series. They do "
        "not explain causes and they are not forecasts."
    )


def render_stability_ranking(region_timeseries_summary: pl.DataFrame) -> None:
    ranking_choice = st.radio(
        "Cross-region ranking",
        ["latest burden", "volatility", "recent increase"],
        horizontal=True,
    )
    ranking = prepare_stability_ranking(region_timeseries_summary, ranking_choice)
    if ranking.is_empty():
        st.warning("Cross-region stability ranking is not available.")
        return
    st.dataframe(ranking, width="stretch", hide_index=True)


def _add_optional_line(
    fig: go.Figure,
    pandas_df,
    column: str | None,
    name: str,
    color: str,
) -> None:
    if column is None or column not in pandas_df.columns:
        return
    fig.add_trace(
        go.Scatter(
            x=pandas_df["date"],
            y=pandas_df[column],
            mode="lines",
            name=name,
            line={"color": color, "width": 2.2},
        )
    )


def render_methodology(
    validation_report: str,
    timeseries_validation_report: str,
) -> None:
    st.subheader("Methodology and Limitations")
    st.markdown(
        """
        **ABI** combines normalized daily alert minutes, merged alert episode count,
        maximum alert duration, and the absence of a long alert-free recovery window.
        Min-max normalization is recomputed when the processed dataset is refreshed,
        so ABI is best read as a refresh-relative descriptive index.

        **SDI** is the share of default Kyiv-local night hours under alert. The
        calendar-day view combines 00:00-07:00 and 22:00-24:00 on the same date.

        **WDI** is the share of the default Monday-Friday 09:00-18:00 Kyiv work/study
        window under alert.

        These metrics are descriptive indicators for civilian resilience analysis.
        They are not causal estimates or forecasts.

        **Stability & Change** uses rolling averages, rolling volatility, and
        rule-based statistical shift detection on historical daily alert burden.
        Shift dates mark statistical signals in the past series, not explanations.
        """
    )
    with st.expander("Metrics validation notes"):
        st.markdown(validation_report)
    with st.expander("Time-series validation notes"):
        st.markdown(timeseries_validation_report)


def _warn_for_missing_columns(
    df: pl.DataFrame,
    columns: set[str],
    label: str,
) -> bool:
    missing = missing_columns(df, columns)
    if missing:
        st.warning(f"Missing expected columns in {label}: {', '.join(missing)}")
        return False
    return True


def _format_decimal(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"


if __name__ == "__main__":
    main()
