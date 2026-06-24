from pathlib import Path

import polars as pl


def list_raw_files(raw_dir: str | Path) -> list[Path]:
    raw_dir = Path(raw_dir)
    return sorted(
        [
            path
            for path in raw_dir.rglob("*")
            if path.suffix.lower() in {".csv", ".json", ".parquet"}
        ]
    )


def load_any_file(path: str | Path) -> pl.DataFrame:
    path = Path(path)

    if path.suffix.lower() == ".csv":
        return pl.read_csv(path)

    if path.suffix.lower() == ".json":
        return pl.read_json(path)

    if path.suffix.lower() == ".parquet":
        return pl.read_parquet(path)

    raise ValueError(f"Unsupported file type: {path}")


def inspect_dataset(raw_dir: str | Path) -> pl.DataFrame:
    rows = []

    for path in list_raw_files(raw_dir):
        try:
            df = load_any_file(path)
            rows.append(
                {
                    "path": str(path),
                    "rows": df.height,
                    "columns": ", ".join(df.columns),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "path": str(path),
                    "rows": None,
                    "columns": f"ERROR: {exc}",
                }
            )

    return pl.DataFrame(rows)
