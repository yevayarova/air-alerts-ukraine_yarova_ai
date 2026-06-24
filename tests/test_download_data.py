from pathlib import Path

from air_alerts.config import EXPECTED_RAW_DATA_FILES
from air_alerts.raw_manifest import build_manifest, missing_expected_files


def test_missing_expected_files_reports_absent_raw_sources(tmp_path: Path) -> None:
    present_file = tmp_path / EXPECTED_RAW_DATA_FILES[0]
    present_file.parent.mkdir(parents=True)
    present_file.write_text("region,started_at\nKyiv,2022-01-01\n", encoding="utf-8")

    missing = missing_expected_files(tmp_path)

    assert EXPECTED_RAW_DATA_FILES[0] not in missing
    assert set(missing) == set(EXPECTED_RAW_DATA_FILES[1:])


def test_manifest_records_expected_file_check(tmp_path: Path) -> None:
    for relative_path in EXPECTED_RAW_DATA_FILES:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("region,started_at\nKyiv,2022-01-01\n", encoding="utf-8")

    manifest = build_manifest(dataset_dir=tmp_path)

    assert manifest["expected_files_present"] is True
    assert manifest["missing_expected_files"] == []
    assert [file_info["path"] for file_info in manifest["files"]] == list(
        EXPECTED_RAW_DATA_FILES
    )
