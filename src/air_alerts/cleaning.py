from __future__ import annotations

from pathlib import Path

import polars as pl

from air_alerts.config import (
    ALERTS_CLEAN_PATH,
    RAW_DATASET_DIR,
    RAW_DATASET_NAME,
)
from air_alerts.storage import write_parquet_atomic

OFFICIAL_EN_FILE = Path("datasets/official_data_en.csv")
VOLUNTEER_EN_FILE = Path("datasets/volunteer_data_en.csv")
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S%z"

INTERVAL_COLUMNS = [
    "alert_id",
    "source_dataset",
    "source_file",
    "source",
    "source_scope",
    "region",
    "oblast",
    "raion",
    "hromada",
    "alert_level",
    "started_at_utc",
    "finished_at_utc",
    "started_date_utc",
    "finished_date_utc",
    "duration_seconds",
    "duration_minutes",
    "duration_quality",
    "volunteer_naive",
]

DEDUPLICATION_COLUMNS = [
    "source_file",
    "source",
    "source_scope",
    "region",
    "oblast",
    "raion",
    "hromada",
    "alert_level",
    "started_at_utc",
    "finished_at_utc",
    "volunteer_naive",
]


def build_clean_intervals(raw_dir: str | Path = RAW_DATASET_DIR) -> pl.DataFrame:
    dataset_dir = resolve_dataset_dir(raw_dir)
    official = _load_official_intervals(dataset_dir)
    volunteer = _load_volunteer_intervals(dataset_dir)

    official = _keep_valid_intervals(official).unique(
        subset=DEDUPLICATION_COLUMNS,
        maintain_order=True,
    )
    volunteer = _keep_valid_intervals(volunteer).unique(
        subset=DEDUPLICATION_COLUMNS,
        maintain_order=True,
    )

    official_start = official.select(pl.col("started_at_utc").min()).item()
    if official_start is not None:
        volunteer = volunteer.filter(pl.col("started_at_utc") < official_start)

    return (
        pl.concat([volunteer, official], how="diagonal")
        .sort(
            [
                "started_at_utc",
                "finished_at_utc",
                "region",
                "alert_level",
                "source",
            ]
        )
        .with_row_index("alert_id", offset=1)
        .select(INTERVAL_COLUMNS)
    )


def write_clean_intervals(
    df: pl.DataFrame,
    output_path: str | Path = ALERTS_CLEAN_PATH,
) -> None:
    write_parquet_atomic(df, output_path)


def summarize_clean_intervals(df: pl.DataFrame) -> dict:
    if df.is_empty():
        return {
            "rows": 0,
            "regions": 0,
            "started_at_min": None,
            "finished_at_max": None,
        }

    summary = df.select(
        pl.len().alias("rows"),
        pl.col("region").n_unique().alias("regions"),
        pl.col("started_at_utc").min().alias("started_at_min"),
        pl.col("finished_at_utc").max().alias("finished_at_max"),
    ).row(0, named=True)
    return {
        "rows": summary["rows"],
        "regions": summary["regions"],
        "started_at_min": summary["started_at_min"].isoformat(),
        "finished_at_max": summary["finished_at_max"].isoformat(),
    }


def resolve_dataset_dir(raw_dir: str | Path) -> Path:
    raw_dir = Path(raw_dir)
    if (raw_dir / "datasets").is_dir():
        return raw_dir

    candidate = raw_dir / RAW_DATASET_NAME
    if (candidate / "datasets").is_dir():
        return candidate

    return raw_dir


def _load_official_intervals(dataset_dir: Path) -> pl.DataFrame:
    path = _require_raw_file(dataset_dir / OFFICIAL_EN_FILE)
    return _with_interval_fields(
        pl.read_csv(path).select(
            pl.lit("vadimkin").alias("source_dataset"),
            pl.lit(OFFICIAL_EN_FILE.as_posix()).alias("source_file"),
            pl.col("source").str.strip_chars().alias("source"),
            pl.lit("official_english_snapshot").alias("source_scope"),
            pl.col("oblast").str.strip_chars().alias("region"),
            pl.col("oblast").str.strip_chars().alias("oblast"),
            pl.col("raion").str.strip_chars().alias("raion"),
            pl.col("hromada").str.strip_chars().alias("hromada"),
            pl.col("level").str.strip_chars().alias("alert_level"),
            pl.col("started_at"),
            pl.col("finished_at"),
            pl.lit(None, dtype=pl.Boolean).alias("volunteer_naive"),
        )
    )


def _load_volunteer_intervals(dataset_dir: Path) -> pl.DataFrame:
    path = _require_raw_file(dataset_dir / VOLUNTEER_EN_FILE)
    return _with_interval_fields(
        pl.read_csv(path).select(
            pl.lit("vadimkin").alias("source_dataset"),
            pl.lit(VOLUNTEER_EN_FILE.as_posix()).alias("source_file"),
            pl.lit("volunteer").alias("source"),
            pl.lit("volunteer_pre_official_coverage").alias("source_scope"),
            pl.col("region").str.strip_chars().alias("region"),
            pl.col("region").str.strip_chars().alias("oblast"),
            pl.lit(None, dtype=pl.String).alias("raion"),
            pl.lit(None, dtype=pl.String).alias("hromada"),
            pl.lit("region").alias("alert_level"),
            pl.col("started_at"),
            pl.col("finished_at"),
            pl.col("naive").alias("volunteer_naive"),
        )
    )


def _with_interval_fields(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.with_columns(
            pl.col("started_at")
            .str.to_datetime(format=TIMESTAMP_FORMAT, strict=False)
            .dt.convert_time_zone("UTC")
            .alias("started_at_utc"),
            pl.col("finished_at")
            .str.to_datetime(format=TIMESTAMP_FORMAT, strict=False)
            .dt.convert_time_zone("UTC")
            .alias("finished_at_utc"),
        )
        .with_columns(
            (
                pl.col("finished_at_utc") - pl.col("started_at_utc")
            ).dt.total_seconds().alias("duration_seconds")
        )
        .with_columns(
            (pl.col("duration_seconds") / 60).alias("duration_minutes"),
            pl.col("started_at_utc").dt.date().alias("started_date_utc"),
            pl.col("finished_at_utc").dt.date().alias("finished_date_utc"),
            pl.when(pl.col("duration_seconds") > 24 * 60 * 60)
            .then(pl.lit("long_interval"))
            .otherwise(pl.lit("ok"))
            .alias("duration_quality"),
        )
        .drop("started_at", "finished_at")
    )


def _keep_valid_intervals(df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(
        pl.col("started_at_utc").is_not_null()
        & pl.col("finished_at_utc").is_not_null()
        & (pl.col("duration_seconds") > 0)
    )


def _require_raw_file(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing required raw file: {path}. "
            "Run `uv run python scripts/download_data.py --source vadimkin`."
        )
    return path
