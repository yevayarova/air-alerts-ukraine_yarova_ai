from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
EXTERNAL_DIR = DATA_DIR / "external"

RAW_DATASET_NAME = "ukrainian-air-raid-sirens-dataset"
RAW_DATASET_DIR = RAW_DIR / RAW_DATASET_NAME
RAW_MANIFEST_PATH = RAW_DIR / "manifest.json"
RAW_FILE_INVENTORY_PATH = INTERIM_DIR / "raw_file_inventory.csv"
ALERTS_CLEAN_PATH = PROCESSED_DIR / "alerts_clean.parquet"

VADIMKIN_REPOSITORY_URL = (
    "https://github.com/Vadimkin/ukrainian-air-raid-sirens-dataset"
)
VADIMKIN_ZIP_URL = f"{VADIMKIN_REPOSITORY_URL}/archive/refs/heads/main.zip"

EXPECTED_RAW_DATA_FILES = (
    "datasets/official_data_en.csv",
    "datasets/official_data_uk.csv",
    "datasets/volunteer_data_en.csv",
    "datasets/volunteer_data_uk.csv",
)

KYIV_TZ = "Europe/Kyiv"

DEFAULT_SLEEP_START_HOUR = 22
DEFAULT_SLEEP_END_HOUR = 7

DEFAULT_WORK_START_HOUR = 9
DEFAULT_WORK_END_HOUR = 18
