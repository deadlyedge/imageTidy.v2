from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

import settings
from imagetidy.planning import (
    FALLBACK_PROJECT_NAME,
    FALLBACK_TIME_RANGE_LABEL,
    build_categories,
    build_projects,
    categorize_extension,
    ensure_json,
    find_time_range,
    match_project,
    parse_date,
)

from openai import OpenAI

load_dotenv()


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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Configuration file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def call_ai_for_config(
    sample: list[dict[str, Any]], temperature: float, max_tokens: int
) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    openai_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY must be set to contact the configured LLM")

    payload = settings.AI_PROMPT.strip()
    payload += "\n\nSample data (JSON array):\n"
    payload += json.dumps(sample, ensure_ascii=False, indent=2)

    response = openai_client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[{"role": "user", "content": payload}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content

    if not content:
        raise SystemExit("AI did not return any content")

    return ensure_json(content)


def derive_target_filename(folder_chain: str, original_name: str) -> str:
    parts = [segment.strip() for segment in folder_chain.split(" / ") if segment.strip()]
    if not parts:
        return original_name
    return "-".join(parts + [original_name])


def build_plan_entries(
    metadata: list[dict[str, Any]],
    config: dict[str, Any],
    target_root: Path,
) -> tuple[list[dict[str, str]], list[str]]:
    if (
        "projects" not in config
        or "categories" not in config
        or "target_pattern" not in config
    ):
        raise KeyError(
            "Plan configuration missing required keys (projects, categories, target_pattern)"
        )

    projects = build_projects(config["projects"])
    categories = build_categories(config["categories"])
    pattern = config["target_pattern"]
    seen_targets: set[str] = set()
    entries: list[dict[str, str]] = []
    warnings: list[str] = []

    for record in metadata:
        folder_chain = record.get("folder_chain", "")
        candidate = match_project(folder_chain, projects)
        canonical = candidate.canonical_name if candidate else FALLBACK_PROJECT_NAME
        if not candidate:
            warnings.append(f"Could not match project for {record['full_path']}")
        modified_date = parse_date(record["modified_time"])
        assigned_range = FALLBACK_TIME_RANGE_LABEL
        if candidate:
            time_range = find_time_range(modified_date, candidate)
            if time_range:
                assigned_range = time_range.label
            else:
                # Use special folder for files outside time ranges
                category = "时间范围有出入"
                # Provide detailed reason for time range mismatch
                if candidate.time_ranges:
                    earliest_start = min(tr.start for tr in candidate.time_ranges)
                    latest_end = max(tr.end for tr in candidate.time_ranges)
                    if modified_date < earliest_start:
                        reason = f"file modified {modified_date} is before earliest project start {earliest_start}"
                    elif modified_date > latest_end:
                        reason = f"file modified {modified_date} is after latest project end {latest_end}"
                    else:
                        # Date is within overall range but not in any specific range
                        ranges_str = ", ".join(f"{tr.start}-{tr.end}" for tr in candidate.time_ranges)
                        reason = f"file modified {modified_date} not in any defined ranges: {ranges_str}"
                else:
                    reason = "project has no defined time ranges"
                # warnings.append(
                #     f"{record['full_path']} falls outside defined time ranges for {canonical}: {reason}"
                # )
        category = categorize_extension(record.get("file_ext", ""), categories)

        target_pattern = pattern.replace("<time-range>", assigned_range)
        target_pattern = target_pattern.replace("<project-name>", canonical)
        target_pattern = target_pattern.replace("<category>", category)

        target_dir = target_root / target_pattern
        base_name = Path(record["full_path"]).name
        tagged_name = derive_target_filename(folder_chain, base_name)
        new_path = target_dir / tagged_name
        note_parts = []
        if not candidate:
            note_parts.append("project fallback")
        if assigned_range == FALLBACK_TIME_RANGE_LABEL:
            note_parts.append("time range fallback")
        if str(new_path) in seen_targets:
            note_parts.append("target collision")
        seen_targets.add(str(new_path))

        entries.append(
            {
                "old_path": record["full_path"],
                "new_path": str(new_path),
                "project": canonical,
                "time_range": assigned_range,
                "category": category,
                "modified_time": record.get("modified_time", ""),
                "notes": "; ".join(note_parts) or "ok",
            }
        )
    return entries, warnings


def write_csv(entries: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "old_path",
        "new_path",
        "project",
        "time_range",
        "category",
        "modified_time",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)


def summarize(entries: list[dict[str, str]]) -> dict[str, Any]:
    projects = Counter(entry["project"] for entry in entries)
    categories = Counter(entry["category"] for entry in entries)
    time_ranges = Counter(entry["time_range"] for entry in entries)
    return {
        "entry_count": len(entries),
        "unique_projects": len(projects),
        "unique_categories": len(categories),
        "time_ranges": dict(time_ranges),
        "category_distribution": dict(categories),
        "project_distribution": dict(projects),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate move plan based on AI output."
    )
    parser.add_argument(
        "--metadata-file",
        type=Path,
        default=Path("output/metadata.json"),
        help="Collected metadata to analyze.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory where plans and logs will be stored.",
    )
    parser.add_argument(
        "--plan-path",
        type=Path,
        default=Path("output/move_plan.csv"),
        help="CSV that captures the reviewed move plan.",
    )
    parser.add_argument(
        "--config-output",
        type=Path,
        default=Path("output/plan_config.json"),
        help="Location to write the parsed plan configuration.",
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=Path(settings.SOURCE_FOLDER).parent
        / f"{Path(settings.SOURCE_FOLDER).name}-organized",
        help="Root directory that will house the tidied structure.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=200,
        help="Number of metadata samples to feed to the LLM.",
    )
    parser.add_argument(
        "--manual-config",
        type=Path,
        help="Skip LLM call and use an existing plan configuration.",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Do not call the LLM; requires --manual-config.",
    )
    parser.add_argument(
        "--ai-temperature",
        type=float,
        default=0.0,
        help="Temperature for the LLM call.",
    )
    parser.add_argument(
        "--ai-max-tokens", type=int, default=1500, help="Max tokens for the LLM call."
    )
    args = parser.parse_args()

    if args.no_ai and not args.manual_config:
        raise SystemExit("--no-ai requires --manual-config to be provided")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / "generate_plan.log"
    setup_logging(log_path)

    if not args.metadata_file.exists():
        raise SystemExit(f"Metadata file not found: {args.metadata_file}")
    metadata = json.loads(args.metadata_file.read_text(encoding="utf-8"))
    if not isinstance(metadata, list):
        raise SystemExit("Metadata file must contain a JSON array")

    sample_size = max(1, min(len(metadata), args.sample_size))
    sample = metadata[:sample_size]

    if args.manual_config:
        config = load_json(args.manual_config)
    elif args.no_ai:
        raise SystemExit("Either provide --manual-config or allow AI lookup")
    else:
        config = call_ai_for_config(sample, args.ai_temperature, args.ai_max_tokens)

    config_output = args.config_output
    config_output.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logging.info("Plan configuration saved to %s", config_output)

    entries, warnings = build_plan_entries(metadata, config, args.target_root)
    write_csv(entries, args.plan_path)
    summary = summarize(entries)
    summary.update(
        {
            "target_root": str(args.target_root),
            "generated_at": datetime.now(UTC).isoformat(),
            "metadata_count": len(metadata),
            "warnings": warnings,
        }
    )
    summary_path = args.output_dir / "plan_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logging.info("Plan written to %s (%d entries)", args.plan_path, len(entries))
    logging.info("Summary written to %s", summary_path)
    for warning in warnings:
        logging.warning(warning)


if __name__ == "__main__":
    main()
