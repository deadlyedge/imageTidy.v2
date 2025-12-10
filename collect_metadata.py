from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, date
from pathlib import Path
from typing import Iterable

import settings


FOLDER_FILTER = re.compile(r"^新建文件夹(?: \(\d+\))?$")


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


def sanitize_folder_chain(parts: Iterable[str]) -> list[str]:
    return [part for part in parts if not FOLDER_FILTER.match(part)]


def register_chain(folder_stats: dict[str, dict], chain: str) -> None:
    parts = chain.split(" / ")
    current_parts: list[str] = []
    for part in parts:
        current_parts.append(part)
        key = " / ".join(current_parts)
        folder_stats.setdefault(
            key,
            {
                "file_count": 0,
                "extensions": Counter(),
                "min_date": None,
                "max_date": None,
            },
        )


def update_date_stats(stats: dict, current: date) -> None:
    min_date = stats["min_date"]
    max_date = stats["max_date"]
    if min_date is None or current < min_date:
        stats["min_date"] = current
    if max_date is None or current > max_date:
        stats["max_date"] = current


def build_folder_summary(metadata: list[dict], root_name: str) -> dict[str, object]:
    folder_stats: dict[str, dict] = {}
    child_map: dict[str, set[str]] = defaultdict(set)

    for entry in metadata:
        chain = entry["folder_chain"]
        register_chain(folder_stats, chain)
        stats = folder_stats[chain]
        stats["file_count"] += 1
        stats["extensions"][entry["file_ext"]] += 1
        mod_date = datetime.fromisoformat(entry["modified_time"]).date()
        update_date_stats(stats, mod_date)

    if root_name not in folder_stats:
        folder_stats[root_name] = {
            "file_count": 0,
            "extensions": Counter(),
            "min_date": None,
            "max_date": None,
        }

    for chain in list(folder_stats):
        if " / " in chain:
            parent = chain.rsplit(" / ", 1)[0]
            child_map[parent].add(chain)
        elif chain != root_name:
            child_map[root_name].add(chain)

    nodes: list[dict] = []
    for chain in sorted(folder_stats):
        stats = folder_stats[chain]
        node = {
            "folder_chain": chain,
            "folder_name": chain.split(" / ")[-1] if chain else "",
            "depth": chain.count(" / ") + 1 if chain else 0,
            "file_count": stats["file_count"],
            "extensions": {ext: count for ext, count in sorted(stats["extensions"].items())},
            "children": sorted(child_map.get(chain, [])),
            "min_date": stats["min_date"].isoformat() if stats["min_date"] else None,
            "max_date": stats["max_date"].isoformat() if stats["max_date"] else None,
        }
        nodes.append(node)

    return {
        "root": root_name,
        "node_count": len(nodes),
        "folders": nodes,
    }


def collect(source: Path) -> list[dict]:
    results: list[dict] = []
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        raw_parts = list(rel.parts[:-1])
        sanitized = sanitize_folder_chain(raw_parts)
        if sanitized:
            folder_parts = sanitized
        else:
            folder_parts = [source.name]
        folder_chain = " / ".join(folder_parts)
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
    parser.add_argument("--source", type=Path, help="Override SOURCE_FOLDER from settings.")
    args = parser.parse_args()

    source_folder = args.source or Path(settings.SOURCE_FOLDER)
    if not source_folder.exists():
        raise SystemExit(f"Source folder not found: {source_folder}")
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "collect_metadata.log"
    setup_logging(log_path)

    logging.info("Scanning %s", source_folder)
    metadata = collect(source_folder)
    metadata_path = output_dir / "metadata.json"
    summary_path = output_dir / "folder_summary.json"

    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = build_folder_summary(metadata, source_folder.name)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    logging.info("Collected %d files", len(metadata))
    logging.info("Metadata written to %s", metadata_path)
    logging.info("Folder summary written to %s", summary_path)


if __name__ == "__main__":
    main()
