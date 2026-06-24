from pathlib import Path

import polars as pl
import pytest

from air_alerts.data_sources import inspect_dataset, list_raw_files, load_any_file


def test_list_raw_files_returns_supported_files_sorted(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("ignore me", encoding="utf-8")
    (tmp_path / "a.csv").write_text("x\n1\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.json").write_text('[{"x": 2}]', encoding="utf-8")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "d.csv").write_text("x\n3\n", encoding="utf-8")

    files = list_raw_files(tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in files] == [
        "a.csv",
        "nested/c.json",
    ]


def test_load_any_file_reads_csv_json_and_parquet(tmp_path: Path) -> None:
    expected = pl.DataFrame({"region": ["Kyiv"], "alerts": [3]})
    csv_path = tmp_path / "alerts.csv"
    json_path = tmp_path / "alerts.json"
    parquet_path = tmp_path / "alerts.parquet"
    unsupported_path = tmp_path / "alerts.txt"

    expected.write_csv(csv_path)
    expected.write_json(json_path)
    expected.write_parquet(parquet_path)
    unsupported_path.write_text("alerts", encoding="utf-8")

    assert load_any_file(csv_path).to_dict(as_series=False) == expected.to_dict(
        as_series=False
    )
    assert load_any_file(json_path).to_dict(as_series=False) == expected.to_dict(
        as_series=False
    )
    assert load_any_file(parquet_path).to_dict(as_series=False) == expected.to_dict(
        as_series=False
    )
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_any_file(unsupported_path)


def test_inspect_dataset_records_raw_schema_inventory(tmp_path: Path) -> None:
    (tmp_path / "alerts.csv").write_text(
        "region,alert_count\nKyiv,3\nLviv,2\n",
        encoding="utf-8",
    )

    inventory = inspect_dataset(tmp_path)

    assert inventory.select(
        "path",
        "rows",
        "column_count",
        "load_error",
    ).to_dicts() == [
        {
            "path": "alerts.csv",
            "rows": 2,
            "column_count": 2,
            "load_error": None,
        }
    ]
