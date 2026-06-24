from __future__ import annotations

import json
from pathlib import Path

import polars as pl

RAW_FILE_SUFFIXES = {".csv", ".json", ".jsonl", ".parquet"}

INVENTORY_SCHEMA = {
    "path": pl.String,
    "extension": pl.String,
    "size_bytes": pl.Int64,
    "rows": pl.Int64,
    "column_count": pl.Int64,
    "columns": pl.String,
    "dtypes": pl.String,
    "load_error": pl.String,
}


def list_raw_files(raw_dir: str | Path) -> list[Path]:
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        return []

    return sorted(
        path
        for path in raw_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in RAW_FILE_SUFFIXES
        and not _is_hidden_relative_path(path, raw_dir)
    )


def load_any_file(path: str | Path) -> pl.DataFrame:
    path = Path(path)

    if path.suffix.lower() == ".csv":
        return pl.read_csv(path)

    if path.suffix.lower() == ".json":
        return pl.read_json(path)

    if path.suffix.lower() == ".jsonl":
        return pl.read_ndjson(path)

    if path.suffix.lower() == ".parquet":
        return pl.read_parquet(path)

    raise ValueError(f"Unsupported file type: {path}")


def inspect_dataset(raw_dir: str | Path) -> pl.DataFrame:
    raw_dir = Path(raw_dir)
    rows = []

    for path in list_raw_files(raw_dir):
        relative_path = path.relative_to(raw_dir)
        base_row = {
            "path": relative_path.as_posix(),
            "extension": path.suffix.lower().lstrip("."),
            "size_bytes": path.stat().st_size,
        }

        try:
            df = load_any_file(path)
            rows.append(
                {
                    **base_row,
                    "rows": df.height,
                    "column_count": df.width,
                    "columns": json.dumps(df.columns, ensure_ascii=False),
                    "dtypes": json.dumps([str(dtype) for dtype in df.dtypes]),
                    "load_error": None,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    **base_row,
                    "rows": None,
                    "column_count": None,
                    "columns": None,
                    "dtypes": None,
                    "load_error": str(exc),
                }
            )

    return pl.DataFrame(rows, schema=INVENTORY_SCHEMA)


def _is_hidden_relative_path(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return any(part.startswith(".") for part in relative_parts)
