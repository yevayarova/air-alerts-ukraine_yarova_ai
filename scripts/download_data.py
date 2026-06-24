from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from air_alerts.config import (
    RAW_DATASET_DIR,
    RAW_DATASET_NAME,
    RAW_DIR,
    RAW_MANIFEST_PATH,
    VADIMKIN_ZIP_URL,
)
from air_alerts.raw_manifest import build_manifest

TEMP_EXTRACT_DIR = RAW_DIR / "_tmp_extract"
TEMP_ZIP_PATH = RAW_DIR / f"{RAW_DATASET_NAME}.zip"


@dataclass(frozen=True)
class DownloadResult:
    requested_url: str
    final_url: str
    size_bytes: int
    sha256: str


def download_file(url: str, output_path: Path) -> DownloadResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256()
    size_bytes = 0

    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with output_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    sha256.update(chunk)
                    size_bytes += len(chunk)
                    file.write(chunk)

        return DownloadResult(
            requested_url=url,
            final_url=response.url,
            size_bytes=size_bytes,
            sha256=sha256.hexdigest(),
        )


def extract_zip(zip_path: Path, output_dir: Path) -> None:
    if TEMP_EXTRACT_DIR.exists():
        shutil.rmtree(TEMP_EXTRACT_DIR)

    TEMP_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            _safe_extract(zip_ref, TEMP_EXTRACT_DIR)

        extracted_dirs = [path for path in TEMP_EXTRACT_DIR.iterdir() if path.is_dir()]
        if len(extracted_dirs) != 1:
            raise RuntimeError(f"Expected one extracted directory, found: {extracted_dirs}")

        extracted_root = extracted_dirs[0]

        if output_dir.exists():
            shutil.rmtree(output_dir)

        shutil.move(str(extracted_root), str(output_dir))
    finally:
        if TEMP_EXTRACT_DIR.exists():
            shutil.rmtree(TEMP_EXTRACT_DIR)


def _safe_extract(zip_ref: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in zip_ref.infolist():
        target = (destination / member.filename).resolve()
        if destination not in target.parents and target != destination:
            raise RuntimeError(f"Refusing to extract unsafe ZIP member: {member.filename}")
    zip_ref.extractall(destination)


def read_existing_manifest() -> dict:
    if not RAW_MANIFEST_PATH.exists():
        return {}
    return json.loads(RAW_MANIFEST_PATH.read_text(encoding="utf-8"))


def write_manifest(manifest: dict) -> None:
    RAW_MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def download_vadimkin_dataset(force: bool = False) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    previous_manifest = read_existing_manifest()
    download_result = None

    try:
        if RAW_DATASET_DIR.exists() and not force:
            print(f"Dataset already exists: {RAW_DATASET_DIR}")
            print("Validating local snapshot.")
        else:
            print(f"Downloading: {VADIMKIN_ZIP_URL}")
            download_result = download_file(VADIMKIN_ZIP_URL, TEMP_ZIP_PATH)

            print(f"Extracting to: {RAW_DATASET_DIR}")
            extract_zip(TEMP_ZIP_PATH, RAW_DATASET_DIR)
    finally:
        if TEMP_ZIP_PATH.exists():
            TEMP_ZIP_PATH.unlink()

    nested_git_dirs = list(RAW_DATASET_DIR.rglob(".git"))
    if nested_git_dirs:
        raise RuntimeError(f"Nested git metadata found in raw data: {nested_git_dirs}")

    downloaded_at_utc = (
        datetime.now(timezone.utc).isoformat()
        if download_result is not None
        else previous_manifest.get("downloaded_at_utc")
    )
    manifest = build_manifest(
        dataset_dir=RAW_DATASET_DIR,
        archive_final_url=download_result.final_url if download_result else None,
        archive_sha256=download_result.sha256 if download_result else None,
        archive_size_bytes=download_result.size_bytes if download_result else None,
        downloaded_at_utc=downloaded_at_utc,
        previous_manifest=previous_manifest,
    )
    write_manifest(manifest)

    if manifest["missing_expected_files"]:
        raise RuntimeError(
            f"Missing expected files: {manifest['missing_expected_files']}. "
            "Use --force to re-download the raw snapshot."
        )

    if RAW_DATASET_DIR.exists() and download_result is None:
        print("Use --force to re-download.")

    print(f"Manifest written: {RAW_MANIFEST_PATH}")
    print("Data download/check complete.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="vadimkin", choices=["vadimkin"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.source == "vadimkin":
        download_vadimkin_dataset(force=args.force)


if __name__ == "__main__":
    main()
