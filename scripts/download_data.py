from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

VADIMKIN_URL = (
    "https://github.com/Vadimkin/ukrainian-air-raid-sirens-dataset/"
    "archive/refs/heads/main.zip"
)

DATASET_DIR = RAW_DIR / "ukrainian-air-raid-sirens-dataset"
ZIP_PATH = RAW_DIR / "sirens_dataset.zip"
MANIFEST_PATH = RAW_DIR / "manifest.json"


def download_file(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with output_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)


def extract_zip(zip_path: Path, output_dir: Path) -> None:
    temp_extract_dir = RAW_DIR / "_tmp_extract"

    if temp_extract_dir.exists():
        shutil.rmtree(temp_extract_dir)

    temp_extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(temp_extract_dir)

    extracted_dirs = [p for p in temp_extract_dir.iterdir() if p.is_dir()]
    if len(extracted_dirs) != 1:
        raise RuntimeError(f"Expected one extracted directory, found: {extracted_dirs}")

    extracted_root = extracted_dirs[0]

    if output_dir.exists():
        shutil.rmtree(output_dir)

    shutil.move(str(extracted_root), str(output_dir))
    shutil.rmtree(temp_extract_dir)


def build_manifest() -> dict:
    expected_files = [
        "datasets/official_data_en.csv",
        "datasets/official_data_uk.csv",
        "datasets/volunteer_data_en.csv",
        "datasets/volunteer_data_uk.csv",
    ]

    files = []
    for relative_path in expected_files:
        path = DATASET_DIR / relative_path
        files.append(
            {
                "path": relative_path,
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
            }
        )

    return {
        "source": "vadimkin_ukrainian_air_raid_sirens_dataset",
        "source_url": VADIMKIN_URL,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_path": str(DATASET_DIR.relative_to(PROJECT_ROOT)),
        "files": files,
    }


def write_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def download_vadimkin_dataset(force: bool = False) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if DATASET_DIR.exists() and not force:
        print(f"Dataset already exists: {DATASET_DIR}")
        print("Use --force to re-download.")
    else:
        print(f"Downloading: {VADIMKIN_URL}")
        download_file(VADIMKIN_URL, ZIP_PATH)

        print(f"Extracting to: {DATASET_DIR}")
        extract_zip(ZIP_PATH, DATASET_DIR)

        if ZIP_PATH.exists():
            ZIP_PATH.unlink()

    manifest = build_manifest()
    write_manifest(manifest)

    missing = [file["path"] for file in manifest["files"] if not file["exists"]]
    if missing:
        raise RuntimeError(f"Missing expected files: {missing}")

    print(f"Manifest written: {MANIFEST_PATH}")
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
