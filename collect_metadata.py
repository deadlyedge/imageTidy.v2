from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import settings


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def collect(source: Path) -> list[dict]:
    results: list[dict] = []
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        folder_chain = " / ".join(rel.parts[:-1])
        modified_time = datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
        results.append(
            {
                "full_path": str(path.resolve()),
                "folder_chain": folder_chain,
                "file_ext": path.suffix.lower(),
                "modified_time": modified_time,
            }
        )
    results.sort(key=lambda entry: entry["full_path"])
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect metadata from SOURCE_FOLDER.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory where metadata artifacts are written.",
    )
    parser.add_argument("--sample-size", type=int, default=500, help="How many entries to keep for AI sampling.")
    parser.add_argument("--source", type=Path, help="Override SOURCE_FOLDER from settings.")
    args = parser.parse_args()

    source_folder = args.source or Path(settings.SOURCE_FOLDER)
    if not source_folder.exists():
        raise SystemExit(f"Source folder not found: {source_folder}")
    if args.sample_size <= 0:
        raise SystemExit("sample-size must be greater than zero")
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "collect_metadata.log"
    setup_logging(log_path)

    logging.info("Scanning %s", source_folder)
    metadata = collect(source_folder)
    metadata_path = output_dir / "metadata.json"
    sample_path = output_dir / "metadata_sample.json"

    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    sample = metadata[: min(len(metadata), args.sample_size)]
    sample_path.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")

    logging.info("Collected %d files", len(metadata))
    logging.info("Sample (%d) written to %s", len(sample), sample_path)
    logging.info("Full metadata written to %s", metadata_path)


if __name__ == "__main__":
    main()
