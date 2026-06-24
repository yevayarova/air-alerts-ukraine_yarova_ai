from __future__ import annotations

import argparse
from pathlib import Path

from air_alerts.cleaning import (
    build_clean_intervals,
    summarize_clean_intervals,
    write_clean_intervals,
)
from air_alerts.config import ALERTS_CLEAN_PATH, RAW_DATASET_DIR


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the canonical historical alert interval table."
    )
    parser.add_argument("--raw-dir", type=Path, default=RAW_DATASET_DIR)
    parser.add_argument("--output", type=Path, default=ALERTS_CLEAN_PATH)
    args = parser.parse_args()

    print("Stage: build clean alert intervals")
    clean_intervals = build_clean_intervals(args.raw_dir)
    write_clean_intervals(clean_intervals, args.output)

    summary = summarize_clean_intervals(clean_intervals)
    print(f"Rows: {summary['rows']}")
    print(f"Regions: {summary['regions']}")
    print(f"Coverage start: {summary['started_at_min']}")
    print(f"Coverage end: {summary['finished_at_max']}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
