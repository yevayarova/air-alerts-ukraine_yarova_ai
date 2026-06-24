from pathlib import Path

import polars as pl
import pytest

from air_alerts.cleaning import build_clean_intervals, summarize_clean_intervals


def test_build_clean_intervals_deduplicates_and_uses_volunteer_pre_official(
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "ukrainian-air-raid-sirens-dataset"
    datasets_dir = dataset_dir / "datasets"
    datasets_dir.mkdir(parents=True)

    (datasets_dir / "official_data_en.csv").write_text(
        "\n".join(
            [
                "oblast,raion,hromada,level,started_at,finished_at,source",
                (
                    "Kyivska oblast,,,oblast,2022-03-15 01:00:00+00:00,"
                    "2022-03-15 02:00:00+00:00,official"
                ),
                (
                    "Kyivska oblast,,,oblast,2022-03-15 01:00:00+00:00,"
                    "2022-03-15 02:00:00+00:00,official"
                ),
                (
                    "Lvivska oblast,,,oblast,2022-03-15 03:00:00+00:00,"
                    "2022-03-15 03:00:00+00:00,official"
                ),
            ]
        ),
        encoding="utf-8",
    )
    (datasets_dir / "volunteer_data_en.csv").write_text(
        "\n".join(
            [
                "region,started_at,finished_at,naive",
                (
                    "Kyiv City,2022-03-01 01:00:00+00:00,"
                    "2022-03-01 01:30:00+00:00,false"
                ),
                (
                    "Kyiv City,2022-03-16 01:00:00+00:00,"
                    "2022-03-16 01:30:00+00:00,false"
                ),
            ]
        ),
        encoding="utf-8",
    )

    clean = build_clean_intervals(tmp_path)

    assert clean.select(
        "source",
        "region",
        "alert_level",
        "duration_minutes",
    ).to_dicts() == [
        {
            "source": "volunteer",
            "region": "Kyiv City",
            "alert_level": "region",
            "duration_minutes": 30.0,
        },
        {
            "source": "official",
            "region": "Kyivska oblast",
            "alert_level": "oblast",
            "duration_minutes": 60.0,
        },
    ]
    assert clean["alert_id"].to_list() == [1, 2]


def test_build_clean_intervals_fails_clearly_when_raw_file_missing(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="Missing required raw file"):
        build_clean_intervals(tmp_path)


def test_summarize_clean_intervals_returns_dashboard_metadata() -> None:
    df = pl.DataFrame(
        {
            "region": ["Kyiv City", "Kyivska oblast"],
            "started_at_utc": [
                "2022-03-01 01:00:00+00:00",
                "2022-03-15 01:00:00+00:00",
            ],
            "finished_at_utc": [
                "2022-03-01 01:30:00+00:00",
                "2022-03-15 02:00:00+00:00",
            ],
        }
    ).with_columns(
        pl.col("started_at_utc")
        .str.to_datetime(format="%Y-%m-%d %H:%M:%S%z")
        .alias("started_at_utc"),
        pl.col("finished_at_utc")
        .str.to_datetime(format="%Y-%m-%d %H:%M:%S%z")
        .alias("finished_at_utc"),
    )

    summary = summarize_clean_intervals(df)

    assert summary["rows"] == 2
    assert summary["regions"] == 2
    assert summary["started_at_min"] == "2022-03-01T01:00:00+00:00"
    assert summary["finished_at_max"] == "2022-03-15T02:00:00+00:00"
