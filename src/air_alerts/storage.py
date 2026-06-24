from __future__ import annotations

from pathlib import Path

import polars as pl


def write_parquet_atomic(df: pl.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")

    try:
        df.write_parquet(temp_path)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
