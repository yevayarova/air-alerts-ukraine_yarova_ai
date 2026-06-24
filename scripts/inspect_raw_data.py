from __future__ import annotations

from air_alerts.config import RAW_DATASET_DIR, RAW_FILE_INVENTORY_PATH
from air_alerts.data_sources import inspect_dataset


def main() -> None:
    df = inspect_dataset(RAW_DATASET_DIR)
    print(df)

    RAW_FILE_INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(RAW_FILE_INVENTORY_PATH)

    print(f"Saved: {RAW_FILE_INVENTORY_PATH}")


if __name__ == "__main__":
    main()
