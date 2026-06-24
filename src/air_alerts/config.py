from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
EXTERNAL_DIR = DATA_DIR / "external"

KYIV_TZ = "Europe/Kyiv"

DEFAULT_SLEEP_START_HOUR = 22
DEFAULT_SLEEP_END_HOUR = 7

DEFAULT_WORK_START_HOUR = 9
DEFAULT_WORK_END_HOUR = 18
