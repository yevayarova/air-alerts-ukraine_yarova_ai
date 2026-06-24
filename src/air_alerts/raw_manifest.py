from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from air_alerts.config import (
    EXPECTED_RAW_DATA_FILES,
    PROJECT_ROOT,
    RAW_DATASET_DIR,
    VADIMKIN_REPOSITORY_URL,
    VADIMKIN_ZIP_URL,
)


def expected_file_status(dataset_dir: Path) -> list[dict]:
    files = []
    for relative_path in EXPECTED_RAW_DATA_FILES:
        path = dataset_dir / relative_path
        files.append(
            {
                "path": relative_path,
                "exists": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else None,
            }
        )
    return files


def missing_expected_files(dataset_dir: Path) -> list[str]:
    return [
        file_info["path"]
        for file_info in expected_file_status(dataset_dir)
        if not file_info["exists"]
    ]


def build_manifest(
    *,
    dataset_dir: Path = RAW_DATASET_DIR,
    archive_final_url: str | None = None,
    archive_sha256: str | None = None,
    archive_size_bytes: int | None = None,
    downloaded_at_utc: str | None = None,
    previous_manifest: dict | None = None,
) -> dict:
    previous_manifest = previous_manifest or {}
    files = expected_file_status(dataset_dir)
    missing_files = [file_info["path"] for file_info in files if not file_info["exists"]]

    return {
        "source": "vadimkin",
        "source_name": "Ukrainian Air Raid Sirens Dataset",
        "repository_url": VADIMKIN_REPOSITORY_URL,
        "archive_url": VADIMKIN_ZIP_URL,
        "archive_final_url": archive_final_url
        if archive_final_url is not None
        else previous_manifest.get("archive_final_url"),
        "archive_sha256": archive_sha256
        if archive_sha256 is not None
        else previous_manifest.get("archive_sha256"),
        "archive_size_bytes": archive_size_bytes
        if archive_size_bytes is not None
        else previous_manifest.get("archive_size_bytes"),
        "downloaded_at_utc": downloaded_at_utc
        if downloaded_at_utc is not None
        else previous_manifest.get("downloaded_at_utc"),
        "manifest_created_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_path": _display_path(dataset_dir),
        "expected_files_present": not missing_files,
        "missing_expected_files": missing_files,
        "files": files,
    }


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
